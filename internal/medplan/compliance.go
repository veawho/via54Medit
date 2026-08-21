// Compliance engine: applies the rule table to a StrategyOutline and,
// when an LLM is configured, adds a semantic review pass for
// violations regex cannot catch (off-label hints, evidence-free
// superlatives, disguised comparative claims).
package medplan

import (
	"context"
	"encoding/json"
	"fmt"
	"regexp"
	"strings"
	"time"

	"github.com/veawho/via54Medit/internal/foundation"
)

// ComplianceChecker verifies outlines against mainland-China medical
// compliance rules. The zero value is a rules-only checker.
type ComplianceChecker struct {
	// LLM is optional; when set a semantic pass runs after the rules.
	LLM foundation.LLMProvider
}

// NewComplianceChecker returns a checker; llm may be nil.
func NewComplianceChecker(llm foundation.LLMProvider) *ComplianceChecker {
	return &ComplianceChecker{LLM: llm}
}

// Check verifies one outline. Never fails on LLM errors — the rules
// pass is authoritative and the engine string records the degradation.
func (c *ComplianceChecker) Check(ctx context.Context, o *StrategyOutline, product Product) (*ComplianceReport, error) {
	if o == nil {
		return nil, fmt.Errorf("medplan: compliance: nil outline")
	}
	rep := &ComplianceReport{
		Project:   o.Project,
		Audience:  o.Audience,
		Version:   o.Version,
		Engine:    "rules",
		CheckedAt: nowUTC(),
	}
	rep.Findings = append(rep.Findings, c.checkRules(o, product)...)

	if c.LLM != nil {
		findings, err := c.semanticPass(ctx, o, product)
		if err == nil && len(findings) > 0 {
			rep.Findings = append(rep.Findings, findings...)
			rep.Engine = "rules+llm"
		}
	}

	rep.SortFindings()
	rep.Verdict = rep.ComputeVerdict()
	annotateSections(o, rep)
	return rep, nil
}

// negationWindow is how many chars before a match are scanned for a
// negation prefix. Compliance outlines legitimately contain phrases
// like "处方药不得面向公众发布广告" — discussing a ban is not a violation.
const negationWindow = 16

// negationRe matches negation prefixes that exempt a nearby hit.
var negationRe = regexp.MustCompile(`不得|禁止|不能|严禁|避免|不含|不可|勿|不得含|不使用|未获|无需`)

// isNegated reports whether a match is a *statement of a prohibition*
// rather than a violation: either the preceding text negates it, or the
// matched span itself carries a negation ("处方药不得面向公众发布广告"
// matches the Rx pattern as a whole, with 不得 inside the span).
func isNegated(text string, loc []int) bool {
	lo := loc[0] - negationWindow
	if lo < 0 {
		lo = 0
	}
	return negationRe.MatchString(text[lo:loc[0]]) ||
		negationRe.MatchString(text[loc[0]:loc[1]])
}

// checkRules runs the deterministic table. Section-level scan gives
// each finding a location; presence rules scan the outline as a whole.
func (c *ComplianceChecker) checkRules(o *StrategyOutline, product Product) []ComplianceFinding {
	rules := rulesFor(o.Audience, product)
	full := o.FullText()
	var out []ComplianceFinding

	type scanTarget struct {
		id, title, text string
	}
	targets := []scanTarget{{id: "", title: "定位/核心信息", text: o.Positioning + "\n" + o.KeyMessage}}
	o.WalkAll(func(sec *OutlineSection) bool {
		targets = append(targets, scanTarget{
			id:    sec.ID,
			title: sec.Title,
			text:  sec.Title + "\n" + strings.Join(sec.Points, "\n"),
		})
		return true
	})

	for _, r := range rules {
		if r.Kind == checkPresence {
			if !anyMatch(r.Patterns, full) {
				out = append(out, ComplianceFinding{
					RuleID:     r.ID,
					Category:   r.Category,
					Severity:   r.Severity,
					LegalBasis: r.LegalBasis,
					Suggestion: r.Suggestion,
				})
			}
			continue
		}
		for _, t := range targets {
			for _, re := range r.Patterns {
				for _, loc := range re.FindAllStringIndex(t.text, -1) {
					if isNegated(t.text, loc) {
						continue // stating a prohibition ≠ violating it
					}
					out = append(out, ComplianceFinding{
						RuleID:       r.ID,
						Category:     r.Category,
						Severity:     r.Severity,
						SectionID:    t.id,
						SectionTitle: t.title,
						Matched:      t.text[loc[0]:loc[1]],
						LegalBasis:   r.LegalBasis,
						Suggestion:   r.Suggestion,
					})
				}
			}
		}
	}
	return out
}

// anyMatch reports whether any pattern matches s.
func anyMatch(pats []*regexp.Regexp, s string) bool {
	for _, re := range pats {
		if re.MatchString(s) {
			return true
		}
	}
	return false
}

// annotateSections writes a compliance note onto every section that
// produced a finding, so renders can flag them in place.
func annotateSections(o *StrategyOutline, rep *ComplianceReport) {
	bySection := map[string][]ComplianceFinding{}
	for _, f := range rep.Findings {
		if f.SectionID != "" {
			bySection[f.SectionID] = append(bySection[f.SectionID], f)
		}
	}
	o.WalkAll(func(sec *OutlineSection) bool {
		fs := bySection[sec.ID]
		if len(fs) == 0 {
			return true
		}
		var tags []string
		for _, f := range fs {
			tags = append(tags, fmt.Sprintf("%s[%s]", f.RuleID, f.Severity))
		}
		sec.ComplianceNote = strings.Join(tags, " ")
		return true
	})
}

// --- LLM semantic layer ---

const semanticSystem = `你是中国大陆医药领域资深医学合规审核专家, 精通《广告法》《药品管理法》
《医疗广告管理办法》与 RDPAC 行业行为准则。你的任务是审查医学策划方案大纲,
找出正则规则无法捕捉的合规风险。只输出 JSON, 不要输出任何其他文字。`

const semanticUserTmpl = `审查以下面向%s的医学策划方案大纲 (产品: %s, 药品分类: %s)。

合规重点 (仅报告以下类别, 每类最多 3 条):
1. off_label: 宣传产品未经批准的适应症或超说明书用途
2. unsupported_claim: 无证据支撑的疗效/安全性/经济学优势表述
3. disguised_compare: 变相与其他药品比较功效安全性 (未直接使用"优于")
4. rx_dtc_risk: 处方药面向公众传播的隐性风险 (如通过疾病教育夹带产品促销)
5. guideline_misquote: 指南/文献引用失真风险 (夸大推荐级别或断章取义)

输出 JSON:
{"findings":[{"category":"...","severity":"fatal|warn|info","section_title":"...","matched":"原文片段","suggestion":"修改建议"}]}

=== 大纲全文 ===
%s`

// semanticPass asks the LLM for JSON findings; every finding becomes a
// ComplianceFinding with an LLM- prefix on the rule ID.
func (c *ComplianceChecker) semanticPass(ctx context.Context, o *StrategyOutline, product Product) ([]ComplianceFinding, error) {
	rxLabel := product.RxStatus
	if rxLabel == "" {
		rxLabel = "未标注"
	}
	user := fmt.Sprintf(semanticUserTmpl, o.Audience.StringCN(), product.Name, rxLabel, truncateRunes(o.FullText(), 6000))
	raw, err := c.LLM.Complete(ctx, semanticSystem, user)
	if err != nil {
		return nil, fmt.Errorf("semantic pass: %w", err)
	}
	var got struct {
		Findings []struct {
			Category     string `json:"category"`
			Severity     string `json:"severity"`
			SectionTitle string `json:"section_title"`
			Matched      string `json:"matched"`
			Suggestion   string `json:"suggestion"`
		} `json:"findings"`
	}
	if err := json.Unmarshal([]byte(extractJSON(raw)), &got); err != nil {
		return nil, fmt.Errorf("semantic pass: parse: %w", err)
	}
	// Map LLM categories to stable rule IDs.
	categoryRule := map[string]string{
		"off_label":          "LLM-OFFLABEL",
		"unsupported_claim":  "LLM-UNSUPPORTED",
		"disguised_compare":  "LLM-DISGUISED-CMP",
		"rx_dtc_risk":        "LLM-RXDTC",
		"guideline_misquote": "LLM-MISQUOTE",
	}
	out := make([]ComplianceFinding, 0, len(got.Findings))
	for _, f := range got.Findings {
		ruleID, ok := categoryRule[f.Category]
		if !ok {
			continue // unknown category from a chatty model: drop
		}
		sev := SevWarn
		switch strings.ToLower(f.Severity) {
		case "fatal":
			sev = SevFatal
		case "info":
			sev = SevInfo
		}
		// Anchor to a section by title when possible.
		secID, secTitle := locateSection(o, f.SectionTitle)
		out = append(out, ComplianceFinding{
			RuleID:       ruleID,
			Category:     "语义审查: " + f.Category,
			Severity:     sev,
			SectionID:    secID,
			SectionTitle: secTitle,
			Matched:      truncateRunes(f.Matched, 120),
			LegalBasis:   "LLM 语义审查 (需人工复核)",
			Suggestion:   f.Suggestion,
		})
	}
	return out, nil
}

// locateSection resolves an LLM-reported section title to an outline
// section ID (best-effort substring match, document order).
func locateSection(o *StrategyOutline, title string) (string, string) {
	title = strings.TrimSpace(title)
	if title == "" {
		return "", ""
	}
	var id, found string
	o.WalkAll(func(sec *OutlineSection) bool {
		if found == "" && (strings.Contains(sec.Title, title) || strings.Contains(title, sec.Title)) {
			id, found = sec.ID, sec.Title
			return false
		}
		return true
	})
	return id, found
}

// extractJSON pulls the first balanced JSON object out of an LLM reply
// (models tend to wrap JSON in prose or code fences).
func extractJSON(s string) string {
	start := strings.Index(s, "{")
	if start < 0 {
		return s
	}
	depth := 0
	inStr := false
	esc := false
	for i := start; i < len(s); i++ {
		ch := s[i]
		if esc {
			esc = false
			continue
		}
		switch {
		case ch == '\\' && inStr:
			esc = true
		case ch == '"':
			inStr = !inStr
		case ch == '{' && !inStr:
			depth++
		case ch == '}' && !inStr:
			depth--
			if depth == 0 {
				return s[start : i+1]
			}
		}
	}
	return s[start:]
}

// truncateRunes cuts a string to at most n runes.
func truncateRunes(s string, n int) string {
	r := []rune(s)
	if len(r) <= n {
		return s
	}
	return string(r[:n]) + "..."
}

// nowUTC is the single clock injection point (tests can stub it).
var nowUTC = func() time.Time { return time.Now().UTC() }
