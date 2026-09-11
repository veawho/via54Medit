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
import shutil
import sys
import time
import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

REPO_DIR = Path(__file__).resolve().parent.parent

# 日志落在 ~/.medit 下 (与遥测模块一致), 不再放 /tmp。
# /tmp 会被 macOS 的 periodic(8) 回收 —— 3 天未访问即删除, 历史说没就没, 出了问题无从回溯。
LOG_FILE = Path.home() / ".medit" / "autosync.log"
LOG_BACKUP_FILE = Path(str(LOG_FILE) + ".1")
LOG_MAX_BYTES = 5 * 1024 * 1024

# 拉取重试: 网络 / 代理抖动 (Clash 换节点、重连) 常在一两秒内自愈, 短重试远比等 6 小时划算。
PULL_ATTEMPTS = 3
PULL_RETRY_DELAY_SECONDS = 10


def rotate_log_if_needed():
    """日志超过上限时留一份 .1 备份再就地清空。

    用「复制 + 截断」而不是「改名 + 新建」: launchd 的 StandardOutPath 只在启动时打开
    文件一次并长期持有该 fd, 改名会让它继续写旧 inode, 与按路径写新文件的进程分叉。
    """
    try:
        if LOG_FILE.stat().st_size <= LOG_MAX_BYTES:
            return
    except OSError:
        return
    try:
        shutil.copy2(LOG_FILE, LOG_BACKUP_FILE)
        with open(LOG_FILE, "w", encoding="utf-8"):
            pass
    except Exception:
        pass


def _stdout_is_log_file() -> bool:
    """stdout 是否已经就是日志文件本身 (launchd 的 StandardOutPath 场景)。"""
    try:
        out = os.fstat(sys.stdout.fileno())
        target = LOG_FILE.stat()
    except Exception:
        return False
    return (out.st_dev, out.st_ino) == (target.st_dev, target.st_ino)


def log(message: str = ""):
    """打一行**带时间戳**的日志。

    时间戳是这次排查最大的障碍 —— 旧日志一行时间都没有, 失败无法与时刻对应。

    落点只有一处, 避免重复: launchd 已经把 stdout 重定向到同一个文件, 这时只 print
    (由 launchd 落盘); 手工在终端跑时则 print + 自己写文件, 两边都能看到。
    """
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}" if message else ""

    # 轮转无条件执行: 即使本次由 launchd 落盘, 也需要有人把超限的日志收一下。
    try:
        rotate_log_if_needed()
    except Exception:
        pass

    if not _stdout_is_log_file():
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    try:
        print(line)
    except Exception:
        pass


# 拉取状态 -> 人话, 供日志与告警卡片共用
_PULL_STATE_TEXT = {
    "ok": "成功",
    "skipped_dirty": "跳过 (工作区有未提交改动)",
    "failed": "失败 (暂时性网络/代理故障)",
}


def notify(title: str, lines, key: str, level: str = "warning") -> bool:
    """把关键事件推到外部告警通道 (飞书)。

    直接复用 ``telemetry.alerter`` —— 同一条链路、同一份限流账本 (~/.medit/alerts_state.json),
    不重复实现一套。告警只在这几种失败场景触发, 成功时保持安静。

    惰性导入 + 整段吞异常: 告警通道不可用时 (包未部署、网络不通、依赖缺失) 绝不能影响
    同步任务本身 —— "发不出告警"不该升级成新的故障。
    """
    try:
        repo = str(REPO_DIR)
        if repo not in sys.path:
            sys.path.insert(0, repo)
        from telemetry.alerter import send_alert

        ok, msg = send_alert(title, list(lines), key=key, level=level)
        log(f"  {'✓' if ok else 'ⓘ'} 告警推送: {msg}")
        return ok
    except Exception as e:
        log(f"  ⚠️ 告警通道不可用 (已忽略, 不影响同步任务): {e}")
        return False


def launchd_path() -> str:
    """为 LaunchAgent 构造 PATH。

    launchd 默认只给 /usr/bin:/bin:/usr/sbin:/sbin —— 不含 Homebrew (/opt/homebrew/bin),
    于是 go 在定时任务里"找不到", 而这类失败又很容易被当成无害警告咽下去。这里显式列出
    同步所需的目录: go 所在目录 + 常见包管理器目录 + 系统目录。

    刻意不整段照抄安装时的交互式 PATH —— 那会把 IDE / 沙箱的内部路径固化进 LaunchAgent,
    一旦该应用升级换目录就整体失效, 很脆。
    """
    candidates = []
    go_bin = shutil.which("go")
    if go_bin:
        candidates.append(os.path.dirname(go_bin))
    candidates += [
        "/opt/homebrew/bin",
        "/usr/local/bin",
        str(Path.home() / ".local" / "bin"),
        "/usr/bin", "/bin", "/usr/sbin", "/sbin",
    ]
    parts = []
    for c in candidates:
        if c and c not in parts and os.path.isdir(c):
            parts.append(c)
    return os.pathsep.join(parts)


def run_cmd(cmd, cwd=REPO_DIR, timeout=300):
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return res.returncode == 0, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        return False, "", str(e)


def check_updates():
    """检查远程是否有新 commit"""
    log("[auto_sync] 正在检查 GitHub 远程更新...")
    ok, _, err = run_cmd(["git", "fetch", "origin", "main"])
    if not ok:
        log(f"  ⚠️ git fetch 失败 (疑似网络/代理抖动): {err}")
        return False, "fetch_failed"

    ok, count, _ = run_cmd(["git", "rev-list", "HEAD..origin/main", "--count"])
    if ok and count.isdigit() and int(count) > 0:
        log(f"  ✓ 发现远程有 {count} 个新提交待更新")
        return True, int(count)
    log("  ✓ 本地代码已是最新版本")
    return False, 0


def worktree_is_dirty() -> bool:
    """工作区是否有未提交改动。"""
    ok, out, _ = run_cmd(["git", "status", "--porcelain"])
    return bool(ok and out.strip())


def pull_with_retry():
    """拉取 origin/main, 返回 (是否成功, 末次输出, 实际尝试次数)。

    本机 git 走 Clash 本地代理, 换节点 / 重连会让 TLS 会话被中途掐断
    (`SSL_ERROR_SYSCALL`), 这类抖动通常一两秒内自愈 —— 短重试远比留到 6 小时后划算。
    """
    last = ""
    for attempt in range(1, PULL_ATTEMPTS + 1):
        ok, out, err = run_cmd(["git", "pull", "--rebase", "origin", "main"])
        if ok:
            return True, out, attempt
        last = err or out
        if attempt < PULL_ATTEMPTS:
            log(f"  ⚠️ 第 {attempt}/{PULL_ATTEMPTS} 次拉取失败: {last}")
            log(f"     疑似网络/代理抖动, {PULL_RETRY_DELAY_SECONDS}s 后重试...")
            time.sleep(PULL_RETRY_DELAY_SECONDS)
    return False, last, PULL_ATTEMPTS


def pull_and_rebuild():
    """同步代码并重新构建部署, 返回 (部署是否已更新, 拉取状态)。

    拉取状态取 ``ok`` / ``skipped_dirty`` / ``failed``。

    关键原则: **任何拉取问题都不应中止构建**。构建用的是本地工作区, 与拉取成功与否无关;
    过去一遇拉取失败就 return, 白白放弃了一次更新二进制并验证的机会 —— 这也是"构建失败"
    看起来层出不穷的原因之一 (其实是根本没走到构建)。
    """
    log("[auto_sync] 开始执行代码同步与重新编译...")

    # 1. 代码同步
    pull_state = "ok"
    pull_detail = ""
    pull_attempts = 0
    if worktree_is_dirty():
        # 刻意不用 --autostash: 无人值守时一旦 autostash 回放冲突, 会在工作区留下冲突现场,
        # 下一个周期照样卡住。跳过更安全, 且构建仍然照做。
        pull_state = "skipped_dirty"
        log("  ⚠️ 工作区有未提交改动, 本次跳过代码拉取 (避免 autostash 回放冲突)。")
        log("     仍会从当前工作区重新构建; 提交或 stash 后下个周期自动恢复同步。")
    else:
        ok, pull_detail, pull_attempts = pull_with_retry()
        if ok:
            suffix = f" (第 {pull_attempts} 次尝试)" if pull_attempts > 1 else ""
            log(f"  ✓ 代码拉取成功: {pull_detail}{suffix}")
        else:
            pull_state = "failed"
            log(f"  ✗ 代码拉取失败 (已重试 {pull_attempts} 次): {pull_detail}")
            log("     → 判定为暂时性网络/代理故障; 本次仍继续构建, 下个周期会自动重试拉取。")

    # 2. 编译 Go 核心 (走 Makefile, 以便按 git describe 打上正确的版本戳)
    log("[auto_sync] 重新构建 Go 核心二进制 (bin/medit, bin/medit-mcp)...")
    ok, out, err = run_cmd(["make", "build"])
    build_ok = ok
    build_detail = ""
    if ok:
        log("  ✓ bin/medit, bin/medit-mcp 构建成功")
    else:
        lines = [ln.strip() for ln in (out + "\n" + err).splitlines() if ln.strip()]
        build_detail = lines[-1] if lines else "(无输出)"
        log(f"  ✗ 构建失败: {build_detail}")

    # 3. 运行 Python 单元测试验证
    log("[auto_sync] 验证 Python 核心算法健康状态...")
    test_script = REPO_DIR / "scripts" / "hl_v3_final" / "test_hl_lib.py"
    if test_script.exists():
        ok, _, err = run_cmd([sys.executable, str(test_script)])
        if ok:
            log("  ✓ 核心单元测试全部通过")
        else:
            log(f"  ⚠️ 测试提示: {err}")

    # 3b. 仓库卫生不变量: 技能分发包不得携带过期的高亮工具链; 命令不得重复注册。
    #     这两类问题都不会让任何东西报错, 只会静默退化 (2026-09-11 实测: 手工同步漏了 6 个
    #     文件, 分发包带着旧版工具链跑了 4 天无人发现), 所以放进每 6 小时的巡检里。
    log("[auto_sync] 校验仓库卫生不变量 (工具链镜像一致 + 命令注册无重复)...")
    hyg_ok, hyg_out, hyg_err = run_cmd(
        [sys.executable, "-m", "unittest", "tests.test_repo_hygiene"]
    )
    if hyg_ok:
        log("  ✓ 仓库卫生不变量通过")
    else:
        hyg_lines = [ln.strip() for ln in (hyg_err or hyg_out).splitlines() if ln.strip()]
        hyg_detail = hyg_lines[-1] if hyg_lines else "(无输出)"
        log(f"  ⚠️ 仓库卫生不变量失败: {hyg_detail}")
        notify(
            "定时同步巡检: 仓库卫生不变量失败",
            [
                f"**仓库**：`{REPO_DIR}`",
                f"**失败摘要**：`{hyg_detail}`",
                "**常见原因**：只改了 `scripts/hl_v3_final/` 而没同步技能分发包 —— "
                "技能会带着旧代码被分发出去。",
                "**修法**：`python3 scripts/sync_skill_bundle.py` "
                "(若是命令重复注册, 按测试提示定位 `rootCmd.AddCommand`)。",
            ],
            key="autosync-hygiene-failed",
            level="warning",
        )

    # 4. 结论: 只有「构建没成功」才算部署未更新; 拉取问题单独表述, 不掩盖也不冒领
    if not build_ok:
        log("[auto_sync] ✗ 同步未完成: Go 二进制构建失败, 本地部署仍停留在旧版本。")
        log("         排查: 确认 go / make 在 PATH 中 (launchd 默认 PATH 不含 Homebrew),")
        log("         或在仓库根目录手工执行 make build 复现。")
        notify(
            "auto_sync 构建失败",
            [
                f"**仓库**：`{REPO_DIR}`",
                f"**失败摘要**：`{build_detail or '(无输出)'}`",
                f"**代码同步**：{_PULL_STATE_TEXT.get(pull_state, pull_state)}",
                "**影响**：本地部署的 Go 二进制仍停留在旧版本，定时同步实际未生效。",
                "**排查**：确认 `go` / `make` 在 PATH 中；或在仓库根手工执行 `make build` 复现。",
            ],
            key="autosync-build-failed",
            level="critical",
        )
        return False, pull_state

    if pull_state == "ok":
        log("[auto_sync] ✅ 本地部署已更新 (代码已同步 + 二进制已重建)。")
    elif pull_state == "skipped_dirty":
        log("[auto_sync] ✅ 二进制已从当前工作区重建; 代码未同步 (工作区有未提交改动)。")
    else:
        log("[auto_sync] ⚠️ 二进制已重建, 但代码未同步 (本次拉取失败, 下个周期重试)。")
        notify(
            "auto_sync 代码未同步",
            [
                f"**仓库**：`{REPO_DIR}`",
                f"**失败摘要**：`{pull_detail or '(无输出)'}`",
                f"**已重试**：{pull_attempts} 次",
                "**判读**：疑似网络 / 代理 (Clash) 抖动，属暂时性故障。",
                "**影响**：二进制已按本地工作区重建；代码落后于远端。下个周期会自动重试拉取。",
            ],
            key="autosync-pull-failed",
            level="warning",
        )
    return True, pull_state


def install_cron(interval_hours=6):
    """注册 crontab 周期拉取 (macOS / Linux)"""
    script_path = os.path.abspath(__file__)
    python_path = sys.executable
    cron_job = (f"0 */{interval_hours} * * * {python_path} {script_path} --pull "
                f">> {LOG_FILE} 2>&1")

    ok, current_cron, _ = run_cmd(["crontab", "-l"])
    current_cron = current_cron if ok else ""

    if script_path in current_cron:
        log("[auto_sync] Crontab 定时任务已存在，无需重复添加。")
        return True

    new_cron = (current_cron.strip() + "\n" + cron_job + "\n").lstrip()
    proc = subprocess.Popen(["crontab", "-"], stdin=subprocess.PIPE, text=True)
    proc.communicate(input=new_cron)
    if proc.returncode == 0:
        log(f"[auto_sync] ✓ 成功注册 Crontab 定时同步任务 (每 {interval_hours} 小时执行一次)")
        return True
    else:
        log("[auto_sync] ✗ 注册 Crontab 失败")
        return False


def install_launchd(interval_hours=6):
    """注册 macOS LaunchAgent 守护任务"""
    if sys.platform != "darwin":
        log("[auto_sync] LaunchAgent 仅支持 macOS。")
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
        <string>{escape(python_path)}</string>
        <string>{escape(script_path)}</string>
        <string>--pull</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{escape(launchd_path())}</string>
        <key>HOME</key>
        <string>{escape(str(Path.home()))}</string>
    </dict>
    <key>StartInterval</key>
    <integer>{interval_seconds}</integer>
    <!-- 与脚本自身的写日志目标是同一个文件: 脚本写业务日志, launchd 兜住未捕获的 traceback。
         两边指向同一路径不会重复 —— 脚本只在非终端 (即此处) 模式下不 print。 -->
    <key>StandardOutPath</key>
    <string>{escape(str(LOG_FILE))}</string>
    <key>StandardErrorPath</key>
    <string>{escape(str(LOG_FILE))}</string>
</dict>
</plist>
"""
    with open(plist_path, "w", encoding="utf-8") as f:
        f.write(plist_content)
        
    run_cmd(["launchctl", "unload", str(plist_path)])
    ok, _, err = run_cmd(["launchctl", "load", str(plist_path)])
    if ok:
        log(f"[auto_sync] ✓ 成功安装并启动 macOS LaunchAgent ({plist_path})，每 {interval_hours} 小时自动同步")
        return True
    else:
        log(f"[auto_sync] ⚠️ 加载 LaunchAgent 提示: {err}")
        return False


def run_daemon(interval_minutes=360):
    """前台守护循环模式"""
    log(f"[auto_sync] 启动自动同步守护进程 (轮询周期: {interval_minutes} 分钟)...")
    while True:
        try:
            has_updates, _ = check_updates()
            if has_updates:
                pull_and_rebuild()
        except Exception as e:
            log(f"[auto_sync] 轮询周期发生异常: {e}")
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
    if not (has_updates or args.pull):
        return

    updated, pull_state = pull_and_rebuild()

    if not updated:
        # 退出码 1 = 构建失败, 部署确实没更新。此前这种情况会照打 ✅ 并退出 0,
        # 故障因此静默了数周 —— 退出码必须如实反映。
        sys.exit(1)

    if pull_state == "failed":
        # 退出码 2 = 二进制已重建, 但代码没同步 (暂时性网络/代理故障)。
        # 与"构建失败"分开, 便于从 launchctl 的退出码一眼判断要不要管。
        sys.exit(2)


if __name__ == "__main__":
    main()
