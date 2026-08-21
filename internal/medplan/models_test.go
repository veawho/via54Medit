package medplan

import (
	"strings"
	"testing"
	"time"
)

func TestParseAudience(t *testing.T) {
	for _, ok := range []string{"hcp", "patient", "industry", "HCP", " Patient "} {
		if _, err := ParseAudience(ok); err != nil {
			t.Errorf("ParseAudience(%q) unexpected error: %v", ok, err)
		}
	}
	if _, err := ParseAudience("doctor"); err == nil {
		t.Error("ParseAudience(doctor) should fail")
	}
}

func TestOutlineWalkAndFlatten(t *testing.T) {
	o := Skeleton("p1", AudienceHCP)
	if got := o.SectionCount(); got < 7 {
		t.Errorf("HCP skeleton should have >=7 sections, got %d", got)
	}
	flat := o.Flatten()
	if len(flat) != o.SectionCount() {
		t.Errorf("Flatten len %d != SectionCount %d", len(flat), o.SectionCount())
	}
	if o.FindSection("1") == nil || o.FindSection("6") == nil {
		t.Error("expected sections 1 and 6 in skeleton")
	}
	if o.FindSection("nope") != nil {
		t.Error("FindSection(nope) should be nil")
	}
}

func TestSkeletonPerAudience(t *testing.T) {
	cases := []struct {
		a    Audience
		want []string
	}{
		{AudienceHCP, []string{"循证证据链构建", "学术传播与医学教育"}},
		{AudiencePatient, []string{"疾病认知与患者旅程", "治疗可及与患者支持"}},
		{AudienceIndustry, []string{"支付与准入策略", "商业模式与合作生态"}},
	}
	for _, c := range cases {
		o := Skeleton("p", c.a)
		text := o.FullText()
		for _, w := range c.want {
			if !strings.Contains(text, w) {
				t.Errorf("audience %s skeleton missing %q", c.a, w)
			}
		}
	}
	// Five core modules exist for every audience.
	for _, a := range AllAudiences() {
		text := Skeleton("p", a).FullText()
		for _, core := range []string{"市场环境分析", "竞品分析", "品牌本体", "核心竞争优势包装", "传播策略"} {
			if !strings.Contains(text, core) {
				t.Errorf("audience %s skeleton missing core module %q", a, core)
			}
		}
	}
}

func TestFullTextIncludesPositioning(t *testing.T) {
	o := Skeleton("p", AudienceHCP)
	o.Positioning = "定位 ABC"
	o.KeyMessage = "钥匙 XYZ"
	full := o.FullText()
	if !strings.Contains(full, "定位 ABC") || !strings.Contains(full, "钥匙 XYZ") {
		t.Error("FullText must include positioning and key message")
	}
}

func TestComplianceVerdictAndSort(t *testing.T) {
	r := &ComplianceReport{
		Findings: []ComplianceFinding{
			{RuleID: "ADV-09", Severity: SevWarn},
			{RuleID: "ADV-16", Severity: SevFatal},
			{RuleID: "PAT-D", Severity: SevInfo},
		},
	}
	if v := r.ComputeVerdict(); v != "fail" {
		t.Errorf("verdict with fatal = %s, want fail", v)
	}
	r.SortFindings()
	if r.Findings[0].Severity != SevFatal || r.Findings[2].Severity != SevInfo {
		t.Errorf("sort order wrong: %+v", r.Findings)
	}
	r2 := &ComplianceReport{}
	if v := r2.ComputeVerdict(); v != "pass" {
		t.Errorf("empty verdict = %s, want pass", v)
	}
}

func TestDossierHelpers(t *testing.T) {
	d := &ResearchDossier{
		Items: []ResearchItem{
			{ID: "L001", Dimension: DimLiterature},
			{ID: "C001", Dimension: DimCompetitor},
			{ID: "L002", Dimension: DimLiterature},
		},
	}
	if n := len(d.ItemsByDimension(DimLiterature)); n != 2 {
		t.Errorf("literature items = %d, want 2", n)
	}
	dims := d.Dimensions()
	if len(dims) != 2 || dims[0] != DimLiterature || dims[1] != DimCompetitor {
		t.Errorf("Dimensions order wrong: %v", dims)
	}
}

func TestTimeFieldsRoundTrip(t *testing.T) {
	// nowUTC stub: guarantee deterministic CreatedAt paths.
	orig := nowUTC
	nowUTC = func() time.Time { return time.Date(2026, 8, 21, 0, 0, 0, 0, time.UTC) }
	defer func() { nowUTC = orig }()
	o := Skeleton("p", AudiencePatient)
	if o.CreatedAt.Year() != 2026 {
		t.Errorf("stubbed clock not honored: %v", o.CreatedAt)
	}
}

func TestAttachEvidence(t *testing.T) {
	o := Skeleton("p", AudienceHCP)
	items := []ResearchItem{
		{ID: "L001", Dimension: DimLiterature},
		{ID: "C001", Dimension: DimCompetitor},
		{ID: "P001", Dimension: DimPolicy},
	}
	o.AttachEvidence(items)
	if sec := o.FindSection("2"); sec == nil || !containsStr(sec.Evidence, "C001") {
		t.Error("competitor item should attach to section 2")
	}
	if sec := o.FindSection("4"); sec == nil || !containsStr(sec.Evidence, "L001") {
		t.Error("literature item should attach to section 4")
	}
	if sec := o.FindSection("1"); sec == nil || !containsStr(sec.Evidence, "P001") {
		t.Error("policy item should attach to section 1")
	}
}

func containsStr(ss []string, want string) bool {
	for _, s := range ss {
		if s == want {
			return true
		}
	}
	return false
}
