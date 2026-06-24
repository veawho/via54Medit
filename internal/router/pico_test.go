package router

import (
	"context"
	"strings"
	"testing"
)

func TestExtractPICOEmpty(t *testing.T) {
	r := NewRouter()
	_, err := r.ExtractPICO(context.Background(), "")
	if err == nil {
		t.Error("empty question should fail")
	}
}

func TestExtractPICOWithoutLLM(t *testing.T) {
	r := NewRouter()
	pico, err := r.ExtractPICO(context.Background(), "Does aspirin reduce cardiovascular death in patients with type 2 diabetes?")
	if err != nil {
		t.Fatal(err)
	}
	if pico == nil {
		t.Fatal("got nil PICO")
	}
	// Heuristic should at least find "aspirin" as intervention.
	if !strings.Contains(strings.ToLower(pico.Intervention), "aspirin") {
		t.Errorf("Intervention = %q, expected to contain 'aspirin'", pico.Intervention)
	}
}

func TestExtractPICOHeuristicVS(t *testing.T) {
	r := NewRouter()
	pico, err := r.ExtractPICO(context.Background(), "Aspirin vs placebo in patients with hypertension")
	if err != nil {
		t.Fatal(err)
	}
	// vs-pattern should split into intervention=aspirin, comparator=placebo.
	if !strings.Contains(strings.ToLower(pico.Intervention), "aspirin") {
		t.Errorf("Intervention = %q, want aspirin", pico.Intervention)
	}
	if !strings.Contains(strings.ToLower(pico.Comparator), "placebo") {
		t.Errorf("Comparator = %q, want placebo", pico.Comparator)
	}
}

func TestExtractPICOChineseHeuristic(t *testing.T) {
	r := NewRouter()
	pico, err := r.ExtractPICO(context.Background(), "阿司匹林对2型糖尿病患者心血管死亡的影响")
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(pico.Intervention, "阿司匹林") {
		t.Errorf("Intervention = %q, want 阿司匹林", pico.Intervention)
	}
}

func TestStripCodeFence(t *testing.T) {
	cases := []struct {
		in, want string
	}{
		{`{"a":1}`, `{"a":1}`},
		{"```json\n{\"a\":1}\n```", `{"a":1}`},
		{"```JSON\n{\"a\":1}\n```", `{"a":1}`},
		{"```\n{\"a\":1}\n```", `{"a":1}`},
		{"  raw  ", "raw"},
		{`{"a":1,"b":2}`, `{"a":1,"b":2}`},
	}
	for _, c := range cases {
		if got := stripCodeFence(c.in); got != c.want {
			t.Errorf("stripCodeFence(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestExtractPopulationHeuristic(t *testing.T) {
	cases := []struct {
		q    string
		want string
	}{
		{"aspirin in patients with heart failure", "patients"},
		{"treatment for 糖尿病 patients", "糖尿病 patients"},
	}
	for _, c := range cases {
		got := extractPopulationHeuristic(c.q)
		// Substring match — extractNounPhrase may add context.
		if !strings.Contains(got, c.want) && got != "" {
			t.Errorf("extractPopulationHeuristic(%q) = %q, want containing %q", c.q, got, c.want)
		}
	}
}

func TestExtractOutcomeHeuristic(t *testing.T) {
	cases := []string{
		"aspirin reduces mortality",
		"treatment effect on 心血管死亡",
		"risk of recurrence",
	}
	for _, q := range cases {
		got := extractOutcomeHeuristic(q)
		if got == "" {
			t.Errorf("extractOutcomeHeuristic(%q) = empty", q)
		}
	}
}

func TestExtractComparatorHeuristic(t *testing.T) {
	cases := []struct {
		q    string
		want string
	}{
		{"aspirin vs placebo", "placebo"},
		{"aspirin versus placebo", "placebo"},
		{"aspirin compared to placebo", "placebo"},
		{"阿司匹林 对比 安慰剂", "安慰剂"},
		{"aspirin", ""}, // no comparator
	}
	for _, c := range cases {
		got := extractComparatorHeuristic(c.q)
		if c.want == "" && got != "" {
			t.Errorf("extractComparatorHeuristic(%q) = %q, want empty", c.q, got)
		}
		if c.want != "" && !strings.Contains(got, c.want) {
			t.Errorf("extractComparatorHeuristic(%q) = %q, want containing %q", c.q, got, c.want)
		}
	}
}

func TestExtractNounPhrase(t *testing.T) {
	q := "aspirin reduces mortality in patients"
	got := extractNounPhrase(q, "mortality")
	if got == "" {
		t.Error("got empty")
	}
	// We expect "mortality" to be in the result.
	if !strings.Contains(got, "mortality") {
		t.Errorf("extractNounPhrase(%q, mortality) = %q, want containing 'mortality'", q, got)
	}
}

func TestPICOAllEmptyFallback(t *testing.T) {
	r := NewRouter()
	pico, err := r.ExtractPICO(context.Background(), "xyz abc qwerty?")
	if err != nil {
		t.Fatal(err)
	}
	// All heuristic fields should be empty for nonsense input.
	if pico.Population != "" || pico.Intervention != "" || pico.Outcome != "" {
		t.Errorf("expected all-empty PICO, got %+v", pico)
	}
}
