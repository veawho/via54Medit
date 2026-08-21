// citation.go — Citation algorithm CLI subcommand (Phase 6)
//
// 用法:
//   medit citation match <reference> <pdf-text>
//     Match a D-column reference against a PDF's text content.
//     Returns score + matched/missing fields.
//   medit citation test-extract <reference>
//     Extract key fields from a reference text and print as JSON.
//   medit citation replayer [--generate] [--seed <json>]
//     Run the experience loop: list pending corrections, optionally generate
//     Go test file, optionally seed from a JSON file.
package commands

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/spf13/cobra"

	"github.com/veawho/via54Medit/internal/citation"
	"github.com/veawho/via54Medit/internal/citation/corrections"
)

var citationCmd = &cobra.Command{
	Use:   "citation",
	Short: "Citation table algorithm core (Phase 6 — algorithm-driven)",
	Long: `citation 命令直接调用 via54Medit 内部的算法核心 — 这是所有文献整理项目
(如 雷管方案_文献整理) 应当使用的统一接口.

支持子命令:
  medit citation match <reference> <pdf-text>   # D 列 vs PDF 内容匹配
  medit citation test-extract <reference>        # 抽取关键字段
  medit citation replayer [--generate] [--seed]  # 经验闭环

设计原则:
  - 算法驱动 (regex + probabilistic + LLM reflection), 不是规则
  - 经验闭环: 每次修正 → corrections.json → 自动转测试 → CI 验证
  - 跟 medit-mcp 同一进程, 复用 internal/citation/
  - 零硬编码 (100% env / config)

算法目录:
  keyword_match.go    D 列关键字段 (author + journal + year + trial + drug + DOI tail)
  rich_text.go        飞书 H 列 rich text 自动转换 (URL → {type: 'link'})
  cell_parser.go      飞书 cell 嵌套解析 (string / dict / list / rich_text)
  corrections/        经验闭环 (corrections.json + replayer + go test gen)`,
}

var citationMatchCmd = &cobra.Command{
	Use:   "match <reference> <pdf-text>",
	Short: "Match a D-column reference against a PDF's text content",
	Long: `match extracts key fields from the reference and matches them against
the PDF text. Returns a score (0.0-1.0), matched fields, and missing fields.

Examples:
  medit citation match "Qin S, et al. Lancet Oncol. 2025" "This IMbrave150 study..."
  medit citation match "Abou-Alfa GK. NEJMEvid 2022" "Tremelimumab + Durvalumab in HCC..."`,
	Args: cobra.ExactArgs(2),
	RunE: runCitationMatch,
}

var citationExtractCmd = &cobra.Command{
	Use:   "test-extract <reference>",
	Short: "Extract key fields from a reference and print as JSON",
	Args:  cobra.ExactArgs(1),
	RunE:  runCitationExtract,
}

var citationReplayerCmd = &cobra.Command{
	Use:   "replayer",
	Short: "Run the experience loop (corrections → test cases)",
	Long: `replayer is the heart of the experience loop:

  medit citation replayer                 # list pending corrections
  medit citation replayer --generate       # generate Go test file
  medit citation replayer --seed <json>    # seed from JSON file`,
	RunE: runCitationReplayer,
}

var (
	citationReplayerGenerate bool
	citationReplayerSeed     string
)

func init() {
	citationCmd.AddCommand(citationMatchCmd)
	citationCmd.AddCommand(citationExtractCmd)
	citationCmd.AddCommand(citationReplayerCmd)

	citationReplayerCmd.Flags().BoolVar(&citationReplayerGenerate, "generate", false,
		"Generate Go test file from pending corrections")
	citationReplayerCmd.Flags().StringVar(&citationReplayerSeed, "seed", "",
		"Seed corrections from JSON file")
}

func runCitationMatch(cmd *cobra.Command, args []string) error {
	c := citation.Citation{Reference: args[0]}
	kf := c.ExtractKeyFields()

	result := kf.Match(args[1])
	out := map[string]interface{}{
		"reference":      args[0],
		"pdf_text_len":   len(args[1]),
		"key_fields":     kf,
		"match_score":    result.Score,
		"matched_fields": result.MatchedFields,
		"missing_fields": result.MissingFields,
		"reason":         result.Reason,
	}
	enc := json.NewEncoder(cmd.OutOrStdout())
	enc.SetIndent("", "  ")
	return enc.Encode(out)
}

func runCitationExtract(cmd *cobra.Command, args []string) error {
	c := citation.Citation{Reference: args[0]}
	kf := c.ExtractKeyFields()
	enc := json.NewEncoder(cmd.OutOrStdout())
	enc.SetIndent("", "  ")
	return enc.Encode(kf)
}

func runCitationReplayer(cmd *cobra.Command, args []string) error {
	logPath := os.Getenv("CORRECTIONS_LOG")
	if logPath == "" {
		logPath = corrections.DefaultLogPath
	}

	log, err := corrections.LoadLog(logPath)
	if err != nil {
		return fmt.Errorf("load corrections log: %w", err)
	}

	if citationReplayerSeed != "" {
		// Seed from JSON file
		data, err := os.ReadFile(citationReplayerSeed)
		if err != nil {
			return fmt.Errorf("read seed file: %w", err)
		}
		var entries []corrections.CorrectionEntry
		if err := json.Unmarshal(data, &entries); err != nil {
			return fmt.Errorf("parse seed: %w", err)
		}
		for _, e := range entries {
			if err := log.Record(e); err != nil {
				return fmt.Errorf("record: %w", err)
			}
		}
		cmd.Printf("Seeded %d corrections from %s\n", len(entries), citationReplayerSeed)
		return nil
	}

	if citationReplayerGenerate {
		code := log.GenerateGoTestFile("citation")
		outFile := "internal/citation/corrections_generated_test.go"
		if err := os.WriteFile(outFile, []byte(code), 0644); err != nil {
			return err
		}
		cmd.Printf("Generated %s (%d bytes)\n", outFile, len(code))
		return nil
	}

	// Default: list pending
	pending := log.PendingCorrections()
	if len(pending) == 0 {
		cmd.Println("✅ No pending corrections")
		return nil
	}

	cmd.Printf("⚠️  %d pending corrections:\n", len(pending))
	for _, c := range pending {
		cmd.Printf("  %s [%s] %s\n", c.ID, c.Type, c.Context)
	}
	os.Exit(2)
	return nil
}