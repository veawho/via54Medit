// Package router - PICO extraction.
//
// PICO = Population / Intervention / Comparator / Outcome, the standard
// framework for clinical research questions (per Cochrane Handbook).
//
// Phase 3 implementation: ask an LLM to extract the four elements from
// a natural-language question. The LLM must return valid JSON; we parse
// it strictly and fall back to a heuristic (regex-based) extraction
// when the LLM call fails.
//
// The LLM call is OPTIONAL — if r.LLM is nil, we use heuristics only.
// This keeps PICO extraction working in air-gapped environments.
package router

import (
	"context"
	"encoding/json"
	"fmt"
	"regexp"
	"strings"

	"github.com/veawho/via54Medit/pkg/types"
)

// picoPrompt is the system prompt that asks the LLM to extract PICO.
// The strict JSON instruction is critical — we parse the response
// with no fuzziness.
const picoPrompt = `You are an EBM (Evidence-Based Medicine) assistant.
Extract the PICO elements from the user's clinical question.

Return ONLY valid JSON in this exact format (no markdown, no commentary):
{"population":"...","intervention":"...","comparator":"...","outcome":"..."}

Rules:
- If an element is not mentioned in the question, use empty string "".
- "Population" = the patient group (e.g. "type 2 diabetes with heart failure").
- "Intervention" = the treatment/exposure (e.g. "SGLT2 inhibitors").
- "Comparator" = what is being compared (e.g. "placebo", or "" if not stated).
- "Outcome" = the endpoint of interest (e.g. "cardiovascular death", "HbA1c").
- Be concise: 2-8 words per element.
- Use English unless the user wrote in Chinese (then use Chinese).

User question: `

// ExtractPICO pulls PICO out of a clinical question.
// Tries LLM first; on failure, falls back to regex heuristics.
func (r *Router) ExtractPICO(ctx context.Context, question string) (*types.PICO, error) {
	if strings.TrimSpace(question) == "" {
		return nil, fmt.Errorf("pico: empty question")
	}

	if r.LLM != nil {
		pico, err := r.llmExtractPICO(ctx, question)
		if err == nil && pico != nil {
			return pico, nil
		}
		// LLM failed or returned nil — fall through to heuristics.
	}
	return heuristicPICO(question), nil
}

// llmExtractPICO calls the LLM and parses its JSON response.
func (r *Router) llmExtractPICO(ctx context.Context, question string) (*types.PICO, error) {
	system := picoPrompt
	user := question
	raw, err := r.LLM.Complete(ctx, system, user)
	if err != nil {
		return nil, fmt.Errorf("pico: LLM: %w", err)
	}
	// Strip code fences if the LLM wrapped the JSON.
	cleaned := stripCodeFence(raw)
	var got struct {
		Population   string `json:"population"`
		Intervention string `json:"intervention"`
		Comparator   string `json:"comparator"`
		Outcome      string `json:"outcome"`
	}
	if err := json.Unmarshal([]byte(cleaned), &got); err != nil {
		return nil, fmt.Errorf("pico: parse LLM JSON: %w (raw: %q)", err, truncate(raw, 200))
	}
	return &types.PICO{
		Population:   strings.TrimSpace(got.Population),
		Intervention: strings.TrimSpace(got.Intervention),
		Comparator:   strings.TrimSpace(got.Comparator),
		Outcome:      strings.TrimSpace(got.Outcome),
	}, nil
}

// stripCodeFence removes ```json ... ``` wrappers that some LLMs add.
func stripCodeFence(s string) string {
	s = strings.TrimSpace(s)
	for _, fence := range []string{"```json", "```JSON", "```"} {
		if strings.HasPrefix(s, fence) {
			s = strings.TrimPrefix(s, fence)
			break
		}
	}
	if strings.HasSuffix(s, "```") {
		s = strings.TrimSuffix(s, "```")
	}
	return strings.TrimSpace(s)
}

// truncate returns the first n bytes of s, with "..." if longer.
// (Duplicate of source.truncate — kept local to avoid cross-package
// dependency from router into source.)
func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}

// heuristicPICO does a best-effort extraction using common medical
// query patterns. It looks for "vs" / "compared to" for the comparator
// and falls back to marking the whole question as the "intervention".
//
// This is intentionally simple — it's a fallback for when the LLM
// is unavailable. The returned PICO may have all-empty fields, in
// which case the caller should retry with an LLM.
func heuristicPICO(question string) *types.PICO {
	q := strings.ToLower(question)
	pico := &types.PICO{
		Population:   extractPopulationHeuristic(q),
		Intervention: extractInterventionHeuristic(q),
		Comparator:   extractComparatorHeuristic(q),
		Outcome:      extractOutcomeHeuristic(q),
	}
	return pico
}

// --- heuristic extractors (very simple, Phase 3 placeholder for a
// real keyword-based extractor) ---

// commonPats are common English/Chinese markers for PICO components.
var (
	// We split on the first occurrence of any of these markers.
	// Order matters: longer markers first to avoid partial matches
	// ("compared to" before "compare").
	// We do NOT use \b because Chinese characters don't have ASCII
	// word boundaries; instead we look for the marker as a substring
	// surrounded by whitespace, punctuation, or string start/end.
	vsPattern    = regexp.MustCompile(`(?i)(?:^|\s|[,.;:?!])(vs\.?|versus|compared\s+to|compared\s+with|与|和|对比)(?:\s|[,.;:?!]|$)`)
	outcomeWords = []string{"mortality", "survival", "outcome", "death", "risk", "adverse",
		"efficacy", "safety", "recurrence", "progression", "remission",
		"心血管死亡", "全因死亡", "住院", "不良事件", "复发", "缓解率"}
	popWords = []string{"patient", "patients", "adult", "adults", "children", "men", "women",
		"糖尿病", "心衰", "高血压", "肿瘤", "抑郁"}
	intWords = []string{"aspirin", "statin", "metformin", "insulin", "vaccine", "surgery",
		"chemotherapy", "radiation", "therapy", "treatment",
		"阿司匹林", "他汀", "二甲双胍", "胰岛素", "免疫治疗", "手术"}
)

func extractPopulationHeuristic(q string) string {
	for _, w := range popWords {
		if strings.Contains(q, w) {
			return extractNounPhrase(q, w)
		}
	}
	return ""
}

func extractInterventionHeuristic(q string) string {
	// Look for "X vs Y" — X is often the intervention.
	if loc := vsPattern.FindStringIndex(q); loc != nil {
		// The chunk before "vs" is likely the intervention.
		return strings.TrimSpace(q[:loc[0]])
	}
	for _, w := range intWords {
		if strings.Contains(q, w) {
			return extractNounPhrase(q, w)
		}
	}
	return ""
}

func extractComparatorHeuristic(q string) string {
	if loc := vsPattern.FindStringIndex(q); loc != nil {
		// The chunk after "vs" is likely the comparator.
		after := q[loc[1]:]
		// Trim to first punctuation/comma.
		for i, r := range after {
			if r == ',' || r == '?' || r == ';' {
				return strings.TrimSpace(after[:i])
			}
		}
		return strings.TrimSpace(after)
	}
	return ""
}

func extractOutcomeHeuristic(q string) string {
	for _, w := range outcomeWords {
		if strings.Contains(q, w) {
			return extractNounPhrase(q, w)
		}
	}
	return ""
}

// extractNounPhrase pulls a 1-3 word phrase around the given keyword.
// Very rough — Phase 3 placeholder.
func extractNounPhrase(q, keyword string) string {
	idx := strings.Index(q, keyword)
	if idx < 0 {
		return keyword
	}
	// Take the keyword plus 1 word before and 1 word after, when available.
	words := strings.Fields(q)
	for i, w := range words {
		// Strip punctuation for matching.
		wClean := strings.Trim(w, ",.?:;")
		if strings.Contains(wClean, keyword) || strings.Contains(keyword, wClean) {
			parts := []string{wClean}
			if i > 0 {
				parts = append([]string{strings.Trim(words[i-1], ",.?:;")}, parts...)
			}
			if i+1 < len(words) {
				parts = append(parts, strings.Trim(words[i+1], ",.?:;"))
			}
			return strings.Join(parts, " ")
		}
	}
	return keyword
}
