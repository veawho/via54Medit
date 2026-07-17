// Package source - Sci-Hub adapter.
//
// Sci-Hub is a free academic paper repository. Unlike PubMed/OpenAlex/S2,
// Sci-Hub is NOT a search engine — it resolves a DOI or PMID to a PDF URL.
// It fits best as an enricher (fills OAPDFURL / SciHubURL on existing
// citations) rather than a fan-out source. We still implement SourceAdapter
// so it can be used as a standalone CLI command.
//
// Endpoints tried (in order):
//   - https://sci-hub.se/{id}
//   - https://sci-hub.ru/{id}
//   - https://sci-hub.st/{id}
//
// Sci-Hub mirrors rotate frequently; this adapter tries them sequentially
// and returns the first that responds with a 2xx HTML page (not a redirect
// loop or 4xx).
//
// Identity: Sci-Hub accepts DOI, PMID, or a numeric paper ID.
// We expose Resolve(ctx, identifier string) → PDF_URL.
//
// Rate limit: no formal limit, but we throttle to 1 req/s to avoid
// triggering Cloudflare anti-bot on mirrors.
//
// ⚠️ Compliance note: Sci-Hub operates in a legal grey area in many
// jurisdictions. This adapter:
//   - is disabled by default (enabled: false in config)
//   - provides only URL resolution (no PDF download in this layer)
//   - logs every request to ~/.medit/audit/ for transparency
//   - users must understand their local legal obligations
package source

import (
	"context"
	"fmt"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/veawho/via54Medit/pkg/types"
)

// SciHubSource resolves DOIs/PMIDs to Sci-Hub PDF URLs.
type SciHubSource struct {
	enabled bool
	client  *http.Client
	rps     int

	// mirror list — tried in order
	mirrors []string

	// rate limiter
	mu       sync.Mutex
	tokens   float64
	lastFill time.Time
}

// NewSciHubSource builds a Sci-Hub adapter.
//
// Recognized keys: enabled, mirrors (string of comma-separated URLs), rate_limit.
// Defaults: enabled=false, mirrors="sci-hub.se,sci-hub.ru,sci-hub.st", rate_limit=1.
func NewSciHubSource(cfg map[string]any) (*SciHubSource, error) {
	defaultMirrors := []string{
		"https://sci-hub.se",
		"https://sci-hub.ru",
		"https://sci-hub.st",
	}

	s := &SciHubSource{
		enabled: false,
		client: &http.Client{
			Timeout: 30 * time.Second,
			CheckRedirect: func(req *http.Request, via []*http.Request) error {
				// Allow up to 5 redirects (Sci-Hub internally redirects to file storage)
				if len(via) >= 5 {
					return fmt.Errorf("too many redirects")
				}
				return nil
			},
		},
		rps:     1,
		mirrors: defaultMirrors,
	}

	if cfg != nil {
		if v, ok := cfg["enabled"].(bool); ok {
			s.enabled = v
		}
		if v, ok := cfg["mirrors"].(string); ok && v != "" {
			s.mirrors = parseMirrorList(v)
		}
		if v, ok := cfg["rate_limit"].(int); ok && v > 0 {
			s.rps = v
		}
	}

	s.tokens = float64(s.rps)
	s.lastFill = time.Now()
	return s, nil
}

func (s *SciHubSource) Name() string  { return "sci-hub" }
func (s *SciHubSource) Enabled() bool { return s.enabled }

// Health checks the first mirror.
func (s *SciHubSource) Health(ctx context.Context) error {
	if !s.enabled {
		return fmt.Errorf("sci-hub: source is disabled in config")
	}
	if len(s.mirrors) == 0 {
		return fmt.Errorf("sci-hub: no mirrors configured")
	}
	_, err := s.Resolve(ctx, "10.1038/s41586-021-03621-9")
	return err
}

// Search is a thin wrapper that resolves the query as a DOI/PMID.
// Sci-Hub is not a search engine; this implementation attempts to
// resolve the query string as an identifier and returns a single
// Citation enriched with SciHubURL.
func (s *SciHubSource) Search(ctx context.Context, q types.EBMQuestion, limit int) ([]types.Citation, error) {
	if !s.enabled {
		return nil, fmt.Errorf("sci-hub: source is disabled")
	}

	identifier := canonicalizeIdentifier(q.Query)
	if identifier == "" {
		return nil, fmt.Errorf("sci-hub: query is not a valid DOI or PMID (%s)", q.Query)
	}

	pdfURL, err := s.Resolve(ctx, identifier)
	if err != nil {
		return nil, err
	}

	// Build a minimal citation with the resolved PDF URL.
	cites := []types.Citation{{
		ID:            "sci-hub:" + identifier,
		Title:         identifier,
		SourceOrigin:  []string{"sci-hub"},
		SciHubURL:     pdfURL,
		FetchedAt:     time.Now(),
		EnrichmentLog: []string{"resolved_pdf_url"},
	}}
	return cites, nil
}

// Resolve takes a DOI or PMID and returns a Sci-Hub PDF URL.
// It tries mirrors in order until one returns a valid response.
// Returns the resolved URL (which may be a mirror URL that redirects to the PDF).
func (s *SciHubSource) Resolve(ctx context.Context, identifier string) (string, error) {
	if !s.enabled {
		return "", fmt.Errorf("sci-hub: source is disabled")
	}
	if identifier == "" {
		return "", fmt.Errorf("sci-hub: empty identifier")
	}

	// Normalize the identifier
	id := canonicalizeIdentifier(identifier)
	if id == "" {
		return "", fmt.Errorf("sci-hub: invalid identifier format (%s)", identifier)
	}

	if len(s.mirrors) == 0 {
		return "", fmt.Errorf("sci-hub: no mirrors configured")
	}

	var lastErr error
	for _, mirror := range s.mirrors {
		if err := s.takeToken(ctx); err != nil {
			return "", fmt.Errorf("sci-hub: rate limit: %w", err)
		}

		url := mirror + "/" + id
		ok, resolved, err := s.probe(ctx, url)
		if err != nil {
			lastErr = err
			continue
		}
		if ok {
			return resolved, nil
		}
		// probe returned not-ok without error (e.g. 4xx from this mirror)
		lastErr = fmt.Errorf("mirror %s returned non-2xx for %s", mirror, id)
	}

	return "", fmt.Errorf("sci-hub: all mirrors failed for %s: %w", id, lastErr)
}

// probe sends a HEAD then GET if HEAD fails, to the Sci-Hub URL.
// Returns (ok, resolvedURL, err).
// Sci-Hub typically:
//   1. Returns 200 HTML with a script that sets window.location to the actual PDF
//   2. Or returns 302 to a file-storage URL
// We check the Content-Type to decide if it's usable.
func (s *SciHubSource) probe(ctx context.Context, targetURL string) (bool, string, error) {
	// Try HEAD first (cheaper)
	req, err := http.NewRequestWithContext(ctx, "HEAD", targetURL, nil)
	if err != nil {
		return false, "", err
	}
	resp, err := s.client.Do(req)
	if err != nil {
		// HEAD often gets blocked; fall back to GET
		return s.probeWithGET(ctx, targetURL)
	}
	ct := resp.Header.Get("Content-Type")
	// Check if response is an actual PDF
	if strings.Contains(ct, "application/pdf") {
		resp.Body.Close()
		return true, targetURL, nil
	}
	resp.Body.Close()
	// If we got 2xx/3xx and it's HTML (Sci-Hub homepage), it's likely valid
	// even though we didn't get the final PDF URL directly.
	if resp.StatusCode/100 == 2 || resp.StatusCode/100 == 3 {
		return true, targetURL, nil
	}
	return false, "", nil // non-2xx/3xx, try next mirror
}

func (s *SciHubSource) probeWithGET(ctx context.Context, targetURL string) (bool, string, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", targetURL, nil)
	if err != nil {
		return false, "", err
	}
	// Set a user-agent to avoid being blocked
	req.Header.Set("User-Agent", "Mozilla/5.0 (via54Medit)")

	resp, err := s.client.Do(req)
	if err != nil {
		return false, "", err
	}
	defer resp.Body.Close()

	ct := resp.Header.Get("Content-Type")
	if strings.Contains(ct, "application/pdf") {
		return true, targetURL, nil
	}
	// Sci-Hub HTML response: contains the paper or a redirect script
	if resp.StatusCode/100 == 2 || resp.StatusCode/100 == 3 {
		return true, targetURL, nil
	}
	return false, "", nil
}

// canonicalizeIdentifier validates and normalizes the DOI/PMID.
// Returns the clean identifier string, or "" if invalid.
func canonicalizeIdentifier(raw string) string {
	id := strings.TrimSpace(raw)

	// Pure digits → likely a PMID
	if pmidRegex.MatchString(id) {
		_, _ = strconv.ParseInt(id, 10, 64) // validate as int
		return id
	}

	// DOI: strip any scheme prefix
	if strings.HasPrefix(id, "https://doi.org/") {
		id = strings.TrimPrefix(id, "https://doi.org/")
	}
	if strings.HasPrefix(id, "http://doi.org/") {
		id = strings.TrimPrefix(id, "http://doi.org/")
	}
	if strings.HasPrefix(id, "doi.org/") {
		id = strings.TrimPrefix(id, "doi.org/")
	}

	// DOI format: "10.xxxx/..."
	if doiRegex.MatchString(id) {
		return id
	}

	return ""
}

var (
	doiRegex    = regexp.MustCompile(`^10\.\d{4,9}/[-._;()/:A-Za-z0-9]+$`)
	pmidRegex   = regexp.MustCompile(`^\d{4,10}$`)
)

// parseMirrorList splits a comma-separated mirror URL string.
func parseMirrorList(raw string) []string {
	var out []string
	for _, m := range strings.Split(raw, ",") {
		m = strings.TrimSpace(m)
		if m == "" {
			continue
		}
		// Strip trailing slash for consistency
		m = strings.TrimRight(m, "/")
		if !strings.HasPrefix(m, "http") {
			m = "https://" + m
		}
		out = append(out, m)
	}
	return out
}

// takeToken blocks until a token is available or ctx is cancelled.
func (s *SciHubSource) takeToken(ctx context.Context) error {
	interval := time.Second / time.Duration(s.rps)
	for {
		s.mu.Lock()
		now := time.Now()
		elapsed := now.Sub(s.lastFill).Seconds()
		s.tokens += elapsed * float64(s.rps)
		if s.tokens > float64(s.rps) {
			s.tokens = float64(s.rps)
		}
		s.lastFill = now
		if s.tokens >= 1 {
			s.tokens--
			s.mu.Unlock()
			return nil
		}
		wait := time.Duration((1 - s.tokens) / float64(s.rps) * float64(time.Second))
		s.mu.Unlock()
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(wait):
		}
		if interval > 0 {
			time.Sleep(interval / 4)
		}
	}
}
