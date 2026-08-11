// Package commands — gscholar subcommand.
//
// gscholar queries Google Scholar via HTML scraping.
//
// Usage:
//
//	medit gscholar "lung cancer immunotherapy"
//	medit gscholar --query "heart failure" --limit 5
//
// ⚠️  Compliance note: Scraping Google Scholar violates its Terms of
//
//	Service. This command is disabled by default and logs every
//	request to ~/.medit/audit/.
package commands

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/spf13/cobra"
	"github.com/veawho/via54Medit/internal/source"
	"github.com/veawho/via54Medit/pkg/types"
)

var (
	gsQuery  string
	gsLimit  int
	gsRate   int  // req/min
	gsForce  bool // force-enable even when disabled
	gsNoWarn bool // suppress compliance warning
	gsJSON   bool // JSON output
)

var gScholarCmd = &cobra.Command{
	Use:   "gscholar <query>",
	Short: "Search Google Scholar via scraping",
	Long: `Search Google Scholar for medical literature citations.

Google Scholar has no official API — this command scrapes the HTML
search results page.

Examples:
  medit gscholar --force-enable "lung cancer immunotherapy"
  medit gscholar --force-enable "heart failure" --limit 5
  medit gscholar --force-enable --no-warn "diabetes" --json

⚠️  Compliance note: Scraping Google Scholar violates its Terms of
   Service in many jurisdictions. This command:
   - is disabled by default (pass --force-enable to use)
   - uses conservative rate limiting (6 req/min)
   - logs every request to ~/.medit/audit/`,
	Args: cobra.MaximumNArgs(1),
	RunE: runGScholar,
}

func init() {
	gScholarCmd.Flags().StringVarP(&gsQuery, "query", "q", "",
		"Search query (required if no positional argument)")
	gScholarCmd.Flags().IntVarP(&gsLimit, "limit", "n", 10,
		"Maximum results to return")
	gScholarCmd.Flags().IntVar(&gsRate, "rate", 6,
		"Rate limit in requests per minute")
	gScholarCmd.Flags().BoolVar(&gsForce, "force-enable", false,
		"Override config and enable Google Scholar for this run")
	gScholarCmd.Flags().BoolVar(&gsNoWarn, "no-warn", false,
		"Suppress the compliance warning")
	gScholarCmd.Flags().BoolVar(&gsJSON, "json", false,
		"Output results as JSON")
}

func runGScholar(cmd *cobra.Command, args []string) error {
	if !gsNoWarn {
		fmt.Fprintln(os.Stderr, "⚠️  WARNING: Scraping Google Scholar violates its Terms of")
		fmt.Fprintln(os.Stderr, "   Service in many jurisdictions. This command uses conservative")
		fmt.Fprintln(os.Stderr, "   rate limiting (6 req/min) and logs every request to")
		fmt.Fprintln(os.Stderr, "   ~/.medit/audit/. Use --no-warn to suppress this warning.")
		fmt.Fprintln(os.Stderr)
	}

	query := gsQuery
	if len(args) > 0 {
		query = strings.Join(args, " ")
	}
	if query == "" {
		return fmt.Errorf("gscholar: query required (pass positional arg or --query)")
	}

	if !gsForce {
		return fmt.Errorf("gscholar: disabled by default. Pass --force-enable to use, " +
			"or enable in ~/.medit/config.yaml (sources.gscholar.enabled: true)")
	}

	cfg := map[string]any{
		"enabled":    true,
		"rate_limit": gsRate,
	}

	s, err := source.NewGScholarSource(cfg)
	if err != nil {
		return fmt.Errorf("gscholar: %w", err)
	}

	ctx, cancel := context.WithTimeout(cmd.Context(), 45*time.Second)
	defer cancel()

	ebmQ := types.EBMQuestion{
		Query:      query,
		MaxResults: gsLimit,
	}

	out := cmd.OutOrStdout()

	cites, err := s.Search(ctx, ebmQ, gsLimit)
	if err != nil {
		return fmt.Errorf("gscholar search failed: %w", err)
	}

	if len(cites) == 0 {
		fmt.Fprintf(out, "Google Scholar returned no results for: %s\n", query)
		return nil
	}

	fmt.Fprintf(out, "Google Scholar results for: %s (%d results)\n\n", query, len(cites))

	for i, c := range cites {
		fmt.Fprintf(out, "[%d] %s\n", i+1, c.Title)
		if c.Authors != nil && len(c.Authors) > 0 {
			fmt.Fprintf(out, "    Authors: %s\n", strings.Join(c.Authors, ", "))
		}
		if c.Journal != "" {
			fmt.Fprintf(out, "    Journal: %s\n", c.Journal)
		}
		if c.Year > 0 {
			fmt.Fprintf(out, "    Year: %d\n", c.Year)
		}
		if c.CitedBy > 0 {
			fmt.Fprintf(out, "    Cited by: %d\n", c.CitedBy)
		}
		if c.DOI != "" {
			fmt.Fprintf(out, "    DOI: %s\n", c.DOI)
		}
		if c.OAPDFURL != "" {
			fmt.Fprintf(out, "    PDF: %s\n", c.OAPDFURL)
		}
		if c.Abstract != "" {
			// Truncate abstract for display
			abs := c.Abstract
			if len(abs) > 120 {
				abs = abs[:120] + "..."
			}
			fmt.Fprintf(out, "    Abstract: %s\n", abs)
		}
		fmt.Fprintln(out)
	}

	fmt.Fprintf(out, "Total: %d results\n", len(cites))

	return nil
}
