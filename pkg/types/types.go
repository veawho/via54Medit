// Package types defines the core data models for via54Medit.
//
// All data flowing through the system (queries, citations, evidence packages)
// is represented by the types in this file. They are designed to be:
//   - JSON-serializable (for persistence and MCP transport)
//   - LLM-friendly (clear field names, no abbreviations)
//   - Stable across versions (breaking changes bump major version)
package types

import "time"

// EBMQuestion represents a clinical research question from a user.
//
// It carries the original natural language query plus any structural
// information (PICO, intent) either auto-extracted by an LLM or
// manually specified by the user.
type EBMQuestion struct {
	// Query is the raw natural language question.
	Query string `json:"query"`

	// PICO is the structured Population/Intervention/Comparator/Outcome.
	// May be nil if extraction failed or wasn't requested.
	PICO *PICO `json:"pico,omitempty"`

	// Language: "zh" | "en" | "auto". Default: "auto".
	Language string `json:"language"`

	// Intent determines the workflow.
	// search | systematic | grade | annotate | index
	Intent Intent `json:"intent"`

	// Sources restricts which sources to query. Empty = all enabled.
	Sources []string `json:"sources,omitempty"`

	// MaxResults limits citations returned. Default: 20.
	MaxResults int `json:"max_results"`

	// TimeRange limits publication date.
	TimeRange *TimeRange `json:"time_range,omitempty"`

	// Filters: journal, mesh, section, etc.
	Filters map[string]string `json:"filters,omitempty"`

	// Context is optional background info the user provided.
	Context string `json:"context,omitempty"`
}

// PICO is the structured form of a clinical question.
type PICO struct {
	Population   string `json:"population"`
	Intervention string `json:"intervention"`
	Comparator   string `json:"comparator"`
	Outcome      string `json:"outcome"`
}

// TimeRange restricts publication date (inclusive).
type TimeRange struct {
	From int `json:"from"` // year
	To   int `json:"to"`   // year
}

// Intent is the user's goal.
type Intent string

const (
	IntentSearch    Intent = "search"    // 快速检索
	IntentSystematic Intent = "systematic" // PRISMA 综述
	IntentGrade     Intent = "grade"     // GRADE 评级
	IntentAnnotate  Intent = "annotate"  // 标注 PPT
	IntentIndex     Intent = "index"     // 入知识库
)

// Citation is a unified reference across all sources.
type Citation struct {
	// ID is the internal UUID (stable for deduplication).
	ID string `json:"id"`

	// Bibliographic
	Title   string   `json:"title"`
	Authors []string `json:"authors"`
	Journal string   `json:"journal"`
	Year    int      `json:"year"`

	// Identifiers
	PMID string `json:"pmid,omitempty"`
	DOI  string `json:"doi,omitempty"`

	// Content
	Abstract string   `json:"abstract,omitempty"`
	MeSH     []string `json:"mesh,omitempty"`

	// Impact metrics
	CitedBy int     `json:"cited_by,omitempty"`     // from S2
	FWCI    float64 `json:"fwci,omitempty"`          // from OpenAlex
	TLDR    string  `json:"tldr,omitempty"`          // from S2 AI summary
	OAPDFURL string `json:"oa_pdf_url,omitempty"`    // Open Access PDF

	// Provenance
	SourceOrigin []string `json:"source_origin"` // which sources returned this

	// Audit
	FetchedAt     time.Time `json:"fetched_at"`
	EnrichmentLog []string  `json:"enrichment_log,omitempty"`
}

// EvidencePackage is the final output of an ask/systematic/grade workflow.
type EvidencePackage struct {
	// Question
	Question EBMQuestion `json:"question"`

	// Citations: deduplicated, sorted by score, top N.
	Citations []Citation `json:"citations"`

	// LLM-generated EBM-style summary.
	Summary string `json:"summary"`

	// GRADE: "A" | "B" | "C" | "D" (empty if not graded)
	GRADE string `json:"grade,omitempty"`

	// GRADEReasoning is the human-readable justification.
	GRADEReasoning string `json:"grade_reasoning,omitempty"`

	// Output paths (set if rendered/serialized)
	JSONPath   string `json:"json_path,omitempty"`
	BibTeXPath string `json:"bibtex_path,omitempty"`
	PPTPath    string `json:"ppt_path,omitempty"`

	// Meta
	Duration    time.Duration      `json:"duration"`
	SourcesUsed map[string]int     `json:"sources_used"` // source -> count
	CreatedAt   time.Time          `json:"created_at"`
	ConvID      string             `json:"conv_id"` // unique question ID
}
