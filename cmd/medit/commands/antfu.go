// Package commands wires the 13 medit CLI subcommands.
//
// This file replaces the Phase 0 stub antfu command with the real
// implementation that drives a Chrome instance via DevTools Protocol.
//
// Subcommands:
//
//	medit antfu ask <query> [--json]
//	    Send a question to chat.antafu.com and return extracted references.
//	medit antfu extract <file.html>
//	    Run the HTML extractor on a local file (no Chrome required).
//	medit antfu health
//	    Check that Chrome is reachable on cdp_url.
package commands

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"time"

	"github.com/spf13/cobra"

	"github.com/veawho/via54Medit/internal/source"
	"github.com/veawho/via54Medit/pkg/types"
)

// antfuCmd is the parent command.
var antfuCmd = &cobra.Command{
	Use:   "antfu",
	Short: "Drive the 蚂蚁阿福 (chat.antafu.com) chat via Chrome DevTools Protocol",
	Long: `antfu controls a Chrome instance via CDP and queries chat.antafu.com.

Prerequisites:
  1. Chrome is running with --remote-debugging-port=9223
     (e.g. chrome.exe --remote-debugging-port=9223 --user-data-dir=C:\chrome-debug)
  2. You have logged into chat.antafu.com once (cookies persist)

Examples:
  medit antfu ask "SGLT2 inhibitor for heart failure" --json
  medit antfu extract saved-page.html
  medit antfu health`,
}

// antfuAskCmd sends a question.
var antfuAskCmd = &cobra.Command{
	Use:   "ask <query>",
	Short: "Ask a question and return extracted references",
	Args:  cobra.MinimumNArgs(1),
	RunE:  runAntfuAsk,
}

// antfuExtractCmd runs the HTML extractor on a local file.
var antfuExtractCmd = &cobra.Command{
	Use:   "extract <file.html>",
	Short: "Run the HTML extractor on a local file (no Chrome required)",
	Args:  cobra.ExactArgs(1),
	RunE:  runAntfuExtract,
}

// antfuHealthCmd checks Chrome reachability.
var antfuHealthCmd = &cobra.Command{
	Use:   "health",
	Short: "Check that Chrome is reachable on cdp_url",
	RunE:  runAntfuHealth,
}

var (
	antfuCDP     string
	antfuJSON    bool
	antfuTimeout time.Duration
)

func init() {
	antfuAskCmd.Flags().StringVar(&antfuCDP, "cdp-url", "http://localhost:9223", "Chrome DevTools Protocol base URL")
	antfuAskCmd.Flags().BoolVar(&antfuJSON, "json", false, "Output JSON instead of human-readable text")
	antfuAskCmd.Flags().DurationVar(&antfuTimeout, "timeout", 60*time.Second, "Max wait for the antfu RAG response")

	antfuExtractCmd.Flags().BoolVar(&antfuJSON, "json", false, "Output JSON instead of human-readable text")

	antfuHealthCmd.Flags().StringVar(&antfuCDP, "cdp-url", "http://localhost:9223", "Chrome DevTools Protocol base URL")

	antfuCmd.AddCommand(antfuAskCmd, antfuExtractCmd, antfuHealthCmd)
}

func runAntfuAsk(cmd *cobra.Command, args []string) error {
	ctx, cancel := context.WithTimeout(cmd.Context(), antfuTimeout+10*time.Second)
	defer cancel()

	src, err := source.NewAntfuSource(map[string]any{
		"enabled": true,
		"cdp_url": antfuCDP,
		"timeout": antfuTimeout.String(),
	})
	if err != nil {
		return fmt.Errorf("antfu: init: %w", err)
	}

	cites, err := src.Search(ctx, types.EBMQuestion{
		Query:  args[0],
		Intent: types.IntentSearch,
	}, 20)
	if err != nil {
		return fmt.Errorf("antfu ask: %w", err)
	}
	return outputCitations(cmd, cites)
}

func runAntfuExtract(cmd *cobra.Command, args []string) error {
	path := args[0]
	f, err := os.Open(path)
	if err != nil {
		return fmt.Errorf("antfu extract: open %s: %w", path, err)
	}
	defer f.Close()

	extracted, err := source.Extract(f, source.DefaultExtractConfig())
	if err != nil {
		return fmt.Errorf("antfu extract: %w", err)
	}

	out := cmd.OutOrStdout()
	if antfuJSON {
		enc := json.NewEncoder(out)
		enc.SetIndent("", "  ")
		return enc.Encode(extracted)
	}
	fmt.Fprintf(out, "Answer (%d chars):\n", len(extracted.Answer))
	// Print first 500 chars to keep CLI output sane.
	if len(extracted.Answer) > 500 {
		fmt.Fprintf(out, "%s...\n", extracted.Answer[:500])
	} else {
		fmt.Fprintln(out, extracted.Answer)
	}
	fmt.Fprintf(out, "\nReferences (%d):\n", len(extracted.References))
	for i, r := range extracted.References {
		fmt.Fprintf(out, "  [%d] %s\n", i+1, r.Title)
		if r.URL != "" {
			fmt.Fprintf(out, "      %s\n", r.URL)
		}
		if r.Year > 0 {
			fmt.Fprintf(out, "      Year: %d\n", r.Year)
		}
	}
	return nil
}

func runAntfuHealth(cmd *cobra.Command, args []string) error {
	ctx, cancel := context.WithTimeout(cmd.Context(), 5*time.Second)
	defer cancel()
	if err := source.ChromeHealth(ctx, antfuCDP); err != nil {
		fmt.Fprintf(cmd.ErrOrStderr(), "antfu: Chrome NOT reachable at %s: %v\n", antfuCDP, err)
		fmt.Fprintln(cmd.ErrOrStderr(), "Hint: start Chrome with --remote-debugging-port=9223")
		os.Exit(1)
	}
	fmt.Fprintf(cmd.OutOrStdout(), "antfu: Chrome reachable at %s\n", antfuCDP)
	return nil
}
