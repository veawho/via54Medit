package medplan

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/veawho/via54Medit/pkg/types"
)

func testBrief() *Brief {
	return &Brief{
		Project:     "test-proj",
		Instruction: "为产品上市撰写学术传播策略",
		Product: Product{
			Name:            "DrugA",
			Company:         "PharmaCo",
			Indications:     []string{"2型糖尿病"},
			MOA:             "GLP-1 受体激动剂",
			Differentiators: []string{"每周一次给药"},
			Competitors:     []string{"DrugB"},
			RxStatus:        rxStatusRx,
		},
		Audiences: []Audience{AudienceHCP, AudiencePatient, AudienceIndustry},
	}
}

func TestQueryMatrixDeterministic(t *testing.T) {
	b := testBrief()
	m1 := buildQueryMatrix(b)
	m2 := buildQueryMatrix(b)
	// Compare serialized form (map iteration order varies).
	for _, dim := range AllDimensions() {
		q1, q2 := m1[dim], m2[dim]
		if len(q1) != len(q2) {
			t.Fatalf("dimension %s length mismatch", dim)
		}
		for i := range q1 {
			if q1[i].Query != q2[i].Query {
				t.Errorf("query %d differs: %q vs %q", i, q1[i].Query, q2[i].Query)
			}
		}
	}
	// Product + indication queries present.
	joined := ""
	for _, q := range m1[DimLiterature] {
		joined += q.Query + "\n"
	}
	if !strings.Contains(joined, "DrugA") || !strings.Contains(joined, "2型糖尿病") {
		t.Errorf("literature queries missing product/indication: %s", joined)
	}
	// Audience research terms appear.
	if !strings.Contains(joined, "guideline") {
		t.Errorf("HCP research term missing from queries: %s", joined)
	}
	// Competitor query per known competitor.
	if len(m1[DimCompetitor]) == 0 || !strings.Contains(m1[DimCompetitor][0].Query, "DrugB") {
		t.Errorf("competitor queries wrong: %+v", m1[DimCompetitor])
	}
}

func TestResearchLiteratureItems(t *testing.T) {
	fs := &fakeSearcher{cites: []types.Citation{
		{Title: "DrugA phase 3", PMID: "1", Year: 2025, CitedBy: 42, SourceOrigin: []string{"pubmed"}},
		{Title: "DrugA safety", PMID: "2", Year: 2024},
	}}
	r := &Researcher{Searcher: fs, MaxPerQuery: 5}
	d, err := r.Research(context.Background(), testBrief())
	if err != nil {
		t.Fatal(err)
	}
	lits := d.ItemsByDimension(DimLiterature)
	if len(lits) != 2 {
		t.Fatalf("literature items = %d, want 2", len(lits))
	}
	if lits[0].ID != "L001" || lits[1].ID != "L002" {
		t.Errorf("IDs wrong: %s %s", lits[0].ID, lits[1].ID)
	}
	if lits[0].Citation == nil || lits[0].Citation.PMID != "1" {
		t.Error("citation not linked")
	}
	// Non-literature dims skipped without LLM (queries logged).
	if len(d.ItemsByDimension(DimNews)) != 0 {
		t.Error("news should be empty without LLM")
	}
	var newsQueryErr bool
	for _, q := range d.Queries {
		if q.Dimension == DimNews && q.Error != "" {
			newsQueryErr = true
		}
	}
	if !newsQueryErr {
		t.Error("news query should record skip error without LLM")
	}
}

func TestResearchSearcherErrorRecorded(t *testing.T) {
	fs := &fakeSearcher{err: errors.New("boom")}
	r := &Researcher{Searcher: fs}
	d, err := r.Research(context.Background(), testBrief())
	if err != nil {
		t.Fatalf("research should not fail wholesale: %v", err)
	}
	if len(d.Items) != 0 {
		t.Errorf("items = %d, want 0", len(d.Items))
	}
	errs := 0
	for _, q := range d.Queries {
		if q.Error != "" {
			errs++
		}
	}
	if errs == 0 {
		t.Error("per-query errors should be recorded")
	}
}

func TestResearchSynthesizedDimensions(t *testing.T) {
	llm := &fakeLLM{resp: `{"items":[{"title":"医保谈判动态","summary":"准入窗口","published":"2025"}]}`}
	fs := &fakeSearcher{}
	r := &Researcher{Searcher: fs, LLM: llm}
	d, err := r.Research(context.Background(), testBrief())
	if err != nil {
		t.Fatal(err)
	}
	pols := d.ItemsByDimension(DimPolicy)
	if len(pols) == 0 {
		t.Fatal("policy items should be synthesized with LLM")
	}
	if !pols[0].NeedsVerification {
		t.Error("synthesized items must be flagged NeedsVerification")
	}
	if pols[0].Source != "llm" {
		t.Errorf("source = %s, want llm", pols[0].Source)
	}
	if d.Notes == "" {
		t.Error("notes should be synthesized")
	}
}

func TestIngestItems(t *testing.T) {
	d := &ResearchDossier{Items: []ResearchItem{{ID: "L001", Dimension: DimLiterature}}}
	IngestItems(d, []ResearchItem{
		{Dimension: DimNews, Title: "新闻1"},
		{Dimension: DimNews, Title: "新闻2"},
		{Dimension: "", Title: "默认新闻"}, // defaults to news
	})
	if len(d.Items) != 4 {
		t.Fatalf("items = %d, want 4", len(d.Items))
	}
	news := d.ItemsByDimension(DimNews)
	if len(news) != 3 {
		t.Fatalf("news = %d, want 3", len(news))
	}
	if news[0].ID != "N001" || news[2].ID != "N003" {
		t.Errorf("ingest IDs wrong: %+v", news)
	}
	// Deterministic order: literature before news.
	if d.Items[0].Dimension != DimLiterature {
		t.Errorf("sort order wrong: %+v", d.Items)
	}
}

func TestHeuristicInsights(t *testing.T) {
	b := testBrief()
	d := &ResearchDossier{Items: []ResearchItem{
		{ID: "L001", Dimension: DimLiterature, Citation: &types.Citation{CitedBy: 10}},
		{ID: "L002", Dimension: DimLiterature, Citation: &types.Citation{CitedBy: 99}},
	}}
	a := &Analyzer{}
	ins, err := a.Analyze(context.Background(), b, d)
	if err != nil {
		t.Fatal(err)
	}
	if len(ins.Insights) < 3 { // 2 literature + 1 differentiator
		t.Errorf("insights = %d, want >=3", len(ins.Insights))
	}
	var adv bool
	for _, x := range ins.Insights {
		if x.Advantage && strings.Contains(x.Claim, "每周一次给药") {
			adv = true
		}
	}
	if !adv {
		t.Error("differentiator should become an advantage insight")
	}
	if len(ins.SWOT.Strengths) == 0 || len(ins.SWOT.Threats) == 0 {
		t.Errorf("SWOT incomplete: %+v", ins.SWOT)
	}
}

func TestLLMInsightsValidation(t *testing.T) {
	llm := &fakeLLM{resp: `{
		"insights":[
			{"claim":"给药便利带来依从性优势","dimension":"literature","item_ids":["L001","BAD9"],"strength":"strong","advantage":true},
			{"claim":"无效观点引用不存在材料","item_ids":["ZZZ"],"dimension":"weird","strength":"ultimate"}
		],
		"swot":{"strengths":["S1"],"weaknesses":[],"opportunities":["O1"],"threats":[]}
	}`}
	a := &Analyzer{LLM: llm}
	d := &ResearchDossier{Items: []ResearchItem{{ID: "L001", Dimension: DimLiterature}}}
	ins, err := a.Analyze(context.Background(), testBrief(), d)
	if err != nil {
		t.Fatal(err)
	}
	if len(ins.Insights) != 2 {
		t.Fatalf("insights = %d, want 2", len(ins.Insights))
	}
	first := ins.Insights[0]
	if len(first.ItemIDs) != 1 || first.ItemIDs[0] != "L001" {
		t.Errorf("invalid item id not filtered: %v", first.ItemIDs)
	}
	second := ins.Insights[1]
	if second.Dimension != DimLiterature || second.Strength != "moderate" {
		t.Errorf("dimension/strength not defaulted: %+v", second)
	}
}

func TestAnalyzeLLMErrorFallsBack(t *testing.T) {
	llm := &fakeLLM{err: errors.New("llm down")}
	a := &Analyzer{LLM: llm}
	ins, err := a.Analyze(context.Background(), testBrief(), &ResearchDossier{})
	if err != nil {
		t.Fatal(err)
	}
	if len(ins.Insights) == 0 {
		t.Error("heuristic fallback should still produce insights")
	}
}
