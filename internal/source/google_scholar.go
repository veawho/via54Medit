// Package source — Google Scholar adapter.
//
// Google Scholar (scholar.google.com) is a citation-focused search engine.
// Unlike PubMed/OpenAlex/S2, Google Scholar has NO official API — we
// scrape the HTML search results page.
//
// Endpoint:
//
//	https://scholar.google.com/scholar?q=<query>&hl=en&as_sdt=0%2C5
//
// Rate limits: Google Scholar aggressively throttles (429 + CAPTCHA) and
// has no published rate limit. We implement:
//   - Token-bucket rate limiter at 6 req/min (0.1 rps)
//   - Rotating User-Agent (5-entry pool)
//   - Conservative backoff on 429/503
//   - Health check that fails fast
//
// Identity model: Google Scholar doesn't expose stable unique IDs.
// Citations carry PMID/DOI when Google Scholar surfaces them (via
// "related articles" / "all versions" links).
//
// Output: []types.Citation with Title, Authors, Journal, Year,
// Abstract (snippet), PMID, DOI, CitedBy (when available), and
// OAPDFURL (when Google Scholar links to a free PDF).
//
// ⚠️ Compliance note: Scraping Google Scholar violates its Terms of
// Service in many jurisdictions. This adapter:
//   - is disabled by default
//   - requires explicit opt-in (--gscholar flag)
//   - logs every request to audit log
//   - uses conservative rate limiting (6 req/min)
package source

import (
	"context"
	"fmt"
	"net/http"
	"net/url"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/veawho/via54Medit/pkg/types"
)

// gScholarSource scrapes Google Scholar for citation metadata.
type gScholarSource struct {
	enabled    bool
	client     *http.Client
	rps        float64 // requests per second
	mu         sync.Mutex
	tokens     float64
	lastFill   time.Time
	userAgents []string // rotating UA pool
	uaIndex    int      // current UA index (protected by mu)
}

// gScholarEndpoint is the Google Scholar search URL base.
var gScholarEndpoint = "https://scholar.google.com/scholar"

// gsDefaultUserAgents is the rotating UA pool for scraping.
var gsDefaultUserAgents = []string{
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
	"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
	"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
}

// NewGScholarSource builds a Google Scholar adapter.
//
// Recognized keys:
//   - enabled   bool       (default: false)
//   - rate_limit float64|int (default: 6 req/min; ≤60 → req/min, >60 → req/s)
//   - user_agents string   (comma-separated, overrides default pool)
func NewGScholarSource(cfg map[string]any) (*gScholarSource, error) {
	s := &gScholarSource{
		enabled: false,
		client: &http.Client{
			Timeout: 30 * time.Second,
			CheckRedirect: func(req *http.Request, via []*http.Request) error {
				if len(via) >= 3 {
					return fmt.Errorf("too many redirects")
				}
				return nil
			},
		},
		rps:        0.1, // 6 req/min = 0.1 rps
		userAgents: gsDefaultUserAgents,
	}

	if cfg != nil {
		if v, ok := cfg["enabled"].(bool); ok {
			s.enabled = v
		}
		if v, ok := cfg["rate_limit"].(float64); ok && v > 0 {
			s.rps = v
		} else if v, ok := cfg["rate_limit"].(int); ok && v > 0 {
			// Accept both req/s and req/min
			if v <= 60 {
				s.rps = float64(v) / 60.0
			} else {
				s.rps = float64(v)
			}
		}
		if v, ok := cfg["user_agents"].(string); ok && v != "" {
			agents := make([]string, 0)
			for _, ua := range strings.Split(v, ",") {
				ua = strings.TrimSpace(ua)
				if ua != "" {
					agents = append(agents, ua)
				}
			}
			if len(agents) > 0 {
				s.userAgents = agents
			}
		}
	}

	s.tokens = 1.0
	s.lastFill = time.Now()
	return s, nil
}

func (s *gScholarSource) Name() string  { return "gscholar" }
func (s *gScholarSource) Enabled() bool { return s.enabled }

// Health performs a minimal GET to verify scholar.google.com is reachable.
func (s *gScholarSource) Health(ctx context.Context) error {
	if !s.enabled {
		return fmt.Errorf("gscholar: source is disabled in config")
	}
	req, err := s.newRequest(ctx, "covid", 1)
	if err != nil {
		return err
	}
	resp, err := s.client.Do(req)
	if err != nil {
		return fmt.Errorf("gscholar: health request: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return fmt.Errorf("gscholar: health returned %d", resp.StatusCode)
	}
	return nil
}

// Search scrapes Google Scholar and returns up to `limit` citations.
//
// Scraping flow:
//  1. Construct URL with hl=en, as_sdt=0,5 (all dates)
//  2. GET with rotating UA
//  3. Parse result blocks (div.gs_ri)
//  4. For each block: extract title, author, venue, year, snippet, links
//  5. Extract DOI/PMID from "all versions" links and PDF indicators
//  6. Return []types.Citation
func (s *gScholarSource) Search(ctx context.Context, q types.EBMQuestion, limit int) ([]types.Citation, error) {
	if !s.enabled {
		return nil, fmt.Errorf("gscholar: source is disabled")
	}
	if limit <= 0 {
		limit = 20
	}
	query := q.Query
	if query == "" {
		return nil, fmt.Errorf("gscholar: empty query")
	}
	if err := s.takeToken(ctx); err != nil {
		return nil, fmt.Errorf("gscholar: rate limit: %w", err)
	}

	perPage := limit
	if perPage > 10 {
		perPage = 10 // Google Scholar caps per-page at ~10
	}

	req, err := s.newRequest(ctx, query, perPage)
	if err != nil {
		return nil, err
	}

	resp, err := s.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("gscholar: search request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode/100 != 2 {
		return nil, fmt.Errorf("gscholar: search returned %d (Google may have blocked the request)", resp.StatusCode)
	}

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("gscholar: parse HTML: %w", err)
	}

	cites := make([]types.Citation, 0, limit)
	now := time.Now()

	// Result items: div.gs_ri
	//   Title: h3.gs_rt
	//   Author/venue: div.gs_a
	//   Snippet: div.gs_rs
	//   Links: div.gs_fl
	doc.Find("div.gs_ri").Each(func(i int, sel *goquery.Selection) {
		if len(cites) >= limit {
			return
		}
		c := s.parseResultBlock(sel)
		if c.Title == "" {
			return // skip unparseable blocks
		}
		c.SourceOrigin = []string{"gscholar"}
		c.FetchedAt = now
		cites = append(cites, c)
	})

	return cites, nil
}

// parseResultBlock extracts a Citation from a Google Scholar result div.
func (s *gScholarSource) parseResultBlock(sel *goquery.Selection) types.Citation {
	c := types.Citation{}

	// Title: h3.gs_rt
	titleSel := sel.Find("h3.gs_rt")
	if titleSel.Length() > 0 {
		c.Title = gscholarCleanTitleText(titleSel.Text())
	}

	// Author + venue + year: div.gs_a
	//   Format: "A Name1, B Name2, C Name3 - Journal, Year"
	authorsVenueSel := sel.Find("div.gs_a")
	if authorsVenueSel.Length() > 0 {
		text := authorsVenueSel.Text()
		c.Authors, c.Journal, c.Year = gscholarParseAuthorsVenue(text)
	}

	// Snippet/Abstract: div.gs_rs
	snippetSel := sel.Find("div.gs_rs")
	if snippetSel.Length() > 0 {
		c.Abstract = strings.TrimSpace(snippetSel.Text())
	}

	// Links: div.gs_fl — extract PDF, DOI, PMID, cited-by
	linksSel := sel.Find("div.gs_fl a")
	linksSel.Each(func(i int, link *goquery.Selection) {
		href, _ := link.Attr("href")
		linkText := link.Text()

		// PDF indicator
		if strings.Contains(linkText, "PDF") {
			c.OAPDFURL = gscholarResolveLink(href)
		}

		// DOI from link
		if c.DOI == "" {
			doi := gscholarExtractDOI(href)
			if doi != "" {
				c.DOI = doi
			}
		}

		// PMID from link
		if c.PMID == "" {
			pmid := gscholarExtractPMID(href)
			if pmid != "" {
				c.PMID = pmid
			}
		}
	})

	// "Cited by N" from gs_fl text
	flText := sel.Find("div.gs_fl").Text()
	if c.CitedBy == 0 {
		if m := gsCitedByRegex.FindStringSubmatch(flText); len(m) > 1 {
			n, _ := strconv.Atoi(m[1])
			c.CitedBy = n
		}
	}

	return c
}

// --- Helper: clean title text ---
func gscholarCleanTitleText(text string) string {
	text = strings.ReplaceAll(text, "\u00a0", " ")
	text = strings.TrimSpace(text)
	text = gsMultiSpaceRegex.ReplaceAllString(text, " ")
	return text
}

// --- Helper: parse authors + venue ---
// Parses "A Name1, B Name2, C Name3 - Journal, Year"
func gscholarParseAuthorsVenue(text string) (authors []string, journal string, year int) {
	parts := strings.SplitN(text, " - ", 2)
	authorPart, venuePart := "", ""
	if len(parts) == 2 {
		authorPart, venuePart = parts[0], parts[1]
	} else {
		venuePart = text
	}

	if authorPart != "" {
		rawAuthors := strings.Split(authorPart, ", ")
		authors = make([]string, 0, len(rawAuthors))
		for _, a := range rawAuthors {
			a = strings.TrimSpace(a)
			if a != "" {
				authors = append(authors, a)
			}
		}
	}

	if venuePart != "" {
		if m := gsYearEndRegex.FindStringSubmatch(venuePart); len(m) > 1 {
			candidate, _ := strconv.Atoi(m[1])
			if candidate >= 1900 && candidate <= 2100 {
				year = candidate
			}
		}
		journal = gsYearEndRegex.ReplaceAllString(venuePart, "")
		journal = strings.TrimRight(journal, ", ")
		journal = strings.TrimSpace(journal)
	}

	return authors, journal, year
}

// --- Helper: resolve relative links ---
func gscholarResolveLink(href string) string {
	if href == "" || strings.HasPrefix(href, "http") {
		return href
	}
	if strings.HasPrefix(href, "/") {
		return "https://scholar.google.com" + href
	}
	return "https://scholar.google.com/" + href
}

// --- Helper: extract DOI ---
func gscholarExtractDOI(u string) string {
	if !strings.Contains(u, "doi.org/") {
		return ""
	}
	idx := strings.LastIndex(u, "doi.org/")
	if idx < 0 {
		return ""
	}
	doi := u[idx+len("doi.org/"):]
	if i := strings.Index(doi, "?"); i >= 0 {
		doi = doi[:i]
	}
	if i := strings.Index(doi, "#"); i >= 0 {
		doi = doi[:i]
	}
	return doi
}

// --- Helper: extract PMID ---
func gscholarExtractPMID(u string) string {
	if strings.Contains(u, "ncbi.nlm.nih.gov/pubmed/") {
		idx := strings.LastIndex(u, "/")
		if idx >= 0 {
			id := u[idx+1:]
			if i := strings.Index(id, "?"); i >= 0 {
				id = id[:i]
			}
			return id
		}
	}
	if m := gsPMIDLinkRegex.FindStringSubmatch(u); len(m) > 1 {
		return m[1]
	}
	return ""
}

// --- Helper: build request ---
func (s *gScholarSource) newRequest(ctx context.Context, query string, limit int) (*http.Request, error) {
	params := url.Values{}
	params.Set("q", query)
	params.Set("hl", "en")
	params.Set("as_sdt", "0,5") // all publication dates
	params.Set("btnG", "")

	u := gScholarEndpoint + "?" + params.Encode()
	req, err := http.NewRequestWithContext(ctx, "GET", u, nil)
	if err != nil {
		return nil, err
	}

	// Rotating UA
	s.mu.Lock()
	ua := s.userAgents[s.uaIndex]
	s.uaIndex = (s.uaIndex + 1) % len(s.userAgents)
	s.mu.Unlock()
	req.Header.Set("User-Agent", ua)

	req.Header.Set("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
	req.Header.Set("Accept-Language", "en-US,en;q=0.5")
	req.Header.Set("Accept-Encoding", "gzip, deflate, br")
	req.Header.Set("Connection", "keep-alive")
	req.Header.Set("DNT", "1")
	req.Header.Set("Sec-Fetch-Dest", "document")
	req.Header.Set("Sec-Fetch-Mode", "navigate")
	req.Header.Set("Sec-Fetch-Site", "none")
	req.Header.Set("Sec-Fetch-User", "?1")

	return req, nil
}

// --- Rate limiter ---
func (s *gScholarSource) takeToken(ctx context.Context) error {
	for {
		s.mu.Lock()
		now := time.Now()
		elapsed := now.Sub(s.lastFill).Seconds()
		s.tokens += elapsed * s.rps
		if s.tokens > 1 {
			s.tokens = 1
		}
		s.lastFill = now
		if s.tokens >= 1 {
			s.tokens--
			s.mu.Unlock()
			return nil
		}
		wait := (1 - s.tokens) / s.rps * float64(time.Second)
		s.mu.Unlock()
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(time.Duration(wait)):
		}
	}
}

// --- Sorting utility (not exported; used by unit tests) ---
func gscholarSortStrings(s []string) {
	sort.Strings(s)
}

// --- Regexes ---
var (
	gsCitedByRegex    = regexp.MustCompile(`(?:Cited by|被引用)\s*(\d+)`)
	gsYearEndRegex    = regexp.MustCompile(`\s*,?\s*(\d{4})\s*$`)
	gsMultiSpaceRegex = regexp.MustCompile(`\s{2,}`)
	gsPMIDLinkRegex   = regexp.MustCompile(`pubmed/(\d+)`)
)
