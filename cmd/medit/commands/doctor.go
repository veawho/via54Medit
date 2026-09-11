// Package commands — doctor subcommand (部署自检 + 自动接入).
//
// medit doctor — 部署到新设备、或更新版本之后的设备自检入口。
//
// 深度扫描的**唯一事实来源**是 scripts/deploy_scan.py 里的能力矩阵, doctor 不自带清单:
// 历史上 Go 侧、deps_auto.py、bootstrap_device.py 各有一份, 互相打架
// (最典型的是 Go 侧还在把 LibreOffice 报成"PPT 真渲染", 而那个通道早已按规范删除)。
//
// 能力矩阵的三个承诺:
//   - **按平台过滤**: 与平台无关的能力标"不适用", 既不安装也不校验
//     (pywin32 只在 Windows; 桌面版 Office 只在 Windows/macOS; Linux 上不存在)。
//   - **只装缺失的**: 已就绪的能力不会被重装。
//   - **按正确通道装**: mmx-cli 走 npm(它**不是** PyPI 包), Python 包走 pip,
//     系统工具走 brew/apt/winget/choco/scoop。
package commands

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"time"

	"github.com/spf13/cobra"

	"github.com/veawho/via54Medit/internal/foundation"
	"github.com/veawho/via54Medit/internal/source"
)

var doctorCmd = &cobra.Command{
	Use:   "doctor",
	Short: "部署自检: 深度扫描本机环境/依赖/工具, 按平台报告缺口",
	Long: `doctor 调用 scripts/deploy_scan.py 的能力矩阵做深度扫描 (跨平台, 2026-09-12):
  - 环境     OS/架构/容器/解释器/包管理器/输出编码
  - 依赖     PyMuPDF / python-pptx / Pillow / OCR(PaddleOCR) / pywin32 (仅 Windows)
  - 视觉     mmx-cli 视觉引擎 (经 **npm** 安装, 不是 PyPI) + MINIMAX_API_KEY
  - 渲染     桌面版 PowerPoint / Word (仅 Windows/macOS; Linux 无桌面 Office, 标"不适用")
  - 工具     poppler / Chrome / Go 工具链 / lark-cli
  - 兼容性   硬编码 /tmp、外机绝对路径、未加 darwin 守卫的 osascript 等平台相关代码点

与平台无关的能力标"不适用", 且**不安装、不校验**。
--fix 真正执行安装 (缺什么装什么; 重依赖如 OCR 可用 --skip-heavy 跳过)。
--strict 让平台兼容性问题也计入失败。

退出码 0 = 必需能力齐备。`,
	RunE: runDoctor,
}

var (
	doctorFix      bool
	doctorStrict   bool
	doctorSkipHevy bool
	doctorPlan     bool
	doctorCDPPort  int
)

func init() {
	doctorCmd.Flags().BoolVar(&doctorFix, "fix", false, "执行安装 (缺什么装什么)")
	doctorCmd.Flags().BoolVar(&doctorPlan, "plan", false,
		"只打印将要执行的动作, 不做任何修改 (等价于 --dry-run)")
	doctorCmd.Flags().BoolVar(&doctorStrict, "strict", false, "平台兼容性问题也计入失败")
	doctorCmd.Flags().BoolVar(&doctorSkipHevy, "skip-heavy", false, "跳过重依赖 (OCR/Paddle)")
	doctorCmd.Flags().IntVar(&doctorCDPPort, "port", DefaultCDPPort, "DevTools 端口")
}

// ---- deploy_scan.py 的 JSON 契约 ----
type dsRow struct {
	Key      string `json:"key"`
	Label    string `json:"label"`
	Kind     string `json:"kind"`
	Status   string `json:"status"`
	Detail   string `json:"detail"`
	Hint     string `json:"hint"`
	Required bool   `json:"required"`
	Heavy    bool   `json:"heavy"`
	Gate     bool   `json:"gate"`
	// Verified 为 false 表示"安装器报成功, 但装完复验没过" —— 这正是 Word 通道
	// 踩过的那个坑(save as 返回 rc=0 却没有任何产出), 必须单独可见。
	// 注意: JSON 里的 "channel" 是个**对象**, 这里不要用 string 去接 —— 类型不匹配会让
	// json.Unmarshal 整份失败, doctor 就会报"输出不是合法 JSON"(已实测)。
	Verified *bool  `json:"verified"`
	Verify   string `json:"verify_detail"`
}

type dsFinding struct {
	File   string `json:"file"`
	Line   int    `json:"line"`
	Detail string `json:"detail"`
}

type dsResult struct {
	Capabilities []dsRow `json:"capabilities"`
	Compat       struct {
		Findings      []dsFinding `json:"findings"`
		ScannedFiles  int         `json:"scanned_files"`
		AffectedFiles int         `json:"affected_files"`
	} `json:"compat"`
	Summary struct {
		Blockers      int `json:"blockers"`
		Unresolvable  int `json:"unresolvable"`
		VerifyFailed  int `json:"verify_failed"`
		Warnings      int `json:"warnings"`
		NotApplicable int `json:"not_applicable"`
		Fixed         int `json:"fixed"`
		Planned       int `json:"planned"`
	} `json:"summary"`
	DryRun bool `json:"dry_run"`
	OK     bool `json:"ok"`
}

// locateRepoScript 按"已安装的 skill -> 仓库 scripts/ -> 相对可执行文件"三处找脚本。
func locateRepoScript(name string) string {
	cands := []string{
		foundation.HermesPath("skills", "via54medit", name),
		filepath.Join("scripts", name),
	}
	if exe, err := os.Executable(); err == nil {
		// bin/medit -> 仓库根
		cands = append(cands, filepath.Join(filepath.Dir(filepath.Dir(exe)), "scripts", name))
	}
	for _, c := range cands {
		if _, err := os.Stat(c); err == nil {
			return c
		}
	}
	return ""
}

func runDoctor(cmd *cobra.Command, _ []string) error {
	out := cmd.OutOrStdout()
	fmt.Fprintln(out, "== medit doctor — 部署自检 ==")
	fmt.Fprintf(out, "  平台: %s/%s\n", runtime.GOOS, runtime.GOARCH)

	py, err := foundation.ResolvePython(nil)
	if err != nil || py == "" {
		fmt.Fprintln(out, "  ✗ Python 解释器: 未找到 → 装 Python 3.10+ 或设置 $PYTHON")
		return fmt.Errorf("doctor: 没有可用 Python 解释器, 深度扫描无法进行")
	}

	script := locateRepoScript("deploy_scan.py")
	if script == "" {
		fmt.Fprintln(out, "  ✗ 未找到 scripts/deploy_scan.py → 深度扫描无法进行 (请用完整仓库形态部署)")
		return fmt.Errorf("doctor: 缺少 scripts/deploy_scan.py")
	}

	args := []string{script, "--json"}
	if doctorPlan {
		// --plan 等价于 deploy_scan.py 的 --dry-run: 只报计划, 不落地。
		args = append(args, "--dry-run")
	} else if !doctorFix {
		args = append(args, "--check")
	}
	if doctorStrict {
		args = append(args, "--strict")
	}
	if doctorSkipHevy {
		args = append(args, "--skip-heavy")
	}
	cctx, cancel := context.WithTimeout(cmd.Context(), 30*time.Minute)
	defer cancel()
	proc := exec.CommandContext(cctx, py, args...)
	proc.Stderr = os.Stderr
	raw, runErr := proc.Output()

	var res dsResult
	if jerr := json.Unmarshal(raw, &res); jerr != nil {
		fmt.Fprintf(out, "  ✗ 解析 deploy_scan.py 输出失败: %v\n", jerr)
		if runErr != nil {
			return fmt.Errorf("doctor: deploy_scan 失败: %w", runErr)
		}
		return fmt.Errorf("doctor: 输出不是合法 JSON")
	}

	// 能力矩阵(按平台过滤后的结果)
	fail := 0
	for _, r := range res.Capabilities {
		var mark string
		switch r.Status {
		case "ok":
			mark = "✓"
		case "fixed":
			mark = "＋"
		case "na":
			mark = "·"
		case "plan":
			mark = "→"
		default:
			mark = "✗"
			if r.Required && r.Gate {
				fail++
			}
		}
		line := fmt.Sprintf("  %s %-34s %s", mark, r.Label, r.Detail)
		if (r.Status == "missing" || r.Status == "plan") && r.Hint != "" {
			line += fmt.Sprintf("  → %s", r.Hint)
		}
		fmt.Fprintln(out, line)
		// 安装器报成功但复验没过 —— 与"压根没装"是两件事, 得说清楚。
		if r.Verified != nil && !*r.Verified {
			fmt.Fprintf(out, "        → 复验详情: %s\n", orDefault(r.Verify, "无"))
		}
	}

	// Go 侧才能做的: CDP 可达性
	if chrome, cerr := source.DetectChrome(); cerr == nil {
		cdp := fmt.Sprintf("http://127.0.0.1:%d", doctorCDPPort)
		hctx, hcancel := context.WithTimeout(cmd.Context(), 3*time.Second)
		cdpOK := source.ChromeHealth(hctx, cdp) == nil
		hcancel()
		if cdpOK {
			fmt.Fprintf(out, "  ✓ %-34s %s + CDP 就绪\n", "CDP 调试实例", filepath.Base(chrome))
		} else {
			fmt.Fprintf(out, "  ~ %-34s 浏览器在, 但 CDP 未起 → `medit browser start`\n",
				"CDP 调试实例")
		}
	}

	// 平台兼容性
	c := res.Compat
	if len(c.Findings) == 0 {
		fmt.Fprintf(out, "  ✓ %-34s 扫描 %d 个 .py, 未发现不兼容点\n", "平台兼容性", c.ScannedFiles)
	} else {
		fmt.Fprintf(out, "  ✗ %-34s %d 处 / %d 个文件 (最多列 5)\n",
			"平台兼容性", len(c.Findings), c.AffectedFiles)
		for i, f := range c.Findings {
			if i >= 5 {
				fmt.Fprintf(out, "      ... 其余 %d 处见 `python3 scripts/deploy_scan.py --json`\n",
					len(c.Findings)-5)
				break
			}
			fmt.Fprintf(out, "      %s:%d  %s\n", f.File, f.Line, f.Detail)
		}
	}

	if res.DryRun {
		fmt.Fprintf(out, "== 计划: 待补 %d 项 (必需缺口 %d · 复验未过 %d) —— 本次未做任何修改 ==\n",
			res.Summary.Planned, res.Summary.Blockers, res.Summary.VerifyFailed)
		fmt.Fprintln(out, "   真正执行: `medit doctor --fix`")
		if res.Summary.Unresolvable > 0 {
			return fmt.Errorf("doctor: %d 项必需能力没有任何自动通道, 得人工安装", res.Summary.Unresolvable)
		}
		return nil
	}
	fmt.Fprintf(out, "== 结果: %s (必需缺口 %d · 提示 %d · 本平台不适用 %d · 本次补齐 %d · 复验未过 %d) ==\n",
		boolLabel(fail == 0), fail, res.Summary.Warnings, res.Summary.NotApplicable,
		res.Summary.Fixed, res.Summary.VerifyFailed)
	if fail > 0 {
		fmt.Fprintln(out, "   修复: `medit doctor --fix` (缺什么装什么)")
		return fmt.Errorf("doctor: %d 项必需能力未就绪", fail)
	}
	if runErr != nil {
		return fmt.Errorf("doctor: 扫描返回非零: %w", runErr)
	}
	return nil
}

func boolLabel(b bool) string {
	if b {
		return "OK"
	}
	return "缺失"
}

func orDefault(v, d string) string {
	if v == "" {
		return d
	}
	return v
}
