// Antfu (蚂蚁阿福) adapter — Phase 1.5 implementation.
//
// This adapter drives a real Chrome instance via DevTools Protocol (CDP)
// to chat.antafu.com, sends a medical question, waits for the RAG
// response (~48s with deep_search=true), and extracts the answer +
// references from the rendered HTML.
//
// Prerequisite for runtime use:
//  1. Chrome is running with --remote-debugging-port=9223
//     (e.g. on Windows: chrome.exe --remote-debugging-port=9223 --user-data-dir=C:\chrome-debug)
//  2. User has logged into chat.antafu.com at least once (cookies persist via user-data-dir)
//  3. AntfuSource.cdp_url points to the Chrome instance
//
// If Chrome is not reachable, Search/Health return clear errors rather
// than panicking. Tests use mock servers (see antfu_cdp_test.go).
package source

import (
	"context"
	"fmt"
	"log"
	"net/url"
	"strings"
	"time"

	"github.com/veawho/via54Medit/pkg/types"
)

// AntfuSource is the real (Phase 1.5) implementation. It composes a
// CDPClient (Chrome DevTools Protocol) and the goquery-based Extract.
type AntfuSource struct {
	cdpURL     string
	deepSearch bool
	timeout    time.Duration
	enabled    bool
	extractCfg ExtractConfig
}

// NewAntfuSource builds the antfu adapter.
func NewAntfuSource(cfg map[string]any) (*AntfuSource, error) {
	s := &AntfuSource{
		cdpURL:     "http://localhost:9223",
		deepSearch: true,
		timeout:    60 * time.Second,
		enabled:    true,
		extractCfg: DefaultExtractConfig(),
	}
	if cfg != nil {
		if v, ok := cfg["enabled"].(bool); ok {
			s.enabled = v
		}
		if v, ok := cfg["cdp_url"].(string); ok && v != "" {
			s.cdpURL = v
		}
		if v, ok := cfg["deep_search"].(bool); ok {
			s.deepSearch = v
		}
		if v, ok := cfg["timeout"].(string); ok && v != "" {
			if d, err := time.ParseDuration(v); err == nil {
				s.timeout = d
			}
		}
	}
	return s, nil
}

func (s *AntfuSource) Name() string  { return "antfu" }
func (s *AntfuSource) Enabled() bool { return s.enabled }

// Health checks Chrome is reachable and the antfu page loads.
func (s *AntfuSource) Health(ctx context.Context) error {
	if !s.enabled {
		return fmt.Errorf("antfu: source is disabled")
	}
	return ChromeHealth(ctx, s.cdpURL)
}

// Search drives a single ask round-trip:
//  1. Connect to Chrome (CDP)
//  2. Navigate to chat.antafu.com
//  3. Inject the query into the input box
//  4. Wait for the response to render
//  5. Extract answer + references from the HTML
//  6. Return citations (one per reference) — the answer text is logged
//     but not yet attached to a single citation (Phase 2 router will).
//
// The Search contract is "return citations" — antfu's "answer" is
// context for the user, not a citation. So the citations we return
// are the cited references.
func (s *AntfuSource) Search(ctx context.Context, q types.EBMQuestion, limit int) ([]types.Citation, error) {
	if !s.enabled {
		return nil, fmt.Errorf("antfu: source is disabled")
	}
	if limit <= 0 {
		limit = 20
	}

	// [1] Connect to Chrome.
	dialCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	cdp, err := NewCDPClient(dialCtx, s.cdpURL)
	if err != nil {
		return nil, fmt.Errorf("antfu: connect to Chrome at %s: %w", s.cdpURL, err)
	}
	defer cdp.Close()

	// [2] Navigate to antfu chat page.
	navCtx, navCancel := context.WithTimeout(ctx, 30*time.Second)
	defer navCancel()
	if err := cdp.Navigate(navCtx, "https://chat.antafu.com/"); err != nil {
		return nil, fmt.Errorf("antfu: navigate: %w", err)
	}

	// [2.5] Verify login status.
	verifyCtx, verifyCancel := context.WithTimeout(ctx, 10*time.Second)
	defer verifyCancel()

	if err := cdp.WaitForSelector(verifyCtx, "body", 5*time.Second); err != nil {
		return nil, fmt.Errorf("antfu: verify page load: %w", err)
	}

	loginCheckExpr := `
		(async function() {
			const sleep = ms => new Promise(r => setTimeout(r, ms));
			const deadline = Date.now() + 10000;
			while (Date.now() < deadline) {
				const userSec = document.querySelector('div[class*=userSection]');
				if (userSec) {
					const text = userSec.textContent || "";
					if (text.includes("点击登录") || text.includes("登录/注册") || text.includes("登录")) {
						return "NOT_LOGGED_IN";
					}
					return "OK";
				}
				await sleep(200);
			}
			return "TIMEOUT";
		})()
	`
	loginStatus, err := cdp.Evaluate(verifyCtx, loginCheckExpr)
	if err != nil {
		return nil, fmt.Errorf("antfu: check login status: %w", err)
	}
	
	// Debug logging
	debugURL, _ := cdp.Evaluate(verifyCtx, "window.location.href")
	debugTitle, _ := cdp.Evaluate(verifyCtx, "document.title")
	log.Printf("DEBUG: Target URL = %q, Title = %q, loginStatus = %q", debugURL, debugTitle, loginStatus)

	if loginStatus == "NOT_LOGGED_IN" {
		return nil, fmt.Errorf("您尚未登录蚂蚁阿福 (chat.antafu.com) 或登录已失效，请在已连通的浏览器窗口中登录后再试")
	}
	if loginStatus == "TIMEOUT" {
		return nil, fmt.Errorf("登录校验超时：无法检测到登录状态，请确保您已在浏览器中打开并登录 chat.antafu.com")
	}

	// [3] Inject the query into the input box.
	// The selector below targets the common antfu input element. If antfu
	// changes their DOM, the user can override via extractCfg (Phase 2).
	injectCtx, injectCancel := context.WithTimeout(ctx, 15*time.Second)
	defer injectCancel()

	expr := fmt.Sprintf(`
		(async function() {
			const sleep = ms => new Promise(r => setTimeout(r, ms));
			const deadline = Date.now() + 10000;
			while (Date.now() < deadline) {
				const ta = document.querySelector('textarea.ant-input, textarea[class*=ant-input]');
				if (ta) {
					const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
					setter.call(ta, %q);
					ta.dispatchEvent(new Event('input', { bubbles: true }));
					return 'OK';
				}
				await sleep(200);
			}
			return 'NO_INPUT';
		})()
	`, q.Query)
	jsResult, err := cdp.Evaluate(injectCtx, expr)
	if err != nil {
		return nil, fmt.Errorf("antfu: inject query: %w", err)
	}
	if jsResult != "OK" {
		return nil, fmt.Errorf("antfu: input box not found (page may have changed)")
	}

	// Wait 1 second for React to process state updates and enable the button
	time.Sleep(1 * time.Second)

	// [4] Click the send button. The selector targets antfu's send icon.
	sendCtx, sendCancel := context.WithTimeout(ctx, 10*time.Second)
	defer sendCancel()
	clickExpr := `
		(async function() {
			const sleep = ms => new Promise(r => setTimeout(r, ms));
			const deadline = Date.now() + 5000;
			while (Date.now() < deadline) {
				const btn = document.querySelector('button[class*=ant-btn-primary], [class*=sendButton], button[type=submit], button[class*=send-button]');
				if (btn) {
					btn.click();
					btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
					return 'OK';
				}
				await sleep(200);
			}
			return 'NO_BUTTON';
		})()
	`
	if jsResult, err := cdp.Evaluate(sendCtx, clickExpr); err != nil {
		return nil, fmt.Errorf("antfu: click send: %w", err)
	} else if jsResult != "OK" {
		return nil, fmt.Errorf("antfu: send button not found (page may have changed)")
	}

	// [5] Wait for the response to fully render. We poll for the
	// presence of .quotedMaterials (the references panel), or for
	// a "typing" indicator to disappear. The RAG response is slow
	// (~48s with deep_search=true), so the timeout is the configured
	// s.timeout.
	waitCtx, waitCancel := context.WithTimeout(ctx, s.timeout)
	defer waitCancel()
	if err := cdp.WaitForSelector(waitCtx, s.extractCfg.QuoteContainerSelector, s.timeout); err != nil {
		// Fallback: even if we don't see the references panel, capture
		// whatever the assistant wrote. Many queries have no refs.
	}

	// [6] Read the rendered HTML and extract answer + references.
	htmlCtx, htmlCancel := context.WithTimeout(ctx, 10*time.Second)
	defer htmlCancel()
	htmlStr, err := cdp.Evaluate(htmlCtx, "document.documentElement.outerHTML")
	if err != nil {
		return nil, fmt.Errorf("antfu: read HTML: %w", err)
	}

	extracted, err := Extract(strings.NewReader(htmlStr), s.extractCfg)
	if err != nil {
		return nil, fmt.Errorf("antfu: extract: %w", err)
	}

	// [7] Convert AntfuRef to types.Citation. antfu doesn't always
	// provide PMID/DOI, so we use the URL itself as the ID.
	cites := make([]types.Citation, 0, len(extracted.References))
	now := time.Now()
	for i, ref := range extracted.References {
		c := types.Citation{
			ID:    "antfu:" + urlSafeID(ref.URL, i),
			Title: ref.Title,
			Year:  ref.Year,
		}
		// Use the snippet as the abstract proxy.
		c.Abstract = ref.Snippet
		// Stash the original URL in the enrichment log for downstream use.
		c.EnrichmentLog = []string{"antfu_url=" + ref.URL}
		// Try to extract DOI from URL.
		c.DOI = extractDOIFromURL(ref.URL)
		c.SourceOrigin = []string{"antfu"}
		c.FetchedAt = now
		cites = append(cites, c)
		if len(cites) >= limit {
			break
		}
	}
	return cites, nil
}

// urlSafeID returns a short, filesystem-safe identifier from a URL.
// Used to build the internal ID (c.ID) when antfu doesn't provide a PMID/DOI.
func urlSafeID(rawURL string, fallback int) string {
	if rawURL == "" {
		return fmt.Sprintf("ref-%d", fallback)
	}
	// Trim URL, replace non-alnum with '_'.
	cleaned := strings.Map(func(r rune) rune {
		if (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9') {
			return r
		}
		return '_'
	}, rawURL)
	if len(cleaned) > 60 {
		cleaned = cleaned[:60]
	}
	return cleaned
}

// extractDOIFromURL pulls a DOI like 10.1056/NEJMoa... from a URL string.
// Returns "" if no DOI present.
func extractDOIFromURL(rawURL string) string {
	if rawURL == "" {
		return ""
	}
	u, err := url.Parse(rawURL)
	if err != nil {
		return ""
	}
	// Common DOI hostnames.
	doiHosts := map[string]bool{
		"doi.org":        true,
		"dx.doi.org":     true,
		"www.doi.org":    true,
		"hdl.handle.net": true,
	}
	if !doiHosts[u.Host] {
		return ""
	}
	// Path is usually "/10.1056/NEJMoa..."
	parts := strings.SplitN(strings.TrimPrefix(u.Path, "/"), "/", 2)
	if len(parts) >= 2 && strings.HasPrefix(parts[0], "10.") {
		return parts[0] + "/" + parts[1]
	}
	return ""
}
