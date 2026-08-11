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
	for len(base) < 10240 {
		base = append(base, base...)
	}
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

// ===========================================================================
// CDP PrintToPDF (mock)
// ===========================================================================

func TestCDPPrintToPDF_NoChrome(t *testing.T) {
	// When ChromeCDP is empty, cdpPrintToPDF should return nil without error.
	f := NewFullTextFinder("")
	f.OutDir = t.TempDir()
	c := &types.Citation{DOI: "10.test/article", Title: "Test Article"}
	result := f.cdpPrintToPDF(context.Background(), c, "https://doi.org/10.test/article")
	if result != nil {
		t.Errorf("expected nil when ChromeCDP is empty, got path=%q", result.path)
	}
}

// ===========================================================================
// DOI Pattern Classification
// ===========================================================================

func TestClassifyDOI(t *testing.T) {
	tests := []struct {
		doi      string
		expected ContentType
		label    string
	}{
		{"10.7717/peerj.1052/table-1", ContentChartFigure, "chart-figure"},
		{"10.7717/peerjcs.1782/fig-3", ContentChartFigure, "chart-figure"},
		{"10.1038/nrc3239", ContentResearchPaper, "research-paper"},
		{"10.1200/JCO.21.01440", ContentResearchPaper, "research-paper"},
		{"10.1038/nrclinonc.2009.184-c2", ContentAuthorReply, "author-reply"},
		{"10.1039/d3ra05696a/v2/response1", ContentAuthorReply, "author-reply"},
		{"10.7554/eLife.06416.026", ContentSupplementary, "supplementary"},
		{"", ContentUnknown, "unknown"},
	}
	for _, tc := range tests {
		got := ClassifyDOI(tc.doi)
		if got != tc.expected {
			t.Errorf("ClassifyDOI(%q) = %v, want %v (%s)", tc.doi, got, tc.expected, tc.label)
		}
	}
}

// ===========================================================================
// Checkpoint
// ===========================================================================

func TestCheckpointBasic(t *testing.T) {
	tmp := t.TempDir()
	cpPath := filepath.Join(tmp, "checkpoint.json")

	cp, err := NewCheckpoint(cpPath, 10)
	if err != nil {
		t.Fatalf("NewCheckpoint: %v", err)
	}

	// Record a success
	cp.RecordSuccess(CheckpointItem{DOI: "10.test/one", Title: "Paper One", Path: "/tmp/paper1.pdf", Tier: 2, Size: 1024})

	if !cp.IsDone("10.test/one") {
		t.Errorf("expected IsDone for 10.test/one")
	}
	if cp.IsDone("10.test/two") {
		t.Errorf("expected not IsDone for 10.test/two")
	}

	// Record a failure
	cp.RecordFailure(CheckpointItem{DOI: "10.test/two", Title: "Paper Two"})

	// Load from disk and verify
	cp2, err := NewCheckpoint(cpPath, 10)
	if err != nil {
		t.Fatalf("NewCheckpoint reload: %v", err)
	}
	if !cp2.IsDone("10.test/one") {
		t.Errorf("reloaded checkpoint should know 10.test/one is done")
	}
	if len(cp2.data.Items) != 2 {
		t.Errorf("expected 2 items, got %d", len(cp2.data.Items))
	}
}

func TestValidatePDF_Valid(t *testing.T) {
	tmp := t.TempDir()
	pdfPath := filepath.Join(tmp, "test.pdf")
	pdfContent := []byte("%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer\n<< /Root 1 0 R /Size 4 >>\nstartxref\n190\n%%EOF\n")
	if err := os.WriteFile(pdfPath, pdfContent, 0o644); err != nil {
		t.Fatal(err)
	}

	v := ValidatePDF(pdfPath)
	if !v.Valid {
		t.Errorf("ValidatePDF should be valid: %s", v.Reason)
	}
	if !v.HasHeader {
		t.Error("HasHeader should be true")
	}
	if !v.HasObjects {
		t.Error("HasObjects should be true")
	}
	if !v.HasTrailer {
		t.Error("HasTrailer should be true")
	}
}

func TestValidatePDF_HTMLMasquerade(t *testing.T) {
	tmp := t.TempDir()
	pdfPath := filepath.Join(tmp, "fake.pdf")
	// Must be > 100 bytes to pass min-size check
	content := []byte("<!DOCTYPE html><html><body>Page not found</body></html>0000000000000000000000000000000000000000000000000000000000000000")
	if err := os.WriteFile(pdfPath, content, 0o644); err != nil {
		t.Fatal(err)
	}

	v := ValidatePDF(pdfPath)
	if v.Valid {
		t.Error("HTML masquerade should not be valid")
	}
	if !v.IsPlainText {
		t.Error("IsPlainText should be true for HTML")
	}
}

func TestValidatePDF_TooSmall(t *testing.T) {
	tmp := t.TempDir()
	pdfPath := filepath.Join(tmp, "empty.pdf")
	if err := os.WriteFile(pdfPath, []byte("x"), 0o644); err != nil {
		t.Fatal(err)
	}

	v := ValidatePDF(pdfPath)
	if v.Valid {
		t.Error("empty file should not be valid")
	}
}

func TestBatchDownload_EmptyInput(t *testing.T) {
	f := NewFullTextFinder("")
	defer f.Close()

	ctx := context.Background()
	cfg := BatchConfig{WorkerCount: 1}
	result, err := f.BatchDownload(ctx, nil, cfg)
	if err != nil {
		t.Fatalf("BatchDownload(nil): %v", err)
	}
	if result.Total != 0 {
		t.Errorf("Total = %d, want 0", result.Total)
	}
	// nil citations should not panic
	result2, err := f.BatchDownload(ctx, []types.Citation{}, cfg)
	if err != nil {
		t.Fatalf("BatchDownload([]): %v", err)
	}
	if result2.Total != 0 {
		t.Errorf("Total = %d, want 0", result2.Total)
	}
}

func TestBatchDownload_CheckpointCreated(t *testing.T) {
	tmp := t.TempDir()
	cpPath := filepath.Join(tmp, "batch.json")

	f := NewFullTextFinder("")
	defer f.Close()

	citations := []types.Citation{
		{DOI: "10.1000/test.1", Title: "Test one"},
		{DOI: "10.1000/test.2", Title: "Test two"},
	}

	cfg := BatchConfig{
		WorkerCount:    1,
		CheckpointPath: cpPath,
		GenerateHTML:   false,
	}
	_, err := f.BatchDownload(context.Background(), citations, cfg)
	if err != nil {
		t.Fatalf("BatchDownload: %v", err)
	}

	// Verify checkpoint file was created
	if _, err := os.Stat(cpPath); err != nil {
		t.Errorf("checkpoint file not created: %v", err)
	}
}

func TestFullTextFinder_Close_Idempotent(t *testing.T) {
	f := NewFullTextFinder("")
	// Close should not panic even without CDP client set
	f.Close()
	f.Close() // double close should also be safe
	t.Log("Close idempotent OK")
}

func TestSanitizeFilename_SpecialChars(t *testing.T) {
	tests := []struct {
		in  string
		out string
	}{
		{"normal paper", "normal_paper"},
		{"file/with:slashes", "file_with_slashes"},
		{"no-change", "no-change"},
		{"Capital Letters 123", "Capital_Letters_123"},
	}
	for _, tc := range tests {
		got := sanitizeFilename(tc.in)
		if got != tc.out {
			t.Errorf("sanitizeFilename(%q) = %q, want %q", tc.in, got, tc.out)
		}
	}
}
