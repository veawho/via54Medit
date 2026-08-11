// Package source - unit tests for Sci-Hub adapter.
package source

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/veawho/via54Medit/pkg/types"
)

func TestNewSciHubSource(t *testing.T) {
	tests := []struct {
		name     string
		cfg      map[string]any
		wantName string
		wantEn   bool
	}{
		{
			name:     "defaults",
			cfg:      nil,
			wantName: "sci-hub",
			wantEn:   false, // disabled by default
		},
		{
			name:     "enabled",
			cfg:      map[string]any{"enabled": true},
			wantName: "sci-hub",
			wantEn:   true,
		},
		{
			name:     "custom rate limit",
			cfg:      map[string]any{"enabled": true, "rate_limit": 2},
			wantName: "sci-hub",
			wantEn:   true,
		},
		{
			name:     "custom mirrors",
			cfg:      map[string]any{"enabled": true, "mirrors": "sci-hub.se,sci-hub.ru"},
			wantName: "sci-hub",
			wantEn:   true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			s, err := NewSciHubSource(tt.cfg)
			if err != nil {
				t.Fatalf("NewSciHubSource() error = %v", err)
			}
			if s.Name() != tt.wantName {
				t.Errorf("Name() = %q, want %q", s.Name(), tt.wantName)
			}
			if s.Enabled() != tt.wantEn {
				t.Errorf("Enabled() = %v, want %v", s.Enabled(), tt.wantEn)
			}
		})
	}
}

func TestSciHubSource_DisabledReturnsError(t *testing.T) {
	s, err := NewSciHubSource(nil)
	if err != nil {
		t.Fatalf("NewSciHubSource() error = %v", err)
	}

	// Search should fail when disabled
	_, err = s.Search(context.Background(), types.EBMQuestion{Query: "10.1038/s41586-021-03621-9"}, 1)
	if err == nil {
		t.Error("Search() on disabled source should return error")
	}

	// Health should fail when disabled
	err = s.Health(context.Background())
	if err == nil {
		t.Error("Health() on disabled source should return error")
	}

	// Resolve should fail when disabled
	_, err = s.Resolve(context.Background(), "10.1038/s41586-021-03621-9")
	if err == nil {
		t.Error("Resolve() on disabled source should return error")
	}
}

func TestResolve_Disabled(t *testing.T) {
	s, err := NewSciHubSource(nil)
	if err != nil {
		t.Fatalf("NewSciHubSource() error = %v", err)
	}
	_, err = s.Resolve(context.Background(), "10.1038/s41586-021-03621-9")
	if err == nil {
		t.Error("Resolve() on disabled source should fail")
	}
}

func TestResolve_MirrorReturnsPDF(t *testing.T) {
	// Create a test server that returns a PDF response
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/pdf")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("%PDF-1.4"))
	}))
	defer server.Close()

	s, err := NewSciHubSource(map[string]any{
		"enabled":    true,
		"mirrors":    server.URL, // use test server as mirror
		"rate_limit": 100,
	})
	if err != nil {
		t.Fatalf("NewSciHubSource() error = %v", err)
	}

	ctx := context.Background()
	pdfURL, err := s.Resolve(ctx, "10.1038/s41586-021-03621-9")
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}
	if pdfURL == "" {
		t.Error("Resolve() returned empty PDF URL")
	}
}

func TestResolve_MirrorReturnsHTML_OK(t *testing.T) {
	// Sci-Hub typically returns HTML with a redirect script; status 200 is valid
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("<html><body><script>window.location='/storage/file.pdf'</script></body></html>"))
	}))
	defer server.Close()

	s, err := NewSciHubSource(map[string]any{
		"enabled":    true,
		"mirrors":    server.URL,
		"rate_limit": 100,
	})
	if err != nil {
		t.Fatalf("NewSciHubSource() error = %v", err)
	}

	pdfURL, err := s.Resolve(context.Background(), "10.1038/s41586-021-03621-9")
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}
	if pdfURL == "" {
		t.Error("Resolve() should return URL even for HTML response")
	}
}

func TestResolve_MirrorReturns404_NextMirror(t *testing.T) {
	// Two mirrors: first returns 404, second returns 200 HTML
	server1 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server1.Close()

	server2 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer server2.Close()

	s, err := NewSciHubSource(map[string]any{
		"enabled":    true,
		"mirrors":    fmt.Sprintf("%s,%s", server1.URL, server2.URL),
		"rate_limit": 100,
	})
	if err != nil {
		t.Fatalf("NewSciHubSource() error = %v", err)
	}

	pdfURL, err := s.Resolve(context.Background(), "10.1038/s41586-021-03621-9")
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}
	if pdfURL == "" {
		t.Error("Resolve() should fall back to second mirror")
	}
}

func TestResolve_AllMirrorsFail(t *testing.T) {
	// Both mirrors return 404
	server1 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server1.Close()

	server2 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer server2.Close()

	s, err := NewSciHubSource(map[string]any{
		"enabled":    true,
		"mirrors":    fmt.Sprintf("%s,%s", server1.URL, server2.URL),
		"rate_limit": 100,
	})
	if err != nil {
		t.Fatalf("NewSciHubSource() error = %v", err)
	}

	_, err = s.Resolve(context.Background(), "10.1038/s41586-021-03621-9")
	if err == nil {
		t.Error("Resolve() should fail when all mirrors return non-2xx")
	}
}

func TestResolve_EmptyIdentifier(t *testing.T) {
	s, err := NewSciHubSource(map[string]any{"enabled": true})
	if err != nil {
		t.Fatalf("NewSciHubSource() error = %v", err)
	}
	_, err = s.Resolve(context.Background(), "")
	if err == nil {
		t.Error("Resolve('') should return error")
	}
}

func TestResolve_InvalidIdentifier(t *testing.T) {
	s, err := NewSciHubSource(map[string]any{"enabled": true})
	if err != nil {
		t.Fatalf("NewSciHubSource() error = %v", err)
	}
	_, err = s.Resolve(context.Background(), "not-a-valid-identifier")
	if err == nil {
		t.Error("Resolve('not-a-valid-identifier') should return error")
	}
}

func TestCanonicalizeIdentifier(t *testing.T) {
	tests := []struct {
		name string
		raw  string
		want string
	}{
		// DOI variants
		{"DOI plain", "10.1038/s41586-021-03621-9", "10.1038/s41586-021-03621-9"},
		{"DOI full url", "https://doi.org/10.1038/s41586-021-03621-9", "10.1038/s41586-021-03621-9"},
		{"DOI http", "http://doi.org/10.1056/NEJMoa1911303", "10.1056/NEJMoa1911303"},
		{"DOI doi.org", "doi.org/10.1126/science.1234567", "10.1126/science.1234567"},
		{"DOI with spaces", "  10.1056/NEJMoa1911303  ", "10.1056/NEJMoa1911303"},
		// PMID variants
		{"PMID plain", "31535829", "31535829"},
		{"PMID with spaces", " 31535829 ", "31535829"},
		{"PMID short", "12345", "12345"},
		{"PMID long", "3153582901", "3153582901"}, // max 10 digits
		// Invalid
		{"empty", "", ""},
		{"letters", "not-a-doi", ""},
		{"mixed", "PMID:12345", ""},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := canonicalizeIdentifier(tt.raw)
			if got != tt.want {
				t.Errorf("canonicalizeIdentifier(%q) = %q, want %q", tt.raw, got, tt.want)
			}
		})
	}
}

func TestParseMirrorList(t *testing.T) {
	tests := []struct {
		name string
		raw  string
		want []string
	}{
		{
			name: "simple comma list",
			raw:  "sci-hub.se,sci-hub.ru,sci-hub.st",
			want: []string{
				"https://sci-hub.se",
				"https://sci-hub.ru",
				"https://sci-hub.st",
			},
		},
		{
			name: "with spaces",
			raw:  " sci-hub.se , sci-hub.ru ",
			want: []string{"https://sci-hub.se", "https://sci-hub.ru"},
		},
		{
			name: "already with https",
			raw:  "https://sci-hub.se,https://sci-hub.ru",
			want: []string{"https://sci-hub.se", "https://sci-hub.ru"},
		},
		{
			name: "mixed",
			raw:  "sci-hub.se,https://sci-hub.ru",
			want: []string{"https://sci-hub.se", "https://sci-hub.ru"},
		},
		{
			name: "empty",
			raw:  "",
			want: []string{},
		},
		{
			name: "trailing slash",
			raw:  "sci-hub.se/",
			want: []string{"https://sci-hub.se"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := parseMirrorList(tt.raw)
			if len(got) != len(tt.want) {
				t.Fatalf("parseMirrorList(%q) len = %d, want %d", tt.raw, len(got), len(tt.want))
			}
			for i := range got {
				if got[i] != tt.want[i] {
					t.Errorf("parseMirrorList(%q)[%d] = %q, want %q", tt.raw, i, got[i], tt.want[i])
				}
			}
		})
	}
}
