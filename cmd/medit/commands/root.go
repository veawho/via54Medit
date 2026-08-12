// Package commands wires the 13 medit CLI subcommands.
//
// HLO 集成 (Phase 5, 2026-07-28):
//   新增 4 个 subcommand: medit hlo ask/audit/truth/corr
//   每个调 hlo_nlu_v2.py (Python) - 0 浏览器注册, 0 密钥
package commands

import (
	"fmt"

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
and outputs graded evidence packages with optional PPT rendering.

Phase 5 (2026-07-28): HLO (Hermes Literature Orchestrator) 集成
  - medit hlo ask "处理 P5-7"    (NLU 入口, 14 意图路由)
  - medit hlo audit              (32 Producer 白名单真伪鉴定)
  - medit hlo truth P5-7         (字段真值表查询)
  - medit hlo corr 5-7 d "Qin S" "Meyer T"  (NL 修正自升级)

Phase 6 (2026-07-31): Feishu (飞书) 集成
  - medit feishu verify           (CSV ↔ 飞书 一致性 verify)
  - medit feishu push [--dry-run] (CSV → 飞书 push, auto-fix)
  - medit citation match <ref> <pdf>  (算法驱动 D 列 vs PDF 内容匹配)
  - medit citation test-extract <ref> (抽取 author+journal+year+trial+drug+DOI)
  - medit citation replayer           (经验闭环: 修正 → 测试 → CI)`,
	Version: version.Short(),
}

// Execute is the main entry point called by cmd/medit/main.go.
func Execute() error {
	return rootCmd.Execute()
}

// versionCmd prints the multi-line build metadata. The single-line
// short form is exposed by cobra's --version flag (rootCmd.Version).
var versionCmd = &cobra.Command{
	Use:   "version",
	Short: "Print full version info (commit, build date, go version, license)",
	Long:  "Prints multi-line build metadata for via54Medit. The short form (`medit --version`) prints only semver + commit.",
	Args:  cobra.NoArgs,
	Run: func(cmd *cobra.Command, _ []string) {
		fmt.Fprintln(cmd.OutOrStdout(), version.Full())
	},
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

	// Wire all 13 + 4 HLO subcommands
	registerAll()
}

// registerAll wires the 13 + 4 HLO subcommands.
func registerAll() {
	// --- Retrieval (5) ---
	rootCmd.AddCommand(askCmd)        // ask <query>
	rootCmd.AddCommand(searchCmd)     // search <query>
	rootCmd.AddCommand(picoCmd)       // pico <query>
	rootCmd.AddCommand(systematicCmd) // systematic <query>
	rootCmd.AddCommand(gradeCmd)      // grade <package>

	// --- Source adapters (6) ---
	rootCmd.AddCommand(pubmedCmd)   // pubmed <subcmd>
	rootCmd.AddCommand(openalexCmd) // openalex <subcmd>
	rootCmd.AddCommand(s2Cmd)       // s2 <subcmd>
	rootCmd.AddCommand(antfuCmd)    // antfu <subcmd>
	rootCmd.AddCommand(sciHubCmd)   // sci-hub <doi|pmid>
	rootCmd.AddCommand(gScholarCmd) // gscholar <query>
	rootCmd.AddCommand(fullTextCmd) // fulltext <search|download>

	// --- Enrich + persist (3) ---
	rootCmd.AddCommand(enrichCmd) // enrich <refs.json>
	rootCmd.AddCommand(indexCmd)  // index <file/dir>
	rootCmd.AddCommand(queryCmd)  // query <query>

	// --- Render (1) ---
	rootCmd.AddCommand(anno2pptCmd) // anno2ppt <package>

	// --- Document processing (2) ---
	rootCmd.AddCommand(docprocCmd) // docproc <file>
	rootCmd.AddCommand(pptxCmd)    // pptx verify|extract <file.pptx>

	// --- Citation extraction (1) ---
	rootCmd.AddCommand(NewCiteCommand()) // cite extract|verify|list <file>

	// --- Phase 3 additions (pico_grade.go) ---
	rootCmd.AddCommand(picoCmd)       // pico <query>
	rootCmd.AddCommand(systematicCmd) // systematic <query>
	rootCmd.AddCommand(gradeCmd)      // grade <conv_id>
	rootCmd.AddCommand(listCmd)       // list (saved conversations)

	// --- pptx sub-subcommands ---
	pptxCmd.AddCommand(pptxVerifyCmd)  // pptx verify <file.pptx>
	pptxCmd.AddCommand(pptxExtractCmd) // pptx extract <file.pptx>

	// --- HLO 集成 (Phase 5, 2026-07-28) ---
	rootCmd.AddCommand(hloCmd) // hlo <ask|audit|truth|corr> [args...]

	// --- Feishu 集成 (Phase 6, 2026-07-31) ---
	rootCmd.AddCommand(feishuCmd) // feishu <verify|push> [args...]

	// --- Citation 算法核心 (Phase 6, 2026-07-31) ---
	rootCmd.AddCommand(citationCmd) // citation <match|test-extract|replayer> [args...]

	// --- Meta (1, --version is via root.Version; "version" subcommand for multi-line Full()) ---
	rootCmd.AddCommand(versionCmd)
}
