#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
uninstall.py — via54Medit 一键完全卸载与清理脚本 (Cross-platform Uninstaller)
========================================================================
支持平台: Windows / macOS / Linux
核心功能:
  1. 终止所有运行中的 via54Medit / telemetry 守护进程与采集进程
  2. 注销并清除系统定时任务 (Windows schtasks / macOS·Linux crontab / launchd)
  3. 移除开机自启脚本 (Windows Startup VBS / macOS LaunchAgent)
  4. 彻底删除已部署的主目录 (~/.via54medit, ~/.medit)
  5. 清理豆包/飞书工作伙伴部署技能与临时解压目录
  6. 清理下载的安装包归档与临时缓存
  7. 支持一并清理本地代码仓库 (--clean-repo)

用法 / Usage:
  python uninstall.py                 # 执行全量卸载 (保留当前源码目录)
  python uninstall.py --clean-repo    # 执行全量卸载并删除本地代码仓库
  python uninstall.py --check-only    # 仅体检待清理项目，不实际删除
"""

import argparse
import os
import platform
import shutil
import signal
import subprocess
import sys
from pathlib import Path

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

HOME = os.path.expanduser("~")
BIN_DIR = os.path.join(HOME, ".via54medit")
CFG_DIR = os.path.join(HOME, ".medit")
PID_FILE = os.path.join(CFG_DIR, "daemon.pid")

REPORT = []


def rep(name, status, detail=""):
    REPORT.append((name, status, detail))
    mark = {"OK": "✅", "REMOVED": "🗑️", "KILLED": "🛑", "SKIP": "➖", "FAIL": "❌", "WARN": "⚠️"}.get(status, "·")
    print(f"{mark} {name:<36} {detail}", flush=True)


def run_cmd(cmd, silent=True):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return -1, "", str(e)


def is_windows():
    return platform.system().lower() == "windows"


def is_macos():
    return platform.system().lower() == "darwin"


def is_linux():
    return platform.system().lower() == "linux"


# ================= 1. 停止运行中的进程 =================
def kill_processes(check_only=False):
    print("\n[1/6] 检查并终止后台运行中的 via54Medit / Telemetry 进程...", flush=True)
    killed = 0

    # 1. 尝试从 PID 文件读取
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
            if pid > 0:
                if check_only:
                    rep("守护进程 PID (来自记录)", "WARN", f"发现存活守护进程 PID: {pid}")
                else:
                    if is_windows():
                        run_cmd(["taskkill", "/F", "/PID", str(pid)])
                    else:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except OSError:
                            pass
                    rep("守护进程 (daemon.pid)", "KILLED", f"已终止 PID: {pid}")
                    killed += 1
        except Exception:
            pass

    # 2. 扫描包含 telemetry.cli / usage_collector / monday_finalize / medit 的进程
    if is_windows():
        ps_script = """
        Get-CimInstance Win32_Process | Where-Object {
            $_.CommandLine -match "telemetry\\.cli|usage_collector|monday_finalize|\\.via54medit" -and
            $_.ExecutablePath -notmatch "Intel\\\\TelemetryAgent"
        } | Select-Object -ExpandProperty ProcessId
        """
        rc, out, _ = run_cmd(["powershell", "-NoProfile", "-Command", ps_script])
        if rc == 0 and out.strip():
            for line in out.splitlines():
                line = line.strip()
                if line.isdigit():
                    p = int(line)
                    if p != os.getpid():
                        if check_only:
                            rep("运行中进程", "WARN", f"检测到进程 PID: {p}")
                        else:
                            run_cmd(["taskkill", "/F", "/PID", str(p)])
                            rep("运行中进程", "KILLED", f"已强制终止 PID: {p}")
                            killed += 1
    else:
        # macOS / Linux pkill
        patterns = ["telemetry.cli", "usage_collector.py", "monday_finalize.py", "medit"]
        for pat in patterns:
            rc, out, _ = run_cmd(["pgrep", "-f", pat])
            if rc == 0 and out.strip():
                for p_str in out.splitlines():
                    p_str = p_str.strip()
                    if p_str.isdigit():
                        p = int(p_str)
                        if p != os.getpid():
                            if check_only:
                                rep(f"运行中进程 ({pat})", "WARN", f"检测到 PID: {p}")
                            else:
                                run_cmd(["kill", "-9", str(p)])
                                rep(f"运行中进程 ({pat})", "KILLED", f"已终止 PID: {p}")
                                killed += 1

    if killed == 0:
        rep("后台进程检查", "OK", "无活跃的 via54Medit / Telemetry 进程")


# ================= 2. 注销定时任务与计划任务 =================
def remove_scheduled_tasks(check_only=False):
    print("\n[2/6] 清除系统计划任务与定时排程...", flush=True)

    if is_windows():
        tasks = [
            "medit-usage-collector",
            "medit-monday-finalize",
            "MeditTelemetryWeekly",
            "MeditTelemetryMonthly",
        ]
        for t in tasks:
            rc, out, _ = run_cmd(["schtasks", "/Query", "/TN", t])
            if rc == 0:
                if check_only:
                    rep(f"计划任务: {t}", "WARN", "已注册待删除")
                else:
                    rc_del, _, _ = run_cmd(["schtasks", "/Delete", "/F", "/TN", t])
                    if rc_del == 0:
                        rep(f"计划任务: {t}", "REMOVED", "已成功注销并移除")
                    else:
                        rep(f"计划任务: {t}", "FAIL", "注销失败")
            else:
                rep(f"计划任务: {t}", "OK", "未注册或已清理")
    else:
        # macOS / Linux Crontab 清理
        rc, out, _ = run_cmd(["crontab", "-l"])
        if rc == 0 and out.strip():
            lines = out.splitlines()
            cleaned = [
                l for l in lines
                if "usage_collector.py" not in l
                and "monday_finalize.py" not in l
                and "medit" not in l
                and "create_sched.py" not in l
            ]
            if len(cleaned) != len(lines):
                if check_only:
                    rep("Crontab 定时任务", "WARN", f"发现 {len(lines) - len(cleaned)} 条待清除项")
                else:
                    tmp = os.path.join(HOME, ".medit_crontab.tmp")
                    with open(tmp, "w", encoding="utf-8") as f:
                        f.write("\n".join(cleaned) + "\n")
                    run_cmd(["crontab", tmp])
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                    rep("Crontab 定时任务", "REMOVED", "已清除全部 via54Medit 自动排程条目")
            else:
                rep("Crontab 定时任务", "OK", "无残留条目")
        else:
            rep("Crontab 定时任务", "OK", "未配置")

        # macOS LaunchAgent 清理
        if is_macos():
            plist = os.path.expanduser("~/Library/LaunchAgents/com.via54.medit.telemetry.plist")
            if os.path.exists(plist):
                if check_only:
                    rep("macOS LaunchAgent", "WARN", plist)
                else:
                    run_cmd(["launchctl", "unload", "-w", plist])
                    try:
                        os.remove(plist)
                        rep("macOS LaunchAgent", "REMOVED", f"已注销并删除: {plist}")
                    except Exception as e:
                        rep("macOS LaunchAgent", "FAIL", str(e))


# ================= 3. 移除开机自启脚本 =================
def remove_autostart_files(check_only=False):
    print("\n[3/6] 检查并移除开机启动脚本与伴随启动器...", flush=True)

    if is_windows():
        startup_dir = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
        targets = [
            os.path.join(startup_dir, "traework_telemetry_silent.vbs"),
            os.path.join(startup_dir, "启动 TraeWork (带自动监控).vbs"),
            os.path.join(os.path.join(HOME, "Desktop"), "启动 TraeWork (带自动监控).vbs"),
        ]
        for t in targets:
            if os.path.exists(t):
                if check_only:
                    rep(f"自启项: {os.path.basename(t)}", "WARN", t)
                else:
                    try:
                        os.remove(t)
                        rep(f"自启项: {os.path.basename(t)}", "REMOVED", f"已删除: {t}")
                    except Exception as e:
                        rep(f"自启项: {os.path.basename(t)}", "FAIL", str(e))
            else:
                rep(f"自启项: {os.path.basename(t)}", "OK", "不存在")
    else:
        rep("自启启动项检查", "OK", "非 Windows，已在第 2 步统一清理")


# ================= 4. 删除已部署主目录与数据 =================
def remove_deployed_directories(check_only=False):
    print("\n[4/6] 清除已部署主目录 (~/.via54medit / ~/.medit)...", flush=True)

    dirs_to_remove = [
        BIN_DIR,  # ~/.via54medit
        CFG_DIR,  # ~/.medit
    ]

    for d in dirs_to_remove:
        if os.path.exists(d):
            if check_only:
                rep(f"已部署目录: {os.path.basename(d)}", "WARN", d)
            else:
                try:
                    shutil.rmtree(d, ignore_errors=False)
                    rep(f"已部署目录: {os.path.basename(d)}", "REMOVED", f"已递归彻底清除: {d}")
                except Exception as e:
                    # 容错尝试只读属性清理
                    try:
                        def on_exc(fn, path, excinfo):
                            os.chmod(path, 0o777)
                            fn(path)
                        shutil.rmtree(d, onerror=on_exc)
                        rep(f"已部署目录: {os.path.basename(d)}", "REMOVED", f"重试后已删除: {d}")
                    except Exception as e2:
                        rep(f"已部署目录: {os.path.basename(d)}", "FAIL", str(e2))
        else:
            rep(f"已部署目录: {os.path.basename(d)}", "OK", "不存在或已清理")


# ================= 5. 清理豆包工作伙伴、技能与安装临时文件 =================
def remove_integrations_and_temps(check_only=False):
    print("\n[5/6] 清理工作伙伴解压缓存、用户技能与安装归档...", flush=True)

    # 1. 飞书/豆包 lark-chats 解压目录
    doubao_chat_medit = os.path.join(HOME, r".doubao\lark-chats\2026-10-12\new-chat\via54Medit")
    if os.path.exists(doubao_chat_medit):
        if check_only:
            rep("豆包解压工作空间", "WARN", doubao_chat_medit)
        else:
            try:
                shutil.rmtree(doubao_chat_medit, ignore_errors=True)
                rep("豆包解压工作空间", "REMOVED", doubao_chat_medit)
            except Exception as e:
                rep("豆包解压工作空间", "FAIL", str(e))
    else:
        rep("豆包解压工作空间", "OK", "未发现残留")

    # 2. 豆包 / LarkShell 用户技能目录
    skills_parent = os.path.join(
        os.environ.get("APPDATA", ""),
        r"LarkShell\aha\users\d3cbefc07078f021dab889c87626bd02\doubao\.doubao\agent_mode\workspace\.user_skills"
    )
    if os.path.exists(skills_parent):
        for entry in os.listdir(skills_parent):
            if entry.startswith("via54medit"):
                full_skill_path = os.path.join(skills_parent, entry)
                if check_only:
                    rep(f"豆包技能: {entry}", "WARN", full_skill_path)
                else:
                    try:
                        shutil.rmtree(full_skill_path, ignore_errors=True)
                        rep(f"豆包技能: {entry}", "REMOVED", entry)
                    except Exception as e:
                        rep(f"豆包技能: {entry}", "FAIL", str(e))

    # 3. 安装归档与 Temp 缓存
    temp_candidates = [
        os.path.join(HOME, r"Downloads\via54medit-workmate-installer-v5.4.51.zip"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Temp\rel50"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Temp\rel51"),
    ]
    for tc in temp_candidates:
        if os.path.exists(tc):
            if check_only:
                rep(f"安装缓存: {os.path.basename(tc)}", "WARN", tc)
            else:
                try:
                    if os.path.isdir(tc):
                        shutil.rmtree(tc, ignore_errors=True)
                    else:
                        os.remove(tc)
                    rep(f"安装缓存: {os.path.basename(tc)}", "REMOVED", tc)
                except Exception as e:
                    rep(f"安装缓存: {os.path.basename(tc)}", "FAIL", str(e))


# ================= 6. 清理本地仓库 =================
def clean_local_repo(repo_path, check_only=False):
    print("\n[6/6] 本地代码仓库清理...", flush=True)
    if not repo_path or not os.path.exists(repo_path):
        rep("本地仓库", "OK", "未指定或路径不存在")
        return

    abs_repo = os.path.abspath(repo_path)
    if check_only:
        rep("本地代码仓库", "WARN", f"待清理目录: {abs_repo}")
        return

    try:
        shutil.rmtree(abs_repo, ignore_errors=False)
        rep("本地代码仓库", "REMOVED", f"已成功删除本地代码仓库: {abs_repo}")
    except Exception as e:
        # 重试并强制清理只读文件 (如 .git/objects)
        def on_rm_error(func, path, exc_info):
            os.chmod(path, 0o777)
            func(path)
        try:
            shutil.rmtree(abs_repo, onerror=on_rm_error)
            rep("本地代码仓库", "REMOVED", f"强制清理成功: {abs_repo}")
        except Exception as e2:
            rep("本地代码仓库", "FAIL", f"清理失败: {e2}")


def main():
    parser = argparse.ArgumentParser(
        prog="uninstall.py",
        description="via54Medit 一键完全卸载与清理脚本 (Cross-platform Uninstaller)"
    )
    parser.add_argument("--check-only", action="store_true", help="仅体检检查，不实际删除")
    parser.add_argument("--clean-repo", action="store_true", help="同时清除当前本地代码仓库")
    parser.add_argument("--repo-path", default="", help="指定本地代码仓库路径（若省略且指定了 --clean-repo，则清理当前脚本所在仓库）")
    args = parser.parse_args()

    print("==================================================================", flush=True)
    print(" 🧹 via54Medit 一键完全卸载与清理引擎 (Full Uninstaller & Cleaner)", flush=True)
    print(f" 平台系统: {platform.system()} {platform.release()} ({platform.machine()})", flush=True)
    print("==================================================================", flush=True)

    kill_processes(args.check_only)
    remove_scheduled_tasks(args.check_only)
    remove_autostart_files(args.check_only)
    remove_deployed_directories(args.check_only)
    remove_integrations_and_temps(args.check_only)

    if args.clean_repo:
        target_repo = args.repo_path
        if not target_repo:
            current_script_dir = os.path.dirname(os.path.abspath(__file__))
            if os.path.exists(os.path.join(current_script_dir, ".git")):
                target_repo = current_script_dir
        if target_repo:
            clean_local_repo(target_repo, args.check_only)
        else:
            rep("本地代码仓库", "WARN", "未定位到有效 .git 仓库，跳过仓库删除")

    print("\n========================= 卸载与清理总结 =========================", flush=True)
    removed = sum(1 for _, s, _ in REPORT if s in ("REMOVED", "KILLED"))
    ok = sum(1 for _, s, _ in REPORT if s == "OK")
    warn = sum(1 for _, s, _ in REPORT if s == "WARN")
    fail = sum(1 for _, s, _ in REPORT if s == "FAIL")

    print(f" 🗑️ 已清理/终止: {removed}   ✅ 已就绪/无残留: {ok}   ⚠️ 待处理: {warn}   ❌ 失败: {fail}\n", flush=True)
    if fail > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
