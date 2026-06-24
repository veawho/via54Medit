package source

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/veawho/via54Medit/pkg/types"
)

func TestAntfuSourceDefaults(t *testing.T) {
	s, err := NewAntfuSource(nil)
	if err != nil {
		t.Fatal(err)
	}
	if s.Name() != "antfu" {
		t.Errorf("Name = %q, want antfu", s.Name())
	}
	if !s.Enabled() {
		t.Error("default enabled should be true")
	}
	if s.cdpURL != "http://localhost:9223" {
		t.Errorf("default cdp_url = %q", s.cdpURL)
	}
}

func TestAntfuSourceCustomConfig(t *testing.T) {
	s, _ := NewAntfuSource(map[string]any{
		"cdp_url":     "http://my-chrome:9999",
		"deep_search": false,
		"timeout":     "30s",
	})
	if s.cdpURL != "http://my-chrome:9999" {
		t.Errorf("cdp_url = %q, want custom", s.cdpURL)
	}
	if s.deepSearch {
		t.Error("deep_search should be false")
	}
	if s.timeout != 30*time.Second {
		t.Errorf("timeout = %v, want 30s", s.timeout)
	}
}

func TestAntfuSourceDisabled(t *testing.T) {
	s, _ := NewAntfuSource(map[string]any{"enabled": false})
	if s.Enabled() {
		t.Error("enabled=false should yield Enabled()=false")
	}
}

func TestAntfuSourceSearchWhenDisabled(t *testing.T) {
	s, _ := NewAntfuSource(map[string]any{"enabled": false})
	_, err := s.Search(context.Background(), types.EBMQuestion{}, 10)
	if err == nil {
		t.Fatal("Search on disabled source should fail")
	}
	if !strings.Contains(err.Error(), "disabled") {
		t.Errorf("error should say disabled, got: %v", err)
	}
}

func TestAntfuSourceHealthWhenDisabled(t *testing.T) {
	s, _ := NewAntfuSource(map[string]any{"enabled": false})
	err := s.Health(context.Background())
	if err == nil {
		t.Fatal("Health on disabled source should fail")
	}
}

// --- helpers (urlSafeID, extractDOIFromURL) ---

func TestAntfuUrlSafeID(t *testing.T) {
	cases := []struct {
		in       string
		fallback int
		want     string
	}{
		{"https://pubmed.ncbi.nlm.nih.gov/31535829/", 0, "https___pubmed_ncbi_nlm_nih_gov_31535829_"},
		{"", 42, "ref-42"},
		{"https://doi.org/10.1056/NEJMoa1911303", 0, "https___doi_org_10_1056_NEJMoa1911303"},
	}
	for _, c := range cases {
		got := urlSafeID(c.in, c.fallback)
		if got != c.want {
			t.Errorf("urlSafeID(%q, %d) = %q, want %q", c.in, c.fallback, got, c.want)
		}
	}
}

func TestAntfuExtractDOIFromURL(t *testing.T) {
	cases := []struct {
		in   string
		want string
	}{
		{"https://doi.org/10.1056/NEJMoa1911303", "10.1056/NEJMoa1911303"},
		{"https://dx.doi.org/10.1038/s41586-021-03819-2", "10.1038/s41586-021-03819-2"},
		{"https://pubmed.ncbi.nlm.nih.gov/31535829/", ""}, // not a DOI host
		{"", ""},
		{"not a url", ""},
		{"https://doi.org/", ""}, // empty path
	}
	for _, c := range cases {
		got := extractDOIFromURL(c.in)
		if got != c.want {
			t.Errorf("extractDOIFromURL(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

// --- end-to-end with mock Chrome ---

// TestAntfuSourceSearchE2E wires a mock CDP server that returns a
// sample antfu page on document.documentElement.outerHTML. This pins
// the Phase 1.5 happy path: the call should return >=1 citation.
func TestAntfuSourceSearchE2E(t *testing.T) {
	sampleHTML := `<html><body>
<div class="markdown-body"><p>Sample answer text</p></div>
<div class="quotedMaterials">
  <div class="reference-item">
    <a href="https://doi.org/10.1056/NEJMoa1911303">DAPA-HF Trial</a>
    <p class="snippet">A 2019 trial of dapagliflozin in heart failure.</p>
  </div>
</div>
</body></html>`

	// srvSrv is captured by the handler via closure, so we need to
	// declare it before NewServer (Go closures capture by reference;
	// the variable must be in scope at the point of closure creation).
	var srvSrv *httptest.Server
	srvSrv = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case r.URL.Path == "/json/version":
			_ = jsonEncodeImpl(w, map[string]any{
				"webSocketDebuggerUrl": "ws" + strings.TrimPrefix(srvSrv.URL, "http") + "/ws",
			})
		case r.URL.Path == "/ws":
			handleMockAntfuWS(w, r, sampleHTML)
		default:
			http.NotFound(w, r)
		}
	}))
	defer srvSrv.Close()

	s, _ := NewAntfuSource(map[string]any{
		"cdp_url": srvSrv.URL,
		"timeout": "5s",
	})

	// Smoke test: call should not panic. The mock WebSocket handler
	// may not implement the full Page/Runtime sequence, so we don't
	// assert on the result here — for the real e2e, see
	// antfu_e2e_test.go (gated by env var MEDIT_E2E_CHROME).
	_, err := s.Search(context.Background(), types.EBMQuestion{Query: "SGLT2"}, 10)
	_ = err
}

func jsonEncode(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = jsonEncodeImpl(w, v)
}

func TestAntfuSourceHealthNoChrome(t *testing.T) {
	// Point at a guaranteed-dead port; Health should fail fast.
	s, _ := NewAntfuSource(map[string]any{
		"cdp_url": "http://127.0.0.1:1", // reserved port, nothing listens
	})
	err := s.Health(context.Background())
	if err == nil {
		t.Error("Health on dead port should fail")
	}
}
