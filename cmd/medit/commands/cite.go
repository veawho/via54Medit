// cite.go — CLI for citation extraction and verification (PPTX/PDF/DOCX)
// Renamed all internal functions with "cite" prefix to avoid conflicts
// with pptx.go (runVerify) and pico_grade.go (runList).
package commands

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"
	"github.com/veawho/via54Medit/internal/cite"
)

// NewCiteCommand returns the root "cite" subcommand with extract/verify/list.
func NewCiteCommand() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "cite <command>",
		Short: "Extract and verify citations from PPTX/PDF/DOCX",
		Long: `Extract academic citations from PPTX, PDF, and DOCX documents,
enrich them via PubMed/Crossref, and output structured JSON.

Usage:
  medit cite extract <file>   — extract citations (offline)
  medit cite verify <file>   — extract + verify via PubMed/Crossref
  medit cite list <file>     — extract + list in markdown table
`,
	}

	cmd.AddCommand(&cobra.Command{
		Use:   "extract <file>",
		Short: "Extract citations from a document (offline)",
		RunE: func(cmd *cobra.Command, args []string) error {
			if len(args) < 1 {
				return fmt.Errorf("missing file path argument")
			}
			return citeCmdExtract(args[0])
		},
	})

	cmd.AddCommand(&cobra.Command{
		Use:   "verify <file>",
		Short: "Extract citations and verify via PubMed/Crossref",
		RunE: func(cmd *cobra.Command, args []string) error {
			if len(args) < 1 {
				return fmt.Errorf("missing file path argument")
			}
			return citeCmdVerify(args[0])
		},
	})

	cmd.AddCommand(&cobra.Command{
		Use:   "list <file>",
		Short: "Extract citations and display as markdown table",
		RunE: func(cmd *cobra.Command, args []string) error {
			if len(args) < 1 {
				return fmt.Errorf("missing file path argument")
			}
			return citeCmdList(args[0])
		},
	})

	return cmd
}

// ---- helpers (scoped to this file) ----

func citeCmdExtract(file string) error {
	citations, err := citeCmdRunPipeline(file)
	if err != nil {
		return err
	}
	data, _ := json.MarshalIndent(citations, "", "  ")
	fmt.Println(string(data))
	citeCmdPrintSummary(citations, file)
	return nil
}

func citeCmdVerify(file string) error {
	citations, err := citeCmdRunPipeline(file)
	if err != nil {
		return err
	}
	fmt.Printf("[verify] verifying %d citations via PubMed/Crossref...\n", len(citations))
	pipeline, err := cite.NewPipeline(file)
	if err != nil {
		return fmt.Errorf("pipeline: %w", err)
	}
	pipeline.VerifyAll(citations)

	data, _ := json.MarshalIndent(citations, "", "  ")
	fmt.Println(string(data))
	citeCmdPrintVerifySummary(citations, file)
	return nil
}

func citeCmdList(file string) error {
	citations, err := citeCmdRunPipeline(file)
	if err != nil {
		return err
	}
	fmt.Printf("# Citations from %s\n\n", filepath.Base(file))
	fmt.Println("| # | Slide/Page | Authors | Journal | Year | PMID | Status |")
	fmt.Println("|---|------------|---------|---------|------|------|--------|")
	for i, c := range citations {
		fmt.Printf("| %d | %d | %s | %s | %d | %s | %s |\n",
			i+1, c.PageIndex, c.Authors, c.Journal, c.Year, c.PMID, c.Status)
	}
	fmt.Printf("\n# Total: %d citations\n", len(citations))
	return nil
}

func citeCmdRunPipeline(file string) ([]cite.Citation, error) {
	if _, err := os.Stat(file); os.IsNotExist(err) {
		return nil, fmt.Errorf("file not found: %s", file)
	}
	ext := strings.ToLower(filepath.Ext(file))
	fmt.Fprintf(os.Stderr, "[cite] extracting citations from %s (%s)...\n", file, ext)
	pipeline, err := cite.NewPipeline(file)
	if err != nil {
		return nil, fmt.Errorf("pipeline: %w", err)
	}
	citations, err := pipeline.Run(nil)
	if err != nil {
		return nil, fmt.Errorf("extract: %w", err)
	}
	fmt.Fprintf(os.Stderr, "[cite] found %d citation candidates\n", len(citations))
	return citations, nil
}

func citeCmdPrintSummary(citations []cite.Citation, file string) {
	fmt.Fprintf(os.Stderr, "\n--- Summary: %s ---\n", filepath.Base(file))
	fmt.Fprintf(os.Stderr, "Total citations: %d\n", len(citations))
}

func citeCmdPrintVerifySummary(citations []cite.Citation, file string) {
	fmt.Fprintf(os.Stderr, "\n--- Verification Summary: %s ---\n", filepath.Base(file))
	verified, unverified, errCount := 0, 0, 0
	for _, c := range citations {
		switch c.Status {
		case "verified":
			verified++
		case "unverified":
			unverified++
		case "error":
			errCount++
		}
	}
	fmt.Fprintf(os.Stderr, "Verified: %d\nUnverified: %d\nErrors: %d\nTotal: %d\n",
		verified, unverified, errCount, len(citations))
}
