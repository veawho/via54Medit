package medplan

import (
	"context"
	"errors"
	"strings"
	"testing"
)

func TestGenerateTemplateWithoutLLM(t *testing.T) {
	g := &Generator{}
	o, err := g.Generate(context.Background(), testBrief(), nil, nil, AudienceHCP)
	if err != nil {
		t.Fatal(err)
	}
	if o.GeneratedBy != "template" {
		t.Errorf("GeneratedBy = %s, want template", o.GeneratedBy)
	}
	if o.Version != 1 || o.SectionCount() < 7 {
		t.Errorf("template outline wrong: v%d sections %d", o.Version, o.SectionCount())
	}
}

func TestGenerateWithLLM(t *testing.T) {
	llm := &fakeLLM{resp: `{
		"positioning":"为 T2DM 患者提供每周一次的血糖控制选择",
		"key_message":"每周一次, 依从性优势",
		"sections":[
			{"title":"市场环境分析","points":["中国 T2DM 患病率持续上升","未满足需求: 依从性差"],"evidence":["L001","FAKE9"]},
			{"title":"核心竞争优势包装","points":["给药频率差异"],"evidence":["L002"],"children":[
				{"title":"证据矩阵","points":["头对头数据"],"evidence":[]}
			]}
		]
	}`}
	g := &Generator{LLM: llm, ProviderLabel: "llm:fake"}
	d := &ResearchDossier{Items: []ResearchItem{
		{ID: "L001", Dimension: DimLiterature},
		{ID: "L002", Dimension: DimLiterature},
	}}
	o, err := g.Generate(context.Background(), testBrief(), d, nil, AudienceHCP)
	if err != nil {
		t.Fatal(err)
	}
	if o.GeneratedBy != "llm:fake" {
		t.Errorf("GeneratedBy = %s", o.GeneratedBy)
	}
	if !strings.Contains(o.Positioning, "每周一次") {
		t.Errorf("positioning missing: %q", o.Positioning)
	}
	// Evidence filtering: FAKE9 dropped.
	sec1 := o.FindSection("1")
	if sec1 == nil || len(sec1.Evidence) != 1 || sec1.Evidence[0] != "L001" {
		t.Errorf("evidence not filtered: %+v", sec1.Evidence)
	}
	// Children ID nesting.
	child := o.FindSection("2.1")
	if child == nil || child.Title != "证据矩阵" {
		t.Errorf("child section missing: %+v", o.Sections)
	}
	// Prompt includes skeleton + compliance instruction.
	if !strings.Contains(llm.lastUser, "市场环境分析") || !strings.Contains(llm.lastUser, "合规") {
		t.Error("prompt should embed skeleton and compliance boundary")
	}
}

func TestGenerateLLMParseFailureFallsBack(t *testing.T) {
	llm := &fakeLLM{err: errors.New("boom")}
	g := &Generator{LLM: llm}
	o, err := g.Generate(context.Background(), testBrief(), nil, nil, AudienceHCP)
	if err == nil {
		t.Error("expected degraded error to surface")
	}
	if o == nil || o.GeneratedBy != "template" {
		t.Error("fallback outline should be the template")
	}
}

func TestOptimizeVersionsAndChangelog(t *testing.T) {
	llm := &fakeLLM{resp: `{
		"positioning":"优化后的定位",
		"key_message":"优化后的钥匙",
		"change_summary":"扩充了传播策略",
		"sections":[
			{"title":"市场环境分析","points":["p1","p2","p3"]},
			{"title":"传播策略","points":["县域市场","线上学术","患者教育","KOL 联动","零售渠道"],"children":[
				{"title":"县域市场打法","points":["基层医疗覆盖"]}
			]}
		]
	}`}
	opt := &Optimizer{LLM: llm}
	base := Skeleton("test-proj", AudienceHCP)
	next, err := opt.Optimize(context.Background(), base, testBrief(), nil, "把传播策略扩充到县域市场")
	if err != nil {
		t.Fatal(err)
	}
	if next.Version != base.Version+1 {
		t.Errorf("version = %d, want %d", next.Version, base.Version+1)
	}
	if len(next.ChangeLog) != 1 || next.ChangeLog[0].Instruction != "把传播策略扩充到县域市场" {
		t.Errorf("changelog wrong: %+v", next.ChangeLog)
	}
	if !strings.Contains(next.ChangeLog[0].Summary, "章节") {
		t.Errorf("summary should include structural diff: %q", next.ChangeLog[0].Summary)
	}
	// Input not mutated.
	if base.Version != 1 || len(base.ChangeLog) != 0 {
		t.Error("base outline must not be mutated")
	}
}

func TestOptimizeRequiresInstruction(t *testing.T) {
	opt := &Optimizer{LLM: &fakeLLM{}}
	if _, err := opt.Optimize(context.Background(), Skeleton("p", AudienceHCP), testBrief(), nil, "  "); err == nil {
		t.Error("empty instruction should error")
	}
	noLLM := &Optimizer{}
	if _, err := noLLM.Optimize(context.Background(), Skeleton("p", AudienceHCP), testBrief(), nil, "x"); err == nil {
		t.Error("no-LLM optimizer should error")
	}
}

func TestExpandSection(t *testing.T) {
	llm := &fakeLLM{resp: `{"sections":[{"title":"传播策略","points":["a","b"],"children":[{"title":"分阶段节奏","points":["x"]}]}]}`}
	opt := &Optimizer{LLM: llm}
	next, err := opt.ExpandSection(context.Background(), Skeleton("p", AudienceHCP), testBrief(), nil, "5", "聚焦县域")
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(llm.lastUser, "传播策略") || !strings.Contains(llm.lastUser, "县域") {
		t.Error("expand instruction should carry section title and focus")
	}
	if next.Version != 2 {
		t.Errorf("version = %d, want 2", next.Version)
	}
	// Unknown section errors.
	if _, err := opt.ExpandSection(context.Background(), Skeleton("p", AudienceHCP), testBrief(), nil, "99", ""); err == nil {
		t.Error("unknown section should error")
	}
}

func TestDiffSummary(t *testing.T) {
	before := Skeleton("p", AudienceHCP)
	after := Skeleton("p", AudienceHCP)
	after.Sections = append(after.Sections, OutlineSection{ID: "8", Title: "新增章节", Points: []string{"a"}})
	s := diffSummary(before, after)
	if !strings.Contains(s, "+1") {
		t.Errorf("diff should report +1: %s", s)
	}
}
