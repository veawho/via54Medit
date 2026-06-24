package source

import (
	"encoding/json"
	"net/http"
	"strings"

	"github.com/gorilla/websocket"
)

// handleMockAntfuWS is a mock WebSocket handler that emulates the antfu
// chat page for unit tests. It responds to Page.navigate with success,
// to Runtime.evaluate calls with a canned HTML body for
// `document.documentElement.outerHTML` and a simple OK for everything
// else.
//
// Phase 1.5: this mock is intentionally minimal — full happy-path E2E
// requires a real Chrome and is in antfu_e2e_test.go (gated by env).
func handleMockAntfuWS(w http.ResponseWriter, r *http.Request, htmlBody string) {
	upgrader := websocket.Upgrader{CheckOrigin: func(r *http.Request) bool { return true }}
	conn, err := upgrader.Upgrade(w, r, nil)
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
			_ = conn.WriteJSON(map[string]any{
				"id":     req.ID,
				"result": map[string]any{},
			})
			_ = conn.WriteJSON(map[string]any{"method": "Page.loadEventFired"})
		case "Runtime.evaluate":
			var p struct {
				Expression string `json:"expression"`
			}
			_ = json.Unmarshal(req.Params, &p)
			// If asking for outerHTML, return the canned body; else echo.
			var value string
			if strings.Contains(p.Expression, "outerHTML") {
				value = htmlBody
			} else {
				value = "OK"
			}
			_ = conn.WriteJSON(map[string]any{
				"id": req.ID,
				"result": map[string]any{
					"type":  "string",
					"value": value,
				},
			})
		}
	}
}

// jsonEncodeImpl is a small wrapper so we don't have to import encoding/json
// in tests that only need a one-liner.
func jsonEncodeImpl(w http.ResponseWriter, v any) error {
	return json.NewEncoder(w).Encode(v)
}
