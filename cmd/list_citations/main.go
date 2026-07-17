package main

import (
	"encoding/json"
	"fmt"
	"log"
	"strings"

	"github.com/veawho/via54Medit/internal/pptx"
)

func main() {
	path := "/Users/david/Downloads/标准答案/【原始文件】雷管方案：三重获益，引领uHCC一线治疗新标准_0622.pptx"
	ext := pptx.NewExtractor(path)
	slideTexts, err := ext.ExtractText()
	if err != nil {
		log.Fatalf("ExtractText failed: %s", err)
	}

	fmt.Printf("Total slides with text: %d\n", len(slideTexts))

	lines := pptx.ExtractCitationLines(slideTexts)
	if len(lines) == 0 {
		fmt.Println("\n⚠️  No citations found!")
		return
	}

	fmt.Printf("Total citation candidates: %d\n", len(lines))
	fmt.Println(strings.Repeat("=", 60))
	fmt.Println("ALL CITATIONS FOUND:")
	fmt.Println(strings.Repeat("=", 60))

	for i, line := range lines {
		entry := pptx.ParseCitationLine(line.RawText)
		fmt.Printf("\n[%d] Slide %d\n", i+1, line.SlideIndex)
		fmt.Printf("    Raw: %s\n", line.RawText)
		if entry.PMID != "" {
			fmt.Printf("    PMID: %s\n", entry.PMID)
		}
		if entry.DOI != "" {
			// entry.DOI is already string - check directly
			fmt.Printf("    DOI:  %s\n", entry.DOI)
		}
		if entry.Year != 0 {
			fmt.Printf("    Year: %d\n", entry.Year)
		}
		if entry.Journal != "" {
			fmt.Printf("    Journal: %s\n", entry.Journal)
		}
		if entry.Pages != "" {
			fmt.Printf("    Pages: %s\n", entry.Pages)
		}
	}

	jsonBytes, _ := json.MarshalIndent(lines, "", "  ")
	fmt.Printf("\n\n=== JSON OUTPUT ===\n%s\n", string(jsonBytes))
}
