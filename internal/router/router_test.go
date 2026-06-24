package router

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/veawho/via54Medit/pkg/types"
)

// fakeSource implements source.SourceAdapter for tests.
type fakeSource struct {
	name    string
	enabled bool
	cites   []types.Citation
	err     error
	delay   time.Duration
}

func (f *fakeSource) Name() string  { return f.name }
func (f *fakeSource) Enabled() bool { return f.enabled }
func (f *fakeSource) Search(ctx context.Context, q types.EBMQuestion, limit int) ([]types.Citation, error) {
	if f.delay > 0 {
		select {
		case <-time.After(f.delay):
		case <-ctx.Done():
			return nil, ctx.Err()
		}
	}
	if f.err != nil {
		return nil, f.err
	}
	if limit > 0 && len(f.cites) > limit {
		return f.cites[:limit], nil
	}
	return f.cites, nil
}
func (f *fakeSource) Health(ctx context.Context) error { return nil }

func TestNewRouterDefaults(t *testing.T) {
	r := NewRouter()
	if r.Concurrency != 4 {
		t.Errorf("Concurrency = %d, want 4", r.Concurrency)
	}
	if r.TimeoutPerSource != 30*time.Second {
		t.Errorf("TimeoutPerSource = %v, want 30s", r.TimeoutPerSource)
	}
	if r.MaxRetries != 1 {
		t.Errorf("MaxRetries = %d, want 1", r.MaxRetries)
	}
}

func TestRouterFanOutDisabledSkipped(t *testing.T) {
	r := NewRouter()
	r.AddSource(&fakeSource{name: "off", enabled: false, cites: []types.Citation{{Title: "X"}}})
	r.AddSource(&fakeSource{name: "on", enabled: true, cites: []types.Citation{{Title: "Y"}}})
	_, used := r.fanOut(context.Background(), types.EBMQuestion{Query: "test"})
	if used["off"] != 0 {
		t.Errorf("off should be skipped, got used=%d", used["off"])
	}
	if used["on"] != 1 {
		t.Errorf("on should return 1, got used=%d", used["on"])
	}
}

func TestRouterFanOutAllSucceed(t *testing.T) {
	r := NewRouter()
	r.AddSource(&fakeSource{name: "a", enabled: true, cites: []types.Citation{{PMID: "1", Title: "T1"}}})
	r.AddSource(&fakeSource{name: "b", enabled: true, cites: []types.Citation{{PMID: "2", Title: "T2"}}})
	cites, used := r.fanOut(context.Background(), types.EBMQuestion{Query: "x"})
	if len(cites) != 2 {
		t.Errorf("got %d cites, want 2", len(cites))
	}
	if used["a"] != 1 || used["b"] != 1 {
		t.Errorf("used = %v", used)
	}
}

func TestRouterFanOutPartialFailure(t *testing.T) {
	r := NewRouter()
	r.AddSource(&fakeSource{name: "ok", enabled: true, cites: []types.Citation{{Title: "T"}}})
	r.AddSource(&fakeSource{name: "fail", enabled: true, err: errors.New("boom")})
	cites, used := r.fanOut(context.Background(), types.EBMQuestion{Query: "x"})
	if len(cites) != 1 {
		t.Errorf("got %d, want 1 (ok only)", len(cites))
	}
	if used["ok"] != 1 {
		t.Errorf("ok = %d, want 1", used["ok"])
	}
	if used["fail"] != 0 {
		t.Errorf("fail = %d, want 0", used["fail"])
	}
}

func TestRouterFanOutConcurrency(t *testing.T) {
	r := NewRouter()
	r.Concurrency = 2
	for i := 0; i < 4; i++ {
		r.AddSource(&fakeSource{
			name:    string(rune('a' + i)),
			enabled: true,
			cites:   []types.Citation{{Title: "T"}},
			delay:   100 * time.Millisecond,
		})
	}
	start := time.Now()
	_, _ = r.fanOut(context.Background(), types.EBMQuestion{Query: "x"})
	elapsed := time.Since(start)
	// 4 sources × 100ms with concurrency=2 → ~200ms total.
	// Allow generous slack for CI: 400ms upper bound.
	if elapsed > 400*time.Millisecond {
		t.Errorf("fanOut took %v, want ~200ms (concurrency=2)", elapsed)
	}
	if elapsed < 100*time.Millisecond {
		t.Errorf("fanOut took %v, want >=100ms (sources actually ran)", elapsed)
	}
}

func TestRouterFanOutTimeout(t *testing.T) {
	r := NewRouter()
	r.TimeoutPerSource = 50 * time.Millisecond
	r.MaxRetries = 0
	r.AddSource(&fakeSource{
		name:    "slow",
		enabled: true,
		delay:   200 * time.Millisecond, // longer than timeout
	})
	cites, used := r.fanOut(context.Background(), types.EBMQuestion{Query: "x"})
	if len(cites) != 0 {
		t.Errorf("got %d cites, want 0 (timeout)", len(cites))
	}
	if used["slow"] != 0 {
		t.Errorf("slow used = %d, want 0", used["slow"])
	}
}

func TestRouterFanOutRetry(t *testing.T) {
	// Source that fails first call, succeeds second.
	r := NewRouter()
	r.MaxRetries = 2
	counter := 0
	src := &retrySource{
		fakeSource: &fakeSource{name: "retry", enabled: true, cites: []types.Citation{{Title: "OK"}}},
		counter:    &counter,
	}
	r.AddSource(src)
	_, used := r.fanOut(context.Background(), types.EBMQuestion{Query: "x"})
	if used["retry"] != 1 {
		t.Errorf("retry used = %d, want 1 (eventually succeeded)", used["retry"])
	}
	if *src.counter < 2 {
		t.Errorf("expected ≥2 calls, got %d", *src.counter)
	}
}

// retrySource fails on the first call, succeeds after.
type retrySource struct {
	*fakeSource
	counter *int
}

func (r *retrySource) Search(ctx context.Context, q types.EBMQuestion, limit int) ([]types.Citation, error) {
	*r.counter++
	if *r.counter == 1 {
		return nil, errors.New("transient")
	}
	return r.fakeSource.Search(ctx, q, limit)
}

func TestRouterAskNoSources(t *testing.T) {
	r := NewRouter()
	ep, err := r.Ask(context.Background(), types.EBMQuestion{Query: "x"})
	if err != nil {
		t.Fatal(err)
	}
	if ep == nil {
		t.Fatal("got nil EvidencePackage")
	}
	if len(ep.Citations) != 0 {
		t.Errorf("got %d citations, want 0", len(ep.Citations))
	}
}

func TestRouterAskEndToEnd(t *testing.T) {
	r := NewRouter()
	r.Concurrency = 4
	r.TimeoutPerSource = 1 * time.Second
	r.AddSource(&fakeSource{
		name:    "pubmed",
		enabled: true,
		cites: []types.Citation{
			{PMID: "1", Title: "DAPA-HF"},
		},
	})
	r.AddSource(&fakeSource{
		name:    "openalex",
		enabled: true,
		cites: []types.Citation{
			{PMID: "1", Title: "DAPA-HF (OpenAlex mirror)", CitedBy: 200},
		},
	})
	ep, err := r.Ask(context.Background(), types.EBMQuestion{Query: "SGLT2"})
	if err != nil {
		t.Fatal(err)
	}
	if len(ep.Citations) != 1 {
		t.Errorf("got %d citations, want 1 (merged by PMID)", len(ep.Citations))
	}
	// The richer one (OpenAlex) should win.
	if ep.Citations[0].CitedBy != 200 {
		t.Errorf("CitedBy = %d, want 200 (OpenAlex richer)", ep.Citations[0].CitedBy)
	}
	if ep.SourcesUsed["pubmed"] != 1 || ep.SourcesUsed["openalex"] != 1 {
		t.Errorf("SourcesUsed = %v, want both = 1", ep.SourcesUsed)
	}
	if ep.ConvID == "" {
		t.Error("ConvID should be set")
	}
}

func TestRouterSummarizeWithoutLLM(t *testing.T) {
	r := NewRouter()
	cites := []types.Citation{
		{Title: "A"}, {Title: "B"}, {Title: "C"}, {Title: "D"},
	}
	got := r.summarize(context.Background(), cites)
	if got == "" {
		t.Error("summary should be non-empty")
	}
	if !contains(got, "A") {
		t.Errorf("summary should mention at least one title, got %q", got)
	}
}

func TestRouterSummarizeEmptyCites(t *testing.T) {
	r := NewRouter()
	got := r.summarize(context.Background(), nil)
	if got == "" {
		t.Error("summary should be non-empty even with no cites")
	}
}

func contains(s, sub string) bool {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
