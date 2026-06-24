// Package router - GRADE evidence rating (simplified, Phase 3).
//
// GRADE = Grading of Recommendations Assessment, Development and
// Evaluation. Full GRADE requires Cochrane RoB 2.0 assessment, GRADEpro
// software, and per-outcome expert judgment — out of scope for Phase 3.
//
// Per ARCHITECTURE §19 #3 (Phase 0 拍板), we ship the SIMPLIFIED
// version that the user picked. Phase 3.0 algorithm:
//
//	score = (n_citations ≥ 5 ? +2 : +1)
//	      + (multi_source_count ≥ 3 ? +2 : 0)
//	      + (RCT_ratio ≥ 0.5 ? +2 : 0)
//	      + (recency ≥ 3yr ? +1 : 0)
//
//	grade = A if score 6-7, B if 4-5, C if 2-3, D if 0-1
//
// RCT detection is heuristic (Phase 3.5 will add a proper classifier).
// We use the title/abstract keywords "randomized", "placebo", "RCT",
// "随机" (Chinese for "random").
//
// Phase 3.5 (v0.5) may upgrade to a real Cochrane RoB 2.0 + GRADEpro
// workflow. Until then, this is the canonical implementation.
package router

import (
	"fmt"
	"strings"
	"time"

	"github.com/veawho/via54Medit/pkg/types"
)

// GradeResult is the output of Grade().
type GradeResult struct {
	GRADE      string // "A" | "B" | "C" | "D"
	Score      int    // 0-7
	Reasoning  string // human-readable
	NCitations int
	NSources   int
	RCTRatio   float64 // 0-1
	RecencyOK  bool
}

// Grade computes the simplified GRADE rating for an EvidencePackage.
func Grade(ep *types.EvidencePackage) GradeResult {
	if ep == nil || len(ep.Citations) == 0 {
		return GradeResult{
			GRADE:     "D",
			Reasoning: "no citations to grade",
		}
	}

	n := len(ep.Citations)
	sources := map[string]bool{}
	rctCount := 0
	now := time.Now()
	recentCount := 0

	for _, c := range ep.Citations {
		for _, s := range c.SourceOrigin {
			sources[s] = true
		}
		if isRCT(c) {
			rctCount++
		}
		// Recency: prefer citations within last 3 years.
		if c.Year > 0 && now.Year()-c.Year <= 3 {
			recentCount++
		}
	}

	rctRatio := float64(rctCount) / float64(n)

	score := 0
	reasons := []string{}

	// 1. Citation count
	if n >= 5 {
		score += 2
		reasons = append(reasons, fmt.Sprintf("citation count %d (≥5)", n))
	} else {
		score += 1
		reasons = append(reasons, fmt.Sprintf("citation count %d (<5)", n))
	}

	// 2. Multi-source
	ns := len(sources)
	if ns >= 3 {
		score += 2
		reasons = append(reasons, fmt.Sprintf("%d sources (≥3)", ns))
	} else if ns >= 2 {
		score += 1
		reasons = append(reasons, fmt.Sprintf("%d sources (2)", ns))
	} else {
		reasons = append(reasons, fmt.Sprintf("only %d source (insufficient)", ns))
	}

	// 3. RCT ratio
	if rctRatio >= 0.5 {
		score += 2
		reasons = append(reasons, fmt.Sprintf("RCT ratio %.0f%% (≥50%%)", rctRatio*100))
	} else if rctRatio >= 0.25 {
		score += 1
		reasons = append(reasons, fmt.Sprintf("RCT ratio %.0f%% (25-50%%)", rctRatio*100))
	} else {
		reasons = append(reasons, fmt.Sprintf("RCT ratio %.0f%% (<25%%)", rctRatio*100))
	}

	// 4. Recency
	recencyOK := recentCount > 0
	if recencyOK {
		score++
		reasons = append(reasons, fmt.Sprintf("recent: %d/%d within 3yr", recentCount, n))
	} else {
		reasons = append(reasons, "no recent citations (within 3yr)")
	}

	grade := scoreToGrade(score)

	return GradeResult{
		GRADE:      grade,
		Score:      score,
		Reasoning:  strings.Join(reasons, "; "),
		NCitations: n,
		NSources:   ns,
		RCTRatio:   rctRatio,
		RecencyOK:  recencyOK,
	}
}

func scoreToGrade(score int) string {
	switch {
	case score >= 6:
		return "A"
	case score >= 4:
		return "B"
	case score >= 2:
		return "C"
	default:
		return "D"
	}
}

// isRCT uses a heuristic to flag a citation as a randomized
// controlled trial. Phase 3.5 may add a proper classifier.
func isRCT(c types.Citation) bool {
	// Combine title + abstract + journal for matching.
	haystack := strings.ToLower(c.Title + " " + c.Abstract + " " + c.Journal)
	keywords := []string{
		"randomized", "randomised", "randomly assigned",
		"placebo-controlled", "double-blind",
		"rct", "controlled trial",
		"随机", "安慰剂", "对照",
	}
	for _, k := range keywords {
		if strings.Contains(haystack, k) {
			return true
		}
	}
	return false
}
