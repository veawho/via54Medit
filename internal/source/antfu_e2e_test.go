// End-to-end tests for the antfu adapter. These tests require a real
// Chrome instance with --remote-debugging-port=9223 and a logged-in
// chat.antafu.com session. To run:
//
//	# 1. Start Chrome with debug port
//	# Windows:
//	"chrome.exe" --remote-debugging-port=9223 --user-data-dir=C:\chrome-debug
//	# macOS:
//	"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
//	  --remote-debugging-port=9223 --user-data-dir=/tmp/chrome-debug
//
//	# 2. Log in to chat.antafu.com once (cookies persist in user-data-dir)
//
//	# 3. Run the tests
//	MEDIT_E2E_CHROME=1 go test -v -run TestAntfuE2E ./internal/source/...
//
// Without MEDIT_E2E_CHROME=1, the tests are skipped (so CI without
// Chrome doesn't fail).
package source

import (
	"context"
	"encoding/json"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/veawho/via54Medit/pkg/types"
)

// chromeTestURL is the URL of the running Chrome instance. Override
// with MEDIT_E2E_CHROME_URL for non-default hosts.
func chromeTestURL() string {
	if v := os.Getenv("MEDIT_E2E_CHROME_URL"); v != "" {
		return v
	}
	return "http://localhost:9223"
}

func skipIfNoChrome(t *testing.T) {
	t.Helper()
	if os.Getenv("MEDIT_E2E_CHROME") == "" {
		t.Skip("MEDIT_E2E_CHROME not set; skipping e2e (set to 1 to run)")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	if err := ChromeHealth(ctx, chromeTestURL()); err != nil {
		t.Skipf("Chrome not reachable at %s: %v", chromeTestURL(), err)
	}
}

// TestAntfuE2EHealth is the simplest possible e2e: just verify we can
// talk to Chrome. If this fails, all subsequent e2e tests will too.
func TestAntfuE2EHealth(t *testing.T) {
	skipIfNoChrome(t)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := ChromeHealth(ctx, chromeTestURL()); err != nil {
		t.Fatalf("ChromeHealth: %v", err)
	}
}

// TestAntfuE2EConnect opens a WebSocket to Chrome and closes cleanly.
// This validates the CDP handshake against a real Chrome version.
func TestAntfuE2EConnect(t *testing.T) {
	skipIfNoChrome(t)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	cdp, err := NewCDPClient(ctx, chromeTestURL())
	if err != nil {
		t.Fatalf("NewCDPClient: %v", err)
	}
	defer cdp.Close()
	// Sanity: send a no-op evaluate to make sure the round-trip works.
	v, err := cdp.Evaluate(ctx, "1+1")
	if err != nil {
		t.Fatalf("Evaluate 1+1: %v", err)
	}
	if v != "2" {
		t.Errorf("Evaluate 1+1 = %q, want \"2\"", v)
	}
}

// TestAntfuE2ENavigateAndRead navigates to a known stable page
// (example.com) and reads back document.title. This validates the
// Page.navigate + Runtime.evaluate + outerHTML chain against real Chrome.
func TestAntfuE2ENavigateAndRead(t *testing.T) {
	skipIfNoChrome(t)
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	cdp, err := NewCDPClient(ctx, chromeTestURL())
	if err != nil {
		t.Fatal(err)
	}
	defer cdp.Close()

	if err := cdp.Navigate(ctx, "https://example.com"); err != nil {
		t.Fatalf("Navigate: %v", err)
	}
	title, err := cdp.Evaluate(ctx, "document.title")
	if err != nil {
		t.Fatalf("Evaluate title: %v", err)
	}
	if !strings.Contains(strings.ToLower(title), "example") {
		t.Errorf("document.title = %q, expected to contain \"example\"", title)
	}

	// Read full HTML to verify outerHTML works.
	html, err := cdp.Evaluate(ctx, "document.documentElement.outerHTML")
	if err != nil {
		t.Fatalf("Evaluate outerHTML: %v", err)
	}
	if !strings.Contains(html, "<html") {
		t.Errorf("outerHTML doesn't look like HTML (first 100 chars: %q)", html[:min(100, len(html))])
	}
}

// TestAntfuE2ESearch is the full happy path: query → citations.
// This test will FAIL with a real antfu page if the DOM selectors
// don't match (see antfu_extract.go DefaultExtractConfig).
func TestAntfuE2ESearch(t *testing.T) {
	skipIfNoChrome(t)
	s, err := NewAntfuSource(map[string]any{
		"cdp_url": chromeTestURL(),
		"timeout": "90s", // antfu RAG can take 30-60s
	})
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 100*time.Second)
	defer cancel()
	cites, err := s.Search(ctx, types.EBMQuestion{
		Query:  "SGLT2 inhibitor for heart failure",
		Intent: types.IntentSearch,
	}, 5)
	if err != nil {
		t.Fatalf("Search: %v (this is expected if antfu is down — see test output)", err)
	}
	if len(cites) == 0 {
		t.Log("Search returned 0 citations (antfu may have no refs for this query)")
	}
	for i, c := range cites {
		dump, _ := json.MarshalIndent(c, "", "  ")
		t.Logf("citation[%d]: %s", i, string(dump))
	}
}

// min is a small helper (Go 1.21+ has it as a builtin, but we keep this
// for older toolchains).
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
