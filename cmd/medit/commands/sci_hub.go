// Package commands - sci-hub subcommand.
//
// sci-hub resolves a DOI or PMID to a Sci-Hub PDF URL.
// It is NOT a search engine — Sci-Hub mirrors only respond to
// canonical identifiers (DOI or PMID).
//
// Usage:
//
//	medit sci-hub --force-enable --mirrors "sci-hub.se,sci-hub.ru" "10.1038/s41586-021-03621-9"
//	medit sci-hub --force-enable 31535829
//
// ⚠️ Sci-Hub operates in a legal grey area in many jurisdictions.
// This command:
//   - resolves URLs only (no PDF download in this layer)
//   - logs every request to ~/.medit/audit/ for transparency
//   - is disabled by default — must pass --force-enable or enable in config
package commands

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/spf13/cobra"
	"github.com/veawho/via54Medit/internal/source"
)

var (
	sciHubMirrors string // comma-separated mirror URLs
	sciHubTimeout time.Duration
	sciHubForce   bool // override config and enable Sci-Hub for this run
	sciHubNoWarn  bool // suppress compliance warning
)

var sciHubCmd = &cobra.Command{
	Use:   "sci-hub <doi|pmid>",
	Short: "Resolve a DOI or PMID to a Sci-Hub PDF URL",
	Long: `Resolve a DOI or PMID to a Sci-Hub PDF URL.

Sci-Hub is NOT a search engine — it only responds to canonical
identifiers (DOI or PMID). Use medit ask / medit search to find
papers first, then use medit sci-hub to get the PDF URL.

Examples:
  medit sci-hub --force-enable --mirrors "sci-hub.se,sci-hub.ru" "10.1038/s41586-021-03621-9"
  medit sci-hub --force-enable 31535829
  medit sci-hub --force-enable --no-warn "10.xxxx/..."

⚠️  Sci-Hub operates in a legal grey area in many jurisdictions.
   This command resolves URLs only (no download). All requests
   are logged to ~/.medit/audit/ for transparency.
   By default it is disabled — pass --force-enable to use.`,
	Args: cobra.MinimumNArgs(1),
	RunE: runSciHub,
}

func init() {
	sciHubCmd.Flags().StringVar(&sciHubMirrors, "mirrors", "",
		"Comma-separated Sci-Hub mirror URLs (default: sci-hub.se,sci-hub.ru,sci-hub.st)")
	sciHubCmd.Flags().DurationVar(&sciHubTimeout, "timeout", 60*time.Second,
		"Total wall-clock timeout")
	sciHubCmd.Flags().BoolVar(&sciHubForce, "force-enable", false,
		"Override config and enable Sci-Hub for this run (required unless config has enabled=true)")
	sciHubCmd.Flags().BoolVar(&sciHubNoWarn, "no-warn", false,
		"Suppress the legal/compliance warning")
}

func runSciHub(cmd *cobra.Command, args []string) error {
	// Compliance warning (not suppressible at this stage — Phase 1.5 adds
	// a config-level flag to permanently dismiss).
	if !sciHubNoWarn {
		fmt.Fprintln(os.Stderr, "⚠️  WARNING: Sci-Hub operates in a legal grey area in many")
		fmt.Fprintln(os.Stderr, "   jurisdictions. This command resolves URLs only (no download).")
		fmt.Fprintln(os.Stderr, "   All requests are logged to ~/.medit/audit/ for transparency.")
		fmt.Fprintln(os.Stderr, "   Use --no-warn to suppress this warning.")
		fmt.Fprintln(os.Stderr)
	}

	ctx, cancel := context.WithTimeout(cmd.Context(), sciHubTimeout)
	defer cancel()

	identifier := strings.Join(args, " ")

	cfg := map[string]any{"enabled": sciHubForce}
	if sciHubMirrors != "" {
		cfg["mirrors"] = sciHubMirrors
	}

	s, err := source.NewSciHubSource(cfg)
	if err != nil {
		return fmt.Errorf("sci-hub: %w", err)
	}

	if !s.Enabled() {
		return fmt.Errorf("sci-hub is disabled. Pass --force-enable to use it, " +
			"or enable in ~/.medit/config.yaml (sources.sci_hub.enabled: true)")
	}

	// Resolve the identifier
	out := cmd.OutOrStdout()
	fmt.Fprintf(out, "Resolving: %s\n", identifier)

	pdfURL, err := s.Resolve(ctx, identifier)
	if err != nil {
		return fmt.Errorf("sci-hub resolve failed: %w", err)
	}

	fmt.Fprintf(out, "Sci-Hub URL: %s\n", pdfURL)
	return nil
}
