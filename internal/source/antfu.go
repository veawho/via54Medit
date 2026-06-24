// Antfu (蚂蚁阿福) adapter — Phase 1 STUB.
//
// The real adapter (Phase 1.5) will drive a Chrome instance via DevTools
// Protocol (CDP) at http://localhost:9223, navigate to chat.antafu.com,
// inject the query, wait ~48s for the RAG response, and extract
// references from the quoted-materials panel.
//
// Phase 1 ships the registry entry + the public method signatures so:
//  1. The router (Phase 2) can wire antfu into its 4-source fan-out
//     without crashing — the call just returns a clear "not implemented" error.
//  2. The CLI subcommand `medit antfu ask` can be wired to a friendly message
//     rather than a nil pointer dereference.
//
// To enable the real implementation, set `antfu.enabled: true` in
// ~/.medit/config.yaml AND set `antfu.cdp_url` to a running Chrome
// with `--remote-debugging-port=9223`.
//
// Why this is a stub: the CDP client (gorilla/websocket) requires
// running Chrome with a user-data-dir, and 48s RAG waits make e2e
// tests slow + flaky. Phase 1.5 will ship:
//   - internal/source/antfu_cdp.go (websocket + Page.navigate)
//   - internal/source/antfu_extract.go (goquery parse of quotedMaterials)
//   - tests/e2e/antfu_e2e.sh (requires real Chrome)
package source

import (
	"context"
	"fmt"
	"time"

	"github.com/veawho/via54Medit/pkg/types"
)

// AntfuSource is the Phase 1 stub. Real implementation lands in Phase 1.5.
type AntfuSource struct {
	cdpURL     string
	deepSearch bool
	timeout    time.Duration
	enabled    bool
}

// NewAntfuSource builds the antfu adapter. Even with enabled=true the
// search call returns an error in Phase 1 — see package doc.
func NewAntfuSource(cfg map[string]any) (*AntfuSource, error) {
	s := &AntfuSource{
		cdpURL:     "http://localhost:9223",
		deepSearch: true,
		timeout:    60 * time.Second,
		enabled:    true,
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

// Search returns a "not implemented" error in Phase 1. The router treats
// this like any other source error: log + continue with partial results.
func (s *AntfuSource) Search(ctx context.Context, q types.EBMQuestion, limit int) ([]types.Citation, error) {
	if !s.enabled {
		return nil, fmt.Errorf("antfu: source is disabled")
	}
	return nil, fmt.Errorf("antfu: Phase 1.5 not implemented yet — needs Chrome 9223 + CDP client. " +
		"See internal/source/antfu.go package doc for the enablement checklist")
}

// Health returns a clear Phase-1 message rather than faking a healthy
// response. The router's pre-flight check will surface this to the user.
func (s *AntfuSource) Health(ctx context.Context) error {
	return fmt.Errorf("antfu: Phase 1.5 not implemented yet — would check %s", s.cdpURL)
}
