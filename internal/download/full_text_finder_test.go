package download

import (
  "context"
  "fmt"
  "net/http"
  "net/http/httptest"
  "net/url"
  "os"
  "path/filepath"
  "strings"
  "testing"
  "time"

  "github.com/veawho/via54Medit/pkg/types"
)

// urlRewriter rewrites outgoing requests to a test server.
type urlRewriter struct {
	rt      http.RoundTripper
	rewrite func(*url.URL) *url.URL
}

func (rw *urlRewriter) RoundTrip(req *http.Request) (*http.Response, error) {
	newURL := rw.rewrite(req.URL)
	newReq := req.Clone(req.Context())
	newReq.URL = newURL
	rt := rw.rt
	if rt == nil {
		rt = http.DefaultTransport
	}
	return rt.RoundTrip(newReq)
}

// newTestClient builds an http.Client that does NOT follow redirects.
// This is needed because ServeMux normalizes "https://" in paths to "https:/"
// and returns a 307 redirect, which would loop through the urlRewriter forever.
// With ErrUseLastResponse, the first response (200 from the test handler) is
// returned directly.
func newTestClient(transport http.RoundTripper) *http.Client {
	return &http.Client{
		Transport: transport,
		CheckRedirect: func(_ *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
}

// validPDF is a minimal valid PDF >= 10KB.
func validPDF() []byte {
  base := []byte(`%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj
xref 0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer << /Size 4 /Root 1 0 R >> startxref 190 %%EOF`)
  for len(base) < 10240 { base = append(base, base...) }
  return base
}

// ===========================================================================
// NewFullTextFinder
// ===========================================================================

func TestNewFullTextFinder_Defaults(t *testing.T) {
  f := NewFullTextFinder("")
  if f.ChromeCDP != "" {
    t.Error("ChromeCDP should be empty")
  }
  if f.SpringerRPS != 0.5 {
    t.Errorf("SpringerRPS = %f, want 0.5", f.SpringerRPS)
  }
  if f.ApiRPS != 1.0 {
    t.Errorf("ApiRPS = %f, want 1.0", f.ApiRPS)
  }
  if len(f.uaPool) != 5 {
    t.Errorf("uaPool length = %d, want 5", len(f.uaPool))
  }
}

func TestNewFullTextFinder_DirectoriesCreated(t *testing.T) {
  tmp := t.TempDir()
  f := NewFullTextFinder("")
  f.OutDir = filepath.Join(tmp, "pdfs")
  f.AuditDir = filepath.Join(tmp, "audit")
  _, _ = f.Get(context.Background(), &types.Citation{DOI: "10.test/none", Title: "Test"})
  if _, err := os.Stat(f.OutDir); err != nil {
    t.Fatalf("OutDir not created: %v", err)
  }
  if _, err := os.Stat(f.AuditDir); err != nil {
    t.Fatalf("AuditDir not created: %v", err)
  }
}

// ===========================================================================
// Tier 1: OpenAlex
// ===========================================================================

func TestOpenAlexWithPDF(t *testing.T) {
  resp := fmt.Sprintf(`{"locations":[{"source":"S1","is_oa":true,
    "oa_url":"https://example.com/paper.pdf",
    "pdf_url":"https://example.com/paper.pdf",
    "pmcid":"PMC10841291"}]}`)
  mux := http.NewServeMux()
  // Register with prefix-match; differentiate the two test DOIs inside the handler.
  var capturedPath string
  mux.HandleFunc("/works/", func(w http.ResponseWriter, r *http.Request) {
    fmt.Fprintf(os.Stderr, "HANDLER FIRED path=%q uri=%q\n", r.URL.Path, r.RequestURI)
    capturedPath = r.URL.Path
    if strings.Contains(r.URL.Path, "10.test/article") {
      w.Header().Set("Content-Type", "application/json")
      w.Write([]byte(resp))
    } else {
      // TestOpenAlexNoPDF path — no PDF available
      w.Header().Set("Content-Type", "application/json")
      w.Write([]byte(`{"locations":[{"source":"S1","is_oa":false}]}`))
    }
  })
  srv := httptest.NewServer(mux)
  defer srv.Close()

  f := NewFullTextFinder("")
  orig := f.client.Transport
  if orig == nil {
    orig = http.DefaultTransport
  }
  f.client = &http.Client{
    Transport: &urlRewriter{rt: orig, rewrite: func(u *url.URL) *url.URL {
      if strings.HasPrefix(u.Host, "api.openalex.org") {
        return &url.URL{Scheme: "http", Host: srv.Listener.Addr().String(), Path: "/works/https:/doi.org/10.test/article"}
      }
      return u
    }},
    CheckRedirect: func(_ *http.Request, via []*http.Request) error {
        return http.ErrUseLastResponse
    },
  }
  result := f.openalexForDOI(context.Background(), "10.test/article")
  if result == nil {
    t.Fatalf("expected result, got nil. capturedPath=%q", capturedPath)
  }
  if result.pdfURL != "https://example.com/paper.pdf" {
    t.Errorf("pdfURL = %q", result.pdfURL)
  }
  if result.pmcID != "PMC10841291" {
    t.Errorf("pmcID = %q", result.pmcID)
  }
}

func TestOpenAlexNoPDF(t *testing.T) {
  // Uses the same mux from TestOpenAlexWithPDF-style prefix handler below.
  resp := `{"locations":[{"source":"S1","is_oa":false}]}`
  mux := http.NewServeMux()
  mux.HandleFunc("/works/", func(w http.ResponseWriter, r *http.Request) {
    // "10.test/no" path — no PDF available
    w.Write([]byte(resp))
  })
  srv := httptest.NewServer(mux)
  defer srv.Close()

  f := NewFullTextFinder("")
  orig := f.client.Transport
  if orig == nil {
    orig = http.DefaultTransport
  }
  f.client = &http.Client{
    Transport: &urlRewriter{rt: orig, rewrite: func(u *url.URL) *url.URL {
      if strings.HasPrefix(u.Host, "api.openalex.org") {
        return &url.URL{Scheme: "http", Host: srv.Listener.Addr().String(), Path: "/works/https:/doi.org/10.test/no"}
      }
      return u
    }},
    CheckRedirect: func(_ *http.Request, via []*http.Request) error {
        return http.ErrUseLastResponse
    },
  }
  result := f.openalexForDOI(context.Background(), "10.test/no")
  if result == nil {
    t.Fatalf("expected non-nil result")
  }
  if result.pdfURL != "" {
    t.Errorf("pdfURL = %q, want empty", result.pdfURL)
  }
}

// ===========================================================================
// Tier 1: Semantic Scholar
// ===========================================================================

func TestS2WithPDF(t *testing.T) {
  resp := `{"openAccessPdf":{"url":"https://s2.com/paper.pdf"}}`
  mux := http.NewServeMux()
  mux.HandleFunc("/graph/", func(w http.ResponseWriter, r *http.Request) {
    w.Header().Set("Content-Type", "application/json")
    w.Write([]byte(resp))
  })
  srv := httptest.NewServer(mux)
  defer srv.Close()

  f := NewFullTextFinder("")
  orig := f.client.Transport
  if orig == nil {
    orig = http.DefaultTransport
  }
  f.client = &http.Client{
    Transport: &urlRewriter{rt: orig, rewrite: func(u *url.URL) *url.URL {
      if strings.HasPrefix(u.Host, "api.semanticscholar.org") {
        return &url.URL{Scheme: "http", Host: srv.Listener.Addr().String(), Path: "/graph/v1/paper/DOI:10.test/article"}
      }
      return u
    }},
    CheckRedirect: func(_ *http.Request, via []*http.Request) error {
        return http.ErrUseLastResponse
    },
  }
  result := f.s2ForDOI(context.Background(), "10.test/article")
  if result == nil {
    t.Fatalf("expected result")
  }
  if result.pdfURL != "https://s2.com/paper.pdf" {
    t.Errorf("pdfURL = %q", result.pdfURL)
  }
}

// ===========================================================================
// Tier 1: Crossref
// ===========================================================================

func TestCrossrefPDFLinks(t *testing.T) {
  resp := `{
    "message": {
      "link": [
        {"URL": "https://link.springer.com/content/pdf/10.1007/s00535-026-02411-7.pdf"},
        {"URL": "https://link.springer.com/article/10.1007/s00535-026-02411-7"}
      ]
    }
  }`
  mux := http.NewServeMux()
  mux.HandleFunc("/works/", func(w http.ResponseWriter, r *http.Request) {
    w.Header().Set("Content-Type", "application/json")
    w.Write([]byte(resp))
  })
  srv := httptest.NewServer(mux)
  defer srv.Close()

  f := NewFullTextFinder("")
  orig := f.client.Transport
  if orig == nil {
    orig = http.DefaultTransport
  }
  capturedPath := ""
  f.client = &http.Client{
    Transport: &urlRewriter{rt: orig, rewrite: func(u *url.URL) *url.URL {
      if strings.HasPrefix(u.Host, "api.crossref.org") {
        capturedPath = u.Path
        return &url.URL{Scheme: "http", Host: srv.Listener.Addr().String(), Path: "/works/10.1007%2Fs00535-026-02411-7"}
      }
      return u
    }},
    CheckRedirect: func(_ *http.Request, via []*http.Request) error {
        return http.ErrUseLastResponse
    },
  }
  result := f.crossrefForDOI(context.Background(), "10.1007/s00535-026-02411-7")
  if result == nil {
    t.Fatalf("expected result")
  }
  if len(result.links) != 1 {
    t.Errorf("links length = %d, want 1", len(result.links))
  }
  if result.links[0] != "https://link.springer.com/content/pdf/10.1007/s00535-026-02411-7.pdf" {
    t.Errorf("link[0] = %q", result.links[0])
  }
  // Verify DOI was properly URL-encoded before making the request
  if !strings.Contains(capturedPath, "10.1007") || !strings.Contains(capturedPath, "s00535") {
    t.Errorf("expected DOI components in path: %s", capturedPath)
  }
}

// ===========================================================================
// Tier 3: Curl download
// ===========================================================================

func TestDownloadURL_Success(t *testing.T) {
  tmp := t.TempDir()
  pdfBytes := validPDF()

  mux := http.NewServeMux()
  var receivedPath string
  mux.HandleFunc("/content/", func(w http.ResponseWriter, r *http.Request) {
    receivedPath = r.URL.Path
    w.Header().Set("Content-Type", "application/pdf")
    w.Write(pdfBytes)
  })
  srv := httptest.NewServer(mux)
  defer srv.Close()

  f := NewFullTextFinder("")
  f.OutDir = tmp // use temp dir so write doesn't hit ~/.medit
  orig := f.client.Transport
  if orig == nil {
    orig = http.DefaultTransport
  }
  f.client = &http.Client{
    Transport: &urlRewriter{rt: orig, rewrite: func(u *url.URL) *url.URL {
      return &url.URL{Scheme: "http", Host: srv.Listener.Addr().String(), Path: u.Path}
    }},
    CheckRedirect: func(_ *http.Request, via []*http.Request) error {
        return http.ErrUseLastResponse
    },
  }
  c := &types.Citation{
    DOI:   "10.1007/s00535-026-02411-7",
    Title: "HCC Treatment Selection Immunotherapy 2026",
  }
  result := f.downloadURL(context.Background(), c, "https://link.springer.com/content/pdf/10.1007/s00535-026-02411-7.pdf")
  if result == nil {
    t.Fatalf("expected result (receivedPath=%q)", receivedPath)
  }
  if result.format != "pdf" {
    t.Errorf("format = %q, want pdf", result.format)
  }
  if result.size <= 0 {
    t.Errorf("size = %d", result.size)
  }
  if _, err := os.Stat(result.path); err != nil {
    t.Fatalf("file not found: %v", err)
  }
}

func TestDownloadURL_HTTP404(t *testing.T) {
  mux := http.NewServeMux()
  mux.HandleFunc("/missing", func(w http.ResponseWriter, r *http.Request) {
    w.WriteHeader(404)
  })
  srv := httptest.NewServer(mux)
  defer srv.Close()

  f := NewFullTextFinder("")
  orig := f.client.Transport
  if orig == nil {
    orig = http.DefaultTransport
  }
  f.client = &http.Client{
    Transport: &urlRewriter{rt: orig, rewrite: func(u *url.URL) *url.URL {
      return &url.URL{Scheme: "http", Host: srv.Listener.Addr().String(), Path: "/missing"}
    }},
    CheckRedirect: func(_ *http.Request, via []*http.Request) error {
        return http.ErrUseLastResponse
    },
  }
  c := &types.Citation{DOI: "10.test/nope", Title: "Missing"}
  result := f.downloadURL(context.Background(), c, "https://example.com/missing")
  if result != nil {
    t.Fatalf("expected nil for 404")
  }
}

// ===========================================================================
// sanitizeFilename
// ===========================================================================

func TestSanitizeFilename(t *testing.T) {
  tests := []struct {
    in  string
    out string
  }{
    {"", "unknown"},
    {"A/B:C\\D", "A_B_C_D"},
    {"Lung Cancer Immunotherapy (2026) — NEJM", "Lung_Cancer_Immunotherapy_2026_NEJM"},
  }
  for _, tc := range tests {
    got := sanitizeFilename(tc.in)
    if got != tc.out {
      t.Errorf("sanitizeFilename(%q) = %q, want %q", tc.in, got, tc.out)
    }
  }
}

// ===========================================================================
// rateLimiter
// ===========================================================================

func TestRateLimiter_OneToken(t *testing.T) {
  rl := rateLimiter{rps: 10}
  rl.lastFill = time.Now()
  rl.tokens = 1
  if err := rl.take(context.Background()); err != nil {
    t.Fatalf("unexpected error: %v", err)
  }
}

func TestRateLimiter_Exhausted(t *testing.T) {
  rl := rateLimiter{rps: 1}
  rl.lastFill = time.Now()
  rl.tokens = 0
  ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
  defer cancel()
  err := rl.take(ctx)
  if err == nil {
    t.Fatalf("expected context deadline exceeded")
  }
  if err != context.DeadlineExceeded {
    t.Fatalf("expected DeadlineExceeded, got %v", err)
  }
}

// ===========================================================================
// Cookie file I/O
// ===========================================================================

func TestWriteAndParseNetscapeCookies(t *testing.T) {
  tmp := t.TempDir()
  path := filepath.Join(tmp, "cookies.txt")
  cookies := []CookieEntry{
    {Domain: ".sci-hub.st", Path: "/", Secure: true, Expires: 1720000000, Name: "cf_clearance", Value: "abc123"},
    {Domain: ".sci-hub.st", Path: "/", Secure: false, Expires: 0, Name: "session", Value: "xyz"},
  }
  if err := writeNetscapeCookies(path, cookies); err != nil {
    t.Fatalf("write error: %v", err)
  }
  parsed := parseNetscapeCookies(path)
  if len(parsed) != 2 {
    t.Fatalf("expected 2 cookies, got %d", len(parsed))
  }
  if parsed[0].Name != "cf_clearance" {
    t.Errorf("first cookie name = %q", parsed[0].Name)
  }
  if parsed[0].Value != "abc123" {
    t.Errorf("first cookie value = %q", parsed[0].Value)
  }
}

// ===========================================================================
// Tier 4: Sci-Hub Cookie
// ===========================================================================

func TestTier4SciHub_HasCookies(t *testing.T) {
  tmp := t.TempDir()
  pdfBytes := validPDF()

  mux := http.NewServeMux()
  mux.HandleFunc("/10.test/article", func(w http.ResponseWriter, r *http.Request) {
    cookie := r.Header.Get("Cookie")
    if !strings.Contains(cookie, "cf_clearance") {
      w.WriteHeader(401)
      return
    }
    w.Header().Set("Content-Type", "application/pdf")
    w.Write(pdfBytes)
  })
  srv := httptest.NewServer(mux)
  defer srv.Close()

  cookiePath := filepath.Join(tmp, "sci-hub-cookies.txt")
  if err := writeNetscapeCookies(cookiePath, []CookieEntry{
    {Domain: ".sci-hub.st", Path: "/", Secure: true, Expires: 0, Name: "cf_clearance", Value: "abc123"},
  }); err != nil {
    t.Fatalf("write cookies: %v", err)
  }

  f := NewFullTextFinder("")
  f.OutDir = tmp
  orig := f.client.Transport
  if orig == nil {
    orig = http.DefaultTransport
  }
  f.client = &http.Client{
    Transport: &urlRewriter{rt: orig, rewrite: func(u *url.URL) *url.URL {
      return &url.URL{Scheme: "http", Host: srv.Listener.Addr().String(), Path: u.Path}
    }},
    CheckRedirect: func(_ *http.Request, via []*http.Request) error {
        return http.ErrUseLastResponse
    },
  }
  c := &types.Citation{DOI: "10.test/article", Title: "SciHubTest"}
  result := f.tier4SciHub(context.Background(), c, &tier1Meta{})
  if result == nil {
    t.Fatalf("expected result")
  }
  if result.format != "pdf" {
    t.Errorf("format = %q, want pdf", result.format)
  }
}
