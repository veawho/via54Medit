// Package router is the heart of via54Medit: it takes a natural language
// question, fans out to 4 sources concurrently, deduplicates results,
// and produces an EvidencePackage with citations and an optional LLM
// summary.
//
// Design (Phase 2):
//
//	[1] User query → types.EBMQuestion
//	[2] Router.Ask fans out to N sources (pubmed, openalex, s2, antfu)
//	    concurrently with a per-source timeout + 3-retry exponential backoff
//	[3] Partial results: each source's response (success or error) is
//	    collected independently; a failing source doesn't block the others
//	[4] internal/dedupe.Dedupe merges duplicates by PMID/DOI/simhash
//	[5] (optional) LLM summarizes the top-N citations
//	[6] Return types.EvidencePackage
package router

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/veawho/via54Medit/internal/dedupe"
	"github.com/veawho/via54Medit/internal/foundation"
	"github.com/veawho/via54Medit/internal/source"
	"github.com/veawho/via54Medit/pkg/types"
)

// Router fans out queries to multiple SourceAdapters.
type Router struct {
	// Sources is the set of adapters to query. Add/remove via Register.
	Sources []source.SourceAdapter

	// LLM is the optional summarizer. If nil, summary is just the
	// first citation's title (no LLM call).
	LLM foundation.LLMProvider

	// Concurrency limits the number of sources queried in parallel.
	// 0 = len(Sources) (all at once).
	Concurrency int

	// TimeoutPerSource is the per-source deadline.
	TimeoutPerSource time.Duration

	// MaxRetries per source.
	MaxRetries int
}

// NewRouter returns a router with sensible defaults.
func NewRouter() *Router {
	return &Router{
		Concurrency:      4,
		TimeoutPerSource: 30 * time.Second,
		MaxRetries:       1, // first attempt + 1 retry = 2 total
	}
}

// AddSource appends a source adapter to the router.
func (r *Router) AddSource(s source.SourceAdapter) {
	r.Sources = append(r.Sources, s)
}

// Ask is the high-level entry point. It fans out to all registered
// sources concurrently, deduplicates, optionally summarizes, and
// returns an EvidencePackage.
func (r *Router) Ask(ctx context.Context, q types.EBMQuestion) (*types.EvidencePackage, error) {
	start := time.Now()

	cites, sourcesUsed := r.fanOut(ctx, q)
	merged := dedupe.Dedupe(cites)

	summary := ""
	if r.LLM != nil {
		summary = r.summarize(ctx, merged)
	} else {
		summary = "[Phase 2] no LLM configured — citation list only"
	}

	ep := &types.EvidencePackage{
		Question:    q,
		Citations:   merged,
		Summary:     summary,
		Duration:    time.Since(start),
		SourcesUsed: sourcesUsed,
		CreatedAt:   time.Now(),
		ConvID:      fmt.Sprintf("conv-%d", start.UnixNano()),
	}
	return ep, nil
}

// fanOut dispatches the query to all enabled sources concurrently.
// Returns the merged citations and a per-source success/failure map.
func (r *Router) fanOut(ctx context.Context, q types.EBMQuestion) ([]types.Citation, map[string]int) {
	enabled := make([]source.SourceAdapter, 0, len(r.Sources))
	for _, s := range r.Sources {
		if s.Enabled() {
			enabled = append(enabled, s)
		}
	}

	concurrency := r.Concurrency
	if concurrency <= 0 || concurrency > len(enabled) {
		concurrency = len(enabled)
	}
	if concurrency == 0 {
		return nil, map[string]int{}
	}

	sem := make(chan struct{}, concurrency)
	results := make(chan sourceResult, len(enabled))
	var wg sync.WaitGroup

	for _, s := range enabled {
		wg.Add(1)
		sem <- struct{}{}
		go func(s source.SourceAdapter) {
			defer wg.Done()
			defer func() { <-sem }()
			cites, err := r.callOne(ctx, s, q)
			results <- sourceResult{source: s.Name(), cites: cites, err: err}
		}(s)
	}

	wg.Wait()
	close(results)

	allCites := make([]types.Citation, 0)
	used := map[string]int{}
	for r := range results {
		if r.err == nil {
			allCites = append(allCites, r.cites...)
			used[r.source] = len(r.cites)
		} else {
			used[r.source] = 0
		}
	}
	return allCites, used
}

// callOne invokes a single source with per-source timeout + retry.
func (r *Router) callOne(ctx context.Context, s source.SourceAdapter, q types.EBMQuestion) ([]types.Citation, error) {
	timeout := r.TimeoutPerSource
	if timeout <= 0 {
		timeout = 30 * time.Second
	}
	maxRetries := r.MaxRetries
	if maxRetries < 0 {
		maxRetries = 0
	}
	limit := q.MaxResults
	if limit <= 0 {
		limit = 20
	}

	var lastErr error
	for attempt := 0; attempt <= maxRetries; attempt++ {
		if attempt > 0 {
			// Exponential backoff: 500ms, 1s, 2s...
			backoff := time.Duration(1<<uint(attempt-1)) * 500 * time.Millisecond
			select {
			case <-ctx.Done():
				return nil, ctx.Err()
			case <-time.After(backoff):
			}
		}
		callCtx, cancel := context.WithTimeout(ctx, timeout)
		cites, err := s.Search(callCtx, q, limit)
		cancel()
		if err == nil {
			return cites, nil
		}
		lastErr = err
	}
	return nil, fmt.Errorf("%s: %w", s.Name(), lastErr)
}

// summarize asks the LLM to produce a brief EBM-style summary of the
// top citations. If the LLM call fails, the summary degrades to a
// truncated citation list.
func (r *Router) summarize(ctx context.Context, cites []types.Citation) string {
	if len(cites) == 0 {
		return "[Phase 2] no citations found"
	}
	if r.LLM == nil {
		// Truncate to first 3 titles.
		n := len(cites)
		if n > 3 {
			n = 3
		}
		out := "Top results:\n"
		for i := 0; i < n; i++ {
			out += fmt.Sprintf("  - %s\n", cites[i].Title)
		}
		return out
	}

	// Build prompt: top 10 citations → EBM summary.
	prompt := "You are an EBM assistant. Given the following medical literature " +
		"results, produce a 3-5 sentence summary highlighting the most relevant findings.\n\n"
	n := len(cites)
	if n > 10 {
		n = 10
	}
	for i := 0; i < n; i++ {
		prompt += fmt.Sprintf("[%d] %s (%d)\n", i+1, cites[i].Title, cites[i].Year)
	}
	prompt += "\nSummary:"

	summary, err := r.LLM.Complete(ctx,
		"你是一个循证医学助手, 用简洁准确的语言总结证据。",
		prompt,
	)
	if err != nil {
		return fmt.Sprintf("[Phase 2] LLM summary failed: %v", err)
	}
	return summary
}

// sourceResult is the per-source result envelope.
type sourceResult struct {
	source string
	cites  []types.Citation
	err    error
}
