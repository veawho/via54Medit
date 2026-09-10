"""运行环境自检：识别被外部工具链注入、且与本解释器不匹配的 Python 环境变量。

背景
----
部分 IDE / 沙箱 / 构建工具会在终端里预置 ``PYTHONHOME`` 与 ``PYTHONPATH``，指向它们
自带的 Python。一旦该 Python 与 medit-telemetry 所用解释器版本不一致：

- 轻则 ``sys.path`` 被塞入别的版本的 ``site-packages``，可能导入到 ABI 不兼容的扩展
  模块（例如 PDF 相关扩展），报出难以理解的导入错误；
- 重则解释器在**启动阶段**直接崩溃::

      Fatal Python error: init_fs_encoding: failed to get the Python codec of the
      filesystem encoding ... ModuleNotFoundError: No module named 'encodings'

后一种情形连一行 Python 代码都来不及执行，因此本模块无法覆盖它 —— 那部分由外壳层
启动器 ``telemetry/scripts/medit-telemetry`` 在进程启动前拦截并给出同样的提示。

本模块只做「只读检测 + 人话提示」，不修改任何环境变量，也不改变命令行为。
"""

import os
import re
import sys
from typing import Dict, List, NamedTuple, Optional

__all__ = [
    "EnvIssue",
    "collect_issues",
    "render",
    "render_self_check",
    "warn_if_needed",
    "reset_warning_state",
    "current_version",
    "fix_command",
    "ISOLATED_ENV_VAR",
]

# 形如 .../python3.10/... 或 .../python3.10/site-packages 的版本目录
_PY_VERSION_DIR = re.compile(r"python(\d+)\.(\d+)")

# 外壳启动器 (telemetry/scripts/medit-telemetry) 检测到冲突并改用 -E 执行时会置位。
# 用于避免「启动器提示一次 + 本模块再提示一次」的重复刷屏。
ISOLATED_ENV_VAR = "MEDITELEMETRY_ENV_ISOLATED"

_warned = False


class EnvIssue(NamedTuple):
    """一条环境冲突。level 取 ``error`` (会直接致病) 或 ``warning`` (可能致病)。"""

    level: str
    title: str
    detail: str


def current_version() -> str:
    """当前解释器的主次版本号，如 ``3.11``。"""
    return f"{sys.version_info[0]}.{sys.version_info[1]}"


def _real(path: str) -> str:
    """解析软链接后的绝对路径；解析失败时退回原串，避免因路径不存在而报错。"""
    if not path:
        return ""
    try:
        return os.path.realpath(path)
    except Exception:
        return path


def _interpreter_prefix() -> str:
    """本解释器自身的安装前缀 (venv 下取基础解释器前缀)。"""
    return _real(getattr(sys, "base_prefix", "") or sys.prefix or "")


def _foreign_pythonpath_entries(pythonpath: str) -> List[tuple]:
    """挑出 PYTHONPATH 中指向其它 Python 版本的条目，返回 [(条目, 版本)]。"""
    ver = current_version()
    found: List[tuple] = []
    seen = set()
    for entry in pythonpath.split(os.pathsep):
        entry = entry.strip()
        if not entry:
            continue
        m = _PY_VERSION_DIR.search(entry)
        if not m:
            continue
        got = f"{m.group(1)}.{m.group(2)}"
        if got == ver or got in seen:
            continue
        seen.add(got)
        found.append((entry, got))
    return found


def collect_issues(environ: Optional[Dict[str, str]] = None) -> List[EnvIssue]:
    """检测环境变量冲突。``environ`` 仅用于测试注入，默认读取 ``os.environ``。"""
    env = os.environ if environ is None else environ
    issues: List[EnvIssue] = []

    home = (env.get("PYTHONHOME") or "").strip()
    if home:
        expected = _interpreter_prefix()
        if _real(home) != expected:
            issues.append(EnvIssue(
                "error",
                "PYTHONHOME 指向的解释器与本命令所用的不是同一个",
                f"PYTHONHOME        = {home}\n"
                f"本命令解释器前缀  = {expected or '(未知)'}\n"
                f"本命令解释器      = {sys.executable}",
            ))

    pythonpath = (env.get("PYTHONPATH") or "").strip()
    if pythonpath:
        ver = current_version()
        for entry, got in _foreign_pythonpath_entries(pythonpath):
            issues.append(EnvIssue(
                "warning",
                f"PYTHONPATH 注入了 Python {got} 的库路径, 本命令解释器是 {ver}",
                f"条目 = {entry}",
            ))

    return issues


def fix_command() -> str:
    """给出可直接复制的规避命令，命令名随调用方式自适应。"""
    name = os.path.basename(sys.argv[0] or "")
    if not name or name.endswith(".py") or name == "python":
        name = "python -m telemetry.cli"
    return f"env -u PYTHONHOME -u PYTHONPATH {name} <子命令>"


def render(issues: List[EnvIssue]) -> str:
    """把冲突渲染成人话提示。无冲突时返回空串。"""
    if not issues:
        return ""
    lines: List[str] = []
    lines.append("⚠️  运行环境自检: 检测到 Python 环境变量冲突")
    for it in issues:
        tag = "严重" if it.level == "error" else "提示"
        lines.append(f"  [{tag}] {it.title}")
        for d in it.detail.splitlines():
            lines.append(f"         {d}")
    lines.append("")
    lines.append("  这两个变量通常是 IDE / 沙箱工具链为它自带的 Python 预置的。")
    lines.append("  medit-telemetry 只依赖标准库, 不需要它们, 移除后不影响任何功能。")
    lines.append("")
    lines.append("  👉 临时规避 (立即生效):")
    lines.append(f"       {fix_command()}")
    lines.append("     或在当前终端先执行:")
    lines.append("       unset PYTHONHOME PYTHONPATH")
    lines.append("  👉 根治: 在 shell 启动脚本 (~/.zshrc / ~/.bashrc) 中删除对这两个变量的 export。")
    lines.append("")
    lines.append("  • 后台守护进程由 LaunchAgent / 计划任务拉起, 不继承终端环境, 因此不受影响。")
    return "\n".join(lines)


def render_self_check() -> str:
    """``--env-check`` 显式自检的输出 (无论有无冲突都给出结论)。"""
    home = os.environ.get("PYTHONHOME", "")
    pythonpath = os.environ.get("PYTHONPATH", "")
    lines: List[str] = []
    lines.append("🔍 medit-telemetry 运行环境自检")
    lines.append("=" * 55)
    lines.append(f"• 解释器      : {sys.executable}")
    lines.append(f"• 版本        : {current_version()} ({sys.version.split()[0]})")
    lines.append(f"• 解释器前缀  : {_interpreter_prefix()}")
    lines.append(f"• PYTHONHOME  : {home or '(未设置)'}")
    lines.append(f"• PYTHONPATH  : {pythonpath or '(未设置)'}")
    if os.environ.get(ISOLATED_ENV_VAR):
        lines.append("• 启动器      : 已检测到冲突, 本次已忽略 PYTHON* 变量执行")
    lines.append("=" * 55)

    issues = collect_issues()
    if not issues:
        lines.append("✓ 未发现冲突, 当前环境可直接使用。")
        return "\n".join(lines)

    lines.append(render(issues))
    return "\n".join(lines)


def warn_if_needed(stream=None, force: bool = False) -> bool:
    """发现冲突时向 ``stream`` (默认 stderr) 打印提示。

    同一进程内只提示一次, 避免子命令嵌套调用时重复刷屏; ``force=True`` 可强制输出。
    若外壳启动器已经拦截并提示过 (``ISOLATED_ENV_VAR`` 置位), 这里不再重复。
    返回 True 表示本次确实打印了提示。
    """
    global _warned
    if _warned and not force:
        return False
    _warned = True
    if os.environ.get(ISOLATED_ENV_VAR):
        return False
    issues = collect_issues()
    if not issues:
        return False
    print(render(issues), file=stream or sys.stderr)
    print("", file=stream or sys.stderr)
    return True


def reset_warning_state() -> None:
    """仅供测试使用：重置「已提示」标记。"""
    global _warned
    _warned = False
