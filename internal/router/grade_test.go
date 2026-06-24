package router

import (
	"strings"
	"testing"
	"time"

	"github.com/veawho/via54Medit/pkg/types"
)

func TestGradeNilOrEmpty(t *testing.T) {
	if g := Grade(nil); g.GRADE != "D" {
		t.Errorf("Grade(nil) = %q, want D", g.GRADE)
	}
	ep := &types.EvidencePackage{}
	if g := Grade(ep); g.GRADE != "D" {
		t.Errorf("Grade(empty) = %q, want D", g.GRADE)
	}
}

func TestGradeSingleCitation(t *testing.T) {
	ep := &types.EvidencePackage{
		Citations: []types.Citation{
			{Title: "DAPA-HF", Year: 2019, SourceOrigin: []string{"pubmed"}},
		},
	}
	g := Grade(ep)
	// n=1 (+1), 1 source (+0), 0% RCT (+0), no recency (+0) → score 1 → D
	if g.GRADE != "D" {
		t.Errorf("grade = %q, want D (score=%d)", g.GRADE, g.Score)
	}
}

func TestGradeHighQuality(t *testing.T) {
	now := time.Now().Year()
	cites := make([]types.Citation, 6)
	for i := range cites {
		cites[i] = types.Citation{
			Title:        "Randomized controlled trial of drug X",
			Year:         now,
			SourceOrigin: []string{"pubmed", "openalex", "s2"},
			Journal:      "NEJM",
		}
	}
	ep := &types.EvidencePackage{Citations: cites}
	g := Grade(ep)
	// n=6 (+2), 3 sources (+2), 100% RCT (+2), recent (+1) → score 7 → A
	if g.GRADE != "A" {
		t.Errorf("grade = %q, want A (score=%d, reasoning=%q)", g.GRADE, g.Score, g.Reasoning)
	}
}

func TestGradeMediumQuality(t *testing.T) {
	now := time.Now().Year()
	cites := []types.Citation{
		{Title: "Randomized trial", Year: now, SourceOrigin: []string{"pubmed", "openalex"}},
		{Title: "Another RCT", Year: now, SourceOrigin: []string{"pubmed"}},
		{Title: "Observational study", Year: now - 2, SourceOrigin: []string{"openalex"}},
		{Title: "Case series", Year: now - 5, SourceOrigin: []string{"s2"}},
	}
	ep := &types.EvidencePackage{Citations: cites}
	g := Grade(ep)
	// n=4 (+1), 3 sources (+2), 50% RCT (+2), recent ≥1 (+1) → score 6 → A
	// Or if n=4 then 1; sources 3 (+2), RCT 2/4=50% (+2), recent 2 (+1) → 6
	if g.GRADE != "A" && g.GRADE != "B" {
		t.Errorf("grade = %q (score=%d, reasoning=%q), want A or B",
			g.GRADE, g.Score, g.Reasoning)
	}
}

func TestGradeChineseRCTDetection(t *testing.T) {
	cites := []types.Citation{
		{Title: "随机对照试验", Year: 2024, SourceOrigin: []string{"pubmed"}},
	}
	ep := &types.EvidencePackage{Citations: cites}
	g := Grade(ep)
	if g.RCTRatio != 1.0 {
		t.Errorf("RCTRatio = %f, want 1.0 (Chinese RCT detected)", g.RCTRatio)
	}
}

func TestIsRCT(t *testing.T) {
	cases := []struct {
		title string
		want  bool
	}{
		{"A randomized controlled trial of aspirin", true},
		{"Randomised double-blind study", true},
		{"Placebo-controlled trial", true},
		{"观察性研究 (Observational study)", false},
		{"A systematic review", false},
		{"Random sample survey", false},
		{"随机双盲试验", true},
		{"", false},
	}
	for _, c := range cases {
		got := isRCT(types.Citation{Title: c.title})
		if got != c.want {
			t.Errorf("isRCT(%q) = %v, want %v", c.title, got, c.want)
		}
	}
}

func TestScoreToGrade(t *testing.T) {
	cases := []struct {
		score int
		want  string
	}{
		{0, "D"},
		{1, "D"},
		{2, "C"},
		{3, "C"},
		{4, "B"},
		{5, "B"},
		{6, "A"},
		{7, "A"},
		{99, "A"},
	}
	for _, c := range cases {
		if got := scoreToGrade(c.score); got != c.want {
			t.Errorf("scoreToGrade(%d) = %q, want %q", c.score, got, c.want)
		}
	}
}

func TestGradeReasoningContainsKeyFields(t *testing.T) {
	ep := &types.EvidencePackage{
		Citations: []types.Citation{
			{Title: "Randomized", Year: 2024, SourceOrigin: []string{"a", "b"}},
			{Title: "Trial", Year: 2024, SourceOrigin: []string{"c"}},
		},
	}
	g := Grade(ep)
	for _, want := range []string{"citation count", "source", "RCT"} {
		if !strings.Contains(g.Reasoning, want) {
			t.Errorf("Reasoning missing %q: %q", want, g.Reasoning)
		}
	}
}
