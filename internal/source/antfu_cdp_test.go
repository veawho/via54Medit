package source

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

// mockCDPServer is a tiny in-process Chrome DevTools Protocol server for
// unit tests. It implements:
//   - GET /json/version → returns a fake webSocketDebuggerUrl
//   - WebSocket upgrade at the same path → handles Page.navigate and
//     Runtime.evaluate round-trips
type mockCDPServer struct {
	*httptest.Server
	upgrader     websocket.Upgrader
	navCalls     atomic.Int32
	evalCalls    atomic.Int32
	lastExpr     atomic.Value // string
	evalResponse string
}

func newMockCDPServer(t *testing.T, evalResponse string) *mockCDPServer {
	t.Helper()
	m := &mockCDPServer{
		upgrader:     websocket.Upgrader{CheckOrigin: func(r *http.Request) bool { return true }},
		evalResponse: evalResponse,
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/json/version", func(w http.ResponseWriter, r *http.Request) {
		// Return a webSocketDebuggerUrl pointing to the same test server.
		wsURL := "ws" + strings.TrimPrefix(m.URL, "http") + "/devtools/browser/test-id"
		_ = json.NewEncoder(w).Encode(map[string]any{
			"Browser":              "MockChrome/1.0",
			"Protocol-Version":     "1.3",
			"webSocketDebuggerUrl": wsURL,
		})
	})
	mux.HandleFunc("/devtools/browser/test-id", m.handleWS)
	m.Server = httptest.NewServer(mux)
	return m
}

func (m *mockCDPServer) handleWS(w http.ResponseWriter, r *http.Request) {
	conn, err := m.upgrader.Upgrade(w, r, nil)
	if err != nil {
		return
	}
	defer conn.Close()
	for {
		_, raw, err := conn.ReadMessage()
		if err != nil {
			return
		}
		var req struct {
			ID     int64           `json:"id"`
			Method string          `json:"method"`
			Params json.RawMessage `json:"params"`
		}
		if err := json.Unmarshal(raw, &req); err != nil {
			continue
		}
		switch req.Method {
		case "Page.navigate":
			m.navCalls.Add(1)
			resp := map[string]any{"id": req.ID, "result": map[string]any{}}
			_ = conn.WriteJSON(resp)
			// Also send a Page.loadEventFired event so waitForEvent returns.
			_ = conn.WriteJSON(map[string]any{"method": "Page.loadEventFired"})
		case "Runtime.evaluate":
			m.evalCalls.Add(1)
			var p struct {
				Expression string `json:"expression"`
			}
			_ = json.Unmarshal(req.Params, &p)
			m.lastExpr.Store(p.Expression)
			// Build the CDP response shape. The "value" field is a Go
			// string; conn.WriteJSON will JSON-encode it once (adding
			// quotes), so the wire bytes are {"value":"hello world"}.
			// Do NOT pre-marshal the value — that would cause double
			// encoding.
			resp := map[string]any{
				"id": req.ID,
				"result": map[string]any{
					"type":  "string",
					"value": m.evalResponse,
				},
			}
			_ = conn.WriteJSON(resp)
		}
	}
}

func TestChromeHealth(t *testing.T) {
	m := newMockCDPServer(t, "ok")
	defer m.Close()
	if err := ChromeHealth(context.Background(), m.URL); err != nil {
		t.Errorf("ChromeHealth: %v", err)
	}
}

func TestChromeHealthDown(t *testing.T) {
	m := newMockCDPServer(t, "ok")
	m.Close()
	if err := ChromeHealth(context.Background(), m.URL); err == nil {
		t.Error("ChromeHealth on closed server should fail")
	}
}

func TestChromeHealthBadJSON(t *testing.T) {
	// HTTP 500 response: ChromeHealth just checks status, not JSON shape.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "boom", http.StatusInternalServerError)
	}))
	defer srv.Close()
	if err := ChromeHealth(context.Background(), srv.URL); err == nil {
		t.Error("ChromeHealth on HTTP 500 should fail")
	}
}

func TestNewCDPClientConnects(t *testing.T) {
	m := newMockCDPServer(t, "ok")
	defer m.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	c, err := NewCDPClient(ctx, m.URL)
	if err != nil {
		t.Fatal(err)
	}
	defer c.Close()
	if c.wsURL == "" {
		t.Error("wsURL not set after NewCDPClient")
	}
}

func TestNewCDPClientDiscoveryFails(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "boom", http.StatusInternalServerError)
	}))
	defer srv.Close()
	_, err := NewCDPClient(context.Background(), srv.URL)
	if err == nil {
		t.Error("NewCDPClient on 500 should fail")
	}
}

func TestCDPNavigate(t *testing.T) {
	m := newMockCDPServer(t, "ok")
	defer m.Close()

	c, err := NewCDPClient(context.Background(), m.URL)
	if err != nil {
		t.Fatal(err)
	}
	defer c.Close()

	if err := c.Navigate(context.Background(), "https://example.com"); err != nil {
		t.Fatalf("Navigate: %v", err)
	}
	if got := m.navCalls.Load(); got != 1 {
		t.Errorf("navCalls = %d, want 1", got)
	}
}

func TestCDPEvaluate(t *testing.T) {
	m := newMockCDPServer(t, "hello world")
	defer m.Close()

	c, _ := NewCDPClient(context.Background(), m.URL)
	defer c.Close()

	got, err := c.Evaluate(context.Background(), "1+1")
	if err != nil {
		t.Fatal(err)
	}
	// Evaluate unquotes JSON strings: a JS string "hello world" comes
	// back as the Go string "hello world" (no surrounding quotes).
	if got != "hello world" {
		t.Errorf("Evaluate = %q, want %q", got, "hello world")
	}
	if calls := m.evalCalls.Load(); calls != 1 {
		t.Errorf("evalCalls = %d, want 1", calls)
	}
}

func TestCDPEvaluateJSException(t *testing.T) {
	// Build a separate server that always returns exceptionDetails.
	// We use a closure so the URL inside the handler captures the
	// final srv.URL after httptest.NewServer returns.
	var srvURL string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/json/version" {
			_ = json.NewEncoder(w).Encode(map[string]any{
				"webSocketDebuggerUrl": "ws" + strings.TrimPrefix(srvURL, "http") + "/ws",
			})
			return
		}
		conn, _ := (&websocket.Upgrader{CheckOrigin: func(r *http.Request) bool { return true }}).Upgrade(w, r, nil)
		defer conn.Close()
		_, raw, err := conn.ReadMessage()
		if err != nil {
			return
		}
		var req struct {
			ID     int64  `json:"id"`
			Method string `json:"method"`
		}
		_ = json.Unmarshal(raw, &req)
		_ = conn.WriteJSON(map[string]any{
			"id": req.ID,
			"result": map[string]any{
				"exceptionDetails": map[string]any{"text": "ReferenceError: x is not defined"},
			},
		})
	}))
	srvURL = srv.URL
	defer srv.Close()

	c, _ := NewCDPClient(context.Background(), srv.URL)
	defer c.Close()

	_, err := c.Evaluate(context.Background(), "throw new Error('boom')")
	if err == nil {
		t.Fatal("Evaluate on JS exception should fail")
	}
	if !strings.Contains(err.Error(), "ReferenceError") {
		t.Errorf("error should mention exception text, got: %v", err)
	}
}

func TestCDPCloseIsIdempotent(t *testing.T) {
	m := newMockCDPServer(t, "ok")
	defer m.Close()
	c, _ := NewCDPClient(context.Background(), m.URL)
	if err := c.Close(); err != nil {
		t.Errorf("first Close: %v", err)
	}
	if err := c.Close(); err != nil {
		t.Errorf("second Close (should be no-op): %v", err)
	}
}

func TestCDPClosedClientRejects(t *testing.T) {
	m := newMockCDPServer(t, "ok")
	defer m.Close()
	c, _ := NewCDPClient(context.Background(), m.URL)
	c.Close()
	_, err := c.Evaluate(context.Background(), "1+1")
	if err == nil {
		t.Error("Evaluate on closed client should fail")
	}
}
