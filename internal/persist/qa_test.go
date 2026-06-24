package persist

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/veawho/via54Medit/pkg/types"
)

func TestNewQAStore(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "qa")
	s, err := NewQAStore(dir)
	if err != nil {
		t.Fatal(err)
	}
	if s == nil {
		t.Fatal("got nil store")
	}
	// Verify dir was created.
	if _, err := os.Stat(dir); err != nil {
		t.Errorf("dir not created: %v", err)
	}
}

func TestSaveAndLoad(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "qa")
	s, _ := NewQAStore(dir)
	ep := &types.EvidencePackage{
		ConvID:   "conv-test-123",
		Question: types.EBMQuestion{Query: "SGLT2 heart failure"},
		Summary:  "Test summary",
		Citations: []types.Citation{
			{Title: "DAPA-HF", PMID: "31535829", Year: 2019},
		},
		SourcesUsed: map[string]int{"pubmed": 1, "openalex": 1},
		CreatedAt:   time.Now(),
		Duration:    2 * time.Second,
	}
	if err := s.Save(ep); err != nil {
		t.Fatal(err)
	}
	got, err := s.Load(ep.ConvID)
	if err != nil {
		t.Fatal(err)
	}
	if got.ConvID != ep.ConvID {
		t.Errorf("ConvID = %q, want %q", got.ConvID, ep.ConvID)
	}
	if got.Summary != ep.Summary {
		t.Errorf("Summary = %q, want %q", got.Summary, ep.Summary)
	}
	if len(got.Citations) != 1 {
		t.Errorf("Citations = %d, want 1", len(got.Citations))
	}
	if got.SourcesUsed["pubmed"] != 1 {
		t.Errorf("SourcesUsed[pubmed] = %d, want 1", got.SourcesUsed["pubmed"])
	}
}

func TestSaveCreatesMarkdown(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "qa")
	s, _ := NewQAStore(dir)
	ep := &types.EvidencePackage{
		ConvID:      "conv-md-1",
		Question:    types.EBMQuestion{Query: "test"},
		Summary:     "A test summary",
		Citations:   []types.Citation{{Title: "T1", PMID: "1"}},
		SourcesUsed: map[string]int{"pubmed": 1},
		CreatedAt:   time.Now(),
	}
	if err := s.Save(ep); err != nil {
		t.Fatal(err)
	}
	md, err := os.ReadFile(filepath.Join(dir, "conv-md-1.md"))
	if err != nil {
		t.Fatal(err)
	}
	got := string(md)
	if !strings.Contains(got, "# via54Medit Evidence Package") {
		t.Error("md missing header")
	}
	if !strings.Contains(got, "test") {
		t.Error("md missing question text")
	}
	if !strings.Contains(got, "A test summary") {
		t.Error("md missing summary")
	}
}

func TestSaveNil(t *testing.T) {
	s, _ := NewQAStore(t.TempDir())
	if err := s.Save(nil); err == nil {
		t.Error("Save(nil) should fail")
	}
}

func TestSaveEmptyConvID(t *testing.T) {
	s, _ := NewQAStore(t.TempDir())
	ep := &types.EvidencePackage{ConvID: ""}
	if err := s.Save(ep); err == nil {
		t.Error("Save with empty ConvID should fail")
	}
}

func TestListEmpty(t *testing.T) {
	s, _ := NewQAStore(t.TempDir())
	ids, err := s.List()
	if err != nil {
		t.Fatal(err)
	}
	if len(ids) != 0 {
		t.Errorf("got %d ids, want 0", len(ids))
	}
}

func TestListSortedByModTime(t *testing.T) {
	dir := t.TempDir()
	s, _ := NewQAStore(dir)
	// Save 3 packages with deliberate time gaps.
	for _, id := range []string{"conv-old", "conv-mid", "conv-new"} {
		ep := &types.EvidencePackage{ConvID: id, Question: types.EBMQuestion{Query: id}, CreatedAt: time.Now()}
		if err := s.Save(ep); err != nil {
			t.Fatal(err)
		}
		time.Sleep(10 * time.Millisecond) // ensure mtime differs
	}
	ids, err := s.List()
	if err != nil {
		t.Fatal(err)
	}
	if len(ids) != 3 {
		t.Fatalf("got %d, want 3", len(ids))
	}
	// Newest first.
	if ids[0] != "conv-new" {
		t.Errorf("ids[0] = %q, want conv-new (newest)", ids[0])
	}
	if ids[2] != "conv-old" {
		t.Errorf("ids[2] = %q, want conv-old (oldest)", ids[2])
	}
}

func TestDelete(t *testing.T) {
	dir := t.TempDir()
	s, _ := NewQAStore(dir)
	ep := &types.EvidencePackage{
		ConvID: "conv-del", Question: types.EBMQuestion{Query: "x"}, CreatedAt: time.Now(),
	}
	_ = s.Save(ep)
	if _, err := s.Load(ep.ConvID); err != nil {
		t.Fatal(err)
	}
	if err := s.Delete(ep.ConvID); err != nil {
		t.Fatal(err)
	}
	if _, err := s.Load(ep.ConvID); err == nil {
		t.Error("Load after Delete should fail")
	}
}

func TestDeleteMissingIsOK(t *testing.T) {
	s, _ := NewQAStore(t.TempDir())
	if err := s.Delete("nonexistent"); err != nil {
		t.Errorf("Delete missing should be no-op, got: %v", err)
	}
}

func TestSafeFilename(t *testing.T) {
	cases := []struct {
		in, want string
	}{
		{"conv-123", "conv-123"},
		{"conv/with/slashes", "conv_with_slashes"},
		{"a:b*c?d", "a_b_c_d"},
		{"", "unnamed"},
		{"你好", "__"}, // 2 non-ASCII runes → 2 underscores
	}
	for _, c := range cases {
		if got := safeFilename(c.in); got != c.want {
			t.Errorf("safeFilename(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestAtomicWrite(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "test.txt")
	if err := atomicWrite(path, []byte("hello")); err != nil {
		t.Fatal(err)
	}
	got, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != "hello" {
		t.Errorf("got %q, want hello", got)
	}
	// Verify no leftover .tmp-* files.
	entries, _ := os.ReadDir(dir)
	for _, e := range entries {
		if strings.HasPrefix(e.Name(), ".tmp-") {
			t.Errorf("leftover temp file: %s", e.Name())
		}
	}
}

func TestRenderMarkdownHasKeyFields(t *testing.T) {
	ep := &types.EvidencePackage{
		ConvID:      "test",
		Question:    types.EBMQuestion{Query: "SGLT2"},
		Summary:     "Summary text",
		Citations:   []types.Citation{{Title: "Paper", PMID: "12345", Year: 2020}},
		SourcesUsed: map[string]int{"pubmed": 1},
		CreatedAt:   time.Now(),
	}
	md := renderMarkdown(ep)
	for _, want := range []string{"via54Medit", "test", "Summary text", "Paper", "12345", "pubmed"} {
		if !strings.Contains(md, want) {
			t.Errorf("md missing %q", want)
		}
	}
}

func TestLoadInvalidJSON(t *testing.T) {
	dir := t.TempDir()
	s, _ := NewQAStore(dir)
	path := filepath.Join(dir, "bad.json")
	if err := os.WriteFile(path, []byte("not json"), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := s.Load("bad"); err == nil {
		t.Error("Load of invalid JSON should fail")
	}
}

// keep the json import in case future tests use it
var _ = json.Marshal
