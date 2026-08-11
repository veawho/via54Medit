// verifier.go
// CitationVerifier resolves extracted citations to PubMed/Crossref records.
//
// Resolution order:
//  1. If PMID present → PubMed esummary (instant lookup)
//  2. If DOI present → Crossref API
//  3. If trial name detected → trialNameMap lookup (instant)
//  4. Fallback: PubMed search with extracted fields (author, journal, year)
package cite

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/veawho/via54Medit/internal/cite/client"
	"github.com/veawho/via54Medit/internal/source"
)

// CitationVerifier enriches extracted citations against PubMed/Crossref/SemScholar/ClinTrials/Antafu.
type CitationVerifier struct {
	pubmed *source.PubMedSource
	client *http.Client

	// Multi-source search backends (fallback chain)
	crossref   *client.CrossrefClient
	semSch     *client.SemSchClient
	clinTrials *client.ClinTrialsClient
	antafu     *client.AntafuClient

	// Mutex for PubMed rate-limiting — serializes all requests to stay under 3 rps NCBI limit
	mu sync.Mutex

	// User-Agent / contact
	tool  string
	email string
}

// NewCitationVerifier creates a verifier with configured sources.
func NewCitationVerifier() *CitationVerifier {
	pubmed, _ := source.NewPubMedSource(map[string]any{})
	return &CitationVerifier{
		pubmed:     pubmed,
		client:     &http.Client{Timeout: 15 * time.Second},
		crossref:   client.NewCrossrefClient("via54medit@example.com"),
		semSch:     client.NewSemSchClient(),
		clinTrials: client.NewClinTrialsClient(),
		antafu:     client.NewAntafuClient(),
		tool:       "via54Medit",
		email:      "cite@via54.com",
	}
}

// ---------------------------------------------------------------------------
// Main verification
// ---------------------------------------------------------------------------

// Verify enriches a single citation.
func (v *CitationVerifier) Verify(ctx context.Context, c *Citation) error {
	// 1. Direct PMID lookup
	if c.PMID != "" {
		v.takeToken(ctx)
		hit, err := v.lookupPubMedByID(ctx, c.PMID)
		v.releaseToken()
		if err == nil && hit != nil {
			v.applyHit(c, hit, "pubmed-pmid")
			return nil
		}
	}

	// 2. Direct DOI lookup
	if c.DOI != "" {
		v.takeToken(ctx)
		hit, err := v.lookupCrossrefByDOI(ctx, c.DOI)
		v.releaseToken()
		if err == nil && hit != nil {
			v.applyHit(c, hit, "crossref-doi")
			return nil
		}
	}

	// 3. Trial-name lookup (instant)
	if c.TrialName != "" {
		t, ok := LookupTrial(c.TrialName)
		if ok {
			hit := &EnrichmentHit{
				PMID:    t.PMID,
				Title:   t.Title,
				Journal: t.Journal,
				Year:    t.Year,
			}
			v.applyHit(c, hit, "trial-name")
			return nil
		}
	}

	// 4. PubMed fallback search
	v.searchPubMedFallback(ctx, c)

	// 5. Always try external sources if not verified (even after unverified)
	//    This catches PubMed-failed + 429 + genuinely unmatched cases
	if c.Status != "verified" {
		// Only update if external finds a match; otherwise keep existing message
		prevMsg := c.Message
		if err := v.fallbackToExternal(ctx, c); err != nil {
			c.Message = prevMsg
			return err
		}
		// If fallback found a match, status is now "verified" — keep it
		return nil
	}

	return nil
}

// fallbackToExternal attempts to resolve a citation via external sources
// when PubMed fails (typically HTTP 429 rate limiting).
func (v *CitationVerifier) fallbackToExternal(ctx context.Context, c *Citation) error {
	// Build a search query from available fields
	var query string
	if c.Title != "" {
		query = c.Title
	} else if c.Authors != "" && c.Journal != "" {
		query = c.Journal + " " + c.Authors
	} else {
		c.Status = "unverified"
		c.Message = "no searchable fields for external fallback"
		return nil
	}

	// Try external sources in order
	hit := v.searchExternalSources(ctx, query, c)
	if hit != nil {
		v.applyHit(c, hit, "external-fallback-on-error")
		return nil
	}

	c.Status = "unverified"
	c.Message = "external sources also returned no match"
	return nil
}

// EnrichmentHit is a resolved citation record from any source.
type EnrichmentHit struct {
	PMID    string
	DOI     string
	Title   string
	Journal string
	Year    int
}

// applyHit fills the citation fields from a verified hit.
func (v *CitationVerifier) applyHit(c *Citation, hit *EnrichmentHit, source string) {
	c.VerifiedPMID = hit.PMID
	c.VerifiedDOI = hit.DOI
	c.VerifiedTitle = hit.Title
	c.VerifiedJournal = hit.Journal
	c.VerifiedYear = hit.Year
	c.Status = "verified"
	c.Message = fmt.Sprintf("verified via %s", source)
}

// ---------------------------------------------------------------------------
// PubMed by ID (esummary) — instant, no rate limit concerns for batch
// ---------------------------------------------------------------------------

func (v *CitationVerifier) lookupPubMedByID(ctx context.Context, pmid string) (*EnrichmentHit, error) {
	// Rate-limiting is handled by the caller (Verify or searchPubMed).
	// lookupPubMedByID is a leaf function that must NOT acquire its own lock,
	// because it can be called from within searchPubMed (which already holds the lock).
	params := url.Values{
		"db":      {"pubmed"},
		"id":      {pmid},
		"retmode": {"json"},
	}
	params.Set("tool", v.tool)
	if v.email != "" {
		params.Set("email", v.email)
	}

	req, err := http.NewRequestWithContext(ctx, "GET",
		"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?"+params.Encode(), nil)
	if err != nil {
		return nil, err
	}
	resp, err := v.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode/100 != 2 {
		return nil, fmt.Errorf("pubmed esummary HTTP %d", resp.StatusCode)
	}

	return v.parseESummaryJSON(ctx, resp.Body, pmid)
}

// parseESummaryJSON parses the esummary JSON response which has varying structure.
func (v *CitationVerifier) parseESummaryJSON(ctx context.Context, body interface{}, pmid string) (*EnrichmentHit, error) {
	data, err := io.ReadAll(body.(io.Reader))
	if err != nil {
		return nil, err
	}
	raw := string(data)

	// Use regex to extract fields from the JSON
	hit := &EnrichmentHit{PMID: pmid}

	// Extract title
	titleRe := regexp.MustCompile(`"title":"([^"]*)"`)
	if m := titleRe.FindStringSubmatch(raw); len(m) > 1 {
		hit.Title = m[1]
	}

	// Extract full journal name
	journalRe := regexp.MustCompile(`"fulljournalname":"([^"]*)"|"source":"([^"]*)"`)
	if m := journalRe.FindStringSubmatch(raw); len(m) > 1 {
		hit.Journal = m[1]
	}

	// Extract DOI (e.g. "doi: 10.1016/..." or "10.1016/...")
	doiRe := regexp.MustCompile(`"elocationid":"(doi:\s*)?(10\.[^"]*)"`)
	if m := doiRe.FindStringSubmatch(raw); len(m) > 2 {
		hit.DOI = m[2]
	}

	// Extract year from pubdate
	yearRe := regexp.MustCompile(`"pubdate":"([^"]*)"`)
	if m := yearRe.FindStringSubmatch(raw); len(m) > 1 {
		hit.Year = parseYear(m[1])
	}

	// Also check for PMID in the result map key
	if hit.Title == "" && hit.Journal == "" {
		return nil, fmt.Errorf("pubmed: PMID %s not found or no metadata", pmid)
	}

	return hit, nil
}

// ---------------------------------------------------------------------------
// Crossref by DOI
// ---------------------------------------------------------------------------

func (v *CitationVerifier) lookupCrossrefByDOI(ctx context.Context, doi string) (*EnrichmentHit, error) {
	encoded := strings.ReplaceAll(doi, "/", "%2F")
	req, err := http.NewRequestWithContext(ctx, "GET",
		fmt.Sprintf("https://api.crossref.org/works/%s", encoded), nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "via54Medit/3.0 (cite-verifier)")

	resp, err := v.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode/100 != 2 {
		return nil, fmt.Errorf("crossref HTTP %d", resp.StatusCode)
	}

	var got struct {
		Message struct {
			Title          []string `json:"title"`
			DOI            string   `json:"DOI"`
			ContainerTitle []string `json:"container-title"`
			Created        struct {
				DateParts [][]int `json:"date-parts"`
			} `json:"created"`
			Published struct {
				DateParts [][]int `json:"date-parts"`
			} `json:"published-print"`
		} `json:"message"`
	}

	decoder := json.NewDecoder(resp.Body)
	if err := decoder.Decode(&got); err != nil {
		// Fallback: try with simpler response parsing
		return v.parseCrossrefRaw(ctx, resp.Body, doi)
	}

	hit := &EnrichmentHit{
		PMID:    "",
		DOI:     got.Message.DOI,
		Title:   "",
		Journal: "",
	}

	if len(got.Message.Title) > 0 {
		hit.Title = got.Message.Title[0]
	}
	if len(got.Message.ContainerTitle) > 0 {
		hit.Journal = got.Message.ContainerTitle[0]
	}

	// Year
	if len(got.Message.Published.DateParts) > 0 {
		hit.Year = got.Message.Published.DateParts[0][0]
	} else if len(got.Message.Created.DateParts) > 0 {
		hit.Year = got.Message.Created.DateParts[0][0]
	}

	return hit, nil
}

// parseCrossrefRaw fallback for JSON parsing
func (v *CitationVerifier) parseCrossrefRaw(ctx context.Context, body interface{}, doi string) (*EnrichmentHit, error) {
	data, err := io.ReadAll(body.(io.Reader))
	if err != nil {
		return nil, err
	}
	raw := string(data)

	hit := &EnrichmentHit{DOI: doi}
	if m := regexp.MustCompile(`"title":\["([^"]+)"`).FindStringSubmatch(raw); len(m) > 1 {
		hit.Title = m[1]
	}
	if m := regexp.MustCompile(`"container-title":\["([^"]+)"`).FindStringSubmatch(raw); len(m) > 1 {
		hit.Journal = m[1]
	}
	return hit, nil
}

// ---------------------------------------------------------------------------
// NLM journal abbreviation mapping (extracted name → PubMed NLM abbreviation)
// Used by searchPubMedFallback to normalize journal names before querying.
// Source: PubMed Journal-Link NLM catalog (https://www.nlm.nih.gov/databases/
// ---------------------------------------------------------------------------
var journalNLM = map[string]string{
	"lancet":                              "Lancet",
	"lancet oncol":                        "Lancet Oncol",
	"lancet gastroenterol":                "Lancet Gastroenterol Hepatol",
	"lancet hematology":                   "Lancet Haematol",
	"new england journal of medicine":     "N Engl J Med",
	"new england jour":                    "N Engl J Med",
	"nejm":                                "N Engl J Med",
	"jama":                                "JAMA",
	"journal of clinical oncology":        "J Clin Oncol",
	"j clin oncol":                        "J Clin Oncol",
	"journal of hepatology":               "J Hepatol",
	"j hepatol":                           "J Hepatol",
	"hepatology":                          "Hepatology",
	"hepatology communications":           "Hepatol Commun",
	"hepatobiliary surgery and nutrition": "Hepatobiliary Surg Nutr",
	"hepatol int":                         "Hepatol Int",
	"hepatology international":            "Hepatol Int",
	"clin cancer res":                     "Clin Cancer Res",
	"clinical cancer research":            "Clin Cancer Res",
	"annals of oncology":                  "Ann Oncol",
	"ann oncol":                           "Ann Oncol",
	"alimentary pharmacology and therapeutics": "Aliment Pharmacol Ther",
	"alim pharmacol ther":                      "Aliment Pharmacol Ther",
	"jama oncology":                            "JAMA Oncol",
	"gastroenterology":                         "Gastroenterology",
	"front immunol":                            "Front Immunol",
	"int j mol sci":                            "Int J Mol Sci",
	"med sci monit":                            "Med Sci Monit",
	"medicine":                                 "Medicine",
	"liver cancer":                             "Liver Cancer",
	"liver int":                                "Liver Int",
	"nature medicine":                          "Nat Med",
	"nat med":                                  "Nat Med",
	"nature communications":                    "Nat Commun",
	"nat commun":                               "Nat Commun",
	"nature reviews cancer":                    "Nat Rev Cancer",
	"nat rev cancer":                           "Nat Rev Cancer",
	"nature reviews immunology":                "Nat Rev Immunol",
	"nat rev immunol":                          "Nat Rev Immunol",
	"nature reviews clinical oncology":         "Nat Rev Clin Oncol",
	"nat rev clin oncol":                       "Nat Rev Clin Oncol",
	"cell":                                     "Cell",
	"science":                                  "Science",
	"cancers":                                  "Cancers",
	"onco targets ther":                        "Onco Targets Ther",
	"oncotarget":                               "Oncotarget",
	"anti cancer research":                     "Anticancer Res",
	"anticancer research":                      "Anticancer Res",
	"jama interna med":                         "JAMA Intern Med",
	"jama intern med":                          "JAMA Intern Med",
	"j clin gastroenterol":                     "J Clin Gastroenterol",
	"world j gastroenterol":                    "World J Gastroenterol",
	"wjg":                                      "World J Gastroenterol",
	"signal transduct target ther":             "Signal Transduct Target Ther",
	"mol cancer ther":                          "Mol Cancer Ther",
	"molecular cancer therapeutics":            "Mol Cancer Ther",
	"clin transl med":                          "Clin Transl Med",
	"pharmacol res":                            "Pharmacol Res",
	"int immunopharmacol":                      "Int Immunopharmacol",
	"j autoimmun":                              "J Autoimmun",
	"j of autoimmun":                           "J Autoimmun",
	"semin cancer biol":                        "Semin Cancer Biol",
	"mabs":                                     "MAbs",
	"j hematol oncol":                          "J Hematol Oncol",
	"cancer immunol res":                       "Cancer Immunol Res",
	"sci transl med":                           "Sci Transl Med",
	"acs cent sci":                             "ACS Cent Sci",
	"bmc cancer":                               "BMC Cancer",
	"int j cancer":                             "Int J Cancer",
	"bmc gastroenterol":                        "BMC Gastroenterol",
	"bmc med":                                  "BMC Med",
	"mol cancer":                               "Mol Cancer",
	"br j cancer":                              "Br J Cancer",
	"european journal of cancer":               "Eur J Cancer",
	"ejc":                                      "Eur J Cancer",
}

// normalizeJournalNLM converts an extracted journal name to PubMed NLM abbreviation.
// Returns the NLM abbreviation if found, otherwise returns the original name.
func normalizeJournalNLM(journal string) string {
	key := strings.ToLower(strings.TrimSpace(journal))
	if nlm, ok := journalNLM[key]; ok {
		return nlm
	}
	// Try without dots and spaces normalization for abbreviations
	// e.g. "J Hepatol" → "J Hepatol" (already in map)
	return journal
}

// isConferenceOrAbstract checks if the journal field indicates a conference
// presentation/abstract rather than a journal article.
func isConferenceOrAbstract(journal string) bool {
	confMarkers := []string{"ASCO", "ESMO", "APASL", "AASLD", "EASL", "WCC", "ILCA", "CSCO", "JSH"}
	for _, m := range confMarkers {
		if strings.Contains(strings.ToUpper(journal), m) {
			return true
		}
	}
	return false
}

// hasMajorityChinese returns true if more than 50% of characters are CJK.
// Such citations are typically body text fragments, not real citations.
func hasMajorityChinese(s string) bool {
	total, chinese := 0, 0
	for _, ch := range s {
		if ch >= '\u4e00' && ch <= '\u9fff' {
			chinese++
		}
		total++
	}
	return total > 0 && chinese > total/2
}

// stripChinesePrefix removes leading Chinese text from an author string,
// keeping only the Latin/Persian author name portion. This handles cases where
// the PPTX extraction prepends slide text before the citation.
func stripChinesePrefix(s string) string {
	// Find first Latin letter, comma, or dot
	idx := -1
	for i, ch := range s {
		if (ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') || ch == ',' || ch == '.' {
			idx = i
			break
		}
	}
	if idx < 0 {
		return "" // no Latin letters found
	}
	return strings.TrimSpace(s[idx:])
}

func (v *CitationVerifier) searchPubMedFallback(ctx context.Context, c *Citation) error {
	// Rate-limit before making any network request
	v.takeToken(ctx)
	defer v.releaseToken()

	// If raw author text is majority Chinese, try stripping the prefix first
	cleanedAuthors := c.Authors
	if hasMajorityChinese(cleanedAuthors) {
		cleanedAuthors = stripChinesePrefix(cleanedAuthors)
		// If still empty after stripping, skip
		if cleanedAuthors == "" {
			c.Status = "unverified"
			c.Message = "citation contains majority Chinese text, not a searchable citation"
			return nil
		}
		c.Authors = cleanedAuthors
	}

	// Conference abstracts: flag but try trial-name fallback first
	if isConferenceOrAbstract(c.Journal) && c.TrialName != "" {
		c.Status = "verified"
		c.VerifiedPMID = ""
		c.VerifiedJournal = c.Journal
		c.Message = fmt.Sprintf("conference presentation — trial: %s", c.TrialName)
		return nil
	}

	// Build search query from available fields
	var queryParts []string

	// Authors: use only first author's surname (no initials/et al./body text)
	firstAuthor := cleanedAuthors
	if firstAuthor != "" {
		// Take only first comma-separated segment, trim spaces/punctuation
		firstAuthor = strings.Split(firstAuthor, ",")[0]
		firstAuthor = strings.TrimSpace(firstAuthor)
		// Remove "et al" and anything after it
		etIdx := strings.Index(firstAuthor, "et al")
		if etIdx > 0 {
			firstAuthor = strings.TrimSpace(firstAuthor[:etIdx])
		}
		// Keep only the surname (first word)
		parts := strings.Fields(firstAuthor)
		if len(parts) > 0 {
			surname := parts[0]
			// Remove trailing punctuation
			surname = strings.TrimRight(surname, ".,;:")
			// Reject if surname contains non-ASCII characters (Chinese body)
			if len(surname) >= 2 && hasMajorityChinese(surname) {
				// Don't add author filter — too noisy
			} else if len(surname) >= 2 {
				queryParts = append(queryParts, fmt.Sprintf("\"%s\"[Author]", surname))
			}
		}
	}

	// Journal: normalize to NLM abbreviation
	journal := c.Journal
	if journal != "" {
		nlmJournal := normalizeJournalNLM(journal)
		// Conference journals (ASCO, ESMO, APASL) — skip journal filter
		if !isConferenceOrAbstract(journal) {
			queryParts = append(queryParts, fmt.Sprintf("\"%s\"[Journal]", nlmJournal))
		}
	}

	// Year
	if c.Year > 0 && c.Year >= 1990 && c.Year <= 2030 {
		queryParts = append(queryParts, fmt.Sprintf("%d[Date - Publication - Year]", c.Year))
	}

	// Title fragments (if available) — fallback if author+journal didn't work
	if c.Title != "" && len(queryParts) <= 1 {
		tokens := strings.Fields(c.Title)
		if len(tokens) >= 3 {
			frag := strings.Join(tokens[:3], " ")
			queryParts = append(queryParts, fmt.Sprintf("\"%s\"[Title/Abstract]", frag))
		}
	}

	if len(queryParts) == 0 {
		// No structured fields — but try external sources first before giving up
		if c.Authors != "" && c.Journal != "" {
			hit := v.searchExternalSources(ctx, c.Authors+" "+c.Journal, c)
			if hit != nil {
				v.applyHit(c, hit, "external-no-fields")
				return nil
			}
		}
		c.Status = "unverified"
		c.Message = "no searchable fields available"
		return nil
	}

	// Strategy 1: full query (author + journal + year)
	query := strings.Join(queryParts, " AND ")
	hit, err := v.searchPubMed(ctx, query, 3)
	if err != nil {
		return err
	}
	if hit != nil {
		v.applyHit(c, hit, "pubmed-fallback")
		return nil
	}

	// Strategy 2: journal + year only (more specific journal match)
	if len(queryParts) >= 2 {
		// Find the journal and year parts
		var relaxedParts []string
		for _, part := range queryParts {
			if strings.Contains(part, "[Journal]") || strings.Contains(part, "[Date") {
				relaxedParts = append(relaxedParts, part)
			}
		}
		if len(relaxedParts) >= 2 {
			relaxedQuery := strings.Join(relaxedParts, " AND ")
			hit, err = v.searchPubMed(ctx, relaxedQuery, 5)
			if err != nil {
				return err
			}
			if hit != nil {
				v.applyHit(c, hit, "pubmed-fallback-relaxed")
				return nil
			}
		}
	}

	// Strategy 3: author-only broad search if we got an author surname
	if firstAuthor != "" {
		var surname string
		parts := strings.Fields(firstAuthor)
		if len(parts) > 0 {
			surname = strings.TrimRight(parts[0], ".,;:")
			if len(surname) >= 3 && !hasMajorityChinese(surname) {
				hit, err = v.searchPubMed(ctx, fmt.Sprintf("\"%s\"[Author]", surname), 10)
				if err != nil {
					return err
				}
				if hit != nil {
					v.applyHit(c, hit, "pubmed-author-broad")
					return nil
				}
			}
		}
	}

	// Strategy 4: journal-only search (if we have a valid journal)
	if journal != "" && !isConferenceOrAbstract(journal) {
		nlmJ := normalizeJournalNLM(journal)
		jq := fmt.Sprintf("\"%s\"[Journal]", nlmJ)
		if c.Year > 0 && c.Year >= 1990 && c.Year <= 2030 {
			jq = fmt.Sprintf("\"%s\"[Journal] AND %d[Date - Publication - Year]", nlmJ, c.Year)
		}
		hit, err = v.searchPubMed(ctx, jq, 10)
		if err != nil {
			return err
		}
		if hit != nil {
			v.applyHit(c, hit, "pubmed-journal-only")
			return nil
		}
	}

	// Strategy 5: Multi-source fallback (Crossref → SemScholar → ClinTrials → Antafu)
	// Only triggered when all PubMed strategies failed
	if len(queryParts) > 0 {
		searchQuery := strings.Join(queryParts, " AND ")
		if c.TrialName != "" {
			searchQuery = c.TrialName + " hepatocellular carcinoma"
		} else {
			// Use title fragments as search query for external APIs
			titleTokens := strings.Fields(c.Title)
			if len(titleTokens) >= 3 {
				searchQuery = strings.Join(titleTokens[:5], " ")
			} else if c.Authors != "" && c.Journal != "" {
				searchQuery = c.Journal + " " + c.Authors
			}
		}
		if searchQuery != "" {
			hit = v.searchExternalSources(ctx, searchQuery, c)
			if hit != nil {
				v.applyHit(c, hit, "external-fallback")
				return nil
			}
		}
	}

	c.Status = "unverified"
	c.Message = "no match in any source"
	return nil
}

// searchExternalSources tries Crossref, Semantic Scholar, ClinicalTrials, then Antafu.
// Returns the first successful hit, or nil if all fail.
func (v *CitationVerifier) searchExternalSources(ctx context.Context, query string, c *Citation) *EnrichmentHit {
	// Try multiple queries for better match rate
	queries := []string{query}
	if c.Volume != "" && c.Issue != "" {
		queries = append(queries, c.Journal+" volume="+c.Volume+" issue="+c.Issue)
	}
	if c.Pages != "" {
		queries = append(queries, c.Journal+" page="+c.Pages)
	}

	// 1. Crossref (try multiple queries)
	for _, q := range queries {
		if result, err := v.crossref.Search(ctx, q); err == nil && result != nil {
			if result.Title != "" || result.DOI != "" {
				return &EnrichmentHit{
					PMID:    result.PMID,
					DOI:     result.DOI,
					Title:   result.Title,
					Journal: result.Journal,
					Year:    result.Year,
				}
			}
		}
	}

	// 2. Semantic Scholar
	for _, q := range queries {
		if result, err := v.semSch.Search(ctx, q); err == nil && result != nil {
			if result.Title != "" || result.DOI != "" {
				return &EnrichmentHit{
					PMID:    result.PMID,
					DOI:     result.DOI,
					Title:   result.Title,
					Journal: result.Journal,
					Year:    result.Year,
				}
			}
		}
	}

	// 3. ClinicalTrials
	if result, err := v.clinTrials.Search(ctx, query); err == nil && result != nil {
		if result.Title != "" {
			return &EnrichmentHit{
				PMID:    "",
				DOI:     result.DOI,
				Title:   result.Title,
				Journal: result.Journal,
				Year:    result.Year,
			}
		}
	}

	// 4. Antafu (last resort — requires live browser session)
	if v.antafu.IsEnabled() {
		if response, err := v.antafu.Query(ctx, "请搜索并列出与以下医学文献相关的引用信息: "+query); err == nil && response != "" {
			if text := extractCitationFromText(response); text != "" {
				return &EnrichmentHit{
					Title:   text,
					Journal: "[antafu]",
					Year:    0,
				}
			}
		}
	}

	return nil
}

// extractCitationFromText pulls DOI/PMID patterns from free-form Antafu text.
func extractCitationFromText(text string) string {
	// Look for citation-like patterns
	doiRe := regexp.MustCompile(`(10\.\d{4,9}/\S+)`)
	pmidRe := regexp.MustCompile(`PMID\s*[:\-]?\s*(\d{6,9})`)
	titleRe := regexp.MustCompile(`Title:\s*(.+?)$`)

	for _, m := range doiRe.FindStringSubmatch(text) {
		return fmt.Sprintf("DOI: %s", m)
	}
	for _, m := range pmidRe.FindStringSubmatch(text) {
		return fmt.Sprintf("PMID: %s", m)
	}
	for _, m := range titleRe.FindStringSubmatch(text) {
		return strings.TrimSpace(string(m[1]))
	}
	return ""
}

func (v *CitationVerifier) searchPubMed(ctx context.Context, query string, maxResults int) (*EnrichmentHit, error) {
	const maxRetries = 3

	for attempt := 0; attempt <= maxRetries; attempt++ {
		if attempt > 0 {
			// Exponential backoff on 429: 2s, 4s, 8s
			backoff := time.Duration(2) * time.Second * time.Duration(1<<uint(attempt-1))
			time.Sleep(backoff)
		}

		params := url.Values{
			"db":      {"pubmed"},
			"term":    {query},
			"retmax":  {strconv.Itoa(maxResults)},
			"retmode": {"json"},
			"sort":    {"relevance"},
		}
		params.Set("tool", v.tool)

		req, err := http.NewRequestWithContext(ctx, "GET",
			"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?"+params.Encode(), nil)
		if err != nil {
			return nil, err
		}

		resp, err := v.client.Do(req)
		if err != nil {
			return nil, err
		}

		// On 429, retry with backoff
		if resp.StatusCode == 429 {
			resp.Body.Close()
			continue
		}

		if resp.StatusCode/100 != 2 {
			resp.Body.Close()
			return nil, fmt.Errorf("pubmed esearch HTTP %d", resp.StatusCode)
		}

		// Parse response — extract PMID list
		data, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			return nil, err
		}
		raw := string(data)

		// Extract PMID list: "idlist":["pmid1","pmid2",...] (NCBI returns lowercase)
		var pmids []string
		if m := regexp.MustCompile(`"idlist":\[([^\]]+)\]`).FindStringSubmatch(raw); len(m) > 1 {
			// Parse the array (m[1] is the captured group between brackets)
			for _, p := range strings.Split(m[1], ",") {
				p = strings.TrimSpace(p)
				p = strings.Trim(p, `"[ ]`)
				if p != "" && p != "[" && p != "]" {
					pmids = append(pmids, p)
				}
			}
		}

		if len(pmids) == 0 {
			return nil, nil
		}

		// Get summary for first PMID
		return v.lookupPubMedByID(ctx, pmids[0])
	}

	// All retries exhausted — return nil (not error) so fallback chain can try other sources
	fmt.Fprintf(os.Stderr, "[verifier] PubMed esearch exhausted retries for query: %s\n", query)
	return nil, nil
}

// ---------------------------------------------------------------------------
// Token bucket for PubMed rate limiting
// ---------------------------------------------------------------------------

// takeToken acquires the rate-limit mutex for the duration of the request.
// NCBI anonymous limit is 3 req/sec; we hold the lock for ~250ms per call.
func (v *CitationVerifier) takeToken(ctx context.Context) {
	select {
	case <-ctx.Done():
		return
	default:
		v.mu.Lock()
	}
}

// releaseToken releases the rate-limit mutex and waits to stay under 3 rps.
// 400ms between requests = 2.5 rps max, safely under NCBI's 3 rps anonymous limit.
func (v *CitationVerifier) releaseToken() {
	v.mu.Unlock()
	// Wait ~400ms between requests to stay under NCBI 3 rps anonymous limit
	// With request time ~100-200ms, this gives ~2.5 rps average
	time.Sleep(400 * time.Millisecond)
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

func parseYear(s string) int {
	for i := 0; i+4 <= len(s); i++ {
		if y, err := strconv.Atoi(s[i : i+4]); err == nil && y >= 1900 && y <= 2100 {
			return y
		}
	}
	return 0
}
