// Package router implements the semantic router — the core of via54Medit.
//
// The router takes a natural language question, extracts PICO,
// classifies the EBM question type and user intent, plans a dispatch
// across multiple sources, fuses results, and returns an EvidencePackage.
package router

import (
	"context"
	"time"

	"github.com/veawho/via54Medit/pkg/types"
)

// Router is the main entry point.
type Router struct {
	// Phase 0: empty struct — Phase 2 wired with LLM + Registry + Pipeline
}

// NewRouter creates a router. Phase 0: no-op.
func NewRouter() *Router {
	return &Router{}
}

// Ask is the high-level entry: question → EvidencePackage.
//
// Phase 0: returns a stub package indicating the project is in skeleton.
func (r *Router) Ask(ctx context.Context, q types.EBMQuestion) (*types.EvidencePackage, error) {
	return &types.EvidencePackage{
		Question:    q,
		Citations:   []types.Citation{},
		Summary:     "[Phase 0] 骨架阶段 - Ask 流程尚未实现, 见 docs/ROADMAP.md Phase 2",
		Duration:    0,
		SourcesUsed: map[string]int{},
		CreatedAt:   time.Now(),
		ConvID:      "phase0-stub",
	}, nil
}

// Classify is a Phase 5 helper — classify a question into EBM type + intent.
// Phase 0: returns "unknown" stubs.
func (r *Router) Classify(q types.EBMQuestion) (ebmType, intent string) {
	return "unknown", "search"
}
