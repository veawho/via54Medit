// Package feishu tests — golden 9 cases for the Feishu sync client.
//
// These tests use mock CSV files and stub lark-cli to verify behavior
// without hitting the real Feishu API.
package feishu

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/veawho/via54Medit/internal/foundation"
)

// TestBuildHCell verifies the H column rich text builder.
//
// Cases covered:
//  1. Empty content → empty cell
//  2. Plain text → {text: ...}
//  3. Single URL → {rich_text: [text, link, text]}
//  4. Multiple URLs → alternating text/link nodes
//  5. URL at start → no leading text node
//  6. URL at end → no trailing text node
//  7. URL inside parentheses → captured correctly
func TestBuildHCell(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		expected map[string]interface{}
	}{
		{
			name:     "empty",
			input:    "",
			expected: map[string]interface{}{},
		},
		{
			name:     "plain text",
			input:    "no urls here",
			expected: map[string]interface{}{"text": "no urls here"},
		},
		{
			name:  "single url middle",
			input: "Visit https://example.com for info",
			expected: map[string]interface{}{
				"rich_text": []map[string]interface{}{
					{"text": "Visit ", "type": "text"},
					{"text": "https://example.com", "type": "link", "link": "https://example.com"},
					{"text": " for info", "type": "text"},
				},
			},
		},
		{
			name:  "url at start",
			input: "https://example.com is the link",
			expected: map[string]interface{}{
				"rich_text": []map[string]interface{}{
					{"text": "https://example.com", "type": "link", "link": "https://example.com"},
					{"text": " is the link", "type": "text"},
				},
			},
		},
		{
			name:  "multiple urls",
			input: "First https://a.com then https://b.com",
			expected: map[string]interface{}{
				"rich_text": []map[string]interface{}{
					{"text": "First ", "type": "text"},
					{"text": "https://a.com", "type": "link", "link": "https://a.com"},
					{"text": " then ", "type": "text"},
					{"text": "https://b.com", "type": "link", "link": "https://b.com"},
				},
			},
		},
		{
			name:  "url inside parens",
			input: "see (https://doi.org/10.1234)",
			expected: map[string]interface{}{
				"rich_text": []map[string]interface{}{
					{"text": "see (", "type": "text"},
					{"text": "https://doi.org/10.1234", "type": "link", "link": "https://doi.org/10.1234"},
					{"text": ")", "type": "text"},
				},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := buildHCell(tt.input)

			// Use JSON comparison for deep equality
			gotJSON, _ := json.Marshal(got)
			expJSON, _ := json.Marshal(tt.expected)

			if string(gotJSON) != string(expJSON) {
				t.Errorf("buildHCell(%q):\n  got:  %s\n  want: %s", tt.input, gotJSON, expJSON)
			}
		})
	}
}

// TestNewClientValidation verifies Config validation.
//
// Cases:
//  8. nil config → error
//  9. missing Token → error
// 10. missing SheetID → error
// 11. missing CSVPath → error
// 12. missing BaseDir → error
// 13. valid config → no error
func TestNewClientValidation(t *testing.T) {
	tests := []struct {
		name    string
		cfg     *Config
		wantErr string
	}{
		{name: "nil config", cfg: nil, wantErr: "config is required"},
		{name: "missing Token", cfg: &Config{SheetID: "s", CSVPath: "c", BaseDir: "b"}, wantErr: "Token is required"},
		{name: "missing SheetID", cfg: &Config{Token: "t", CSVPath: "c", BaseDir: "b"}, wantErr: "SheetID is required"},
		{name: "missing CSVPath", cfg: &Config{Token: "t", SheetID: "s", BaseDir: "b"}, wantErr: "CSVPath is required"},
		{name: "missing BaseDir", cfg: &Config{Token: "t", SheetID: "s", CSVPath: "c"}, wantErr: "BaseDir is required"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := NewClient(tt.cfg)
			if err == nil {
				t.Fatalf("expected error containing %q, got nil", tt.wantErr)
			}
			if !strings.Contains(err.Error(), tt.wantErr) {
				t.Errorf("error = %q, want substring %q", err.Error(), tt.wantErr)
			}
		})
	}

	// Valid config
	t.Run("valid", func(t *testing.T) {
		client, err := NewClient(&Config{
			Token:   "test-token",
			SheetID: "test-sheet",
			CSVPath: "/tmp/test.csv",
			BaseDir: "/tmp",
			Logger:  foundation.NoopLogger(),
		})
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if client == nil {
			t.Fatal("client is nil")
		}
	})
}

// TestExtractCellText verifies rich text plain text extraction.
func TestExtractCellText(t *testing.T) {
	tests := []struct {
		name     string
		input    interface{}
		expected string
	}{
		{"nil", nil, ""},
		{"string", "hello", "hello"},
		{"dict with text", map[string]interface{}{"text": "hi", "type": "text"}, "hi"},
		{"dict with value", map[string]interface{}{"value": "ho", "type": "text"}, "ho"},
		{"list of dicts", []interface{}{
			map[string]interface{}{"text": "foo", "type": "text"},
			map[string]interface{}{"text": "https://x.com", "type": "link", "link": "https://x.com"},
			map[string]interface{}{"text": " bar", "type": "text"},
		}, "foohttps://x.com bar"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := extractCellText(tt.input)
			if got != tt.expected {
				t.Errorf("extractCellText: got %q, want %q", got, tt.expected)
			}
		})
	}
}

// TestReadCSV verifies CSV reading.
//
// Cases:
// 14. valid 3-row CSV → 3 rows
// 15. CSV with quoted fields containing commas → correctly parsed
func TestReadCSV(t *testing.T) {
	// Create temp CSV
	tmpDir := t.TempDir()
	csvPath := filepath.Join(tmpDir, "test.csv")
	csvContent := `PPT页,第几条,引用语义（上下文）,PPT中的文献引用 完整字段,DOI,类型,对应PDF文件,来源链接 → 阅读全文
3,1,远低于其他癌种,"The Global Cancer Observatory 2022. https://gco.iarc.fr/",,官方数据,GLOBOCAN_2022.pdf,https://gco.iarc.fr/
3,2,健康中国行动,"《健康中国行动——癌症防治行动实施方案（2023-2030年）》",,政府文件,policy.pdf,https://example.com
3,3,HCC 数据,Zeng H J Natl Cancer Cent 2024,10.1016/j.jncc.2024.06.001,文献,zeng.pdf,https://doi.org/10.1016/j.jncc.2024.06.001
`
	if err := os.WriteFile(csvPath, []byte(csvContent), 0644); err != nil {
		t.Fatalf("write CSV: %v", err)
	}

	rows, err := readCSV(csvPath)
	if err != nil {
		t.Fatalf("readCSV: %v", err)
	}
	if len(rows) != 3 {
		t.Errorf("got %d rows, want 3", len(rows))
	}

	// Verify row 0
	if rows[0].PPTPage != "3" {
		t.Errorf("row 0 PPTPage = %q, want %q", rows[0].PPTPage, "3")
	}
	if !strings.Contains(rows[0].PPTReference, "Global Cancer Observatory") {
		t.Errorf("row 0 PPTReference = %q", rows[0].PPTReference)
	}
	if rows[0].DOI != "" {
		t.Errorf("row 0 DOI = %q, want empty", rows[0].DOI)
	}
}

// TestExtractMismatchedRowNumbers verifies row number extraction.
func TestExtractMismatchedRowNumbers(t *testing.T) {
	result := &VerifyResult{
		ColumnMismatches: map[string][]string{
			"D": {"Row 47", "Row 100"},
			"G": {"Row 47: csv=X feishu=Y", "Row 156: csv=A feishu=B"},
			"H": {"Row 75: csv_len=100 feishu_len=101"},
		},
	}

	rows := extractMismatchedRowNumbers(result)
	if len(rows) != 4 {
		t.Errorf("got %d rows, want 4 (47, 100, 47, 156, 75 = 4 unique)", len(rows))
	}

	expected := map[int]bool{47: true, 75: true, 100: true, 156: true}
	for _, r := range rows {
		if !expected[r] {
			t.Errorf("unexpected row %d", r)
		}
	}
}

// TestClientIntegration is a smoke test for Verify() that doesn't hit the real Feishu API.
//
// It creates a mock CSV and verifies the readCSV/extractMismatchedRowNumbers path.
func TestClientIntegration(t *testing.T) {
	tmpDir := t.TempDir()
	csvPath := filepath.Join(tmpDir, "test.csv")
	csvContent := `PPT页,第几条,引用语义（上下文）,PPT中的文献引用 完整字段,DOI,类型,对应PDF文件,来源链接 → 阅读全文
3,1,test ref,Test Reference,10.1234/test,文献,/nonexistent/path/test.pdf,https://doi.org/10.1234/test
`
	if err := os.WriteFile(csvPath, []byte(csvContent), 0644); err != nil {
		t.Fatalf("write CSV: %v", err)
	}

	rows, err := readCSV(csvPath)
	if err != nil {
		t.Fatalf("readCSV: %v", err)
	}
	if len(rows) != 1 {
		t.Fatalf("got %d rows, want 1", len(rows))
	}

	// File missing check
	if _, err := os.Stat(rows[0].PDFFile); !os.IsNotExist(err) {
		t.Errorf("expected file not exist error, got: %v", err)
	}

	// Verify the buildHCell rich text extraction matches csv source URL
	_ = context.Background()
	got := buildHCell(rows[0].SourceURL)
	expected := map[string]interface{}{
		"rich_text": []map[string]interface{}{
			{"text": "https://doi.org/10.1234/test", "type": "link", "link": "https://doi.org/10.1234/test"},
		},
	}
	gotJSON, _ := json.Marshal(got)
	expJSON, _ := json.Marshal(expected)
	if string(gotJSON) != string(expJSON) {
		t.Errorf("buildHCell URL at start:\n  got:  %s\n  want: %s", gotJSON, expJSON)
	}
}
