// Chrome DevTools Protocol (CDP) client for via54Medit's antfu adapter.
//
// This file implements the minimal CDP subset needed to drive chat.antafu.com:
//   - Connect to a running Chrome with --remote-debugging-port=9223
//   - Navigate to a URL
//   - Evaluate JavaScript expressions
//   - Wait for a CSS selector to appear (polling Runtime.evaluate)
//
// Reference: https://chromedevtools.github.io/devtools-protocol/
//
// Design notes:
//   - We use a single goroutine to read messages from the WebSocket and
//     dispatch them to either (a) the response channel for a pending
//     request, or (b) an event channel for server-pushed events.
//   - Each request gets a unique id; responses are matched by id.
//   - We do NOT support Target.* or Page.* frame management — Phase 1.5
//     assumes a single page (the default about:blank → navigated target).
package source

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	"github.com/gorilla/websocket"
)

// CDPClient is a single-connection Chrome DevTools Protocol client.
// Not safe for concurrent use of the same instance; create one per task.
type CDPClient struct {
	wsURL   string
	conn    *websocket.Conn
	mu      sync.Mutex // guards nextID, pending
	nextID  int64
	pending map[int64]chan cdpResponse
	events  chan cdpEvent
	closed  atomic.Bool
	readErr error
}

// cdpResponse is what we hand back to a waiting caller.
type cdpResponse struct {
	Result json.RawMessage `json:"result,omitempty"`
	Error  *cdpError       `json:"error,omitempty"`
}

type cdpError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

func (e *cdpError) Error() string {
	return fmt.Sprintf("CDP error %d: %s", e.Code, e.Message)
}

// cdpEvent is a server-pushed notification (no id, has method).
type cdpEvent struct {
	Method string          `json:"method"`
	Params json.RawMessage `json:"params,omitempty"`
}

// CDPVersion is the shape of GET /json/version response.
type CDPVersion struct {
	Browser              string `json:"Browser"`
	ProtocolVersion      string `json:"Protocol-Version"`
	WebSocketDebuggerURL string `json:"webSocketDebuggerUrl"`
}

// NewCDPClient connects to a Chrome instance via the given HTTP base URL
// (e.g., "http://localhost:9223"). It performs:
//  1. GET {baseURL}/json/version → fetch webSocketDebuggerUrl
//  2. WebSocket dial to that URL
//  3. Spawn a read pump goroutine
//
// Caller must call Close() when done. ctx controls the dial deadline.
func NewCDPClient(ctx context.Context, baseURL string) (*CDPClient, error) {
	var wsURL string

	// Try PUT /json/new first to create a new page target (supporting Page domain)
	newTabURL := strings.TrimRight(baseURL, "/") + "/json/new"
	req, err := http.NewRequestWithContext(ctx, "PUT", newTabURL, nil)
	if err == nil {
		httpClient := &http.Client{Timeout: 5 * time.Second}
		resp, err := httpClient.Do(req)
		if err == nil {
			defer resp.Body.Close()
			if resp.StatusCode/100 == 2 {
				var tab map[string]any
				if err := json.NewDecoder(resp.Body).Decode(&tab); err == nil {
					if id, ok := tab["id"].(string); ok && id != "" {
						// Activate the tab to bring it to foreground (prevents background throttle)
						activateURL := strings.TrimRight(baseURL, "/") + "/json/activate/" + id
						reqAct, errAct := http.NewRequestWithContext(ctx, "GET", activateURL, nil)
						if errAct == nil {
							if respAct, errAct2 := httpClient.Do(reqAct); errAct2 == nil {
								respAct.Body.Close()
							}
						}
					}
					if urlStr, ok := tab["webSocketDebuggerUrl"].(string); ok && urlStr != "" {
						wsURL = urlStr
					}
				}
			}
		}
	}

	// Fallback to GET /json/version (e.g. for mock servers or old versions)
	if wsURL == "" {
		discoveryURL := strings.TrimRight(baseURL, "/") + "/json/version"
		req, err := http.NewRequestWithContext(ctx, "GET", discoveryURL, nil)
		if err != nil {
			return nil, fmt.Errorf("cdp: build discovery request: %w", err)
		}
		httpClient := &http.Client{Timeout: 5 * time.Second}
		resp, err := httpClient.Do(req)
		if err != nil {
			return nil, fmt.Errorf("cdp: GET %s: %w", discoveryURL, err)
		}
		defer resp.Body.Close()
		if resp.StatusCode/100 != 2 {
			body, _ := io.ReadAll(resp.Body)
			return nil, fmt.Errorf("cdp: discovery returned %d: %s", resp.StatusCode, truncate(string(body), 200))
		}
		var ver CDPVersion
		if err := json.NewDecoder(resp.Body).Decode(&ver); err != nil {
			return nil, fmt.Errorf("cdp: decode version: %w", err)
		}
		wsURL = ver.WebSocketDebuggerURL
	}

	if wsURL == "" {
		return nil, errors.New("cdp: server returned empty webSocketDebuggerUrl")
	}

	// [2] WebSocket dial
	dialCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	conn, _, err := websocket.DefaultDialer.DialContext(dialCtx, wsURL, nil)
	if err != nil {
		return nil, fmt.Errorf("cdp: dial %s: %w", wsURL, err)
	}

	c := &CDPClient{
		wsURL:   wsURL,
		conn:    conn,
		pending: make(map[int64]chan cdpResponse),
		events:  make(chan cdpEvent, 32),
		// closed will be initialized to false automatically
	}
	go c.readPump()
	return c, nil
}

// readPump runs in its own goroutine. It reads JSON-RPC messages and
// dispatches responses (matched by id) to pending callers, and events
// (no id, has method) to the event channel. On read error, it closes
// everything and stores the error for later inspection.
func (c *CDPClient) readPump() {
	for {
		_, raw, err := c.conn.ReadMessage()
		if err != nil {
			c.closed.Store(true)
			c.mu.Lock()
			c.readErr = err
			// Unblock all pending callers.
			for _, ch := range c.pending {
				close(ch)
			}
			c.pending = nil
			c.mu.Unlock()
			close(c.events)
			return
		}
		// Peek at the structure: response has "id" + "result/error",
		// event has "method" + "params".
		var probe struct {
			ID     *int64          `json:"id,omitempty"`
			Method string          `json:"method,omitempty"`
			Result json.RawMessage `json:"result,omitempty"`
			Error  *cdpError       `json:"error,omitempty"`
		}
		if err := json.Unmarshal(raw, &probe); err != nil {
			continue // ignore malformed
		}
		if probe.Method != "" && probe.ID == nil {
			// Event
			select {
			case c.events <- cdpEvent{Method: probe.Method, Params: probe.Result}:
			default:
				// Event channel full; drop. Caller should poll fast enough.
			}
			continue
		}
		if probe.ID != nil {
			// The caller (send) wants the entire response body, not just
			// the "result" sub-object, so it can detect error vs result
			// without us re-marshaling. We pass the whole raw bytes.
			resp := cdpResponse{Result: raw, Error: probe.Error}
			c.mu.Lock()
			ch, ok := c.pending[*probe.ID]
			if ok {
				delete(c.pending, *probe.ID)
			}
			c.mu.Unlock()
			if ok {
				ch <- resp
				close(ch)
			}
		}
	}
}

// send marshals a request, sends it, and waits for the response (or ctx).
// Caller provides the method + params; we fill in the id.
func (c *CDPClient) send(ctx context.Context, method string, params any) (json.RawMessage, error) {
	if c.closed.Load() {
		return nil, errors.New("cdp: client is closed")
	}
	id := atomic.AddInt64(&c.nextID, 1)
	ch := make(chan cdpResponse, 1)
	c.mu.Lock()
	c.pending[id] = ch
	c.mu.Unlock()

	req := map[string]any{
		"id":     id,
		"method": method,
	}
	if params != nil {
		req["params"] = params
	}
	if err := c.conn.WriteJSON(req); err != nil {
		c.mu.Lock()
		delete(c.pending, id)
		c.mu.Unlock()
		return nil, fmt.Errorf("cdp: write %s: %w", method, err)
	}

	select {
	case resp, ok := <-ch:
		if !ok {
			c.mu.Lock()
			err := c.readErr
			c.mu.Unlock()
			return nil, fmt.Errorf("cdp: read pump died: %w", err)
		}
		if resp.Error != nil {
			return nil, resp.Error
		}
		return resp.Result, nil
	case <-ctx.Done():
		c.mu.Lock()
		delete(c.pending, id)
		c.mu.Unlock()
		return nil, ctx.Err()
	}
}

// Navigate loads a URL and waits for the page load event (or ctx deadline).
func (c *CDPClient) Navigate(ctx context.Context, targetURL string) error {
	// Validate URL: CDP rejects malformed URLs with a generic error.
	if _, err := url.Parse(targetURL); err != nil {
		return fmt.Errorf("cdp: invalid url %q: %w", targetURL, err)
	}
	// Send Page.navigate
	_, err := c.send(ctx, "Page.navigate", map[string]any{"url": targetURL})
	if err != nil {
		return fmt.Errorf("cdp: Page.navigate(%s): %w", targetURL, err)
	}
	// Wait for Page.loadEventFired (best-effort; many sites fire it
	// before the RAG response starts streaming, so callers should also
	// use WaitForSelector for application-specific readiness).
	waitCtx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	if err := c.waitForEvent(waitCtx, "Page.loadEventFired", 30*time.Second); err != nil {
		// Non-fatal: some pages fire loadEventFired very fast, before we
		// even start listening. Log via context, continue.
		_ = err
	}
	return nil
}

// Evaluate runs a JavaScript expression and returns the value as a string.
// The expression must evaluate to a string, number, or boolean (objects
// are returned via JSON.stringify). Use EvaluateJSON for structured data.
func (c *CDPClient) Evaluate(ctx context.Context, expression string) (string, error) {
	res, err := c.send(ctx, "Runtime.evaluate", map[string]any{
		"expression":    expression,
		"returnByValue": true,
		"awaitPromise":  true,
	})
	if err != nil {
		return "", fmt.Errorf("cdp: Runtime.evaluate: %w", err)
	}
	log.Printf("DEBUG CDP Evaluate raw res: %s", string(res))
	var got struct {
		Result struct {
			Result struct {
				Type  string          `json:"type"`
				Value json.RawMessage `json:"value"`
			} `json:"result"`
			Type             string          `json:"type"`
			Value            json.RawMessage `json:"value"`
			ExceptionDetails *struct {
				Text string `json:"text"`
			} `json:"exceptionDetails,omitempty"`
		} `json:"result"`
	}
	if err := json.Unmarshal(res, &got); err != nil {
		return "", fmt.Errorf("cdp: decode evaluate: %w", err)
	}
	if got.Result.ExceptionDetails != nil {
		return "", fmt.Errorf("cdp: JS exception: %s", got.Result.ExceptionDetails.Text)
	}

	typ := got.Result.Result.Type
	val := got.Result.Result.Value
	if typ == "" {
		typ = got.Result.Type
		val = got.Result.Value
	}

	switch typ {
	case "string":
		var s string
		if err := json.Unmarshal(val, &s); err != nil {
			return "", fmt.Errorf("cdp: decode string value: %w", err)
		}
		return s, nil
	default:
		return string(val), nil
	}
}

// waitForEvent blocks until the given method is observed (or ctx fires).
// It does NOT consume the event — every event goes to the channel pool.
// Caller should use this for one-shot "did the page load" signals.
func (c *CDPClient) waitForEvent(ctx context.Context, method string, timeout time.Duration) error {
	waitCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	// Drain events until we see ours.
	for {
		select {
		case ev, ok := <-c.events:
			if !ok {
				return errors.New("cdp: event channel closed (read pump died)")
			}
			if ev.Method == method {
				return nil
			}
		case <-waitCtx.Done():
			return waitCtx.Err()
		}
	}
}

// WaitForSelector polls Runtime.evaluate until the given CSS selector
// matches at least one element in the DOM, or the timeout fires.
//
// Polling interval: 500ms. The expression uses document.querySelectorAll
// and returns the count as a JSON-safe integer.
func (c *CDPClient) WaitForSelector(ctx context.Context, selector string, timeout time.Duration) error {
	// Sanitize: the selector goes into a JS string literal.
	// Escape backslashes and double-quotes.
	js := fmt.Sprintf(`document.querySelectorAll(%q).length`, selector)
	deadline := time.Now().Add(timeout)
	interval := 500 * time.Millisecond
	for {
		out, err := c.Evaluate(ctx, js)
		if err == nil && out != "0" && out != "null" {
			return nil
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("cdp: selector %q not found within %v", selector, timeout)
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(interval):
		}
	}
}

// Close shuts down the WebSocket connection and the read pump.
func (c *CDPClient) Close() error {
	if c.closed.Swap(true) {
		return nil // already closed
	}
	return c.conn.Close()
}

// Health checks the Chrome is reachable (CDP discovery endpoint).
// Does NOT establish a WebSocket — useful for pre-flight checks.
func ChromeHealth(ctx context.Context, baseURL string) error {
	req, err := http.NewRequestWithContext(ctx, "GET", strings.TrimRight(baseURL, "/")+"/json/version", nil)
	if err != nil {
		return err
	}
	resp, err := (&http.Client{Timeout: 3 * time.Second}).Do(req)
	if err != nil {
		return fmt.Errorf("chrome health: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return fmt.Errorf("chrome health: HTTP %d", resp.StatusCode)
	}
	return nil
}

// strToInt is a tiny helper for parsing number values from CDP's
// JSON-encoded return values (they come back as JSON numbers, not Go ints).
func strToInt(s string) int {
	n, _ := strconv.Atoi(s)
	return n
}

// keep imports tidy (errors, url, strconv are used above)
var _ = errors.New
var _ = url.Parse
var _ = strToInt

// truncate returns the first n bytes of s, with "..." if longer.
func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}
