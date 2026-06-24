package dedupe

import (
	"strings"
	"testing"

	"github.com/veawho/via54Medit/pkg/types"
)

func TestDedupeEmpty(t *testing.T) {
	out := Dedupe(nil)
	if out != nil {
		t.Errorf("Dedupe(nil) = %v, want nil", out)
	}
}

func TestDedupeByPMID(t *testing.T) {
	in := []types.Citation{
		{ID: "pubmed:1", PMID: "31535829", Title: "DAPA-HF", CitedBy: 100, SourceOrigin: []string{"pubmed"}},
		{ID: "openalex:W1", PMID: "31535829", Title: "DAPA-HF Trial", CitedBy: 200, SourceOrigin: []string{"openalex"}},
	}
	out := Dedupe(in)
	if len(out) != 1 {
		t.Fatalf("got %d, want 1 (merged by PMID)", len(out))
	}
	// Should pick the higher-CitedBy version (OpenAlex).
	if out[0].ID != "openalex:W1" {
		t.Errorf("best = %q, want openalex:W1 (higher CitedBy)", out[0].ID)
	}
	// SourceOrigin should be merged.
	if len(out[0].SourceOrigin) != 2 {
		t.Errorf("SourceOrigin = %v, want 2", out[0].SourceOrigin)
	}
	hasPubmed, hasOpenalex := false, false
	for _, s := range out[0].SourceOrigin {
		if s == "pubmed" {
			hasPubmed = true
		}
		if s == "openalex" {
			hasOpenalex = true
		}
	}
	if !hasPubmed || !hasOpenalex {
		t.Errorf("SourceOrigin missing one: %v", out[0].SourceOrigin)
	}
}

func TestDedupeByDOI(t *testing.T) {
	in := []types.Citation{
		{ID: "a", DOI: "10.1056/NEJMoa1911303", Title: "T1", CitedBy: 50},
		{ID: "b", DOI: "10.1056/nejmoa1911303", Title: "T2", CitedBy: 100}, // lowercase DOI
	}
	out := Dedupe(in)
	if len(out) != 1 {
		t.Fatalf("got %d, want 1 (merged by DOI case-insensitive)", len(out))
	}
}

func TestDedupeBySimHash(t *testing.T) {
	// Two citations with no PMID/DOI but very similar titles.
	in := []types.Citation{
		{ID: "a", Title: "Dapagliflozin in Heart Failure with Reduced Ejection Fraction"},
		{ID: "b", Title: "Dapagliflozin in heart failure with reduced ejection fraction"}, // case diff
	}
	out := Dedupe(in)
	if len(out) != 1 {
		t.Errorf("got %d, want 1 (merged by simhash)", len(out))
	}
}

func TestDedupeSimHashThreshold(t *testing.T) {
	// Two completely different titles should NOT merge.
	in := []types.Citation{
		{ID: "a", Title: "Dapagliflozin in Heart Failure"},
		{ID: "b", Title: "A completely unrelated paper about machine learning in cardiology"},
	}
	out := Dedupe(in)
	if len(out) != 2 {
		t.Errorf("got %d, want 2 (not merged)", len(out))
	}
}

func TestDedupeSortByRichness(t *testing.T) {
	in := []types.Citation{
		{ID: "a", PMID: "1", Title: "T1", CitedBy: 10},
		{ID: "b", PMID: "2", Title: "T2", CitedBy: 1000},
		{ID: "c", PMID: "3", Title: "T3", CitedBy: 100},
	}
	out := Dedupe(in)
	if len(out) != 3 {
		t.Fatalf("got %d", len(out))
	}
	if out[0].ID != "b" {
		t.Errorf("out[0] = %q, want b (highest CitedBy)", out[0].ID)
	}
}

func TestDedupeMergesSourceOrigin(t *testing.T) {
	in := []types.Citation{
		{ID: "a", PMID: "1", Title: "T", SourceOrigin: []string{"pubmed"}, CitedBy: 5},
		{ID: "b", PMID: "1", Title: "T", SourceOrigin: []string{"openalex", "s2"}, CitedBy: 3},
	}
	out := Dedupe(in)
	if len(out) != 1 {
		t.Fatalf("got %d", len(out))
	}
	if len(out[0].SourceOrigin) != 3 {
		t.Errorf("SourceOrigin = %v, want 3 merged", out[0].SourceOrigin)
	}
	// Check sorted.
	got := strings.Join(out[0].SourceOrigin, ",")
	if got != "openalex,pubmed,s2" {
		t.Errorf("SourceOrigin = %q, want \"openalex,pubmed,s2\"", got)
	}
}

func TestGroupKey(t *testing.T) {
	cases := []struct {
		c    *types.Citation
		want string
	}{
		{&types.Citation{PMID: "31535829"}, "pmid:31535829"},
		{&types.Citation{DOI: "10.1234/X"}, "doi:10.1234/x"}, // lowercase
		{&types.Citation{}, ""},
		{&types.Citation{PMID: "1", DOI: "10.1/x"}, "pmid:1"}, // PMID takes priority
	}
	for _, c := range cases {
		if got := groupKey(c.c); got != c.want {
			t.Errorf("groupKey(%+v) = %q, want %q", c.c, got, c.want)
		}
	}
}

func TestRichness(t *testing.T) {
	cases := []struct {
		c    *types.Citation
		want float64
	}{
		{&types.Citation{CitedBy: 100}, 100},
		{&types.Citation{FWCI: 1.5}, 15},
		{&types.Citation{CitedBy: 100, FWCI: 2.0, SourceOrigin: []string{"a", "b"}}, 130}, // 100 + 20 + 5*2
		{&types.Citation{}, 0},
	}
	for _, c := range cases {
		if got := richness(c.c); got != c.want {
			t.Errorf("richness(%+v) = %f, want %f", c.c, got, c.want)
		}
	}
}

func TestHammingDistance(t *testing.T) {
	a := "\x00\x00\x00\x00\x00\x00\x00\x00"
	b := "\x00\x00\x00\x00\x00\x00\x00\x01"
	if got := hammingDistance(a, b); got != 1 {
		t.Errorf("hammingDistance(diff 1 bit) = %d, want 1", got)
	}
	if got := hammingDistance(a, a); got != 0 {
		t.Errorf("hammingDistance(equal) = %d, want 0", got)
	}
	if got := hammingDistance(a, "\xff\xff\xff\xff\xff\xff\xff\xff"); got != 64 {
		t.Errorf("hammingDistance(all bits) = %d, want 64", got)
	}
}

func TestSimHash(t *testing.T) {
	h1 := simhash("Hello World")
	h2 := simhash("Hello World")
	if h1 != h2 {
		t.Errorf("simhash not deterministic: %x vs %x", h1, h2)
	}
	if len(h1) != 8 {
		t.Errorf("simhash len = %d, want 8", len(h1))
	}
	// Similar strings → small hamming distance.
	h3 := simhash("Hello World!")
	d := hammingDistance(h1, h3)
	if d > 5 {
		t.Errorf("similar strings hamming = %d, want ≤ 5", d)
	}
	// Empty string → empty fingerprint.
	if simhash("") != "" {
		t.Error("simhash of empty should be empty")
	}
}
