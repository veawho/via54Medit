// Package commands wires the 13 medit CLI subcommands.
//
// This file replaces the Phase 0 stub pubmed command with the real
// implementation that talks to NCBI E-utilities.
//
// Subcommands:
//
//	medit pubmed search <query> [--max N] [--json]
//	    Search PubMed and print citations (default text, --json for JSON).
//	medit pubmed fetch <PMID> [--json]
//	    Fetch metadata for a single PMID.
//	medit pubmed efetch <PMID>
//	    Fetch raw XML for a single PMID.
package commands

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"time"

	"github.com/spf13/cobra"

	"github.com/veawho/via54Medit/internal/source"
	"github.com/veawho/via54Medit/pkg/types"
)

// pubmedCmd is the parent command. All pubmed subcommands attach here.
var pubmedCmd = &cobra.Command{
	Use:   "pubmed",
	Short: "Search and fetch from PubMed (NCBI E-utilities)",
	Long: `pubmed provides direct access to NCBI's E-utilities API.

Examples:
  medit pubmed search "SGLT2 heart failure" --max 10
  medit pubmed fetch 31535829
  medit pubmed efetch 31535829`,
}

// pubmedSearchCmd implements `medit pubmed search`.
var pubmedSearchCmd = &cobra.Command{
	Use:   "search <query>",
	Short: "Search PubMed and return up to N citations",
	Args:  cobra.MinimumNArgs(1),
	RunE:  runPubmedSearch,
}

// pubmedFetchCmd implements `medit pubmed fetch`.
var pubmedFetchCmd = &cobra.Command{
	Use:   "fetch <PMID>",
	Short: "Fetch metadata for a single PMID",
	Args:  cobra.ExactArgs(1),
	RunE:  runPubmedFetch,
}

// pubmedEfetchCmd implements `medit pubmed efetch` (raw XML).
var pubmedEfetchCmd = &cobra.Command{
	Use:   "efetch <PMID>",
	Short: "Fetch raw XML for a single PMID (advanced)",
	Args:  cobra.ExactArgs(1),
	RunE:  runPubmedEfetch,
}

var (
	pubmedMax   int
	pubmedJSON  bool
	pubmedEmail string
	pubmedKey   string
)

func init() {
	pubmedSearchCmd.Flags().IntVar(&pubmedMax, "max", 20, "Maximum number of citations to return")
	pubmedSearchCmd.Flags().BoolVar(&pubmedJSON, "json", false, "Output JSON instead of human-readable text")
	pubmedSearchCmd.Flags().StringVar(&pubmedEmail, "email", "", "NCBI contact email (improves rate limit)")
	pubmedSearchCmd.Flags().StringVar(&pubmedKey, "api-key", "", "NCBI API key (improves rate limit to 10/s)")

	pubmedFetchCmd.Flags().BoolVar(&pubmedJSON, "json", false, "Output JSON instead of human-readable text")
	pubmedFetchCmd.Flags().StringVar(&pubmedEmail, "email", "", "NCBI contact email")
	pubmedFetchCmd.Flags().StringVar(&pubmedKey, "api-key", "", "NCBI API key")

	pubmedEfetchCmd.Flags().StringVar(&pubmedEmail, "email", "", "NCBI contact email")
	pubmedEfetchCmd.Flags().StringVar(&pubmedKey, "api-key", "", "NCBI API key")

	pubmedCmd.AddCommand(pubmedSearchCmd, pubmedFetchCmd, pubmedEfetchCmd)
}

func runPubmedSearch(cmd *cobra.Command, args []string) error {
	ctx, cancel := context.WithTimeout(cmd.Context(), 60*time.Second)
	defer cancel()

	src, err := source.NewPubMedSource(buildPubmedConfig())
	if err != nil {
		return fmt.Errorf("pubmed: init: %w", err)
	}

	cites, err := src.Search(ctx, types.EBMQuestion{
		Query:      args[0],
		Intent:     types.IntentSearch,
		MaxResults: pubmedMax,
	}, pubmedMax)
	if err != nil {
		return fmt.Errorf("pubmed search: %w", err)
	}

	return outputCitations(cmd, cites)
}

func runPubmedFetch(cmd *cobra.Command, args []string) error {
	ctx, cancel := context.WithTimeout(cmd.Context(), 30*time.Second)
	defer cancel()

	pmid := args[0]
	if _, err := strconv.Atoi(pmid); err != nil {
		return fmt.Errorf("pubmed fetch: invalid PMID %q: %w", pmid, err)
	}

	// Reuse Search: passing the PMID as a query would also work
	// (esearch matches PMIDs), but Search returns esummary metadata
	// which is exactly what fetch is meant to do. The current
	// PubMedSource.Search implementation handles this case.
	src, err := source.NewPubMedSource(buildPubmedConfig())
	if err != nil {
		return fmt.Errorf("pubmed: init: %w", err)
	}
	cites, err := src.Search(ctx, types.EBMQuestion{
		Query:  pmid,
		Intent: types.IntentSearch,
	}, 1)
	if err != nil {
		return fmt.Errorf("pubmed fetch: %w", err)
	}
	if len(cites) == 0 {
		return fmt.Errorf("pubmed fetch: no result for PMID %s", pmid)
	}
	return outputCitations(cmd, cites)
}

func runPubmedEfetch(cmd *cobra.Command, args []string) error {
	// efetch returns raw XML. Phase 1.5 uses the public esummary
	// endpoint which already returns XML; the underlying Source
	// doesn't expose raw XML in Phase 1.5. Print a helpful message
	// instead of pretending.
	pmid := args[0]
	if _, err := strconv.Atoi(pmid); err != nil {
		return fmt.Errorf("pubmed efetch: invalid PMID %q: %w", pmid, err)
	}
	fmt.Fprintf(os.Stderr, "pubmed efetch: raw XML for PMID %s\n", pmid)
	fmt.Fprintf(os.Stderr, "Visit: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=%s\n", pmid)
	fmt.Fprintf(os.Stderr, "Note: Phase 1.5 ships JSON via `medit pubmed fetch`. Raw XML output is Phase 2.\n")
	return nil
}

func buildPubmedConfig() map[string]any {
	return map[string]any{
		"enabled":    true,
		"email":      pubmedEmail,
		"api_key":    pubmedKey,
		"rate_limit": 3,
	}
}

// outputCitations writes the citations in the requested format.
func outputCitations(cmd *cobra.Command, cites []types.Citation) error {
	out := cmd.OutOrStdout()
	if pubmedJSON {
		enc := json.NewEncoder(out)
		enc.SetIndent("", "  ")
		return enc.Encode(cites)
	}
	if len(cites) == 0 {
		fmt.Fprintln(out, "(no results)")
		return nil
	}
	for i, c := range cites {
		fmt.Fprintf(out, "[%d] %s\n", i+1, c.Title)
		if c.Journal != "" {
			journal := c.Journal
			if c.Year > 0 {
				journal = fmt.Sprintf("%s (%d)", journal, c.Year)
			}
			fmt.Fprintf(out, "    %s\n", journal)
		}
		if len(c.Authors) > 0 {
			authors := c.Authors
			if len(authors) > 3 {
				authors = append(authors[:3], "et al.")
			}
			fmt.Fprintf(out, "    Authors: %v\n", authors)
		}
		if c.PMID != "" {
			fmt.Fprintf(out, "    PMID: %s\n", c.PMID)
		}
		if c.DOI != "" {
			fmt.Fprintf(out, "    DOI:  %s\n", c.DOI)
		}
		if c.Abstract != "" {
			abs := c.Abstract
			if len(abs) > 300 {
				abs = abs[:300] + "..."
			}
			fmt.Fprintf(out, "    %s\n", abs)
		}
		fmt.Fprintln(out)
	}
	return nil
}
