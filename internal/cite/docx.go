// DocxExtractor extracts text from .docx files using python-docx via subprocess.
// The .docx is a ZIP; we unzip it and extract text from document.xml <w:t> runs.
package cite

import (
	"archive/zip"
	"encoding/xml"
	"fmt"
	"io"
	"os"
	"regexp"
	"strings"
)

// DocxExtractor reads a .docx as a ZIP and extracts text from all paragraphs.
type DocxExtractor struct {
	filePath string
}

// NewDocxExtractor creates an extractor for the given .docx file.
func NewDocxExtractor(filePath string) *DocxExtractor {
	return &DocxExtractor{filePath: filePath}
}

func (e *DocxExtractor) Type() string { return "docx" }

// ExtractPages returns (page_number, full_text) for the docx.
// DOCX does not have explicit page boundaries in its XML, so we extract
// all text and group it into paragraphs. Page numbering is simulated
// by paragraph count (rough: ~30 paragraphs per page for body text).
// For citation extraction this is good enough — we just need the text.
func (e *DocxExtractor) ExtractPages() (map[int]string, error) {
	if _, err := os.Stat(e.filePath); os.IsNotExist(err) {
		return nil, fmt.Errorf("cite: file not found: %s", e.filePath)
	}

	f, err := zip.OpenReader(e.filePath)
	if err != nil {
		return nil, fmt.Errorf("cite: cannot open zip: %w", err)
	}
	defer f.Close()

	var bodyText string
	for _, entry := range f.File {
		if entry.Name == "word/document.xml" || entry.Name == "word/body.xml" {
			rc, err := entry.Open()
			if err != nil {
				continue
			}
			data, _ := io.ReadAll(rc)
			rc.Close()
			bodyText = extractDocxText(data)
			break
		}
	}

	if bodyText == "" {
		return nil, fmt.Errorf("cite: no text extracted from docx")
	}

	// Split text into paragraphs (paragraph breaks in docx are between <w:p> tags)
	// Since we already joined with spaces, we split on sentence-ending patterns
	// For citation extraction, we return the whole text as one "page"
	// and let the citation finder do the rest.
	result := make(map[int]string)
	result[1] = bodyText

	return result, nil
}

// extractDocxText parses the document.xml and returns concatenated <w:t> text.
func extractDocxText(data []byte) string {
	// Try XML unmarshalling first (minimal namespace handling)
	var body struct {
		Any []DocxText `xml:"t"`
	}
	if err := xml.Unmarshal(data, &body); err == nil && len(body.Any) > 0 {
		var parts []string
		for _, t := range body.Any {
			s := strings.TrimSpace(t.Text)
			if s != "" {
				parts = append(parts, s)
			}
		}
		if len(parts) > 0 {
			return strings.Join(parts, " ")
		}
	}

	// Fallback: regex — text between last '>' and '</w:t>'
	re := regexp.MustCompile(`>([^<]{1,1000})</w:t>`)
	matches := re.FindAllSubmatch(data, -1)
	if len(matches) == 0 {
		return ""
	}
	var parts []string
	for _, m := range matches {
		s := strings.TrimSpace(string(m[1]))
		if s != "" {
			parts = append(parts, s)
		}
	}
	return strings.Join(parts, " ")
}

type DocxText struct {
	XMLName xml.Name `xml:"t"`
	Text    string   `xml:",chardata"`
}
