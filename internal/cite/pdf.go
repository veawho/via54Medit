// PdfExtractor extracts text from PDF files using pdftotext (poppler).
package cite

import (
	"fmt"
	"os/exec"
	"strings"
)

// PdfExtractor uses pdftotext to extract text page-by-page.
type PdfExtractor struct {
	filePath     string
	pdftotextBin string
}

// NewPdfExtractor creates an extractor for the given PDF file.
func NewPdfExtractor(filePath string) *PdfExtractor {
	return &PdfExtractor{filePath: filePath, pdftotextBin: "pdftotext"}
}

// SetPdftotextBin overrides the path to pdftotext.
func (e *PdfExtractor) SetPdftotextBin(bin string) {
	e.pdftotextBin = bin
}

func (e *PdfExtractor) Type() string { return "pdf" }

// ExtractPages returns (page_number, text) for each page.
// pdftotext -layout with separate per-page extraction via fdfgen is not used;
// instead we extract the whole doc and split by page-form markers.
func (e *PdfExtractor) ExtractPages() (map[int]string, error) {
	// pdftotext -layout file -  writes to stdout, page breaks via form-feed (\f)
	// For multi-page docs, we get a continuous text stream with \f between pages.

	// Check binary exists
	_, err := exec.LookPath(e.pdftotextBin)
	if err != nil {
		return nil, fmt.Errorf("cite: pdftotext not found (install poppler: brew install poppler)")
	}

	cmd := exec.Command(e.pdftotextBin, "-layout", e.filePath, "-")
	data, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("cite: pdftotext failed: %w", err)
	}

	raw := string(data)

	// Split on form-feed (\f)
	pages := strings.Split(raw, "\f")
	result := make(map[int]string)
	for i, p := range pages {
		text := strings.TrimSpace(p)
		if text != "" {
			result[i+1] = text // 1-based page number
		}
	}

	if len(result) == 0 {
		return nil, fmt.Errorf("cite: no text extracted from PDF")
	}

	return result, nil
}

// ---------------------------------------------------------------------------
// For citation extraction from PDFs, we don't need context — pdftotext
// is fast and synchronous. The only async case would be very large PDFs,
// which is rare for citation extraction (usually reference lists are small).
// ---------------------------------------------------------------------------
