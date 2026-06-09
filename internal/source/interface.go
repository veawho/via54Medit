// Package source defines the SourceAdapter interface and the 4
// built-in implementations (PubMed, OpenAlex, Semantic Scholar, Antfu).
//
// All sources return []types.Citation. The router deduplicates and ranks.
package source

import (
	"context"

	"github.com/veawho/via54Medit/pkg/types"
)

// SourceAdapter is the contract every literature source must implement.
//
// Implementations should be:
//   - Concurrent-safe (multiple goroutines may share an instance)
//   - Resilient (return partial results + error rather than panic)
//   - Rate-limited (use internal token bucket per source config)
//   - Traceable (log every query to audit log)
type SourceAdapter interface {
	// Name returns the unique source identifier (e.g., "pubmed").
	Name() string

	// Enabled returns whether the source is configured active.
	Enabled() bool

	// Search performs a query and returns up to limit citations.
	//
	// Implementations should:
	//   - Apply PICO when provided
	//   - Respect TimeRange
	//   - Apply source-specific Filters
	//   - Set SourceOrigin to []string{s.Name()}
	//   - Return partial results on timeout (don't fail wholesale)
	Search(ctx context.Context, q types.EBMQuestion, limit int) ([]types.Citation, error)

	// Health checks the source is reachable.
	// Used by the router's pre-flight check.
	Health(ctx context.Context) error
}

// Registry holds the configured source adapters.
type Registry struct {
	sources map[string]SourceAdapter
}

// NewRegistry creates an empty registry.
func NewRegistry() *Registry {
	return &Registry{sources: make(map[string]SourceAdapter)}
}

// Register adds a source to the registry.
func (r *Registry) Register(s SourceAdapter) {
	r.sources[s.Name()] = s
}

// Get retrieves a source by name. Returns nil if not found.
func (r *Registry) Get(name string) SourceAdapter {
	return r.sources[name]
}

// All returns all registered sources.
func (r *Registry) All() []SourceAdapter {
	out := make([]SourceAdapter, 0, len(r.sources))
	for _, s := range r.sources {
		out = append(out, s)
	}
	return out
}

// Enabled returns only enabled sources.
func (r *Registry) Enabled() []SourceAdapter {
	out := make([]SourceAdapter, 0)
	for _, s := range r.sources {
		if s.Enabled() {
			out = append(out, s)
		}
	}
	return out
}
