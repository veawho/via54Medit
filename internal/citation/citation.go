// Package citation provides the core citation table algorithms for
// via54Medit. This is the algorithm core that replaces scattered Python
// scripts in user projects (e.g. 雷管方案_文献整理) — those projects become
// consumers of via54Medit's library, not maintainers of their own.
//
// Philosophy (2026-07-31, user-taught):
//
//  1. Algorithm-driven, not rule-driven. Use regex/probabilistic scoring/
//     LRU/PageRank instead of hardcoded if/else.
//  2. Algorithm + LLM co-pilot. When confidence is low, let LLM reflect.
//  3. Never write hardcoded absolute values. Dynamic learning + continuous
//     integration.
//  4. Experience loop. Every user correction → automatic test case +
//     algorithm upgrade.
//  5. Local projects consume via54Medit (this is the core), not maintain
//     their own copies.
//
// Layering:
//
//	internal/citation/         ← algorithm core (THIS package)
//	internal/citation/corrections/  ← experience loop
//	internal/integrations/feishu/   ← Feishu sync (calls citation)
//	cmd/medit/commands/citation.go  ← CLI entry
//
// Algorithm inventory:
//
//	keyword_match.go    - D column field matching (author+journal+year+trial+drug)
//	doi_validate.go     - DOI accuracy via Crossref + PDF content
//	pdf_extract.go      - PyMuPDF content/title/DOI extraction
//	rich_text.go        - Feishu H column rich text auto-conversion
//	csv_sync.go         - One-way push + file lock + retry + verify
//	cell_parser.go      - Feishu nested cell parsing (list/dict/rich text)
//	pnx_resolver.go     - Pn-x directory resolution (shared PDFs across slides)
//	naming.go           - File naming convention v2.0 (Pn-x_main_xxx.pdf)
package citation

import (
	"fmt"
	"strings"
)

// Citation represents one row in a citation table (e.g. citation_table.csv).
//
// Column mapping (matches citation_table.csv schema):
//
//	SlidePage  "PPT页"
//	CiteIndex  "第几条"
//	Context    "引用语义（上下文）"
//	Reference  "PPT中的文献引用 完整字段"
//	DOI        "DOI"
//	DocType    "类型"
//	PDFFile    "对应PDF文件" (relative path, e.g. "P3-1/P3-1_main.pdf")
//	SourceURL  "来源链接 → 阅读全文" (rich text)
type Citation struct {
	SlidePage string
	CiteIndex string
	Context   string
	Reference string
	DOI       string
	DocType   string
	PDFFile   string
	SourceURL string
}

// String returns a debug-friendly representation.
func (c Citation) String() string {
	return fmt.Sprintf("Citation{slide=%s-%s ref=%q doi=%s file=%q}",
		c.SlidePage, c.CiteIndex, truncStr(c.Reference, 50), c.DOI, c.PDFFile)
}

// KeyFields returns the canonical key fields used for matching a citation
// row against a candidate PDF.
//
// Order matters: more specific fields first.
//
// Returns: author surnames (up to 5), journal, year, trial name, drug name,
// DOI tail.
type KeyFields struct {
	Authors []string // last names only
	Journal string   // raw journal name (e.g. "Lancet", "NEJMEvid")
	Year    string   // 4-digit year
	Trial   string   // trial acronym (HIMALAYA, IMbrave150, ...)
	Drug    string   // drug name (Tremelimumab, Atezolizumab, ...)
	DOITail string   // last component of DOI (e.g. "000518619")
}

// ExtractKeyFields returns the canonical KeyFields for a citation row.
//
// Implementation note (2026-07-31): this is the algorithm version 2, which
// replaces the v1 hardcoded regex from 雷管方案_文献整理. Improvements:
//
//   - Supports hyphenated author names (Abou-Alfa, Schöffski-Piva)
//   - Multi-author support (last names separated by space/comma)
//   - Fuzzy journal matching (handles "Lancet Oncol" vs "LancetOncol" vs
//     "Lancet Oncology")
//   - Trial acronym detection (10+ patterns)
//   - Drug name detection (12+ HCC drugs)
//   - DOI tail extraction (last path component)
//
// It also incorporates the Citation.DOI field by concatenating it to the
// Reference text, so that DOI matches even when only in DOI metadata.
func (c Citation) ExtractKeyFields() KeyFields {
	text := c.Reference
	if c.DOI != "" {
		text = text + " " + c.DOI
	}
	return ExtractKeyFieldsFromText(text)
}

// truncStr truncates s to max characters.
func truncStr(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max] + "..."
}

// normalizeForMatching lowercases + strips whitespace + unifies punctuation.
// Used for fuzzy matching across D column and PDF content.
func normalizeForMatching(s string) string {
	s = strings.ToLower(s)
	// Replace various whitespace with single space
	var b strings.Builder
	prevSpace := false
	for _, r := range s {
		if r == ' ' || r == '\t' || r == '\n' {
			if !prevSpace {
				b.WriteByte(' ')
				prevSpace = true
			}
		} else {
			b.WriteRune(r)
			prevSpace = false
		}
	}
	return strings.TrimSpace(b.String())
}