package foundation

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// 这组测试盯的是一个真实故障 (2026-09-12):
//
//	~/.local/bin/python3.11 有 pymupdf 却没有 paddleocr, 而它在候选链里排第一,
//	于是 `medit anno2ppt ocr` 直接 ModuleNotFoundError; 同时它的脚本路径首选项
//	(带一层多余 via54medit 的 ~/.hermes 路径)根本不存在, fallback 又是相对 cwd 的,
//	所以这个命令只在"恰好 cd 到仓库根"时才工作。
//
// 两处都不是"看起来坏了"的类型 —— 命令报的错是别人的; 所以要有测试钉住。

// withPythonCanImport 临时替换能力判定, 返回还原函数。
//
// 为什么必须注入: 跨平台 CI 上造不出"有 pymupdf 没有 paddleocr"的真实解释器,
// 而这条判定正是本文件的核心逻辑。
func withPythonCanImport(t *testing.T, fn func(exe string, need []string) error) {
	t.Helper()
	orig := PythonCanImport
	PythonCanImport = fn
	t.Cleanup(func() { PythonCanImport = orig })
}

func TestResolvePythonForPicksFirstSatisfying(t *testing.T) {
	var asked []string
	// 只认 "python3" 结尾的解释器 —— 模拟"python3.11 缺包, python3 才有"。
	withPythonCanImport(t, func(exe string, need []string) error {
		asked = append(asked, exe)
		if strings.HasSuffix(exe, "python3") {
			return nil
		}
		return errStub
	})

	got, err := ResolvePythonFor([]string{"paddleocr"}, "", nil)
	if err != nil {
		t.Skipf("本机没有可用的解释器候选: %v", err)
	}
	if !strings.HasSuffix(got, "python3") {
		t.Fatalf("应跳过不满足依赖的解释器, 实际选中 %q (问过: %v)", got, asked)
	}
	for _, a := range asked {
		if strings.HasSuffix(a, "python3") {
			break
		}
	}
	if asked[len(asked)-1] != got {
		t.Fatalf("最后一次探测的应该是被选中的那个: asked=%v got=%q", asked, got)
	}
}

func TestResolvePythonForReportsEveryCandidateWhenNoneSatisfies(t *testing.T) {
	withPythonCanImport(t, func(exe string, need []string) error { return errStub })

	_, err := ResolvePythonFor([]string{"paddleocr", "pymupdf"}, OCRPythonEnv, nil)
	if err == nil {
		t.Skip("本机没有解释器候选, 这条断言依赖至少有一个候选")
	}
	msg := err.Error()
	// "找不到"本身没有信息量 —— 要的是"找过哪些、各缺什么"
	if !strings.Contains(msg, "paddleocr") || !strings.Contains(msg, "pymupdf") {
		t.Fatalf("错误里必须点名缺什么: %v", err)
	}
	if !strings.Contains(msg, "python") {
		t.Fatalf("错误里必须列出试过的候选: %v", err)
	}
	if !strings.Contains(msg, OCRPythonEnv) {
		t.Fatalf("错误里必须给出显式指定的开关 $%s: %v", OCRPythonEnv, err)
	}
}

func TestResolvePythonForHonoursExplicitOverrideStrictly(t *testing.T) {
	self, err := os.Executable()
	if err != nil {
		t.Skip("拿不到可执行文件路径")
	}
	t.Setenv(OCRPythonEnv, self)

	// 1) 显式指定且满足 -> 就是它
	withPythonCanImport(t, func(string, []string) error { return nil })
	if got, err := ResolvePythonFor([]string{"paddleocr"}, OCRPythonEnv, nil); err != nil || got != self {
		t.Fatalf("显式指定且可用时应原样采用: got=%q err=%v", got, err)
	}

	// 2) 显式指定但不满足 -> 报错, **不静默换别的** ——
	//    悄悄换会把"我把解释器配错了"藏起来。
	withPythonCanImport(t, func(string, []string) error { return errStub })
	got, err := ResolvePythonFor([]string{"paddleocr"}, OCRPythonEnv, nil)
	if err == nil {
		t.Fatalf("显式指定的解释器不满足依赖时必须报错, 却返回了 %q", got)
	}
	if !strings.Contains(err.Error(), OCRPythonEnv) {
		t.Fatalf("错误里必须点明是哪个显式设置的问题: %v", err)
	}
}

func TestResolvePythonForNoNeedFallsBackToPlainResolver(t *testing.T) {
	// need 为空时不该做能力探测(否则任何调用方都要付解释器启动的代价)
	withPythonCanImport(t, func(string, []string) error {
		t.Fatal("need 为空时不该调用能力判定")
		return nil
	})
	_, _ = ResolvePythonFor(nil, "", nil)
}

// errStub 是一个固定的判定失败值。
var errStub = &stubError{}

type stubError struct{}

func (*stubError) Error() string { return "stub: 缺 paddleocr" }

func TestOCRScriptCandidatesAreAnchoredNotCwdDependent(t *testing.T) {
	root := FindRepoRoot()
	if root == "" {
		t.Skip("不在仓库内跑测试, 无法断言仓库锚定")
	}
	// 把仓库根钉住(等价于"全局安装的二进制 + 显式 $VIA54_REPO"这一部署形态),
	// 然后换 cwd —— 候选列表必须一个字都不变。
	t.Setenv(RepoRootEnv, root)

	before := OCRScriptCandidates()
	if len(before) == 0 {
		t.Fatal("候选列表不该为空")
	}
	anchored := filepath.Join(root, "scripts", "paddleocr_pdf_page.py")
	if before[0] != anchored {
		t.Fatalf("仓库内的脚本应作为首个候选 (锚定仓库根): %v", before)
	}

	orig, err := os.Getwd()
	if err != nil {
		t.Skip("拿不到 cwd")
	}
	if err := os.Chdir(t.TempDir()); err != nil {
		t.Skipf("无法切换 cwd: %v", err)
	}
	t.Cleanup(func() { _ = os.Chdir(orig) })

	after := OCRScriptCandidates()
	if len(after) != len(before) {
		t.Fatalf("候选数量不该随 cwd 变化:\n before=%v\n after=%v", before, after)
	}
	for i := range before {
		if before[i] != after[i] {
			t.Fatalf("候选顺序不该随 cwd 变化 (第 %d 项):\n before=%v\n after=%v",
				i, before, after)
		}
	}
	// cwd 相对的那条(开发态兜底)必须排最后 —— 它是唯一依赖 cwd 的候选
	if filepath.IsAbs(after[len(after)-1]) {
		t.Fatalf("最后一条应是 cwd 相对兜底, 实际是 %q", after[len(after)-1])
	}
}

func TestOCRScriptCandidatesDegradeGracefullyWithoutRepoRoot(t *testing.T) {
	// 仓库根找不到时(临时目录 + 未知二进制位置)不该崩, 仍要给出可尝试的候选;
	// 真正的报错交给 ResolveOCRScript, 它会列出全部尝试过的路径。
	t.Setenv(RepoRootEnv, "")
	orig, err := os.Getwd()
	if err != nil {
		t.Skip("拿不到 cwd")
	}
	if err := os.Chdir(t.TempDir()); err != nil {
		t.Skipf("无法切换 cwd: %v", err)
	}
	t.Cleanup(func() { _ = os.Chdir(orig) })

	if got := OCRScriptCandidates(); len(got) == 0 {
		t.Fatal("找不到仓库根时仍应给出候选(技能包 / cwd 兜底)")
	}
}

func TestResolveOCRScriptExplicitOverrideIsStrict(t *testing.T) {
	// 指向一个不存在的路径 -> 报错, 而不是悄悄改用别的候选
	t.Setenv(OCRScriptEnv, filepath.Join(t.TempDir(), "nope.py"))
	if got, err := ResolveOCRScript(); err == nil {
		t.Fatalf("$%s 指向不存在的文件时应报错, 却返回 %q", OCRScriptEnv, got)
	} else if !strings.Contains(err.Error(), OCRScriptEnv) {
		t.Fatalf("错误里应点明是 $%s 的问题: %v", OCRScriptEnv, err)
	}

	// 指向真实文件 -> 原样采用
	real := filepath.Join(t.TempDir(), "paddleocr_pdf_page.py")
	if err := os.WriteFile(real, []byte("# stub\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	t.Setenv(OCRScriptEnv, real)
	if got, err := ResolveOCRScript(); err != nil || got != real {
		t.Fatalf("应原样采用显式指定的脚本: got=%q err=%v", got, err)
	}
}

func TestResolveOCRScriptFindsRepoScriptFromBinLayout(t *testing.T) {
	// 仓库里就有这个脚本, 且可执行文件在 <repo>/bin/ 下 —— 解析必须命中它,
	// 这样才不依赖 cwd。
	if _, err := os.Stat(filepath.Join("..", "..", "scripts", "paddleocr_pdf_page.py")); err != nil {
		t.Skipf("不在仓库内跑测试 (%v)", err)
	}
	got, err := ResolveOCRScript()
	if err != nil {
		t.Fatalf("从仓库内应能找到 OCR 脚本: %v", err)
	}
	if !strings.HasSuffix(got, "paddleocr_pdf_page.py") {
		t.Fatalf("解析结果不像脚本路径: %q", got)
	}
}
