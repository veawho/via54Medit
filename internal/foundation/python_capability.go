// Capability-aware Python interpreter selection + anchored script lookup.
//
// 为什么需要这一层 (2026-09-12 实测故障)
// --------------------------------------
// “medit anno2ppt ocr“ 之前用 “ResolvePython“ 按**名字**挑解释器: 候选链是
// python3.11 → python3 → python, 谁先出现在 PATH 就用谁。本机实测:
//
//	~/.local/bin/python3.11   pymupdf ✓  paddleocr ✗  paddle ✗   ← 先被选中
//	.../python@3.10/bin/python3  三个全 ✓
//
// 于是命令直接 “ModuleNotFoundError: No module named 'paddleocr'“;
// 更糟的是**部署报告仍然写着"PaddleOCR 已就绪"** —— 因为报告用自己的解释器探测,
// 而命令用的是另一个。名字对不等于包里装了东西, 所以这里按"能不能 import"来选。
package foundation

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"
)

// OCRPythonEnv 是 OCR 专用解释器的显式覆盖变量。
//
// 显式指定的解释器**必须**满足依赖, 不满足就报错而不是悄悄换一个 ——
// 悄悄换会把"我把 PATH 配错了"这种问题藏起来, 正是本文件要消除的东西。
const OCRPythonEnv = "VIA54_OCR_PYTHON"

// OCRScriptEnv 是 OCR 脚本路径的显式覆盖变量。
const OCRScriptEnv = "VIA54_OCR_SCRIPT"

// PythonProbeTimeout bounds one capability probe. “importlib.util.find_spec“
// 本身是瞬时的, 这个上界只是防"解释器启动就卡住"(例如 Windows 上被安全软件拦)。
const PythonProbeTimeout = 20 * time.Second

// pythonProbeScript 打印出**缺失**的模块名(逗号分隔), 全都有则退出码 0。
//
// 用 “find_spec“ 而不是真 “import“: 本函数每次解析都要跑一遍, 真 import paddle
// 是秒级开销, 而 find_spec 只查文件在不在(实测 0.00s)。能 catch 的正是"装到了别的
// 解释器里"这类问题; "装了但坏掉"交给真正跑一次识别去发现(见 paddleocr_pdf_page.py --smoke)。
const pythonProbeScript = "import importlib.util as u, sys\n" +
	"missing = [m for m in sys.argv[1:] if u.find_spec(m) is None]\n" +
	"print(','.join(missing))\n" +
	"sys.exit(3 if missing else 0)\n"

// PythonCanImport 判断 exe 能否 import 全部 need。
//
// 抽成包级变量是为了让测试能注入假判定: 跨平台 CI 上造不出"有 pymupdf 没有 paddleocr"
// 的真实解释器, 而这条判定正是本文件的核心, 必须被覆盖。
var PythonCanImport = func(exe string, need []string) error {
	ctx, cancel := context.WithTimeout(context.Background(), PythonProbeTimeout)
	defer cancel()
	args := append([]string{"-c", pythonProbeScript}, need...)
	out, err := exec.CommandContext(ctx, exe, args...).CombinedOutput()
	text := strings.TrimSpace(string(out))
	if err == nil {
		return nil
	}
	var missing string
	if lines := strings.Split(text, "\n"); len(lines) > 0 {
		missing = strings.TrimSpace(lines[len(lines)-1])
	}
	if missing == "" {
		return fmt.Errorf("探测失败: %v (%s)", err, truncateForErr(text, 80))
	}
	return fmt.Errorf("缺 %s", missing)
}

func truncateForErr(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "…"
}

// ResolvePythonFor 挑出**第一个能 import 全部 need** 的解释器。
//
// 严格项(不满足就报错, 不静默回退): “cfg["python_path"]“、“$envOverride“。
// 尽力项(不满足就继续往下试): “$PYTHON“、“PythonCandidates“。
// 两个显式开关之所以严格 —— 用户写下"用这个解释器"时, 悄悄换成另一个才是更坏的结局。
//
// 返回的错误里列出**每个候选**与它缺什么, 因为"该装到哪个解释器里"才是排障要的那句话。
func ResolvePythonFor(need []string, envOverride string, cfg map[string]any) (string, error) {
	if len(need) == 0 {
		return ResolvePython(cfg)
	}

	type cand struct{ exe, from string }
	var strict, loose []cand
	seen := map[string]bool{}
	add := func(dst *[]cand, exe, from string) {
		if exe == "" || seen[exe] {
			return
		}
		seen[exe] = true
		*dst = append(*dst, cand{exe, from})
	}

	if v, ok := cfg["python_path"].(string); ok && v != "" {
		add(&strict, v, "config python_path")
	}
	if envOverride != "" {
		add(&strict, os.Getenv(envOverride), "$"+envOverride)
	}
	add(&loose, os.Getenv("PYTHON"), "$PYTHON")
	for _, c := range PythonCandidates {
		if p, err := exec.LookPath(c); err == nil {
			add(&loose, p, "PATH:"+c)
			continue
		}
		if runtime.GOOS == "windows" {
			if p, err := exec.LookPath(c + ".exe"); err == nil {
				add(&loose, p, "PATH:"+c+".exe")
			}
		}
	}

	var tried []string
	for _, c := range strict {
		if err := PythonCanImport(c.exe, need); err != nil {
			return "", fmt.Errorf("显式指定的解释器 %s (%s) %v; 请在其中执行 "+
				"`pip install %s`, 或改掉这个设置",
				c.exe, c.from, err, strings.Join(need, " "))
		}
		return c.exe, nil
	}
	for _, c := range loose {
		if err := PythonCanImport(c.exe, need); err == nil {
			return c.exe, nil
		} else {
			tried = append(tried, fmt.Sprintf("%s (%s): %v", c.exe, c.from, err))
		}
	}
	if len(tried) == 0 {
		return "", fmt.Errorf("没有找到任何 Python 解释器 (候选 %v); 设置 $%s 指定一个",
			PythonCandidates, envOverride)
	}
	hint := ""
	if envOverride != "" {
		// 只有真的存在这个开关时才提它 —— 否则会印出一个孤零零的 "$"
		hint = fmt.Sprintf(", 或用 $%s 显式指定", envOverride)
	}
	return "", fmt.Errorf("没有解释器能 import %v —— 逐个试过: %s。修法: 在目标解释器里执行 "+
		"`pip install %s`%s",
		need, strings.Join(tried, "; "), strings.Join(need, " "), hint)
}

// OCRScriptCandidates 列出 “paddleocr_pdf_page.py“ 可能所在的位置(按优先级)。
//
// 为什么不能只用相对路径: 旧实现的首选项是
// “~/.hermes/skills/via54medit/via54medit-anno2ppt-phase7/scripts/...“ —— 本机不存在
// (多了一层 “via54medit“, 且技能分发包里根本没有 “scripts/“ 目录); fallback 则是
// “filepath.Join("scripts", ...)“, 那是相对**当前工作目录**的, 站在 /tmp 里跑就变成
// “/tmp/scripts/...“。两条都落空, 于是这个命令只在"恰好 cd 到仓库根"时才工作。
//
// 现在以**仓库根**为锚(见 FindRepoRoot: 可执行文件位置与 cwd 上溯都算),
// cwd 相对路径只作为开发态的最后兜底。
func OCRScriptCandidates() []string {
	const rel = "paddleocr_pdf_page.py"
	var out []string
	add := func(p string) {
		if p == "" {
			return
		}
		for _, o := range out {
			if o == p {
				return
			}
		}
		out = append(out, p)
	}

	add(os.Getenv(OCRScriptEnv))
	if root := FindRepoRoot(); root != "" {
		add(filepath.Join(root, "scripts", rel))
		add(filepath.Join(root, "skills", "via54medit-anno2ppt-phase7", "scripts", rel))
	}
	// 兼容旧 hermes 布局: 仅当 HERMES_HOME 显式设置时才加入候选, 不作为默认。
	if os.Getenv("HERMES_HOME") != "" {
		add(HermesPath("skills", "via54medit-anno2ppt-phase7", "scripts", rel))
		add(HermesPath("skills", "via54medit", "via54medit-anno2ppt-phase7", "scripts", rel))
	}
	add(filepath.Join("scripts", rel)) // 开发态兜底, 明确排最后
	return out
}

// RepoRootEnv 显式指定仓库根(全局安装的二进制 + 仓库不在默认位置时用)。
const RepoRootEnv = "VIA54_REPO"

// repoRootMarkers 用来判定"这个目录就是仓库根"。用路径而不是单一文件名:
// go.mod 在开发态必有; 而 OCR 脚本的存在能覆盖"只分发脚本子集"的部署形态。
var repoRootMarkers = []string{"go.mod", filepath.Join("scripts", "paddleocr_pdf_page.py")}

func looksLikeRepoRoot(dir string) bool {
	for _, m := range repoRootMarkers {
		if st, err := os.Stat(filepath.Join(dir, m)); err == nil && !st.IsDir() {
			return true
		}
	}
	return false
}

// FindRepoRoot 定位仓库根, 找不到返回空串。
//
// 顺序: $VIA54_REPO > 可执行文件所在目录及其上溯 > 当前工作目录上溯。
//
// 为什么必须有 cwd 上溯这一条: 只看可执行文件位置是不够的 —— 全局安装的 medit
// 不在仓库里, 而 `go test` 时 os.Executable() 指向的也是临时构建目录。两种情况下
// "仓库内的资源在哪"只能靠从有意义的起点向上找标记文件。
func FindRepoRoot() string {
	if v := os.Getenv(RepoRootEnv); v != "" {
		if st, err := os.Stat(v); err == nil && st.IsDir() {
			return v
		}
	}
	var starts []string
	if exe, err := os.Executable(); err == nil {
		starts = append(starts, filepath.Dir(exe))
	}
	if wd, err := os.Getwd(); err == nil {
		starts = append(starts, wd)
	}
	for _, start := range starts {
		dir := start
		for i := 0; i < 8; i++ { // 上界, 免得在怪布局下无限走
			if looksLikeRepoRoot(dir) {
				return dir
			}
			parent := filepath.Dir(dir)
			if parent == dir {
				break
			}
			dir = parent
		}
	}
	return ""
}

// ResolveOCRScript 返回第一个真实存在的候选脚本路径。
//
// 找不到时把**尝试过的全部路径**列出来 —— "找不到"本身没有信息量,
// "我找过这些地方"才能让人一次改对。
//
// “$OCRScriptEnv“ 是**严格**的: 显式写下的路径不存在就报错, 不悄悄换用别的 ——
// 悄悄换会把"我把路径配错了"藏起来(与 ResolvePythonFor 对显式解释器的处理一致)。
func ResolveOCRScript() (string, error) {
	if v := os.Getenv(OCRScriptEnv); v != "" {
		if st, err := os.Stat(v); err == nil && !st.IsDir() {
			return v, nil
		}
		return "", fmt.Errorf("$%s 指向的脚本不存在: %s", OCRScriptEnv, v)
	}
	cands := OCRScriptCandidates()
	for _, p := range cands {
		if st, err := os.Stat(p); err == nil && !st.IsDir() {
			return p, nil
		}
	}
	return "", fmt.Errorf("找不到 paddleocr_pdf_page.py; 已尝试:\n  %s\n"+
		"  可用 $%s 显式指定脚本路径", strings.Join(cands, "\n  "), OCRScriptEnv)
}
