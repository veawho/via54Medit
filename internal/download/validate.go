// Package download provides layered full-text acquisition.
//
// validate.go — PDF validation after download to detect stub/empty pages.
package download

import (
	"bytes"
	"fmt"
	"os"
	"strings"
)

// PDFValidation holds the result of validating a downloaded PDF.
type PDFValidation struct {
	Path        string
	Size        int64
	Valid       bool
	PageCount   int
	HasContent  bool
	HasHeader   bool
	HasObjects  bool
	HasTrailer  bool
	IsPlainText bool // non-PDF file masquerading as .pdf
	Reason      string
}

// ValidatePDF checks whether the file at path is a valid, non-trivial PDF.
// It inspects: PDF header, xref table/trailer, object count, and content.
func ValidatePDF(path string) PDFValidation {
	r := PDFValidation{Path: path}

	stat, err := os.Stat(path)
	if err != nil {
		r.Reason = fmt.Sprintf("stat error: %v", err)
		return r
	}
	r.Size = stat.Size()

	if r.Size < 100 {
		r.Reason = fmt.Sprintf("too small (%d bytes)", r.Size)
		return r
	}

	data, err := os.ReadFile(path)
	if err != nil {
		r.Reason = fmt.Sprintf("read error: %v", err)
		return r
	}

	// Check PDF header
	r.HasHeader = bytes.HasPrefix(data, []byte("%PDF-"))
	if !r.HasHeader {
		// Check if it's actually HTML or text masquerading as PDF
		headStr := string(data[:min(len(data), 200)])
		if strings.Contains(headStr, "<!DOCTYPE html") ||
			strings.Contains(headStr, "<html") ||
			strings.Contains(headStr, "<HTML") {
			r.IsPlainText = true
			r.Reason = "HTML page (likely paywall/error), not PDF"
			return r
		}
		if bytes.Contains(data[:min(len(data), 100)], []byte("Page not found")) ||
			bytes.Contains(data[:min(len(data), 100)], []byte("404")) {
			r.IsPlainText = true
			r.Reason = "error page (404), not PDF"
			return r
		}
		r.Reason = "missing %PDF- header"
		return r
	}

	// Count PDF objects — use " obj" as separator (more reliable than \nobj)
	objCount := bytes.Count(data, []byte(" obj"))
	endobjCount := bytes.Count(data, []byte("endobj"))
	streamCount := bytes.Count(data, []byte("\nstream\n")) +
		bytes.Count(data, []byte("\nstream\r\n"))

	r.HasObjects = objCount > 0 && endobjCount > 0 && abs(objCount-endobjCount) <= 1
	if !r.HasObjects {
		r.Reason = fmt.Sprintf("object mismatch: %d obj vs %d endobj", objCount, endobjCount)
	}

	// Check xref / trailer
	r.HasTrailer = bytes.Contains(data, []byte("trailer")) &&
		(bytes.Contains(data, []byte("startxref")) || bytes.Contains(data, []byte("xref")))

	// Estimate page count from /Type /Page entries
	pageEntries := bytes.Count(data, []byte("/Type")) +
		bytes.Count(data, []byte("/Page\n"))
	r.PageCount = pageEntries
	r.HasContent = r.PageCount > 0 || streamCount > 0
	if !r.HasContent {
		r.Reason = "no /Type/Page entries and no streams"
	}

	r.Valid = r.HasHeader && r.HasObjects && r.HasTrailer && r.HasContent

	if r.Valid {
		r.Reason = fmt.Sprintf("valid PDF, ~%d page(s), %d streams", pageEntries, streamCount)
	}

	return r
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func abs(x int) int {
	if x < 0 {
		return -x
	}
	return x
}
