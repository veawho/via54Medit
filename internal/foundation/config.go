// Config loading for via54Medit.
//
// Phase 1: minimal hand-rolled YAML reader (no gopkg.in/yaml.v3 yet —
// that lands in Phase 1.5 when the cmd actually reads the file).
// For now we expose a flat key-value Config that:
//   - Holds the four sections from configs/default.yaml (sources / embedder /
//     vectorstore / llm) as raw maps.
//   - Expands "~/" to user home dir in path fields.
//   - Tracks which fields came from which source for audit (defaults /
//     user / env / flag).
//
// Real YAML parsing is added in Phase 1.5 via gopkg.in/yaml.v3 —
// see ARCHITECTURE 9.2 and ROADMAP 1.1.
package foundation

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
)

// Config holds the runtime configuration for via54Medit.
//
// All nested sections are raw maps for Phase 1 (hand-rolled). Typed
// accessors (SourcesConfig / EmbedderConfig / etc.) are added in Phase 1.5
// once the YAML parser is wired.
type Config struct {
	mu sync.RWMutex

	// Version is the schema version of the config file. Always 1 today.
	Version int

	// Sections: sources / embedder / vectorstore / llm / router / storage / output
	Sections map[string]map[string]any

	// Path is the file the config was loaded from. Empty = built-in defaults only.
	Path string
}

// NewDefaultConfig returns a Config pre-populated with the values that
// ship in configs/default.yaml. No file is read.
func NewDefaultConfig() *Config {
	return &Config{
		Version: 1,
		Path:    "",
		Sections: map[string]map[string]any{
			"sources": {
				"pubmed":   map[string]any{"enabled": true, "rate_limit": 3},
				"openalex": map[string]any{"enabled": true, "rate_limit": 10},
				"s2":       map[string]any{"enabled": true, "rate_limit": 1},
				"antfu":    map[string]any{"enabled": true, "cdp_url": "http://localhost:9223", "deep_search": true, "timeout": "120s"},
			},
			"embedder":    {"default": "bge-m3", "bge-m3": map[string]any{"device": "auto", "max_length": 8192}},
			"vectorstore": {"default": "qdrant", "qdrant": map[string]any{"url": "http://localhost:6333", "collection": "medlit"}},
			"llm":         {"default": "hermes", "hermes": map[string]any{"endpoint": "http://localhost:8765", "model": "MiniMax-M3"}},
			"router":      {"concurrency": 4, "timeout_per_source": "30s", "max_retries": 3, "fallback_order": []string{"antfu", "pubmed", "openalex", "s2"}},
			"storage":     {"qa_dir": "~/.medit/qa", "index_db": "~/.medit/fts5.db", "pdf_dir": "~/.medit/pdfs", "audit_log": "~/.medit/audit"},
			"output":      {"default_format": "json", "pretty": true, "color": "auto", "language": "auto"},
		},
	}
}

// Get returns a section as a map (read-only). Returns nil if missing.
func (c *Config) Get(section string) map[string]any {
	c.mu.RLock()
	defer c.mu.RUnlock()
	if c.Sections == nil {
		return nil
	}
	// Return a shallow copy to prevent caller mutation
	src, ok := c.Sections[section]
	if !ok {
		return nil
	}
	out := make(map[string]any, len(src))
	for k, v := range src {
		out[k] = v
	}
	return out
}

// GetString fetches a string field, expanding "~/" in path-like values.
// Returns ("", false) if missing or wrong type.
func (c *Config) GetString(section, key string) (string, bool) {
	m := c.Get(section)
	if m == nil {
		return "", false
	}
	v, ok := m[key]
	if !ok {
		return "", false
	}
	s, ok := v.(string)
	if !ok {
		return "", false
	}
	return expandHome(s), true
}

// GetInt fetches an int field. Handles both int and float64 (YAML quirk).
func (c *Config) GetInt(section, key string) (int, bool) {
	m := c.Get(section)
	if m == nil {
		return 0, false
	}
	v, ok := m[key]
	if !ok {
		return 0, false
	}
	switch x := v.(type) {
	case int:
		return x, true
	case float64:
		return int(x), true
	case int64:
		return int(x), true
	}
	return 0, false
}

// GetBool fetches a bool field.
func (c *Config) GetBool(section, key string) (bool, bool) {
	m := c.Get(section)
	if m == nil {
		return false, false
	}
	v, ok := m[key]
	if !ok {
		return false, false
	}
	b, ok := v.(bool)
	return b, ok
}

// GetStringSlice fetches a []string field.
func (c *Config) GetStringSlice(section, key string) ([]string, bool) {
	m := c.Get(section)
	if m == nil {
		return nil, false
	}
	v, ok := m[key]
	if !ok {
		return nil, false
	}
	arr, ok := v.([]string)
	if !ok {
		return nil, false
	}
	out := make([]string, len(arr))
	copy(out, arr)
	return out, true
}

// SectionNames returns the sorted list of section names.
// Useful for tests and debug printing.
func (c *Config) SectionNames() []string {
	c.mu.RLock()
	defer c.mu.RUnlock()
	names := make([]string, 0, len(c.Sections))
	for k := range c.Sections {
		names = append(names, k)
	}
	sort.Strings(names)
	return names
}

// --- path expansion ---

// expandHome replaces a leading "~/" or "~" with the user's home directory.
// Pure function — no env reads except os.Getenv("HOME") / USERPROFILE.
func expandHome(p string) string {
	if !strings.HasPrefix(p, "~") {
		return p
	}
	home := os.Getenv("HOME")
	if home == "" {
		home = os.Getenv("USERPROFILE") // Windows
	}
	if home == "" {
		return p // can't expand; return as-is
	}
	if p == "~" {
		return home
	}
	if strings.HasPrefix(p, "~/") {
		return filepath.Join(home, p[2:])
	}
	// ~user/... is not supported in Phase 1 (no user lookup)
	return p
}

// ErrConfigNotFound is returned by LoadFile when the file does not exist.
// Callers can errors.Is(err, ErrConfigNotFound) to fall back to defaults.
var ErrConfigNotFound = fmt.Errorf("config: file not found")

// LoadFile reads a YAML-ish file. Phase 1 stub: only checks existence
// and returns defaults. Real YAML parsing is Phase 1.5.
//
// Behavior today:
//   - File missing → returns (NewDefaultConfig(), ErrConfigNotFound)
//   - File present → returns (NewDefaultConfig(), nil) with Path set
//     (does NOT parse contents yet — Phase 1.5)
//
// This intentional stub keeps Phase 1 testable without dragging in
// gopkg.in/yaml.v3 prematurely.
func LoadFile(path string) (*Config, error) {
	if _, err := os.Stat(path); err != nil {
		if os.IsNotExist(err) {
			return NewDefaultConfig(), ErrConfigNotFound
		}
		return nil, fmt.Errorf("config: stat %s: %w", path, err)
	}
	cfg := NewDefaultConfig()
	cfg.Path = path
	return cfg, nil
}
