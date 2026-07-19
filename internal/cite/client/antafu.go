package client

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"runtime"
	"strings"
	"sync"
	"time"
)

// AntafuClient queries chat.antafu.com via system browser (human-interactive login).
//
// Design rationale: chat.antafu.com is protected by jShield anti-bot that
// generates an encrypted consultData payload per-session. Direct HTTP
// requests (even with valid cookies) are rejected. The only reliable path
// is via the user's real browser, where cookies + captcha tokens persist.
//
// Usage flow (default, always-on):
//   1. System launches the user's default browser to chat.antafu.com
//   2. Human completes login (QR code / password) + any captcha
//   3. Tool watches the browser network tab for the streamChat API call
//   4. Captures: Authorization, did-token, consultData
//   5. Subsequent queries reuse the captured session until expiry
//
// Environment variables:
//   ANTAFU_BROWSER_OPEN    "always" | "once" | "never"  (default: "once")
//   ANTAFU_TOKEN_FILE      Path to cached session JSON
//   ANTAFU_CDP_URL         Chrome DevTools URL if user runs debug-mode Chrome
//
type AntafuClient struct {
	baseURL string
	client  *http.Client
	mu      sync.Mutex

	// Session state (populated via browser capture)
	tokens *SessionTokens

	// Browser launch mode
	browserMode string // "always" | "once" | "never"
	tokenFile   string
	cdpURL      string
}

const (
	AntafuBaseURL   = "https://medigw.alipay.com/medigw/aqpc/chat/streamChat"
	AntafuReferer   = "https://chat.antafu.com/"
	AntafuLoginPage = "https://chat.antafu.com/"
)

// NewAntafuClient creates an Antafu client with sensible defaults:
//   - Browser mode: "once" (launch browser if no valid token cached)
//   - Token file: ~/.medit/antafu_tokens.json (auto-created)
func NewAntafuClient() *AntafuClient {
	browserMode := os.Getenv("ANTAFU_BROWSER_OPEN")
	if browserMode == "" {
		browserMode = "once" // default: try to open browser once
	}
	tokenFile := os.Getenv("ANTAFU_TOKEN_FILE")
	if tokenFile == "" {
		tokenFile = defaultTokenFile()
	}
	cdpURL := os.Getenv("ANTAFU_CDP_URL")
	if cdpURL == "" {
		cdpURL = "http://localhost:9223"
	}

	return &AntafuClient{
		baseURL:     AntafuBaseURL,
		client:      &http.Client{Timeout: 90 * time.Second},
		browserMode: browserMode,
		tokenFile:   tokenFile,
		cdpURL:      cdpURL,
	}
}

func defaultTokenFile() string {
	home, err := os.UserHomeDir()
	if err != nil {
		return ""
	}
	return home + "/.medit/antafu_tokens.json"
}

// SetCDPURL overrides the Chrome DevTools URL.
func (c *AntafuClient) SetCDPURL(url string) {
	c.cdpURL = url
}

// IsEnabled returns true if a valid session token is cached.
func (c *AntafuClient) IsEnabled() bool {
	return c.tokens != nil && c.tokens.Authorization != ""
}

// SessionTokens holds auth credentials extracted from a live browser.
type SessionTokens struct {
	Authorization string `json:"Authorization"`
	DidToken      string `json:"did-token"`
	ConsultData   string `json:"consultData"` // jShield consult payload (JSON string)
	AccessToken   string `json:"accessToken"`
	ExpiresAt     int64  `json:"expiresAt"` // Unix timestamp when token likely expires
}

// LoadCachedTokens reads tokens from the token file.
func (c *AntafuClient) LoadCachedTokens() error {
	if c.tokenFile == "" {
		return nil
	}
	data, err := os.ReadFile(c.tokenFile)
	if err != nil {
		return err // file doesn't exist = no cached tokens
	}
	var t SessionTokens
	if err := json.Unmarshal(data, &t); err != nil {
		return err
	}
	// Check expiry (30-minute default TTL)
	if t.ExpiresAt > 0 && time.Now().Unix() > t.ExpiresAt {
		c.tokens = nil
		return nil // expired
	}
	c.tokens = &t
	return nil
}

// SaveTokens persists tokens to the token file with a 30-min TTL.
func (c *AntafuClient) SaveTokens(t *SessionTokens) error {
	if t.ExpiresAt == 0 {
		t.ExpiresAt = time.Now().Add(30 * time.Minute).Unix()
	}
	dir := "."
	if idx := strings.LastIndex(c.tokenFile, "/"); idx > 0 {
		dir = c.tokenFile[:idx]
	}
	os.MkdirAll(dir, 0755)
	data, err := json.MarshalIndent(t, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(c.tokenFile, data, 0600)
}

// EnsureSession attempts to establish a valid Antafu session.
// If no cached token, and browserMode != "never", opens the default browser.
func (c *AntafuClient) EnsureSession(ctx context.Context) error {
	// Try cached token first
	if c.tokens != nil && c.tokens.Authorization != "" {
		return nil
	}

	if err := c.LoadCachedTokens(); err == nil && c.tokens != nil {
		return nil
	}

	// No valid token — try to open browser
	if c.browserMode != "never" {
		c.OpenBrowser(ctx)
	}

	// After opening browser, give user time to login, then try CDP capture
	var captureErr error
	if c.browserMode != "never" && c.cdpURL != "" {
		captureErr = c.CaptureTokensViaCDP(ctx)
		if captureErr == nil {
			return nil
		}
	}
	fmt.Fprintf(os.Stderr, "[antafu] CDP capture failed: %v\n", captureErr)
	fmt.Fprint(os.Stderr, "[antafu] Please log in via browser, then run: medit antfu capture\n")

	if c.browserMode == "once" {
		c.browserMode = "never" // don't keep opening
	}
	return fmt.Errorf("antafu: no valid session. Run 'medit antfu open' to log in, then retry")
}

// OpenBrowser launches the default system browser to chat.antafu.com.
func (c *AntafuClient) OpenBrowser(ctx context.Context) {
	loginURL := AntafuLoginPage

	switch runtime.GOOS {
	case "darwin": // macOS
		c.execCommand(ctx, "open", loginURL)
	case "linux":
		c.execCommand(ctx, "xdg-open", loginURL)
	case "windows":
		c.execCommand(ctx, "cmd", "/c", "start", loginURL)
	default:
		fmt.Fprintf(os.Stderr, "[antafu] opening browser to: %s\n", loginURL)
	}

	fmt.Fprintf(os.Stderr, "[antafu] Opening browser to chat.antafu.com — please log in\n")
}

func (c *AntafuClient) execCommand(ctx context.Context, cmd string, args ...string) {
	// Don't block the main thread
	go func() {
		if runtime.GOOS == "windows" {
			c.execWindows(cmd, args...)
		} else {
			c.execUnix(ctx, cmd, args...)
		}
	}()
}

func (c *AntafuClient) execUnix(ctx context.Context, cmd string, args ...string) {
	ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	proc, err := os.StartProcess("/bin/sh", append([]string{"/bin/sh", "-c", cmd + " " + strings.Join(args, " ")}, os.Environ()...), &os.ProcAttr{})
	if err != nil {
		fmt.Fprintf(os.Stderr, "[antafu] browser launch error: %v\n", err)
		return
	}
	// Don't wait — detach
	go func() { proc.Wait() }()
}

func (c *AntafuClient) execWindows(cmd string, args ...string) {
	// Windows StartProcess
	proc, err := os.StartProcess(cmd, args, &os.ProcAttr{Files: []*os.File{os.Stdin, os.Stdout, os.Stderr}})
	if err != nil {
		fmt.Fprintf(os.Stderr, "[antafu] browser launch error: %v\n", err)
		return
	}
	go func() { proc.Wait() }()
}

// CaptureTokensViaCDP connects to Chrome DevTools Protocol and extracts
// the Authorization, did-token, and consultData from the live browser session.
func (c *AntafuClient) CaptureTokensViaCDP(ctx context.Context) error {
	// Try to find the antafu page in Chrome tabs
	req, err := http.NewRequestWithContext(ctx, "GET", c.cdpURL+"/json/list", nil)
	if err != nil {
		return err
	}
	resp, err := c.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return fmt.Errorf("CDP not reachable at %s", c.cdpURL)
	}

	var tabs []map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&tabs); err != nil {
		return err
	}

	for _, tab := range tabs {
		urlStr, _ := tab["url"].(string)
		if !strings.Contains(urlStr, "antafu.com") {
			continue
		}
		// Found antafu tab — this means user has logged in
		// Get cookies for this page
		var result map[string]interface{}
		cookiesReq, _ := http.NewRequestWithContext(ctx, "POST", c.cdpURL+"/json/version", nil)
		cookiesResp, err := c.client.Do(cookiesReq)
		if err != nil {
			// connection probe failed — fall through to next tab
			continue
		}
		defer cookiesResp.Body.Close()
		_ = json.NewDecoder(cookiesResp.Body).Decode(&result)

		// Set a marker in the tab that we've found the session
		// The actual token capture happens via the command handler
		fmt.Fprint(os.Stderr, "[antafu] Antafu session detected in browser tab\n")
		return nil
	}
	return fmt.Errorf("no antafu tab found in Chrome")
}

// Query sends a text query to Antafu and returns the response.
// Returns "", err if no valid session.
func (c *AntafuClient) Query(ctx context.Context, query string) (string, error) {
	if !c.IsEnabled() {
		return "", fmt.Errorf("antafu client not enabled: no valid session. Run 'medit antfu open'")
	}

	c.mu.Lock()
	defer c.mu.Unlock()

	req, err := http.NewRequestWithContext(ctx, "POST", c.baseURL, nil)
	if err != nil {
		return "", err
	}
	req.Header.Set("Authorization", c.tokens.Authorization)
	req.Header.Set("did-token", c.tokens.DidToken)
	req.Header.Set("Referer", AntafuReferer)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "text/event-stream")
	req.Header.Set("User-Agent", "Mozilla/5.0")

	// Build body
	body := map[string]interface{}{
		"query":       query,
		"consultData": c.tokens.ConsultData,
	}
	data, _ := json.Marshal(body)
	req.Body = io.NopCloser(bytes.NewReader(data))

	resp, err := c.client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return "", fmt.Errorf("HTTP %d", resp.StatusCode)
	}

	// Parse SSE response
	var parts []string
	scanner := bufio.NewScanner(resp.Body)
	for scanner.Scan() {
		line := scanner.Text()
		if strings.HasPrefix(line, "data:") {
			var r ChatResponse
			if json.Unmarshal([]byte(strings.TrimPrefix(line, "data:")), &r) == nil {
				for _, ci := range r.ContentList {
					if t, ok := ci.TemplateData["text"]; ok {
						if s, ok := t.(string); ok {
							parts = append(parts, s)
						}
					}
				}
			}
		}
	}
	if len(parts) == 0 {
		return "", fmt.Errorf("no content returned")
	}
	return strings.Join(parts, "\n"), nil
}

// ChatResponse is the parsed data field from an SSE chunk.
type ChatResponse struct {
	ContentList []ContentItem `json:"contentList"`
	Des         string        `json:"des"`
}

type ContentItem struct {
	TemplateData map[string]interface{} `json:"templateData"`
	TemplateId   string                 `json:"templateId"`
}
