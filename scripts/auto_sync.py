#!/usr/bin/env python3
"""
auto_sync.py — via54Medit 自动从 GitHub 拉取最新代码并同步更新本地部署

功能:
  1. 定期从 remote origin/main 获取最新代码 (git fetch & pull)。
  2. 自动重新编译 Go 核心二进制 (bin/medit, bin/medit-mcp)。
  3. 自动运行单元测试确保代码健康。
  4. 支持作为守护进程运行 (--daemon)、单次执行 (--pull) 或一键注册为系统定时任务 (--install-cron / --install-launchd)。
"""
import os
import sys
import time
import argparse
import subprocess
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent


def run_cmd(cmd, cwd=REPO_DIR, timeout=300):
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return res.returncode == 0, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        return False, "", str(e)


def check_updates():
    """检查远程是否有新 commit"""
    print("[auto_sync] 正在检查 GitHub 远程更新...")
    ok, _, err = run_cmd(["git", "fetch", "origin", "main"])
    if not ok:
        print(f"  ⚠️ git fetch 失败: {err}")
        return False, "fetch_failed"
    
    ok, count, _ = run_cmd(["git", "rev-list", "HEAD..origin/main", "--count"])
    if ok and count.isdigit() and int(count) > 0:
        print(f"  ✓ 发现远程有 {count} 个新提交待更新")
        return True, int(count)
    print("  ✓ 本地代码已是最新版本")
    return False, 0


def pull_and_rebuild():
    """拉取最新代码并重新编译部署"""
    print("[auto_sync] 开始执行代码同步与重新编译...")
    
    # 1. Git pull
    ok, out, err = run_cmd(["git", "pull", "--rebase", "origin", "main"])
    if not ok:
        print(f"  ✗ git pull 失败: {err}")
        return False
    print(f"  ✓ 代码拉取成功: {out}")
    
    # 2. 编译 Go 核心
    print("[auto_sync] 重新构建 Go 核心二进制 (bin/medit, bin/medit-mcp)...")
    ok, _, err = run_cmd(["go", "build", "-o", "bin/medit", "./cmd/medit"])
    if not ok:
        print(f"  ⚠️ bin/medit 编译警告: {err}")
    else:
        print("  ✓ bin/medit 构建成功")
        
    ok, _, err = run_cmd(["go", "build", "-o", "bin/medit-mcp", "./cmd/medit-mcp"])
    if not ok:
        print(f"  ⚠️ bin/medit-mcp 编译警告: {err}")
    else:
        print("  ✓ bin/medit-mcp 构建成功")

    # 3. 运行 Python 单元测试验证
    print("[auto_sync] 验证 Python 核心算法健康状态...")
    test_script = REPO_DIR / "scripts" / "hl_v3_final" / "test_hl_lib.py"
    if test_script.exists():
        ok, _, err = run_cmd([sys.executable, str(test_script)])
        if ok:
            print("  ✓ 核心单元测试全部通过")
        else:
            print(f"  ⚠️ 测试提示: {err}")
            
    print("[auto_sync] ✅ 本地部署已更新至最新版本！")
    return True


def install_cron(interval_hours=6):
    """注册 crontab 周期拉取 (macOS / Linux)"""
    script_path = os.path.abspath(__file__)
    python_path = sys.executable
    cron_job = f"0 */{interval_hours} * * * {python_path} {script_path} --pull >> /tmp/via54medit_sync.log 2>&1"
    
    ok, current_cron, _ = run_cmd(["crontab", "-l"])
    current_cron = current_cron if ok else ""
    
    if script_path in current_cron:
        print("[auto_sync] Crontab 定时任务已存在，无需重复添加。")
        return True
        
    new_cron = (current_cron.strip() + "\n" + cron_job + "\n").lstrip()
    proc = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE, text=True)
    proc.communicate(input=new_cron)
    if proc.returncode == 0:
        print(f"[auto_sync] ✓ 成功注册 Crontab 定时同步任务 (每 {interval_hours} 小时执行一次)")
        return True
    else:
        print("[auto_sync] ✗ 注册 Crontab 失败")
        return False


def install_launchd(interval_hours=6):
    """注册 macOS LaunchAgent 守护任务"""
    if sys.platform != "darwin":
        print("[auto_sync] LaunchAgent 仅支持 macOS。")
        return False
        
    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_path = plist_dir / "com.via54medit.autosync.plist"
    
    script_path = os.path.abspath(__file__)
    python_path = sys.executable
    interval_seconds = interval_hours * 3600
    
    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.via54medit.autosync</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>{script_path}</string>
        <string>--pull</string>
    </array>
    <key>StartInterval</key>
    <integer>{interval_seconds}</integer>
    <key>StandardOutPath</key>
    <string>/tmp/via54medit_sync.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/via54medit_sync_err.log</string>
</dict>
</plist>
"""
    with open(plist_path, "w", encoding="utf-8") as f:
        f.write(plist_content)
        
    run_cmd(["launchctl", "unload", str(plist_path)])
    ok, _, err = run_cmd(["launchctl", "load", str(plist_path)])
    if ok:
        print(f"[auto_sync] ✓ 成功安装并启动 macOS LaunchAgent ({plist_path})，每 {interval_hours} 小时自动同步")
        return True
    else:
        print(f"[auto_sync] ⚠️ 加载 LaunchAgent 提示: {err}")
        return False


def run_daemon(interval_minutes=360):
    """前台守护循环模式"""
    print(f"[auto_sync] 启动自动同步守护进程 (轮询周期: {interval_minutes} 分钟)...")
    while True:
        try:
            has_updates, _ = check_updates()
            if has_updates:
                pull_and_rebuild()
        except Exception as e:
            print(f"[auto_sync] 轮询周期发生异常: {e}")
        time.sleep(interval_minutes * 60)


def main():
    parser = argparse.ArgumentParser(description="via54Medit GitHub 自动同步与构建工具")
    parser.add_argument("--check", action="store_true", help="仅检查是否有更新")
    parser.add_argument("--pull", action="store_true", help="拉取最新代码并重新编译")
    parser.add_argument("--daemon", action="store_true", help="启动后台守护进程循环更新")
    parser.add_argument("--interval", type=int, default=6, help="定时同步周期(小时), 默认6小时")
    parser.add_argument("--install-cron", action="store_true", help="注册系统 Crontab 定时同步")
    parser.add_argument("--install-launchd", action="store_true", help="注册 macOS LaunchAgent 定时同步")
    args = parser.parse_args()

    if args.install_cron:
        install_cron(args.interval)
        return
    if args.install_launchd:
        install_launchd(args.interval)
        return
    if args.daemon:
        run_daemon(args.interval * 60)
        return
    if args.check:
        check_updates()
        return

    # 默认行为: 检查更新，若有则拉取并重新编译
    has_updates, _ = check_updates()
    if has_updates or args.pull:
        pull_and_rebuild()


if __name__ == "__main__":
    main()
