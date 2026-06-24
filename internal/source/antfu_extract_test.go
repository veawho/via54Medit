package source

import (
	"strings"
	"testing"
)

const sampleHTML = `
<html>
<body>
  <div class="chat-container">
    <div class="markdown-body">
      <p>第一段:简短摘要</p>
      <p>第二段:详细分析,包含 <em>关键术语</em>。</p>
    </div>
    <div class="quotedMaterials">
      <div class="reference-item">
        <a href="https://pubmed.ncbi.nlm.nih.gov/31535829/">DAPA-HF: Dapagliflozin in Heart Failure</a>
        <p class="snippet">A 2019 trial showing cardiovascular benefits in heart failure patients with reduced ejection fraction.</p>
      </div>
      <div class="reference-item">
        <a href="https://doi.org/10.1056/NEJMoa1911303">NEJM Article on SGLT2</a>
        <p>2020 follow-up analysis.</p>
      </div>
      <div class="reference-item">
        <!-- Title missing — should still be picked up via URL -->
        <a href="https://example.com/no-title">https://example.com/no-title</a>
      </div>
    </div>
  </div>
</body>
</html>`

func TestExtractDefaults(t *testing.T) {
	cfg := DefaultExtractConfig()
	if cfg.AnswerSelector == "" {
		t.Error("AnswerSelector must have a default")
	}
	if cfg.QuoteContainerSelector == "" {
		t.Error("QuoteContainerSelector must have a default")
	}
}

func TestExtractAnswer(t *testing.T) {
	res, err := Extract(strings.NewReader(sampleHTML), DefaultExtractConfig())
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(res.Answer, "第一段") {
		t.Errorf("Answer missing first paragraph: %q", res.Answer)
	}
	if !strings.Contains(res.Answer, "第二段") {
		t.Errorf("Answer missing second paragraph: %q", res.Answer)
	}
	if !strings.Contains(res.Answer, "关键术语") {
		t.Errorf("Answer missing inner text: %q", res.Answer)
	}
}

func TestExtractReferencesCount(t *testing.T) {
	res, err := Extract(strings.NewReader(sampleHTML), DefaultExtractConfig())
	if err != nil {
		t.Fatal(err)
	}
	if len(res.References) != 3 {
		t.Fatalf("got %d references, want 3", len(res.References))
	}
}

func TestExtractReferenceFields(t *testing.T) {
	res, _ := Extract(strings.NewReader(sampleHTML), DefaultExtractConfig())
	first := res.References[0]
	if first.Title == "" {
		t.Error("first ref missing title")
	}
	if !strings.Contains(first.URL, "pubmed.ncbi.nlm.nih.gov") {
		t.Errorf("first ref URL wrong: %q", first.URL)
	}
	if first.Snippet == "" {
		t.Error("first ref missing snippet")
	}
	if first.Year != 2019 {
		t.Errorf("first ref year = %d, want 2019", first.Year)
	}
}

func TestExtractReferenceNoTitle(t *testing.T) {
	res, _ := Extract(strings.NewReader(sampleHTML), DefaultExtractConfig())
	last := res.References[2]
	if last.Title == "" {
		t.Error("ref with no title should still be picked up (URL only)")
	}
	if !strings.Contains(last.URL, "example.com/no-title") {
		t.Errorf("ref URL wrong: %q", last.URL)
	}
}

func TestExtractEmptyHTML(t *testing.T) {
	res, err := Extract(strings.NewReader("<html><body></body></html>"), DefaultExtractConfig())
	if err != nil {
		t.Fatal(err)
	}
	if res.Answer != "" {
		t.Errorf("Answer = %q, want empty", res.Answer)
	}
	if len(res.References) != 0 {
		t.Errorf("References = %d, want 0", len(res.References))
	}
}

func TestExtractInvalidHTML(t *testing.T) {
	// goquery is very forgiving; even broken HTML returns some doc.
	// We just verify no panic and no error.
	_, err := Extract(strings.NewReader("<not really html"), DefaultExtractConfig())
	if err != nil {
		t.Logf("Extract on broken HTML returned: %v (acceptable)", err)
	}
}

func TestSplitSelectors(t *testing.T) {
	cases := []struct {
		in   string
		want []string
	}{
		{"a,b,c", []string{"a", "b", "c"}},
		{"a , b ,c", []string{"a", "b", "c"}},
		{"", nil},
		{"only-one", []string{"only-one"}},
	}
	for _, c := range cases {
		got := splitSelectors(c.in)
		if len(got) != len(c.want) {
			t.Errorf("splitSelectors(%q) = %v, want %v", c.in, got, c.want)
			continue
		}
		for i := range got {
			if got[i] != c.want[i] {
				t.Errorf("splitSelectors(%q)[%d] = %q, want %q", c.in, i, got[i], c.want[i])
			}
		}
	}
}

func TestExtractYear(t *testing.T) {
	cases := []struct {
		in   string
		want int
	}{
		{"published in 2019", 2019},
		{"2020-Mar-15", 2020},
		{"no year", 0},
		{"old: 1899", 0},    // below 1900
		{"future: 2150", 0}, // above 2099
		{"1995 to 2005", 1995},
		{"  2024  ", 2024},
	}
	for _, c := range cases {
		if got := extractYear(c.in); got != c.want {
			t.Errorf("extractYear(%q) = %d, want %d", c.in, got, c.want)
		}
	}
}
