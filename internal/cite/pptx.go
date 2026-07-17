// PptxExtractor wraps the existing internal/pptx package.
// It extracts (page_number, full_slide_text) from a .pptx file
// by reading all slide XML + notesSlide XML via <a:t> runs.
package cite

import (
	"archive/zip"
	"encoding/xml"
	"fmt"
	"io"
	"os"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

// PptxExtractor reads a .pptx as a ZIP and extracts text from slides + notes.
type PptxExtractor struct {
	filePath string
}

// NewPptxExtractor creates an extractor for the given .pptx file.
func NewPptxExtractor(filePath string) *PptxExtractor {
	return &PptxExtractor{filePath: filePath}
}

func (e *PptxExtractor) Type() string { return "pptx" }

// ExtractPages reads the PPTX and returns (slideNumber, fullText).
// slideNumber is 1-based. Notes are appended with a [NOTES: ...] prefix.
func (e *PptxExtractor) ExtractPages() (map[int]string, error) {
	if _, err := os.Stat(e.filePath); os.IsNotExist(err) {
		return nil, fmt.Errorf("cite: file not found: %s", e.filePath)
	}

	f, err := zip.OpenReader(e.filePath)
	if err != nil {
		return nil, fmt.Errorf("cite: cannot open zip: %w", err)
	}
	defer f.Close()

	result := make(map[int]string)

	var slideFiles []string
	notesFiles := make(map[int]string) // slide number → notes content

	for _, entry := range f.File {
		if strings.HasPrefix(entry.Name, "ppt/slides/slide") && strings.HasSuffix(entry.Name, ".xml") {
			slideFiles = append(slideFiles, entry.Name)
		}
		if strings.HasPrefix(entry.Name, "ppt/notesSlides/notesSlide") && strings.HasSuffix(entry.Name, ".xml") {
			idx := extractSlideNum(entry.Name)
			if idx > 0 {
				rc, err := entry.Open()
				if err == nil {
					data, _ := io.ReadAll(rc)
					rc.Close()
					notesFiles[idx] = extractSlideText(data)
				}
			}
		}
	}

	sort.Strings(slideFiles)

	for _, name := range slideFiles {
		idx := extractSlideNum(name)
		if idx == 0 {
			continue
		}
		rc, err := entryForFile(f.File, name)
		if err != nil {
			continue
		}
		data, _ := io.ReadAll(rc)
		rc.Close()

		mainText := extractSlideText(data)
		if notes := notesFiles[idx]; notes != "" {
			mainText += "\n[NOTES: " + notes + "]"
		}
		result[idx] = mainText
	}

	return result, nil
}

// ---------------------------------------------------------------------------
// XML helpers (copied from internal/pptx — minimal dependency)
// ---------------------------------------------------------------------------

type PptxText struct {
	XMLName xml.Name `xml:"t"`
	Text    string   `xml:",chardata"`
}

type PptxTextBody struct {
	Any []PptxText `xml:"t"`
}

func extractSlideText(data []byte) string {
	// Try XML unmarshalling first
	var body PptxTextBody
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

	// Fallback: regex — text between last '>' and '</a:t>'
	re := regexp.MustCompile(`>([^<]{1,500})</a:t>`)
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

func extractSlideNum(name string) int {
	re := regexp.MustCompile(`(\d+)\.xml$`)
	m := re.FindStringSubmatch(name)
	if len(m) < 2 {
		return 0
	}
	n, _ := strconv.Atoi(m[1])
	return n
}

func entryForFile(entries []*zip.File, name string) (io.ReadCloser, error) {
	for _, e := range entries {
		if e.Name == name {
			return e.Open()
		}
	}
	return nil, fmt.Errorf("entry not found: %s", name)
}
