package citation

import (
	"strings"
	"testing"
)

func TestBuildRichCell_Empty(t *testing.T) {
	got := BuildRichCell("")
	want := map[string]interface{}{"text": ""}
	if !mapsEqual(got, want) {
		t.Errorf("BuildRichCell('') = %v, want %v", got, want)
	}
}

func TestBuildRichCell_PlainText(t *testing.T) {
	got := BuildRichCell("hello world")
	want := map[string]interface{}{"text": "hello world"}
	if !mapsEqual(got, want) {
		t.Errorf("BuildRichCell('hello world') = %v, want %v", got, want)
	}
}

func TestBuildRichCell_SingleURL(t *testing.T) {
	got := BuildRichCell("see https://doi.org/10.1056/EVIDoa2100070")

	rt, ok := got["rich_text"].([]map[string]interface{})
	if !ok {
		t.Fatalf("expected rich_text array, got: %v", got)
	}
	if len(rt) != 2 {
		t.Fatalf("expected 2 nodes, got %d: %v", len(rt), rt)
	}
	if rt[0]["text"] != "see " || rt[0]["type"] != "text" {
		t.Errorf("node[0] = %v, want {text: 'see ', type: 'text'}", rt[0])
	}
	if rt[1]["text"] != "https://doi.org/10.1056/EVIDoa2100070" ||
		rt[1]["type"] != "link" ||
		rt[1]["link"] != "https://doi.org/10.1056/EVIDoa2100070" {
		t.Errorf("node[1] = %v, want link node", rt[1])
	}
}

func TestBuildRichCell_MultipleURLs(t *testing.T) {
	got := BuildRichCell("first https://a.com and https://b.com end")

	rt, ok := got["rich_text"].([]map[string]interface{})
	if !ok {
		t.Fatalf("expected rich_text array, got: %v", got)
	}
	if len(rt) != 5 {
		t.Fatalf("expected 5 nodes, got %d: %v", len(rt), rt)
	}
	// Expected: [text, link, text, link, text]
	expected := []struct{ text, typ string }{
		{"first ", "text"},
		{"https://a.com", "link"},
		{" and ", "text"},
		{"https://b.com", "link"},
		{" end", "text"},
	}
	for i, exp := range expected {
		if rt[i]["text"] != exp.text || rt[i]["type"] != exp.typ {
			t.Errorf("node[%d] = %v, want {text: %q, type: %q}", i, rt[i], exp.text, exp.typ)
		}
	}
}

func TestBuildRichCell_URLInsideParens(t *testing.T) {
	got := BuildRichCell("(https://example.com)")
	rt := got["rich_text"].([]map[string]interface{})
	if len(rt) != 3 {
		t.Fatalf("expected 3 nodes [(, link, )], got %d: %v", len(rt), rt)
	}
	if rt[0]["text"] != "(" || rt[0]["type"] != "text" {
		t.Errorf("node[0] = %v, want '(' text node", rt[0])
	}
	if rt[1]["text"] != "https://example.com" || rt[1]["type"] != "link" {
		t.Errorf("node[1] = %v, want link node", rt[1])
	}
	if rt[2]["text"] != ")" || rt[2]["type"] != "text" {
		t.Errorf("node[2] = %v, want ')' text node", rt[2])
	}
}

func TestBuildRichCell_TrailingNewlineStripped(t *testing.T) {
	got := BuildRichCell("content with trailing newline\n")
	want := map[string]interface{}{"text": "content with trailing newline"}
	if !mapsEqual(got, want) {
		t.Errorf("expected newline stripped, got: %v", got)
	}
}

func TestParseCell_String(t *testing.T) {
	c := ParseCell("hello")
	if c.String() != "hello" {
		t.Errorf("String = %q, want 'hello'", c.String())
	}
	if len(c.Nodes) != 1 || c.Nodes[0].Type != "text" {
		t.Errorf("expected 1 text node, got: %+v", c.Nodes)
	}
}

func TestParseCell_DictWithText(t *testing.T) {
	c := ParseCell(map[string]interface{}{"text": "hi", "type": "text"})
	if c.String() != "hi" {
		t.Errorf("String = %q, want 'hi'", c.String())
	}
}

func TestParseCell_DictWithValue(t *testing.T) {
	c := ParseCell(map[string]interface{}{"value": "value_field"})
	if c.String() != "value_field" {
		t.Errorf("String = %q, want 'value_field'", c.String())
	}
}

func TestParseCell_DictWithRichText(t *testing.T) {
	raw := map[string]interface{}{
		"rich_text": []interface{}{
			map[string]interface{}{"text": "foo ", "type": "text"},
			map[string]interface{}{"text": "https://a.com", "type": "link", "link": "https://a.com"},
			map[string]interface{}{"text": " bar", "type": "text"},
		},
	}
	c := ParseCell(raw)
	if c.String() != "foo https://a.com bar" {
		t.Errorf("String = %q, want 'foo https://a.com bar'", c.String())
	}
	if len(c.Nodes) != 3 {
		t.Errorf("expected 3 nodes, got %d", len(c.Nodes))
	}
}

func TestParseCell_ListOfDicts(t *testing.T) {
	raw := []interface{}{
		map[string]interface{}{"text": "a", "type": "text"},
		map[string]interface{}{"text": "b", "type": "text"},
	}
	c := ParseCell(raw)
	if c.String() != "ab" {
		t.Errorf("String = %q, want 'ab'", c.String())
	}
}

func TestParseCell_NestedList(t *testing.T) {
	raw := []interface{}{
		[]interface{}{
			map[string]interface{}{"text": "nested", "type": "text"},
		},
	}
	c := ParseCell(raw)
	if c.String() != "nested" {
		t.Errorf("String = %q, want 'nested'", c.String())
	}
}

func TestParseCell_Nil(t *testing.T) {
	c := ParseCell(nil)
	if !c.IsEmpty() {
		t.Errorf("nil should be empty, got: %+v", c)
	}
}

func TestCellsEqual_TrailingNewlineHandling(t *testing.T) {
	// Trailing newlines should be ignored for comparison (Feishu adds one).
	a := Cell{Nodes: []RichNode{{Text: "hello\n", Type: "text"}}}
	b := Cell{Nodes: []RichNode{{Text: "hello", Type: "text"}}}
	if !CellsEqual(a, b) {
		t.Errorf("trailing newline should be ignored in comparison")
	}
}

func TestCellsEqual_DifferentContent(t *testing.T) {
	a := Cell{Nodes: []RichNode{{Text: "hello", Type: "text"}}}
	b := Cell{Nodes: []RichNode{{Text: "world", Type: "text"}}}
	if CellsEqual(a, b) {
		t.Errorf("different content should not be equal")
	}
}

func TestCell_RoundTripBuildAndParse(t *testing.T) {
	// Round-trip: BuildRichCell → ParseCell → String
	// Original text with URL that doesn't have trailing space issue.
	original := "See https://example.com for details"
	built := BuildRichCell(original)
	c := ParseCell(map[string]interface{}{"rich_text": built["rich_text"]})

	if c.String() != original {
		t.Errorf("round-trip mismatch: got %q, want %q", c.String(), original)
	}
}

// mapsEqual compares two maps[string]interface{} for deep equality on
// the specific structures produced by BuildRichCell.
func mapsEqual(a, b map[string]interface{}) bool {
	if len(a) != len(b) {
		return false
	}
	for k, av := range a {
		bv, ok := b[k]
		if !ok {
			return false
		}
		// Compare text fields directly
		if k == "text" {
			if av != bv {
				return false
			}
		}
		if k == "rich_text" {
			aList, aOk := av.([]map[string]interface{})
			bList, bOk := bv.([]map[string]interface{})
			if !aOk || !bOk || len(aList) != len(bList) {
				return false
			}
			for i := range aList {
				if aList[i]["text"] != bList[i]["text"] ||
					aList[i]["type"] != bList[i]["type"] {
					return false
				}
				if aList[i]["link"] != bList[i]["link"] {
					return false
				}
			}
		}
	}
	return true
}

// Helper: ensure imports are used
var _ = strings.TrimSpace