// Package download is the layered full-text acquisition pipeline
// grounded in /Users/david/Downloads/Telegram Desktop/literature_crawl_exp.md
// (2026-07-17 field test conclusions).
//
// It does NOT mutate the SourceAdapter contract and is NOT a fan-out
// member.  It operates on an existing Citation and fills concrete PDF /
// text bytes on disk under ~/.medit/pdfs/<doi|.txt|.pdf>.
//
// Tier 1 — Metadata APIs (read-only, no download):
//
//	OpenAlex → PMC ID + publisher links
//	Semantic Scholar → OA PDF URL
//	Crossref → DOI → publisher link
//
// Tier 2 — User Chrome CDP (localhost:9223):
//
//	PMC article HTML → article.innerText (60-70% success)
//	sci-hub Cookie extraction (DDoS-Guard cookie, 2-4 h lifetime)
//	Nature/NEJM paywalled articles via user browser session
//
// Tier 3 — curl direct download (publisher PDF links):
//
//	Springer Link (~40% success)
//	PMC PDF URLs (behind CAPTCHA, ~0-10% via curl)
//
// Tier 4 — Sci-Hub via extracted Cookie (fallback for known-in-database DOIs):
//
//	curl with Netscape-format cookies extracted from Chrome
//
// Every successful or failed attempt is logged to ~/.medit/audit/.
package download

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/veawho/via54Medit/internal/source"
	"github.com/veawho/via54Medit/pkg/types"
)

// ---------------------------------------------------------------------------
// FullTextFinder
// ---------------------------------------------------------------------------

// FullTextFinder orchestrates the tiered PDF / full-text acquisition.
//
// Typical call flow:
//
//		f := NewFullTextFinder("http://localhost:9223")
//		c := types.Citation{DOI: "10.1016/j.cell.2021.01.001"}
//		result, err := f.Get(ctx, &c)
//
//	 result.Path  → absolute path to the saved artifact (PDF or txt)
//	 result.Tier  → which tier succeeded (1-4)
//	 result.Err   → first non-nil error across all tiers (non-fatal)
type FullTextFinder struct {
	// User Chrome CDP base URL (e.g. "http://localhost:9223").
	// Empty means "skip all CDP-based tiers".
	ChromeCDP string

	// CookieFile is the path to a Netscape-format Sci-Hub cookie file.
	CookieFile string

	// Output directory for downloaded files.
	// Default: ~/.medit/pdfs/
	OutDir string

	// Audit directory for the operation log.
	// Default: ~/.medit/audit/
	AuditDir string

	// cdpClient is a long-lived CDP connection reused across tier 2 calls.
	// When non-nil, it avoids creating a new Chrome tab per citation.
	// Lifetime: set once via SetCDPClient or on first tier-2 call.
	// The caller must call Close() on the client when done.
	cdpClient *source.CDPClient

	// Rate limiting per publisher (requests/second).
	// Default: 0.5 (Springer), 1.0 (OpenAlex/S2/Crossref).
	SpringerRPS float64
	ApiRPS      float64

	// User-Agent for curl-style requests.
	UserAgent string

	// http.Client reused across tiers.
	client *http.Client

	// Token-bucket guard per publisher group.
	springerBkt rateLimiter
	apiBkt      rateLimiter

	// Embedded assets (UA list, etc.)
	uaPool []string

	// audit log writer
	auditMu sync.Mutex
	audit   []auditEntry
}

type rateLimiter struct {
	mu       sync.Mutex
	tokens   float64
	lastFill time.Time
	rps      float64
}

type cdpPMCRet struct {
	path   string
	format string
	size   int64
}

func (f *rateLimiter) take(ctx context.Context) error {
	for {
		f.mu.Lock()
		now := time.Now()
		elapsed := now.Sub(f.lastFill).Seconds()
		f.tokens += elapsed * f.rps
		if f.tokens > 1 {
			f.tokens = 1
		}
		f.lastFill = now
		if f.tokens >= 1 {
			f.tokens--
			f.mu.Unlock()
			return nil
		}
		waitSecs := (1 - f.tokens) / f.rps
		f.mu.Unlock()
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(time.Duration(waitSecs * float64(time.Second))):
		}
	}
}

// FullTextResult carries what (if anything) was retrieved.
type FullTextResult struct {
	Citation *types.Citation // original citation (may be mutated in-place)
	Path     string          // absolute path to artifact ("" = nothing)
	Tier     int             // 0 = failed; 1 = metadata-only; 2 = CDP; 3 = curl; 4 = sci-hub
	Format   string          // "pdf" | "txt"
	Size     int64           // bytes on disk
	Duration time.Duration   // wall time for this attempt
	Err      error           // first non-nil across all tiers (non-fatal)
	Used     []string        // which tiers succeeded (e.g. ["openalex", "pmc-cdp"])
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

func NewFullTextFinder(chromeCDP string) *FullTextFinder {
	f := &FullTextFinder{
		ChromeCDP:   chromeCDP,
		SpringerRPS: 0.5,
		ApiRPS:      1.0,
		UserAgent:   "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
		client: &http.Client{
			Timeout: 45 * time.Second,
			CheckRedirect: func(req *http.Request, via []*http.Request) error {
				if len(via) >= 6 {
					return fmt.Errorf("too many redirects")
				}
				return nil
			},
		},
		uaPool: defaultUA(),
	}
	// Resolve defaults for out + audit dirs
	home, _ := os.UserHomeDir()
	if home == "" {
		home = os.Getenv("HOME")
	}
	if home == "" {
		home = "/tmp/medit-user"
	}
	f.OutDir = filepath.Join(home, ".medit", "pdfs")
	f.AuditDir = filepath.Join(home, ".medit", "audit")
	f.springerBkt.rps = f.SpringerRPS
	f.apiBkt.rps = f.ApiRPS
	return f
}

// ---------------------------------------------------------------------------
// Top-level entry point
// ---------------------------------------------------------------------------

func (f *FullTextFinder) Get(ctx context.Context, c *types.Citation) (*FullTextResult, error) {
	start := time.Now()
	r := &FullTextResult{
		Citation: c,
	}

	// Ensure output dirs exist
	for _, d := range []string{f.OutDir, f.AuditDir} {
		if err := os.MkdirAll(d, 0o700); err != nil {
			return nil, fmt.Errorf("full-text: mkdir %s: %w", d, err)
		}
	}

	// --- Tier 1: metadata API ---
	mr := f.tier1Metadata(ctx, c)
	if mr.pdfURL != "" {
		c.OAPDFURL = mr.pdfURL
	}
	r.Used = append(r.Used, mr.used...)

	// --- Tier 2: CDP (PMC HTML + sci-hub cookie) ---
	if f.ChromeCDP != "" {
		cdr := f.tier2CDP(ctx, c, mr)
		if cdr.path != "" {
			r.Path = cdr.path
			r.Tier = 2
			r.Format = cdr.format
			r.Size = cdr.size
			r.Used = append(r.Used, cdr.used...)
			r.Duration = time.Since(start)
			f.auditLog("cdp", c.DOI, r.Format, cdr.path, cdr.err)
			return r, nil // found via CDP, return early
		}
		r.Used = append(r.Used, cdr.used...)
	}

	// --- Tier 3: curl direct publisher ---
	cur := f.tier3Curl(ctx, c, mr)
	if cur.path != "" {
		r.Path = cur.path
		r.Tier = 3
		r.Format = cur.format
		r.Size = cur.size
		r.Used = append(r.Used, cur.used...)
		r.Duration = time.Since(start)
		f.auditLog("curl", c.DOI, r.Format, cur.path, cur.err)
		return r, nil
	}
	r.Used = append(r.Used, cur.used...)

	// --- Tier 4: Sci-Hub via cookie ---
	sr := f.tier4SciHub(ctx, c, mr)
	if sr.path != "" {
		r.Path = sr.path
		r.Tier = 4
		r.Format = sr.format
		r.Size = sr.size
		r.Used = append(r.Used, sr.used...)
		r.Duration = time.Since(start)
		f.auditLog("sci-hub", c.DOI, r.Format, sr.path, sr.err)
		return r, nil
	}
	r.Used = append(r.Used, sr.used...)

	// --- Nothing succeeded ---
	r.Err = errors.New("full-text: all tiers failed")
	r.Duration = time.Since(start)
	f.auditLog("failed", c.DOI, "", "", r.Err)
	return r, r.Err
}

// ---------------------------------------------------------------------------
// Audit
// ---------------------------------------------------------------------------

type auditEntry struct {
	Tier      string `json:"tier"`
	DOI       string `json:"doi"`
	Format    string `json:"format"`
	Path      string `json:"path,omitempty"`
	Error     string `json:"error,omitempty"`
	Timestamp string `json:"ts"`
}

func (f *FullTextFinder) auditLog(tier, doi, format, path string, err error) {
	e := auditEntry{
		Tier: tier, DOI: doi, Format: format, Path: path,
		Timestamp: time.Now().UTC().Format(time.RFC3339),
	}
	if err != nil {
		e.Error = err.Error()
	}
	f.auditMu.Lock()
	defer f.auditMu.Unlock()
	f.audit = append(f.audit, e)
	// Also append to file
	fn := filepath.Join(f.AuditDir, "fulltext-audit.log")
	file, err := os.OpenFile(fn, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o600)
	if err != nil {
		return
	}
	defer file.Close()
	b, _ := json.Marshal(e)
	fmt.Fprintf(file, "%s\n", b)
}

// ---------------------------------------------------------------------------
// Tier 1: Metadata APIs
// ---------------------------------------------------------------------------

type tier1Meta struct {
	pdfURL string
	pmcID  string
	links  []string
	used   []string
}

func (f *FullTextFinder) tier1Metadata(ctx context.Context, c *types.Citation) *tier1Meta {
	m := &tier1Meta{}

	// OpenAlex — DOI → works, get OA PDF + PMC ID
	if c.DOI != "" {
		oa := f.openalexForDOI(ctx, c.DOI)
		if oa != nil {
			if oa.pdfURL != "" {
				m.pdfURL = oa.pdfURL
			}
			if oa.pmcID != "" {
				m.pmcID = oa.pmcID
			}
			m.links = append(m.links, oa.links...)
			m.used = append(m.used, "openalex")
		}
	}

	// Semantic Scholar — DOI → OA PDF URL
	if c.DOI != "" && m.pdfURL == "" {
		s2 := f.s2ForDOI(ctx, c.DOI)
		if s2 != nil {
			if s2.pdfURL != "" {
				m.pdfURL = s2.pdfURL
			}
			m.used = append(m.used, "semantic-scholar")
		}
	}

	// Crossref — DOI → publisher links
	if c.DOI != "" {
		cr := f.crossrefForDOI(ctx, c.DOI)
		if cr != nil {
			m.links = append(m.links, cr.links...)
			m.used = append(m.used, "crossref")
		}
	}

	// Also look at existing citation fields
	if c.OAPDFURL != "" && m.pdfURL == "" {
		m.pdfURL = c.OAPDFURL
		m.used = append(m.used, "citation-oa-pdf")
	}
	if c.PMID != "" && strings.HasPrefix(c.PMID, "PMC") {
		m.pmcID = c.PMID
	}

	return m
}

// ---------------------------------------------------------------------------
// OpenAlex
// ---------------------------------------------------------------------------

type openalexResult struct {
	pdfURL string
	pmcID  string
	links  []string
}

func (f *FullTextFinder) openalexForDOI(ctx context.Context, doi string) *openalexResult {
	if err := f.apiBkt.take(ctx); err != nil {
		return nil
	}
	// URL-escape the DOI reference (contains slashes) so the path doesn't collapse.
	encodedDOI := url.PathEscape(doi)
	u := fmt.Sprintf("https://api.openalex.org/works/https%%3A%%2F%%2Fdoi.org/%s", encodedDOI)
	req, err := http.NewRequestWithContext(ctx, "GET", u, nil)
	if err != nil {
		return nil
	}
	req.Header.Set("User-Agent", f.userAgent())
	resp, err := f.client.Do(req)
	if err != nil {
		return nil
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return nil
	}

	// Parse minimal JSON — look at locations array
	var work struct {
		Locations []struct {
			Src    string `json:"source"`
			IsOA   bool   `json:"is_oa"`
			OAURL  string `json:"oa_url"`
			PDFURL string `json:"pdf_url"`
			PMCID  string `json:"pmcid"`
		} `json:"locations"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&work); err != nil {
		return nil
	}

	r := &openalexResult{}
	for _, loc := range work.Locations {
		if loc.PDFURL != "" {
			r.pdfURL = loc.PDFURL
		}
		if loc.PMCID != "" {
			r.pmcID = loc.PMCID
		}
		if r.pdfURL != "" {
			break
		}
	}
	return r
}

// ---------------------------------------------------------------------------
// Semantic Scholar
// ---------------------------------------------------------------------------

type s2Result struct {
	pdfURL string
}

func (f *FullTextFinder) s2ForDOI(ctx context.Context, doi string) *s2Result {
	if err := f.apiBkt.take(ctx); err != nil {
		return nil
	}
	u := fmt.Sprintf("https://api.semanticscholar.org/graph/v1/paper/DOI:%s?fields=openAccessPdf", doi)
	req, err := http.NewRequestWithContext(ctx, "GET", u, nil)
	if err != nil {
		return nil
	}
	req.Header.Set("User-Agent", f.userAgent())
	resp, err := f.client.Do(req)
	if err != nil {
		return nil
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return nil
	}

	var s2 struct {
		OA *struct{ URL string } `json:"openAccessPdf"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&s2); err != nil {
		return nil
	}
	if s2.OA != nil && s2.OA.URL != "" {
		return &s2Result{pdfURL: s2.OA.URL}
	}
	return nil
}

// ---------------------------------------------------------------------------
// Crossref
// ---------------------------------------------------------------------------

type crossrefResult struct {
	links []string
}

func (f *FullTextFinder) crossrefForDOI(ctx context.Context, doi string) *crossrefResult {
	if err := f.apiBkt.take(ctx); err != nil {
		return nil
	}
	encoded := strings.ReplaceAll(doi, "/", "%2F")
	u := fmt.Sprintf("https://api.crossref.org/works/%s", encoded)
	req, err := http.NewRequestWithContext(ctx, "GET", u, nil)
	if err != nil {
		return nil
	}
	req.Header.Set("User-Agent", f.userAgent())
	resp, err := f.client.Do(req)
	if err != nil {
		return nil
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return nil
	}

	var cr struct {
		Message struct {
			Link []map[string]string `json:"link"`
		} `json:"message"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&cr); err != nil {
		return nil
	}

	r := &crossrefResult{}
	for _, l := range cr.Message.Link {
		if href, ok := l["URL"]; ok && href != "" {
			// Keep pdf links
			if strings.HasSuffix(strings.ToLower(href), ".pdf") {
				r.links = append(r.links, href)
			}
		}
	}
	if len(r.links) == 0 {
		return nil
	}
	return r
}

// ---------------------------------------------------------------------------
// Tier 2: CDP (User Chrome)
// ---------------------------------------------------------------------------

type tier2Result struct {
	path   string
	format string
	size   int64
	used   []string
	err    error
}

func (f *FullTextFinder) tier2CDP(ctx context.Context, c *types.Citation, meta *tier1Meta) *tier2Result {
	r := &tier2Result{used: []string{}}

	// --- 2a: PMC article HTML via CDP ---
	if meta.pmcID != "" && strings.HasPrefix(meta.pmcID, "PMC") {
		pr := f.cdpPMC(ctx, c.Title, meta.pmcID)
		if pr.path != "" {
			r.path = pr.path
			r.format = "txt"
			r.size = pr.size
			r.used = append(r.used, "pmc-cdp")
			return r
		}
		r.used = append(r.used, "pmc-cdp-failed")
	}

	// --- 2b: CDP Page.printToPDF for ANY URL (DOI or OA PDF URL) ---
	// This is the most reliable strategy: use Chrome to render the page and print to PDF.
	// It works even for paywalled content if the user has institutional cookies in Chrome.
	var urlsToTry []string
	if c.DOI != "" {
		urlsToTry = append(urlsToTry, fmt.Sprintf("https://doi.org/%s", c.DOI))
	}
	if meta.pdfURL != "" {
		urlsToTry = append(urlsToTry, meta.pdfURL)
	}

	for _, u := range urlsToTry {
		if f.ChromeCDP == "" {
			break
		}
		pr := f.cdpPrintToPDF(ctx, c, u)
		if pr.path != "" {
			r.path = pr.path
			r.format = "pdf"
			r.size = pr.size
			r.used = append(r.used, "cdp-print-pdf")
			return r
		}
		r.used = append(r.used, fmt.Sprintf("cdp-print-pdf-failed(%s)", u))
	}

	// --- 2c: Sci-Hub Cookie + curl (Tier 4 via CDP Cookie) ---
	// Sci-Hub Cookie extraction is a Tier 2/4 hybrid.
	// We'll extract cookies from Chrome, then use in tier4.
	cookies := f.extractSciHubCookies(ctx)
	if len(cookies) > 0 {
		r.used = append(r.used, "sci-hub-cookie-extracted")
		// Store cookies for tier 4
		// We save to ~/.medit/pdfs/sci-hub-cookies.txt
		cookiePath := filepath.Join(f.OutDir, "sci-hub-cookies.txt")
		if err := writeNetscapeCookies(cookiePath, cookies); err == nil {
			r.used = append(r.used, "sci-hub-cookie-saved")
		}
	}

	return r
}

// ---------------------------------------------------------------------------
// CDP PMC: navigate to PMC article, extract article.innerText
// ---------------------------------------------------------------------------

func (f *FullTextFinder) cdpPMC(ctx context.Context, title string, pmcid string) *cdpPMCRet {
	// Reuse or create CDP client
	var client *source.CDPClient
	var ownClient bool
	if f.cdpClient != nil {
		client = f.cdpClient
	} else {
		var err error
		client, err = source.NewCDPClient(ctx, f.ChromeCDP)
		if err != nil {
			return nil
		}
		ownClient = true
	}
	if ownClient {
		defer client.Close()
	}

	// Navigate to PMC article HTML page
	articleURL := fmt.Sprintf("https://pmc.ncbi.nlm.nih.gov/articles/%s/", pmcid)
	if err := client.Navigate(ctx, articleURL); err != nil {
		return nil
	}

	// Wait for article element to appear (replaces brittle time.Sleep)
	_ = client.WaitForSelector(ctx, "article", 10*time.Second)

	// Extract article.innerText
	js := `
(() => {
    const article = document.querySelector('article');
    if (article) {
        return article.innerText;
    }
    return null;
})()`
	text, err := client.Evaluate(ctx, js)
	if err != nil {
		return nil
	}
	if text == "null" || text == "" {
		return nil
	}

	// Save to file
	safeTitle := sanitizeFilename(title)
	fn := filepath.Join(f.OutDir, fmt.Sprintf("%s.txt", safeTitle))
	if err := os.WriteFile(fn, []byte(text), 0o644); err != nil {
		return nil
	}

	info, _ := os.Stat(fn)
	return &cdpPMCRet{path: fn, format: "txt", size: info.Size()}
}

// cdpPrintToPDF navigates to a URL via Chrome CDP, renders the page, and saves as PDF.
// If cdpCli is non-nil, it reuses that client; otherwise it creates a new one
// (new clients create a new Chrome tab each time).
func (f *FullTextFinder) cdpPrintToPDF(ctx context.Context, c *types.Citation, targetURL string) *cdpPMCRet {
	if f.ChromeCDP == "" {
		return nil
	}

	// Reuse or create CDP client
	var client *source.CDPClient
	var ownClient bool
	if f.cdpClient != nil {
		client = f.cdpClient
	} else {
		var err error
		client, err = source.NewCDPClient(ctx, f.ChromeCDP)
		if err != nil {
			return nil
		}
		ownClient = true
	}
	if ownClient {
		defer client.Close()
	}

	// Retry once on failure (transient CDP timeouts)
	var pdfBytes []byte
	for attempt := 0; attempt < 2; attempt++ {
		if attempt > 0 {
			// Brief pause before retry
			time.Sleep(1 * time.Second)
		}
		var err error
		pdfBytes, err = client.PrintToPDF(ctx, targetURL, 500)
		if err == nil {
			break
		}
	}
	if pdfBytes == nil {
		return nil
	}

	// Size cap: reject PDFs > 50MB (unreasonable for a single paper)
	if len(pdfBytes) > 50*1024*1024 {
		return nil
	}

	// Minimum size check (PDFs smaller than 2KB are likely empty/stub pages)
	if len(pdfBytes) < 2048 {
		return nil
	}

	// Save to file
	safeTitle := sanitizeFilename(c.Title)
	if safeTitle == "unknown" && c.DOI != "" {
		safeTitle = "doi_" + strings.NewReplacer("/", "_", ":", "_").Replace(c.DOI)
	}
	fn := filepath.Join(f.OutDir, safeTitle+".pdf")
	if err := os.WriteFile(fn, pdfBytes, 0o644); err != nil {
		return nil
	}

	info, _ := os.Stat(fn)
	return &cdpPMCRet{path: fn, format: "pdf", size: info.Size()}
}

// ---------------------------------------------------------------------------
// Extract sci-hub cookies from Chrome via CDP
// ---------------------------------------------------------------------------

// CookieEntry represents a Netscape-format cookie line.
type CookieEntry struct {
	Domain  string
	Path    string
	Secure  bool
	Expires int64 // 0 = session
	Name    string
	Value   string
}

func (f *FullTextFinder) extractSciHubCookies(ctx context.Context) []CookieEntry {
	client, err := source.NewCDPClient(ctx, f.ChromeCDP)
	if err != nil {
		return nil
	}
	defer client.Close()

	// Navigate to sci-hub.st to trigger/update cookies
	if err := client.Navigate(ctx, "https://sci-hub.st/"); err != nil {
		return nil
	}
	time.Sleep(5 * time.Second) // wait for DDoS-Guard handshake

	// Extract cookies via Runtime.evaluate
	js := `
(() => {
    const cookies = [];
    document.cookie.split(/;\s*/).forEach(pair => {
        const [name, ...rest] = pair.split('=');
        const value = rest.join('=');
        cookies.push({name, value});
    });
    return JSON.stringify(cookies);
})()`
	raw, err := client.Evaluate(ctx, js)
	if err != nil {
		return nil
	}

	var cookiePairs []struct{ Name, Value string }
	if err := json.Unmarshal([]byte(raw), &cookiePairs); err != nil {
		return nil
	}

	// Filter sci-hub cookies and convert to Netscape format
	var out []CookieEntry
	for _, cp := range cookiePairs {
		// Filter for relevant cookies (cf_clearance, __ddg_, etc.)
		if strings.Contains(strings.ToLower(cp.Name), "cf_") ||
			strings.Contains(strings.ToLower(cp.Name), "ddg_") ||
			strings.Contains(strings.ToLower(cp.Name), "sid") ||
			strings.Contains(strings.ToLower(cp.Name), "cookie") {
			out = append(out, CookieEntry{
				Domain: ".sci-hub.st", Path: "/", Secure: true,
				Name: cp.Name, Value: cp.Value,
			})
		}
	}

	return out
}

// ---------------------------------------------------------------------------
// Tier 3: curl direct publisher PDF
// ---------------------------------------------------------------------------

type tier3Result struct {
	path   string
	format string
	size   int64
	used   []string
	err    error
}

func (f *FullTextFinder) tier3Curl(ctx context.Context, c *types.Citation, meta *tier1Meta) *tier3Result {
	r := &tier3Result{used: []string{}}

	// Candidate PDF URLs:
	// 1. OAPDFURL from citation / meta
	// 2. Crossref publisher PDF links
	// 3. PMC PDF URL (if PMCID present)
	// 4. Springer Link constructed URL from DOI

	var candidates []string

	if meta.pdfURL != "" {
		candidates = append(candidates, meta.pdfURL)
	}
	candidates = append(candidates, meta.links...)

	if c.PMID != "" && strings.HasPrefix(c.PMID, "PMC") {
		// PMC PDF URL (often behind CAPTCHA but worth trying)
		pmcid := strings.TrimPrefix(c.PMID, "PMC")
		candidates = append(candidates,
			fmt.Sprintf("https://pmc.ncbi.nlm.nih.gov/articles/%s/pdf/%s.pdf", c.PMID, pmcid))
	}

	if c.DOI != "" {
		// Springer Link pattern: https://link.springer.com/content/pdf/10.xxxx/xxx.pdf
		if strings.Contains(c.DOI, "10.1007/") {
			candidates = append(candidates,
				fmt.Sprintf("https://link.springer.com/content/pdf/%s.pdf", c.DOI))
		}
	}

	if len(candidates) == 0 {
		return r
	}

	for _, u := range candidates {
		if err := f.springerBkt.take(ctx); err != nil {
			continue
		}
		result := f.downloadURL(ctx, c, u)
		if result.path != "" {
			r.path = result.path
			r.format = result.format
			r.size = result.size
			r.used = append(r.used, "curl-direct")
			return r
		}
		r.used = append(r.used, fmt.Sprintf("curl-failed(%s)", u))
	}

	return r
}

// downloadURL attempts to download a single PDF URL with curl-style headers.
func (f *FullTextFinder) downloadURL(ctx context.Context, c *types.Citation, urlStr string) *cdpPMCRet {
	req, err := http.NewRequestWithContext(ctx, "GET", urlStr, nil)
	if err != nil {
		return nil
	}

	// Full browser header set
	req.Header.Set("User-Agent", f.userAgent())
	req.Header.Set("Accept", "application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
	req.Header.Set("Accept-Language", "en-US,en;q=0.9")
	req.Header.Set("Referer", "https://www.google.com/")
	req.Header.Set("Accept-Encoding", "gzip, deflate, br")
	req.Header.Set("Connection", "keep-alive")

	resp, err := f.client.Do(req)
	if err != nil {
		return nil
	}
	defer resp.Body.Close()

	// Must be 2xx
	if resp.StatusCode/100 != 2 {
		return nil
	}

	// Check content type
	ct := resp.Header.Get("Content-Type")
	isPDF := strings.Contains(ct, "pdf") || strings.HasSuffix(urlStr, ".pdf")

	// Read body
	buf := new(bytes.Buffer)
	if _, err := io.Copy(buf, resp.Body); err != nil {
		return nil
	}
	body := buf.Bytes()

	// Minimum size check (PDFs are typically > 10KB)
	if len(body) < 10240 {
		return nil // too small, likely an error page
	}

	// Detect format
	format := "pdf"
	if !isPDF && len(body) > 0 && body[0] == '<' {
		// Probably HTML — might be article text
		format = "txt"
	}

	// Save file
	safeTitle := sanitizeFilename(c.Title)
	var fn string
	if format == "txt" {
		fn = filepath.Join(f.OutDir, safeTitle+".txt")
	} else {
		fn = filepath.Join(f.OutDir, safeTitle+".pdf")
	}

	if err := os.WriteFile(fn, body, 0o644); err != nil {
		return nil
	}

	info, _ := os.Stat(fn)
	return &cdpPMCRet{path: fn, format: format, size: info.Size()}
}

// ---------------------------------------------------------------------------
// Tier 4: Sci-Hub via Cookie
// ---------------------------------------------------------------------------

type tier4Result struct {
	path   string
	format string
	size   int64
	used   []string
	err    error
}

func (f *FullTextFinder) tier4SciHub(ctx context.Context, c *types.Citation, meta *tier1Meta) *tier4Result {
	r := &tier4Result{used: []string{}}

	if c.DOI == "" {
		return r
	}

	// Load cookies from previously saved file
	cookiePath := filepath.Join(f.OutDir, "sci-hub-cookies.txt")
	if _, err := os.Stat(cookiePath); err != nil {
		// No cookies saved — can't use this tier
		return r
	}

	// Sci-Hub URL
	sciHubURL := fmt.Sprintf("https://sci-hub.st/%s", c.DOI)

	// We need to send the cookie file with curl.
	// In Go, we reconstruct the Cookie header from the Netscape file.
	cookies := parseNetscapeCookies(cookiePath)
	if len(cookies) == 0 {
		return r
	}

	req, err := http.NewRequestWithContext(ctx, "GET", sciHubURL, nil)
	if err != nil {
		return r
	}

	// Build cookie header
	var cookieParts []string
	for _, ck := range cookies {
		cookieParts = append(cookieParts, fmt.Sprintf("%s=%s", ck.Name, ck.Value))
	}
	req.Header.Set("Cookie", strings.Join(cookieParts, "; "))
	req.Header.Set("User-Agent", f.userAgent())
	req.Header.Set("Accept", "application/pdf,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")

	resp, err := f.client.Do(req)
	if err != nil {
		return r
	}
	defer resp.Body.Close()

	if resp.StatusCode/100 != 2 {
		return r
	}

	buf := new(bytes.Buffer)
	if _, err := io.Copy(buf, resp.Body); err != nil {
		return r
	}
	body := buf.Bytes()

	if len(body) < 10240 {
		return r
	}

	safeTitle := sanitizeFilename(c.Title)
	fn := filepath.Join(f.OutDir, safeTitle+".pdf")
	if err := os.WriteFile(fn, body, 0o644); err != nil {
		return r
	}

	info, _ := os.Stat(fn)
	r.path = fn
	r.format = "pdf"
	r.size = info.Size()
	r.used = append(r.used, "sci-hub-cookie")

	return r
}

// ---------------------------------------------------------------------------
// Cookie file I/O
// ---------------------------------------------------------------------------

func writeNetscapeCookies(path string, cookies []CookieEntry) error {
	file, err := os.Create(path)
	if err != nil {
		return err
	}
	defer file.Close()
	for _, c := range cookies {
		expires := "0"
		if c.Expires > 0 {
			expires = fmt.Sprintf("%d", c.Expires)
		}
		secure := "FALSE"
		if c.Secure {
			secure = "TRUE"
		}
		fmt.Fprintf(file, "%s\t%s\t%s\t%s\t%s\t%s\t%s\n",
			c.Domain, "TRUE", c.Path, secure, expires, c.Name, c.Value)
	}
	return nil
}

func parseNetscapeCookies(path string) []CookieEntry {
	var out []CookieEntry
	file, err := os.Open(path)
	if err != nil {
		return nil
	}
	defer file.Close()

	raw, err := io.ReadAll(file)
	if err != nil {
		return nil
	}
	for _, line := range strings.Split(string(raw), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.Split(line, "	")
		if len(parts) < 7 {
			continue
		}
		var expires int64
		expires, _ = strconv.ParseInt(parts[4], 10, 64)
		secure := parts[3] == "TRUE"
		out = append(out, CookieEntry{
			Domain:  parts[0],
			Path:    parts[2],
			Secure:  secure,
			Expires: expires,
			Name:    parts[5],
			Value:   parts[6],
		})
	}
	return out
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

func (f *FullTextFinder) userAgent() string {
	if len(f.uaPool) == 0 {
		return f.UserAgent
	}
	// Round-robin
	idx := (time.Now().UnixMilli() % int64(len(f.uaPool))) / 1000
	return f.uaPool[int(idx)%len(f.uaPool)]
}

func sanitizeFilename(title string) string {
	if title == "" {
		return "unknown"
	}
	re := regexp.MustCompile(`[^a-zA-Z0-9._-]+`)
	s := re.ReplaceAllString(title, "_")
	// Collapse multiple underscores
	s = strings.ReplaceAll(s, "__", "_")
	s = strings.Trim(s, "_-. ")
	if len(s) > 120 {
		s = s[:117] + "..."
	}
	return s
}

func defaultUA() []string {
	return []string{
		"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
		"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
		"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
		"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
		"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
	}
}
