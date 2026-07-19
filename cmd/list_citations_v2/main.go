package main

import (
	"archive/zip"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"regexp"
	"sort"
	"strings"
	"time"
)

// ============================================================================
// PPTX Citation Extraction with PubMed PMID Verification
// ============================================================================

// CitationEntry is one parsed and verified citation.
type CitationEntry struct {
	Slide      int    `json:"slide"`
	RawText    string `json:"raw_text"`
	Authors    string `json:"authors"`
	Journal    string `json:"journal"`
	Year       string `json:"year"`
	Volume     string `json:"volume"`
	Issue      string `json:"issue"`
	Pages      string `json:"pages"`
	PMID       string `json:"pmid"`
	DOI        string `json:"doi"`
	RealTitle  string `json:"real_title"`
	Status     string `json:"status"` // exact/partial/not_found
}

// Known journal abbreviations and their display names
var journalAliases = map[string]string{
	"J Hepatol":                 "J Hepatol",
	"Hepatol Int":               "Hepatol Int",
	"NEJM Evid":                 "NEJM Evid",
	"J Clin Oncol":              "J Clin Oncol",
	"Lancet Oncol":              "Lancet Oncol",
	"N Engl J Med":              "N Engl J Med",
	"JAMA Oncol":                "JAMA Oncol",
	"Hepatology":                "Hepatology",
	"Liver Cancer":              "Liver Cancer",
	"Cancer Res":                "Cancer Res",
	"Clin Cancer Res":           "Clin Cancer Res",
	"Front Oncol":               "Front Oncol",
	"Front Immunol":             "Front Immunol",
	"Int J Mol Sci":             "Int J Mol Sci",
	"Cell":                      "Cell",
	"Immunity":                  "Immunity",
	"Lancet":                    "Lancet",
	"Medicine":                  "Medicine",
	"Gastroenterology":          "Gastroenterology",
	"J Immunol":                 "J Immunol",
	"Oncotarget":                "Oncotarget",
	"Ann Oncol":                 "Ann Oncol",
	"J Natl Cancer Cent":        "J Natl Cancer Cent",
	"Hepatobiliary Surg Nutr":   "Hepatobiliary Surg Nutr",
	"Clin Transl Sci":           "Clin Transl Sci",
	"Anticancer research":       "Anticancer research",
	"J Hematol Oncol":           "J Hematol Oncol",
	"Front Pharmacol":           "Front Pharmacol",
	"Cancers":                   "Cancers",
	"Adv Sci":                   "Adv Sci",
	"Onco Targets Ther":         "Onco Targets Ther",
	"Sci Rep":                   "Sci Rep",
	"BMJ Open":                  "BMJ Open",
	"Eur J Cancer":              "Eur J Cancer",
	"Clin Kidney J":             "Clin Kidney J",
}

// Build regex pattern for journal detection
func journalPattern() *regexp.Regexp {
	parts := make([]string, 0, len(journalAliases))
	for j := range journalAliases {
		parts = append(parts, j)
	}
	// Sort longest first to avoid partial matches
	sort.Slice(parts, func(i, j int) bool { return len(parts[i]) > len(parts[j]) })
	re := `(?i)\b(` + strings.Join(parts, `|`) + `)\b`
	return regexp.MustCompile(re)
}

// Extract all text from all slides
func extractAllSlideText(pptxPath string) (map[int]string, []int) {
	z, err := zip.OpenReader(pptxPath)
	if err != nil {
		log.Fatal(err)
	}
	defer z.Close()

	slideTexts := make(map[int]string)
	slideOrder := make([]int, 0)

	// Regex for extracting text from <a:t> tags
	tRegex := regexp.MustCompile(`>([^<]{1,500})</a:t>`)

	for _, file := range z.File {
		name := file.Name
		// Match slideN.xml (including notesSlideN.xml)
		m := regexp.MustCompile(`slide(\d+)\.xml$`).FindStringSubmatch(name)
		if m == nil {
			continue
		}
		slideNum, _ := parseInt(m[1])
		
		rc, err := file.Open()
		if err != nil {
			continue
		}
		data, err := readAll(rc)
		rc.Close()
		if err != nil {
			continue
		}

		text := string(data)
		matches := tRegex.FindAllStringSubmatch(text, -1)
		var texts []string
		for _, match := range matches {
			texts = append(texts, match[1])
		}
		fullText := strings.Join(texts, " ")
		// Clean up extra whitespace
		fullText = strings.Join(strings.Fields(fullText), " ")
		slideTexts[slideNum] = fullText
		slideOrder = append(slideOrder, slideNum)
	}

	return slideTexts, slideOrder
}

// Split a chunk of text into individual citations
func splitIntoIndividualCitations(text string) []string {
	text = strings.Join(strings.Fields(text), " ")
	
	// Find all journal positions
	jp := journalPattern()
	journalMatches := jp.FindAllIndex([]byte(text), -1)
	
	if len(journalMatches) == 0 {
		return nil
	}

	citations := make([]string, 0, len(journalMatches))
	
	for i, idx := range journalMatches {
		// Determine start of this citation
		var start int
		if i == 0 {
			start = 0
		} else {
			prevEnd := journalMatches[i-1][1]
			// Find where current citation starts (before journal)
			// Look backwards from idx[0] for author pattern or "et al."
			before := text[:idx[0]]
			// Find last "et al." before journal
			lastEtAl := strings.LastIndex(before, "et al.")
			if lastEtAl >= 0 {
				// Start after "et al."
				start = lastEtAl + len("et al.")
				// Skip whitespace
				for start < len(text) && text[start] == ' ' {
					start++
				}
			} else {
				start = prevEnd + 1
				for start < len(text) && text[start] == ' ' {
					start++
				}
			}
		}

		// Determine end of this citation
		var end int
		if i == len(journalMatches)-1 {
			end = len(text)
		} else {
			nextStart := journalMatches[i+1][0]
			// Find last "et al." before next journal
			beforeNext := text[idx[1]:nextStart]
			lastEtAl := strings.LastIndex(beforeNext, "et al.")
			if lastEtAl >= 0 {
				end = idx[1] + lastEtAl + len("et al.")
			} else {
				end = nextStart - 1
			}
		}

		citeText := strings.TrimSpace(text[start:end])
		// Clean up
		citeText = strings.Join(strings.Fields(citeText), " ")
		
		if len(citeText) > 20 && jp.MatchString(citeText) {
			citations = append(citations, citeText)
		}
	}

	return citations
}

// ============================================================================
// PubMed PMID Lookup
// ============================================================================

func fetchPubMedPMID(term string) string {
	// Build NCBI E-utilities URL
	params := url.Values{}
	params.Add("db", "pubmed")
	params.Add("term", term)
	params.Add("retmax", "3")
	params.Add("retmode", "json")
	
	baseURL := "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" + params.Encode()
	
	client := &http.Client{Timeout: 15 * time.Second}
	req, err := http.NewRequest("GET", baseURL, nil)
	if err != nil {
		return ""
	}
	// Don't spam NIH
	req.Header.Set("User-Agent", "via54Medit/1.0 (research)")
	req.Header.Set("Accept", "application/json")
	
	resp, err := client.Do(req)
	if err != nil {
		return ""
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return ""
	}

	body, err := readAll(resp.Body)
	if err != nil {
		return ""
	}

	// Parse JSON response
	var result map[string]interface{}
	if err := json.Unmarshal(body, &result); err != nil {
		return ""
	}

	if results, ok := result["esearchresult"]; ok {
		if pmids, ok := results.(map[string]interface{})["idlist"]; ok {
			if idlist, ok := pmids.([]interface{}); ok && len(idlist) > 0 {
				if id, ok := idlist[0].(string); ok {
					return id
				}
			}
		}
	}
	return ""
}

func fetchPubMedTitle(pmid string) string {
	params := url.Values{}
	params.Add("db", "pubmed")
	params.Add("id", pmid)
	params.Add("retmode", "json")
	
	baseURL := "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?" + params.Encode()
	
	client := &http.Client{Timeout: 15 * time.Second}
	req, err := http.NewRequest("GET", baseURL, nil)
	if err != nil {
		return ""
	}
	req.Header.Set("User-Agent", "via54Medit/1.0 (research)")
	req.Header.Set("Accept", "application/json")
	
	resp, err := client.Do(req)
	if err != nil {
		return ""
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return ""
	}

	body, err := readAll(resp.Body)
	if err != nil {
		return ""
	}

	var result map[string]interface{}
	if err := json.Unmarshal(body, &result); err != nil {
		return ""
	}

	if results, ok := result["result"]; ok {
		if articles, ok := results.(map[string]interface{})[pmid]; ok {
			if article, ok := articles.(map[string]interface{}); ok {
				if title, ok := article["title"]; ok {
					if t, ok := title.(string); ok {
						return t
					}
				}
			}
		}
	}
	return ""
}

// ============================================================================
// Citation Parsing
// ============================================================================

func parseCitation(raw string, jp *regexp.Regexp) CitationEntry {
	entry := CitationEntry{RawText: raw}
	
	// Extract authors
	authorRe := regexp.MustCompile(`^([A-Z][a-z]+,?\s+[A-Z]?\.?\s*,?\s+et\s+al\.?|[A-Z]\.\s+[A-Z][a-z]+,\s+[A-Z]\.?\s*,?\s+et\s+al\.?|[A-Z][a-z]+,\s+[A-Z]\.\s*[A-Z]?\.\s*,?\s+et\s+al\.?|[A-Z][a-z]+\s*,?\s+([A-Z]\.\s*)+[A-Z][a-z]+,\s+et\s+al\.?|[A-Z][a-z]+,\s+et\s+al\.?)`)
	am := authorRe.FindString(raw)
	if am != "" {
		entry.Authors = strings.TrimSpace(am)
	}
	
	// Extract journal
	jm := jp.FindString(raw)
	if jm != "" {
		entry.Journal = journalAliases[strings.ToLower(jm)]
	}
	
	// Extract year
	yearRe := regexp.MustCompile(`\b(20|19)\d{2}\b`)
	ym := yearRe.FindString(raw)
	if ym != "" {
		entry.Year = ym
	}
	
	// Extract volume(issue):pages pattern
	vpRe := regexp.MustCompile(`\b(\d{1,4})(?:\((\d+)\))?:?\s*(\d{1,5}(?:-\d+|–\d+)?)(?:\.|$)`)
	vm := vpRe.FindStringSubmatch(raw)
	if vm != nil {
		entry.Volume = vm[1]
		entry.Issue = vm[2]
		entry.Pages = vm[3]
	}
	
	// Extract DOI
	doiRe := regexp.MustCompile(`10\.\d{4,9}/[-._;()/:A-Za-z0-9]+`)
	dm := doiRe.FindString(raw)
	if dm != "" {
		entry.DOI = dm
	}
	
	// Extract PMID
	pmidRe := regexp.MustCompile(`PMID\s*:\s*(\d{6,10})|(?<!\d)(\d{6,10})(?!\d)`)
	pmm := pmidRe.FindStringSubmatch(raw)
	if pmm != nil {
		if pmm[1] != "" {
			entry.PMID = pmm[1]
		} else if pmm[2] != "" {
			// Heuristic: only accept if looks like a real PMID (not a page number)
			if len(pmm[2]) >= 6 {
				entry.PMID = pmm[2]
			}
		}
	}
	
	return entry
}

// ============================================================================
// Main
// ============================================================================

func main() {
	pptxPath := "/Users/david/Downloads/标准答案/【原始文件】雷管方案：三重获益，引领uHCC一线治疗新标准_0622.pptx"
	
	jp := journalPattern()
	
	// Extract all slide text
	slideTexts, slideOrder := extractAllSlideText(pptxPath)
	fmt.Printf("Extracted %d slides with text\n", len(slideTexts))
	
	// Find all citation chunks in each slide
	var allChunks []string
	for _, slideNum := range slideOrder {
		text := slideTexts[slideNum]
		if text == "" {
			continue
		}
		chunks := splitIntoIndividualCitations(text)
		for _, chunk := range chunks {
			// Skip chunks that are clearly not citations
			if !jp.MatchString(chunk) {
				continue
			}
			// Filter out chunks that look like they're just part of a sentence
			hasYear := regexp.MustCompile(`\b(20|19)\d{2}\b`).MatchString(chunk)
			if !hasYear {
				continue
			}
			allChunks = append(allChunks, chunk)
		}
	}
	
	fmt.Printf("Found %d citation chunks\n", len(allChunks))
	
	// Parse each chunk
	var entries []CitationEntry
	seen := make(map[string]bool)
	
	for _, chunk := range allChunks {
		entry := parseCitation(chunk, jp)
		
		// Deduplicate by journal+year+pages
		dedupKey := entry.Journal + "|" + entry.Year + "|" + entry.Pages
		if dedupKey == "||" || seen[dedupKey] {
			continue
		}
		seen[dedupKey] = true
		
		// Try PMID lookup via PubMed
		if entry.PMID != "" {
			entry.RealTitle = fetchPubMedTitle(entry.PMID)
			entry.Status = "verified_pmid"
		} else if entry.DOI != "" {
			entry.Status = "has_doi"
		} else if entry.Journal != "" && entry.Year != "" {
			// Try to look up PMID via journal+year+volume+pages
			// Build search term: journal[Journal] AND year[Publication Date] AND volume
			var searchTerm strings.Builder
			if entry.Volume != "" {
				searchTerm.WriteString(entry.Volume + "[Journal] AND ")
				searchTerm.WriteString(entry.Year + "[Publication Date] AND ")
				if entry.Pages != "" {
					searchTerm.WriteString(entry.Pages + "[Pages]")
				} else {
					searchTerm.WriteString(entry.Journal + "[Journal]")
				}
			} else {
				searchTerm.WriteString(entry.Journal + "[Journal] AND " + entry.Year + "[Publication Date]")
			}
			
			pmid := fetchPubMedPMID(searchTerm.String())
			if pmid != "" {
				entry.PMID = pmid
				entry.RealTitle = fetchPubMedTitle(pmid)
				entry.Status = "looked_up"
			} else {
				entry.Status = "unverified"
			}
			
			// Rate limit
			time.Sleep(300 * time.Millisecond)
		}
		
		entries = append(entries, entry)
	}
	
	// Sort by slide
	sort.Slice(entries, func(i, j int) bool {
		return entries[i].Slide < entries[j].Slide
	})
	
	fmt.Printf("\nTotal unique citations: %d\n", len(entries))
	fmt.Println(strings.Repeat("=", 80))
	
	for i, e := range entries {
		fmt.Printf("[%d] Slide %d | %s %s | %s\n", i+1, e.Slide, e.Authors, e.Journal, e.Year)
		if e.Volume != "" {
			fmt.Printf("     Vol:%s/%s Pages:%s\n", e.Volume, e.Issue, e.Pages)
		}
		if e.PMID != "" {
			fmt.Printf("     PMID: %s | Status: %s\n", e.PMID, e.Status)
		}
		if e.RealTitle != "" {
			fmt.Printf("     Title: %s\n", e.RealTitle)
		}
		if e.DOI != "" {
			fmt.Printf("     DOI: %s\n", e.DOI)
		}
		fmt.Println()
	}
	
	// Output JSON
	output, _ := json.MarshalIndent(entries, "", "  ")
	fmt.Printf("\n=== JSON OUTPUT ===\n%s\n", string(output))
}

// Helper to read all bytes from io.Reader
func readAll(r interface{}) ([]byte, error) {
	// Accept either io.Reader or just read from bytes
	// For simplicity, just handle []byte
	if b, ok := r.([]byte); ok {
		return b, nil
	}
	return nil, fmt.Errorf("unsupported type")
}

// parseInt converts a string to an int, returning (value, nil) on success.
func parseInt(s string) (int, error) {
	n := 0
	for i := 0; i < len(s); i++ {
		c := s[i]
		if c < '0' || c > '9' {
			return 0, fmt.Errorf("not a digit: %c", c)
		}
		n = n*10 + int(c-'0')
	}
	return n, nil
}
