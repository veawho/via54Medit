// feishu.go — CSV ↔ Feishu spreadsheet sync CLI subcommand (Phase 6)
//
// 用法:
//   medit feishu verify [--json] [--column G]
//     只读 verify, 不修改任何数据
//   medit feishu push [--dry-run] [--fix] [--row N]
//     Push CSV → 飞书, 自动检测漂移
//
// 设计 (2026-07-31):
//   - 跟 medit-mcp 同源, 复用 internal/integrations/feishu/Client
//   - 零硬编码 token / 路径 (从 env 或 config 读取)
//   - GitHub-ready: 私有项目路径不进入代码
//
// 环境变量:
//   FEISHU_TOKEN     - 飞书 spreadsheet token
//   SHEET_ID         - sheet ID (e.g. "b03e59")
//   CSV_PATH         - 本地 citation_table.csv 路径
//   BASE_DIR         - 项目根目录 (用于 lock 文件)
package commands

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/spf13/cobra"

	"github.com/veawho/via54Medit/internal/integrations/feishu"
)

// feishuCmd is the parent command.
var feishuCmd = &cobra.Command{
	Use:   "feishu",
	Short: "CSV ↔ Feishu spreadsheet sync (zero-config, GitHub-ready)",
	Long: `feishu 命令用于保证本地 CSV (例如 citation_table.csv) 跟飞书表格的 D/E/F/G/H 列完全一致.

支持 2 个子命令:

  medit feishu verify [--json] [--column G]
    只读比对, 检测 CSV ↔ 飞书是否一致. 不会修改任何数据.

  medit feishu push [--dry-run] [--fix] [--row N]
    推送 CSV → 飞书, 自动检测漂移, 单 row push + 锁 + retry + verify.

设计原则:
  - 单向 push (CSV → 飞书), 不反向
  - 永远 re-read CSV (不用内存缓存)
  - 文件锁 (_citation_table/csv.lock) 防并发
  - Rich text (H 列) 自动检测 URL → 转 {type: 'link'} 节点
  - 零硬编码 token / 路径 (100% 从 env 或 config 读取)

必需环境变量:
  FEISHU_TOKEN   飞书 spreadsheet token
  SHEET_ID       飞书 sheet ID
  CSV_PATH       本地 CSV 文件绝对路径
  BASE_DIR       项目根目录 (用于 lock 文件)

示例:
  export FEISHU_TOKEN="..." SHEET_ID="b03e59" \\
         CSV_PATH="/path/to/citation_table.csv" \\
         BASE_DIR="/path/to/project"
  medit feishu verify
  medit feishu push --dry-run
  medit feishu push --row 47`,
}

// feishuVerifyCmd is the verify subcommand.
var feishuVerifyCmd = &cobra.Command{
	Use:   "verify",
	Short: "Verify CSV ↔ Feishu consistency (read-only, no modifications)",
	Long: `verify reads both the local CSV and the Feishu table, then compares them row-by-row.
Reports mismatches in D/E/F/G/H columns. Does not modify any data.

Examples:
  medit feishu verify
  medit feishu verify --json
  medit feishu verify --column G`,
	RunE: runFeishuVerify,
}

// feishuPushCmd is the push subcommand.
var feishuPushCmd = &cobra.Command{
	Use:   "push",
	Short: "Push CSV → Feishu (auto-fix mismatches)",
	Long: `push reads the local CSV, verifies against Feishu, and pushes only mismatched rows
back to Feishu. Each push is followed by a single-row verify (3 retry with backoff).

Use --dry-run to preview what would be pushed without actually modifying.
Use --fix to force-push all rows (not just mismatched).
Use --row N to push a single specific row (for debugging).

Examples:
  medit feishu push
  medit feishu push --dry-run
  medit feishu push --fix
  medit feishu push --row 47`,
	RunE: runFeishuPush,
}

var (
	feishuVerifyJSON    bool
	feishuVerifyColumn  string
	feishuPushDryRun    bool
	feishuPushFix       bool
	feishuPushSingleRow int
)

func init() {
	feishuCmd.AddCommand(feishuVerifyCmd)
	feishuCmd.AddCommand(feishuPushCmd)

	feishuVerifyCmd.Flags().BoolVar(&feishuVerifyJSON, "json", false,
		"Output result as JSON")
	feishuVerifyCmd.Flags().StringVar(&feishuVerifyColumn, "column", "all",
		"Only verify specified column: D | E | F | G | H | all")

	feishuPushCmd.Flags().BoolVar(&feishuPushDryRun, "dry-run", false,
		"Show what would be pushed without actually pushing")
	feishuPushCmd.Flags().BoolVar(&feishuPushFix, "fix", false,
		"Force push all rows, not just mismatched")
	feishuPushCmd.Flags().IntVar(&feishuPushSingleRow, "row", 0,
		"Push only a single specific row (for debugging)")
}

// loadFeishuConfig loads Config from environment variables.
func loadFeishuConfig() (*feishu.Config, error) {
	cfg := &feishu.Config{
		Token:   os.Getenv("FEISHU_TOKEN"),
		SheetID: os.Getenv("SHEET_ID"),
		CSVPath: os.Getenv("CSV_PATH"),
		BaseDir: os.Getenv("BASE_DIR"),
		LarkCLI: os.Getenv("LARK_CLI"), // optional
	}
	if cfg.Token == "" || cfg.SheetID == "" || cfg.CSVPath == "" || cfg.BaseDir == "" {
		return nil, fmt.Errorf(`feishu: missing required environment variables.
Set:
  FEISHU_TOKEN   飞书 spreadsheet token
  SHEET_ID       飞书 sheet ID
  CSV_PATH       本地 CSV 文件绝对路径
  BASE_DIR       项目根目录`)
	}
	return cfg, nil
}

func runFeishuVerify(cmd *cobra.Command, args []string) error {
	cfg, err := loadFeishuConfig()
	if err != nil {
		return err
	}

	client, err := feishu.NewClient(cfg)
	if err != nil {
		return err
	}

	result, err := client.Verify(cmd.Context())
	if err != nil {
		return fmt.Errorf("verify: %w", err)
	}

	if feishuVerifyJSON {
		enc := json.NewEncoder(cmd.OutOrStdout())
		enc.SetIndent("", "  ")
		return enc.Encode(result)
	}

	// Human-readable output
	cmd.Println("=== CSV ↔ Feishu verify ===")
	cmd.Printf("CSV rows: %d\n", result.TotalRows)
	cmd.Printf("Feishu rows: %d\n", result.FeishuRows)
	cmd.Println()
	cmd.Println("=== Mismatch 统计 ===")
	for col, mismatches := range result.ColumnMismatches {
		cmd.Printf("%s 列: %d\n", col, len(mismatches))
	}
	cmd.Printf("文件不存在: %d\n", len(result.FileMissing))
	cmd.Println()

	if result.Consistent {
		cmd.Println("✅ CSV ↔ Feishu 100% 一致")
		return nil
	}

	cmd.Println("❌ 需修复:")
	for col, mismatches := range result.ColumnMismatches {
		if len(mismatches) == 0 {
			continue
		}
		cmd.Printf("  %s 列:\n", col)
		for _, m := range mismatches {
			cmd.Printf("    %s\n", m)
		}
	}
	if len(result.FileMissing) > 0 {
		cmd.Println("  文件不存在:")
		for _, f := range result.FileMissing {
			cmd.Printf("    %s\n", f)
		}
	}
	cmd.Println()
	cmd.Println("运行 `medit feishu push` 自动修复")
	os.Exit(2)
	return nil
}

func runFeishuPush(cmd *cobra.Command, args []string) error {
	cfg, err := loadFeishuConfig()
	if err != nil {
		return err
	}

	client, err := feishu.NewClient(cfg)
	if err != nil {
		return err
	}

	cmd.Println("=== CSV → Feishu push ===")
	if feishuPushDryRun {
		cmd.Println("(DRY-RUN mode)")
	}

	opts := feishu.PushOptions{
		DryRun:    feishuPushDryRun,
		FixMode:   feishuPushFix,
		SingleRow: feishuPushSingleRow,
	}

	success, fails, err := client.Push(cmd.Context(), opts)
	if err != nil {
		return fmt.Errorf("push: %w", err)
	}

	cmd.Printf("\n✅ Success: %d\n", success)
	if len(fails) > 0 {
		cmd.Printf("❌ Failed: %d\n", len(fails))
		for _, f := range fails {
			cmd.Printf("  %v\n", f)
		}
		os.Exit(2)
	}
	return nil
}
