// Package medplan implements the medical planning-proposal workflow
// (医学策划方案) on top of via54Medit's literature research capability.
//
// Pipeline (v1, 2026-08-21):
//
//	[1] Brief        — 指令 + 产品信息 (models.Brief)
//	[2] Research     — 文献/新闻/研报/政策/竞品 五维调研 (research.go)
//	[3] Analyze      — 竞争优势提炼 + 观点输出 (analyze.go)
//	[4] Outline      — 按受众 (HCP/患者/行业) 生成策略大纲 (outline.go)
//	[5] Optimize     — 语义驱动的深度优化/扩充 (optimize.go)
//	[6] Compliance   — 中国大陆医学合规验证 (compliance.go)
//
// Every stage is deterministic when no LLM is configured: research falls
// back to the router's citation list, outline falls back to the audience
// skeleton template, and compliance is always rule-driven first.
//
// Storage layout (project.go):
//
//	~/.medit/medplan/<project>/brief.json
//	~/.medit/medplan/<project>/research.json
//	~/.medit/medplan/<project>/insights.json
//	~/.medit/medplan/<project>/outline_<audience>.json
//	~/.medit/medplan/<project>/compliance_<audience>.json
package medplan

import (
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/veawho/via54Medit/pkg/types"
)

// Audience identifies the target reader group of a strategy outline.
type Audience string

const (
	// AudienceHCP targets health-care professionals (医护人员): evidence,
	// guidelines, academic communication.
	AudienceHCP Audience = "hcp"
	// AudiencePatient targets patients / caregivers (患者及家属):
	// disease awareness, journey, access — strictest compliance profile.
	AudiencePatient Audience = "patient"
	// AudienceIndustry targets industry stakeholders (行业客户/商业伙伴):
	// market size, access, business model.
	AudienceIndustry Audience = "industry"
)

// AllAudiences returns the supported audiences in stable order.
func AllAudiences() []Audience {
	return []Audience{AudienceHCP, AudiencePatient, AudienceIndustry}
}

// ParseAudience validates an audience string.
func ParseAudience(s string) (Audience, error) {
	switch Audience(strings.ToLower(strings.TrimSpace(s))) {
	case AudienceHCP:
		return AudienceHCP, nil
	case AudiencePatient:
		return AudiencePatient, nil
	case AudienceIndustry:
		return AudienceIndustry, nil
	}
	return "", fmt.Errorf("medplan: unknown audience %q (want hcp|patient|industry)", s)
}

// StringCN returns the Chinese display name.
func (a Audience) StringCN() string {
	switch a {
	case AudienceHCP:
		return "医护人员 (HCP)"
	case AudiencePatient:
		return "患者及家属"
	case AudienceIndustry:
		return "行业/商业伙伴"
	}
	return string(a)
}

// Brief is the mission input: the instruction plus product facts.
// It is the single source of truth for every downstream stage.
type Brief struct {
	// Project is the short project slug (used as storage dir name).
	Project string `json:"project"`

	// Instruction is the natural-language task from the requester,
	// e.g. "为 XX 产品上市撰写学术传播策略".
	Instruction string `json:"instruction"`

	// Product describes the medical product.
	Product Product `json:"product"`

	// Audiences lists the outline targets (subset of AllAudiences).
	Audiences []Audience `json:"audiences"`

	// ExtraConstraints carries optional free-form requirements
	// (budget, timeline, region, channel preferences).
	ExtraConstraints string `json:"extra_constraints,omitempty"`

	CreatedAt time.Time `json:"created_at"`
}

// Product captures the medical-product facts needed for research and
// positioning. Only Name is required; empty fields simply narrow the
// research query matrix.
type Product struct {
	Name            string   `json:"name"`                      // 通用名/商品名 (required)
	Company         string   `json:"company,omitempty"`         // 持有企业
	Modality        string   `json:"modality,omitempty"`        // 药品/器械/数字医疗/疫苗...
	MOA             string   `json:"moa,omitempty"`             // 作用机制
	Indications     []string `json:"indications,omitempty"`     // 适应症
	Stage           string   `json:"stage,omitempty"`           // 研发/上市/医保阶段
	Differentiators []string `json:"differentiators,omitempty"` // 已知差异化点
	Competitors     []string `json:"competitors,omitempty"`     // 已知竞品
	// RxStatus: "rx" (处方药) | "otc" | "device" | "" (未知).
	// Drives the strictest compliance rules (处方药禁止大众媒介广告).
	RxStatus string `json:"rx_status,omitempty"`
}

// ResearchDimension labels what a research item is about.
type ResearchDimension string

const (
	DimLiterature ResearchDimension = "literature" // 医学文献
	DimNews       ResearchDimension = "news"       // 新闻报道
	DimReport     ResearchDimension = "report"     // 行业研报
	DimPolicy     ResearchDimension = "policy"     // 政策/监管
	DimCompetitor ResearchDimension = "competitor" // 竞品动态
)

// AllDimensions returns the five research dimensions in stable order.
func AllDimensions() []ResearchDimension {
	return []ResearchDimension{DimLiterature, DimNews, DimReport, DimPolicy, DimCompetitor}
}

// StringCN returns the Chinese display name.
func (d ResearchDimension) StringCN() string {
	switch d {
	case DimLiterature:
		return "医学文献"
	case DimNews:
		return "新闻报道"
	case DimReport:
		return "行业研报"
	case DimPolicy:
		return "政策监管"
	case DimCompetitor:
		return "竞品动态"
	}
	return string(d)
}

// ResearchItem is one piece of evidence gathered during research.
type ResearchItem struct {
	ID        string            `json:"id"` // e.g. "L001", "N001"
	Dimension ResearchDimension `json:"dimension"`
	Title     string            `json:"title"`
	Summary   string            `json:"summary,omitempty"` // why it matters for this brief
	URL       string            `json:"url,omitempty"`
	Source    string            `json:"source,omitempty"`    // pubmed / web / manual
	Published string            `json:"published,omitempty"` // free-form date
	// Citation links the item to the router's unified citation model
	// (populated for the literature dimension).
	Citation *types.Citation `json:"citation,omitempty"`
	// NeedsVerification marks items synthesized by an LLM that were not
	// backed by a retrievable source (news/report/policy in v1).
	NeedsVerification bool `json:"needs_verification,omitempty"`
}

// ResearchDossier is the aggregated output of the research stage.
type ResearchDossier struct {
	Project string          `json:"project"`
	Queries []ResearchQuery `json:"queries"` // what was asked, per dimension
	Items   []ResearchItem  `json:"items"`
	// Notes is the LLM cross-dimension synthesis ("" when no LLM).
	Notes     string              `json:"notes,omitempty"`
	Topics    map[string][]string `json:"topics,omitempty"` // dimension -> key topics
	Duration  time.Duration       `json:"duration"`
	CreatedAt time.Time           `json:"created_at"`
}

// ResearchQuery records one executed query for auditability.
type ResearchQuery struct {
	Dimension ResearchDimension `json:"dimension"`
	Query     string            `json:"query"`
	Results   int               `json:"results"`
	Error     string            `json:"error,omitempty"`
}

// ItemsByDimension returns the items of one dimension in slice order.
func (d *ResearchDossier) ItemsByDimension(dim ResearchDimension) []ResearchItem {
	out := make([]ResearchItem, 0, len(d.Items))
	for _, it := range d.Items {
		if it.Dimension == dim {
			out = append(out, it)
		}
	}
	return out
}

// Dimensions returns the dimensions that have at least one item,
// in AllDimensions order (deterministic).
func (d *ResearchDossier) Dimensions() []ResearchDimension {
	present := map[ResearchDimension]bool{}
	for _, it := range d.Items {
		present[it.Dimension] = true
	}
	var out []ResearchDimension
	for _, dim := range AllDimensions() {
		if present[dim] {
			out = append(out, dim)
		}
	}
	return out
}

// Insight is an extracted, defensible viewpoint. Insights are the
// backbone of competitive-advantage packaging.
type Insight struct {
	ID    string `json:"id"` // "I1", "I2", ...
	Claim string `json:"claim"`
	// Dimension hints which research backs the claim.
	Dimension ResearchDimension `json:"dimension"`
	// ItemIDs references ResearchItem IDs that support the claim.
	ItemIDs []string `json:"item_ids,omitempty"`
	// Strength: "strong" (多项一致证据) | "moderate" | "weak" (单一/间接证据).
	Strength string `json:"strength"`
	// Advantage marks insights usable as competitive-advantage claims.
	Advantage bool `json:"advantage,omitempty"`
}

// Insights is the analyze-stage output.
type Insights struct {
	Project  string    `json:"project"`
	Insights []Insight `json:"insights"`
	// SWOT carries the classic four quadrants (each a list of claims).
	SWOT      SWOT      `json:"swot"`
	CreatedAt time.Time `json:"created_at"`
}

// SWOT groups strategic findings.
type SWOT struct {
	Strengths     []string `json:"strengths,omitempty"`
	Weaknesses    []string `json:"weaknesses,omitempty"`
	Opportunities []string `json:"opportunities,omitempty"`
	Threats       []string `json:"threats,omitempty"`
}

// OutlineSection is one node of the strategy outline tree.
type OutlineSection struct {
	ID       string           `json:"id"` // "1", "1.1", ...
	Title    string           `json:"title"`
	Points   []string         `json:"points,omitempty"`   // key talking points
	Evidence []string         `json:"evidence,omitempty"` // ResearchItem IDs
	Children []OutlineSection `json:"children,omitempty"`
	// ComplianceNote flags the section as compliance-sensitive during
	// verification (set by the compliance stage).
	ComplianceNote string `json:"compliance_note,omitempty"`
}

// Walk calls fn for the section and all descendants in document order.
// If fn returns false the subtree under that section is skipped.
func (s *OutlineSection) Walk(fn func(sec *OutlineSection) bool) {
	if s == nil || !fn(s) {
		return
	}
	for i := range s.Children {
		s.Children[i].Walk(fn)
	}
}

// StrategyOutline is a complete audience-specific strategy proposal.
type StrategyOutline struct {
	Project  string   `json:"project"`
	Audience Audience `json:"audience"`
	Version  int      `json:"version"` // increments on each optimize pass
	// Positioning is the one-line brand positioning statement.
	Positioning string `json:"positioning,omitempty"`
	// KeyMessage is the single core message (信息钥匙).
	KeyMessage string           `json:"key_message,omitempty"`
	Sections   []OutlineSection `json:"sections"`
	// InsightIDs references the insights used in this outline.
	InsightIDs []string `json:"insight_ids,omitempty"`
	// ChangeLog records optimize passes (optimize.go).
	ChangeLog   []OutlineChange `json:"change_log,omitempty"`
	GeneratedBy string          `json:"generated_by,omitempty"` // "llm:<provider>" | "template"
	CreatedAt   time.Time       `json:"created_at"`
	UpdatedAt   time.Time       `json:"updated_at"`
}

// OutlineChange documents one semantic optimization pass.
type OutlineChange struct {
	Version     int       `json:"version"`
	Instruction string    `json:"instruction"` // the user's optimization instruction
	Summary     string    `json:"summary"`     // what changed
	At          time.Time `json:"at"`
}

// WalkAll walks every top-level section in document order.
func (o *StrategyOutline) WalkAll(fn func(sec *OutlineSection) bool) {
	for i := range o.Sections {
		o.Sections[i].Walk(fn)
	}
}

// SectionCount returns the total number of sections (recursive).
func (o *StrategyOutline) SectionCount() int {
	n := 0
	o.WalkAll(func(_ *OutlineSection) bool { n++; return true })
	return n
}

// Flatten returns every section (recursive, document order).
func (o *StrategyOutline) Flatten() []*OutlineSection {
	var out []*OutlineSection
	o.WalkAll(func(sec *OutlineSection) bool { out = append(out, sec); return true })
	return out
}

// FindSection returns the section with the given ID, or nil.
func (o *StrategyOutline) FindSection(id string) *OutlineSection {
	var found *OutlineSection
	o.WalkAll(func(sec *OutlineSection) bool {
		if sec.ID == id {
			found = sec
			return false
		}
		return true
	})
	return found
}

// FullText concatenates every title and point — the corpus the
// compliance engine scans.
func (o *StrategyOutline) FullText() string {
	var b strings.Builder
	o.WalkAll(func(sec *OutlineSection) bool {
		b.WriteString(sec.Title)
		b.WriteString("\n")
		for _, p := range sec.Points {
			b.WriteString(p)
			b.WriteString("\n")
		}
		return true
	})
	if o.Positioning != "" {
		b.WriteString(o.Positioning)
		b.WriteString("\n")
	}
	if o.KeyMessage != "" {
		b.WriteString(o.KeyMessage)
		b.WriteString("\n")
	}
	return b.String()
}

// ComplianceSeverity ranks a finding.
type ComplianceSeverity string

const (
	SevFatal ComplianceSeverity = "fatal" // 明确违法, 必须删除/改写
	SevWarn  ComplianceSeverity = "warn"  // 高风险, 需法务复核
	SevInfo  ComplianceSeverity = "info"  // 提示项 (缺免责声明等)
)

// ComplianceFinding is one rule violation.
type ComplianceFinding struct {
	RuleID       string             `json:"rule_id"`
	Category     string             `json:"category"`
	Severity     ComplianceSeverity `json:"severity"`
	SectionID    string             `json:"section_id,omitempty"`
	SectionTitle string             `json:"section_title,omitempty"`
	Matched      string             `json:"matched,omitempty"` // offending text
	LegalBasis   string             `json:"legal_basis,omitempty"`
	Suggestion   string             `json:"suggestion,omitempty"`
}

// ComplianceReport is the verification result for one outline.
type ComplianceReport struct {
	Project  string              `json:"project"`
	Audience Audience            `json:"audience"`
	Version  int                 `json:"outline_version"`
	Findings []ComplianceFinding `json:"findings"`
	// Verdict: "pass" (no fatal/warn) | "warn" | "fail" (any fatal).
	Verdict   string    `json:"verdict"`
	Engine    string    `json:"engine,omitempty"` // "rules" | "rules+llm"
	CheckedAt time.Time `json:"checked_at"`
}

// CountsBySeverity returns fatal/warn/info counts (deterministic order).
func (r *ComplianceReport) CountsBySeverity() map[ComplianceSeverity]int {
	m := map[ComplianceSeverity]int{}
	for _, f := range r.Findings {
		m[f.Severity]++
	}
	return m
}

// ComputeVerdict derives the verdict from findings: any fatal → fail,
// any warn → warn, else pass.
func (r *ComplianceReport) ComputeVerdict() string {
	counts := r.CountsBySeverity()
	if counts[SevFatal] > 0 {
		return "fail"
	}
	if counts[SevWarn] > 0 {
		return "warn"
	}
	return "pass"
}

// SortFindings orders findings by severity (fatal < warn < info), then
// rule ID, then section ID — deterministic output for diffing.
func (r *ComplianceReport) SortFindings() {
	rank := map[ComplianceSeverity]int{SevFatal: 0, SevWarn: 1, SevInfo: 2}
	sort.SliceStable(r.Findings, func(i, j int) bool {
		a, b := r.Findings[i], r.Findings[j]
		if rank[a.Severity] != rank[b.Severity] {
			return rank[a.Severity] < rank[b.Severity]
		}
		if a.RuleID != b.RuleID {
			return a.RuleID < b.RuleID
		}
		return a.SectionID < b.SectionID
	})
}
