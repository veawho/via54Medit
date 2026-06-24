// Types_test covers the core data models.
//
// Phase 0 baseline: 4 cases guarding the invariants every later phase
// will depend on. Keep this file dependency-free (stdlib only).
//
// Note: tests live in the same package (not types_test) so `go test -cover`
// counts the source statements — Phase 0 coverage reporting needs this.
package types

import (
	"encoding/json"
	"testing"
	"time"
)

// TestIntentConstants locks the wire values of every Intent.
// JSON consumers (MCP transport, persist_qa.py compat) parse these strings;
// renaming a constant is a breaking change.
func TestIntentConstants(t *testing.T) {
	cases := []struct {
		got  Intent
		want string
	}{
		{IntentSearch, "search"},
		{IntentSystematic, "systematic"},
		{IntentGrade, "grade"},
		{IntentAnnotate, "annotate"},
		{IntentIndex, "index"},
	}
	for _, c := range cases {
		if string(c.got) != c.want {
			t.Errorf("Intent %q: got %q, want %q", c.want, string(c.got), c.want)
		}
	}
}

// TestEBMQuestionJSONRoundTrip guarantees the wire format is stable.
// Any field rename without bumping the major version breaks MCP clients.
func TestEBMQuestionJSONRoundTrip(t *testing.T) {
	q := EBMQuestion{
		Query:      "SGLT2 抑制剂对 2 型糖尿病合并心衰的预后",
		Language:   "zh",
		Intent:     IntentSearch,
		Sources:    []string{"pubmed", "openalex"},
		MaxResults: 20,
		PICO: &PICO{
			Population:   "2 型糖尿病合并心衰",
			Intervention: "SGLT2 抑制剂",
			Comparator:   "安慰剂",
			Outcome:      "心血管死亡",
		},
	}

	data, err := json.Marshal(q)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}

	var got EBMQuestion
	if err := json.Unmarshal(data, &got); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}

	if got.Query != q.Query {
		t.Errorf("Query: got %q, want %q", got.Query, q.Query)
	}
	if got.PICO == nil || *got.PICO != *q.PICO {
		t.Errorf("PICO: got %+v, want %+v", got.PICO, q.PICO)
	}
	if got.MaxResults != 20 {
		t.Errorf("MaxResults: got %d, want 20", got.MaxResults)
	}
}

// TestCitationRequiredFields ensures the four bibliographic minimums
// that every source adapter MUST populate are part of the struct.
func TestCitationRequiredFields(t *testing.T) {
	c := Citation{
		Title:        "DAPA-HF trial",
		Authors:      []string{"McMurray JJV", "DeMets DL"},
		Journal:      "NEJM",
		Year:         2019,
		PMID:         "31535829",
		DOI:          "10.1056/NEJMoa1911303",
		SourceOrigin: []string{"pubmed", "openalex"},
		FetchedAt:    time.Now(),
	}

	if c.Title == "" {
		t.Error("Title must be populated")
	}
	if len(c.Authors) == 0 {
		t.Error("Authors must be populated")
	}
	if c.Year < 1900 {
		t.Errorf("Year %d looks bogus", c.Year)
	}
	if c.PMID == "" && c.DOI == "" {
		t.Error("at least one of PMID / DOI must be set (router dedup key)")
	}
	if len(c.SourceOrigin) == 0 {
		t.Error("SourceOrigin must list every source that returned this citation")
	}
}

// TestEvidencePackageStubShape pins the Phase 0 stub return shape.
// Phase 2 will replace Ask() with a real implementation; this test
// documents the contract Phase 1 callers can rely on today.
func TestEvidencePackageStubShape(t *testing.T) {
	ep := EvidencePackage{
		Question:    EBMQuestion{Query: "test"},
		Citations:   []Citation{},
		Summary:     "[Phase 0] stub",
		Duration:    0,
		SourcesUsed: map[string]int{},
		CreatedAt:   time.Now(),
		ConvID:      "phase0-stub",
	}

	if ep.Summary == "" {
		t.Error("Summary must be set even in Phase 0 (UI relies on it)")
	}
	if ep.ConvID == "" {
		t.Error("ConvID must be set (persist_qa uses it as filename)")
	}
	if ep.CreatedAt.IsZero() {
		t.Error("CreatedAt must be set (audit log uses it)")
	}
}
