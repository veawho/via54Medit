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
                           timeout=timeout, env=env, cwd=REPO)
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
def pip_cmd(packages):
    if isinstance(packages, str):
        packages = [packages]
    return [sys.executable, "-m", "pip", "install"] + list(packages)


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


def pip_install(packages):
    """Python 包 —— 只走当前解释器的 pip。

    撞上 PEP 668 时**默认不越过**这道边界(本项目 v5.4.3 的既定决定: 是否突破由
    解释器管理方(uv/系统/Homebrew)划下的边界, 不该由部署脚本代用户决定)。
    这与 openclaw "探测不通过就停在改包之前" 是同一种克制。
    """
    pkgs = [packages] if isinstance(packages, str) else list(packages)
    cmd = pip_cmd(pkgs)
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
    path = _which("mmx") or _which("mmx-cli")
    if not path:
        return False, "未安装 (npm 包 mmx-cli)"
    ok, out = _run([path, "--version"], timeout=60)
    ver = out.splitlines()[0].strip() if ok and out else "版本未知"
    if not ok:
        return False, "%s 存在但执行失败(不该发生): %s" % (path, ver)
    if not os.environ.get("MINIMAX_API_KEY"):
        return True, "%s (缺 MINIMAX_API_KEY, 调用会失败)" % ver
    return True, ver


def _probe_ocr():
    """OCR 腿要 **两个包都能导入** 才算就绪。

    这里刻意不加线程上界 —— paddle 首次导入会做编译/初始化, 被掐断只会得到假阴性
    (实测: 同一台机器两次运行一次 missing 一次 ok)。失败时把异常原因带出来,
    因为"socket 里没装"和"装了但 ABI 不匹配"需要完全不同的处置。
    """
    bad = []
    for mod in ("paddleocr", "paddle"):
        ok, detail = _import_probe(mod)
        if not ok:
            bad.append(detail)
    if bad:
        return False, "; ".join(bad)
    return True, "paddleocr 与 paddle 均可导入"


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
            install=lambda: pip_install(["paddleocr", "paddlepaddle"]),
            plan=lambda: " ".join(pip_cmd(["paddleocr", "paddlepaddle"])) + "   (数百 MB)",
            hint="pip install paddleocr paddlepaddle  (数百 MB; 加 --skip-heavy 可跳过)",
            why="l3_vision_verify 的 L2 中文/图片识别腿; 缺它则纯图片页无法识别"))
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


def run(install=True, include_heavy=True, strict=False, as_json=False, env=None,
        dry_run=False, only=None, stage="all", emit_frame=False):
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
    s = result["summary"]
    if dry_run:
        # dry-run 的语义是"计划已生成", 不是"环境就绪"; 只有必需且**无任何自动通道**
        # 的缺口才该让它非零退出(那种情况再跑一百次也补不上)。
        ok = not s["unresolvable"]
    else:
        ok = not s["blockers"] and (not strict or not result["compat"]["findings"])
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
  --help            显示本帮助

环境变量: VIA54_DRY_RUN / VIA54_ONLY / VIA54_SKIP_HEAVY / VIA54_STRICT /
          VIA54_JSON / VIA54_STAGE / VIA54_HOME / VIA54_ALLOW_BREAK_SYSTEM
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

    return run(install=install, include_heavy=include_heavy, strict=strict,
               as_json=as_json, dry_run=dry_run, only=only, stage=stage)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
