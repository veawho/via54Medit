// finder.go
// CitationFinder extracts citation candidates from document text using regex patterns.
// It supports numbered references ([1], [2]), author-year style (Smith et al., 2023),
// and inline citations (Smith 2023; Jones et al. 2024).
package cite

import (
	"context"
	"fmt"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

// CitationCandidate is an unverified citation extracted from text.
type CitationCandidate struct {
	PageIndex int    // 1-based page/slide number
	RawText   string // the raw citation line
	Number    int    // reference number if numbered style (0 = unknown)
}

// CitationFinder extracts citation candidates from extracted pages.
type CitationFinder struct {
	// Patterns to match citation lines
	// These are compiled regexes for:
	// 1. Numbered citations: "[1]" or "[1][2]" patterns in text
	// 2. Reference list entries: "1. Author et al. Title Journal Year;Vol:Pages."
	// 3. Author-year citations: "Author et al. 2023" or "(Author 2023)"
	// 4. Full DOI patterns
	patNumberedRef   *regexp.Regexp // match reference list entries like "1. Author..."
	patInlineNum     *regexp.Regexp // match "[1]", "[1,2]", etc.
	patAuthorYear    *regexp.Regexp // match "(Author et al., 2023)" or "Author 2023"
	patJournal       *regexp.Regexp // match journal names in citation
	patVolumeIssue   *regexp.Regexp // match "2021;26:1234-45"
	patYear          *regexp.Regexp // match year at end
	patPMID          *regexp.Regexp // match PMID
	patDOI           *regexp.Regexp // match DOI
	patConf          *regexp.Regexp // match conference/abstract markers (APASL, ASCO, ESMO, etc.)
	patAuthor        *regexp.Regexp // match author name pattern at start of line
}

// NewCitationFinder creates a finder with compiled patterns.
func NewCitationFinder() *CitationFinder {
	return &CitationFinder{
	// Numbered reference list entry: "1. Author..." or "[1] Author..."
	// Matches lines starting with a number followed by a period or space and author name
	// The author name starts with an uppercase letter
	patNumberedRef: regexp.MustCompile(`^\s*\[?(\d+)\]?\.?\s*([A-Z][a-z]+)`),
	// Inline numbered citations: "[1]", "[1, 2]", "[1-5]"
	patInlineNum: regexp.MustCompile(`\[(\d+(?:\s*,\s*\d+)*|\d+\s*[-–]\s*\d+)\]`),
	// Author-year citations: "(Smith et al., 2023)" or "Smith et al. 2023"
	patAuthorYear: regexp.MustCompile(`\(([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+et al\.)?,\s*\d{4})\)`),
	// Journal name patterns — HCC/oncology/relevant journals (expanded)
	// Note: for journals with parenthetical city (e.g. "Cancers (Basel)"), we match the
	// bare journal name; the (City) suffix is extra context and breaks \b after the paren.
	patJournal: regexp.MustCompile(`(?i)\b(New\s*England\s*J\s*Med|New\s*England\s*Journal\s*of\s*Medicine|N\s*Engl\s*J\s*Med|N\.?\s*Engl\.?\s*J\.?\s*Med|NEJM|NEJM\s*Evid|Lancet|Lancet\s*Oncol|Lancet\s*Gastroenterol|JAMA|JAMA\s*Oncol|Journal\s*of\s*Clinical\s*Oncology|J Clin Oncol|J\.?\s*Clin\.?\s*Oncol|J Hepatol|J\.?\s*Hepatol|Hepatology|Gastroenterology|Ann Oncol|BMJ|Nat Med|Nat\s*Med|Cell|Science|Nature|Sci\s*Transl\s*Med|Signal Transduct Target Ther|Hepatol\s*Commun|Hepatobiliary\s*Surg\s*Nutr|Hepatol\s*Int|J\s*Gastroenterol\s*Hepatol|World\s*J\s*Gastroenterol|Clin\s*Cancer\s*Res|Clin\s*Transl\s*Med|Med\s*Sci\s*Monit|Medicine|Liver\s*Cancer|Liver\s*Int|Int\s*J\s*Mol\s*Sci|Front\s*Immunol|Anticancer\s*Research|Nat\s*Rev\s*Cancer|Nat\s*Rev\s*Immunol|Nat\s*Rev\s*Clin\s*Oncol|Nat\s*Commun|J\s*Autoimmun|Semin\s*Cancer\s*Biol|Cancers|ACS\s*Cent\s*Sci|Onco\s*Targets\s*Ther|OncoTargets\s*Ther|Oncotarget|Int\s*Immunopharmacol|MAbs|J\s*Immunol|Antibodies|J\s*Hematol\s*Oncol|Acta\s*Crystallogr|Cancer\s*Immunol\s*Res|Pharmaceuticals|Pharmacol\s*Res|Transl\s*Med)\b`),
	// Conference / abstract markers
	patConf: regexp.MustCompile(`(?i)\b(APASL|ASCO|ESMO|AASLD|EASL|WCC|ILCA|JSH|APASL\s*OP|APASL\s*LB|APASL\s*PO|CSCO|EASL|WCO)\b`),
	// Volume/issue/pages: "2021;26:1234-45" or "26(3):1234-1245"
	patVolumeIssue: regexp.MustCompile(`(\d{4}[;:,]\s*\d+|;\s*\d+[:\s]\d+[-–]\d+|\d+[-–]\d+)`),
	// Year pattern: 4-digit year at word boundary
	patYear: regexp.MustCompile(`\b(19\d{2}|20\d{2})\b`),
	// PMID
	patPMID: regexp.MustCompile(`PMID:\s*(\d+)`),
	// DOI
	patDOI: regexp.MustCompile(`DOI:\s*(\d{4,5}/\S+)`),
	// Author name pattern: uppercase letter start, lowercase continuation, optional comma/dot
	patAuthor: regexp.MustCompile(`^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s*[,\.]?`),
}
}

// FindCitations extracts citation candidates from a map of (page_number, text).
// For PPTX and similar formats where slide text is concatenated without newlines,
// it first splits each page's text by numbered reference patterns (e.g. "1. Author",
// "2. Author") to recover individual citation lines before parsing.
func (f *CitationFinder) FindCitations(pages map[int]string) []CitationCandidate {
	var candidates []CitationCandidate
	seen := make(map[string]bool)

	// Sort page numbers
	var pageNums []int
	for p := range pages {
		pageNums = append(pageNums, p)
	}
	sort.Ints(pageNums)

	for _, pageIdx := range pageNums {
		text := pages[pageIdx]
		lines := f.splitCitationLines(text)

		for _, line := range lines {
			line = strings.TrimSpace(line)
			if len(line) < 20 {
				continue // skip very short lines
			}

			// Check if this line looks like a citation
			if f.isCitationLine(line) {
				candidate := CitationCandidate{
					PageIndex: pageIdx,
					RawText:   line,
					Number:    0,
				}
				// Try to extract reference number
				if num := f.extractNumber(line); num > 0 {
					candidate.Number = num
				}

				// Deduplicate by normalized text
				norm := strings.ToLower(f.normalize(line))
				if !seen[norm] {
					seen[norm] = true
					candidates = append(candidates, candidate)
				}
			}
		}
	}

	return candidates
}

// splitCitationLines splits text into citation candidate lines.
// For text already with newlines, splits on "\n".
// For concatenated text (PPTX footnotes, slide notes, reference lists),
// splits on numbered reference patterns like "1. ", "2. ", "[1]", etc.
func (f *CitationFinder) splitCitationLines(text string) []string {
	// First split on newlines
	parts := strings.Split(text, "\n")
	var allLines []string

	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}

		// If part already has newlines within it (multiple lines), handle it
		// If part is a single line, check if it's a long concatenated reference list
		// (contains multiple numbered references separated by "n. " or "n.)"
		if len(part) > 200 {
			// Likely concatenated references — split by numbered patterns
			splitLines := f.splitNumberedReferences(part)
			allLines = append(allLines, splitLines...)
		} else {
			allLines = append(allLines, part)
		}
	}

	return allLines
}

// splitNumberedReferences splits a long text block into individual numbered reference entries.
// Splits on all "N. Author" / "N) Author" patterns and uses journal/author signals
// to reject false positives (page-number artifacts like "601. Qin" from "545-601").
func (f *CitationFinder) splitNumberedReferences(text string) []string {
	s := strings.ReplaceAll(text, "  ", " ")

	// Match 1-2 digit ref numbers: "1. Smith", "12) Lee", "3.Smith", "1 ) Zhang"
	splitPattern := regexp.MustCompile(`([1-9][0-9]?)\s*[.)]\s*([A-Z])`)

	matches := splitPattern.FindAllStringIndex(s, -1)
	if len(matches) < 2 {
		return []string{s}
	}

	var lines []string
	for i := 0; i < len(matches)-1; i++ {
		start := matches[i][0]
		end := matches[i+1][0]
		segment := strings.TrimSpace(s[start:end])
		if len(segment) >= 20 {
			lines = append(lines, segment)
		}
	}
	lastStart := matches[len(matches)-1][0]
	lastSegment := strings.TrimSpace(s[lastStart:])
	if len(lastSegment) >= 20 {
		lines = append(lines, lastSegment)
	}

	// Validate each segment: a real citation starts with a 1-2 digit reference number.
	// Artifacts from page ranges (e.g. "601. Qin" from "545-601") have 3+ digit numbers.
	var filtered []string
	for _, l := range lines {
		if len(l) >= 20 {
			// Extract the leading number
			n := f.extractNumber(l)
			if n > 0 && n < 100 {
				filtered = append(filtered, l)
				continue
			}
			// Fallback: accept if it looks like a citation without a leading number
			// (e.g. body text merged with refs)
			hasJ := f.patJournal.MatchString(l)
			hasC := f.patConf.MatchString(l)
			hasY := f.patYear.MatchString(l)
			hasEtAl := strings.Contains(strings.ToLower(l), "et al")
			hasPresented := strings.Contains(strings.ToLower(l), "presented")
			if hasEtAl {
				filtered = append(filtered, l)
				continue
			}
			if (hasJ || hasC) && (hasY || hasPresented) {
				filtered = append(filtered, l)
				continue
			}
			if hasPresented && f.patAuthor.MatchString(l) {
				filtered = append(filtered, l)
			}
		}
	}

	if len(filtered) == 0 {
		return []string{s}
	}

	return filtered
}

// isCitationLine checks if a line looks like a citation/reference.
func (f *CitationFinder) isCitationLine(line string) bool {
	// Must be at least 30 characters
	if len(line) < 30 {
		return false
	}

	// Check for citation-like patterns:
	hasAuthorLike := false
	hasJournalLike := false
	hasYear := false
	hasPages := false

	// Author-like: starts with uppercase letter(s) and contains "et al" or ", "
	if matched, _ := regexp.MatchString(`^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,?`, line); matched {
		hasAuthorLike = true
	}

	// Check for "et al"
	if strings.Contains(strings.ToLower(line), "et al") {
		hasAuthorLike = true
	}

	// Check for journal name
	if f.patJournal.MatchString(line) {
		hasJournalLike = true
	}

	// Check for year
	if f.patYear.MatchString(line) {
		hasYear = true
	}

	// Check for volume/issue/pages pattern
	if f.patVolumeIssue.MatchString(line) {
		hasPages = true
	}

	// Check for DOI
	if f.patDOI.MatchString(line) {
		hasPages = true
	}

	// Check for PMID
	if f.patPMID.MatchString(line) {
		hasPages = true
	}

	// A citation typically has: author-like + year OR journal-like + year
	// OR explicit reference number at start
	if num := f.extractNumber(line); num > 0 {
		return true
	}

	if (hasAuthorLike && hasYear) || (hasJournalLike && hasPages) {
		return true
	}

	// Also catch lines with semicolons separating multiple citations
	if strings.Count(line, ";") >= 2 && hasYear {
		return true
	}

	return false
}

// extractNumber tries to find a reference number at the start of the line.
func (f *CitationFinder) extractNumber(line string) int {
	if m := f.patNumberedRef.FindStringSubmatch(line); len(m) > 2 {
		if n, err := strconv.Atoi(m[1]); err == nil {
			return n
		}
	}
	return 0
}

// normalize removes extra spaces and punctuation for deduplication.
func (f *CitationFinder) normalize(text string) string {
	// Collapse multiple spaces
	s := reSpaces.ReplaceAllString(text, " ")
	// Remove trailing punctuation
	s = strings.TrimRight(s, ".;,:")
	return s
}

// reSpaces matches multiple consecutive whitespace characters.
var reSpaces = regexp.MustCompile(`\s+`)

// ---------------------------------------------------------------------------
// Parse a citation candidate into structured fields
// ---------------------------------------------------------------------------

// ParseCitation parses a raw citation text into Citation fields.
func (f *CitationFinder) ParseCitation(raw string) *Citation {
	cite := &Citation{
		RawText: raw,
		Status:  "unverified",
	}

	// Extract reference number
	if num := f.extractNumber(raw); num > 0 {
		cite.Number = num
	}

	// Extract author (first part before first comma or journal name)
	cite.Authors = f.extractAuthors(raw)

	// Extract journal
	cite.Journal = f.extractJournal(raw)

	// Extract year
	cite.Year = f.extractYear(raw)

	// Extract volume/issue/pages
	cite.Volume, cite.Issue, cite.Pages = f.extractVolumeIssuePages(raw)

	// Extract PMID
	if m := f.patPMID.FindStringSubmatch(raw); len(m) > 1 {
		cite.PMID = m[1]
	}

	// Extract DOI
	if m := f.patDOI.FindStringSubmatch(raw); len(m) > 1 {
		cite.DOI = m[1]
	}

	// Detect trial name from known trials
	cite.TrialName = f.detectTrialName(raw)
	cite.IsTrialPaper = cite.TrialName != ""

	return cite
}

// detectTrialName checks if the citation mentions any known trial name.
func (f *CitationFinder) detectTrialName(raw string) string {
	// Build a regex from all known trial names
	trials := AllTrials()
	if len(trials) == 0 {
		return ""
	}
	for _, t := range trials {
		// Look for the trial name (case-insensitive) in the raw text
		// Use \b for word boundary to avoid false matches like "HIMALAYA-xx"
		pat := `(?i)\b` + regexp.QuoteMeta(t.Name) + `\b`
		if regexp.MustCompile(pat).MatchString(raw) {
			return t.Name
		}
	}
	return ""
}

// extractAuthors extracts author names from the citation.
func (f *CitationFinder) extractAuthors(raw string) string {
	// Only process the citation segment (after numbered reference prefix), not body text.
	// Strip numbered prefix like "1. " or "[1] "
	s := raw
	if numPat := regexp.MustCompile(`^\s*\[?\d+\]?\.?\s*`); numPat.MatchString(s) {
		s = numPat.ReplaceAllString(s, "")
	}
	// Strip leading punctuation (*, -, etc.)
	s = strings.TrimLeft(s, "*-–— ")

	// Authors typically end at "et al." or before first comma/semicolon.
	// Try "et al." boundary first
	for _, marker := range []string{"et al.", "et al, ", "et al."} {
		idx := strings.Index(s, marker)
		if idx > 0 {
			// Take everything up to and including the author before "et al."
			// e.g. "Lau G, et al. 2025..." → "Lau G"
			s = strings.TrimSpace(s[:idx])
			// Remove trailing punctuation
			s = strings.TrimRight(s, ",.;:")
			return s
		}
	}

	// Try comma: "Lau G, et al." → "Lau G"
	commaIdx := strings.Index(s, ",")
	if commaIdx > 0 && commaIdx < 20 { // small window = likely first author
		return strings.TrimSpace(s[:commaIdx])
	}

	// Try journal name boundary
	if m := f.patJournal.FindStringIndex(s); m != nil {
		return strings.TrimSpace(s[:m[0]])
	}

	// Try conference marker
	if m := f.patConf.FindStringIndex(s); m != nil {
		return strings.TrimSpace(s[:m[0]])
	}

	// Try year (4-digit) boundary — take text before first year
	if m := f.patYear.FindStringIndex(s); m != nil {
		return strings.TrimSpace(s[:m[0]])
	}

	// Fallback: take first 30 chars (typically first author surname + initials)
	s = strings.TrimSpace(s)
	if len(s) > 30 {
		s = s[:30]
		// Truncate at word boundary
		idx := strings.LastIndex(s, " ")
		if idx > 5 {
			s = s[:idx]
		}
	}
	return s
}

// extractJournal extracts the journal name or conference/abstract marker from the citation.
func (f *CitationFinder) extractJournal(raw string) string {
	// Try journal first
	if m := f.patJournal.FindStringSubmatch(raw); len(m) > 1 {
		return m[1]
	}
	// Try conference marker
	if m := f.patConf.FindStringSubmatch(raw); len(m) > 1 {
		return m[1]
	}
	// Try "presented at <conference>"
	if idx := strings.Index(raw, "presented at"); idx >= 0 {
		rest := strings.TrimSpace(raw[idx+len("presented at"):])
		// Extract first word or known conference name
		if m := f.patConf.FindString(rest); len(m) > 0 {
			return m
		}
		// Otherwise return the conference name from context (first few words)
		// e.g. "2024CSCO" or "2025 ESMO"
		parts := strings.Fields(rest)
		if len(parts) > 0 {
			return parts[0]
		}
	}
	return ""
}

// extractYear extracts the publication year from the citation.
func (f *CitationFinder) extractYear(raw string) int {
	// First check for explicit year patterns in conference/abstract format: "2025 ESMO" or "2025 APASL"
	if m := f.patConf.FindStringIndex(raw); m != nil {
		// Look for a 4-digit year before the conference marker
		before := raw[:m[0]]
		if ym := regexp.MustCompile(`\b(19\d{2}|20\d{2})\b`).FindAllString(before, -1); len(ym) > 0 {
			if y, err := strconv.Atoi(ym[len(ym)-1]); err == nil && y >= 2000 && y <= 2030 {
				return y
			}
		}
	}
	// Standard year extraction
	if m := f.patYear.FindAllString(raw, -1); len(m) > 0 {
		lastYear := m[len(m)-1]
		if y, err := strconv.Atoi(lastYear); err == nil && y >= 1900 && y <= 2030 {
			return y
		}
	}
	return 0
}

// extractVolumeIssuePages parses "Year;Volume:Pages" or "Volume(Issue):Pages".
func (f *CitationFinder) extractVolumeIssuePages(raw string) (volume, issue, pages string) {
	// Try: "2021;26:1234-45"
	if m := regexp.MustCompile(`(\d{4});(\d+):(\d+[-–]\d+)`).FindStringSubmatch(raw); len(m) > 4 {
		return m[2], "", m[3]
	}
	// Try: "26(3):1234-1245"
	if m := regexp.MustCompile(`(\d+)\((\d+)\):(\d+[-–]\d+)`).FindStringSubmatch(raw); len(m) > 4 {
		return m[1], m[2], m[3]
	}
	// Try: ";26:1234"
	if m := regexp.MustCompile(`;(\d+):(\d+[-–]?\d*)`).FindStringSubmatch(raw); len(m) > 3 {
		return m[1], "", m[2]
	}
	return "", "", ""
}

// ---------------------------------------------------------------------------
// Pipeline: ExtractPages → FindCitations → ParseCitation → Verify
// ---------------------------------------------------------------------------

// Pipeline orchestrates the full citation extraction workflow.
type Pipeline struct {
	Extractor  Extractor
	Finder     *CitationFinder
	Verifier   *CitationVerifier
	DocumentType string
}

// NewPipeline creates a full citation extraction pipeline for a given file.
func NewPipeline(filePath string) (*Pipeline, error) {
	extractor, err := NewExtractor(filePath)
	if err != nil {
		return nil, err
	}
	return &Pipeline{
		Extractor:   extractor,
		Finder:      NewCitationFinder(),
		Verifier:    NewCitationVerifier(),
		DocumentType: extractor.Type(),
	}, nil
}

// Run executes the full pipeline: extract pages → find citations → verify.
// Returns a list of Citation with enrichment.
func (p *Pipeline) Run(ctx interface{}) ([]Citation, error) {
	// Extract pages
	pages, err := p.Extractor.ExtractPages()
	if err != nil {
		return nil, fmt.Errorf("cite: extraction failed: %w", err)
	}

	// Find citation candidates
	candidates := p.Finder.FindCitations(pages)

	// Parse into structured citations
	citations := make([]Citation, len(candidates))
	for i, cand := range candidates {
		cite := p.Finder.ParseCitation(cand.RawText)
		cite.PageIndex = cand.PageIndex
		cite.DocumentType = p.DocumentType
		citations[i] = *cite
	}

	return citations, nil
}

// VerifyAll enriches all citations sequentially with rate-limiting.
func (p *Pipeline) VerifyAll(citations []Citation) {
	ctx := context.Background()
	for i := range citations {
		p.Verifier.Verify(ctx, &citations[i])
	}
}

// ---------------------------------------------------------------------------
// Convenience functions
// ---------------------------------------------------------------------------

// ExtractAndVerify is a convenience function that runs the full pipeline.
// Returns: ([]Citation, error)
func ExtractAndVerify(filePath string) ([]Citation, error) {
	pipeline, err := NewPipeline(filePath)
	if err != nil {
		return nil, err
	}

	citations, err := pipeline.Run(nil)
	if err != nil {
		return nil, err
	}

	pipeline.VerifyAll(citations)
	return citations, nil
}
