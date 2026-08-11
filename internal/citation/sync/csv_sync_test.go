package sync

import (
	"os"
	"path/filepath"
	"testing"
)

// TestCanonicalSchemaFrozen guards against silent schema drift.
// If you change CanonicalHeader intentionally, update both:
//  1. The CanonicalHeader slice in csv_sync.go
//  2. The Feishu spreadsheet b03e59 column headers
//  3. This test (only if the column NAMES change)
func TestCanonicalSchemaFrozen(t *testing.T) {
	want := []string{
		"PPT页",
		"第几条",
		"引用语义（上下文）",
		"PPT中的文献引用 完整字段",
		"DOI",
		"类型",
		"对应PDF文件",
		"来源链接 → 阅读全文",
	}
	if len(CanonicalHeader) != len(want) {
		t.Fatalf("CanonicalHeader length: got %d, want %d",
			len(CanonicalHeader), len(want))
	}
	for i, w := range want {
		if CanonicalHeader[i] != w {
			t.Errorf("CanonicalHeader[%d]: got %q, want %q",
				i, CanonicalHeader[i], w)
		}
	}
}

func TestVerifyHeader_Valid(t *testing.T) {
	if err := VerifyHeader(CanonicalHeader); err != nil {
		t.Errorf("canonical header should pass: %v", err)
	}
}

func TestVerifyHeader_WrongCount(t *testing.T) {
	bad := []string{"A", "B", "C"}
	if err := VerifyHeader(bad); err == nil {
		t.Error("3-col header should fail (want 8)")
	}
}

func TestVerifyHeader_WrongName(t *testing.T) {
	bad := make([]string, len(CanonicalHeader))
	copy(bad, CanonicalHeader)
	bad[3] = "Wrong Name" // Reference column
	if err := VerifyHeader(bad); err == nil {
		t.Error("renamed column should fail")
	}
}

func TestVerifyHeader_BOMStrictlyChecked(t *testing.T) {
	// VerifyHeader is strict: BOM-containing header fails.
	// ReadCSVRows strips BOM from the first cell BEFORE calling VerifyHeader.
	withBOM := make([]string, len(CanonicalHeader))
	copy(withBOM, CanonicalHeader)
	withBOM[0] = "\ufeff" + CanonicalHeader[0]
	if err := VerifyHeader(withBOM); err == nil {
		t.Error("BOM in header cell should fail VerifyHeader (strict mode)")
	}
}

func TestReadWriteCSVRoundTrip(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "test.csv")

	original := [][]string{
		{"3", "1", "PPT标号1: 左半区主标题", "GLOBOCAN 2022", "10.3322/caac.21834", "数据", "P3-1/P3-1_main.pdf", "🎯 Row 2 (P3-1)..."},
		{"3", "2", "PPT标号2: 右半区主标题", "健康中国行动", "备注: 无 DOI", "指南", "P3-2/P3-2_main.pdf", "🎯 Row 3 (P3-2)..."},
		// 包含中文双引号 "..." (会被 csv 自动转义)
		{"3", "3", `引用包含"嵌套引号"`, "Zeng 2024", "10.1016/j.jncc.2024.06.005", "文献", "P3-3/P3-3_main.pdf", "🎯 Row 4..."},
	}

	// Write
	if err := WriteCSVRows(path, nil, original); err != nil {
		t.Fatalf("write: %v", err)
	}

	// Read back
	hdr, rows, err := ReadCSVRows(path)
	if err != nil {
		t.Fatalf("read: %v", err)
	}
	if len(hdr) != 8 {
		t.Errorf("header length: got %d, want 8", len(hdr))
	}
	if len(rows) != 3 {
		t.Errorf("rows length: got %d, want 3", len(rows))
	}

	// Cell-by-cell compare
	for i, want := range original {
		for j, wcell := range want {
			if rows[i][j] != wcell {
				t.Errorf("row %d col %d: got %q, want %q",
					i, j, rows[i][j], wcell)
			}
		}
	}
}

func TestReadCSV_BadHeader(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "bad.csv")

	// Write file with no header
	content := "\ufeff" + `3,1,foo,bar,baz,qux,quux,corge
4,2,foo,bar,baz,qux,quux,corge
`
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	_, _, err := ReadCSVRows(path)
	if err == nil {
		t.Error("should fail: header row '3,1,foo...' doesn't match canonical schema")
	}
}

func TestReadCSV_MissingHeader(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "noheader.csv")

	// Write file with NO header, just data
	content := `3,1,foo,bar,baz,qux,quux,corge
`
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	_, _, err := ReadCSVRows(path)
	if err == nil {
		t.Error("should fail: no canonical header in file")
	}
}

func TestWriteCSV_BadHeaderRefused(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "bad.csv")

	bad := []string{"A", "B", "C"}
	if err := WriteCSVRows(path, bad, nil); err == nil {
		t.Error("should refuse to write with bad header")
	}
}

func TestWriteCSV_BadRowCountRefused(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "bad.csv")

	// Row with wrong column count
	rows := [][]string{{"a", "b"}} // only 2 cols, want 8
	if err := WriteCSVRows(path, nil, rows); err == nil {
		t.Error("should refuse to write row with wrong column count")
	}
}

func TestDiffRow_NoDifference(t *testing.T) {
	row := []string{"3", "1", "ctx", "ref", "doi", "type", "file", "url"}
	if diff := DiffRow(row, row); diff != "" {
		t.Errorf("identical rows should have no diff: %q", diff)
	}
}

func TestDiffRow_FirstCellDiffers(t *testing.T) {
	local := []string{"3", "1", "ctx", "ref", "doi", "type", "file", "url"}
	feishu := []string{"4", "1", "ctx", "ref", "doi", "type", "file", "url"}
	diff := DiffRow(local, feishu)
	want := `column A: local="3" feishu="4"`
	if diff != want {
		t.Errorf("got %q, want %q", diff, want)
	}
}

func TestDiffRow_TrimmedCompare(t *testing.T) {
	// Trailing whitespace should not trigger a diff
	local := []string{"3", "1", "ctx", "ref", "doi", "type", "file", "url"}
	feishu := []string{"3", "1", "ctx", "ref", "doi", "type", "file", "url  "}
	if diff := DiffRow(local, feishu); diff != "" {
		t.Errorf("trailing whitespace should be trimmed: %q", diff)
	}
}

func TestColumnLetter(t *testing.T) {
	cases := map[int]string{
		0:  "A",
		1:  "B",
		7:  "H",
		25: "Z",
		26: "AA",
		27: "AB",
	}
	for input, want := range cases {
		got := columnLetter(input)
		if got != want {
			t.Errorf("columnLetter(%d): got %q, want %q", input, got, want)
		}
	}
}
