// Package sync provides CSV ↔ Feishu sync for citation tables.
//
// Iron rule (2026-08-01, user-taught):
//
//	citation_table.csv MUST have a header row matching the canonical
//	schema below. Every row (data + header) must equal the corresponding
//	Feishu cell. Mismatch = data corruption.
//
// Schema (matches Feishu spreadsheet column headers, frozen 2026-08-01):
//
//	"PPT页"                            - SlidePage (e.g. "3", "4", ..., "43")
//	"第几条"                            - CiteIndex (1, 2, 3, ...)
//	"引用语义（上下文）"                - Context (D column: PPT position + claim)
//	"PPT中的文献引用 完整字段"          - Reference (full citation string)
//	"DOI"                               - DOI (or "备注: 无 DOI ..." for non-DOI)
//	"类型"                              - DocType (文献/数据/指南/EDITORIAL/...)
//	"对应PDF文件"                       - PDFFile (e.g. "P3-1/P3-1_main_xxx.pdf")
//	"来源链接 → 阅读全文"               - SourceURL (H column, rich text)
package sync

import (
	"encoding/csv"
	"fmt"
	"io"
	"os"
	"strings"
)

// CanonicalHeader is the frozen column order for citation_table.csv.
// Last reviewed 2026-08-01 against Feishu spreadsheet b03e59.
//
// Update with care: any change to this slice breaks every existing
// citation_table.csv file. The sync.Verify() method will fail loudly.
var CanonicalHeader = []string{
	"PPT页",
	"第几条",
	"引用语义（上下文）",
	"PPT中的文献引用 完整字段",
	"DOI",
	"类型",
	"对应PDF文件",
	"来源链接 → 阅读全文",
}

// ReadCSVRows reads a citation_table.csv and returns (header, data).
//
// Behavior:
//   - BOM is auto-stripped from the first cell of the header.
//   - The first non-empty line is taken as the header.
//   - Subsequent non-empty lines are data rows.
//   - Empty lines are skipped.
//   - Any internal quote/escape is handled by encoding/csv.
//
// If the header doesn't match CanonicalHeader, ReadCSVRows returns an
// error. This is by design: the iron rule says CSV must mirror Feishu.
//
// Example:
//
//	hdr, rows, err := ReadCSVRows("/path/to/citation_table.csv")
//	if err != nil { log.Fatal(err) }
//	for _, row := range rows { ... }
func ReadCSVRows(path string) (header []string, rows [][]string, err error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, nil, fmt.Errorf("open csv: %w", err)
	}
	defer f.Close()

	r := csv.NewReader(f)
	r.FieldsPerRecord = -1 // variable, allow any number of fields per row

	// First record = header
	hdr, err := r.Read()
	if err == io.EOF {
		return nil, nil, fmt.Errorf("empty csv: %s", path)
	}
	if err != nil {
		return nil, nil, fmt.Errorf("read header: %w", err)
	}

	// Strip BOM from first header cell
	if len(hdr) > 0 {
		hdr[0] = strings.TrimPrefix(hdr[0], "\ufeff")
	}

	// Validate header against canonical schema
	if err := VerifyHeader(hdr); err != nil {
		return nil, nil, fmt.Errorf("header validation failed: %w (got: %v)", err, hdr)
	}

	// Remaining records = data
	for {
		rec, err := r.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, nil, fmt.Errorf("read data row: %w", err)
		}
		// Skip blank lines (single empty cell from CSV writer trailing newline)
		if len(rec) == 1 && strings.TrimSpace(rec[0]) == "" {
			continue
		}
		rows = append(rows, rec)
	}

	return hdr, rows, nil
}

// VerifyHeader checks hdr against CanonicalHeader.
//
// Returns nil if hdr matches exactly, otherwise an error describing the
// first mismatch (count or cell value).
//
// This is the gatekeeper for the iron rule. Call it from:
//   - ReadCSVRows (auto-validation on read)
//   - CSV writers after constructing a new row
//   - Tests
func VerifyHeader(hdr []string) error {
	if len(hdr) != len(CanonicalHeader) {
		return fmt.Errorf("column count mismatch: got %d, want %d",
			len(hdr), len(CanonicalHeader))
	}
	for i, want := range CanonicalHeader {
		got := strings.TrimSpace(hdr[i])
		if got != want {
			return fmt.Errorf("column %d (%s) mismatch: got %q, want %q",
				i+1, columnLetter(i), got, want)
		}
	}
	return nil
}

// WriteCSVRows writes (header + data rows) to path with the canonical
// schema enforced. If header is empty, the canonical header is written
// automatically. If header is non-empty, it must match the canonical
// header or WriteCSVRows returns an error.
//
// The output is UTF-8 with BOM (so Excel + Lark + pandas all read it
// correctly). Internal quotes are auto-escaped by encoding/csv.
func WriteCSVRows(path string, header []string, rows [][]string) error {
	if len(header) == 0 {
		header = CanonicalHeader
	}
	if err := VerifyHeader(header); err != nil {
		return fmt.Errorf("header validation failed: %w", err)
	}

	// Validate each data row has the expected column count
	for i, row := range rows {
		if len(row) != len(CanonicalHeader) {
			return fmt.Errorf("row %d: column count %d, want %d",
				i+2, len(row), len(CanonicalHeader)) // +2 for 1-based + header
		}
	}

	f, err := os.Create(path)
	if err != nil {
		return fmt.Errorf("create csv: %w", err)
	}
	defer f.Close()

	// Write UTF-8 BOM for Excel/Lark/pandas compatibility
	if _, err := f.Write([]byte{0xEF, 0xBB, 0xBF}); err != nil {
		return fmt.Errorf("write bom: %w", err)
	}

	w := csv.NewWriter(f)
	if err := w.Write(header); err != nil {
		return fmt.Errorf("write header: %w", err)
	}
	for _, row := range rows {
		if err := w.Write(row); err != nil {
			return fmt.Errorf("write row: %w", err)
		}
	}
	w.Flush()
	if err := w.Error(); err != nil {
		return fmt.Errorf("flush: %w", err)
	}
	return nil
}

// columnLetter converts 0-based column index to A1 notation letter.
// 0 -> "A", 1 -> "B", ..., 25 -> "Z", 26 -> "AA", ...
func columnLetter(i int) string {
	s := ""
	for i >= 0 {
		s = string(rune('A'+(i%26))) + s
		i = i/26 - 1
	}
	return s
}

// DiffRow reports differences between a local CSV row and a Feishu row.
// Returns nil if all cells match. Otherwise returns a string describing
// the first mismatch (column index, local value, feishu value).
//
// Both row slices must have the same length as CanonicalHeader. The
// caller is responsible for ensuring this.
func DiffRow(localRow, feishuRow []string) string {
	for i := 0; i < len(CanonicalHeader); i++ {
		if i >= len(localRow) || i >= len(feishuRow) {
			return fmt.Sprintf("column %s: local=%d feishu=%d fields",
				columnLetter(i), len(localRow), len(feishuRow))
		}
		l := strings.TrimSpace(localRow[i])
		f := strings.TrimSpace(feishuRow[i])
		if l != f {
			return fmt.Sprintf("column %s: local=%q feishu=%q",
				columnLetter(i), l, f)
		}
	}
	return ""
}
