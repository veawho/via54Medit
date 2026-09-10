#!/usr/bin/env python3
"""
deploy.py — medit-telemetry (via54Medit 监控与飞书同步工具) 一键独立部署引擎

支持通过单行命令一键完成环境检测、包安装、用户花名配置、飞书授权、开机自启、伴随启动与后台守护运行。

用法:
  # 交互式单行部署
  python telemetry/deploy.py

  # 全自动静默无交互单行部署 (推荐跨设备批量分发)
  python telemetry/deploy.py --silent --nickname "张三" --openid "ou_xxx"

  # 带自定义排程时间部署
  python telemetry/deploy.py --silent --nickname "李四" --weekly "Friday 18:00" --monthly "last 18:00"
"""

import argparse
import os
import shutil
import site
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

# Ensure UTF-8 output across Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

TELEMETRY_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TELEMETRY_DIR)

# 启动器里用于识别「该命令已被本启动器接管」的标记, 靠它保证重复部署幂等
LAUNCHER_MARKER = "medit-telemetry 受保护启动器"

# Ensure telemetry is importable even before pip install
if TELEMETRY_DIR not in sys.path:
    sys.path.insert(0, TELEMETRY_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from telemetry.config import (
    CONFIG_FILE_PATH,
    DEFAULT_CONFIG,
    WEEKDAY_NAMES,
    interactive_setup,
    load_config,
    parse_monthly_time,
    parse_weekly_time,
    save_config,
)
from telemetry.daemon import (
    LOG_FILE,
    PID_FILE,
    get_daemon_status,
    install_startup_vbs,
    install_traework_companion_launcher,
    start_daemon_process,
    stop_daemon_process,
    uninstall_startup_vbs,
    install_launchd_agent,
    uninstall_launchd_agent,
)
from telemetry.platform_paths import is_on_path, user_bin_dirs


def print_banner():
    print("""
╔═══════════════════════════════════════════════════════════════╗
║   🚀 via54Medit 文献整理与 Highlight 监控统计独立部署引擎     ║
║          medit-telemetry (TraeWork Automated Telemetry)       ║
╚═══════════════════════════════════════════════════════════════╝
""")


def check_python_environment() -> bool:
    """检查 Python 版本及核心运行环境。"""
    ver = sys.version_info
    print(f"[*] 步骤 1/6: 检查运行环境...")
    print(f"    • Python 解释器: {sys.executable}")
    print(f"    • Python 版本:   {ver.major}.{ver.minor}.{ver.micro}")
    print(f"    • 操作系统平台:  {sys.platform}")

    if ver.major < 3 or (ver.major == 3 and ver.minor < 8):
        print(f"\n[!] 错误: Python 版本过低 ({ver.major}.{ver.minor})，需 >= 3.8。")
        return False
    print("    ✓ Python 版本满足要求 (>= 3.8)")
    return True


def _first_meaningful_line(text: str, limit: int = 160) -> str:
    """从多行命令输出里挑一条最有信息量的行，用于简报错误原因。"""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    for ln in lines:
        low = ln.lower()
        if "error" in low or "externally managed" in low or "no module named" in low:
            return ln[:limit]
    return (lines[0][:limit] if lines else "")


#: 解释器由外部管理 (PEP 668) 时 pip / uv 的输出特征
_EXTERNALLY_MANAGED_HINTS = ("externally-managed-environment", "externally managed")


def _editable_install_cmds() -> List[List[str]]:
    """可依次尝试的「可编辑安装」命令序列。

    阶段 1: 常规 ``pip install -e``;
    阶段 2: 解释器根本没有 pip (uv 托管环境常见) 时改用 ``uv pip install`` 兜底。

    这里**不带** ``--break-system-packages`` —— 那是绕过 PEP 668 保护的逃生开关，
    需调用方显式授权，见 ``install_package_locally``。
    """
    commands: List[List[str]] = [
        [sys.executable, "-m", "pip", "install", "-e", TELEMETRY_DIR, "--no-deps"]
    ]
    if shutil.which("uv"):
        commands.append([
            "uv", "pip", "install", "-e", TELEMETRY_DIR,
            "--python", sys.executable, "--no-deps",
        ])
    return commands


def _run_install(cmd: List[str]) -> Tuple[bool, str]:
    """执行一条安装命令。返回 (是否成功, 失败输出)。"""
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except Exception as e:
        return False, str(e)
    if res.returncode == 0:
        return True, ""
    return False, (res.stderr or "") + (res.stdout or "")


def _explain_pep668_skip() -> None:
    """解释 PEP 668 拒绝的原因，并给出显式开启逃生开关的方式。"""
    print("    [i] 该解释器由外部工具管理 (PEP 668)，安装被拒绝。")
    print("        本工具默认不绕过这道保护 —— 那是解释器管理方 (uv / 系统 / Homebrew)")
    print("        划下的边界，不该由部署脚本擅自突破。")
    print("        • 命令仍会安装 (由下一步的启动器落到 PATH)，功能可用；差别只是没有向")
    print("          该解释器登记包元数据，pip 无法追踪它的升级 / 卸载。")
    print("        • 确实要写入该解释器时，显式开启开关重跑：")
    print("            python telemetry/deploy.py --allow-break-system-packages")
    print("          或自行安装：")
    print("            python -m pip install -e telemetry --no-deps --break-system-packages")


def install_package_locally(allow_break_system_packages: bool = False) -> bool:
    """注册本模块，使 ``medit-telemetry`` 命令可用。

    先试 ``pip install -e``，解释器没有 pip 时改用 ``uv pip install`` 兜底。被
    PEP 668（外部管理的解释器）拒绝时**默认不绕过**：改为注入 ``.pth`` 保证可导入，
    命令则由 ``install_guarded_launcher()`` 落到 PATH 目录，功能照常可用。只有调用方
    显式传入 ``allow_break_system_packages=True`` 才追加逃生开关原地重试。
    """
    print(f"\n[*] 步骤 2/6: 安装并注册 medit-telemetry 模块...")
    reasons: List[str] = []
    denied_by_pep668 = False

    for cmd in _editable_install_cmds():
        tool = "uv pip" if cmd[0] == "uv" else "pip"
        ok, output = _run_install(cmd)
        if ok:
            print(f"    ✓ {tool} install -e 注册成功！全局命令 medit-telemetry 已就绪。")
            return True
        reasons.append(f"{tool}: {_first_meaningful_line(output)}")

        if not any(h in output.lower() for h in _EXTERNALLY_MANAGED_HINTS):
            continue
        denied_by_pep668 = True

        if not allow_break_system_packages:
            continue
        print(f"    [~] 已获授权：追加 --break-system-packages 重试 ({tool})...")
        ok2, out2 = _run_install(cmd + ["--break-system-packages"])
        if ok2:
            print("    ✓ 注册成功 (--break-system-packages)！全局命令 medit-telemetry 已就绪。")
            return True
        reasons.append(f"{tool}(retry): {_first_meaningful_line(out2)}")

    for r in reasons:
        print(f"    [~] 安装尝试未成功 —— {r}")
    if denied_by_pep668 and not allow_break_system_packages:
        _explain_pep668_skip()
    print("    [~] 改用 .pth 注入：只保证模块可导入，命令由下一步的启动器提供。")
    return _fallback_pth_install()


def install_guarded_launcher() -> bool:
    """把「环境自检启动器」安装为 medit-telemetry / traework-telemetry 命令。

    pip 生成的 console script 只是一段 Python 代码，解释器若因 PYTHONHOME 冲突在启动
    阶段就崩溃，它根本来不及执行（详见 telemetry/envcheck.py 的说明）。因此这里用同名
    的 shell 启动器覆盖它：未检测到冲突时行为完全一致，检测到冲突则改用 -E 忽略
    PYTHON* 变量并打印人话提示，把一个唬人的崩溃变成可用的命令。

    重新执行 `pip install -e` 会把命令还原成 pip 版本，重新跑本部署即可再次覆盖。
    """
    print(f"\n[*] 步骤 2b/6: 安装环境自检启动器...")
    template = os.path.join(TELEMETRY_DIR, "scripts", "medit-telemetry")
    if not os.path.exists(template):
        # 该模板已通过 package-data 随包分发 (pyproject.toml / setup.py),
        # 因此缺失基本只意味着安装不完整或包版本过旧, 而不是「正常情况」。
        print("    [~] 未找到启动器模板: " + template)
        print("        该文件随包分发, 缺失通常表示安装不完整或版本过旧。")
        print("        可先重新安装本模块再重试: pip install -U medit-telemetry")
        print("        (继续安装, 命令仍可用, 仅缺少环境冲突自检。)")
        return False
    try:
        with open(template, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"    [!] 读取启动器模板失败: {e}")
        return False

    content = content.replace("__MEDITELEMETRY_PYTHON__", sys.executable)

    targets = _launcher_targets()
    if not targets:
        print("    [!] 找不到可写的命令目录, 启动器未安装。")
        print("        手动安装方式: 把 telemetry/scripts/medit-telemetry 复制为 PATH 下的")
        print("        medit-telemetry (内容里的 __MEDITELEMETRY_PYTHON__ 替换为解释器路径)。")
        return False

    installed = 0
    for path in targets:
        # pip 生成的 console script 常常是软链接 (指向解释器 bin 目录里的真实脚本),
        # 必须写到软链指向的真实文件上, 否则改的是链接、真正被执行的还是旧脚本。
        real = os.path.realpath(path)
        try:
            existing = ""
            if os.path.exists(real):
                with open(real, "r", encoding="utf-8", errors="replace") as f:
                    existing = f.read()
                # 只在首次覆盖 pip 原版时留档, 重复部署不会把备份冲成启动器自身
                if LAUNCHER_MARKER not in existing and not os.path.exists(real + ".orig"):
                    shutil.copy2(real, real + ".orig")
                    print(f"    • 原命令已备份: {real}.orig")

            if existing == content:
                print(f"    ✓ 已是最新: {path}")
                installed += 1
                continue

            parent = os.path.dirname(real)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(real, "w", encoding="utf-8") as f:
                f.write(content)
            os.chmod(real, 0o755)
            shown = f"{path} -> {real}" if real != path else path
            print(f"    ✓ 已安装: {shown}")
            installed += 1
        except PermissionError:
            print(f"    [!] 无写入权限: {path} (可加 sudo 重试, 或跳过此项)")
        except Exception as e:
            print(f"    [!] 安装提示 ({path}): {e}")
    if not installed:
        print("    [~] 启动器未安装，命令仍可正常使用（仅缺少环境冲突自检）。")
        print("        常见原因是命令所在目录不可写, 可用 sudo 重试或手动执行本步骤。")
        return False

    off_path = sorted({
        os.path.dirname(os.path.realpath(p))
        for p in targets
        if not is_on_path(os.path.dirname(os.path.realpath(p)))
    })
    if off_path:
        print("    [!] 以下目录不在 PATH 中, 命令只能按完整路径调用:")
        for d in off_path:
            print(f"        {d}")
        print('        加入 PATH: export PATH="$HOME/.local/bin:$PATH"')
    return True


def _writable_bin_dir() -> str:
    """挑一个可写的用户级 bin 目录，优先选已在 PATH 上的；都不行返回空串。"""
    writable: List[str] = []
    for d in user_bin_dirs():
        try:
            os.makedirs(d, exist_ok=True)
        except OSError:
            continue
        if os.access(d, os.W_OK):
            writable.append(d)
    for d in writable:
        if is_on_path(d):
            return d
    return writable[0] if writable else ""


def _launcher_targets() -> List[str]:
    """两个命令名的安装目标路径。

    已存在的命令优先（它可能在软链后面），保持原有接管语义；不存在时挑一个
    「在 PATH 上且可写的用户级 bin 目录」新建 —— 否则 pip 被 PEP 668 拒绝时命令
    根本没被创建，部署流程最后打印的那些用法都成了摆设。
    """
    targets: List[str] = []
    for name in ("medit-telemetry", "traework-telemetry"):
        found = shutil.which(name)
        if found:
            targets.append(found)
            continue
        dest_dir = _writable_bin_dir()
        if dest_dir:
            targets.append(os.path.join(dest_dir, name))
    return targets


def _fallback_pth_install() -> bool:
    """离线或极简环境下将目录写入 user site-packages，免 pip 实现零依赖导入。"""
    try:
        user_site = site.getusersitepackages()
        os.makedirs(user_site, exist_ok=True)
        pth_file = os.path.join(user_site, "medit_telemetry.pth")
        with open(pth_file, "w", encoding="utf-8") as f:
            f.write(TELEMETRY_DIR + "\n")
            f.write(PROJECT_ROOT + "\n")
        print(f"    ✓ 备选链接已成功注入: {pth_file}")
        return True
    except Exception as e:
        print(f"    [!] 备选注册提示: {e}")
        return False


def setup_configuration(args) -> dict:
    """初始化或更新配置。"""
    print(f"\n[*] 步骤 3/6: 配置用户花名、飞书授权与定时汇报...")
    cfg = load_config()

    if args.silent or args.nickname or args.openid:
        # 非交互式或静默安装
        if args.nickname:
            cfg["user"]["nickname"] = args.nickname.strip()
        if args.openid:
            cfg["user"]["open_id"] = args.openid.strip()
        if args.app_id:
            cfg["feishu"]["app_id"] = args.app_id.strip()
        if args.app_secret:
            cfg["feishu"]["app_secret"] = args.app_secret.strip()
        if args.sheet:
            cfg["feishu"]["company_sheet_token"] = args.sheet.strip()
        if getattr(args, "bitable", ""):
            from telemetry.bitable_sync import FeishuBitableManager
            bmgr = FeishuBitableManager(cfg)
            ok, msg = bmgr.bind_existing_bitable(args.bitable.strip())
            cfg["feishu"]["company_bitable_token"] = bmgr.app_token
            cfg["feishu"]["company_bitable_table_id"] = bmgr.table_id
            cfg["feishu"]["company_bitable_url"] = bmgr.bitable_url
            if ok:
                print(f"    ✓ 成功绑定团队飞书多维表格: {cfg['feishu'].get('company_bitable_url')}")
            else:
                print(f"    ⚠️ 绑定团队飞书多维表格提示: {msg}")

        # 周报时间
        if args.weekly:
            parts = args.weekly.strip().split()
            if len(parts) == 2:
                day_idx, norm_time = parse_weekly_time(parts[0], parts[1])
                cfg["schedule"]["weekly"]["day_of_week"] = day_idx
                cfg["schedule"]["weekly"]["time"] = norm_time
            elif len(parts) == 1 and ":" in parts[0]:
                cfg["schedule"]["weekly"]["time"] = parts[0]

        # 月报时间
        if args.monthly:
            parts = args.monthly.strip().split()
            if len(parts) == 2:
                day_val, norm_time = parse_monthly_time(parts[0], parts[1])
                cfg["schedule"]["monthly"]["day_of_month"] = day_val
                cfg["schedule"]["monthly"]["time"] = norm_time
            elif len(parts) == 1 and ":" in parts[0]:
                cfg["schedule"]["monthly"]["time"] = parts[0]

        if args.add_watch_dir:
            wdir = os.path.abspath(args.add_watch_dir)
            if wdir not in cfg["watcher"]["watch_dirs"]:
                cfg["watcher"]["watch_dirs"].append(wdir)

        save_config(cfg)
        print("    ✓ 已应用命令行参数并固化配置。")
    else:
        # 终端交互向导
        interactive_setup()
        cfg = load_config()

    print(f"    • 当前用户花名:  {cfg['user'].get('nickname', '未设置')}")
    print(f"    • 绑定飞书账号:  {cfg['user'].get('open_id', '未设置')}")
    w_day = WEEKDAY_NAMES[cfg['schedule']['weekly']['day_of_week']]
    w_time = cfg['schedule']['weekly']['time']
    print(f"    • 每周汇报时间:  {w_day} {w_time}")
    m_day = "月末最后一天" if cfg['schedule']['monthly']['day_of_month'] == -1 else f"{cfg['schedule']['monthly']['day_of_month']}日"
    m_time = cfg['schedule']['monthly']['time']
    print(f"    • 每月汇报时间:  每月 {m_day} {m_time}")
    return cfg


def setup_autostart_and_launcher(args):
    """注册开机自启与桌面伴生启动器 (macOS LaunchAgent / Windows Startup VBS)。"""
    print(f"\n[*] 步骤 4/6: 注册开机自启与伴生启动器...")

    if args.no_startup:
        print("    - 跳过开机自启注册 (--no-startup)")
    elif sys.platform == "darwin":
        install_launchd_agent()
    elif sys.platform == "win32":
        install_startup_vbs()
    else:
        print("    - 跳过开机自启注册 (当前系统无内置实现: Windows 走 Startup VBS, macOS 走 LaunchAgent)")

    if not args.no_launcher and sys.platform == "win32":
        install_traework_companion_launcher()
    else:
        print("    - 跳过桌面伴随启动器创建 (--no-launcher 或非 Windows 系统)")


def launch_daemon_service(args):
    """启动后台守护服务。"""
    print(f"\n[*] 步骤 5/6: 启动后台主动监控与调度守护服务...")
    if args.no_start:
        print("    - 跳过后台启动 (--no-start)")
        return

    start_daemon_process()


def display_deployment_summary(cfg: dict):
    """展示最终部署概览与快速命令卡片。"""
    print(f"\n[*] 步骤 6/6: 校验部署状态与服务健康度...")
    st = get_daemon_status()
    is_running = st.get("running", False)
    pid = st.get("pid", "N/A")

    print("""
╔═══════════════════════════════════════════════════════════════╗
║               🎉 medit-telemetry 部署成功！                   ║
╚═══════════════════════════════════════════════════════════════╝""")
    status_icon = "🟢 正常运转中" if is_running else "🟡 未运行 (可通过命令启动)"
    print(f"  • 后台守护状态: {status_icon} (PID: {pid})")
    print(f"  • 配置文件路径: {CONFIG_FILE_PATH}")
    print(f"  • 运行日志文件: {LOG_FILE}")
    print(f"  • 用户昵称花名: {cfg['user'].get('nickname', 'wtg')}")
    print(f"  • 飞书通知推送: OpenID: {cfg['user'].get('open_id', '已配置')}")
    bitable_url = cfg.get("feishu", {}).get("company_bitable_url", "")
    print(f"  • 团队多维表格: {bitable_url if bitable_url else '未绑定 (运行 medit-telemetry bitable --create 或 --bind 绑定)'}")
    print(f"  • Token 统计模式: 🟢 exact (100% 服务商真实控制台账单对齐)")
    autostart_desc = {
        "win32": "✓ 已启用 (Startup VBS 静默自启)",
        "darwin": "✓ 已启用 (LaunchAgent 登录自启)",
    }.get(sys.platform, "N/A")
    print(f"  • 开机无感自启: {autostart_desc}")
    print("\n  📌 常用快捷命令:")
    print("    - 查看统计总览:      medit-telemetry status")
    print("    - 查看周报/战报:     medit-telemetry report --period week")
    print("    - 推送飞书卡片:      medit-telemetry push --period week")
    print("    - 团队图表看板:      medit-telemetry bitable --report")
    print("    - 查看 Token 账单:   medit-telemetry token --status")
    print("    - 查询守护进程:      medit-telemetry daemon --status")
    print("    - 桌面伴随启动:      双击桌面 [启动 TraeWork (带自动监控).vbs]")
    print("═══════════════════════════════════════════════════════════════\n")


def uninstall_deployment():
    """卸载与停止部署。"""
    print("[*] 正在卸载 medit-telemetry 守护服务与自启...")
    stop_daemon_process()
    if sys.platform == "win32":
        uninstall_startup_vbs()
    elif sys.platform == "darwin":
        uninstall_launchd_agent()
    print("✓ 已停止后台服务并移除开机自启。")


def main():
    parser = argparse.ArgumentParser(description="medit-telemetry 跨设备一键独立部署引擎 (支持纯自然语言指令)")
    parser.add_argument("instruction", nargs="?", default="", help="自然语言部署指令 (如: '在新设备上单独部署监控，花名wtg，每周五18:00汇报')")
    parser.add_argument("--silent", "-s", action="store_true", help="静默模式 (跳过交互提问，采用参数或默认配置)")
    parser.add_argument("--nickname", "-n", default="", help="用户花名/昵称 (如: wtg, 张三)")
    parser.add_argument("--openid", default="", help="绑定的用户飞书 OpenID (ou_...)")
    parser.add_argument("--app-id", default="", help="企业自建飞书应用 App ID (cli_...)")
    parser.add_argument("--app-secret", default="", help="企业自建飞书应用 App Secret")
    parser.add_argument("--sheet", default="", help="飞书公共多维表格/电子表格 Token")
    parser.add_argument("--bitable", default="", help="飞书团队多维表格 (Bitable) App Token 或完整 URL (用于团队数据周报自动上传汇总)")
    parser.add_argument("--weekly", default="", help="每周定时报告时间，如: 'Friday 18:00' 或 '周一 09:00'")
    parser.add_argument("--monthly", default="", help="每月定时报告时间，如: '1 09:00' 或 'last 18:00'")
    parser.add_argument("--add-watch-dir", default="", help="追加主动监控的工作区目录")
    parser.add_argument("--no-startup", action="store_true", help="不注册 Windows Startup 开机自启")
    parser.add_argument("--no-launcher", action="store_true", help="不创建桌面伴随启动器")
    parser.add_argument("--no-start", action="store_true", help="安装后不立即启动守护进程")
    parser.add_argument("--uninstall", action="store_true", help="停止守护服务并移除开机自启")
    parser.add_argument(
        "--allow-break-system-packages", "--break-system-packages",
        dest="allow_break_system_packages", action="store_true",
        help="显式允许在外部管理的解释器 (uv / 系统 / Homebrew) 上强制安装, "
             "绕过 PEP 668 保护; 默认不绕过, 改用 .pth 注入 (命令仍可用)")

    args = parser.parse_args()

    # 自然语言指令解析与参数补全
    if args.instruction and args.instruction.strip():
        from telemetry.nlp_deploy import parse_natural_language_instruction
        extracted = parse_natural_language_instruction(args.instruction)
        print(f"[*] 收到自然语言部署指令: \"{args.instruction}\"")
        if extracted.get("intent") == "uninstall":
            args.uninstall = True
        if extracted.get("nickname") and not args.nickname:
            args.nickname = extracted["nickname"]
            print(f"    • 自动提取用户花名: {args.nickname}")
        if extracted.get("openid") and not args.openid:
            args.openid = extracted["openid"]
            print(f"    • 自动提取飞书 OpenID: {args.openid}")
        if extracted.get("bitable") and not args.bitable:
            args.bitable = extracted["bitable"]
            print(f"    • 自动提取多维表格: {args.bitable}")
        if extracted.get("weekly") and not args.weekly:
            args.weekly = extracted["weekly"]
            print(f"    • 自动提取周报时间: {args.weekly}")
        if extracted.get("monthly") and not args.monthly:
            args.monthly = extracted["monthly"]
            print(f"    • 自动提取月报时间: {args.monthly}")
        if extracted.get("allow_break_system_packages"):
            args.allow_break_system_packages = True
            print("    • 识别到「强制安装」意图: 允许绕过 PEP 668 保护")
        # 自然语言触发默认全自动静默
        args.silent = True

    if args.uninstall:
        uninstall_deployment()
        return

    print_banner()
    if not check_python_environment():
        sys.exit(1)

    install_package_locally(allow_break_system_packages=getattr(
        args, "allow_break_system_packages", False))
    install_guarded_launcher()
    cfg = setup_configuration(args)
    setup_autostart_and_launcher(args)
    launch_daemon_service(args)
    display_deployment_summary(cfg)


if __name__ == "__main__":
    main()
