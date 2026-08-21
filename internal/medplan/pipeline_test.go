package medplan

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestProjectRoundTrip(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "medplan")
	s, err := NewProjectStoreAt(dir)
	if err != nil {
		t.Fatal(err)
	}
	b := testBrief()
	if err := s.SaveBrief(b); err != nil {
		t.Fatal(err)
	}
	got, err := s.LoadBrief("test-proj")
	if err != nil {
		t.Fatal(err)
	}
	if got.Instruction != b.Instruction || got.Product.Name != b.Product.Name {
		t.Errorf("brief round trip mismatch: %+v", got)
	}

	d := &ResearchDossier{Project: b.Project, Items: []ResearchItem{{ID: "L001", Dimension: DimLiterature}}}
	if err := s.SaveResearch(d); err != nil {
		t.Fatal(err)
	}
	if rd, err := s.LoadResearch(b.Project); err != nil || len(rd.Items) != 1 {
		t.Errorf("research round trip: %v %+v", err, rd)
	}

	ins := &Insights{Project: b.Project, Insights: []Insight{{ID: "I1", Claim: "c"}}}
	if err := s.SaveInsights(ins); err != nil {
		t.Fatal(err)
	}
	if ri, err := s.LoadInsights(b.Project); err != nil || len(ri.Insights) != 1 {
		t.Errorf("insights round trip: %v", err)
	}

	o := Skeleton(b.Project, AudienceHCP)
	if err := s.SaveOutline(o); err != nil {
		t.Fatal(err)
	}
	if ro, err := s.LoadOutline(b.Project, AudienceHCP); err != nil || ro.SectionCount() != o.SectionCount() {
		t.Errorf("outline round trip: %v", err)
	}

	rep := &ComplianceReport{Project: b.Project, Audience: AudienceHCP, Verdict: "pass"}
	if err := s.SaveCompliance(rep); err != nil {
		t.Fatal(err)
	}
	if rr, err := s.LoadCompliance(b.Project, AudienceHCP); err != nil || rr.Verdict != "pass" {
		t.Errorf("compliance round trip: %v", err)
	}

	// List finds the project.
	names, err := s.List()
	if err != nil || len(names) != 1 || names[0] != "test-proj" {
		t.Errorf("list = %v err=%v", names, err)
	}

	// Markdown write.
	if err := s.WriteMarkdown(b.Project, AudienceHCP, "# hello"); err != nil {
		t.Fatal(err)
	}
	data, _ := os.ReadFile(s.OutlinePath(b.Project, AudienceHCP))
	if len(data) == 0 {
		t.Error("outline json empty")
	}
	mdPath := filepath.Join(s.Dir(b.Project), "outline_hcp.md")
	if md, err := os.ReadFile(mdPath); err != nil || string(md) != "# hello" {
		t.Errorf("markdown write failed: %v", err)
	}
}

func TestSanitizeProjectName(t *testing.T) {
	cases := map[string]string{
		"DrugA 上市计划":  "DrugA-上市计划",
		"a/b\\c":      "a-b-c",
		"../etc":      "..-etc",
		"!!!":         "project",
		"ok_name-1.2": "ok_name-1.2",
	}
	for in, want := range cases {
		if got := sanitizeProjectName(in); got != want {
			t.Errorf("sanitize(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestRenderMarkdown(t *testing.T) {
	o := Skeleton("test-proj", AudiencePatient)
	o.Positioning = "每周一次的血糖控制选择"
	d := &ResearchDossier{Project: "test-proj", Items: []ResearchItem{
		{ID: "L001", Dimension: DimLiterature, Title: "DrugA Phase 3", Summary: "主要终点达成"},
		{ID: "N001", Dimension: DimNews, Title: "获批新闻", NeedsVerification: true},
	}}
	ins := &Insights{Project: "test-proj", Insights: []Insight{
		{ID: "I1", Claim: "给药便利优势", Strength: "strong", Advantage: true, ItemIDs: []string{"L001"}},
	}, SWOT: SWOT{Strengths: []string{"每周一次"}}}
	rep := &ComplianceReport{Verdict: "warn", Engine: "rules", Findings: []ComplianceFinding{
		{RuleID: "PAT-DISCLAIMER", Severity: SevInfo, Suggestion: "增加提示语"},
	}}
	md := RenderMarkdown(o, RenderOptions{Dossier: d, Insights: ins, Compliance: rep, Brief: testBrief()})
	for _, want := range []string{
		"医学策划方案大纲", "患者及家属", "品牌定位", "合规验证", "⚠️ 需复核",
		"核心观点与竞争优势", "SWOT", "调研证据索引", "L001", "⚠️待人工核验",
	} {
		if !strings.Contains(md, want) {
			t.Errorf("markdown missing %q", want)
		}
	}
}

func TestPipelineEndToEndNoLLM(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "medplan")
	s, err := NewProjectStoreAt(dir)
	if err != nil {
		t.Fatal(err)
	}
	fs := &fakeSearcher{}
	pipe := &Pipeline{
		Researcher: &Researcher{Searcher: fs},
		Analyzer:   &Analyzer{},
		Generator:  &Generator{},
		Checker:    NewComplianceChecker(nil),
		Store:      s,
	}
	res, err := pipe.Run(context.Background(), RunOptions{Brief: testBrief()})
	if err != nil {
		t.Fatal(err)
	}
	if res.Dossier == nil || res.Insights == nil {
		t.Fatal("dossier/insights missing")
	}
	if len(res.Outlines) != 3 {
		t.Errorf("outlines = %d, want 3", len(res.Outlines))
	}
	for _, a := range AllAudiences() {
		o := res.Outlines[a]
		if o == nil || o.GeneratedBy != "template" {
			t.Errorf("audience %s outline wrong", a)
		}
		if _, err := s.LoadOutline("test-proj", a); err != nil {
			t.Errorf("outline not persisted for %s: %v", a, err)
		}
		if _, err := os.Stat(filepath.Join(s.Dir("test-proj"), "outline_"+string(a)+".md")); err != nil {
			t.Errorf("markdown not written for %s: %v", a, err)
		}
		if rep := res.Compliance[a]; rep == nil {
			t.Errorf("compliance missing for %s", a)
		}
	}
}

func TestPipelineAudienceOverrideAndSkipResearch(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "medplan")
	s, _ := NewProjectStoreAt(dir)
	fs := &fakeSearcher{}
	pipe := &Pipeline{
		Researcher: &Researcher{Searcher: fs},
		Analyzer:   &Analyzer{},
		Generator:  &Generator{},
		Checker:    NewComplianceChecker(nil),
		Store:      s,
	}
	res, err := pipe.Run(context.Background(), RunOptions{Brief: testBrief(), Audiences: []Audience{AudienceHCP}})
	if err != nil {
		t.Fatal(err)
	}
	if len(res.Outlines) != 1 {
		t.Fatalf("outlines = %d, want 1", len(res.Outlines))
	}
	if _, ok := res.Outlines[AudienceHCP]; !ok {
		t.Error("HCP outline missing")
	}
	// Second run reuses persisted research with SkipResearch.
	before := len(fs.qs)
	res2, err := pipe.Run(context.Background(), RunOptions{Brief: testBrief(), Audiences: []Audience{AudienceHCP}, SkipResearch: true})
	if err != nil {
		t.Fatal(err)
	}
	if len(fs.qs) != before {
		t.Error("SkipResearch must not issue new searches")
	}
	if res2.Dossier == nil || len(res2.Outlines) != 1 {
		t.Error("skip-research run incomplete")
	}
	// Brief audiences persisted with override.
	b2, _ := s.LoadBrief("test-proj")
	if len(b2.Audiences) != 1 || b2.Audiences[0] != AudienceHCP {
		t.Errorf("brief audiences not overridden: %v", b2.Audiences)
	}
}
