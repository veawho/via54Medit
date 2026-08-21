package medplan

import (
	"context"
	"strings"
	"testing"

	"github.com/veawho/via54Medit/internal/foundation"
	"github.com/veawho/via54Medit/pkg/types"
)

// fakeLLM stubs the provider for deterministic LLM-path tests.
type fakeLLM struct {
	resp     string
	err      error
	calls    int
	lastUser string
}

func (f *fakeLLM) Name() string { return "fake" }

func (f *fakeLLM) Complete(_ context.Context, _, user string) (string, error) {
	f.calls++
	f.lastUser = user
	return f.resp, f.err
}

func (f *fakeLLM) CompleteWithOptions(ctx context.Context, opts foundation.CompleteOptions) (string, error) {
	return f.Complete(ctx, opts.System, opts.User)
}

// fakeSearcher stubs the literature fan-out.
type fakeSearcher struct {
	cites []types.Citation
	err   error
	qs    []string
}

func (f *fakeSearcher) SearchLiterature(_ context.Context, q string, _ int) ([]types.Citation, error) {
	f.qs = append(f.qs, q)
	return f.cites, f.err
}

func outlineWith(texts ...string) *StrategyOutline {
	o := Skeleton("test", AudienceHCP)
	o.Sections = []OutlineSection{{ID: "1", Title: texts[0]}}
	for _, txt := range texts[1:] {
		o.Sections = append(o.Sections, OutlineSection{ID: "2", Title: txt})
	}
	return o
}

func TestComplianceCureClaim(t *testing.T) {
	o := outlineWith(" revolutionary message ")
	o.Sections[0].Points = []string{"彻底根治糖尿病, 治愈率高达95%", "安全无副作用"}
	c := NewComplianceChecker(nil)
	rep, err := c.Check(context.Background(), o, Product{Name: "X"})
	if err != nil {
		t.Fatal(err)
	}
	if rep.Verdict != "fail" {
		t.Errorf("verdict = %s, want fail", rep.Verdict)
	}
	var sawCure, sawSafe bool
	for _, f := range rep.Findings {
		if f.RuleID == "ADV-16-CURE" {
			sawCure = true
		}
		if f.RuleID == "ADV-16-SAFE" {
			sawSafe = true
		}
	}
	if !sawCure || !sawSafe {
		t.Errorf("expected ADV-16-CURE and ADV-16-SAFE, got %+v", rep.Findings)
	}
	// Section annotation set.
	if !strings.Contains(o.Sections[0].ComplianceNote, "ADV-16-CURE") {
		t.Errorf("section compliance note missing: %q", o.Sections[0].ComplianceNote)
	}
}

func TestComplianceAbsoluteWords(t *testing.T) {
	o := outlineWith("全球首创的最佳治疗方案")
	c := NewComplianceChecker(nil)
	rep, _ := c.Check(context.Background(), o, Product{Name: "X"})
	found := false
	for _, f := range rep.Findings {
		if f.RuleID == "ADV-09-ABSOLUTE" {
			found = true
		}
	}
	if !found {
		t.Error("expected ADV-09-ABSOLUTE finding")
	}
	if rep.Verdict != "warn" {
		t.Errorf("verdict = %s, want warn (absolute words only)", rep.Verdict)
	}
}

func TestComplianceRxPublicBanGating(t *testing.T) {
	o := outlineWith("传播策略")
	o.Sections[0].Points = []string{"朋友圈广告投放引爆声量"}
	c := NewComplianceChecker(nil)

	// rx product → fatal.
	rep, _ := c.Check(context.Background(), o, Product{Name: "X", RxStatus: rxStatusRx})
	if rep.Verdict != "fail" {
		t.Errorf("rx verdict = %s, want fail", rep.Verdict)
	}
	// otc product → rule not applicable.
	rep2, _ := c.Check(context.Background(), o, Product{Name: "X", RxStatus: rxStatusOTC})
	for _, f := range rep2.Findings {
		if f.RuleID == "DRG-RX-PUBLIC" {
			t.Error("DRG-RX-PUBLIC should not fire for OTC")
		}
	}
}

func TestCompliancePatientRulesOnlyForPatient(t *testing.T) {
	// Disclaimer presence rule fires only for patient outlines.
	hcp := outlineWith("内容不含提示语")
	rep, _ := NewComplianceChecker(nil).Check(context.Background(), hcp, Product{Name: "X"})
	for _, f := range rep.Findings {
		if f.RuleID == "PAT-DISCLAIMER" {
			t.Error("PAT-DISCLAIMER should not fire for HCP")
		}
	}
	pat := Skeleton("t", AudiencePatient)
	rep2, _ := NewComplianceChecker(nil).Check(context.Background(), pat, Product{Name: "X"})
	saw := false
	for _, f := range rep2.Findings {
		if f.RuleID == "PAT-DISCLAIMER" {
			saw = true
		}
	}
	if !saw {
		t.Error("PAT-DISCLAIMER should fire when patient outline lacks disclaimer")
	}
	// With a disclaimer present it must not fire.
	pat.Sections = append(pat.Sections, OutlineSection{ID: "8", Title: "附注", Points: []string{"请遵医嘱"}})
	rep3, _ := NewComplianceChecker(nil).Check(context.Background(), pat, Product{Name: "X"})
	for _, f := range rep3.Findings {
		if f.RuleID == "PAT-DISCLAIMER" {
			t.Error("PAT-DISCLAIMER should not fire when disclaimer exists")
		}
	}
}

func TestComplianceNegationExemption(t *testing.T) {
	// Stating a prohibition is not a violation (compliance-boundary text).
	// Patient audience so the PatientOnly rule actually applies.
	o := Skeleton("t", AudiencePatient)
	o.Sections = []OutlineSection{{ID: "1", Title: "治疗可及与患者支持", Points: []string{
		"合规边界: 处方药不得面向公众发布广告, 患者材料限于疾病教育",
		"传播规范: 禁止使用疗效优于竞品的比较性表述",
	}}}
	rep, _ := NewComplianceChecker(nil).Check(context.Background(), o, Product{Name: "X", RxStatus: rxStatusRx})
	for _, f := range rep.Findings {
		if f.RuleID == "PAT-PRODUCT-PROMO" || f.RuleID == "ADV-16-COMPARE" {
			t.Errorf("negated statement should be exempt, got %s on %q", f.RuleID, f.Matched)
		}
	}
	// A real violation right after a negated clause still fires.
	o2 := outlineWith("x")
	o2.Sections[0].Points = []string{"本品疗效优于所有竞品且安全无副作用"}
	rep2, _ := NewComplianceChecker(nil).Check(context.Background(), o2, Product{Name: "X"})
	sawCompare, sawSafe := false, false
	for _, f := range rep2.Findings {
		if f.RuleID == "ADV-16-COMPARE" {
			sawCompare = true
		}
		if f.RuleID == "ADV-16-SAFE" {
			sawSafe = true
		}
	}
	if !sawCompare || !sawSafe {
		t.Error("non-negated violations must still fire")
	}
}

func TestComplianceCleanOutlinePasses(t *testing.T) {
	o := Skeleton("t", AudienceIndustry)
	rep, err := NewComplianceChecker(nil).Check(context.Background(), o, Product{Name: "X", RxStatus: rxStatusOTC})
	if err != nil {
		t.Fatal(err)
	}
	if rep.Verdict != "pass" {
		t.Errorf("clean outline verdict = %s (findings: %+v), want pass", rep.Verdict, rep.Findings)
	}
}

func TestComplianceSemanticLayer(t *testing.T) {
	llm := &fakeLLM{resp: `{"findings":[{"category":"off_label","severity":"fatal","section_title":"传播策略","matched":"暗示可用于未经批准的适应症","suggestion":"删除"}]}`}
	c := NewComplianceChecker(llm)
	o := Skeleton("t", AudienceHCP)
	rep, err := c.Check(context.Background(), o, Product{Name: "X"})
	if err != nil {
		t.Fatal(err)
	}
	if rep.Engine != "rules+llm" {
		t.Errorf("engine = %s, want rules+llm", rep.Engine)
	}
	if rep.Verdict != "fail" {
		t.Errorf("verdict = %s, want fail from LLM off-label finding", rep.Verdict)
	}
	found := false
	for _, f := range rep.Findings {
		if f.RuleID == "LLM-OFFLABEL" {
			found = true
		}
	}
	if !found {
		t.Error("expected LLM-OFFLABEL finding")
	}
}

func TestComplianceSemanticDegradesOnLLMError(t *testing.T) {
	llm := &fakeLLM{err: context.Canceled}
	c := NewComplianceChecker(llm)
	o := Skeleton("t", AudienceHCP)
	rep, err := c.Check(context.Background(), o, Product{Name: "X"})
	if err != nil {
		t.Fatal(err)
	}
	if rep.Engine != "rules" {
		t.Errorf("engine = %s, want rules (degraded)", rep.Engine)
	}
}

func TestExtractJSON(t *testing.T) {
	cases := []struct{ in, want string }{
		{`prefix {"a":{"b":"c}"}} suffix`, `{"a":{"b":"c}"}}`},
		{"no braces", "no braces"},
		{`{"x":1}`, `{"x":1}`},
		{`broken {"x":`, `{"x":`},
	}
	for _, c := range cases {
		if got := extractJSON(c.in); got != c.want {
			t.Errorf("extractJSON(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}
