// Package commands — doctor subcommand (部署自检 + 自动接入).
//
// medit doctor — 新设备部署唯一入口: 逐项探测本机软件/工具/包/服务,
// 输出可读矩阵, --fix 尝试自动修复 (pip 依赖走 scripts/deps_auto.py)。
package commands

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/veawho/via54Medit/internal/foundation"
	"github.com/veawho/via54Medit/internal/source"
)

var doctorCmd = &cobra.Command{
	Use:   "doctor",
	Short: "部署自检: 探测本机软件/工具/包/CDP 并报告缺口",
	Long: `doctor 逐项检查新设备集成面 (跨平台, 2026-08-21):
  - Python 解释器 (探测链: $PYTHON > python3.11 > python3 > python)
  - Python 包    (fitz/pptx/PIL; --fix 调 scripts/deps_auto.py 自动 pip 安装)
  - 浏览器       (Chrome/Edge/Chromium 探测 + CDP 9223 可达性)
  - 系统工具     (soffice/libreoffice, pdftotext, lark-cli)
  - 环境变量     (TMA_PROJECT/HLO_DIR/HERMES_HOME 等覆盖点)

输出 每项 ✓/✗ + 修复建议; 退出码 0 = 全部就绪。`,
	RunE: runDoctor,
}

var (
	doctorFix     bool
	doctorCDPPort int
)

func init() {
	doctorCmd.Flags().BoolVar(&doctorFix, "fix", false, "尝试自动修复 (pip 安装缺失 Python 包)")
	doctorCmd.Flags().IntVar(&doctorCDPPort, "port", DefaultCDPPort, "DevTools 端口")
}

type doctorItem struct {
	name   string
	ok     bool
	detail string
	hint   string
}

func runDoctor(cmd *cobra.Command, _ []string) error {
	out := cmd.OutOrStdout()
	items := []doctorItem{}
	report := func(name, detail, hint string, ok bool) {
		items = append(items, doctorItem{name: name, ok: ok, detail: detail, hint: hint})
	}

	// 1. 平台 + 二进制版本
	report("平台", fmt.Sprintf("%s/%s", runtime.GOOS, runtime.GOARCH), "", true)

	// 2. Python 解释器
	py, err := foundation.ResolvePython(nil)
	if err != nil {
		report("Python 解释器", "未找到", "安装 Python 3.10+ 或设置 $PYTHON", false)
		py = ""
	} else {
		ver := ""
		if py != "" {
			if v, verr := exec.Command(py, "--version").Output(); verr == nil {
				ver = strings.TrimSpace(string(v))
			}
		}
		report("Python 解释器", fmt.Sprintf("%s (%s)", py, ver), "", true)
	}

	// 3. Python 包 (通过解释器探测)
	if py != "" {
		for _, pkg := range []struct{ mod, label string }{
			{"fitz", "PyMuPDF (PDF/highlight)"},
			{"pptx", "python-pptx (PPT)"},
			{"PIL", "Pillow (图像)"},
		} {
			ok := pythonModuleOK(py, pkg.mod)
			hint := ""
			if !ok {
				hint = "pip install " + map[string]string{"fitz": "pymupdf", "pptx": "python-pptx", "PIL": "Pillow"}[pkg.mod]
				if doctorFix {
					if installPythonPkg(py, map[string]string{"fitz": "pymupdf", "pptx": "python-pptx", "PIL": "Pillow"}[pkg.mod]) {
						ok = true
						hint = "已自动安装"
					}
				}
			}
			report(pkg.label, boolLabel(ok), hint, ok)
		}
	}

	// 4. 浏览器 + CDP
	chrome, cerr := source.DetectChrome()
	if cerr != nil {
		report("浏览器", "未找到 Chrome/Edge/Chromium", "安装 Chrome 或设置 $CHROME_PATH", false)
	} else {
		cdp := fmt.Sprintf("http://127.0.0.1:%d", doctorCDPPort)
		ctx, cancel := context.WithTimeout(cmd.Context(), 3*time.Second)
		cdpOK := source.ChromeHealth(ctx, cdp) == nil
		cancel()
		hint := ""
		if !cdpOK {
			hint = fmt.Sprintf("`medit browser start` 自动启动调试实例 (port %d)", doctorCDPPort)
		}
		detail := filepath.Base(chrome)
		if cdpOK {
			detail += " + CDP 就绪"
		}
		report("浏览器", detail, hint, cdpOK)
	}

	// 5. 系统工具 (soffice/libreoffice 任一命中即可)
	sofficeOK := false
	for _, tool := range []struct{ name, hint string }{
		{"soffice", "LibreOffice (PPT 真渲染, 可选): brew/apt 安装 libreoffice"},
		{"libreoffice", "LibreOffice 别名 (soffice 未命中时)"},
		{"pdftotext", "poppler-utils (PDF 文本提取): brew install poppler / apt install poppler-utils"},
	} {
		p, lerr := exec.LookPath(tool.name)
		ok := lerr == nil
		if tool.name == "soffice" || tool.name == "libreoffice" {
			if ok {
				sofficeOK = true
			}
			continue // 合并为一行 "LibreOffice (soffice)"
		}
		detail := "未安装"
		if ok {
			detail = p
		}
		report("工具: "+tool.name, detail, tool.hint, ok)
	}
	loDetail := "未安装"
	loHint := "LibreOffice (PPT 真渲染, 可选): brew/apt 安装 libreoffice"
	if sofficeOK {
		loDetail = "soffice 可用"
		loHint = ""
	}
	report("工具: LibreOffice (soffice)", loDetail, loHint, sofficeOK)

	// 6. lark-cli (Feishu 集成)
	if p, lerr := exec.LookPath("lark-cli"); lerr == nil {
		report("lark-cli (飞书)", p, "", true)
	} else if env := os.Getenv("LARK_CLI"); env != "" {
		report("lark-cli (飞书)", env+" ($LARK_CLI)", "", true)
	} else {
		report("lark-cli (飞书)", "未安装", "设置 $LARK_CLI 指向可执行文件或安装 lark-cli", false)
	}

	// 7. 关键环境变量覆盖点 (info 级: 未设置不失败, 仅提示)
	envs := []struct{ name, desc string }{
		{"TMA_PROJECT", "TMA highlight 项目根"},
		{"HLO_DIR", "HLO 脚本目录"},
		{"HERMES_HOME", "skills/venv 数据根"},
		{"LIT_ROOT", "文献库根 (self_check)"},
		{"PYTHON", "Python 解释器覆盖"},
		{"CHROME_PATH", "浏览器路径覆盖"},
	}
	for _, e := range envs {
		v := os.Getenv(e.name)
		report("env: "+e.name, orDefault(v, "(未设置, 用内置默认)"), e.desc, true) // info 级, 不参与 fail
	}

	// 8. 输出
	fmt.Fprintln(out, "== medit doctor — 部署自检 ==")
	fail := 0
	for _, it := range items {
		mark := "✓"
		if !it.ok {
			mark = "✗"
			fail++
		}
		line := fmt.Sprintf("  %s %-28s %s", mark, it.name, it.detail)
		if !it.ok && it.hint != "" {
			line += fmt.Sprintf("  → %s", it.hint)
		}
		fmt.Fprintln(out, line)
	}
	fmt.Fprintf(out, "== 结果: %s (%d 项需处理; 修复建议: --fix 装 pip 包, `medit browser start` 起 Chrome) ==\n",
		boolLabel(fail == 0), fail)
	if fail > 0 {
		return fmt.Errorf("doctor: %d 项未就绪", fail)
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

// pythonModuleOK probes a module via the resolved interpreter.
func pythonModuleOK(py, mod string) bool {
	out, err := exec.Command(py, "-c", "import "+mod).CombinedOutput()
	return err == nil || len(out) == 0
}

// installPythonPkg pip-installs one package via the interpreter.
func installPythonPkg(py, pkg string) bool {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()
	return exec.CommandContext(ctx, py, "-m", "pip", "install", pkg).Run() == nil
}
