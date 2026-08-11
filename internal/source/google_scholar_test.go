package source

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/veawho/via54Medit/pkg/types"
)

func TestGScholar_NewGScholarSource(t *testing.T) {
	t.Run("disabled by default", func(t *testing.T) {
		s, err := NewGScholarSource(nil)
		if err != nil {
			t.Fatalf("NewGScholarSource(nil) = %v", err)
		}
		if s.Enabled() {
			t.Fatal("expected disabled by default")
		}
		if s.Name() != "gscholar" {
			t.Fatalf("Name() = %q, want %q", s.Name(), "gscholar")
		}
	})

	t.Run("enabled via config", func(t *testing.T) {
		cfg := map[string]any{"enabled": true, "rate_limit": 6}
		s, err := NewGScholarSource(cfg)
		if err != nil {
			t.Fatalf("NewGScholarSource(cfg) = %v", err)
		}
		if !s.Enabled() {
			t.Fatal("expected enabled=true")
		}
		// 6 req/min → 0.1 rps
		if s.rps != 0.1 {
			t.Fatalf("rps = %.4f, want 0.1", s.rps)
		}
	})

	t.Run("custom rate_limit as float64", func(t *testing.T) {
		cfg := map[string]any{"enabled": true, "rate_limit": 2.0}
		s, err := NewGScholarSource(cfg)
		if err != nil {
			t.Fatalf("NewGScholarSource(cfg) = %v", err)
		}
		if s.rps != 2.0 {
			t.Fatalf("rps = %.2f, want 2.0", s.rps)
		}
	})

	t.Run("rate_limit > 60 treated as req/s", func(t *testing.T) {
		cfg := map[string]any{"enabled": true, "rate_limit": 120}
		s, err := NewGScholarSource(cfg)
		if err != nil {
			t.Fatalf("NewGScholarSource(cfg) = %v", err)
		}
		if s.rps != 120 {
			t.Fatalf("rps = %.2f, want 120", s.rps)
		}
	})

	t.Run("custom user_agents", func(t *testing.T) {
		cfg := map[string]any{
			"enabled":     true,
			"user_agents": "Mozilla/5.0 test, Custom/1.0",
		}
		s, err := NewGScholarSource(cfg)
		if err != nil {
			t.Fatalf("NewGScholarSource(cfg) = %v", err)
		}
		if len(s.userAgents) != 2 {
			t.Fatalf("userAgents len = %d, want 2", len(s.userAgents))
		}
		if s.userAgents[0] != "Mozilla/5.0 test" {
			t.Fatalf("userAgents[0] = %q, want %q", s.userAgents[0], "Mozilla/5.0 test")
		}
	})
}

func TestGScholar_SearchDisabled(t *testing.T) {
	s, err := NewGScholarSource(nil)
	if err != nil {
		t.Fatalf("NewGScholarSource(nil) = %v", err)
	}

	ctx := context.Background()
	_, err = s.Search(ctx, types.EBMQuestion{Query: "test"}, 10)
	if err == nil {
		t.Fatal("expected error for disabled source")
	}
	if got := err.Error(); got != "gscholar: source is disabled" {
		t.Fatalf("error = %q, want %q", got, "gscholar: source is disabled")
	}
}

func TestGScholar_SearchEmptyQuery(t *testing.T) {
	cfg := map[string]any{"enabled": true}
	s, err := NewGScholarSource(cfg)
	if err != nil {
		t.Fatalf("NewGScholarSource(cfg) = %v", err)
	}

	ctx := context.Background()
	_, err = s.Search(ctx, types.EBMQuestion{Query: ""}, 10)
	if err == nil {
		t.Fatal("expected error for empty query")
	}
	if got := err.Error(); got != "gscholar: empty query" {
		t.Fatalf("error = %q, want %q", got, "gscholar: empty query")
	}
}

func TestGScholar_SearchBlockedReturnsError(t *testing.T) {
	// Start a test server that returns 429
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	defer srv.Close()

	// Override endpoint temporarily
	old := gScholarEndpoint
	gScholarEndpoint = srv.URL + "/scholar"
	defer func() { gScholarEndpoint = old }()

	cfg := map[string]any{"enabled": true, "rate_limit": 100.0}
	s, err := NewGScholarSource(cfg)
	if err != nil {
		t.Fatalf("NewGScholarSource(cfg) = %v", err)
	}

	ctx := context.Background()
	_, err = s.Search(ctx, types.EBMQuestion{Query: "test"}, 10)
	if err == nil {
		t.Fatal("expected error for blocked request")
	}
	if got := err.Error(); got != "gscholar: search returned 429 (Google may have blocked the request)" {
		t.Fatalf("error = %q, want %q", got, "gscholar: search returned 429 (Google may have blocked the request)")
	}
}

func TestGScholar_ParseResultBlock(t *testing.T) {
	// We construct a simple HTML block and parse it with goquery
	html := `
	<div class="gs_ri">
		<h3 class="gs_rt">A test paper on machine learning</h3>
		<div class="gs_a">A Smith, B Jones, C Doe - Nature, 2023</div>
		<div class="gs_rs">This paper investigates machine learning in healthcare.</div>
		<div class="gs_fl">
			<a href="https://doi.org/10.1038/s41586-023-12345">All versions</a>
			<a href="#">Cited by 42</a>
		</div>
	</div>
	`

	s, err := NewGScholarSource(map[string]any{"enabled": true})
	if err != nil {
		t.Fatalf("NewGScholarSource(cfg) = %v", err)
	}

	doc, err := goquery.NewDocumentFromReader(strings.NewReader(html))
	if err != nil {
		t.Fatalf("NewDocumentFromReader = %v", err)
	}

	sel := doc.Find("div.gs_ri")
	if sel.Length() != 1 {
		t.Fatalf("expected 1 result div, got %d", sel.Length())
	}

	c := s.parseResultBlock(sel)

	if c.Title != "A test paper on machine learning" {
		t.Fatalf("Title = %q, want %q", c.Title, "A test paper on machine learning")
	}

	if c.Abstract != "This paper investigates machine learning in healthcare." {
		t.Fatalf("Abstract = %q, want %q", c.Abstract, "This paper investigates machine learning in healthcare.")
	}

	if len(c.Authors) != 3 {
		t.Fatalf("Authors len = %d, want 3", len(c.Authors))
	}

	if c.Journal != "Nature" {
		t.Fatalf("Journal = %q, want %q", c.Journal, "Nature")
	}

	if c.Year != 2023 {
		t.Fatalf("Year = %d, want 2023", c.Year)
	}

	if c.DOI != "10.1038/s41586-023-12345" {
		t.Fatalf("DOI = %q, want %q", c.DOI, "10.1038/s41586-023-12345")
	}

	if c.CitedBy != 42 {
		t.Fatalf("CitedBy = %d, want 42", c.CitedBy)
	}
}

func TestGScholar_ParseResultBlockPDFLink(t *testing.T) {
	html := `
	<div class="gs_ri">
		<h3 class="gs_rt">Another paper</h3>
		<div class="gs_a">A Author - Journal, 2020</div>
		<div class="gs_rs">Abstract text here.</div>
		<div class="gs_fl">
			<a href="https://arxiv.org/pdf/2001.12345.pdf">PDF</a>
		</div>
	</div>
	`

	s, err := NewGScholarSource(map[string]any{"enabled": true})
	if err != nil {
		t.Fatalf("NewGScholarSource(cfg) = %v", err)
	}

	doc, err := goquery.NewDocumentFromReader(strings.NewReader(html))
	if err != nil {
		t.Fatalf("NewDocumentFromReader = %v", err)
	}

	sel := doc.Find("div.gs_ri")
	c := s.parseResultBlock(sel)

	if c.OAPDFURL != "https://arxiv.org/pdf/2001.12345.pdf" {
		t.Fatalf("OAPDFURL = %q, want %q", c.OAPDFURL, "https://arxiv.org/pdf/2001.12345.pdf")
	}
}

func TestGScholar_ParseResultBlockNoYear(t *testing.T) {
	html := `
	<div class="gs_ri">
		<h3 class="gs_rt">No year paper</h3>
		<div class="gs_a">A Author - Some Conference</div>
		<div class="gs_rs">Snippet.</div>
		<div class="gs_fl"><a href="#">Cited by 5</a></div>
	</div>
	`

	s, err := NewGScholarSource(map[string]any{"enabled": true})
	if err != nil {
		t.Fatalf("NewGScholarSource(cfg) = %v", err)
	}

	doc, err := goquery.NewDocumentFromReader(strings.NewReader(html))
	if err != nil {
		t.Fatalf("NewDocumentFromReader = %v", err)
	}

	c := s.parseResultBlock(doc.Find("div.gs_ri"))

	if c.Year != 0 {
		t.Fatalf("Year = %d, want 0", c.Year)
	}
	if c.Journal != "Some Conference" {
		t.Fatalf("Journal = %q, want %q", c.Journal, "Some Conference")
	}
}

func TestGScholar_ParseResultBlockEmptyTitle(t *testing.T) {
	// An unparseable block with no title should return an empty citation
	html := `<div class="gs_ri"><h3></h3></div>`

	s, err := NewGScholarSource(map[string]any{"enabled": true})
	if err != nil {
		t.Fatalf("NewGScholarSource(cfg) = %v", err)
	}

	doc, err := goquery.NewDocumentFromReader(strings.NewReader(html))
	if err != nil {
		t.Fatalf("NewDocumentFromReader = %v", err)
	}

	c := s.parseResultBlock(doc.Find("div.gs_ri"))
	if c.Title != "" {
		t.Fatalf("Title = %q, want empty", c.Title)
	}
}

func TestGScholar_ExtractDOI(t *testing.T) {
	tests := []struct {
		name string
		url  string
		want string
	}{
		{"standard doi.org", "https://doi.org/10.1038/s41586-021-03621-9", "10.1038/s41586-021-03621-9"},
		{"with query", "https://doi.org/10.1126/science.123?ref=link", "10.1126/science.123"},
		{"with fragment", "https://doi.org/10.1016/j.cell.2021.01.001#section", "10.1016/j.cell.2021.01.001"},
		{"no doi", "https://example.com/not-a-doi", ""},
		{"empty", "", ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := gscholarExtractDOI(tt.url)
			if got != tt.want {
				t.Fatalf("gscholarExtractDOI(%q) = %q, want %q", tt.url, got, tt.want)
			}
		})
	}
}

func TestGScholar_ExtractPMID(t *testing.T) {
	tests := []struct {
		name string
		url  string
		want string
	}{
		{"ncbi nlm", "https://www.ncbi.nlm.nih.gov/pubmed/31535829", "31535829"},
		{"with query", "https://www.ncbi.nlm.nih.gov/pubmed/12345?term=test", "12345"},
		{"no pubmed", "https://example.com/page", ""},
		{"empty", "", ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := gscholarExtractPMID(tt.url)
			if got != tt.want {
				t.Fatalf("gscholarExtractPMID(%q) = %q, want %q", tt.url, got, tt.want)
			}
		})
	}
}

func TestGScholar_ResolveLink(t *testing.T) {
	tests := []struct {
		name string
		href string
		want string
	}{
		{"absolute", "https://example.com/paper.pdf", "https://example.com/paper.pdf"},
		{"absolute http", "http://example.com/file.pdf", "http://example.com/file.pdf"},
		{"root relative", "/scholar.pdf", "https://scholar.google.com/scholar.pdf"},
		{"relative", "papers/test.pdf", "https://scholar.google.com/papers/test.pdf"},
		{"empty", "", ""},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := gscholarResolveLink(tt.href)
			if got != tt.want {
				t.Fatalf("gscholarResolveLink(%q) = %q, want %q", tt.href, got, tt.want)
			}
		})
	}
}

func TestGScholar_CleanTitleText(t *testing.T) {
	tests := []struct {
		name string
		in   string
		want string
	}{
		{"normal", "A test title", "A test title"},
		{"nbsp", "A\u00a0test\u00a0title", "A test title"},
		{"trailing spaces", "  A test title  ", "A test title"},
		{"multiple spaces", "A   test    title", "A test title"},
		{"mixed", "  A\u00a0test  title  ", "A test title"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := gscholarCleanTitleText(tt.in)
			if got != tt.want {
				t.Fatalf("gscholarCleanTitleText(%q) = %q, want %q", tt.in, got, tt.want)
			}
		})
	}
}

func TestGScholar_ParseAuthorsVenue(t *testing.T) {
	tests := []struct {
		name     string
		in       string
		wantAuth int // len(authors)
		wantJrnl string
		wantYear int
	}{
		{
			name:     "standard three authors",
			in:       "A Smith, B Jones, C Doe - Nature, 2023",
			wantAuth: 3, wantJrnl: "Nature", wantYear: 2023,
		},
		{
			name:     "single author",
			in:       "A Smith - Cell, 2020",
			wantAuth: 1, wantJrnl: "Cell", wantYear: 2020,
		},
		{
			name:     "no authors",
			in:       "Some Conference, 2019",
			wantAuth: 0, wantJrnl: "Some Conference", wantYear: 2019,
		},
		{
			name:     "no year",
			in:       "A Author - Journal",
			wantAuth: 1, wantJrnl: "Journal", wantYear: 0,
		},
		{
			name:     "future year clamped",
			in:       "A Author - Journal, 2101",
			wantAuth: 1, wantJrnl: "Journal", wantYear: 0,
		},
		{
			name:     "old year",
			in:       "A Author - Journal, 1900",
			wantAuth: 1, wantJrnl: "Journal", wantYear: 1900,
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			authors, journal, year := gscholarParseAuthorsVenue(tt.in)
			if len(authors) != tt.wantAuth {
				t.Fatalf("authors len = %d, want %d", len(authors), tt.wantAuth)
			}
			if journal != tt.wantJrnl {
				t.Fatalf("journal = %q, want %q", journal, tt.wantJrnl)
			}
			if year != tt.wantYear {
				t.Fatalf("year = %d, want %d", year, tt.wantYear)
			}
		})
	}
}

func TestGScholar_TakeTokenRespectsCtxCancel(t *testing.T) {
	// We need to drain the initial token so the source blocks.
	cfg := map[string]any{"enabled": true, "rate_limit": 0.0001} // very slow refill
	s, err := NewGScholarSource(cfg)
	if err != nil {
		t.Fatalf("NewGScholarSource(cfg) = %v", err)
	}

	ctx := context.Background()
	// Drain the single starting token
	_ = s.takeToken(ctx) // takes the initial token (should succeed immediately)

	// Now tokens = 0 and refill is too slow. Next call should block until ctx cancelled.
	ctx2, cancel := context.WithCancel(context.Background())
	cancel() // cancel immediately

	err = s.takeToken(ctx2)
	if err != context.Canceled {
		t.Fatalf("takeToken(cancelled after drain) = %v, want %v", err, context.Canceled)
	}
}

func TestGScholar_TakeTokenAllowsThroughWhenTokensAvailable(t *testing.T) {
	cfg := map[string]any{"enabled": true, "rate_limit": 1000.0} // 1000 rps — effectively no throttle
	s, err := NewGScholarSource(cfg)
	if err != nil {
		t.Fatalf("NewGScholarSource(cfg) = %v", err)
	}

	ctx := context.Background()

	// First two calls should succeed immediately (initial token + refill)
	for i := 0; i < 2; i++ {
		start := time.Now()
		err := s.takeToken(ctx)
		dur := time.Since(start)
		if err != nil {
			t.Fatalf("takeToken call %d = %v, want nil", i, err)
		}
		if dur > 50*time.Millisecond {
			t.Fatalf("takeToken call %d took %v, want < 50ms", i, dur)
		}
	}
}

func TestGScholar_NewRequestSetsRotatingUA(t *testing.T) {
	cfg := map[string]any{
		"enabled":     true,
		"user_agents": "Agent1, Agent2, Agent3",
	}
	s, err := NewGScholarSource(cfg)
	if err != nil {
		t.Fatalf("NewGScholarSource(cfg) = %v", err)
	}

	ctx := context.Background()

	// Make 3 requests and verify UAs cycle
	expectedUAs := []string{"Agent1", "Agent2", "Agent3"}
	for i, wantUA := range expectedUAs {
		req, err := s.newRequest(ctx, "test", 10)
		if err != nil {
			t.Fatalf("newRequest call %d = %v", i, err)
		}
		gotUA := req.Header.Get("User-Agent")
		if gotUA != wantUA {
			t.Fatalf("newRequest call %d UA = %q, want %q", i, gotUA, wantUA)
		}
	}

	// 4th request should wrap to Agent1
	req, err := s.newRequest(ctx, "test", 10)
	if err != nil {
		t.Fatalf("newRequest wrap = %v", err)
	}
	gotUA := req.Header.Get("User-Agent")
	if gotUA != "Agent1" {
		t.Fatalf("newRequest wrap UA = %q, want Agent1", gotUA)
	}
}

func TestGScholar_SearchWithMockHTML(t *testing.T) {
	// Set up a test server that returns mock Google Scholar HTML
	htmlTemplate := `
	<html>
	<head><title>Google Scholar</title></head>
	<body>
		<div class="gs_ri">
			<h3 class="gs_rt">Test Paper Title</h3>
			<div class="gs_a">A Author, B Author - Test Journal, 2024</div>
			<div class="gs_rs">This is a test abstract for the mock.</div>
			<div class="gs_fl">
				<a href="https://doi.org/10.1234/test.2024.001">All versions</a>
				<a href="#">Cited by 7</a>
			</div>
		</div>
	</body>
	</html>
	`

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(htmlTemplate))
	}))
	defer srv.Close()

	old := gScholarEndpoint
	gScholarEndpoint = srv.URL + "/scholar"
	defer func() { gScholarEndpoint = old }()

	cfg := map[string]any{"enabled": true, "rate_limit": 100.0}
	s, err := NewGScholarSource(cfg)
	if err != nil {
		t.Fatalf("NewGScholarSource(cfg) = %v", err)
	}

	ctx := context.Background()
	cites, err := s.Search(ctx, types.EBMQuestion{Query: "test"}, 10)
	if err != nil {
		t.Fatalf("Search(mock) = %v", err)
	}
	if len(cites) != 1 {
		t.Fatalf("Search(mock) len = %d, want 1", len(cites))
	}

	c := cites[0]
	if c.Title != "Test Paper Title" {
		t.Fatalf("Title = %q, want %q", c.Title, "Test Paper Title")
	}
	if c.Journal != "Test Journal" {
		t.Fatalf("Journal = %q, want %q", c.Journal, "Test Journal")
	}
	if c.Year != 2024 {
		t.Fatalf("Year = %d, want 2024", c.Year)
	}
	if c.DOI != "10.1234/test.2024.001" {
		t.Fatalf("DOI = %q, want %q", c.DOI, "10.1234/test.2024.001")
	}
	if c.CitedBy != 7 {
		t.Fatalf("CitedBy = %d, want 7", c.CitedBy)
	}
	if len(c.SourceOrigin) != 1 || c.SourceOrigin[0] != "gscholar" {
		t.Fatalf("SourceOrigin = %v, want [gscholar]", c.SourceOrigin)
	}
}

func TestGScholar_SearchMultipleResults(t *testing.T) {
	htmlTemplate := `
	<html><body>
		<div class="gs_ri">
			<h3 class="gs_rt">First paper</h3>
			<div class="gs_a">A Author - Journal1, 2023</div>
			<div class="gs_rs">Abstract 1.</div>
			<div class="gs_fl"><a href="#">Cited by 10</a></div>
		</div>
		<div class="gs_ri">
			<h3 class="gs_rt">Second paper</h3>
			<div class="gs_a">B Author - Journal2, 2024</div>
			<div class="gs_rs">Abstract 2.</div>
			<div class="gs_fl"><a href="#">Cited by 20</a></div>
		</div>
		<div class="gs_ri">
			<h3 class="gs_rt">Third paper</h3>
			<div class="gs_a">C Author - Journal3, 2025</div>
			<div class="gs_rs">Abstract 3.</div>
			<div class="gs_fl"><a href="#">Cited by 30</a></div>
		</div>
	</body></html>
	`

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(htmlTemplate))
	}))
	defer srv.Close()

	old := gScholarEndpoint
	gScholarEndpoint = srv.URL + "/scholar"
	defer func() { gScholarEndpoint = old }()

	cfg := map[string]any{"enabled": true, "rate_limit": 100.0}
	s, err := NewGScholarSource(cfg)
	if err != nil {
		t.Fatalf("NewGScholarSource(cfg) = %v", err)
	}

	ctx := context.Background()
	cites, err := s.Search(ctx, types.EBMQuestion{Query: "test"}, 10)
	if err != nil {
		t.Fatalf("Search(mock) = %v", err)
	}

	wantTitles := []string{"First paper", "Second paper", "Third paper"}
	if len(cites) != len(wantTitles) {
		t.Fatalf("Search(mock) len = %d, want %d", len(cites), len(wantTitles))
	}
	for i, tt := range wantTitles {
		if cites[i].Title != tt {
			t.Fatalf("cites[%d].Title = %q, want %q", i, cites[i].Title, tt)
		}
	}

	// Verify cited-by values are extracted
	citedBys := []int{10, 20, 30}
	for i, want := range citedBys {
		if cites[i].CitedBy != want {
			t.Fatalf("cites[%d].CitedBy = %d, want %d", i, cites[i].CitedBy, want)
		}
	}
}

func TestGScholar_LimitRespectsCap(t *testing.T) {
	// Create many result blocks (more than limit=5)
	var sb strings.Builder
	sb.WriteString("<html><body>")
	for i := 0; i < 20; i++ {
		sb.WriteString(fmt.Sprintf(`
			<div class="gs_ri">
				<h3 class="gs_rt">Paper %d</h3>
				<div class="gs_a">A Author - Journal, 2024</div>
				<div class="gs_rs">Abstract.</div>
				<div class="gs_fl"><a href="#">Cited by 0</a></div>
			</div>
		`, i+1))
	}
	sb.WriteString("</body></html>")

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(sb.String()))
	}))
	defer srv.Close()

	old := gScholarEndpoint
	gScholarEndpoint = srv.URL + "/scholar"
	defer func() { gScholarEndpoint = old }()

	cfg := map[string]any{"enabled": true, "rate_limit": 100.0}
	s, err := NewGScholarSource(cfg)
	if err != nil {
		t.Fatalf("NewGScholarSource(cfg) = %v", err)
	}

	ctx := context.Background()
	cites, err := s.Search(ctx, types.EBMQuestion{Query: "test"}, 5)
	if err != nil {
		t.Fatalf("Search(mock, limit=5) = %v", err)
	}
	// Google Scholar caps per page at 10; we asked for 5 → should get 5
	if len(cites) != 5 {
		t.Fatalf("Search(mock, limit=5) len = %d, want 5", len(cites))
	}

	// Now test with a large limit — mock returns 20 blocks, so get all 20
	cites, err = s.Search(ctx, types.EBMQuestion{Query: "test"}, 50)
	if err != nil {
		t.Fatalf("Search(mock, limit=50) = %v", err)
	}
	// Mock server serves all 20 blocks (no pagination in mock)
	if len(cites) != 20 {
		t.Fatalf("Search(mock, limit=50) len = %d, want 20", len(cites))
	}
}
