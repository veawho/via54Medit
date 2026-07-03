// Package commands - ask and search subcommands.
//
// ask = high-level entry: query → 4 sources → fuse → LLM summary
// search = low-level: same 4 sources but no LLM (raw citation dump)
//
// Both wire the real router (Phase 2) instead of the Phase 0 stub.
package commands

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"time"

	"github.com/spf13/cobra"

	"github.com/veawho/via54Medit/internal/foundation"
	"github.com/veawho/via54Medit/internal/router"
	"github.com/veawho/via54Medit/internal/source"
	"github.com/veawho/via54Medit/pkg/types"
)

// askCmd replaces the Phase 0 stub with the real 4-source fan-out.
var askCmd = &cobra.Command{
	Use:   "ask <query>",
	Short: "Evidence-based search: query → 4 sources → fuse → summary",
	Long: `ask runs a single clinical question through PubMed, OpenAlex,
Semantic Scholar, and (optionally) 蚂蚁阿福, then merges the results
and produces an EBM-style summary.

Examples:
  medit ask "SGLT2 抑制剂对 2 型糖尿病合并心衰的预后"
  medit ask "aspirin primary prevention" --max 20 --json
  medit ask "heart failure treatment" --no-antfu --no-llm`,
	Args: cobra.MinimumNArgs(1),
	RunE: runAsk,
}

var searchCmd = &cobra.Command{
	Use:   "search <query>",
	Short: "Raw multi-source search: query → 4 sources → no LLM summary",
	Long: `search is the same as ask but skips the LLM summary step. Use it
when you want the raw citation list for further processing (e.g. piping
into a custom analyzer or building a slide deck).`,
	Args: cobra.MinimumNArgs(1),
	RunE: runSearch,
}

var (
	askMax      int
	askJSON     bool
	askNoAntfu  bool
	askAntfuCDP string
	askAntfuTO  time.Duration
	askTimeout  time.Duration
	askSources  string // comma-separated: pubmed,openalex,s2,antfu
)

func init() {
	askCmd.Flags().IntVar(&askMax, "max", 20, "Max citations per source")
	askCmd.Flags().BoolVar(&askJSON, "json", false, "Output JSON")
	askCmd.Flags().BoolVar(&askNoAntfu, "no-antfu", false, "Skip antfu (no Chrome required)")
	askCmd.Flags().StringVar(&askAntfuCDP, "antfu-cdp", "http://localhost:9223", "Chrome DevTools URL for antfu")
	askCmd.Flags().DurationVar(&askAntfuTO, "antfu-timeout", 150*time.Second, "Antfu RAG timeout")
	askCmd.Flags().DurationVar(&askTimeout, "timeout", 180*time.Second, "Total wall-clock timeout")
	askCmd.Flags().StringVar(&askSources, "sources", "pubmed,openalex,s2,antfu", "Comma-separated sources to query")

	searchCmd.Flags().IntVar(&askMax, "max", 20, "Max citations per source")
	searchCmd.Flags().BoolVar(&askJSON, "json", false, "Output JSON")
	searchCmd.Flags().BoolVar(&askNoAntfu, "no-antfu", false, "Skip antfu")
	searchCmd.Flags().StringVar(&askAntfuCDP, "antfu-cdp", "http://localhost:9223", "Chrome DevTools URL for antfu")
	searchCmd.Flags().DurationVar(&askAntfuTO, "antfu-timeout", 150*time.Second, "Antfu RAG timeout")
	searchCmd.Flags().StringVar(&askSources, "sources", "pubmed,openalex,s2,antfu", "Comma-separated sources to query")
	searchCmd.Flags().DurationVar(&askTimeout, "timeout", 180*time.Second, "Total wall-clock timeout")
}

func runAsk(cmd *cobra.Command, args []string) error {
	return runRouter(cmd, args, true)
}

func runSearch(cmd *cobra.Command, args []string) error {
	return runRouter(cmd, args, false)
}

func runRouter(cmd *cobra.Command, args []string, useLLM bool) error {
	ctx, cancel := context.WithTimeout(cmd.Context(), askTimeout)
	defer cancel()

	r, err := buildRouter(useLLM)
	if err != nil {
		return err
	}

	q := types.EBMQuestion{
		Query:      args[0],
		Intent:     types.IntentSearch,
		MaxResults: askMax,
	}
	ep, err := r.Ask(ctx, q)
	if err != nil {
		return fmt.Errorf("ask: %w", err)
	}
	return outputEvidencePackage(cmd, ep)
}

func buildRouter(useLLM bool) (*router.Router, error) {
	r := router.NewRouter()
	r.Concurrency = 4
	r.MaxRetries = 1

	wanted := parseSourceList(askSources)
	r.TimeoutPerSource = 30 * time.Second
	for _, name := range wanted {
		if name == "antfu" && !askNoAntfu {
			r.TimeoutPerSource = askAntfuTO
		}
	}
	for _, name := range wanted {
		switch name {
		case "pubmed":
			s, err := source.NewPubMedSource(nil)
			if err != nil {
				return nil, err
			}
			r.AddSource(s)
		case "openalex":
			s, err := source.NewOpenAlexSource(nil)
			if err != nil {
				return nil, err
			}
			r.AddSource(s)
		case "s2":
			s, err := source.NewS2Source(nil)
			if err != nil {
				return nil, err
			}
			r.AddSource(s)
		case "antfu":
			if askNoAntfu {
				continue
			}
			s, err := source.NewAntfuSource(map[string]any{
				"cdp_url": askAntfuCDP,
				"timeout": askAntfuTO.String(),
			})
			if err != nil {
				return nil, err
			}
			r.AddSource(s)
		}
	}

	if useLLM && !askNoLLM {
		llm, err := buildLLM()
		if err != nil {
			// LLM unavailable: degrade to no-LLM mode with a warning.
			fmt.Fprintf(os.Stderr, "warning: LLM unavailable (%v); skipping summary\n", err)
		} else {
			r.LLM = llm
		}
	}
	return r, nil
}

func buildLLM() (foundation.LLMProvider, error) {
	switch askLLMProv {
	case "hermes", "":
		endpoint := askLLMEndp
		if endpoint == "" {
			endpoint = "http://localhost:8765"
		}
		model := askLLMModel
		if model == "" {
			model = "MiniMax-M3"
		}
		return foundation.NewLLM("hermes", map[string]any{
			"endpoint": endpoint,
			"model":    model,
		})
	case "openai":
		cfg := map[string]any{
			"api_key": askLLMKey,
		}
		if askLLMEndp != "" {
			cfg["endpoint"] = askLLMEndp
		}
		if askLLMModel != "" {
			cfg["model"] = askLLMModel
		}
		return foundation.NewLLM("openai", cfg)
	default:
		return nil, fmt.Errorf("unknown LLM provider: %s", askLLMProv)
	}
}

func parseSourceList(s string) []string {
	if s == "" {
		return []string{"pubmed", "openalex", "s2", "antfu"}
	}
	var out []string
	start := 0
	for i := 0; i < len(s); i++ {
		if s[i] == ',' {
			tok := trimSpace(s[start:i])
			if tok != "" {
				out = append(out, tok)
			}
			start = i + 1
		}
	}
	tok := trimSpace(s[start:])
	if tok != "" {
		out = append(out, tok)
	}
	return out
}

func trimSpace(s string) string {
	start, end := 0, len(s)
	for start < end && (s[start] == ' ' || s[start] == '\t') {
		start++
	}
	for end > start && (s[end-1] == ' ' || s[end-1] == '\t') {
		end--
	}
	return s[start:end]
}

func outputEvidencePackage(cmd *cobra.Command, ep *types.EvidencePackage) error {
	out := cmd.OutOrStdout()
	if askJSON {
		enc := json.NewEncoder(out)
		enc.SetIndent("", "  ")
		return enc.Encode(ep)
	}
	fmt.Fprintf(out, "Question: %s\n", ep.Question.Query)
	fmt.Fprintf(out, "Duration: %s\n", ep.Duration)
	fmt.Fprintf(out, "ConvID: %s\n", ep.ConvID)
	fmt.Fprintf(out, "Sources: %v\n", ep.SourcesUsed)
	fmt.Fprintf(out, "\n--- Summary ---\n%s\n", ep.Summary)
	fmt.Fprintf(out, "\n--- Citations (%d) ---\n", len(ep.Citations))
	for i, c := range ep.Citations {
		fmt.Fprintf(out, "[%d] %s\n", i+1, c.Title)
		if c.Journal != "" {
			j := c.Journal
			if c.Year > 0 {
				j = fmt.Sprintf("%s (%d)", j, c.Year)
			}
			fmt.Fprintf(out, "    %s\n", j)
		}
		if c.PMID != "" {
			fmt.Fprintf(out, "    PMID: %s", c.PMID)
		}
		if c.DOI != "" {
			fmt.Fprintf(out, "  DOI: %s", c.DOI)
		}
		if c.PMID != "" || c.DOI != "" {
			fmt.Fprintln(out)
		}
		if len(c.SourceOrigin) > 0 {
			fmt.Fprintf(out, "    Sources: %v\n", c.SourceOrigin)
		}
	}
	return nil
}
