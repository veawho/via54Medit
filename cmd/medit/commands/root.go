// Package commands wires the 13 medit CLI subcommands.
package commands

import (
	"github.com/spf13/cobra"

	"github.com/veawho/via54Medit/internal/version"
)

// rootCmd is the base command.
var rootCmd = &cobra.Command{
	Use:   "medit",
	Short: "via54Medit — multi-source medical literature router for EBM",
	Long: `via54Medit is a natural-language-driven multi-source medical literature
router for Evidence-Based Medicine. It dispatches clinical questions
to Antfu RAG, PubMed, OpenAlex, and Semantic Scholar, fuses results,
and outputs graded evidence packages with optional PPT rendering.`,
	Version: version.Short(),
}

// Execute is the main entry point called by cmd/medit/main.go.
func Execute() error {
	return rootCmd.Execute()
}

var (
	askLLMProv  string
	askLLMEndp  string
	askLLMKey   string
	askLLMModel string
	askNoLLM    bool
)

func init() {
	// Global persistent flags
	rootCmd.PersistentFlags().String("config", "",
		"Config file (default ~/.medit/config.yaml)")
	rootCmd.PersistentFlags().String("embedder", "bge-m3",
		"Embedder backend: bge-m3 | openai | sense nova | ...")
	rootCmd.PersistentFlags().String("vectorstore", "qdrant",
		"Vector store backend: qdrant | meilisearch | sqlite | ...")
	rootCmd.PersistentFlags().String("provider", "hermes",
		"LLM provider: hermes | openai | anthropic | ollama | ...")
	rootCmd.PersistentFlags().String("lang", "auto",
		"Query language: zh | en | auto")
	rootCmd.PersistentFlags().BoolP("verbose", "v", false, "Verbose logging")
	rootCmd.PersistentFlags().Bool("no-color", false, "Disable ANSI colors")

	// Shared LLM configuration persistent flags
	rootCmd.PersistentFlags().StringVar(&askLLMProv, "llm", "hermes",
		"LLM provider: hermes | openai")
	rootCmd.PersistentFlags().StringVar(&askLLMEndp, "llm-endpoint", "",
		"Custom LLM endpoint")
	rootCmd.PersistentFlags().StringVar(&askLLMKey, "llm-api-key", "",
		"LLM API key (for openai)")
	rootCmd.PersistentFlags().StringVar(&askLLMModel, "llm-model", "",
		"LLM model name")
	rootCmd.PersistentFlags().BoolVar(&askNoLLM, "no-llm", false,
		"Skip LLM summary/extraction")

	// Wire all 13 subcommands (Phase 0: all stubs that print "coming in Phase N")
	registerAll()
}

// registerAll wires the 13 subcommands.
func registerAll() {
	// --- Retrieval (5) ---
	rootCmd.AddCommand(askCmd)        // ask <query>
	rootCmd.AddCommand(searchCmd)     // search <query>
	rootCmd.AddCommand(picoCmd)       // pico <query>
	rootCmd.AddCommand(systematicCmd) // systematic <query>
	rootCmd.AddCommand(gradeCmd)      // grade <package>

	// --- Source adapters (4) ---
	rootCmd.AddCommand(pubmedCmd)   // pubmed <subcmd>
	rootCmd.AddCommand(openalexCmd) // openalex <subcmd>
	rootCmd.AddCommand(s2Cmd)       // s2 <subcmd>
	rootCmd.AddCommand(antfuCmd)    // antfu <subcmd>

	// --- Enrich + persist (3) ---
	rootCmd.AddCommand(enrichCmd) // enrich <refs.json>
	rootCmd.AddCommand(indexCmd)  // index <file/dir>
	rootCmd.AddCommand(queryCmd)  // query <query>

	// --- Render (1) ---
	rootCmd.AddCommand(anno2pptCmd) // anno2ppt <package>

	// --- Phase 3 additions (pico_grade.go) ---
	rootCmd.AddCommand(picoCmd)       // pico <query>
	rootCmd.AddCommand(systematicCmd) // systematic <query>
	rootCmd.AddCommand(gradeCmd)      // grade <conv_id>
	rootCmd.AddCommand(listCmd)       // list (saved conversations)

	// --- Meta (1, already in root.Version) ---
	// rootCmd.AddCommand(versionCmd) is implicit via root.Version
}
