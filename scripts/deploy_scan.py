#!/usr/bin/env python3
"""deploy_scan.py — 部署 / 更新后的**深度环境扫描 + 缺口自愈**

部署到任何设备、或更新到任何版本之后, 都跑同一条命令即可。它回答四件事:

  1. **这台设备是什么环境?** OS / 架构 / 发行版 / 容器 / 解释器 / 包管理器 / 权限 / 编码
  2. **这台设备"应该"有哪些能力?** —— 按平台过滤。与平台无关的能力会被明确标成
     ``不适用``, 而且**绝不会去安装或校验**它。例: Office 自动化在 Windows 走 COM、
     在 macOS 走原生 AppleScript、在 Linux 根本不存在; pywin32 只在 Windows 装。
  3. **缺哪些?** —— **只装缺的**, 并且**按正确通道装**: Python 包走 pip、mmx-cli 走 npm
     (它**不是** PyPI 包 —— 见下)、系统工具走 brew/apt/winget/choco/scoop; 装不了的
     (如桌面版 Office、API Key) 给出可执行的下一步。
  4. **装完真的好了吗?** —— 每次安装之后**立刻复验**; 安装器报成功而复验失败, 一律
     记成"仍然缺失", 并把失败原因一并报出 (见下 §装后复验)。

为什么要专门做这件事
--------------------
部署工具此前有三处硬伤, 都会让"新设备一键部署"变成假动作:

  * ``pip install mmx-cli`` —— mmx-cli **不是 PyPI 包**(PyPI 上无此发行版),
    它是 npm 包(本机: ``~/.local/bin/mmx -> ../lib/node_modules/mmx-cli/dist/mmx.mjs``)。
    这条命令永远失败, 而失败被 ``--upgrade`` 的退出码吞掉, 于是"看起来装过了"。
  * **完全没检测 OCR** —— ``paddleocr`` 缺失时无人知晓, 直到 L2 中文识别那步才炸。
  * **不分平台** —— 无条件把 Windows 专属的 pywin32 也列进安装清单, 反过来
    在 Windows 上又去校验 AppleScript 通道。

本轮 (v5.4.36) 参考了两个成熟项目的部署方式, 借来下面这些机制
-------------------------------------------------------------
参考 ``hermes-agent`` (``scripts/install.sh`` / ``hermes_cli/dep_ensure.py`` /
``hermes_cli/managed_uv.py``) 与 ``openclaw`` (``install.sh`` / ``install-cli.sh`` /
``install.ps1``, 见其 ``docs/install/installer.md``):

  * **探测与安装分离** (两者都有): 探测用 Python 做 —— ``shutil.which`` 全平台可用、
    毫秒级; 不必为"node 装了吗"去拉起一个 shell。安装才走平台通道。
    hermes 的 ``dep_ensure.py`` 把这个理由写在文件头上, 这里照做。
  * **单能力补齐** (hermes ``--ensure node,browser``): ``--only KEY[,KEY]``。让别的入口
    (``install_mmx``、``bootstrap_device``、未来的 GUI 部署器)按需回调同一引擎,
    而不是各自再写一份清单。
  * **装后复验** (hermes: "uv installer reported success but binary not found" → exit 1;
    openclaw: 残留 ``.openclaw-lifecycle-pending`` 标记时必须**判定失败**, 而不是把
    "跳过了生命周期脚本的包"报成安装成功)。这正是本项目在 Word 通道上踩过的坑:
    ``save as`` 返回 rc=0 却**没有任何产出**。所以这里规定 —— 安装器说什么不算,
    **复验通过才算**。
  * **探测要有超时** (openclaw: 探测默认 5 秒、完成的探测提前返回)。本项目的 Office
    探测会走 AppleEvent, 卡住时(``-1712`` 超时)能把部署无限期挂住; 现在每个探测都有
    上界, 超时按"未就绪"处理并给出可操作提示。
  * **探测"真的能跑"而不是"文件在"** (openclaw: "every installer probes the exact npm
    executable it will use; an unreadable npm version stops before package mutation").
    实测教训: ``pdftoppm --version`` 在 poppler 上**不是**合法用法(它把 ``--version``
    当文件名, 报 I/O Error), 只有 ``-v`` 可用。所以每个工具的版本开关各自声明。
  * **私有前缀兜底, 不动系统** (openclaw ``install-cli.sh`` 全程无需 root, 装进
    ``~/.openclaw``; hermes 把 uv/node 装进 ``$HERMES_HOME/bin``、``$HERMES_HOME/node``)。
    ``npm install -g`` 撞权限时自动退回 ``$VIA54_HOME/tools/node`` —— 不 sudo、不污染系统
    node_modules。
  * **不静默越过解释器管理边界** (openclaw: "an unreadable npm version stops before
    package mutation"; 本项目 v5.4.3 的既有决定): 撞上 PEP 668
    (externally-managed-environment) 时**默认不追加** ``--break-system-packages``,
    而是报出三个可执行选项; 只有显式 ``VIA54_ALLOW_BREAK_SYSTEM=1`` 才越界。
  * **``--dry-run``** (openclaw): 只打印"将要执行的动作", 不落地任何修改。
  * **安装方式戳记** (hermes ``.install_method``): 记录每个能力**实际用了哪条通道**,
    下次沿用同一条 —— 免得这次从私有前缀装、下次又去撞全局权限。
  * **阶段协议 + JSON 进度帧** (hermes ``--stage`` / ``emit_stage_json``): ``--stage``
    让外层部署器能分步展示进度, 而不是等一大坨输出。
  * **退出码有语义** (openclaw: 非法 ``--install-method`` 退出 2): 0 = 就绪,
    1 = 仍有必需缺口, 2 = **用法错误**(不该被当成"环境有问题")。
  * **环境变量镜像所有开关** (openclaw ``OPENCLAW_*``): CI / 无人值守部署用得上。
  * **不做交互** (两者都规定 CI 里绝不提示): 本工具**从不提示**。因此不提供
    ``--no-prompt`` —— 它已经是默认行为, 提供一个空开关只会让人误以为需要它。

用法
----
    python3 scripts/deploy_scan.py                 # 扫描 + 自动补齐缺口
    python3 scripts/deploy_scan.py --check          # 只扫描, 不安装
    python3 scripts/deploy_scan.py --dry-run        # 只打印将要做什么, 不改动任何东西
    python3 scripts/deploy_scan.py --only ocr       # 只处理指定能力(逗号分隔)
    python3 scripts/deploy_scan.py --list           # 列出所有能力键
    python3 scripts/deploy_scan.py --json           # 机器可读(供 medit doctor / CI 消费)
    python3 scripts/deploy_scan.py --skip-heavy     # 跳过重依赖(OCR/Paddle, 数百 MB)
    python3 scripts/deploy_scan.py --strict         # 平台兼容性问题也计入失败
    python3 scripts/deploy_scan.py --stage deps     # 只跑一个阶段: env|deps|compat|all

对应的环境变量(CI 用): ``VIA54_DRY_RUN`` / ``VIA54_ONLY`` / ``VIA54_SKIP_HEAVY`` /
``VIA54_STRICT`` / ``VIA54_JSON`` / ``VIA54_STAGE`` / ``VIA54_HOME`` /
``VIA54_ALLOW_BREAK_SYSTEM``。

退出码: 0 = 必需能力齐备; 1 = 仍有必需缺口 (--strict 时兼容性问题同样计失败);
2 = 用法错误。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

WINDOWS, MACOS, LINUX = "windows", "macos", "linux"
ALL = (WINDOWS, MACOS, LINUX)

# 结果状态
OK = "ok"            # 已就绪
FIXED = "fixed"      # 缺失 -> 本次已补齐(且**复验通过**)
MISSING = "missing"  # 缺失且没能补齐
NA = "na"            # 本平台不适用(不会安装、不会校验)
INFO = "info"        # 不可自动安装/仅提示
PLAN = "plan"        # --dry-run: 计划安装, 未落地

#: 退出码语义(openclaw: 非法取值退出 2, 与"环境有问题"区分开)
EXIT_OK, EXIT_GAP, EXIT_USAGE = 0, 1, 2

#: 私有前缀 —— 借鉴 hermes 的 ``$HERMES_HOME`` / openclaw 的 ``~/.openclaw``:
#: 需要"不 sudo 也能装"时, 一律装到这里, 不碰系统的 node_modules / site-packages。
VIA54_HOME = os.environ.get("VIA54_HOME") or os.path.join(os.path.expanduser("~"), ".via54medit")
NODE_PREFIX = os.path.join(VIA54_HOME, "tools", "node")
STAMP_PATH = os.path.join(VIA54_HOME, ".deploy_stamp.json")

#: 安装超时上界(秒)。npm/pip 抓包卡住是真实故障(openclaw 专门为 npm 探测设 5 秒上界)。
PIP_TIMEOUT = 1800
NPM_TIMEOUT = 900

#: ├─ 外进程工具探测(``--version``)的上界 —— 交给 ``subprocess.run(timeout=)``,
#:    这条路径能真正杀掉子进程, 是干净的界。
TOOL_TIMEOUT = 20

#: ├─ **跨 GUI/授权边界**的探测(Office 的 AppleEvent)才需要的"线程上界"。
#:    默认关闭, 见 ``_probe_with_timeout`` 里的理由 —— 给"进程内 import"设上界
#:    是一个**假阴性发生器**: paddle 首次 import 会编译/初始化(实测那条
#:    "No ccache found ... recompiling all source files" 警告就是它), 一旦超过
#:    上界就被误报成"没装"; 更糟的是被掐断的 daemon 线程会把 import 留在半成品
#:    状态, 让同进程里**下一次**探测的结果也跟着抖 —— 同一台机器两次结论不同。
PROBE_TIMEOUT = None

_TRUE = ("1", "true", "yes", "on")


def _env_flag(name):
    return (os.environ.get(name) or "").strip().lower() in _TRUE


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
                           timeout=timeout, env=env, cwd=REPO,
                           encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError) as e:
        return False, "%s: %s" % (type(e).__name__, e)
    out = ((r.stdout or "") + (r.stderr or "")).strip()
    return r.returncode == 0, out[-400:]


def _private_bin_dirs():
    """私有前缀里的可执行文件目录。

    hermes 的探测就带这一层(``_has_hermes_agent_browser`` 会查
    ``$HERMES_HOME/node/bin`` 与 ``node_modules/.bin``)—— 否则"从私有前缀装的"
    会被自己的探测判成"没装", 于是每次部署都重装一遍。
    """
    if os.name == "nt":
        # npm --prefix 在 Windows 上把 .cmd 垫片直接放在 prefix 目录里
        return [NODE_PREFIX]
    return [os.path.join(NODE_PREFIX, "bin")]


def _which(name):
    """在 PATH 与私有前缀里找可执行文件。"""
    p = shutil.which(name)
    if p:
        return p
    for d in _private_bin_dirs():
        for cand in (os.path.join(d, name), os.path.join(d, name + ".cmd"),
                     os.path.join(d, name + ".exe")):
            if os.path.isfile(cand) and os.access(cand, os.X_OK):
                return cand
    return None


def _pkg_managers():
    """本机可用的包管理器(按优先级)。"""
    return [m for m in ("brew", "apt-get", "dnf", "yum", "pacman",
                        "winget", "choco", "scoop") if _which(m)]


def is_interactive():
    """是否有真人盯着终端。

    借鉴两者共同的纪律: 任何"要人点一下"的动作只在真交互时做, CI 里一律走
    非交互分支(打印命令而非弹窗)。本工具当前不对用户提问, 这个判断只用于
    决定**要不要触发系统级安装对话框**(如 macOS 的 Command Line Tools)。
    """
    try:
        return bool(sys.stdin.isatty() and sys.stderr.isatty())
    except Exception:                                   # noqa: BLE001
        return False


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
        "via54_home": VIA54_HOME,
        "interactive": is_interactive(),
    }
    env["python_ok"] = sys.version_info >= (3, 10)
    env["encoding"] = (getattr(sys.stdout, "encoding", "") or "").lower()
    env["in_container"] = os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv")
    try:
        env["writable_home"] = os.access(VIA54_HOME, os.W_OK) if os.path.isdir(VIA54_HOME) \
            else os.access(os.path.dirname(VIA54_HOME) or "/", os.W_OK)
    except Exception:                                   # noqa: BLE001
        env["writable_home"] = False
    return env


# --------------------------------------------------------------------------- #
# 探测工具: 真的跑一次, 而不是只看文件在不在
# --------------------------------------------------------------------------- #
def _probe_tool(names, version_flag="--version", timeout=TOOL_TIMEOUT):
    """跑一次 ``--version`` 以确认**这个可执行文件真的能用**。

    openclaw 的经验: "every installer probes the exact executable it will use";
    一个 exit 非零的二进制不算"就绪"(它在 fresh macOS 上就是 CLT 的残缺垫片)。
    注意版本开关必须**逐个工具声明**: ``pdftoppm --version`` 会把 ``--version``
    当文件名, 报 I/O Error —— 实测踩过, 所以 poppler 传的是 ``-v``。
    """
    if isinstance(names, str):
        names = (names,)
    for n in names:
        p = _which(n)
        if not p:
            continue
        ok, out = _run([p, version_flag], timeout=timeout)
        first = (out.splitlines()[0].strip() if out else "")
        if ok:
            return True, "%s  (%s)" % (first or p, p)
        return False, "%s 在 PATH 里, 但执行失败: %s" % (p, first or "无输出")
    return False, "未安装 (%s)" % " / ".join(names)


def _import_probe(module):
    """import 探测 —— 失败时**把异常原因带出来**。

    原先的实现只在内部 ``__import__`` 后返回布尔, 异常被吞掉, 于是报告里只有
    "paddleocr=False": 分不清是没装、装坏了、还是 ABI/依赖不匹配。部署排障要的
    正是这句话。
    """
    try:
        __import__(module)
    except Exception as e:                              # noqa: BLE001
        return False, "%s 导入失败: %s: %s" % (module, type(e).__name__, str(e)[:160])
    return True, "import %s 正常" % module


def _probe_with_timeout(fn, timeout, label):
    """给**跨 GUI/授权边界**的探测加上界。

    openclaw 的探测默认 5 秒上界, 那是给"拉起外部进程问一句"用的。本项目里真正需要
    上界的是 Office: 它走 AppleEvent, 系统弹窗没人点时会一直卡着(``-1712``),
    把整个部署挂死。所以只有这类探测声明 ``probe_timeout``。

    **不要**给"进程内 import"套这层上界 —— 那样只会制造假阴性: 重的包(如 paddle)
    首次 import 会编译/初始化, 超过任何小上界就被误报"没装"; 而且被 ``join`` 超时
    掐断的 daemon 线程会继续在后台把 import 跑完, 使同进程里下一次探测得到不同
    结果 —— 我在本机实测到过"同一条命令两次一个 missing 一个 ok"。

    用 daemon 线程: 即便探测本身永远不返回, 也不会拦住解释器退出。
    """
    if not timeout or timeout <= 0:
        try:
            return fn()
        except Exception as e:                          # noqa: BLE001
            return False, "探测异常: %s" % e
    box = {}

    def _target():
        try:
            box["v"] = fn()
        except Exception as e:                          # noqa: BLE001
            box["v"] = (False, "探测异常: %s" % e)

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return False, ("探测超时 (%.0fs, %s) —— 多半被系统授权/弹窗拦住, 需要人工点一次"
                       % (timeout, label))
    return box.get("v") or (False, "探测无结果")


# --------------------------------------------------------------------------- #
# 安装通道 —— 命令先构造出来, 这样 --dry-run 能打印**真实**将执行的命令
# --------------------------------------------------------------------------- #
def pip_cmd(packages, python=None):
    """构造 pip 安装命令。

    ``python`` 用于**把包装进指定的解释器** —— OCR 就是这样: 真正跑 OCR 的解释器
    未必是部署脚本自己的那个(实测本机 python3.11 缺 paddleocr, python3 才有)。
    往错的那个装, 探测会一直说"缺", 而人去看的时候又"明明装过了"。
    """
    if isinstance(packages, str):
        packages = [packages]
    return [python or sys.executable, "-m", "pip", "install"] + list(packages)


def npm_cmd(package, prefix=None):
    cmd = [_which("npm") or "npm", "install", "-g"]
    if prefix:
        cmd += ["--prefix", prefix]
    return cmd + [package]


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

#: 这些包管理器在无人值守时必须压掉交互式对话框。
#: hermes 在 apt 上设 ``DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a``。
_MGR_ENV = {
    "apt-get": {"DEBIAN_FRONTEND": "noninteractive", "NEEDRESTART_MODE": "a"},
}


def system_cmd(names_by_manager, mgr=None, sudo=False):
    """构造系统包安装命令; 返回 ``(cmd, manager, needs_admin)`` 或 ``(None, None, False)``。"""
    for m in ([mgr] if mgr else _pkg_managers()):
        pkg = names_by_manager.get(m)
        if not pkg:
            continue
        args, needs_admin = _MGR_ARGS[m]
        cmd = (["sudo"] if (sudo and needs_admin) else []) + [m] + args + [pkg]
        return cmd, m, needs_admin
    return None, None, False


#: 最近一次安装实际用的通道 —— 写进部署戳记(hermes 的 ``.install_method``)。
LAST_INSTALL = {}


def _note_channel(channel, command, **extra):
    rec = {"channel": channel, "command": command}
    rec.update(extra)
    LAST_INSTALL.clear()
    LAST_INSTALL.update(rec)


# --------------------------------------------------------------------------- #
# 部署戳记 (hermes ``.install_method`` 的做法)
# --------------------------------------------------------------------------- #
def read_stamp():
    try:
        with open(STAMP_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_stamp(caps_record, extra=None):
    """记录"每个能力实际用了哪条通道", 供下次沿用。写不了就静默跳过 —— 不能因为
    记不了账就让部署失败(这一点 hermes 也强调: 戳记写在安装树旁边, 不写共享数据目录)。"""
    data = read_stamp()
    data["os"] = current_os()
    data["python_exe"] = sys.executable
    data["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    caps = data.get("capabilities")
    data["capabilities"] = caps if isinstance(caps, dict) else {}
    data["capabilities"].update(caps_record)
    if extra:
        data.update(extra)
    try:
        os.makedirs(VIA54_HOME, exist_ok=True)
        with open(STAMP_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        return STAMP_PATH
    except OSError:
        return None


def _remembered_npm_prefix(package):
    """上次这个 npm 包装到哪个前缀了 —— 沿用同一条通道, 别再撞一次权限。"""
    caps = read_stamp().get("capabilities") or {}
    for rec in caps.values():
        if isinstance(rec, dict) and rec.get("package") == package and rec.get("prefix"):
            return rec["prefix"]
    return None


# --------------------------------------------------------------------------- #
# 安装动作
# --------------------------------------------------------------------------- #
_PEP668_MARK = ("externally-managed-environment", "externally managed")


def pip_install(packages, python=None):
    """Python 包 —— 默认走当前解释器的 pip, 可指定装进另一个解释器(见 pip_cmd)。

    撞上 PEP 668 时**默认不越过**这道边界(本项目 v5.4.3 的既定决定: 是否突破由
    解释器管理方(uv/系统/Homebrew)划下的边界, 不该由部署脚本代用户决定)。
    这与 openclaw "探测不通过就停在改包之前" 是同一种克制。
    """
    pkgs = [packages] if isinstance(packages, str) else list(packages)
    cmd = pip_cmd(pkgs, python)
    ok, out = _run(cmd, timeout=PIP_TIMEOUT)
    if ok:
        _note_channel("pip", " ".join(cmd))
        return True, "pip install %s 成功" % " ".join(pkgs)

    if any(m in out.lower() for m in _PEP668_MARK):
        if _env_flag("VIA54_ALLOW_BREAK_SYSTEM"):
            ok2, out2 = _run(cmd + ["--break-system-packages"], timeout=PIP_TIMEOUT)
            if ok2:
                _note_channel("pip", " ".join(cmd + ["--break-system-packages"]))
                return True, "pip install %s 成功 (按 VIA54_ALLOW_BREAK_SYSTEM 显式授权的 --break-system-packages)" % " ".join(pkgs)
            return False, "已显式授权越界, 但仍失败: %s" % out2
        return False, (
            "被解释器管理方拦下 (PEP 668 externally-managed-environment)。"
            "本工具**默认不越过**这道边界。三个可选做法:\n"
            "     1) 用虚拟环境(推荐): python3 -m venv .venv && .venv/bin/python -m pip install %s\n"
            "     2) 装进托管前缀: %s --user %s\n"
            "     3) 明确授权越界后重跑: VIA54_ALLOW_BREAK_SYSTEM=1 python3 scripts/deploy_scan.py --only <该能力键>"
            % (" ".join(pkgs), sys.executable, " ".join(pkgs)))

    return False, out


def npm_install(package):
    """npm 包 —— mmx-cli 走这里(它不是 PyPI 包)。

    通道顺序(全部无需 sudo, 不碰系统 node_modules):
      1. 上次成功的私有前缀(若有戳记) —— 沿用同一条通道
      2. 全局 ``npm install -g``
      3. 私有前缀 ``$VIA54_HOME/tools/node`` —— openclaw ``install-cli.sh`` 的 rootless 思路

    每一步都**装完立刻复验**可执行文件; 只有复验过了才认为成功 ——
    "安装器说成功"本身不算证据。
    """
    npm = _which("npm")
    if not npm:
        return False, ("本机没有 npm/node —— 无法安装 %s。"
                       "请先装 Node.js, 再跑 `npm install -g %s`。" % (package, package))

    attempts = []
    remembered = _remembered_npm_prefix(package)
    if remembered:
        attempts.append((remembered, "沿用上次成功的私有前缀"))
    attempts.append((None, "全局安装"))
    if not any(p and os.path.abspath(p) == os.path.abspath(NODE_PREFIX) for p, _ in attempts):
        attempts.append((NODE_PREFIX, "私有前缀(无需管理员权限)"))

    last = ""
    for prefix, why in attempts:
        cmd = npm_cmd(package, prefix)
        ok, out = _run(cmd, timeout=NPM_TIMEOUT)
        if ok and _which(package):
            _note_channel("npm", " ".join(cmd), package=package, prefix=prefix or "")
            return True, "npm install %s 成功 (%s)" % (package, why)
        if ok and not _which(package):
            # openclaw 的那类教训: 命令成功 ≠ 东西可用。必须说出来。
            last = "命令返回成功, 但 %r 仍不在 PATH/私有前缀里 (装到别处去了)" % package
        else:
            last = out
    return False, ("npm 安装 %s 失败: %s\n     手动兜底: %s"
                   % (package, last, " ".join(npm_cmd(package, NODE_PREFIX))))


def system_install(names_by_manager):
    """系统工具 —— 按本机可用的包管理器装。

    ``names_by_manager`` 形如 ``{"brew": "poppler", "apt-get": "poppler-utils"}``。
    需要管理员权限且拿不到时会**明确报出该执行的命令**, 而不是假装成功。
    """
    cmd, mgr, needs_admin = system_cmd(names_by_manager)
    if cmd is None:
        want = " / ".join(sorted(set(names_by_manager.values())))
        return False, ("本机没有可用的包管理器, 请手动安装: %s "
                       "(macOS: brew install %s; Linux: apt/dnf install %s)"
                       % (want, names_by_manager.get("brew", want),
                          names_by_manager.get("apt-get", want)))
    env = None
    if mgr in _MGR_ENV:
        env = dict(os.environ)
        env.update(_MGR_ENV[mgr])

    if needs_admin and hasattr(os, "geteuid") and os.geteuid() != 0:
        # 先试无密码 sudo; 不行就如实报告命令, 不静默失败, 也**不去提示输密码**
        ok, out = _run(["sudo", "-n"] + cmd, timeout=PIP_TIMEOUT, env=env)
        if not ok:
            return False, "需要管理员权限, 请手动执行: sudo %s" % " ".join(cmd)
        _note_channel("system", "sudo " + " ".join(cmd), manager=mgr)
        return True, "sudo %s 成功" % " ".join(cmd)

    ok, out = _run(cmd, timeout=PIP_TIMEOUT, env=env)
    if ok:
        _note_channel("system", " ".join(cmd), manager=mgr)
        return True, "%s 成功" % " ".join(cmd)
    return False, out


# --------------------------------------------------------------------------- #
# 能力矩阵 —— 唯一事实来源
# --------------------------------------------------------------------------- #
class Cap:
    """一项能力。

    ``platforms`` 是**该能力存在的平台**。不在其中的平台会被标成 ``不适用``,
    并且**不会被安装、不会被校验** —— 这就是"只部署与系统环境相关的"的落点。

    ``plan`` 是 --dry-run 用的"将要执行的命令"; 没给就退回 ``hint``。
    ``probe_timeout`` 给会卡住的探测(如 AppleEvent)加上界。
    """

    def __init__(self, key, label, platforms, kind, *, required=False, heavy=False,
                 probe=None, install=None, plan=None, hint="", why="", gate=True,
                 probe_timeout=None):
        self.key = key
        self.label = label
        self.platforms = tuple(platforms)
        self.kind = kind
        self.required = required
        self.heavy = heavy
        self._probe = probe
        self._install = install
        self.plan = plan
        self.hint = hint
        self.why = why
        #: 是否计入"必需缺口"的门禁。Office/Key 这类不可自动安装项不门禁, 只强力提示。
        self.gate = gate
        #: 探测超时(秒); None 表示用默认上界。
        self.probe_timeout = probe_timeout

    def applies(self, osname):
        return osname in self.platforms

    def probe(self):
        if self._probe is None:
            return False, "未实现探测"
        return _probe_with_timeout(self._probe,
                                   PROBE_TIMEOUT if self.probe_timeout is None else self.probe_timeout,
                                   self.key)

    def install(self):
        if self._install is None:
            return False, self.hint or "本项无法自动安装"
        return self._install()

    def plan_text(self):
        if callable(self.plan):
            try:
                return self.plan()
            except Exception as e:                      # noqa: BLE001
                return "计划生成失败: %s" % e
        return self.plan or self.hint or "（无自动安装通道）"

    def installable(self):
        return self._install is not None


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
    """mmx-cli 可执行文件本身是否可用。

    **只判"二进制能用", 不判凭据** —— 凭据是另一件独立的事, 由 ``_probe_mmx_auth()``
    按 mmx 自己的状态回答。旧版在这里用 ``MINIMAX_API_KEY`` 下结论, 结果既会误报
    ("缺 key, 调用会失败" —— 而 mmx 早已认证且真能调通), 也会漏报。一件事一个人管。
    """
    path = _mmx_bin()
    if not path:
        return False, "未安装 (npm 包 mmx-cli)"
    ok, out = _run([path, "--version"], timeout=60)
    ver = out.splitlines()[0].strip() if ok and out else "版本未知"
    if not ok:
        return False, "%s 存在但执行失败(不该发生): %s" % (path, ver)
    return True, ver


# --------------------------------------------------------------------------- #
# OCR 的解释器与脚本定位
#
# 这一节存在的唯一理由: **"用哪个解释器跑 OCR" 必须只定一次, 且部署与命令要一致。**
#
# 实测故障 (2026-09-12): 本机 ``~/.local/bin/python3.11`` 有 pymupdf 却没有 paddleocr,
# 而它在 ``ResolvePython`` 的候选链里排第一, 于是 ``medit anno2ppt ocr`` 直接
# ModuleNotFoundError; 同时部署扫描用自己的 ``sys.executable``(装了 paddle 的 3.10)探测,
# 照样报"✓ PaddleOCR 已就绪"。两句话各说各话 —— 这就是"假就绪"的典型形态。
#
# 规则与 Go 侧 ``foundation.ResolvePythonFor`` / ``ResolveOCRScript`` **必须一致**
# (候选链顺序也要一致), 否则同一个问题在两处会得出不同结论。
# --------------------------------------------------------------------------- #

#: OCR 专用解释器 / 脚本的显式覆盖(与 Go 侧同名常量)
OCR_PYTHON_ENV = "VIA54_OCR_PYTHON"
OCR_SCRIPT_ENV = "VIA54_OCR_SCRIPT"

#: 真正跑 OCR 所需的模块。pymupdf 也要 —— 脚本第一步就用它把 PDF 页渲染成图。
OCR_REQUIRED_MODULES = ("paddleocr", "paddle", "pymupdf")

#: 解释器候选链, 与 Go 侧 ``foundation.PythonCandidates`` 保持一致
OCR_PYTHON_CANDIDATES = ("python3.11", "python3", "python")

#: 只查"模块在不在", 不真 import —— 见 ``_python_missing_modules``
_PYTHON_PROBE = ("import importlib.util as u, sys\n"
                 "missing = [m for m in sys.argv[1:] if u.find_spec(m) is None]\n"
                 "print(','.join(missing))\n"
                 "sys.exit(3 if missing else 0)\n")



def _python_missing_modules(exe, modules):
    """返回 ``exe`` 里缺失的模块名列表; 探测本身失败返回 ``None``。

    用 ``importlib.util.find_spec`` 而不是真 ``import``: 只查文件在不在(实测 0.00s),
    而本探测会被管线第 [0] 步**反复**调用, 真 import paddle 是秒级开销。
    它能抓住的正是"装到别的解释器里去了"这一类;"装了但跑不起来"交给 ``ocr_smoke_test``。
    """
    try:
        r = subprocess.run([exe, "-c", _PYTHON_PROBE] + list(modules),
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode == 0:
        return []
    lines = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
    return [m for m in lines[-1].split(",") if m] if lines else list(modules)


def ocr_python():
    """定出**跑 OCR 用哪个解释器**(同时也是依赖该装到哪)。返回 ``(exe, 依据)``。

    规则(与 Go 侧 ``ResolvePythonFor`` 一致):

    1. ``$VIA54_OCR_PYTHON`` —— **严格**: 依赖不齐就报错, 不静默改用别的。
       用户写下"用这个解释器"时, 悄悄换一个才是更坏的结局(那会把配错这件事藏起来)。
    2. 部署脚本自己的解释器 → ``$PYTHON`` → python3.11 → python3 → python:
       取第一个依赖**齐备**的。
    3. 都不齐备 → 返回第一个存在的候选, 说明里标注"依赖不齐, 将安装到它" ——
       这样"探测报缺失 → 安装 → 复验"能形成闭环(否则会卡在"没一个合格所以不知道装哪")。
    """
    override = (os.environ.get(OCR_PYTHON_ENV) or "").strip()
    if override:
        missing = _python_missing_modules(override, OCR_REQUIRED_MODULES)
        if missing is None:
            return None, "$%s 指向的解释器无法启动: %s" % (OCR_PYTHON_ENV, override)
        if missing:
            return None, ("$%s 指定的解释器 %s 缺 %s —— 显式指定会被尊重, 不静默改用别的; "
                          "请在其中执行 `%s -m pip install %s`, 或改掉该设置"
                          % (OCR_PYTHON_ENV, override, ", ".join(missing),
                             override, " ".join(_OCR_PKGS)))
        return override, "$%s" % OCR_PYTHON_ENV

    cands = []
    if sys.executable:
        cands.append((sys.executable, "部署脚本自己的解释器"))
    if (os.environ.get("PYTHON") or "").strip():
        cands.append((os.environ["PYTHON"].strip(), "$PYTHON"))
    for name in OCR_PYTHON_CANDIDATES:
        p = _which(name)
        if p:
            cands.append((p, "PATH:%s" % name))

    seen, uniq = set(), []
    for exe, why in cands:
        if exe not in seen:
            seen.add(exe)
            uniq.append((exe, why))

    first_any = None
    for exe, why in uniq:
        missing = _python_missing_modules(exe, OCR_REQUIRED_MODULES)
        if missing is None:
            continue
        if first_any is None:
            first_any = (exe, why)
        if not missing:
            return exe, why
    if first_any:
        return first_any[0], "%s (依赖不齐, 将安装到它)" % first_any[1]
    return None, "找不到任何 Python 解释器"


def ocr_script_path():
    """定出 OCR 脚本路径。返回 ``(path, 依据)`` 或 ``(None, 报错文案)``。

    锚点是**仓库根**(由本文件位置推出), 不是当前工作目录 —— 旧实现只在"恰好 cd 到
    仓库根"时才找得到脚本: 站在 /tmp 里跑 ``medit anno2ppt ocr`` 会去找
    ``/tmp/scripts/paddleocr_pdf_page.py``。候选与 Go 侧 ``OCRScriptCandidates`` 对齐。
    """
    rel = "paddleocr_pdf_page.py"
    override = (os.environ.get(OCR_SCRIPT_ENV) or "").strip()
    if override:
        if os.path.isfile(override):
            return override, "$%s" % OCR_SCRIPT_ENV
        return None, "$%s 指向的脚本不存在: %s" % (OCR_SCRIPT_ENV, override)

    cands = [
        (os.path.join(REPO, "scripts", rel), "仓库 scripts/"),
        (os.path.join(REPO, "skills", "via54medit-anno2ppt-phase7", "scripts", rel),
         "仓库技能包"),
        (os.path.expanduser("~/.hermes/skills/via54medit-anno2ppt-phase7/scripts/" + rel),
         "旧技能布局"),
        (os.path.join(REPO, "skills", "via54medit", "via54medit-anno2ppt-phase7",
                      "scripts", rel), "旧技能布局(带 via54medit 前缀)"),
        (os.path.join("scripts", rel), "当前工作目录(开发态兜底)"),
    ]
    for path, why in cands:
        if os.path.isfile(path):
            return path, why
    return None, ("找不到 %s; 已尝试: %s; 可用 $%s 显式指定"
                  % (rel, " | ".join(p for p, _ in cands), OCR_SCRIPT_ENV))


def _probe_ocr():
    """OCR 就绪 = **真正会跑 OCR 的那个解释器**里有 paddleocr + paddle + pymupdf。
    这里的关键不是"能不能 import", 而是"**用哪个解释器**判"。

    实测故障 (2026-09-12): 本机 ``~/.local/bin/python3.11`` 有 pymupdf 却没有
    paddleocr, 而它在 Go 侧 ``ResolvePython`` 的候选链里排第一 —— 于是
    ``medit anno2ppt ocr`` 直接 ModuleNotFoundError; 而本探测器当时用的是
    ``sys.executable``(仓库那个装了 paddle 的 3.10), 照样报"✓ 已就绪"。
    报告与命令各说各话, 这就是"假就绪"。

    所以现在先按**同一套规则**定出 OCR 解释器 (``ocr_python()``), 再判它。
    判定用 ``find_spec``(查文件在不在, 0.00s) 而不是真 import —— 本探测器会被管线
    第 [0] 步反复调用, 而真 import paddle 是秒级开销。"装了但坏掉/认不出字"交给
    ``ocr_smoke_test()`` 真跑一次去发现。
    """
    exe, why = ocr_python()
    if not exe:
        return False, why
    missing = _python_missing_modules(exe, OCR_REQUIRED_MODULES)
    if missing is None:
        return False, "无法用 %s 探测依赖(解释器启动失败)" % exe
    if missing:
        return False, ("%s 缺 %s —— 注意这是**运行 OCR 的那个**解释器, "
                       "不是部署脚本自己的; 补法: %s -m pip install %s"
                       % (exe, ", ".join(missing), exe, " ".join(_OCR_PKGS)))
    return True, "%s (%s) 三个依赖齐备" % (os.path.basename(exe), why)


#: OCR 权重缓存目录。PaddleOCR 3.x 的 PaddleX 后端把官方模型放在这里 ——
#: **不是** ``~/.paddleocr``(那是 2.x 时代的路径, 实测在 3.x 上是空的, 照它判断会误报)。
#:
#: 根目录认 ``PADDLE_PDX_CACHE_HOME``: 这是 PaddleX 自己读的变量(实测于
#: ``paddlex/utils/cache.py``: ``CACHE_DIR = os.environ.get("PADDLE_PDX_CACHE_HOME", ~/.paddlex)``)。
#: 用别的名字当覆盖(如 PADDLE_PDX_MODELS_HOME)是无效的 —— 探针会看一个 PaddleX
#: 根本不写的位置, 于是永远报"权重缺失"。
OCR_MODELS_DIR = os.path.join(
    os.path.expanduser(os.environ.get("PADDLE_PDX_CACHE_HOME") or "~/.paddlex"),
    "official_models")

#: 一次真实识别至少要用到的模型家族: det 出检测框, rec 认字。
#: 其余(文本行方向/文档方向/UVDoc)由 PaddleOCR 按参数自行决定, 不在这里要求。
_OCR_MODEL_NEEDLES = ("det", "rec")

def _ocr_cached_model_families():
    """本地已缓存的 OCR 模型家族名(无则空集)。"""
    try:
        return {n for n in os.listdir(OCR_MODELS_DIR)
                if os.path.isdir(os.path.join(OCR_MODELS_DIR, n))}
    except OSError:
        return set()


def _probe_ocr_models():
    """权重是否已落地 —— 便宜的文件系统检查。

    它回答的是"**首次真实调用要不要联网**"这件事: 包装好了但权重没下, 业务路径上
    第一次 OCR 会突然去下载 ~170MB; 在受限网络或离线机器上就是直接失败 ——
    而那时离"部署完成"已经很久了, 没人会把两件事联系起来。

    真正"能不能识别"由 ``ocr_smoke_test()`` 回答; 这里刻意不加载模型(那是秒级开销,
    而本函数会被管线第 [0] 步反复调用)。
    """
    fams = _ocr_cached_model_families()
    if not fams:
        return False, "未发现本地权重 (%s 不存在或为空)" % OCR_MODELS_DIR
    missing = [n for n in _OCR_MODEL_NEEDLES if not any(n in f for f in fams)]
    if missing:
        return False, "权重不全: 缺 %s (已有: %s)" % (
            "/".join("%s 家族" % m for m in missing), ", ".join(sorted(fams)))
    return True, "%d 个模型家族已缓存 (%s)" % (len(fams), ", ".join(sorted(fams)))


def ocr_smoke_test(timeout=300):
    """**真跑一次识别** —— "能 import" 不等于 "能识别"。

    跑的是 ``[ocr_python(), ocr_script_path(), "--smoke"]``: **真正的解释器** + **真正的
    脚本** + 真正的推理。这样一次就把四件事一起验了 —— 解释器选得对不对、脚本找得到
    找不到、API 形状有没有变、权重在不在。自检若与业务不同源, 它验过的就不是会跑的那条路。

    为什么必须是"真跑": 下面三种情况在 import 阶段都看不出来, 只有跑一次才暴露 ——
    权重没下(首次调用突然要联网下 ~170MB, 受限网络直接失败)、ABI 不匹配(能加载却认不出字)、
    以及上面那个解释器错配。同时它也是部署时把权重**预热**下来的动作。

    断言(在脚本里)只要求"识别到非空文本", 不比对具体字符串 —— OCR 把 O 认成 D 是正常的
    (实测 "OCR 12345" → "DCR 12345", 置信度 0.996)。样本文字可用 ``VIA54_OCR_SMOKE_TEXT`` 覆盖。

    返回 ``(ok, detail)``, **不抛异常**。
    """
    exe, why = ocr_python()
    if not exe:
        return False, why
    script, swhy = ocr_script_path()
    if not script:
        return False, swhy
    try:
        r = subprocess.run([exe, script, "--smoke"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, ("真识别超时 (%ds) —— 首次运行要下载权重, 网络受限时会很久; "
                       "可先单独预热: python3 scripts/deploy_scan.py --only ocr_models" % timeout)
    except OSError as e:
        return False, "真识别无法启动 (%s): %s" % (exe, e)
    lines = [ln.strip() for ln in ((r.stderr or "") + "\n" + (r.stdout or "")).splitlines()
             if ln.strip()]
    tail = lines[-1] if lines else "(无输出)"
    detail = tail.replace("[L2][smoke] OK: ", "").replace("[L2][smoke] ERROR: ", "")
    if r.returncode == 0:
        return True, "真识别通过 [%s | %s]: %s" % (
            os.path.basename(exe), swhy, detail)
    return False, "真识别失败 [%s | %s]: %s" % (os.path.basename(exe), swhy, detail)


#: mmx-cli 保存凭据的位置。**与 MINIMAX_API_KEY 是两套东西** —— 见 _probe_mmx_auth。
MMX_CONFIG_PATH = os.path.expanduser("~/.mmx/config.json")


def _mmx_bin():
    return _which("mmx") or _which("mmx-cli")


def _probe_mmx_auth():
    """mmx 是否**已认证** —— 判据只认 mmx 自己的状态, 不认 MINIMAX_API_KEY。

    为什么必须改 (v5.4.44 实测): mmx-cli 用的是**它自己**的凭据(``mmx auth login``
    写进 ``~/.mmx/config.json``, 也支持全局 ``--api-key`` 覆盖), 与 ``MINIMAX_API_KEY``
    是两条互不相通的路径。旧探测把结论建在 ``MINIMAX_API_KEY`` 上, 于是本机同时出现
    了方向相反的两个错误:

    * **假警报**: 本机 ``MINIMAX_API_KEY`` 未设置, 而 ``mmx auth status`` 早就就绪且
      真能调通(后台用量都能读到), 报告却写"缺 MINIMAX_API_KEY, 调用会失败";
    * **假就绪(更危险)**: 有人 export 了 ``MINIMAX_API_KEY`` 但没跑过 ``mmx auth login``,
      报告会写"已配置" —— 而 mmx 实际调用会 401。

    判据: 先看 ``~/.mmx/config.json`` 里的 api_key(快、不联网、api-key 模式下的权威),
    再看 ``mmx auth status --output json``(覆盖 OAuth 模式; 实测 0.09s)。
    """
    if not _mmx_bin():
        return False, "未安装 mmx-cli —— 认证无从谈起"
    try:
        with open(MMX_CONFIG_PATH, encoding="utf-8") as fh:
            cfg = json.load(fh)
        if isinstance(cfg, dict) and str(cfg.get("api_key") or "").strip():
            return True, "已认证 (api-key, 来源 %s)" % MMX_CONFIG_PATH
    except (OSError, ValueError):
        pass
    path = _mmx_bin()
    ok, out = _run([path, "--output", "json", "auth", "status"], timeout=60)
    if ok and out:
        try:
            data = json.loads(out[out.index("{"):])
        except (ValueError, IndexError):
            data = {}
        if isinstance(data, dict) and (data.get("key") or data.get("method")):
            return True, "已认证 (%s, 来源 %s)" % (
                data.get("method", "?"), data.get("source", "?"))
    return False, "未认证 —— `mmx auth login --api-key <key>` 或 `mmx auth login` (OAuth)"


def mmx_auth_login(api_key=None):
    """用凭据把 mmx 登录上。返回 ``(ok, detail)``。

    唯一的自动通道是环境里的 ``MINIMAX_API_KEY``: mmx 的凭据必须**由人提供**,
    部署脚本不能凭空造一个。没有 key 时如实返回失败并给出人工步骤, 而不是假装完成。
    """
    path = _mmx_bin()
    if not path:
        return False, "未安装 mmx-cli"
    key = (api_key or os.environ.get("MINIMAX_API_KEY") or "").strip()
    if not key:
        return False, ("没有可用凭据: 设置 MINIMAX_API_KEY 后重跑, 或交互式执行 "
                       "`mmx auth login`(OAuth)")
    cmd = [path, "auth", "login", "--api-key", key]
    ok, out = _run(cmd, timeout=120)
    _note_channel("env", "mmx auth login --api-key ***")
    if not ok:
        return False, "mmx auth login 失败: %s" % ((out or "").strip()[:200] or "无输出")
    return True, "已用 MINIMAX_API_KEY 完成 mmx 登录"


def _probe_browser():
    """Chrome/Edge/Chromium —— 逐路径确认**文件真的在**(与 hermes 的多路兜底同构)。"""
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


#: OCR 的 pip 包与**版本约束**。
#:
#: 为什么要约束: 管线调的是 PaddleOCR 3.x 的 API(见 ``ocr_smoke_test``), 不约束就会有
#: 一天静默装上 2.x/4.x —— 而"装上"与"能跑"是两件事, 后者只会在 L2 那一步才炸。
#: 上界与下界都给: 4.x 尚未验证, 2.x 的 API 形状不同。
_OCR_PKGS = ["paddleocr>=3.0,<4", "paddlepaddle>=3.0,<4"]

#: 平台 -> 系统工具包名。集中一处, 免得每个能力各写一份、慢慢走样。
_NODE_PKGS = {"brew": "node", "apt-get": "nodejs", "dnf": "nodejs", "yum": "nodejs",
              "pacman": "nodejs", "winget": "OpenJS.NodeJS.LTS", "choco": "nodejs",
              "scoop": "nodejs"}
_GIT_PKGS = {"brew": "git", "apt-get": "git", "dnf": "git", "yum": "git",
             "pacman": "git", "winget": "Git.Git", "choco": "git", "scoop": "git"}
_GO_PKGS = {"brew": "go", "apt-get": "golang", "dnf": "golang", "yum": "golang",
            "pacman": "go", "winget": "GoLang.Go", "choco": "golang", "scoop": "go"}
_POPPLER_PKGS = {"brew": "poppler", "apt-get": "poppler-utils", "dnf": "poppler-utils",
                 "yum": "poppler-utils", "pacman": "poppler",
                 "winget": "oschwartz10612.Poppler", "choco": "poppler", "scoop": "poppler"}


def _system_plan(names_by_manager):
    def _p():
        cmd, _mgr, needs_admin = system_cmd(names_by_manager, sudo=not sys.platform.startswith("win"))
        if cmd is None:
            return "无可用包管理器 —— 手动安装: %s" % " / ".join(sorted(set(names_by_manager.values())))
        return " ".join(cmd) + ("" if needs_admin else "   (无需管理员)")
    return _p


def build_matrix(include_heavy=True):
    """构造能力矩阵。``include_heavy=False`` 时不纳入重依赖(OCR)。"""
    caps = [
        Cap("python", "Python >= 3.10", ALL, "env", required=True,
            probe=lambda: (sys.version_info >= (3, 10), sys.version.split()[0]),
            hint="装 Python 3.10+ 并重跑; 或用 $PYTHON 指向合格解释器",
            why="全部 Python 侧工具链的运行前提", gate=True,
            plan="用系统包管理器安装 Python 3.10+ (或 uv python install 3.12)"),
        Cap("pymupdf", "PyMuPDF (PDF/高亮)", ALL, "python", required=True,
            probe=lambda: _import_probe("pymupdf"),
            install=lambda: pip_install("pymupdf"),
            plan=lambda: " ".join(pip_cmd("pymupdf")),
            hint="pip install pymupdf", why="PDF 解析与高亮落位"),
        Cap("python_pptx", "python-pptx (PPT 结构)", ALL, "python", required=True,
            probe=lambda: _import_probe("pptx"),
            install=lambda: pip_install("python-pptx"),
            plan=lambda: " ".join(pip_cmd("python-pptx")),
            hint="pip install python-pptx", why="PPT 文本/结构提取"),
        Cap("pillow", "Pillow (图像)", ALL, "python", required=True,
            probe=lambda: _import_probe("PIL"),
            install=lambda: pip_install("Pillow"),
            plan=lambda: " ".join(pip_cmd("Pillow")),
            hint="pip install Pillow", why="图片读写与裁剪"),
    ]
    if include_heavy:
        caps.append(Cap(
            "ocr", "PaddleOCR (L2 中文 OCR)", ALL, "python", required=True, heavy=True,
            probe=_probe_ocr,
            # 版本**必须带约束**: 管线用的是 PaddleOCR 3.x 的 API
            # (`PaddleOCR(use_textline_orientation=True, lang='ch').predict()` →
            #  `result[0]['rec_texts']`)。不约束就会在某天静默装上 4.x/2.x,
            # 而"装上了"和"能跑"是两件事。本机实测可用组合: paddleocr 3.7.0 + paddle 3.3.1。
            install=lambda: pip_install(_OCR_PKGS, python=ocr_python()[0]),
            plan=lambda: " ".join(pip_cmd(_OCR_PKGS, ocr_python()[0])) + "   (数百 MB)",
            hint="pip install %s  (数百 MB; 加 --skip-heavy 可跳过)" % " ".join(_OCR_PKGS),
            why="L2 中文/图片识别腿, 由 `medit anno2ppt ocr` 调用 "
                "scripts/paddleocr_pdf_page.py; 缺它则纯图片页无法识别。"
                "**装进哪个解释器**按 ocr_python() 定(不是部署脚本自己那个)"))
        caps.append(Cap(
            "ocr_models", "PaddleOCR 权重 (真识别预热)", ALL, "python",
            required=True, heavy=True,
            probe=_probe_ocr_models,
            install=ocr_smoke_test,
            plan="跑一次真识别, 把 det/rec 权重下到 %s (~170MB)" % OCR_MODELS_DIR,
            hint="权重缺失时首次 OCR 会在业务路径上突然联网下载; "
                 "受限网络下直接失败。补齐: python3 scripts/deploy_scan.py --only ocr_models",
            why="包装好了但权重没下 = 首次真实调用要联网; 离线/受限网络下必然失败, "
                "而且失败点离「部署完成」很远, 没人会把两件事联系起来"))
    caps += [
        Cap("pywin32", "pywin32 (Office COM)", (WINDOWS,), "python", required=True,
            probe=lambda: _import_probe("win32com"),
            install=lambda: pip_install("pywin32"),
            plan=lambda: " ".join(pip_cmd("pywin32")),
            hint="pip install pywin32",
            why="Windows 上 PowerPoint/Word 的 COM 通道 —— **只在 Windows 需要**; "
                "macOS 走原生 AppleScript、Linux 无此通道, 故不在那两个平台安装"),
        Cap("git", "Git (拉取更新/自动同步)", ALL, "system", required=True,
            probe=lambda: _probe_tool("git", "--version"),
            install=lambda: system_install(_GIT_PKGS),
            plan=_system_plan(_GIT_PKGS),
            hint="macOS: 装 Xcode Command Line Tools (`xcode-select --install`) 或 brew install git; "
                 "Linux: apt/dnf install git; Windows: winget install Git.Git",
            why="auto_sync / 版本更新靠 git pull —— 这正是「更新版本后自动补齐」自身的运行前提"),
        Cap("node", "Node.js (含 npm)", ALL, "system", required=False,
            probe=lambda: _probe_tool(["node"]),
            install=lambda: system_install(_NODE_PKGS),
            plan=_system_plan(_NODE_PKGS),
            hint="安装 Node.js (mmx-cli 是 npm 包, 需要它)",
            why="mmx-cli 视觉引擎的运行前提"),
        Cap("mmx_cli", "mmx-cli (默认视觉引擎)", ALL, "npm", required=True,
            probe=_probe_mmx, install=lambda: npm_install("mmx-cli"),
            plan=lambda: " ".join(npm_cmd("mmx-cli")) + "   (失败会自动退回私有前缀 %s)" % NODE_PREFIX,
            hint="npm install -g mmx-cli  (注意: **不是** pip install —— PyPI 上没有这个包)",
            why="VISION_PROVIDER=mmx 的默认实现; 缺它则 L3 视觉校验不可用"),
        Cap("mmx_auth", "mmx 凭据 (已认证)", ALL, "env", required=False, gate=False,
            probe=_probe_mmx_auth,
            # 有 MINIMAX_API_KEY 时可自动登录; 没有就只能人工(脚本不能凭空造凭据)。
            install=mmx_auth_login,
            plan="mmx auth login --api-key $MINIMAX_API_KEY  (没有该环境变量时需人工)",
            hint="`mmx auth login`(OAuth) 或 `mmx auth login --api-key <key>`; "
                 "或先 export MINIMAX_API_KEY 再重跑本脚本由部署流程代登",
            why="mmx 用的是**它自己的**凭据(~/.mmx/config.json), 与 MINIMAX_API_KEY 是两套; "
                "未认证时视觉调用会 401 —— 而这在「二进制已安装」的报告里看不出来"),
        Cap("powerpoint", "桌面版 PowerPoint (PPT 版式渲染)",
            (WINDOWS, MACOS), "office", gate=False,
            probe=_probe_office("powerpoint"),
            hint="装桌面版 Microsoft PowerPoint 并激活。装不了就用显式 RENDER_ENGINE=graph。",
            why="PPT 版式只能由微软引擎产出(见 docs/ppt-render-fidelity.md); "
                "Linux 没有桌面 Office, 故本平台标记为不适用",
            # 唯一真正需要线程上界的探测: 见 _probe_with_timeout 的说明。
            probe_timeout=25),
        Cap("word", "桌面版 Word (Word 版式渲染)",
            (WINDOWS, MACOS), "office", gate=False,
            probe=_probe_office("word"),
            hint="装桌面版 Microsoft Word 并激活; 或先用 Word 另存为 PDF 再传入。",
            why="Word 版式同样只认微软引擎; 仅当源文件是 DOC/DOCX 时才需要",
            probe_timeout=25),
        Cap("poppler", "poppler (pdftoppm/pdftotext)", ALL, "system", required=False,
            probe=lambda: _probe_tool(["pdftoppm", "pdftotext"], version_flag="-v"),
            install=lambda: system_install(_POPPLER_PKGS),
            plan=_system_plan(_POPPLER_PKGS),
            hint="brew install poppler / apt install poppler-utils",
            why="RENDER_RASTERIZER=pdftoppm 时需要; 默认栅格化走 pip 的 pymupdf, 故非必需"),
        Cap("browser", "Chrome/Edge/Chromium (CDP)", ALL, "system", required=False,
            probe=_probe_browser,
            install=None,
            plan="装 Chrome/Edge/Chromium, 或用 $CHROME_PATH 指定",
            hint="装 Chrome/Edge/Chromium, 或用 $CHROME_PATH 指定; 之后 `medit browser start`",
            why="部分检索/抓取步骤走 CDP 调试实例"),
        Cap("go", "Go 工具链", ALL, "system", required=False,
            probe=lambda: _probe_tool("go", "version"),
            install=lambda: system_install(_GO_PKGS),
            plan=_system_plan(_GO_PKGS),
            hint="装 Go 1.21+  (若用预编译 bin/medit 则不需要)",
            why="从源码构建 bin/medit 与 bin/medit-mcp"),
        Cap("lark_cli", "lark-cli (飞书)", ALL, "system", required=False,
            probe=lambda: (bool(_which("lark-cli") or os.environ.get("LARK_CLI")),
                           _which("lark-cli") or os.environ.get("LARK_CLI") or "未配置"),
            install=None,
            plan="设置 $LARK_CLI 指向可执行文件",
            hint="设置 $LARK_CLI 指向可执行文件",
            why="飞书文档/表格/告警通道"),
    ]
    return caps


def capability_keys(include_heavy=True):
    return [c.key for c in build_matrix(include_heavy=include_heavy)]


# --------------------------------------------------------------------------- #
# 平台兼容性扫描 (POSIX 专属假设 = Windows 上的真故障)
# --------------------------------------------------------------------------- #
#: 这些写法在 Windows 上会指向不存在的位置, 属于**平台相关代码**。
_POSIX_PATTERNS = (
    ('"/tmp/', "硬编码 POSIX 临时目录 /tmp (Windows 上是 C:\\tmp, 通常不存在)"),
    ("'/tmp/", "硬编码 POSIX 临时目录 /tmp (Windows 上是 C:\\tmp, 通常不存在)"),
)
_FOREIGN_PATH = ("G:\\", "C:\\Users\\via54")


# --------------------------------------------------------------------------- #
# 平台兼容性扫描 (POSIX 专属假设 = Windows 上的真故障)
# --------------------------------------------------------------------------- #
#: 这些写法在 Windows 上会指向不存在的位置, 属于**平台相关代码**。
_POSIX_PATTERNS = (
    ('"/tmp/', "硬编码 POSIX 临时目录 /tmp (Windows 上是 C:\\tmp, 通常不存在)"),
    ("'/tmp/", "硬编码 POSIX 临时目录 /tmp (Windows 上是 C:\\tmp, 通常不存在)"),
)
_FOREIGN_PATH = ("G:\\", "C:\\Users\\via54")

# macOS 专属硬编码 (v5.4.46)
# -------------------------
# 这一类与 POSIX / 外机路径是**不同**的问题, 所以单列:
#   * `/tmp` 是"POSIX 假设" —— Windows 上位置不对;
#   * `/Users/<某个真实账号>/…` 是"**机器专属**" —— 换用户/换机器就不存在, 而
#     它在 macOS 上看起来完全正常, 所以最容易一路留到别人机器上才炸;
#   * `/Applications`、`/System`、`/Library` 是"**macOS 专属布局**" —— Linux 上不存在;
#   * `osascript`/`sips`/`pbcopy` 等是"**macOS 专属命令**" —— 别的平台没有这些可执行文件。
_MACOS_USER_PATH = re.compile(r"""(['"])/Users/([^/'"\\ ]+)/""")
#: 合成占位符不报 —— 它们本来就不是某个真实账号(测试里用来构造绝对路径)。
_MACOS_USER_ALLOWLIST = {"x", "example", "user", "testuser", "someone", "you"}

_MACOS_ONLY_PREFIXES = (
    ('"/Applications/', "macOS 专属绝对路径 /Applications (其它平台不存在)"),
    ("'/Applications/", "macOS 专属绝对路径 /Applications (其它平台不存在)"),
    ('"/System/', "macOS 专属绝对路径 /System (其它平台不存在)"),
    ("'/System/", "macOS 专属绝对路径 /System (其它平台不存在)"),
    ('"/Library/', "macOS 专属绝对路径 /Library (其它平台不存在)"),
    ("'/Library/", "macOS 专属绝对路径 /Library (其它平台不存在)"),
    ("/opt/homebrew/", "Apple Silicon 专属 Homebrew 前缀 /opt/homebrew"),
)

#: macOS 才有的可执行文件。出现在命令行里而文件内没有平台守卫 = 别的平台必然失败。
#: 只列**明确只有 macOS 才有、且不会与普通字符串混淆**的可执行文件。
#: 刻意不含 ``"open"`` / ``"defaults"`` —— 它们在 JSON 键、状态值里到处都是, 会满屏误报;
#: 而 ``"osascript"``/``"sips"`` 这种名字只可能出现在命令行里。
_MACOS_ONLY_CMDS = ("osascript", "pbcopy", "pbpaste", "sips", "textutil",
                    "sw_vers", "mdls", "qlmanage", "hdiutil", "diskutil")
#: 视为"已做平台守卫"的写法(文件内出现过任一即可)。
_PLATFORM_GUARDS = ("darwin", "sys.platform", "runtime.GOOS", "GOOS",
                    "current_os", "platform.system")

#: "先探测再用"的写法。``/Applications/Google Chrome.app/...`` 这类**候选路径表**本身是对的
#: —— 列它、再逐个 stat/LookPath 选可用的, 就是跨平台的正确做法。所以对"macOS 专属目录"
#: 这一条, 文件里有存在性探测就不再报; 而"macOS 专属命令"不行: 命令找不到就是直接失败,
#: 必须先判平台再调用, 所以它只认 _PLATFORM_GUARDS。
_EXISTENCE_PROBES = ("os.path.exists", "os.path.isfile", "os.path.isdir",
                     "LookPath", "shutil.which", "_which()", "fileExists(")

#: 扫哪些源码。之前只扫 .py 且只扫 scripts/ 与 skills/ —— 于是 Go 侧与 integrations/
#: 的机器专属路径一直不在视野里(实测 internal/cmd/integrations 里就有 12 处)。
_COMPAT_SCAN_EXT = (".py", ".go", ".sh")


def _compat_roots():
    return [HERE, os.path.join(REPO, "skills"),
            os.path.join(REPO, "internal"), os.path.join(REPO, "cmd"),
            os.path.join(REPO, "integrations"), os.path.join(REPO, "telemetry")]


def _is_commented(line, lang):
    s = line.strip()
    if lang == "go":
        return s.startswith("//") or s.startswith("*") or s.startswith("/*")
    return s.startswith("#")


def scan_platform_compat():
    """扫出与当前平台不兼容 / 机器专属的代码点。返回 (findings, scanned_files)。

    规则分工: ``posix_tmp`` / ``foreign_path`` 是老面孔; v5.4.46 补上四类 **macOS 专属硬编码**
    (机器专属账号路径 / macOS 专属目录 / macOS 专属命令 / Apple Silicon 前缀), 并把扫描范围
    从"只有 scripts+skills 的 .py"扩到 .py/.go/.sh + internal/cmd/integrations/telemetry ——
    实测 Go 侧与 integrations/ 里原本就各有机器专属路径, 却一直不在视野里。
    """
    findings = []
    scanned = 0
    for root in _compat_roots():
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in ("__pycache__", ".git")]
            for fn in filenames:
                if not fn.endswith(_COMPAT_SCAN_EXT):
                    continue
                if fn in ("deploy_scan.py", "test_deploy_scan.py"):
                    # 本文件里的这些字面量是**检测规则本身**, 不是在用它们 ——
                    # 否则扫描器会把自己(以及它的测试)报出来。
                    continue
                lang = "go" if fn.endswith(".go") else ("sh" if fn.endswith(".sh") else "py")
                is_test = fn.startswith("test_") or fn.endswith("_test.go") or fn.endswith("_test.py")
                path = os.path.join(dirpath, fn)
                scanned += 1
                try:
                    with open(path, encoding="utf-8", errors="replace") as fh:
                        lines = fh.readlines()
                except OSError:
                    continue
                rel = os.path.relpath(path, REPO)
                whole = "".join(lines)
                guarded = any(g in whole for g in _PLATFORM_GUARDS)
                probed = any(g in whole for g in _EXISTENCE_PROBES)
                for i, line in enumerate(lines, 1):
                    code = line.strip()[:110]
                    commented = _is_commented(line, lang)
                    for pat, desc in _POSIX_PATTERNS:
                        if pat in line and "tempfile" not in line:
                            if not is_test:
                                findings.append({"file": rel, "line": i, "kind": "posix_tmp",
                                                 "detail": desc, "code": code})
                            break
                    for fp in _FOREIGN_PATH:
                        if fp in line:
                            findings.append({"file": rel, "line": i, "kind": "foreign_path",
                                             "detail": "引用了另一台机器的绝对路径: %s" % fp,
                                             "code": code})
                    # --- macOS 专属硬编码 ---
                    if not commented:
                        for m in _MACOS_USER_PATH.finditer(line):
                            if m.group(2) in _MACOS_USER_ALLOWLIST:
                                continue
                            findings.append({
                                "file": rel, "line": i, "kind": "macos_user_path",
                                "detail": "写死了 macOS 账号目录 /Users/%s/ —— 换用户或换机器就"
                                          "不存在。改用 os.path.expanduser(\"~/…\") / $HOME / "
                                          "环境变量派生" % m.group(2),
                                "code": code})
                        for prefix, desc in _MACOS_ONLY_PREFIXES:
                            if prefix in line:
                                if guarded or probed:
                                    break  # 已判平台, 或"先探测再用" —— 属于正确做法
                                findings.append({
                                    "file": rel, "line": i, "kind": "macos_only_path",
                                    "detail": desc + "; 需平台守卫或改用 PATH/环境变量查找",
                                    "code": code})
                                break
                    if _MACOS_ONLY_CMDS and any(
                            ('"%s"' % c) in line or ("'%s'" % c) in line
                            for c in _MACOS_ONLY_CMDS):
                        if not guarded:
                            hit = next(c for c in _MACOS_ONLY_CMDS
                                       if ('"%s"' % c) in line or ("'%s'" % c) in line)
                            findings.append({
                                "file": rel, "line": i, "kind": "macos_only_cmd",
                                "detail": "%s 是 macOS 专属命令, 而本文件没有平台守卫 "
                                          "(非 macOS 会直接失败)" % hit,
                                "code": code})
    return findings, scanned


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def _select_caps(only, include_heavy):
    """``only`` 为 None/空 -> 全部; 否则只留指定的键。返回值含 ``unknown``。"""
    caps = build_matrix(include_heavy=include_heavy)
    if not only:
        return caps, []
    wanted = [k.strip() for k in only if k and k.strip()]
    known = {c.key: c for c in caps}
    unknown = [k for k in wanted if k not in known]
    return [known[k] for k in wanted if k in known], unknown


def collect(install=True, include_heavy=True, env=None, dry_run=False, only=None,
            include_caps=True, include_compat=True):
    """执行扫描(可选补齐缺口), 返回 ``(result_dict, osname)``。**不打印**。

    拆出这一层是为了让别的入口(``deps_auto.ensure_env``、``medit doctor``、
    ``bootstrap_device``)复用同一份结论, 而不是各自再实现一遍依赖清单 ——
    那正是本轮要消除的问题(三份清单互不同步)。
    """
    osname = current_os()
    env = env or scan_environment()
    caps, unknown = _select_caps(only, include_heavy) if include_caps else ([], [])

    rows = []
    for cap in caps:
        if not cap.applies(osname):
            rows.append({
                "key": cap.key, "label": cap.label, "kind": cap.kind,
                "status": NA, "detail": "本平台不适用 (%s) — 不安装、不校验" % osname,
                "hint": cap.why, "required": False, "heavy": cap.heavy, "gate": cap.gate,
            })
            continue
        ok, detail = cap.probe()
        if ok:
            rows.append({"key": cap.key, "label": cap.label, "kind": cap.kind,
                         "status": OK, "detail": detail, "hint": cap.hint,
                         "required": cap.required, "heavy": cap.heavy, "gate": cap.gate})
            continue

        heavy_skipped = cap.heavy and not include_heavy
        if dry_run:
            rows.append({"key": cap.key, "label": cap.label, "kind": cap.kind,
                         "status": PLAN if cap.installable() else MISSING,
                         "detail": ("计划: %s" % cap.plan_text()) if cap.installable()
                                   else detail,
                         "hint": cap.hint, "required": cap.required,
                         "heavy": cap.heavy, "gate": cap.gate,
                         "installable": cap.installable()})
            continue

        if install and cap._install is not None and not heavy_skipped:
            fixed, msg = cap.install()
            if fixed:
                # ── 装后复验 (openclaw "lifecycle-pending marker → 必须判失败";
                #    hermes "installer reported success but binary not found → exit 1") ──
                ok2, detail2 = cap.probe()
                if ok2:
                    rows.append({"key": cap.key, "label": cap.label, "kind": cap.kind,
                                 "status": FIXED, "detail": "%s → 复验通过: %s" % (msg, detail2),
                                 "hint": cap.hint, "required": cap.required,
                                 "heavy": cap.heavy, "gate": cap.gate,
                                 "verified": True, "channel": dict(LAST_INSTALL)})
                    continue
                rows.append({"key": cap.key, "label": cap.label, "kind": cap.kind,
                             "status": MISSING,
                             "detail": "安装器报成功, 但**复验仍失败** —— %s" % msg,
                             "hint": cap.hint, "required": cap.required,
                             "heavy": cap.heavy, "gate": cap.gate,
                             "verified": False, "verify_detail": detail2,
                             "channel": dict(LAST_INSTALL)})
                continue
            rows.append({"key": cap.key, "label": cap.label, "kind": cap.kind,
                         "status": MISSING, "detail": "%s | 自动安装失败: %s" % (detail, msg),
                         "hint": cap.hint, "required": cap.required,
                         "heavy": cap.heavy, "gate": cap.gate, "verified": False})
            continue
        rows.append({"key": cap.key, "label": cap.label, "kind": cap.kind,
                     "status": MISSING, "detail": detail, "hint": cap.hint,
                     "required": cap.required, "heavy": cap.heavy, "gate": cap.gate,
                     "installable": cap.installable()})

    blockers = [r for r in rows if r["status"] == MISSING and r["required"] and r["gate"]]
    warnings = [r for r in rows if r["status"] == MISSING and not (r["required"] and r["gate"])]
    #: --dry-run 时"有通道但还没装"不算失败; 真正无解(必需且没有自动通道)才拦。
    unresolvable = [r for r in blockers if not r.get("installable")]
    verify_failed = [r for r in rows if r.get("verified") is False]

    #: hermes 的 ``.install_method``: 记下"这次每个能力实际用了哪条通道", 下次沿用同一条。
    #: 只在**真装成了**的时候记 —— 复验没过的不能记, 否则下次会去沿用一条已知失败的通道。
    stamp_record = {}
    for r in rows:
        ch = r.get("channel")
        if r["status"] == FIXED and ch:
            stamp_record[r["key"]] = ch

    result = {
        "environment": env,
        "capabilities": rows,
        "compat": {"findings": [], "scanned_files": 0, "affected_files": 0},
        "dry_run": dry_run,
        "only": list(only or []),
        "unknown_only": unknown,
        "compat_included": bool(include_compat),
        "summary": {
            "blockers": len(blockers),
            "unresolvable": len(unresolvable),
            "verify_failed": len(verify_failed),
            "warnings": len(warnings),
            "not_applicable": len([r for r in rows if r["status"] == NA]),
            "fixed": len([r for r in rows if r["status"] == FIXED]),
            "planned": len([r for r in rows if r["status"] == PLAN]),
        },
        #: 就绪与否 —— **这里必须给值**, 不能只靠 ``run()`` 补: ``deps_auto.ensure_env``
        #: 直接消费 ``collect()`` 的输出并交给 ``_render``, 少了这个键就是 KeyError。
        #: (v5.4.34~v5.4.35 期间就是这样把管线第 [0] 步打挂的, 因为当时没有测试覆盖
        #: 这条路径。现在有 ``TestEntrypoints.test_deps_auto_ensure_env_runs`` 守着。)
        "ok": not blockers,
    }
    if include_compat:
        compat, scanned = scan_platform_compat()
        result["compat"] = {"findings": compat, "scanned_files": scanned,
                            "affected_files": len({f["file"] for f in compat})}
    if stamp_record and install and not dry_run:
        result["stamp_path"] = write_stamp(stamp_record)
    return result, osname


#: hermes 的 ``--stage`` 阶段划分: 每个阶段只做一件能被单独复跑的事。
STAGES = ("env", "deps", "compat", "all")


def stage_flags(stage):
    """把阶段名翻译成 ``(include_caps, include_compat)``。未知阶段返回 None。"""
    if stage == "env":
        return False, False
    if stage == "deps":
        return True, False
    if stage == "compat":
        return False, True
    if stage in ("all", "", None):
        return True, True
    return None


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


def verify_llm(live=False, ingest=True):
    """**强制**校验"接入了哪些 LLM"以及"它们的 token 消耗真能读进库"。

    为什么这件事必须由部署流程强制跑, 而不是靠人记得手工看: 记账是**旁路** ——
    一条路径不记用量, 调用本身不会报任何错, 报表只是安静地少一块数字。
    实测就抓到过两处: ``scripts/provider_llm.py``(默认文本 provider)把 ``usage``
    返回给调用方却从不写库; Go 侧 ``internal/foundation/llm.go`` 整个丢弃 ``usage``。
    两者都不会让任何测试变红, 只有主动验证才能发现。

    校验内容(全部离线, 不联网、不花钱):
    * 源码级证据 —— 扫仓库里真实的记账调用点(Python ``record_llm_usage`` /
      Go ``recordLLMUsage``), 不信任任何自我声明;
    * 端到端摄入 —— 用各 provider 的真实响应形状跑一遍落库并读回, 含报表层;
    * Go 侧 spool 链路 —— 落盘 → 摄入 → 读回, 并验别名归一与重放幂等。

    ``live=True`` 时才联网探测凭据可达性(部署机上通常没必要, 也慢)。
    返回 ``(ok, problems, payload)``; ``payload=None`` 说明校验器本身不可用。
    """
    root = REPO
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from telemetry import llm_providers
    except Exception as e:                                  # noqa: BLE001
        return False, ["无法导入 telemetry.llm_providers: %s" % e], None
    try:
        res = llm_providers.audit(live=bool(live), ingest=bool(ingest))
    except Exception as e:                                  # noqa: BLE001
        return False, ["LLM 审计执行异常: %s" % e], None
    return (not res.get("problems")), list(res.get("problems") or []), res


def render_llm_verification(payload):
    """用遥测模块里那**同一份**渲染器输出报告 —— 两处口径不会分叉。"""
    if not payload:
        return
    try:
        from telemetry import llm_providers

        print(llm_providers.format_report(payload))
    except Exception as e:                                  # noqa: BLE001
        print("  (LLM 报告渲染失败: %s)" % e)


def run(install=True, include_heavy=True, strict=False, as_json=False, env=None,
        dry_run=False, only=None, stage="all", emit_frame=False,
        llm_live=False, skip_llm=False):
    flags = stage_flags(stage)
    if flags is None:
        print("未知阶段: %r (可选: %s)" % (stage, ", ".join(STAGES)))
        return EXIT_USAGE
    include_caps, include_compat = flags
    if only:
        _caps, unknown = _select_caps(only, include_heavy)
        if unknown:
            print("未知能力: %s" % ", ".join(unknown))
            print("可选能力: %s" % ", ".join(capability_keys(include_heavy)))
            return EXIT_USAGE

    result, _osname = collect(install=install, include_heavy=include_heavy, env=env,
                              dry_run=dry_run, only=only,
                              include_caps=include_caps, include_compat=include_compat)
    result["strict"] = strict          # 供渲染层区分"阻塞"与"提示"
    result["stage"] = stage

    # --- 强制校验: 接入了哪些 LLM + 它们的 token 消耗真能读进库 ---
    # 只在"全量"阶段跑 —— bootstrap 会分三次调 env / deps / compat, 每步都跑一遍
    # 只是重复同样的扫描。要跳过必须显式给 --no-verify-llm(或设环境变量),
    # 也就是说"忘了验证"是不可能的, 只能"主动不验证"。
    llm = {"skipped": True, "ok": True, "problems": [], "detail": None}
    if not skip_llm and stage in ("all", "", None):
        llm_ok, llm_problems, llm_payload = verify_llm(live=llm_live, ingest=not dry_run)
        llm = {"skipped": False, "ok": llm_ok, "problems": llm_problems,
               "detail": llm_payload, "live": bool(llm_live)}
    elif skip_llm:
        llm["why"] = "已按 --no-verify-llm 跳过"
    else:
        llm["why"] = "阶段 %s 不跑(请用 --verify-llm 单独执行)" % stage
    result["llm"] = llm

    s = result["summary"]
    if dry_run:
        # dry-run 的语义是"计划已生成", 不是"环境就绪"; 只有必需且**无任何自动通道**
        # 的缺口才该让它非零退出(那种情况再跑一百次也补不上)。
        ok = not s["unresolvable"]
    else:
        ok = not s["blockers"] and (not strict or not result["compat"]["findings"])
    # LLM 记账链路不通 = 部署没完成: token 统计会安静地少一块, 且不会报任何错。
    if not llm.get("skipped") and not llm.get("ok"):
        ok = False
    result["ok"] = ok
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _render(result)
    if emit_frame:
        # hermes 的 emit_stage_json: 外层部署器只读这一行就知道成败。
        print(json.dumps({"stage": stage, "ok": ok, "blockers": s["blockers"],
                          "planned": s["planned"], "fixed": s["fixed"],
                          "verify_failed": s["verify_failed"]}, ensure_ascii=False))
    return EXIT_OK if ok else EXIT_GAP


_MARK = {OK: "✓", FIXED: "＋", MISSING: "✗", NA: "·", INFO: "i", PLAN: "→"}


def _render(res):
    e = res["environment"]
    print("== 1. 环境深度扫描 ==")
    print("  OS        : %s (%s/%s)   容器: %s" % (e["os"], e["platform"], e["arch"],
                                                 "是" if e["in_container"] else "否"))
    print("  解释器    : %s  (Python %s)" % (e["python_exe"], e["python"]))
    print("  包管理器  : %s" % (", ".join(e["package_managers"]) or "无"))
    print("  工具链    : node=%s npm=%s go=%s" % (e["node"] or "无", e["npm"] or "无", e["go"] or "无"))
    print("  托管前缀  : %s  %s" % (e["via54_home"], "(可写)" if e.get("writable_home") else "(不可写)"))
    print("  输出编码  : %s   交互终端: %s" % (e["encoding"] or "未知",
                                              "是" if e.get("interactive") else "否"))
    if res.get("dry_run"):
        print("  ⚠️ --dry-run: 本次**不会**改动任何东西, 下面只是计划")
    print()
    caps = res["capabilities"]
    if caps:
        print("== 2. 能力矩阵 (按平台过滤) ==")
        for r in caps:
            mark = _MARK.get(r["status"], "?")
            print("  %s %-34s %s" % (mark, r["label"], r["detail"]))
            if r["status"] in (MISSING, PLAN) and r["hint"]:
                print("        → 处理: %s" % r["hint"])
            if r.get("verified") is False:
                print("        → 复验详情: %s" % r.get("verify_detail", "无"))
        print()
    if res.get("compat_included"):
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
        print()
    # 第 4 节: LLM 接入与 token 用量读取能力 —— 部署/更新后**强制**核验。
    llm = res.get("llm") or {}
    if not llm.get("skipped"):
        print("== 4. LLM 接入与 Token 用量读取能力 (强制校验) ==")
        render_llm_verification(llm.get("detail"))
        if not llm.get("ok"):
            print("  ✗ 校验未通过: token 统计会少一块, 且调用本身不会报错 —— 必须修。")
            for p in llm.get("problems") or []:
                print("      • %s" % p)
        print()
    elif llm.get("why"):
        print("== 4. LLM 接入校验: 已跳过 (%s) ==" % llm["why"])
        print()
    s = res["summary"]
    if res.get("dry_run"):
        print("== 结果: 计划已生成 (待补 %d · 必需缺口 %d · 不适用 %d) =="
              % (s["planned"], s["blockers"], s["not_applicable"]))
        if s["unresolvable"]:
            print("   其中 %d 项必需能力**没有任何自动通道**, 得人工装 —— 见上面的 '→ 处理:'" % s["unresolvable"])
        print("   去掉 --dry-run(或设 VIA54_DRY_RUN=0)即可真正执行。")
        return
    print("== 结果: %s (必需缺口 %d · 提示 %d · 不适用 %d · 本次补齐 %d · 复验未过 %d) =="
          % ("就绪" if res.get("ok") else "未就绪", s["blockers"], s["warnings"],
             s["not_applicable"], s["fixed"], s["verify_failed"]))


_USAGE = """用法: deploy_scan.py [选项]

  --check           只扫描, 不安装
  --dry-run         只打印将要执行的动作, 不做任何修改
  --only KEY[,KEY]  只处理指定能力 (见 --list)
  --list            列出所有能力键后退出
  --json            输出机器可读 JSON
  --skip-heavy      跳过重依赖(OCR/Paddle, 数百 MB)
  --strict          平台兼容性问题也计入失败
  --stage S         只跑一个阶段: env | deps | compat | all
  --verify-platform CI 用: 只校验"平台分类是否与宿主一致"
  --verify-llm      只校验"接入了哪些 LLM + token 消耗能不能读到"(部署/更新后强制跑)
  --verify-ocr      只校验"PaddleOCR 真能识别"(真跑一次识别, 顺带预热权重)
  --verify-mmx      只校验"mmx-cli 可用 + 已认证"(两件事分开报)
  --llm-live        配合 --verify-llm: 联网探测凭据可达性与 mmx 账户级用量
  --no-verify-llm   跳过 LLM 接入校验(仅用于确实无法验证的环境)
  --help            显示本帮助

环境变量: VIA54_DRY_RUN / VIA54_ONLY / VIA54_SKIP_HEAVY / VIA54_STRICT /
          VIA54_JSON / VIA54_STAGE / VIA54_HOME / VIA54_ALLOW_BREAK_SYSTEM /
          VIA54_LLM_LIVE / VIA54_SKIP_LLM_VERIFY / VIA54_OCR_SMOKE_TEXT
退出码: 0=就绪  1=仍有必需缺口  2=用法错误"""


def main(argv):
    if "--help" in argv or "-h" in argv:
        print(_USAGE)
        return EXIT_OK

    include_heavy = "--skip-heavy" not in argv and not _env_flag("VIA54_SKIP_HEAVY")
    stage = "all"
    for i, a in enumerate(argv):
        if a == "--stage" and i + 1 < len(argv):
            stage = argv[i + 1]
        elif a.startswith("--stage="):
            stage = a.split("=", 1)[1]
    if stage == "all" and os.environ.get("VIA54_STAGE"):
        stage = os.environ["VIA54_STAGE"]

    # 环境变量给默认值, 命令行开关优先 (openclaw 把所有开关都镜像成环境变量)。
    dry_run = "--dry-run" in argv or _env_flag("VIA54_DRY_RUN")
    as_json = "--json" in argv or _env_flag("VIA54_JSON")
    strict = "--strict" in argv or _env_flag("VIA54_STRICT")
    install = "--check" not in argv
    if dry_run:
        install = False          # dry-run 绝不落地

    only = None
    for i, a in enumerate(argv):
        if a == "--only" and i + 1 < len(argv):
            only = argv[i + 1].split(",")
        elif a.startswith("--only="):
            only = a.split("=", 1)[1].split(",")
    if only is None and os.environ.get("VIA54_ONLY"):
        only = os.environ["VIA54_ONLY"].split(",")

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                   # noqa: BLE001
        pass

    if "--list" in argv:
        for c in build_matrix(include_heavy=include_heavy):
            print("%-12s %-34s %s%s" % (c.key, c.label, ",".join(c.platforms),
                                        "  [必需]" if c.required else ""))
        return EXIT_OK

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
            return EXIT_OK
        for p in problems:
            print("  ✗ %s" % p)
        return EXIT_GAP

    if "--verify-llm" in argv:
        # 独立模式: 部署器与更新脚本**强制**调用的那一步。只读(除摄入 spool 外),
        # 且失败必须非零退出 —— 否则"验证过了"就成了空话。
        live = "--llm-live" in argv or _env_flag("VIA54_LLM_LIVE")
        ok, problems, payload = verify_llm(live=live, ingest=not dry_run)
        if as_json:
            print(json.dumps({"ok": ok, "problems": problems, "detail": payload},
                             ensure_ascii=False, indent=2))
        else:
            render_llm_verification(payload)
            if ok:
                print("LLM 接入校验 OK: 接入了 %d 个 provider, 全部可读 token 用量"
                      % len((payload or {}).get("providers") or []))
            else:
                print("LLM 接入校验未通过 (%d 项):" % len(problems))
                for p in problems:
                    print("  ✗ %s" % p)
        return EXIT_OK if ok else EXIT_GAP

    if "--verify-ocr" in argv:
        # 部署后 / 真机复检用: 真跑一次识别。这是"OCR 到底能不能用"的**唯一强证据**,
        # 也正是把 det/rec 权重预热下来的动作(见 ocr_smoke_test)。
        ok, detail = ocr_smoke_test()
        print("OCR 真识别自检 %s: %s" % ("OK" if ok else "失败", detail))
        return EXIT_OK if ok else EXIT_GAP

    if "--verify-mmx" in argv:
        # mmx 由**两件独立的事**组成, 分开报 —— 因为修法完全不同:
        #   二进制不可用 -> 重装(npm); 未认证 -> 提供凭据(人工, 脚本造不出来)。
        bin_ok, bin_detail = _probe_mmx()
        auth_ok, auth_detail = _probe_mmx_auth()
        print("mmx-cli : %s %s" % ("✓" if bin_ok else "✗", bin_detail))
        print("凭据    : %s %s" % ("✓" if auth_ok else "✗", auth_detail))
        if not auth_ok:
            print("  补法  : export MINIMAX_API_KEY=... 后重跑 "
                  "`python3 scripts/deploy_scan.py --only mmx_auth`")
            print("          或交互式 `mmx auth login`(OAuth)")
        # 退出码只跟二进制走: 凭据必须由人提供, 把它算成"部署失败"会让部署永远无法成功
        # (这与能力矩阵里 mmx_auth 的 gate=False 是同一条判断)。
        return EXIT_OK if bin_ok else EXIT_GAP

    return run(install=install, include_heavy=include_heavy, strict=strict,
               as_json=as_json, dry_run=dry_run, only=only, stage=stage,
               llm_live=("--llm-live" in argv or bool(_env_flag("VIA54_LLM_LIVE"))),
               skip_llm=("--no-verify-llm" in argv or bool(_env_flag("VIA54_SKIP_LLM_VERIFY"))))

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
