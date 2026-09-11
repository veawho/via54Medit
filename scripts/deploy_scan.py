#!/usr/bin/env python3
"""deploy_scan.py — 部署 / 更新后的**深度环境扫描 + 缺口自愈**

部署到任何设备、或更新到任何版本之后, 都跑同一条命令即可。它回答三件事:

  1. **这台设备是什么环境?** OS / 架构 / 发行版 / 容器 / 解释器 / 包管理器 / 权限 / 编码
  2. **这台设备"应该"有哪些能力?** —— 按平台过滤。与平台无关的能力会被明确标成
     ``不适用``, 而且**绝不会去安装或校验**它。例: Office 自动化在 Windows 走 COM、
     在 macOS 走原生 AppleScript、在 Linux 根本不存在; pywin32 只在 Windows 装。
  3. **缺哪些?** —— **只装缺的**, 并且**按正确通道装**: Python 包走 pip、mmx-cli 走 npm
     (它**不是** PyPI 包 —— 见下)、系统工具走 brew/apt/winget/choco/scoop; 装不了的
     (如桌面版 Office、API Key) 给出可执行的下一步。

为什么要专门做这件事
--------------------
部署工具此前有三处硬伤, 都会让"新设备一键部署"变成假动作:

  * ``pip install mmx-cli`` —— mmx-cli **不是 PyPI 包**(PyPI 上无此发行版),
    它是 npm 包(本机: ``~/.local/bin/mmx -> ../lib/node_modules/mmx-cli/dist/mmx.mjs``)。
    这条命令永远失败, 而失败被 ``--upgrade`` 的退出码吞掉, 于是"看起来装过了"。
  * **完全没检测 OCR** —— ``paddleocr`` 缺失时无人知晓, 直到 L2 中文识别那步才炸。
  * **不分平台** —— 无条件把 Windows 专属的 pywin32 也列进安装清单, 反过来
    在 Windows 上又去校验 AppleScript 通道。

用法
----
    python3 scripts/deploy_scan.py              # 扫描 + 自动补齐缺口
    python3 scripts/deploy_scan.py --check       # 只扫描, 不安装
    python3 scripts/deploy_scan.py --json        # 机器可读(供 medit doctor / CI 消费)
    python3 scripts/deploy_scan.py --skip-heavy  # 跳过重依赖(OCR/Paddle, 数百 MB)
    python3 scripts/deploy_scan.py --strict      # 平台兼容性问题也计入失败

退出码: 0 = 必需能力齐备; 1 = 仍有必需缺口 (--strict 时兼容性问题同样计失败)。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

WINDOWS, MACOS, LINUX = "windows", "macos", "linux"
ALL = (WINDOWS, MACOS, LINUX)

# 结果状态
OK = "ok"            # 已就绪
FIXED = "fixed"      # 缺失 -> 本次已补齐
MISSING = "missing"  # 缺失且没能补齐
NA = "na"            # 本平台不适用(不会安装、不会校验)
INFO = "info"        # 不可自动安装/仅提示


# --------------------------------------------------------------------------- #
# 环境探测
# --------------------------------------------------------------------------- #
def current_os():
    if os.name == "nt":
        return WINDOWS
    if sys.platform == "darwin":
        return MACOS
    return LINUX


def _run(cmd, timeout=900, env=None):
    """跑一条命令, 返回 (ok, 输出尾部)。不抛异常。"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, env=env, cwd=REPO)
    except (OSError, subprocess.SubprocessError) as e:
        return False, "%s: %s" % (type(e).__name__, e)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    return r.returncode == 0, out[-400:]


def _which(name):
    return shutil.which(name)


def _importable(module):
    try:
        __import__(module)
        return True
    except Exception:                                   # noqa: BLE001
        return False


def _pkg_managers():
    """本机可用的包管理器(按优先级)。"""
    return [m for m in ("brew", "apt-get", "dnf", "yum", "pacman",
                        "winget", "choco", "scoop") if _which(m)]


def scan_environment():
    """深度扫描: 这台设备到底是什么环境。"""
    env = {
        "os": current_os(),
        "os_name": os.name,
        "platform": sys.platform,
        "arch": os.uname().machine if hasattr(os, "uname") else os.environ.get("PROCESSOR_ARCHITECTURE", "?"),
        "python": sys.version.split()[0],
        "python_exe": sys.executable,
        "package_managers": _pkg_managers(),
        "node": _which("node") or "",
        "npm": _which("npm") or "",
        "go": _which("go") or "",
    }
    env["python_ok"] = sys.version_info >= (3, 10)
    env["encoding"] = (getattr(sys.stdout, "encoding", "") or "").lower()
    env["in_container"] = os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv")
    return env


# --------------------------------------------------------------------------- #
# 安装通道
# --------------------------------------------------------------------------- #
def pip_install(packages):
    """Python 包 —— 只走当前解释器的 pip。"""
    if isinstance(packages, str):
        packages = [packages]
    cmd = [sys.executable, "-m", "pip", "install"] + list(packages)
    ok, out = _run(cmd)
    return ok, ("pip install %s 成功" % " ".join(packages)) if ok else out


def npm_install(package):
    """npm 包 —— mmx-cli 走这里(它不是 PyPI 包)。"""
    npm = _which("npm")
    if not npm:
        return False, ("本机没有 npm/node —— 无法安装 %s。"
                       "请先装 Node.js, 再跑 `npm install -g %s`。" % (package, package))
    ok, out = _run([npm, "install", "-g", package])
    return ok, ("npm install -g %s 成功" % package) if ok else out


#: 各平台包管理器 -> (安装参数模板, 是否需要管理员)
_MGR_ARGS = {
    "brew": (["install"], False),
    "apt-get": (["install", "-y"], True),
    "dnf": (["install", "-y"], True),
    "yum": (["install", "-y"], True),
    "pacman": (["-S", "--noconfirm"], True),
    "winget": (["install", "--silent", "--accept-package-agreements", "--accept-source-agreements"], False),
    "choco": (["install", "-y"], True),
    "scoop": (["install"], False),
}


def system_install(names_by_manager):
    """系统工具 —— 按本机可用的包管理器装。

    ``names_by_manager`` 形如 ``{"brew": "poppler", "apt-get": "poppler-utils"}``。
    需要管理员权限且拿不到时会**明确报出该执行的命令**, 而不是假装成功。
    """
    for mgr in _pkg_managers():
        pkg = names_by_manager.get(mgr)
        if not pkg:
            continue
        args, needs_admin = _MGR_ARGS[mgr]
        cmd = [mgr] + args + [pkg]
        if needs_admin and hasattr(os, "geteuid") and os.geteuid() != 0:
            # 先试无密码 sudo; 不行就如实报告命令, 不静默失败
            ok, out = _run(["sudo", "-n"] + cmd)
            if not ok:
                return False, "需要管理员权限, 请手动执行: sudo %s" % " ".join(cmd)
            return True, "sudo %s 成功" % " ".join(cmd)
        ok, out = _run(cmd)
        return (True, "%s 成功" % " ".join(cmd)) if ok else (False, out)
    want = " / ".join(sorted(set(names_by_manager.values())))
    return False, ("本机没有可用的包管理器, 请手动安装: %s "
                   "(macOS: brew install %s; Linux: apt/dnf install %s)"
                   % (want, names_by_manager.get("brew", want),
                      names_by_manager.get("apt-get", want)))


# --------------------------------------------------------------------------- #
# 能力矩阵 —— 唯一事实来源
# --------------------------------------------------------------------------- #
class Cap:
    """一项能力。

    ``platforms`` 是**该能力存在的平台**。不在其中的平台会被标成 ``不适用``,
    并且**不会被安装、不会被校验** —— 这就是"只部署与系统环境相关的"的落点。
    """

    def __init__(self, key, label, platforms, kind, *, required=False, heavy=False,
                 probe=None, install=None, hint="", why="", gate=True):
        self.key = key
        self.label = label
        self.platforms = tuple(platforms)
        self.kind = kind
        self.required = required
        self.heavy = heavy
        self._probe = probe
        self._install = install
        self.hint = hint
        self.why = why
        #: 是否计入"必需缺口"的门禁。Office/Key 这类不可自动安装项不门禁, 只强力提示。
        self.gate = gate

    def applies(self, osname):
        return osname in self.platforms

    def probe(self):
        return self._probe() if self._probe else (False, "未实现探测")

    def install(self):
        if self._install is None:
            return False, self.hint or "本项无法自动安装"
        return self._install()


def _probe_office(app):
    """探测桌面版 Office 的**具体某个应用**。

    必须分开探: PPT 与 Word 是两个独立进程, 只探 PowerPoint 会把"没装 Word"
    误报成就绪(初版就是这样, 实测 Word 那行显示的是 "已探测到 PowerPoint (macOS)")。
    """
    def _p():
        # 允许别名, 免得调用点写成 "ppt" 就悄悄落进 Word 分支(初版就是这么错的:
        # PowerPoint 那一行显示成了 "Microsoft Word 16.112.1")。
        which = {"ppt": "powerpoint", "winword": "word"}.get(app, app)
        if which == "powerpoint":
            try:
                import ppt_render_engine as pre
                engines = pre.detect_engines()
            except Exception as e:                      # noqa: BLE001
                return False, "渲染引擎模块不可用: %s" % e
            hits = [n for n, k, _ in engines if k in ("com", "macos_ppt")]
            if hits:
                return True, "已探测到 %s" % ", ".join(hits)
            return False, "未探测到桌面版 PowerPoint"
        if os.name == "nt":
            try:
                import ppt_render_engine as pre
                if pre._progid_available("Word.Application"):
                    return True, "Word.Application COM 已注册"
            except Exception as e:                      # noqa: BLE001
                return False, str(e)[:160]
            return False, "未注册 Word.Application"
        if sys.platform == "darwin":
            try:
                import unified_render_engine as ure
                return ure.probe_macos_word()
            except Exception as e:                      # noqa: BLE001
                return False, "Word 通道模块不可用: %s" % e
        return False, "本平台无 Word 通道"
    return _p


def _probe_mmx():
    path = _which("mmx") or _which("mmx-cli")
    if not path:
        return False, "未安装 (npm 包 mmx-cli)"
    ok, out = _run([path, "--version"], timeout=60)
    ver = out.splitlines()[0].strip() if ok and out else "版本未知"
    if not os.environ.get("MINIMAX_API_KEY"):
        return True, "%s (缺 MINIMAX_API_KEY, 调用会失败)" % ver
    return True, ver


def build_matrix(include_heavy=True):
    """构造能力矩阵。``include_heavy=False`` 时不纳入重依赖(OCR)。"""
    caps = [
        Cap("python", "Python >= 3.10", ALL, "env", required=True,
            probe=lambda: (sys.version_info >= (3, 10), sys.version.split()[0]),
            hint="装 Python 3.10+ 并重跑; 或用 $PYTHON 指向合格解释器",
            why="全部 Python 侧工具链的运行前提", gate=True),
        Cap("pymupdf", "PyMuPDF (PDF/高亮)", ALL, "python", required=True,
            probe=lambda: (_importable("pymupdf"), "import pymupdf"),
            install=lambda: pip_install("pymupdf"),
            hint="pip install pymupdf", why="PDF 解析与高亮落位"),
        Cap("python_pptx", "python-pptx (PPT 结构)", ALL, "python", required=True,
            probe=lambda: (_importable("pptx"), "import pptx"),
            install=lambda: pip_install("python-pptx"),
            hint="pip install python-pptx", why="PPT 文本/结构提取"),
        Cap("pillow", "Pillow (图像)", ALL, "python", required=True,
            probe=lambda: (_importable("PIL"), "import PIL"),
            install=lambda: pip_install("Pillow"),
            hint="pip install Pillow", why="图片读写与裁剪"),
        Cap("pywin32", "pywin32 (Office COM)", (WINDOWS,), "python", required=True,
            probe=lambda: (_importable("win32com"), "import win32com"),
            install=lambda: pip_install("pywin32"),
            hint="pip install pywin32",
            why="Windows 上 PowerPoint/Word 的 COM 通道 —— **只在 Windows 需要**; "
                "macOS 走原生 AppleScript、Linux 无此通道, 故不在那两个平台安装"),
        Cap("node", "Node.js (含 npm)", ALL, "system", required=False,
            probe=lambda: (bool(_which("node") and _which("npm")),
                           "node=%s npm=%s" % (_which("node") or "无", _which("npm") or "无")),
            install=lambda: system_install({"brew": "node", "apt-get": "nodejs",
                                            "dnf": "nodejs", "pacman": "nodejs",
                                            "winget": "OpenJS.NodeJS.LTS", "choco": "nodejs"}),
            hint="安装 Node.js (mmx-cli 是 npm 包, 需要它)",
            why="mmx-cli 视觉引擎的运行前提"),
        Cap("mmx_cli", "mmx-cli (默认视觉引擎)", ALL, "npm", required=True,
            probe=_probe_mmx, install=lambda: npm_install("mmx-cli"),
            hint="npm install -g mmx-cli  (注意: **不是** pip install —— PyPI 上没有这个包)",
            why="VISION_PROVIDER=mmx 的默认实现; 缺它则 L3 视觉校验不可用"),
        Cap("mmx_key", "MINIMAX_API_KEY", ALL, "env", required=False, gate=False,
            probe=lambda: (bool(os.environ.get("MINIMAX_API_KEY")),
                           "已配置" if os.environ.get("MINIMAX_API_KEY") else "未配置"),
            hint="export MINIMAX_API_KEY=... (写进 ~/.zshrc / 系统环境变量)",
            why="mmx 视觉调用需要凭据; 无法由部署脚本代填"),
        Cap("powerpoint", "桌面版 PowerPoint (PPT 版式渲染)",
            (WINDOWS, MACOS), "office", gate=False,
            probe=_probe_office("powerpoint"),
            hint="装桌面版 Microsoft PowerPoint 并激活。装不了就用显式 RENDER_ENGINE=graph。",
            why="PPT 版式只能由微软引擎产出(见 docs/ppt-render-fidelity.md); "
                "Linux 没有桌面 Office, 故本平台标记为不适用"),
        Cap("word", "桌面版 Word (Word 版式渲染)",
            (WINDOWS, MACOS), "office", gate=False,
            probe=_probe_office("word"),
            hint="装桌面版 Microsoft Word 并激活; 或先用 Word 另存为 PDF 再传入。",
            why="Word 版式同样只认微软引擎; 仅当源文件是 DOC/DOCX 时才需要"),
        Cap("poppler", "poppler (pdftoppm/pdftotext)", ALL, "system", required=False,
            probe=lambda: (bool(_which("pdftoppm") or _which("pdftotext")),
                           "pdftoppm=%s" % (_which("pdftoppm") or "无")),
            install=lambda: system_install({"brew": "poppler", "apt-get": "poppler-utils",
                                            "dnf": "poppler-utils", "pacman": "poppler",
                                            "winget": "oschwartz10612.Poppler",
                                            "choco": "poppler"}),
            hint="brew install poppler / apt install poppler-utils",
            why="RENDER_RASTERIZER=pdftoppm 时需要; 默认栅格化走 pip 的 pymupdf, 故非必需"),
        Cap("browser", "Chrome/Edge/Chromium (CDP)", ALL, "system", required=False,
            probe=_probe_browser,
            install=None,
            hint="装 Chrome/Edge/Chromium, 或用 $CHROME_PATH 指定; 之后 `medit browser start`",
            why="部分检索/抓取步骤走 CDP 调试实例"),
        Cap("go", "Go 工具链", ALL, "system", required=False,
            probe=lambda: (bool(_which("go")), _which("go") or "未安装"),
            install=lambda: system_install({"brew": "go", "apt-get": "golang",
                                            "dnf": "golang", "winget": "GoLang.Go",
                                            "choco": "golang"}),
            hint="装 Go 1.21+  (若用预编译 bin/medit 则不需要)",
            why="从源码构建 bin/medit 与 bin/medit-mcp"),
        Cap("lark_cli", "lark-cli (飞书)", ALL, "system", required=False,
            probe=lambda: (bool(_which("lark-cli") or os.environ.get("LARK_CLI")),
                           _which("lark-cli") or os.environ.get("LARK_CLI") or "未配置"),
            install=None,
            hint="设置 $LARK_CLI 指向可执行文件",
            why="飞书文档/表格/告警通道"),
    ]
    if include_heavy:
        caps.insert(6, Cap(
            "ocr", "PaddleOCR (L2 中文 OCR)", ALL, "python", required=True, heavy=True,
            probe=lambda: (_importable("paddleocr") and _importable("paddle"),
                           "paddleocr=%s paddle=%s" % (_importable("paddleocr"), _importable("paddle"))),
            install=lambda: pip_install(["paddleocr", "paddlepaddle"]),
            hint="pip install paddleocr paddlepaddle  (数百 MB; 加 --skip-heavy 可跳过)",
            why="l3_vision_verify 的 L2 中文/图片识别腿; 缺它则纯图片页无法识别"))
    return caps


def _probe_browser():
    cands = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    env = os.environ.get("CHROME_PATH")
    if env and os.path.exists(env):
        return True, env
    for c in cands:
        if os.path.exists(c):
            return True, c
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        p = _which(name)
        if p:
            return True, p
    return False, "未找到 Chrome/Edge/Chromium"


# --------------------------------------------------------------------------- #
# 平台兼容性扫描 (POSIX 专属假设 = Windows 上的真故障)
# --------------------------------------------------------------------------- #
#: 这些写法在 Windows 上会指向不存在的位置, 属于**平台相关代码**。
_POSIX_PATTERNS = (
    ('"/tmp/', "硬编码 POSIX 临时目录 /tmp (Windows 上是 C:\\tmp, 通常不存在)"),
    ("'/tmp/", "硬编码 POSIX 临时目录 /tmp (Windows 上是 C:\\tmp, 通常不存在)"),
)
_FOREIGN_PATH = ("G:\\", "C:\\Users\\via54")


def scan_platform_compat():
    """扫出与当前平台不兼容的代码点。返回 (findings, scanned_files)。"""
    findings = []
    scanned = 0
    roots = [HERE, os.path.join(REPO, "skills")]
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                if fn == "deploy_scan.py":
                    # 本文件里的 `/tmp/` 是**检测规则本身**(在 _POSIX_PATTERNS 里),
                    # 不是在用 /tmp —— 否则扫描器会把自己报出来。
                    continue
                #: 测试文件里的 /tmp 不参与部署(只在 CI/本机跑), 故豁免 posix_tmp 规则;
                #: 外机路径 / 未守卫的 osascript 仍然照查。
                is_test = fn.startswith("test_")
                path = os.path.join(dirpath, fn)
                scanned += 1
                try:
                    with open(path, encoding="utf-8", errors="replace") as fh:
                        lines = fh.readlines()
                except OSError:
                    continue
                rel = os.path.relpath(path, REPO)
                for i, line in enumerate(lines, 1):
                    for pat, desc in _POSIX_PATTERNS:
                        if pat in line and "tempfile" not in line:
                            if not is_test:
                                findings.append({"file": rel, "line": i, "kind": "posix_tmp",
                                                 "detail": desc, "code": line.strip()[:100]})
                            break
                    if "osascript" in line:
                        head = "".join(lines[:i])
                        if "darwin" not in head and "sys.platform" not in line:
                            findings.append({"file": rel, "line": i, "kind": "osascript_unguarded",
                                             "detail": "osascript 未在 darwin 守卫内 (非 macOS 会失败)",
                                             "code": line.strip()[:100]})
                    for fp in _FOREIGN_PATH:
                        if fp in line:
                            findings.append({"file": rel, "line": i, "kind": "foreign_path",
                                             "detail": "引用了另一台机器的绝对路径: %s" % fp,
                                             "code": line.strip()[:100]})
    return findings, scanned


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def collect(install=True, include_heavy=True, env=None):
    """执行扫描(可选补齐缺口), 返回 ``(result_dict, osname)``。**不打印**。

    拆出这一层是为了让别的入口(``deps_auto.ensure_env``、``medit doctor``、
    ``bootstrap_device``)复用同一份结论, 而不是各自再实现一遍依赖清单 ——
    那正是本轮要消除的问题(三份清单互不同步)。
    """
    osname = current_os()
    env = env or scan_environment()
    caps = build_matrix(include_heavy=include_heavy)

    rows = []
    for cap in caps:
        if not cap.applies(osname):
            rows.append({
                "key": cap.key, "label": cap.label, "kind": cap.kind,
                "status": NA, "detail": "本平台不适用 (%s) — 不安装、不校验" % osname,
                "hint": cap.why, "required": False, "heavy": cap.heavy,
            })
            continue
        ok, detail = cap.probe()
        if ok:
            rows.append({"key": cap.key, "label": cap.label, "kind": cap.kind,
                         "status": OK, "detail": detail, "hint": cap.hint,
                         "required": cap.required, "heavy": cap.heavy})
            continue
        if install and cap._install is not None and not (cap.heavy and not include_heavy):
            fixed, msg = cap.install()
            if fixed:
                rows.append({"key": cap.key, "label": cap.label, "kind": cap.kind,
                             "status": FIXED, "detail": msg, "hint": cap.hint,
                             "required": cap.required, "heavy": cap.heavy})
                continue
            rows.append({"key": cap.key, "label": cap.label, "kind": cap.kind,
                         "status": MISSING, "detail": "%s | 自动安装失败: %s" % (detail, msg),
                         "hint": cap.hint, "required": cap.required, "heavy": cap.heavy})
            continue
        rows.append({"key": cap.key, "label": cap.label, "kind": cap.kind,
                     "status": MISSING, "detail": detail, "hint": cap.hint,
                     "required": cap.required, "heavy": cap.heavy})

    #: 每行都带上是否门禁 —— 供 deps_auto / medit doctor 等消费方判"必需缺口"。
    for r in rows:
        r.setdefault("gate", cap_gate(caps, r["key"]))

    compat, scanned = scan_platform_compat()
    blockers = [r for r in rows if r["status"] == MISSING
                and r["required"] and cap_gate(caps, r["key"])]
    warnings = [r for r in rows if r["status"] == MISSING
                and not (r["required"] and cap_gate(caps, r["key"]))]

    result = {
        "environment": env,
        "capabilities": rows,
        "compat": {"findings": compat, "scanned_files": scanned,
                   "affected_files": len({f["file"] for f in compat})},
        "summary": {
            "blockers": len(blockers),
            "warnings": len(warnings),
            "not_applicable": len([r for r in rows if r["status"] == NA]),
            "fixed": len([r for r in rows if r["status"] == FIXED]),
        },
    }
    return result, osname


def verify_platform(result):
    """自检"平台分类是否与宿主一致" —— 给 CI 在真 Windows/Linux/macOS 跑者上用。

    返回 ``(ok, problems)``。**故意不依赖任何 shell 语义**: 这段逻辑最初写在 CI 的
    workflow 里, 用了 ``2>/dev/null`` 与 ``|| true``, 结果在 Windows 跑者的 PowerShell 下
    直接崩(``Could not find a part of the path 'D:\\dev\\null'``)—— 正是本模块要报的那类
    POSIX 假设, 我自己先踩了一遍。放进脚本里既跨平台又能在本机单测。
    """
    problems = []
    env = result["environment"]
    osname = env["os"]
    caps = {r["key"]: r for r in result["capabilities"]}

    if osname not in (WINDOWS, MACOS, LINUX):
        problems.append("宿主平台识别异常: %r" % osname)
    expect = current_os()
    if osname != expect:
        problems.append("environment.os=%r 与 current_os()=%r 不一致" % (osname, expect))

    def status(key):
        return caps.get(key, {}).get("status")

    # Windows 专属能力: 非 Windows 必须"不适用"; Windows 上不得"不适用"
    if osname != WINDOWS and status("pywin32") != NA:
        problems.append("非 Windows 上 pywin32 应为 na, 实际 %s" % status("pywin32"))
    if osname == WINDOWS and status("pywin32") == NA:
        problems.append("Windows 上 pywin32 不该是 na")

    # 桌面 Office: 仅 Windows/macOS 适用
    for key in ("powerpoint", "word"):
        if osname == LINUX and status(key) != NA:
            problems.append("Linux 上 %s 应为 na, 实际 %s" % (key, status(key)))
        if osname in (WINDOWS, MACOS) and status(key) == NA:
            problems.append("%s 上 %s 不该是 na" % (osname, key))

    for key in ("ocr", "mmx_cli", "node"):
        if key not in caps:
            problems.append("能力矩阵缺少 %s" % key)
    return (not problems), problems


def run(install=True, include_heavy=True, strict=False, as_json=False, env=None):
    result, _osname = collect(install=install, include_heavy=include_heavy, env=env)
    result["strict"] = strict          # 供渲染层区分"阻塞"与"提示"
    ok = not result["summary"]["blockers"] and (not strict or not result["compat"]["findings"])
    result["ok"] = ok
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _render(result)
    return 0 if ok else 1


def cap_gate(caps, key):
    for c in caps:
        if c.key == key:
            return c.gate
    return True


_MARK = {OK: "✓", FIXED: "＋", MISSING: "✗", NA: "·", INFO: "i"}


def _render(res):
    e = res["environment"]
    print("== 1. 环境深度扫描 ==")
    print("  OS        : %s (%s/%s)   容器: %s" % (e["os"], e["platform"], e["arch"],
                                                 "是" if e["in_container"] else "否"))
    print("  解释器    : %s  (Python %s)" % (e["python_exe"], e["python"]))
    print("  包管理器  : %s" % (", ".join(e["package_managers"]) or "无"))
    print("  工具链    : node=%s npm=%s go=%s" % (e["node"] or "无", e["npm"] or "无", e["go"] or "无"))
    print("  输出编码  : %s" % (e["encoding"] or "未知"))
    print()
    print("== 2. 能力矩阵 (按平台过滤) ==")
    for r in res["capabilities"]:
        mark = _MARK.get(r["status"], "?")
        print("  %s %-34s %s" % (mark, r["label"], r["detail"]))
        if r["status"] == MISSING and r["hint"]:
            print("        → 处理: %s" % r["hint"])
    print()
    print("== 3. 平台兼容性 ==")
    c = res["compat"]
    if not c["findings"]:
        print("  ✓ 扫描 %d 个 .py, 未发现与 %s 不兼容的代码点" % (c["scanned_files"], e["os"]))
    else:
        # 非 --strict 时这是**提示**不是阻塞(所以用 ~ 而不是 ✗), 免得与"必需缺口"混淆。
        mark = "✗" if res.get("strict") else "~"
        print("  %s 扫描 %d 个 .py, 发现 %d 处, 涉及 %d 个文件 (加 --strict 可让它计失败):"
              % (mark, c["scanned_files"], len(c["findings"]), c["affected_files"]))
        for f in c["findings"][:8]:
            print("      %s:%d  %s" % (f["file"], f["line"], f["detail"]))
        if len(c["findings"]) > 8:
            print("      ... 其余 %d 处见 --json" % (len(c["findings"]) - 8))
    s = res["summary"]
    print()
    print("== 结果: %s (必需缺口 %d · 提示 %d · 本平台不适用 %d · 本次补齐 %d) =="
          % ("就绪" if res["ok"] else "未就绪", s["blockers"], s["warnings"],
             s["not_applicable"], s["fixed"]))


def main(argv):
    as_json = "--json" in argv
    install = "--check" not in argv
    strict = "--strict" in argv
    include_heavy = "--skip-heavy" not in argv
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                   # noqa: BLE001
        pass
    if "--verify-platform" in argv:
        # CI 用: 在真 Windows/Linux/macOS 跑者上验"平台分类是否与宿主一致"。
        # 只读不装, 且不打印整份报告 —— 避免依赖任何 shell 重定向。
        result, _ = collect(install=False, include_heavy=include_heavy)
        ok, problems = verify_platform(result)
        caps = {r["key"]: r["status"] for r in result["capabilities"]}
        if ok:
            print("平台分类自检 OK: os=%s pywin32=%s powerpoint=%s word=%s ocr=%s mmx_cli=%s"
                  % (result["environment"]["os"], caps.get("pywin32"), caps.get("powerpoint"),
                     caps.get("word"), caps.get("ocr"), caps.get("mmx_cli")))
            return 0
        for p in problems:
            print("  ✗ %s" % p)
        return 1
    return run(install=install, include_heavy=include_heavy,
               strict=strict, as_json=as_json)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
