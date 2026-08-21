// End-to-end pipeline: Brief → Research → Analyze → Outline (per
// audience) → Compliance → persist + render. Each stage degrades
// independently (LLM down ⇒ template outline; searcher down ⇒ logged
// empty literature) so `run` always produces a reviewable deliverable.
package medplan

import (
	"context"
	"fmt"
	"log/slog"
	"time"
)

// Pipeline wires the stage implementations together.
type Pipeline struct {
	Researcher *Researcher
	Analyzer   *Analyzer
	Generator  *Generator
	Optimizer  *Optimizer // optional (nil ⇒ optimize stage unavailable)
	Checker    *ComplianceChecker
	Store      *ProjectStore
	Log        *slog.Logger
}

// RunOptions controls one pipeline execution.
type RunOptions struct {
	Brief *Brief
	// Audiences overrides Brief.Audiences when non-empty.
	Audiences []Audience
	// SkipResearch reuses the persisted research.json when present.
	SkipResearch bool
	// SkipCompliance disables the compliance stage.
	SkipCompliance bool
}

// RunResult aggregates every stage artifact.
type RunResult struct {
	Brief      *Brief
	Dossier    *ResearchDossier
	Insights   *Insights
	Outlines   map[Audience]*StrategyOutline
	Compliance map[Audience]*ComplianceReport
	Duration   time.Duration
}

// Run executes the full pipeline and persists every artifact.
func (p *Pipeline) Run(ctx context.Context, opts RunOptions) (*RunResult, error) {
	if p == nil || p.Store == nil {
		return nil, fmt.Errorf("medplan: pipeline requires a store")
	}
	log := p.log()
	start := nowUTC()
	res := &RunResult{
		Outlines:   map[Audience]*StrategyOutline{},
		Compliance: map[Audience]*ComplianceReport{},
	}

	brief := opts.Brief
	if brief == nil {
		return nil, fmt.Errorf("medplan: run: nil brief")
	}
	if len(opts.Audiences) > 0 {
		brief.Audiences = opts.Audiences
	}
	if len(brief.Audiences) == 0 {
		brief.Audiences = AllAudiences()
	}
	if brief.CreatedAt.IsZero() {
		brief.CreatedAt = nowUTC()
	}
	if err := p.Store.SaveBrief(brief); err != nil {
		return nil, err
	}
	res.Brief = brief
	log.Info("brief saved", "project", brief.Project, "audiences", len(brief.Audiences))

	// --- Research ---
	if opts.SkipResearch {
		if d, err := p.Store.LoadResearch(brief.Project); err == nil {
			res.Dossier = d
			log.Info("research reused", "items", len(d.Items))
		}
	}
	if res.Dossier == nil {
		if p.Researcher == nil {
			return nil, fmt.Errorf("medplan: pipeline requires a researcher")
		}
		d, err := p.Researcher.Research(ctx, brief)
		if err != nil {
			return nil, fmt.Errorf("research: %w", err)
		}
		res.Dossier = d
		log.Info("research done", "items", len(d.Items), "queries", len(d.Queries))
	}
	if err := p.Store.SaveResearch(res.Dossier); err != nil {
		return nil, err
	}

	// --- Analyze ---
	if p.Analyzer == nil {
		return nil, fmt.Errorf("medplan: pipeline requires an analyzer")
	}
	ins, err := p.Analyzer.Analyze(ctx, brief, res.Dossier)
	if err != nil {
		return nil, fmt.Errorf("analyze: %w", err)
	}
	res.Insights = ins
	if err := p.Store.SaveInsights(ins); err != nil {
		return nil, err
	}
	log.Info("insights extracted", "count", len(ins.Insights))

	// --- Outline + Compliance per audience ---
	if p.Generator == nil {
		return nil, fmt.Errorf("medplan: pipeline requires a generator")
	}
	for _, a := range brief.Audiences {
		o, err := p.Generator.Generate(ctx, brief, res.Dossier, ins, a)
		if err != nil {
			log.Warn("outline generation degraded", "audience", string(a), "err", err.Error())
		}
		if o == nil {
			return nil, fmt.Errorf("outline(%s): no output", a)
		}
		res.Outlines[a] = o
		if err := p.Store.SaveOutline(o); err != nil {
			return nil, err
		}

		if !opts.SkipCompliance && p.Checker != nil {
			rep, err := p.Checker.Check(ctx, o, brief.Product)
			if err != nil {
				return nil, fmt.Errorf("compliance(%s): %w", a, err)
			}
			res.Compliance[a] = rep
			if err := p.Store.SaveCompliance(rep); err != nil {
				return nil, err
			}
			log.Info("compliance checked", "audience", string(a), "verdict", rep.Verdict,
				"fatal", rep.CountsBySeverity()[SevFatal])
		}

		md := RenderMarkdown(o, RenderOptions{
			Dossier:    res.Dossier,
			Insights:   ins,
			Compliance: res.Compliance[a],
			Brief:      brief,
		})
		if err := p.Store.WriteMarkdown(brief.Project, a, md); err != nil {
			return nil, err
		}
	}

	res.Duration = time.Since(start)
	return res, nil
}

func (p *Pipeline) log() *slog.Logger {
	if p.Log != nil {
		return p.Log
	}
	return slog.Default()
}
