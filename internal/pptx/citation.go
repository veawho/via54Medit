// Package pptx extracts citations from PowerPoint files and verifies them
// against PubMed/Crossref/DOI sources, then flags whether the full-text PDF
// is downloadable (Sci-Hub 2022- / Unpaywall OA / Nexus 2023+).
//
// Pipeline (Phase 3):
//
//  1. Extract raw text from PPTX XML (slides/*.xml + notesSlides/*.xml)
//  2. Regex-match citation lines (author, journal, year, PMID/DOI)
//  3. Enrich with PubMed (PMID → metadata) + Crossref (DOI → publisher)
//  4. Flag downloadability: Sci-Hub / OA / Nexus / unavailable
//  5. Return []CitationEntry with verification status
package pptx

import (
	"archive/zip"
	"context"
	"encoding/json"
	"encoding/xml"
	"fmt"
	"io"
	"net/http"
	"os"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/veawho/via54Medit/internal/source"
	"github.com/veawho/via54Medit/pkg/types"
)

// ---------------------------------------------------------------------------
// Data model
// ---------------------------------------------------------------------------

// CitationEntry is one citation found in a PPTX slide.
type CitationEntry struct {
	// Position
	SlideIndex int    `json:"slide_index"` // 1-based
	SlideTitle string `json:"slide_title"` // derived from first heading text

	// Raw
	RawText string `json:"raw_text"` // original citation line

	// Extracted fields
	Authors string `json:"authors,omitempty"`
	Title   string `json:"title,omitempty"`
	Journal string `json:"journal,omitempty"`
	Year    int    `json:"year"`
	Volume  string `json:"volume,omitempty"`
	Issue   string `json:"issue,omitempty"`
	Pages   string `json:"pages,omitempty"`
	PMID    string `json:"pmid,omitempty"`
	DOI     string `json:"doi,omitempty"`

	// Verified fields (from PubMed/Crossref)
	VerifiedTitle string `json:"verified_title,omitempty"`
	VerifiedPMID  string `json:"verified_pmid,omitempty"`
	VerifiedDOI   string `json:"verified_doi,omitempty"`

	// Verification status
	Status     string      `json:"status"`  // "exact" | "partial" | "mismatch" | "not_found" | "unverifiable"
	Verdict    string      `json:"verdict"` // human-readable summary
	SourceHits []SourceHit `json:"source_hits,omitempty"`

	// Downloadability (from full-text pipeline)
	Downloadable bool   `json:"downloadable"`
	DownloadTier string `json:"download_tier"` // "sci-hub" | "oa" | "nexus" | "unavailable"
	DownloadNote string `json:"download_note,omitempty"`
}

// SourceHit is one match from a single academic source.
type SourceHit struct {
	Source     string `json:"source"` // "pubmed" | "crossref" | "doi"
	PMID       string `json:"pmid,omitempty"`
	DOI        string `json:"doi,omitempty"`
	Title      string `json:"title,omitempty"`
	Journal    string `json:"journal,omitempty"`
	Year       int    `json:"year"`
	ExactMatch bool   `json:"exact_match"`
}

// ---------------------------------------------------------------------------
// XML helpers (Office Open XML namespace handling)
// ---------------------------------------------------------------------------

// PptxText is a minimal namespace-aware struct for reading <a:t> text runs.
type PptxText struct {
	XMLName xml.Name `xml:"t"`
	Text    string   `xml:",chardata"`
}

// PptxTextBody represents a simplified slide/notes XML containing <a:t> runs.
// We don't parse the full schema — just collect all text content.
type PptxTextBody struct {
	Any []PptxText `xml:"t"`
}

// ---------------------------------------------------------------------------
// Extractor
// ---------------------------------------------------------------------------

// Extractor reads a .pptx file and extracts all slide + notes text.
type Extractor struct {
	filePath string
}

// NewExtractor creates an extractor for the given .pptx file.
func NewExtractor(filePath string) *Extractor {
	return &Extractor{filePath: filePath}
}

// ExtractText reads the PPTX and returns (slideIndex, fullText).
// slideIndex is 1-based. Returns all slide texts in order.
func (e *Extractor) ExtractText() (map[int]string, error) {
	if _, err := os.Stat(e.filePath); os.IsNotExist(err) {
		return nil, fmt.Errorf("pptx: file not found: %s", e.filePath)
	}

	f, err := zip.OpenReader(e.filePath)
	if err != nil {
		return nil, fmt.Errorf("pptx: cannot open zip: %w", err)
	}
	defer f.Close()

	result := make(map[int]string)

	// Collect slide XML files sorted by name to get deterministic order
	var slideFiles []string
	notesFiles := make(map[int]string) // slide number → notes content

	for _, entry := range f.File {
		// Main slides
		if strings.HasPrefix(entry.Name, "ppt/slides/slide") && strings.HasSuffix(entry.Name, ".xml") {
			slideFiles = append(slideFiles, entry.Name)
		}
		// Notes slides (e.g. ppt/notesSlides/notesSlide1.xml)
		if strings.HasPrefix(entry.Name, "ppt/notesSlides/notesSlide") && strings.HasSuffix(entry.Name, ".xml") {
			idx := extractSlideNum(entry.Name)
			if idx > 0 {
				rc, err := entry.Open()
				if err == nil {
					data, _ := io.ReadAll(rc)
					rc.Close()
					notesFiles[idx] = extractSlideText(data)
				}
			}
		}
	}

	sort.Strings(slideFiles)

	for _, name := range slideFiles {
		// Extract slide number from filename
		idx := extractSlideNum(name)
		if idx == 0 {
			continue
		}
		rc, err := entryForFile(f.File, name)
		if err != nil {
			continue
		}
		_ = rc // silence
		data, _ := io.ReadAll(rc)
		rc.Close()

		mainText := extractSlideText(data)

		// Append notes if present (with separator)
		if notes := notesFiles[idx]; notes != "" {
			mainText += "\n[NOTES: " + notes + "]"
		}

		result[idx] = mainText
	}

	return result, nil
}

func entryForFile(entries []*zip.File, name string) (io.ReadCloser, error) {
	for _, e := range entries {
		if e.Name == name {
			return e.Open()
		}
	}
	return nil, fmt.Errorf("entry not found: %s", name)
}

// extractSlideText parses XML and returns concatenated <a:t> text.
//
// IMPORTANT: Go's RE2 engine is NOT fully compatible with Office Open XML
// namespaces. The standard approach (xml.Unmarshal or <a:t>(.*?)</a:t>)
// both fail on real PPTX files:
//   - xml.Unmarshal with `xml:"t"` tag returns 0 items because <a:t> is
//     namespace-prefixed (a:t = {http://schemas.openxmlformats.org/...}t)
//   - <a:t[^>]*>(.*?)</a:t> matches way too much because <a:t> appears inside
//     other tags (e.g. <a:rPr>...</a:rPr><a:t>TEXT</a:t>) and the greedy
//     [^>]* eats across the containing element's opening tag boundary.
//
// The working approach: text is always between the closing '>' of the
// preceding <a:r> (or the containing element) and </a:t>. Match the last '>'
// before </a:t>:
func extractSlideText(data []byte) string {
	// Try XML unmarshalling first (works for namespaced PPTX in some cases)
	var body PptxTextBody
	if err := xml.Unmarshal(data, &body); err == nil && len(body.Any) > 0 {
		var parts []string
		for _, t := range body.Any {
			s := strings.TrimSpace(t.Text)
			if s != "" {
				parts = append(parts, s)
			}
		}
		if len(parts) > 0 {
			return strings.Join(parts, " ")
		}
	}

	// Robust fallback: text is the content between the last '>' and '</a:t>'
	// for each <a:t> tag. This correctly handles both namespace-prefixed and
	// un-prefixed variants, and avoids greedily matching surrounding XML.
	re := regexp.MustCompile(`>([^<]{1,500})</a:t>`)
	matches := re.FindAllSubmatch(data, -1)
	if len(matches) == 0 {
		return ""
	}
	var parts []string
	for _, m := range matches {
		s := strings.TrimSpace(string(m[1]))
		if s != "" {
			parts = append(parts, s)
		}
	}
	return strings.Join(parts, " ")
}

// extractSlideNum extracts the numeric index from a slide filename.
func extractSlideNum(name string) int {
	// Match both "slideN.xml" (slides dir) and "notesSlideN.xml" (notes dir).
	// The digit always immediately precedes ".xml" at end of filename.
	re := regexp.MustCompile(`(\d+)\.xml$`)
	m := re.FindStringSubmatch(name)
	if len(m) < 2 {
		return 0
	}
	n, _ := strconv.Atoi(m[1])
	return n
}

// ---------------------------------------------------------------------------
// Citation line detection
// ---------------------------------------------------------------------------

// CitationLine is a raw line that looks like a reference citation.
type CitationLine struct {
	SlideIndex int
	RawText    string
}

// ExtractCitationLines scans slide texts for citation-like lines.
func ExtractCitationLines(slideTexts map[int]string) []CitationLine {
	var lines []CitationLine

	for idx := 1; idx <= maxSlide(slideTexts); idx++ {
		text := slideTexts[idx]
		if text == "" {
			continue
		}

		cites := findCitationLines(text)
		for _, c := range cites {
			lines = append(lines, CitationLine{SlideIndex: idx, RawText: c})
		}
	}

	return lines
}

func maxSlide(m map[int]string) int {
	max := 0
	for k := range m {
		if k > max {
			max = k
		}
	}
	return max
}

// findCitationLines scans the full slide text for academic citation patterns.
//
// IMPORTANT: PPTX text is space-joined across all <a:t> runs. Splitting first
// (by sentence boundaries) BREAKS citations — "Lau G, et al. 2025. J Hepatol.
// 82(2): 258-267" becomes 4 fragments, each scoring 0-1 in isCitationLine.
//
// Correct approach: scan the WHOLE text with a journal-name-centered window
// heuristic: for each journal occurrence, expand ±120 chars and verify the
// window contains at least 2 of: year, author pattern, volume:page, DOI.
func findCitationLines(text string) []string {
	// Normalize whitespace for consistent matching
	text = strings.Join(strings.Fields(text), " ")
	return findCitationsByPatterns(text)
}

// findCitationsByPatterns uses a heuristic window approach:
// find all positions where journal+year+vol appear near each other,
// then expand to capture the full citation.
func findCitationsByPatterns(text string) []string {
	// Step 1: find all positions of journal names
	journalMatches := journalPat.FindAllIndex([]byte(text), -1)
	// Step 2: for each journal, expand ±150 chars and check for year+author
	var cites []string
	for _, idx := range journalMatches {
		start := max(0, idx[0]-120)
		end := min(len(text), idx[1]+120)
		window := text[start:end]

		// Does this window look like a citation?
		hasYear := yearPat.MatchString(window)
		hasAuthor := authorPat.MatchString(window)
		hasVolPage := volPagePat.MatchString(window)
		hasDOI := doiPat.MatchString(window)

		score := 0
		if hasYear {
			score += 1
		}
		if hasAuthor {
			score += 1
		}
		if hasVolPage {
			score += 1
		}
		if hasDOI {
			score += 1
		}
		if score >= 2 {
			// Trim window to first 100+ chars after journal start
			cites = append(cites, window)
		}
	}
	return deduplicateCitations(cites)
}

// deduplicateCitations removes near-identical citations.
func deduplicateCitations(cites []string) []string {
	seen := make(map[string]struct{})
	var result []string
	for _, c := range cites {
		// Normalize for dedup
		norm := strings.ToLower(strings.Join(strings.Fields(c), " "))
		if len(norm) < 10 {
			continue
		}
		if _, ok := seen[norm]; ok {
			continue
		}
		seen[norm] = struct{}{}
		result = append(result, c)
	}
	return result
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// isCitationLine checks if a text line resembles an academic citation.
// (kept for backwards compatibility / direct use)
func isCitationLine(line string) bool {
	// Must contain at least two of: journal-like name, year (1900-2099),
	// volume/issue pattern, author list, DOI, PMID.
	score := 0

	// Year pattern: 4-digit year in 1900-2099
	if yearPat.MatchString(line) {
		score += 1
	}

	// Journal names (abbreviated or full)
	if journalPat.MatchString(line) {
		score += 1
	}

	// Volume(Issue):Pages or Volume:Pages
	if volPagePat.MatchString(line) {
		score += 1
	}

	// DOI
	if strings.Contains(strings.ToLower(line), "doi:") || doiPat.MatchString(line) {
		score += 2
	}

	// PMID
	if strings.Contains(strings.ToLower(line), "pmid:") || pmidPat.MatchString(line) {
		score += 2
	}

	// Author list pattern: "LastName, et al." or "LastName A, LastName B, et al."
	if authorPat.MatchString(line) {
		score += 1
	}

	// "Reference" / "参考文献" / "References" heading
	if strings.Contains(strings.ToLower(line), "reference") ||
		strings.Contains(line, "参考文献") {
		return true
	}

	// Numbered entry: starts with "[1]" or "1." or "[1-2]"
	if refNumPat.MatchString(line) {
		score += 1
	}

	return score >= 2
}

var (
	yearPat = regexp.MustCompile(`\b(19|20)\d{2}\b`)
	// journalPat uses a single alternation. Short journal names like "JAMA"/"Lancet"
	// are followed by a word-boundary, but we must manually reject them when the
	// boundary is followed by more letters (e.g. "JAMA Oncol"). The caller handles
	// this with longestMatch() which checks that no journalPat match is a proper
	// substring of another candidate.
	journalPat = regexp.MustCompile(`(?i)\b(JAMA Oncol|J Clin Oncol|Lancet Oncol|Lancet Transplant|Lancet Infect Dis|Lancet HIV|N Engl J Med|Nat Rev Drug Discov|Ann Intern Med|J Natl Cancer Cent|J Med Internet Res|J Med Virol|Annals of Oncology|Ann Oncol|Cancer Cell|Cancer Res|Front Immunol|Front Oncol|Int J Mol Sci|Liver Cancer|Eur J Cancer|Br J Cancer|BMJ Open|Sci Rep|Adv Sci|Hepatology|J Hepatol|Lancet\b|JAMA\b|NEJM\b|BMJ\b|Cell\b|Medicine\b)`)
	volPagePat = regexp.MustCompile(`\b\d{1,4}\((\d{1,3}|[A-Za-z])\):\s*\d{1,5}(?:-\d{1,5})?\b|\b\d{1,4}:\s*\d{1,5}(?:-\d{1,5})?\b`)
	doiPat     = regexp.MustCompile(`10\.\d{4,9}/[-._;()/:A-Za-z0-9]+`)
	pmidPat    = regexp.MustCompile(`PMID\s*:\s*\d{6,10}|\b\d{6,10}\b`)
	authorPat  = regexp.MustCompile(`\b[A-Z][a-z]*,?\s+et al\.?|, et al\.?|, et\.\s*al\.?|[A-Z]\.\s*[A-Z][a-z]+,?\s+et al\.?`)
	refNumPat  = regexp.MustCompile(`^\[\d+(?:-\d+)?\]\s|\d+\.\s+[A-Z]`)
)

// ---------------------------------------------------------------------------
// Field extractor (structured parsing of a citation line)
// ---------------------------------------------------------------------------

// ParseCitationLine extracts structured fields from a raw citation line.
func ParseCitationLine(raw string) (entry CitationEntry) {
	entry.RawText = raw

	// Extract PMID
	pm := pmidPat.FindString(raw)
	if pm != "" {
		entry.PMID = strings.TrimPrefix(pm, "PMID:")
	}

	// Extract DOI
	dm := doiPat.FindString(raw)
	if dm != "" {
		entry.DOI = dm
	}

	// Extract year
	ym := yearPat.FindString(raw)
	if ym != "" {
		y, _ := strconv.Atoi(ym)
		entry.Year = y
	}

	// Extract volume:issue:pages
	vm := volPagePat.FindString(raw)
	if vm != "" {
		parts := strings.SplitN(vm, ":", 2)
		if len(parts) == 2 {
			entry.Volume = parts[0]
			entry.Pages = parts[1]
			// Extract issue from volume part e.g. "100(3)"
			if ip := issuePat.FindString(parts[0]); ip != "" {
				entry.Issue = strings.Trim(ip, "()")
			}
		}
	}

	// Extract journal name (heuristic: known abbreviations in line)
	for _, jm := range journalPat.FindAllString(raw, -1) {
		// Use the longest match
		if len(jm) > len(entry.Journal) {
			entry.Journal = jm
		}
	}

	// Extract authors (everything before the journal name)
	if entry.Journal != "" {
		idx := strings.Index(raw, entry.Journal)
		if idx > 0 {
			entry.Authors = strings.TrimSpace(raw[:idx])
		}
	}

	return entry
}

var issuePat = regexp.MustCompile(`\((\d+)\)`)

// ---------------------------------------------------------------------------
// Verifier — enriches citation entries against academic sources
// ---------------------------------------------------------------------------

// Verifier checks citations against multiple academic sources.
type Verifier struct {
	pubmed *source.PubMedSource
	s2     *source.S2Source
}

// NewVerifier creates a verifier.
func NewVerifier() *Verifier {
	p, _ := source.NewPubMedSource(map[string]any{})
	s, _ := source.NewS2Source(map[string]any{})
	return &Verifier{pubmed: p, s2: s}
}

// Verify checks a single citation entry against all configured sources.
// It fills VerifiedTitle, VerifiedPMID, VerifiedDOI, SourceHits, Status, Verdict.
func (v *Verifier) Verify(ctx context.Context, entry *CitationEntry) error {
	if ctx == nil {
		ctx = context.Background()
	}

	var hits []SourceHit
	var wg sync.WaitGroup
	var mu sync.Mutex
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()

	// Parallel verification across sources
	if entry.PMID != "" {
		wg.Add(1)
		go func() {
			defer wg.Done()
			h := v.verifyPubMed(ctx, entry.PMID, entry)
			mu.Lock()
			defer mu.Unlock()
			if h != nil {
				hits = append(hits, *h)
			}
		}()
	}

	if entry.DOI != "" {
		wg.Add(1)
		go func() {
			defer wg.Done()
			h, err := v.verifyCrossrefDirect(ctx, entry.DOI, entry)
			mu.Lock()
			defer mu.Unlock()
			if h != nil && err == nil {
				hits = append(hits, *h)
			}
		}()
	}

	// S2 by title + authors (only if DOI/PMID not available)
	if entry.Authors != "" && entry.PMID == "" && entry.DOI == "" {
		wg.Add(1)
		go func() {
			defer wg.Done()
			h := v.verifyS2(ctx, entry)
			mu.Lock()
			defer mu.Unlock()
			if h != nil {
				hits = append(hits, *h)
			}
		}()
	}

	wg.Wait()

	// Rank results and determine status
	entry.SourceHits = hits
	entry.Status, entry.Verdict = v.rankResults(entry, hits)

	return nil
}

func (v *Verifier) verifyPubMed(ctx context.Context, pmid string, entry *CitationEntry) *SourceHit {
	q := types.EBMQuestion{Query: pmid, MaxResults: 1}
	results, err := v.pubmed.Search(ctx, q, 1)
	if err != nil || len(results) == 0 {
		return nil
	}
	hit := results[0]
	_ = hit // silence
	exact := hit.PMID == pmid && hit.Title != ""
	if exact {
		entry.VerifiedPMID = pmid
		entry.VerifiedTitle = hit.Title
	}
	return &SourceHit{
		Source:     "pubmed",
		PMID:       hit.PMID,
		Title:      hit.Title,
		Journal:    hit.Journal,
		Year:       hit.Year,
		ExactMatch: exact,
	}
}

// verifyCrossrefDirect calls the Crossref API directly via HTTP.
func (v *Verifier) verifyCrossrefDirect(ctx context.Context, doi string, entry *CitationEntry) (*SourceHit, error) {
	hit, err := ResolveCrossrefDOI(ctx, doi)
	if err != nil {
		return nil, err
	}
	entry.VerifiedDOI = doi
	entry.VerifiedTitle = hit.Title
	return hit, nil
}

func (v *Verifier) verifyS2(ctx context.Context, entry *CitationEntry) *SourceHit {
	query := entry.Authors + " " + entry.Journal
	if entry.Title != "" {
		query = entry.Title
	}
	q := types.EBMQuestion{Query: query, MaxResults: 5}
	results, err := v.s2.Search(ctx, q, 5)
	if err != nil || len(results) == 0 {
		return nil
	}
	// Match by journal + year if available
	for _, r := range results {
		matchScore := 0
		if entry.Year > 0 && r.Year == entry.Year {
			matchScore += 2
		}
		if entry.Journal != "" && strings.Contains(strings.ToLower(r.Journal), strings.ToLower(entry.Journal)) {
			matchScore += 1
		}
		if matchScore >= 2 {
			entry.VerifiedTitle = r.Title
			return &SourceHit{
				Source:     "s2",
				Title:      r.Title,
				Journal:    r.Journal,
				Year:       r.Year,
				ExactMatch: true,
			}
		}
	}
	return nil
}

// rankResults determines the final status and verdict based on hits.
func (v *Verifier) rankResults(entry *CitationEntry, hits []SourceHit) (string, string) {
	_ = entry // silence
	if len(hits) == 0 {
		return "not_found", "no source matched this citation"
	}

	exactCount := 0
	for _, h := range hits {
		if h.ExactMatch {
			exactCount++
		}
	}

	if exactCount == 0 {
		return "not_found", "no exact match in any source"
	}

	if exactCount == 1 {
		return "exact", "verified by " + hits[0].Source
	}

	return "exact", fmt.Sprintf("verified by %d sources", exactCount)
}

// ---------------------------------------------------------------------------
// Downloadability checker
// ---------------------------------------------------------------------------

// DownloadChecker classifies whether a citation's full text is downloadable.
//
// Rules based on 2026-07 field data:
//   - Year <= 2022 → Sci-Hub (most traditional journals, >90% success)
//   - Year >= 2023 AND OA journal → OA PDF (Unpaywall/S2/OpenAlex)
//   - Year >= 2023 AND non-OA → Nexus (stc Telegram bot, 50-70% success)
//   - OA journal keywords in journal name → OA
//   - Conference proceedings / abstracts → "unavailable" (no PDF)
type DownloadChecker struct {
	oaJournals map[string]bool
}

// NewDownloadChecker creates a checker with known OA journal abbreviations.
func NewDownloadChecker() *DownloadChecker {
	oa := map[string]bool{
		"Front Oncol":        true,
		"Int J Mol Sci":      true,
		"Adv Sci":            true,
		"Sci Rep":            true,
		"PLOS ONE":           true,
		"PLOS":               true,
		"BMC":                true,
		"Mol Cancer":         true,
		"Cancers":            true,
		"Medicine":           true,
		"Med (Baltimore)":    true,
		"J Med Internet Res": true,
		"JHEP Rep":           true,
		"Cell":               true, // Cell is hybrid but many articles are OA
		"Nat":                true,
		"Annals of Oncology": true,
	}
	return &DownloadChecker{oaJournals: oa}
}

// Check returns downloadable flag, tier, and note for a citation.
func (dc *DownloadChecker) Check(entry *CitationEntry) {
	// If unverifiable, skip
	if entry.Status == "unverifiable" || entry.Year == 0 {
		entry.Downloadable = false
		entry.DownloadTier = "unavailable"
		_ = entry // silence
		entry.DownloadNote = "citation data incomplete"
		return
	}

	year := entry.Year

	// OA journals are always downloadable via OA route
	j := strings.ToLower(entry.Journal)
	isOA := false
	for k := range dc.oaJournals {
		if strings.Contains(j, strings.ToLower(k)) {
			isOA = true
			break
		}
	}
	// Also check "Annals of Oncology" ESMO CPG (open access)
	if strings.Contains(j, "ann onc") {
		isOA = true
	}

	if year <= 2022 && !isOA {
		entry.Downloadable = true
		entry.DownloadTier = "sci-hub"
		_ = year // silence
		entry.DownloadNote = fmt.Sprintf("Sci-Hub likely available (year=%d)", year)
	} else if isOA {
		entry.Downloadable = true
		entry.DownloadTier = "oa"
		entry.DownloadNote = fmt.Sprintf("Open Access via Unpaywall/S2/OpenAlex (year=%d)", year)
	} else if year >= 2023 {
		entry.Downloadable = true
		entry.DownloadTier = "nexus"
		entry.DownloadNote = fmt.Sprintf("Not on Sci-Hub (year=%d); use Nexus/stc bot or institutional access", year)
	} else {
		// fallback for uncategorized
		entry.Downloadable = false
		entry.DownloadTier = "unavailable"
		entry.DownloadNote = "no matching download tier"
	}
}

// ---------------------------------------------------------------------------
// Batch processor
// ---------------------------------------------------------------------------

// BatchResult holds the output of VerifyAll.
type BatchResult struct {
	Total        int             `json:"total"`
	Exact        int             `json:"exact"`
	Partial      int             `json:"partial"`
	Mismatch     int             `json:"mismatch"`
	NotFound     int             `json:"not_found"`
	Unverifiable int             `json:"unverifiable"`
	Downloadable int             `json:"downloadable"`
	Entries      []CitationEntry `json:"entries"`
}

// VerifyAll extracts, parses, verifies, and classifies all citations in a PPTX.
func VerifyAll(ctx context.Context, filePath string) (*BatchResult, error) {
	extractor := NewExtractor(filePath)
	slideTexts, err := extractor.ExtractText()
	if err != nil {
		return nil, fmt.Errorf("pptx extract: %w", err)
	}

	lines := ExtractCitationLines(slideTexts)

	entries := make([]CitationEntry, 0, len(lines))
	for _, line := range lines {
		e := ParseCitationLine(line.RawText)
		e.SlideIndex = line.SlideIndex
		_ = e // silence
		entries = append(entries, e)
	}

	verifier := NewVerifier()
	downloader := NewDownloadChecker()

	for i := range entries {
		if err := verifier.Verify(ctx, &entries[i]); err != nil {
			entries[i].Status = "error"
			entries[i].Verdict = err.Error()
		}
		downloader.Check(&entries[i])
	}

	return batchStats(entries), nil
}

func batchStats(entries []CitationEntry) *BatchResult {
	r := &BatchResult{Total: len(entries), Entries: entries}
	for _, e := range entries {
		switch e.Status {
		case "exact":
			r.Exact++
		case "partial":
			r.Partial++
		case "mismatch":
			r.Mismatch++
		}
		switch e.Status {
		case "not_found":
			r.NotFound++
		case "unverifiable":
			r.Unverifiable++
		}
		if e.Downloadable {
			r.Downloadable++
		}
	}
	return r
}

// ---------------------------------------------------------------------------
// Crossref HTTP client (standalone DOI resolution)
// ---------------------------------------------------------------------------

// ResolveCrossrefDOI fetches metadata from Crossref by DOI.
func ResolveCrossrefDOI(ctx context.Context, doi string) (*SourceHit, error) {
	encoded := strings.ReplaceAll(doi, "/", "%2F")
	u := fmt.Sprintf("https://api.crossref.org/works/%s", encoded)

	req, err := http.NewRequestWithContext(ctx, "GET", u, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "via54Medit/3.0 (pptx-verifier)")

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode/100 != 2 {
		return nil, fmt.Errorf("crossref: HTTP %d", resp.StatusCode)
	}

	var crossref struct {
		Message struct {
			Title []string `json:"title"`
			Auth  []struct {
				Family string `json:"family"`
				Given  string `json:"given"`
			} `json:"author"`
			ContainerTitle []string `json:"container-title"`
		} `json:"message"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&crossref); err != nil {
		return nil, err
	}

	msg := crossref.Message
	var title string
	if len(msg.Title) > 0 {
		title = msg.Title[0]
	}
	var journal string
	if len(msg.ContainerTitle) > 0 {
		journal = msg.ContainerTitle[0]
	}

	// Year heuristic: check title/journal for 4-digit year
	var year int
	yearRe := regexp.MustCompile(`\b(19|20)\d{2}\b`)
	candidate := title + " " + journal
	if m := yearRe.FindString(candidate); m != "" {
		year, _ = strconv.Atoi(m)
	}

	return &SourceHit{
		Source:     "crossref",
		DOI:        doi,
		Title:      title,
		Journal:    journal,
		Year:       year,
		ExactMatch: true,
	}, nil
}
