package citation

import (
	"fmt"
	"regexp"
	"strings"
)

// urlPattern matches HTTP/HTTPS URLs.
// Excludes whitespace AND closing parenthesis (so URLs inside parens like
// "(https://example.com)" are captured correctly without trailing ")").
var urlPattern = regexp.MustCompile(`https?://[^\s\)\]]+`)

// Cell is the intermediate representation of a Feishu cell value.
//
// Feishu cells can be:
//   - string: plain text
//   - {value: "..."}: wrapped string
//   - {text: "..."}: text fragment
//   - {rich_text: [...]}: rich text array (Phase 2+)
//   - []interface{}: list of nodes (Phase 1)
//
// This package normalizes all forms to []RichNode.
type Cell struct {
	Nodes []RichNode
}

// RichNode is one node in a rich text cell.
type RichNode struct {
	Text string `json:"text"`
	Type string `json:"type"` // "text" | "link"
	Link string `json:"link,omitempty"`
}

// String returns the plain text of all nodes concatenated.
func (c Cell) String() string {
	var b strings.Builder
	for _, n := range c.Nodes {
		b.WriteString(n.Text)
	}
	return b.String()
}

// IsEmpty returns true if the cell has no content.
func (c Cell) IsEmpty() bool {
	return len(c.Nodes) == 0 || (len(c.Nodes) == 1 && c.Nodes[0].Text == "")
}

// ParseCell parses a Feishu cell value into a Cell.
//
// Handles all known Feishu cell formats (string, dict, list, nested list).
//
// Algorithm:
//  1. If string → wrap as [text node]
//  2. If dict with "rich_text" → flatten its list
//  3. If dict with "text" or "value" → wrap as single node
//  4. If list of dicts → each dict becomes a node
//  5. If list of lists → flatten recursively
//  6. Otherwise → convert to string and wrap as text node
func ParseCell(raw interface{}) Cell {
	switch v := raw.(type) {
	case nil:
		return Cell{}
	case string:
		if v == "" {
			return Cell{}
		}
		return Cell{Nodes: []RichNode{{Text: v, Type: "text"}}}
	case map[string]interface{}:
		return parseDictCell(v)
	case []interface{}:
		return parseListCell(v)
	default:
		// Fallback: stringify
		return Cell{Nodes: []RichNode{{Text: fmt.Sprintf("%v", v), Type: "text"}}}
	}
}

// parseDictCell handles {rich_text: [...]} and {text: "..."} / {value: "..."}.
func parseDictCell(d map[string]interface{}) Cell {
	if rt, ok := d["rich_text"]; ok {
		// Unwrap and parse the inner list. Note: Feishu may return either
		// []interface{} or []map[string]interface{} depending on encoding.
		switch list := rt.(type) {
		case []interface{}:
			return parseListCell(list)
		case []map[string]interface{}:
			// Convert to []interface{} for uniform processing
			asInterface := make([]interface{}, len(list))
			for i, item := range list {
				asInterface[i] = item
			}
			return parseListCell(asInterface)
		}
		return Cell{}
	}
	if t, ok := d["text"].(string); ok {
		return Cell{Nodes: []RichNode{{Text: t, Type: "text"}}}
	}
	if v, ok := d["value"].(string); ok {
		return Cell{Nodes: []RichNode{{Text: v, Type: "text"}}}
	}
	return Cell{}
}

// parseListCell handles a flat list of dicts, or nested list-of-lists.
func parseListCell(list []interface{}) Cell {
	var nodes []RichNode
	for _, item := range list {
		switch v := item.(type) {
		case map[string]interface{}:
			node := RichNode{
				Text: stringFromDict(v, "text", "value"),
				Type: stringFromDict(v, "type"),
				Link: stringFromDict(v, "link"),
			}
			if node.Type == "" {
				node.Type = "text"
			}
			if node.Text != "" {
				nodes = append(nodes, node)
			}
		case []interface{}:
			// Nested list — recurse
			sub := parseListCell(v)
			nodes = append(nodes, sub.Nodes...)
		case string:
			if v != "" {
				nodes = append(nodes, RichNode{Text: v, Type: "text"})
			}
		}
	}
	return Cell{Nodes: nodes}
}

func stringFromDict(d map[string]interface{}, keys ...string) string {
	for _, k := range keys {
		if v, ok := d[k]; ok {
			if s, ok := v.(string); ok {
				return s
			}
		}
	}
	return ""
}

// BuildRichCell converts plain text (with URLs) to a Feishu cell payload.
//
// Algorithm:
//  1. If empty content → return {text: ""} (empty cell)
//  2. Scan for URLs (https?://... non-whitespace, non-paren)
//  3. Split content into text/link/text/link segments
//  4. Wrap in {rich_text: [...]}
//
// Critical: must use {rich_text: [...]} envelope, NOT direct array.
//           must use type='link', NOT 'url'.
//
// Examples:
//
//	""                          → {"text": ""}
//	"hello world"               → {"text": "hello world"}
//	"see https://doi.org/..."   → {"rich_text": [{text: "see ", type: 'text'},
//	                                              {text: "https://doi.org/...", type: 'link', link: '...'}]
//	                                            }
//	"https://a.com and https://b.com"
//	                            → {rich_text: [{text: "https://a.com", type: 'link', ...},
//	                                            {text: " and ", type: 'text'},
//	                                            {text: "https://b.com", type: 'link', ...}]}
func BuildRichCell(content string) map[string]interface{} {
	content = strings.TrimSpace(content)
	if content == "" {
		return map[string]interface{}{"text": ""}
	}

	matches := urlPattern.FindAllStringIndex(content, -1)
	if len(matches) == 0 {
		return map[string]interface{}{"text": content}
	}

	parts := []map[string]interface{}{}
	lastEnd := 0
	for _, m := range matches {
		start, end := m[0], m[1]
		if start > lastEnd {
			parts = append(parts, map[string]interface{}{
				"text": content[lastEnd:start],
				"type": "text",
			})
		}
		url := content[start:end]
		parts = append(parts, map[string]interface{}{
			"text": url,
			"type": "link",
			"link": url,
		})
		lastEnd = end
	}
	if lastEnd < len(content) {
		parts = append(parts, map[string]interface{}{
			"text": content[lastEnd:],
			"type": "text",
		})
	}

	return map[string]interface{}{"rich_text": parts}
}

// CellsEqual compares two cells by their plain text representation.
func CellsEqual(a, b Cell) bool {
	return strings.TrimRight(a.String(), "\r\n") == strings.TrimRight(b.String(), "\r\n")
}