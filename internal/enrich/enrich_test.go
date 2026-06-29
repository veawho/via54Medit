package enrich

import (
	"context"
	"testing"

	"github.com/veawho/via54Medit/pkg/types"
)

func TestPipelineEmpty(t *testing.T) {
	p := NewPipeline()
	out := p.Run(context.Background(), nil, false)
	if out != nil {
		t.Errorf("got %v, want nil", out)
	}
	out = p.Run(context.Background(), []types.Citation{}, false)
	if len(out) != 0 {
		t.Errorf("got %d, want 0", len(out))
	}
}

func TestPipelineNoEnrichers(t *testing.T) {
	p := NewPipeline() // no enrichers
	cites := []types.Citation{{Title: "T"}}
	out := p.Run(context.Background(), cites, false)
	if len(out) != 1 {
		t.Errorf("got %d, want 1 (no-op)", len(out))
	}
}

func TestOpenAlexEnricherSkipsEmptyDOI(t *testing.T) {
	e := NewOpenAlexEnricher()
	c := &types.Citation{Title: "X"}
	actions, err := e.Enrich(context.Background(), c, false)
	if err != nil {
		t.Fatal(err)
	}
	if len(actions) > 0 {
		t.Errorf("expected no actions for empty DOI/PMID, got %v", actions)
	}
}

func TestOpenAlexEnricherSkipsAlreadyEnriched(t *testing.T) {
	e := NewOpenAlexEnricher()
	c := &types.Citation{DOI: "10.1/x", FWCI: 5.0, CitedBy: 100}
	actions, err := e.Enrich(context.Background(), c, false)
	if err != nil {
		t.Fatal(err)
	}
	if len(actions) > 0 {
		t.Errorf("expected no actions (already enriched), got %v", actions)
	}
}

func TestS2EnricherSkipsEmptyDOI(t *testing.T) {
	e := NewS2Enricher()
	c := &types.Citation{Title: "X"}
	actions, _ := e.Enrich(context.Background(), c, false)
	if len(actions) > 0 {
		t.Errorf("expected no actions, got %v", actions)
	}
}

func TestS2EnricherSkipsAlreadyEnriched(t *testing.T) {
	e := NewS2Enricher()
	c := &types.Citation{DOI: "10.1/x", TLDR: "Already have one"}
	actions, _ := e.Enrich(context.Background(), c, false)
	if len(actions) > 0 {
		t.Errorf("expected no actions, got %v", actions)
	}
}

func TestPubMedEnricherSkipsEmptyPMID(t *testing.T) {
	e := NewPubMedEnricher()
	c := &types.Citation{Title: "X"}
	actions, _ := e.Enrich(context.Background(), c, false)
	if len(actions) > 0 {
		t.Errorf("expected no actions, got %v", actions)
	}
}

func TestPubMedEnricherSkipsAlreadyEnriched(t *testing.T) {
	e := NewPubMedEnricher()
	c := &types.Citation{PMID: "1", MeSH: []string{"X"}}
	actions, _ := e.Enrich(context.Background(), c, false)
	if len(actions) > 0 {
		t.Errorf("expected no actions, got %v", actions)
	}
}

func TestPipelineDoesNotMutateInput(t *testing.T) {
	p := NewPipeline()
	orig := []types.Citation{{Title: "T1"}, {Title: "T2"}}
	out := p.Run(context.Background(), orig, false)
	if len(out) != 2 {
		t.Fatalf("got %d, want 2", len(out))
	}
	// The input should be unchanged (even with no enrichers).
	if orig[0].EnrichmentLog != nil {
		t.Errorf("input should be untouched, got EnrichmentLog: %v", orig[0].EnrichmentLog)
	}
}

func TestPipelineParallelSafety(t *testing.T) {
	// Run 50 citations through 3 enrichers; verify no data race.
	// (Go -race will catch this.)
	p := NewPipeline(
		NewOpenAlexEnricher(),
		NewS2Enricher(),
		NewPubMedEnricher(),
	)
	cites := make([]types.Citation, 50)
	for i := range cites {
		cites[i] = types.Citation{Title: "T"}
	}
	p.Run(context.Background(), cites, false)
}

func TestPipelineAdd(t *testing.T) {
	p := NewPipeline()
	p.Add(NewOpenAlexEnricher())
	if len(p.enrichers) != 1 {
		t.Errorf("got %d, want 1", len(p.enrichers))
	}
}

func TestJSON(t *testing.T) {
	p := NewPipeline()
	cites := []types.Citation{{Title: "T1"}, {Title: "T2"}}
	s, err := p.JSON(cites)
	if err != nil {
		t.Fatal(err)
	}
	if s == "" {
		t.Error("got empty JSON")
	}
	if s[0] != '[' {
		t.Errorf("expected JSON array, got: %s...", s[:20])
	}
}
