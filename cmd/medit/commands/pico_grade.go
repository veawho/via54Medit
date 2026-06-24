// Package commands - pico / systematic / grade subcommands.
//
// Phase 3 real implementations (replacing Phase 0 stubs).
//
//	medit pico <query>             - extract PICO (LLM + heuristic fallback)
//	medit systematic <query>       - PICO + 4-source fan-out + PRISMA-style flow
//	medit grade <conv_id>          - apply GRADE to a saved package
//	medit list                      - list saved conversations
//
// The grade command reads EvidencePackages from the persist layer.
// systematic is a meta-command that runs pico → ask → save → print flow.
package commands

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/spf13/cobra"

	"github.com/veawho/via54Medit/internal/persist"
	"github.com/veawho/via54Medit/internal/router"
	"github.com/veawho/via54Medit/internal/source"
	"github.com/veawho/via54Medit/pkg/types"
)

// --- pico ---

var picoCmd = &cobra.Command{
	Use:   "pico <query>",
	Short: "Extract PICO (Population/Intervention/Comparator/Outcome)",
	Long: `pico extracts the four PICO elements from a clinical question.
Uses an LLM if one is configured (--llm-provider), otherwise falls back
to keyword heuristics. Always succeeds — returns an empty PICO if
nothing matches.`,
	Args: cobra.MinimumNArgs(1),
	RunE: runPico,
}

var (
	picoJSON    bool
	picoNoLLM   bool
	picoLLMProv string
)

func init() {
	picoCmd.Flags().BoolVar(&picoJSON, "json", false, "Output JSON")
	picoCmd.Flags().BoolVar(&picoNoLLM, "no-llm", false, "Force heuristic mode")
	picoCmd.Flags().StringVar(&picoLLMProv, "llm", "hermes", "LLM provider: hermes | openai")
}

// --- systematic ---

var systematicCmd = &cobra.Command{
	Use:   "systematic <query>",
	Short: "PRISMA-style review: PICO → 4 sources → grade → save",
	Long: `systematic runs the full PRISMA flow for one clinical question:
  1. Extract PICO (pico)
  2. Fan out to 4 sources (ask)
  3. Deduplicate + score (router)
  4. Apply GRADE (grade)
  5. Save to ~/.medit/qa/<conv_id>.{json,md}
  6. Print summary`,
	Args: cobra.MinimumNArgs(1),
	RunE: runSystematic,
}

var (
	sysJSON   bool
	sysNoSave bool
)

func init() {
	systematicCmd.Flags().BoolVar(&sysJSON, "json", false, "Output JSON")
	systematicCmd.Flags().BoolVar(&sysNoSave, "no-save", false, "Don't persist to disk")
	systematicCmd.Flags().BoolVar(&askNoAntfu, "no-antfu", false, "Skip antfu")
	systematicCmd.Flags().BoolVar(&askNoLLM, "no-llm", false, "Skip LLM summary")
	systematicCmd.Flags().StringVar(&askLLMProv, "llm", "hermes", "LLM provider")
	systematicCmd.Flags().StringVar(&askLLMKey, "llm-api-key", "", "LLM API key")
	systematicCmd.Flags().IntVar(&askMax, "max", 30, "Max citations per source (higher than ask default)")
}

// --- grade ---

var gradeCmd = &cobra.Command{
	Use:   "grade <conv_id|--stdin>",
	Short: "Apply simplified GRADE rating to a saved or piped evidence package",
	Args:  cobra.MaximumNArgs(1),
	RunE:  runGrade,
}

func init() {
	gradeCmd.Flags().String("stdin", "", "Read EvidencePackage JSON from stdin (alternative to conv_id)")
	gradeCmd.Flags().Bool("json", false, "Output JSON")
}

// --- list (bonus) ---

var listCmd = &cobra.Command{
	Use:   "list",
	Short: "List saved conversations (~/.medit/qa)",
	RunE:  runList,
}

// --- implementations ---

func runPico(cmd *cobra.Command, args []string) error {
	r := router.NewRouter()
	if !picoNoLLM {
		if llm, err := buildLLM(); err == nil {
			r.LLM = llm
		}
	}
	ctx, cancel := context.WithTimeout(cmd.Context(), 30*time.Second)
	defer cancel()
	pico, err := r.ExtractPICO(ctx, args[0])
	if err != nil {
		return err
	}
	if picoJSON {
		enc := json.NewEncoder(cmd.OutOrStdout())
		enc.SetIndent("", "  ")
		return enc.Encode(pico)
	}
	fmt.Fprintf(cmd.OutOrStdout(), "PICO for: %q\n\n", args[0])
	fmt.Fprintf(cmd.OutOrStdout(), "  P (Population):   %s\n", emptyOrVal(pico.Population))
	fmt.Fprintf(cmd.OutOrStdout(), "  I (Intervention): %s\n", emptyOrVal(pico.Intervention))
	fmt.Fprintf(cmd.OutOrStdout(), "  C (Comparator):   %s\n", emptyOrVal(pico.Comparator))
	fmt.Fprintf(cmd.OutOrStdout(), "  O (Outcome):       %s\n", emptyOrVal(pico.Outcome))
	return nil
}

func emptyOrVal(s string) string {
	if s == "" {
		return "(not specified)"
	}
	return s
}

func runSystematic(cmd *cobra.Command, args []string) error {
	ctx, cancel := context.WithTimeout(cmd.Context(), 2*time.Minute)
	defer cancel()

	// [1] PICO
	r := router.NewRouter()
	if !askNoLLM {
		if llm, err := buildLLM(); err == nil {
			r.LLM = llm
		}
	}
	pico, err := r.ExtractPICO(ctx, args[0])
	if err != nil {
		return fmt.Errorf("pico: %w", err)
	}

	// [2-4] Use the existing ask flow (router.Ask) which does 4-source + dedup + LLM
	q := types.EBMQuestion{
		Query:      args[0],
		Intent:     types.IntentSystematic,
		MaxResults: askMax,
		PICO:       pico,
	}
	// Build a router with the same 4 sources as `medit ask`.
	r2 := buildRouterForSystematic(!askNoLLM)
	ep, err := r2.Ask(ctx, q)
	if err != nil {
		return fmt.Errorf("ask: %w", err)
	}
	ep.Question.PICO = pico // attach PICO to package

	// [5] GRADE
	g := router.Grade(ep)
	ep.GRADE = g.GRADE
	ep.GRADEReasoning = g.Reasoning

	// [6] Save
	if !sysNoSave {
		store, err := openStore()
		if err != nil {
			fmt.Fprintf(cmd.ErrOrStderr(), "warning: persist disabled: %v\n", err)
		} else if err := store.Save(ep); err != nil {
			fmt.Fprintf(cmd.ErrOrStderr(), "warning: save failed: %v\n", err)
		}
	}

	// [7] Print
	return outputEvidencePackage(cmd, ep)
}

func buildRouterForSystematic(useLLM bool) *router.Router {
	r := router.NewRouter()
	r.Concurrency = 4
	r.TimeoutPerSource = 30 * time.Second
	r.MaxRetries = 1
	for _, name := range parseSourceList(askSources) {
		s, err := systemDefaultSource(name)
		if err != nil {
			continue
		}
		r.AddSource(s)
	}
	if useLLM {
		if llm, err := buildLLM(); err == nil {
			r.LLM = llm
		}
	}
	return r
}

// systemDefaultSource is a thin shim around the regular source
// constructors — used by `medit systematic` so we don't re-import
// the source package's switch block here.
func systemDefaultSource(name string) (source.SourceAdapter, error) {
	switch name {
	case "pubmed":
		return source.NewPubMedSource(nil)
	case "openalex":
		return source.NewOpenAlexSource(nil)
	case "s2":
		return source.NewS2Source(nil)
	case "antfu":
		return source.NewAntfuSource(map[string]any{
			"cdp_url": askAntfuCDP,
			"timeout": askAntfuTO.String(),
		})
	}
	return nil, fmt.Errorf("unknown source: %s", name)
}

func runGrade(cmd *cobra.Command, args []string) error {
	stdinPath, _ := cmd.Flags().GetString("stdin")
	convID := ""
	if len(args) > 0 {
		convID = args[0]
	}
	if stdinPath != "" {
		convID = stdinPath
	}
	if convID == "" {
		return fmt.Errorf("usage: medit grade <conv_id>  OR  medit grade --stdin < pkg.json")
	}

	var ep *types.EvidencePackage
	if stdinPath != "" {
		// Read from stdin.
		data, err := os.ReadFile(stdinPath)
		if err != nil {
			return err
		}
		if err := json.Unmarshal(data, &ep); err != nil {
			return err
		}
	} else {
		store, err := openStore()
		if err != nil {
			return err
		}
		ep, err = store.Load(convID)
		if err != nil {
			return err
		}
	}

	g := router.Grade(ep)
	jsonOut, _ := cmd.Flags().GetBool("json")
	if jsonOut {
		enc := json.NewEncoder(cmd.OutOrStdout())
		enc.SetIndent("", "  ")
		return enc.Encode(g)
	}
	fmt.Fprintf(cmd.OutOrStdout(), "GRADE: %s  (score %d/7)\n", g.GRADE, g.Score)
	fmt.Fprintf(cmd.OutOrStdout(), "Reasoning: %s\n", g.Reasoning)
	fmt.Fprintf(cmd.OutOrStdout(), "  Citations: %d\n", g.NCitations)
	fmt.Fprintf(cmd.OutOrStdout(), "  Sources:   %d\n", g.NSources)
	fmt.Fprintf(cmd.OutOrStdout(), "  RCT ratio: %.0f%%\n", g.RCTRatio*100)
	return nil
}

func runList(cmd *cobra.Command, args []string) error {
	store, err := openStore()
	if err != nil {
		return err
	}
	ids, err := store.List()
	if err != nil {
		return err
	}
	if len(ids) == 0 {
		fmt.Fprintln(cmd.OutOrStdout(), "(no saved conversations)")
		return nil
	}
	fmt.Fprintln(cmd.OutOrStdout(), "Saved conversations:")
	for _, id := range ids {
		fmt.Fprintf(cmd.OutOrStdout(), "  - %s\n", id)
	}
	return nil
}

// openStore returns a QAStore rooted at ~/.medit/qa.
func openStore() (*persist.QAStore, error) {
	dir := qaDir()
	return persist.NewQAStore(dir)
}

func qaDir() string {
	// Honor $MEDIT_HOME for testing.
	if h := os.Getenv("MEDIT_HOME"); h != "" {
		return filepath.Join(h, "qa")
	}
	// Default: ~/.medit/qa
	home, err := os.UserHomeDir()
	if err != nil {
		home = "."
	}
	return filepath.Join(home, ".medit", "qa")
}
