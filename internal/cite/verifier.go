// verifier.go
// CitationVerifier resolves extracted citations to PubMed/Crossref records.
//
// Resolution order:
//   1. If PMID present → PubMed esummary (instant lookup)
//   2. If DOI present → Crossref API
//   3. If trial name detected → trialNameMap lookup (instant)
//   4. Fallback: PubMed search with extracted fields (author, journal, year)
package cite

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/veawho/via54Medit/internal/source"
)

// CitationVerifier enriches extracted citations against PubMed/Crossref.
type CitationVerifier struct {
	pubmed *source.PubMedSource
	client *http.Client

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
		pubmed: pubmed,
		client: &http.Client{Timeout: 15 * time.Second},
		tool:   "via54Medit",
		email:  "cite@via54.com",
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
	if err := v.searchPubMedFallback(ctx, c); err != nil {
		c.Status = "error"
		c.Message = err.Error()
		return err
	}

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
			Title []string `json:"title"`
			DOI   string   `json:"DOI"`
			ContainerTitle []string `json:"container-title"`
			Created struct {
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
		PMID:  "",
		DOI:   got.Message.DOI,
		Title: "",
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
// PubMed fallback search (author + journal + year)
// ---------------------------------------------------------------------------

func (v *CitationVerifier) searchPubMedFallback(ctx context.Context, c *Citation) error {
	// Rate-limit before making any network request
	v.takeToken(ctx)
	defer v.releaseToken()

	// Build search query from available fields
	var queryParts []string

	// Authors (use first author surname + initial)
	if c.Authors != "" {
		first := strings.Split(c.Authors, ",")[0]
		first = strings.TrimSpace(first)
		queryParts = append(queryParts, fmt.Sprintf("\"%s\"[Author]", first))
	}

	// Journal
	if c.Journal != "" {
		queryParts = append(queryParts, fmt.Sprintf("\"%s\"[Journal]", c.Journal))
	}

	// Year
	if c.Year > 0 {
		queryParts = append(queryParts, fmt.Sprintf("%d[Date - Publication - Year]", c.Year))
	}

	// Title fragments (if available)
	if c.Title != "" {
		tokens := strings.Fields(c.Title)
		if len(tokens) >= 3 {
			// Use first 3 significant words as title fragment
			frag := strings.Join(tokens[:3], " ")
			queryParts = append(queryParts, fmt.Sprintf("\"%s\"[Title/Abstract]", frag))
		}
	}

	if len(queryParts) == 0 {
		c.Status = "unverified"
		c.Message = "no search fields available"
		return fmt.Errorf("no search fields")
	}

	query := strings.Join(queryParts, " AND ")

	// Search PubMed
	hit, err := v.searchPubMed(ctx, query, 3)
	if err != nil {
		return err
	}

	if hit != nil {
		v.applyHit(c, hit, "pubmed-fallback")
		return nil
	}

	c.Status = "unverified"
	c.Message = fmt.Sprintf("PubMed search found no match for: %s", query)
	return nil
}

func (v *CitationVerifier) searchPubMed(ctx context.Context, query string, maxResults int) (*EnrichmentHit, error) {
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
	defer resp.Body.Close()

	if resp.StatusCode/100 != 2 {
		return nil, fmt.Errorf("pubmed esearch HTTP %d", resp.StatusCode)
	}

	// Parse response — extract PMID list
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	raw := string(data)

	// Extract PMID list: "idlist":["pmid1","pmid2",...] (NCBI returns lowercase)
	var pmids []string
	if m := regexp.MustCompile(`"idlist":\[([^\]]+)\]`).FindStringSubmatch(raw); len(m) > 1 {
		// Parse the array
		parts := strings.Split(m[1], ",")
		for _, p := range parts {
			p = strings.TrimSpace(p)
			p = strings.Trim(p, `"`)
			if p != "" {
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
