// Package docproc converts raw medical documents (PDF, HTML, text) into
// structured data: extracted entities (symptoms, medications, lab values,
// diagnoses), SOAP-format summaries, and FHIR-compatible JSON.
//
// Architecture inspired by:
//   - medical-document-processor (workflow ingest→extract→summarize→structure)
//   - OpenClaw-Medical-Skills clinical-nlp-extractor (NER)
//   - OpenClaw-Medical-Skills clinical-note-summarization (SOAP)
//
// Pipeline:
//  1. TextExtractor — PDF → text (pdftotext), HTML → text (strip tags), text → text
//  2. EntityExtractor — LLM-based NER for medical entities
//  3. SoapSummarizer — LLM-based SOAP format summarization
//  4. Pipeline — chains all three stages
//
// Design decisions:
//   - LLM-based entity extraction (higher recall than regex for clinical text)
//   - Explicit JSON schema enforcement via LLM prompt
//   - FHIR-compatible output schema for downstream integration
//   - PHI guardrails: flag PHI, never invent missing data
package docproc

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/veawho/via54Medit/internal/foundation"
)

// ---------------------------------------------------------------------------
// Pipeline — orchestrator
// ---------------------------------------------------------------------------

// Pipeline chains text extraction → entity extraction → SOAP summarization.
type Pipeline struct {
	llm     foundation.LLMProvider
	textExt *TextExtractor
	nerExt  *EntityExtractor
	soapExt *SoapSummarizer
}

// NewPipeline creates a document processing pipeline.
func NewPipeline(llm foundation.LLMProvider) *Pipeline {
	return &Pipeline{
		llm:     llm,
		textExt: NewTextExtractor(),
		nerExt:  NewEntityExtractor(llm),
		soapExt: NewSoapSummarizer(llm),
	}
}

// NewPipelineWithEntityOnly creates a pipeline that only does entity extraction
// (skips SOAP summarization). Useful when the downstream consumer only needs
// structured entities.
func NewPipelineWithEntityOnly(llm foundation.LLMProvider) *Pipeline {
	return &Pipeline{
		llm:     llm,
		textExt: NewTextExtractor(),
		nerExt:  NewEntityExtractor(llm),
		soapExt: nil,
	}
}

// Result holds the output of the full pipeline.
type Result struct {
	RawText  string             `json:"raw_text"`
	Entities *ExtractedEntities `json:"entities,omitempty"`
	Soap     *SoapSummary       `json:"soap,omitempty"`
	Errors   []string           `json:"errors,omitempty"`
	Duration time.Duration      `json:"-"`
}

// Process runs the full pipeline on a file path.
func (p *Pipeline) Process(ctx context.Context, path string) (*Result, error) {
	start := time.Now()
	res := &Result{}

	// Stage 1: extract text from file
	text, err := p.textExt.Extract(ctx, path)
	if err != nil {
		return nil, fmt.Errorf("docproc: text extraction failed: %w", err)
	}
	res.RawText = text

	// Stage 2: entity extraction (LLM)
	entities, err := p.nerExt.Extract(ctx, text)
	if err != nil {
		res.Errors = append(res.Errors, fmt.Sprintf("entity extraction failed: %v", err))
	} else {
		res.Entities = entities
	}

	// Stage 3: SOAP summarization (LLM, optional)
	if p.soapExt != nil {
		soap, err := p.soapExt.Summarize(ctx, text)
		if err != nil {
			// SOAP failure is non-fatal if entities succeeded
			res.Errors = append(res.Errors, fmt.Sprintf("soap summarization failed: %v", err))
		} else {
			res.Soap = soap
		}
	}

	res.Duration = time.Since(start)
	return res, nil
}

// ---------------------------------------------------------------------------
// TextExtractor — converts PDF/HTML/text files to plain text
// ---------------------------------------------------------------------------

// TextExtractor converts medical documents to plain text.
type TextExtractor struct {
	// PdftotextBin is the path to the pdftotext binary (poppler-utils).
	// Empty means "use pdftotext from PATH".
	PdftotextBin string
	// MaxChars is the maximum number of characters to return.
	// 0 means no limit.
	MaxChars int
}

// NewTextExtractor creates a new TextExtractor.
func NewTextExtractor() *TextExtractor {
	return &TextExtractor{
		MaxChars: 0,
	}
}

// Extract reads a file and returns its plain text content.
// Supported formats: .pdf (via pdftotext), .html (via goquery), .txt (direct read).
func (e *TextExtractor) Extract(ctx context.Context, path string) (string, error) {
	ext := strings.ToLower(filepath.Ext(path))
	switch ext {
	case ".pdf":
		return e.extractPDF(ctx, path)
	case ".html", ".htm":
		return e.extractHTML(ctx, path)
	case ".txt", ".md":
		return e.extractText(ctx, path)
	default:
		return e.extractText(ctx, path)
	}
}

// extractPDF uses pdftotext to convert a PDF to plain text.
// Falls back to pdftotext in PATH if PdftotextBin is empty.
func (e *TextExtractor) extractPDF(ctx context.Context, path string) (string, error) {
	bin := e.PdftotextBin
	if bin == "" {
		bin = "pdftotext"
	}

	// Verify the binary exists
	_, err := exec.LookPath(bin)
	if err != nil {
		return "", fmt.Errorf("pdftotext not found (install poppler-utils: brew install poppler)")
	}

	// pdftotext file - (outputs to stdout)
	cmd := exec.CommandContext(ctx, bin, "-layout", path, "-")
	cmd.Cancel = func() error {
		if cmd.Process != nil {
			return cmd.Process.Kill()
		}
		return nil
	}
	data, err := cmd.Output()
	if err != nil {
		return "", fmt.Errorf("pdftotext failed: %w", err)
	}

	text := string(data)

	// Clean up excessive blank lines (more than 2 consecutive newlines)
	text = reBlankLines.ReplaceAllString(text, "\n\n")

	if e.MaxChars > 0 && len(text) > e.MaxChars {
		text = text[:e.MaxChars]
	}
	return text, nil
}

// extractHTML reads an HTML file and strips tags using goquery.
func (e *TextExtractor) extractHTML(ctx context.Context, path string) (string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}

	doc, err := goquery.NewDocumentFromReader(strings.NewReader(string(data)))
	if err != nil {
		return "", fmt.Errorf("goquery parse failed: %w", err)
	}

	// Remove scripts and styles
	doc.Find("script, style, nav, footer, header").Remove()

	var lines []string
	doc.Find("p, h1, h2, h3, h4, h5, h6, li, div").Each(func(i int, sel *goquery.Selection) {
		text := sel.Text()
		text = strings.TrimSpace(text)
		if text != "" {
			lines = append(lines, text)
		}
	})

	result := strings.Join(lines, "\n\n")
	if e.MaxChars > 0 && len(result) > e.MaxChars {
		result = result[:e.MaxChars]
	}
	return result, nil
}

// extractText reads a plain text file directly.
func (e *TextExtractor) extractText(ctx context.Context, path string) (string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}

	text := string(data)
	if e.MaxChars > 0 && len(text) > e.MaxChars {
		text = text[:e.MaxChars]
	}
	return text, nil
}

// ---------------------------------------------------------------------------
// EntityExtractor — LLM-based NER for medical entities
// ---------------------------------------------------------------------------

// ExtractedEntities holds the structured entities extracted from clinical text.
type ExtractedEntities struct {
	Symptoms       []Symptom    `json:"symptoms"`
	Medications    []Medication `json:"medications"`
	LabValues      []LabValue   `json:"lab_values"`
	Diagnoses      []Diagnosis  `json:"diagnoses"`
	VitalSigns     []VitalSign  `json:"vital_signs"`
	Procedures     []Procedure  `json:"procedures"`
	ActionItems    []ActionItem `json:"action_items"`
	Contradictions []string     `json:"contradictions"`
	MissingInfo    []string     `json:"missing_info"`
	PHIFlags       []string     `json:"phi_flags"`
}

// Symptom represents an extracted symptom.
type Symptom struct {
	Name        string `json:"name"`
	Severity    string `json:"severity"` // mild / moderate / severe
	Duration    string `json:"duration"`
	Onset       string `json:"onset"`
	Progression string `json:"progression"` // improving / stable / worsening
	Context     string `json:"context"`
}

// Medication represents an extracted medication.
type Medication struct {
	Name      string `json:"name"`
	Dosage    string `json:"dosage"`
	Frequency string `json:"frequency"`
	Route     string `json:"route"`
	Context   string `json:"context"` // new / existing / stopped
}

// LabValue represents an extracted lab result.
type LabValue struct {
	Type        string `json:"type"` // blood_pressure / glucose / cholesterol / ...
	Value       string `json:"value"`
	Unit        string `json:"unit"`
	Timestamp   string `json:"timestamp"`
	NormalRange string `json:"normal_range"`
	Abnormal    bool   `json:"abnormal"`
}

// Diagnosis represents an extracted diagnosis.
type Diagnosis struct {
	Name    string `json:"name"`
	Context string `json:"context"` // confirmed / suspected / ruled_out
}

// VitalSign represents an extracted vital sign.
type VitalSign struct {
	Type      string `json:"type"` // temperature / heart_rate / respiratory_rate / oxygen_saturation / blood_pressure
	Value     string `json:"value"`
	Unit      string `json:"unit"`
	Timestamp string `json:"timestamp"`
}

// Procedure represents an extracted procedure.
type Procedure struct {
	Name    string `json:"name"`
	Type    string `json:"type"` // planned / completed / cancelled
	Context string `json:"context"`
}

// ActionItem represents an extracted action item.
type ActionItem struct {
	Type    string `json:"type"` // appointment / refill / question / callback / test / medication_change
	Details string `json:"details"`
	Urgency string `json:"urgency"` // low / medium / high
	Reason  string `json:"reason"`
}

// EntityExtractor extracts medical entities using an LLM.
type EntityExtractor struct {
	llm foundation.LLMProvider
	// MaxChars is the maximum input length (truncates long text).
	// 0 means no truncation.
	MaxChars int
}

// NewEntityExtractor creates a new entity extractor.
func NewEntityExtractor(llm foundation.LLMProvider) *EntityExtractor {
	return &EntityExtractor{
		llm:      llm,
		MaxChars: 0,
	}
}

// Extract extracts medical entities from clinical text.
func (e *EntityExtractor) Extract(ctx context.Context, text string) (*ExtractedEntities, error) {
	if text == "" {
		return &ExtractedEntities{}, nil
	}

	// Truncate if needed
	input := text
	if e.MaxChars > 0 && len(input) > e.MaxChars {
		input = input[:e.MaxChars] + "\n\n[truncated]"
	}

	systemPrompt := `You are a clinical NLP entity extractor. Extract ALL medical entities from the clinical text.

CRITICAL RULES:
1. NEVER invent or hallucinate entities. Only extract what is explicitly in the text.
2. If something is negated (e.g., "no fever", "denies chest pain"), do NOT list it as a symptom.
3. For each entity, provide the most specific information available.
4. Flag any PHI (patient names, IDs, dates of birth, addresses, phone numbers).
5. Note any contradictions between different parts of the text.
6. Note any missing information that would be clinically relevant.

Return ONLY valid JSON. No markdown. No explanations. No code fences.`

	userPrompt := fmt.Sprintf(`Extract entities from the following clinical text:

%s

Return the entities in this exact JSON format:
{"symptoms":[],"medications":[],"lab_values":[],"diagnoses":[],"vital_signs":[],"procedures":[],"action_items":[],"contradictions":[],"missing_info":[],"phi_flags":[]}`, input)

	// Call LLM with strict settings for JSON output
	result, err := e.llm.CompleteWithOptions(ctx, foundation.CompleteOptions{
		System:      systemPrompt,
		User:        userPrompt,
		Temperature: 0.1, // low temp for deterministic entity extraction
		MaxTokens:   4000,
	})
	if err != nil {
		return nil, fmt.Errorf("entity extraction LLM call failed: %w", err)
	}

	// Parse JSON
	entities := &ExtractedEntities{}
	cleaned := reJSONBlock.ReplaceAllString(result, `$1`)
	cleaned = strings.TrimSpace(cleaned)

	if err := json.Unmarshal([]byte(cleaned), entities); err != nil {
		// Try to recover by trimming to valid JSON
		cleaned = e.recoverJSON(cleaned)
		if err2 := json.Unmarshal([]byte(cleaned), entities); err2 != nil {
			return nil, fmt.Errorf("entity extraction JSON parse failed: %w (raw: %s)", err, result[:200])
		}
	}

	return entities, nil
}

// recoverJSON attempts to recover a valid JSON string from LLM output.
func (e *EntityExtractor) recoverJSON(raw string) string {
	// Find the last complete closing brace
	raw = strings.TrimSpace(raw)
	if strings.HasPrefix(raw, "{") {
		lastBrace := strings.LastIndex(raw, "}")
		if lastBrace > 0 {
			return raw[:lastBrace+1]
		}
	}
	return raw
}

// ---------------------------------------------------------------------------
// SoapSummarizer — LLM-based SOAP format summarization
// ---------------------------------------------------------------------------

// SoapSummary holds the SOAP-format summary.
type SoapSummary struct {
	Subjective  string   `json:"subjective"`
	Objective   string   `json:"objective"`
	Assessment  string   `json:"assessment"`
	Plan        string   `json:"plan"`
	Alerts      []string `json:"alerts"`
	MissingInfo []string `json:"missing_info"`
	Confidence  float64  `json:"confidence"` // 0.0-1.0
}

// SoapSummarizer generates SOAP-format summaries.
type SoapSummarizer struct {
	llm foundation.LLMProvider
}

// NewSoapSummarizer creates a new SOAP summarizer.
func NewSoapSummarizer(llm foundation.LLMProvider) *SoapSummarizer {
	return &SoapSummarizer{llm: llm}
}

// Summarize generates a SOAP summary from clinical text.
func (s *SoapSummarizer) Summarize(ctx context.Context, text string) (*SoapSummary, error) {
	if text == "" {
		return nil, errors.New("soap: input text is empty")
	}

	systemPrompt := `You are a clinical note summarization expert. Convert raw clinical notes into structured SOAP (Subjective/Objective/Assessment/Plan) format.

CRITICAL RULES:
1. NEVER invent findings not in the text. State "not provided" for missing information.
2. Subjective: patient-reported symptoms, concerns, history
3. Objective: measurable data (vitals, labs, exam findings)
4. Assessment: clinical impressions and diagnoses
5. Plan: ordered actions (tests, medications, follow-up)
6. Identify any contradictions between different parts of the note
7. Explicitly list missing clinically relevant information
8. This is documentation support ONLY — not a clinical decision

Return ONLY valid JSON matching this exact schema:
{"subjective":"","objective":"","assessment":"","plan":"","alerts":[],"missing_info":[],"confidence":0.9}`

	userPrompt := fmt.Sprintf(`Convert the following clinical note to SOAP format:

%s`, text)

	result, err := s.llm.CompleteWithOptions(ctx, foundation.CompleteOptions{
		System:      systemPrompt,
		User:        userPrompt,
		Temperature: 0.2,
		MaxTokens:   3000,
	})
	if err != nil {
		return nil, fmt.Errorf("soap summarization LLM call failed: %w", err)
	}

	soap := &SoapSummary{Confidence: 0.9}
	cleaned := reJSONBlock.ReplaceAllString(result, `$1`)
	cleaned = strings.TrimSpace(cleaned)

	if err := json.Unmarshal([]byte(cleaned), soap); err != nil {
		cleaned = (&EntityExtractor{}).recoverJSON(cleaned)
		if err2 := json.Unmarshal([]byte(cleaned), soap); err2 != nil {
			return nil, fmt.Errorf("soap JSON parse failed: %w", err)
		}
	}

	return soap, nil
}

// ---------------------------------------------------------------------------
// Regular expressions
// ---------------------------------------------------------------------------

// reBlankLines matches 3+ consecutive newlines.
var reBlankLines = regexp.MustCompile(`\n{3,}`)

// reJSONBlock matches content between code fences.
var reJSONBlock = regexp.MustCompile("(?s)```(?:json)?\\n?(.*?)\\n?```")

// reTrimJSON matches valid JSON start/end (used in EntityExtractor.recoverJSON).
var reTrimJSON = regexp.MustCompile("^\\{.*\\}$")
