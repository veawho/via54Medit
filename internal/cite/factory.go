// Factory auto-detects document type from file extension and returns the right Extractor.
package cite

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// NewExtractor detects the document type from the file path and returns an Extractor.
// Supported: .pptx, .pdf, .docx (case-insensitive).
func NewExtractor(filePath string) (Extractor, error) {
	if _, err := os.Stat(filePath); os.IsNotExist(err) {
		return nil, fmt.Errorf("cite: file not found: %s", filePath)
	}

	ext := strings.ToLower(filepath.Ext(filePath))
	switch ext {
	case ".pptx":
		return NewPptxExtractor(filePath), nil
	case ".pdf":
		return NewPdfExtractor(filePath), nil
	case ".docx":
		return NewDocxExtractor(filePath), nil
	default:
		return nil, fmt.Errorf("cite: unsupported format: %s (supported: .pptx, .pdf, .docx)", ext)
	}
}
