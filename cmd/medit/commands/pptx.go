package commands

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"

	"github.com/spf13/cobra"
	"github.com/veawho/via54Medit/internal/pptx"
)

// pptxCmd is the "medit pptx" top-level subcommand.
var pptxCmd = &cobra.Command{
	Use:   "pptx",
	Short: "Extract and verify citations from PowerPoint (.pptx) files",
	Long: `Extract citations embedded in .pptx slide XML, verify them against
PubMed/Crossref/Semantic Scholar, and classify downloadability (Sci-Hub / OA / Nexus).

Outputs a JSON array of CitationEntry records.`,
}

// pptxVerifyCmd extracts + verifies citations in a .pptx.
var pptxVerifyCmd = &cobra.Command{
	Use:     "verify [file.pptx]",
	Short:   "Extract and verify citations from a .pptx file",
	Long:    `Run the full citation pipeline: extract → parse → verify (PubMed + Crossref + S2) → downloadability check.`,
	Example: `medit pptx verify deck.pptx
medit pptx verify deck.pptx --json`,
	Args:    cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		return runVerify(args[0], false)
	},
}

// pptxExtractCmd extracts citation lines only (no network calls).
var pptxExtractCmd = &cobra.Command{
	Use:     "extract [file.pptx]",
	Short:   "Extract citation lines from a .pptx file (offline)",
	Long:    `Extract raw citation-like lines from slide XML without calling any academic APIs.`,
	Args:    cobra.ExactArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		return runVerify(args[0], true)
	},
}

func runVerify(path string, offline bool) error {
	if _, err := os.Stat(path); os.IsNotExist(err) {
		return fmt.Errorf("file not found: %s", path)
	}

	if offline {
		// Offline path: extract only
		extractor := pptx.NewExtractor(path)
		slideTexts, err := extractor.ExtractText()
		if err != nil {
			return fmt.Errorf("pptx extract: %w", err)
		}
		lines := pptx.ExtractCitationLines(slideTexts)
		entries := make([]pptx.CitationEntry, len(lines))
		for i, line := range lines {
			e := pptx.ParseCitationLine(line.RawText)
			e.SlideIndex = line.SlideIndex
			entries[i] = e
		}
		return printResult(entries)
	}

	// Full path: extract → verify → classify
	result, err := pptx.VerifyAll(context.Background(), path)
	if err != nil {
		return err
	}
	return printResult(result.Entries)
}

func printResult(entries []pptx.CitationEntry) error {
	// Sort by slide index
	sort.Slice(entries, func(i, j int) bool {
		return entries[i].SlideIndex < entries[j].SlideIndex
	})

	if len(entries) == 0 {
		fmt.Fprintln(os.Stderr, "no citations found")
		return nil
	}

	// Print summary table
	fmt.Fprint(os.Stdout, "\n")
	fmt.Fprintf(os.Stdout, "%-4s %-30s %-10s %-12s %-10s %s\n",
		"Slide", "Authors", "Journal", "Year", "Status", "DownloadTier")
	fmt.Fprint(os.Stdout, strings.Repeat("-", 100)+"\n")
	for _, e := range entries {
		authors := truncate(e.Authors, 28)
		journal := truncate(e.Journal, 10)
		year := fmt.Sprintf("%d", e.Year)
		status := e.Status
		if status == "" {
			status = "—"
		}
		tier := e.DownloadTier
		if tier == "" {
			tier = "—"
		}
		fmt.Fprintf(os.Stdout, "%-4d %-30s %-10s %-12s %-10s %s\n",
			e.SlideIndex, authors, journal, year, status, tier)
	}
	fmt.Fprint(os.Stdout, "\n")

	// Print JSON block
	pretty, err := json.MarshalIndent(entries, "", "  ")
	if err != nil {
		return fmt.Errorf("json marshal: %w", err)
	}
	fmt.Fprint(os.Stdout, "\n--- JSON ---\n")
	fmt.Fprint(os.Stdout, string(pretty))
	fmt.Fprint(os.Stdout, "\n")

	return nil
}

func truncate(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max-1] + "…"
}
