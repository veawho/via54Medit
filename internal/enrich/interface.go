// Package enrich enriches citations with metadata from secondary sources.
//
// The default enrichers are: PubMed (PMID/MeSH), OpenAlex (FWCI/cited_by),
// Semantic Scholar (TLDR/FWCI).
package enrich

import (
	"context"

	"github.com/veawho/via54Medit/pkg/types"
)

// Enricher fetches additional metadata for a citation.
//
// Enrichers are idempotent and may run concurrently per citation.
type Enricher interface {
	// Name identifies this enricher (e.g., "pubmed_meta").
	Name() string

	// Enrich adds fields to c in place.
	// Returns the same slice (or modified copy) plus optional error.
	// Partial enrichment is acceptable; the error indicates non-fatal issues.
	Enrich(ctx context.Context, c *types.Citation) error
}

// Pipeline runs multiple enrichers in sequence.
type Pipeline struct {
	enrichers []Enricher
}

// NewPipeline creates an enricher pipeline.
func NewPipeline(enrichers ...Enricher) *Pipeline {
	return &Pipeline{enrichers: enrichers}
}

// Run applies every enricher to every citation concurrently.
//
// On error, the citation is kept (with partial enrichment) and the
// error is logged in c.EnrichmentLog.
func (p *Pipeline) Run(ctx context.Context, citations []types.Citation) []types.Citation {
	// Phase 0: stub — Phase 2 实际实现
	return citations
}
