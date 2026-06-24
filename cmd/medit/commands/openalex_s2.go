// Package commands - openalex and s2 subcommands.
//
// Both wrap the corresponding Source adapter and print results in the
// same format as `medit pubmed search`. See pubmed.go for the
// outputCitations helper.
package commands

import (
	"context"
	"fmt"
	"time"

	"github.com/spf13/cobra"

	"github.com/veawho/via54Medit/internal/source"
	"github.com/veawho/via54Medit/pkg/types"
)

// --- openalex ---

var openalexCmd = &cobra.Command{
	Use:   "openalex",
	Short: "Search OpenAlex (200M+ scholarly works)",
	Long: `openalex provides direct access to the OpenAlex catalog.

Examples:
  medit openalex search "SGLT2 heart failure" --max 10
  medit openalex health`,
}

var openalexSearchCmd = &cobra.Command{
	Use:   "search <query>",
	Short: "Search OpenAlex and return up to N citations",
	Args:  cobra.MinimumNArgs(1),
	RunE:  runOpenalexSearch,
}

var openalexHealthCmd = &cobra.Command{
	Use:  "health",
	RunE: runOpenalexHealth,
}

var (
	openalexMax  int
	openalexMail string
)

func init() {
	openalexSearchCmd.Flags().IntVar(&openalexMax, "max", 20, "Maximum citations to return")
	openalexSearchCmd.Flags().BoolVar(&jsonOut, "json", false, "Output JSON")
	openalexSearchCmd.Flags().StringVar(&openalexMail, "email", "", "Polite-pool email (improves rate limit to 50/s)")

	openalexHealthCmd.Flags().StringVar(&openalexMail, "email", "", "Polite-pool email")

	openalexCmd.AddCommand(openalexSearchCmd, openalexHealthCmd)
}

func runOpenalexSearch(cmd *cobra.Command, args []string) error {
	ctx, cancel := context.WithTimeout(cmd.Context(), 60*time.Second)
	defer cancel()
	src, err := source.NewOpenAlexSource(map[string]any{
		"enabled": true, "email": openalexMail,
	})
	if err != nil {
		return err
	}
	cites, err := src.Search(ctx, types.EBMQuestion{Query: args[0], Intent: types.IntentSearch, MaxResults: openalexMax}, openalexMax)
	if err != nil {
		return fmt.Errorf("openalex search: %w", err)
	}
	return outputCitations(cmd, cites)
}

func runOpenalexHealth(cmd *cobra.Command, args []string) error {
	ctx, cancel := context.WithTimeout(cmd.Context(), 5*time.Second)
	defer cancel()
	src, _ := source.NewOpenAlexSource(map[string]any{"email": openalexMail})
	if err := src.Health(ctx); err != nil {
		return err
	}
	fmt.Fprintln(cmd.OutOrStdout(), "openalex: reachable")
	return nil
}

// --- s2 ---

var s2Cmd = &cobra.Command{
	Use:   "s2",
	Short: "Search Semantic Scholar (TLDR + FWCI)",
	Long: `s2 provides direct access to the Semantic Scholar Graph API.

Examples:
  medit s2 search "SGLT2 heart failure" --max 10
  medit s2 health`,
}

var s2SearchCmd = &cobra.Command{
	Use:   "search <query>",
	Short: "Search S2 and return up to N citations",
	Args:  cobra.MinimumNArgs(1),
	RunE:  runS2Search,
}

var s2HealthCmd = &cobra.Command{
	Use:  "health",
	RunE: runS2Health,
}

var (
	s2Max   int
	s2Key   string
	jsonOut bool
)

func init() {
	s2SearchCmd.Flags().IntVar(&s2Max, "max", 20, "Maximum citations")
	s2SearchCmd.Flags().BoolVar(&jsonOut, "json", false, "Output JSON")
	s2SearchCmd.Flags().StringVar(&s2Key, "api-key", "", "S2 API key (improves rate limit)")

	s2HealthCmd.Flags().StringVar(&s2Key, "api-key", "", "S2 API key")

	s2Cmd.AddCommand(s2SearchCmd, s2HealthCmd)
}

func runS2Search(cmd *cobra.Command, args []string) error {
	ctx, cancel := context.WithTimeout(cmd.Context(), 60*time.Second)
	defer cancel()
	src, err := source.NewS2Source(map[string]any{"api_key": s2Key})
	if err != nil {
		return err
	}
	cites, err := src.Search(ctx, types.EBMQuestion{Query: args[0], Intent: types.IntentSearch, MaxResults: s2Max}, s2Max)
	if err != nil {
		return fmt.Errorf("s2 search: %w", err)
	}
	return outputCitations(cmd, cites)
}

func runS2Health(cmd *cobra.Command, args []string) error {
	ctx, cancel := context.WithTimeout(cmd.Context(), 5*time.Second)
	defer cancel()
	src, _ := source.NewS2Source(map[string]any{"api_key": s2Key})
	if err := src.Health(ctx); err != nil {
		return err
	}
	fmt.Fprintln(cmd.OutOrStdout(), "s2: reachable")
	return nil
}
