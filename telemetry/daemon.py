"""Background proactive daemon and scheduler engine for via54Medit telemetry."""

import os
import sys
import time
import json
import signal
import subprocess
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .aggregator import TelemetryAggregator
from .config import load_config, WEEKDAY_NAMES
from .db import TelemetryDB
from .feishu_sync import FeishuSyncClient
from .platform_paths import desktop_dir, trae_work_exe, windows_startup_dir
from .watcher import WorkspaceScanner

PID_FILE = os.path.expanduser(r"~/.medit/daemon.pid")
HEARTBEAT_FILE = os.path.expanduser(r"~/.medit/daemon_heartbeat.json")
LOG_FILE = os.path.expanduser(r"~/.medit/daemon.log")


def is_pid_running(pid: int) -> bool:
    """检查 PID 是否在运行。"""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            # Windows 平台通过 tasklist 或 OpenProcess 校验
            out = subprocess.check_output(f'tasklist /FI "PID eq {pid}" /NH', shell=True).decode("utf-8", errors="ignore")
            return str(pid) in out
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


class TelemetryDaemon:
    def __init__(self):
        self.db = TelemetryDB()
        self.aggregator = TelemetryAggregator(self.db)
        self.scanner = WorkspaceScanner(self.db)
        self.last_weekly_sent = ""
        self.last_monthly_sent = ""
        self.last_scan_time = 0.0

    def log(self, message: str):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{now_str}] [TelemetryDaemon] {message}"
        print(line)
        try:
            os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def run_cycle(self):
        """执行单次循环：1. 产出物主动嗅探；2. 定时排程检查。"""
        cfg = load_config()
        now = datetime.now()

        # 1. 产出物主动嗅探 (每 poll_interval_seconds 执行一次)
        poll_int = cfg.get("watcher", {}).get("poll_interval_seconds", 30)
        if time.time() - self.last_scan_time >= poll_int:
            self.last_scan_time = time.time()
            watch_dirs = cfg.get("watcher", {}).get("watch_dirs", [])
            for wdir in watch_dirs:
                if os.path.exists(wdir):
                    try:
                        # 扫描顶层各项目目录
                        for entry in os.listdir(wdir):
                            full_p = os.path.join(wdir, entry)
                            if os.path.isdir(full_p):
                                self.scanner.scan_project(full_p, entry)
                    except Exception as e:
                        self.log(f"扫描目录 {wdir} 异常: {e}")

        # 2. 定时排程检查
        self._check_schedule(cfg, now)

        # 3. 刷新心跳
        self._update_heartbeat(cfg, now)

    def _check_schedule(self, cfg: Dict[str, Any], now: datetime):
        time_str = now.strftime("%H:%M")
        today_str = now.strftime("%Y-%m-%d")
        month_str = now.strftime("%Y-%m")

        # --- A. 周报排程 ---
        weekly_cfg = cfg.get("schedule", {}).get("weekly", {})
        if weekly_cfg.get("enabled", True):
            target_weekday = weekly_cfg.get("day_of_week", 0)  # 0=Monday
            target_time = weekly_cfg.get("time", "09:00")
            if now.weekday() == target_weekday and time_str == target_time:
                if self.last_weekly_sent != today_str:
                    self.last_weekly_sent = today_str
                    self.log(f"⏰ 命中周报推送时间 ({WEEKDAY_NAMES[target_weekday]} {target_time})，启动自动推送与公共表同步...")
                    try:
                        rep = self.aggregator.get_weekly_report()
                        client = FeishuSyncClient()
                        ok_push, msg_push = client.push_to_user_chat(rep)
                        self.db.record_sync_log("feishu_card_weekly", client.user_open_id, "success" if ok_push else "failed", msg_push)
                        self.log(f"  • 飞书卡片直推: {msg_push}")

                        ok_sync, msg_sync = client.sync_to_public_sheet(rep)
                        self.db.record_sync_log("feishu_sheet_weekly", client.sheet_token or "default", "success" if ok_sync else "failed", msg_sync)
                        self.log(f"  • 公共表格同步: {msg_sync}")

                        from .bitable_sync import FeishuBitableManager
                        bmgr = FeishuBitableManager()
                        ok_b, msg_b = bmgr.sync_weekly_report(rep)
                        self.db.record_sync_log("feishu_bitable_weekly", bmgr.app_token or "local_csv", "success" if ok_b else "failed", msg_b)
                        self.log(f"  • 多维表格同步: {msg_b}")
                    except Exception as e:
                        self.log(f"  ❌ 周报自动推送异常: {e}")

        # --- B. 月报排程 ---
        monthly_cfg = cfg.get("schedule", {}).get("monthly", {})
        if monthly_cfg.get("enabled", True):
            target_day = monthly_cfg.get("day_of_month", 1)
            target_time = monthly_cfg.get("time", "09:00")

            is_month_trigger = False
            if target_day == -1:
                # 判断是否是月末最后一天
                tomorrow = now + timedelta(days=1)
                if tomorrow.month != now.month:
                    is_month_trigger = True
            elif now.day == target_day:
                is_month_trigger = True

            if is_month_trigger and time_str == target_time:
                if self.last_monthly_sent != month_str:
                    self.last_monthly_sent = month_str
                    self.log(f"⏰ 命中月报推送时间 ({target_day}日 {target_time})，启动包含历史全量战报的月报推送...")
                    try:
                        rep = self.aggregator.get_monthly_report()
                        client = FeishuSyncClient()
                        ok_push, msg_push = client.push_to_user_chat(rep)
                        self.db.record_sync_log("feishu_card_monthly", client.user_open_id, "success" if ok_push else "failed", msg_push)
                        self.log(f"  • 飞书月报卡片直推: {msg_push}")

                        ok_sync, msg_sync = client.sync_to_public_sheet(rep)
                        self.db.record_sync_log("feishu_sheet_monthly", client.sheet_token or "default", "success" if ok_sync else "failed", msg_sync)
                        self.log(f"  • 公共表格月报同步: {msg_sync}")

                        from .bitable_sync import FeishuBitableManager
                        bmgr = FeishuBitableManager()
                        ok_b, msg_b = bmgr.sync_weekly_report(rep)
                        self.db.record_sync_log("feishu_bitable_monthly", bmgr.app_token or "local_csv", "success" if ok_b else "failed", msg_b)
                        self.log(f"  • 多维表格月报同步: {msg_b}")
                    except Exception as e:
                        self.log(f"  ❌ 月报自动推送异常: {e}")

    def _update_heartbeat(self, cfg: Dict[str, Any], now: datetime):
        hb = {
            "pid": os.getpid(),
            "last_tick": now.strftime("%Y-%m-%d %H:%M:%S"),
            "weekly_schedule": f"{WEEKDAY_NAMES[cfg['schedule']['weekly']['day_of_week']]} {cfg['schedule']['weekly']['time']}",
            "monthly_schedule": f"每月{cfg['schedule']['monthly']['day_of_month']}日 {cfg['schedule']['monthly']['time']}",
            "user": cfg["user"]["nickname"],
            "open_id": cfg["user"]["open_id"],
        }
        try:
            with open(HEARTBEAT_FILE, "w", encoding="utf-8") as f:
                json.dump(hb, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def start_loop(self):
        """进入常驻事件循环。"""
        self.log(f"服务启动就绪 (PID: {os.getpid()})。主动监控已开启，随时待命。")
        try:
            while True:
                self.run_cycle()
                time.sleep(5)  # 5秒滴答
        except KeyboardInterrupt:
            self.log("收到中断信号，服务正常退出。")
        except Exception as e:
            self.log(f"守护主循环严重异常: {e}")


def start_daemon_process(foreground: bool = False):
    """启动守护进程。"""
    if foreground:
        # 前台/子进程直接运行主循环
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        daemon = TelemetryDaemon()
        daemon.start_loop()
        return

    # 后台启动检查
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r", encoding="utf-8") as f:
                old_pid = int(f.read().strip())
                if is_pid_running(old_pid) and old_pid != os.getpid():
                    print(f"[Daemon] 守护进程已在运行中 (PID: {old_pid})，无需重复启动。")
                    return
        except Exception:
            pass

    # 后台生成新进程
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cmd = [sys.executable, "-m", "telemetry.cli", "daemon", "--foreground"]
    creationflags = 0
    if sys.platform == "win32":
        # DETACHED_PROCESS 或 CREATE_NO_WINDOW
        creationflags = 0x00000008 | 0x08000000

    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    log_fp = open(LOG_FILE, "a", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONPATH"] = project_root + os.pathsep + env.get("PYTHONPATH", "")

    proc = subprocess.Popen(
        cmd,
        cwd=project_root,
        env=env,
        stdout=log_fp,
        stderr=log_fp,
        creationflags=creationflags,
        close_fds=True
    )
    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(proc.pid))
    print(f"[Daemon] 主动监控守护进程已在后台成功启动 (PID: {proc.pid})。")
    print(f"  • 工作目录: {project_root}")
    print(f"  • 日志文件: {LOG_FILE}")
    print(f"  • 状态查询: python -m telemetry.cli daemon --status")


def stop_daemon_process():
    """停止守护进程。"""
    if not os.path.exists(PID_FILE):
        print("[Daemon] 未找到运行中的守护进程 PID 文件。")
        return

    try:
        with open(PID_FILE, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
    except Exception:
        print("[Daemon] 读取 PID 文件损坏。")
        return

    if is_pid_running(pid):
        try:
            if sys.platform == "win32":
                subprocess.run(f"taskkill /PID {pid} /F", shell=True, check=False)
            else:
                os.kill(pid, signal.SIGTERM)
            print(f"[Daemon] 守护进程 (PID: {pid}) 已成功终止。")
        except Exception as e:
            print(f"[Daemon] 终止进程异常: {e}")
    else:
        print(f"[Daemon] 进程 (PID: {pid}) 已不存在。")

    try:
        os.remove(PID_FILE)
    except Exception:
        pass


def get_daemon_status() -> Dict[str, Any]:
    """查询守护进程状态。"""
    status = {"running": False, "pid": None, "details": {}}
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
                if is_pid_running(pid):
                    status["running"] = True
                    status["pid"] = pid
        except Exception:
            pass

    if os.path.exists(HEARTBEAT_FILE):
        try:
            with open(HEARTBEAT_FILE, "r", encoding="utf-8") as f:
                status["details"] = json.load(f)
        except Exception:
            pass
    return status


def get_startup_vbs_path() -> Optional[str]:
    """Windows 开机启动脚本路径；非 Windows 平台返回 None。"""
    startup_dir = windows_startup_dir()
    if not startup_dir:
        return None
    return os.path.join(startup_dir, "traework_telemetry_silent.vbs")


def install_startup_vbs():
    """将守护服务注册到 Windows 开机启动文件夹 (Startup)，电脑重启/登录后后台静默自启。"""
    vbs_path = get_startup_vbs_path()
    if not vbs_path:
        print("[Autostart] 跳过: 开机自启脚本仅支持 Windows 系统。")
        return
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    py_exe = sys.executable

    vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "{project_root}"
WshShell.Run """{py_exe}"" -m telemetry.cli daemon --start", 0, False
'''
    try:
        os.makedirs(os.path.dirname(vbs_path), exist_ok=True)
        with open(vbs_path, "w", encoding="gbk") as f:
            f.write(vbs_content)
        print(f"[Autostart] 成功注册开机自启静默脚本:")
        print(f"  • 文件路径: {vbs_path}")
        print(f"  • 效果: 电脑重启或登录系统后，监控守护服务将在后台自动无窗口静默启动。")
    except Exception as e:
        print(f"[Autostart] 注册开机自启异常: {e}")


def uninstall_startup_vbs():
    """移除 Windows 开机自启静默脚本。"""
    vbs_path = get_startup_vbs_path()
    if not vbs_path:
        print("[Autostart] 跳过: 开机自启脚本仅支持 Windows 系统。")
        return
    if os.path.exists(vbs_path):
        try:
            os.remove(vbs_path)
            print(f"[Autostart] 已成功移除开机自启脚本: {vbs_path}")
        except Exception as e:
            print(f"[Autostart] 移除异常: {e}")
    else:
        print(f"[Autostart] 未检测到开机自启脚本。")


def install_traework_companion_launcher():
    """生成桌面 TraeWork 伴生启动器：点击 TraeWork 时，自动连带启动 Telemetry 守护服务。"""
    trae_exe = trae_work_exe()
    if not trae_exe:
        print("[Companion] 跳过: 桌面伴随启动器仅支持 Windows 系统。")
        return
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    py_exe = sys.executable
    launcher_path = os.path.join(desktop_dir(), "启动 TraeWork (带自动监控).vbs")
    vbs_content = f'''Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "{project_root}"
' Step 1: Start Telemetry background daemon silently (skips if already active)
WshShell.Run """{py_exe}"" -m telemetry.cli daemon --start", 0, False
' Step 2: Launch TraeWork UI
WshShell.Run """{trae_exe}""", 1, False
'''
    try:
        with open(launcher_path, "w", encoding="gbk") as f:
            f.write(vbs_content)
        print(f"[Companion] 成功生成 TraeWork 伴随启动器:")
        print(f"  • 桌面启动器: {launcher_path}")
        print(f"  • 效果: 点击此桌面脚本即可同时启动 TraeWork 与 Telemetry 监控守护服务。")
    except Exception as e:
        print(f"[Companion] 创建伴随启动器异常: {e}")


LAUNCHD_LABEL = "com.via54medit.telemetry"


def get_launchd_plist_path() -> Optional[str]:
    """macOS LaunchAgent plist 路径; 非 macOS 返回 None。"""
    if sys.platform != "darwin":
        return None
    return os.path.expanduser(f"~/Library/LaunchAgents/{LAUNCHD_LABEL}.plist")


def _launchd_domain() -> str:
    return f"gui/{os.getuid()}"


def _launchctl(*args: str) -> bool:
    """执行 launchctl 子命令, 返回是否成功。"""
    try:
        res = subprocess.run(["launchctl", *args], capture_output=True, text=True)
        return res.returncode == 0
    except Exception:
        return False


def get_launchd_status() -> Optional[bool]:
    """LaunchAgent 是否已加载; 非 macOS 返回 None。"""
    if sys.platform != "darwin":
        return None
    try:
        res = subprocess.run(
            ["launchctl", "print", f"{_launchd_domain()}/{LAUNCHD_LABEL}"],
            capture_output=True, text=True,
        )
        return res.returncode == 0
    except Exception:
        return False


def install_launchd_agent():
    """把守护服务注册为 macOS LaunchAgent: 登录后自动后台常驻 (KeepAlive)。"""
    plist_path = get_launchd_plist_path()
    if not plist_path:
        print("[Autostart] 跳过: LaunchAgent 仅支持 macOS。")
        return

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    py_exe = sys.executable
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    plist = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LAUNCHD_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{py_exe}</string>
        <string>-m</string>
        <string>telemetry.cli</string>
        <string>daemon</string>
        <string>--foreground</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{project_root}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>{project_root}</string>
        <key>HOME</key>
        <string>{os.path.expanduser("~")}</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{LOG_FILE}</string>
    <key>StandardErrorPath</key>
    <string>{LOG_FILE}</string>
</dict>
</plist>
'''
    try:
        # 先卸载旧实例并停掉手工启动的游离进程, 避免双跑/重复加载
        _launchctl("bootout", f"{_launchd_domain()}/{LAUNCHD_LABEL}")
        stop_daemon_process()

        os.makedirs(os.path.dirname(plist_path), exist_ok=True)
        with open(plist_path, "w", encoding="utf-8") as f:
            f.write(plist)

        ok = (_launchctl("bootstrap", _launchd_domain(), plist_path)
              or _launchctl("load", "-w", plist_path))
        if ok:
            print("[Autostart] 已注册 macOS 开机自启 LaunchAgent:")
            print(f"  • plist: {plist_path}")
            print("  • 效果: 登录后守护服务自动后台常驻, 异常退出也会被拉起。")
        else:
            print(f"[Autostart] plist 已写入但 launchctl 加载失败; 可手动执行: launchctl load -w {plist_path}")
    except Exception as e:
        print(f"[Autostart] 注册 LaunchAgent 异常: {e}")


def uninstall_launchd_agent():
    """移除 macOS LaunchAgent。"""
    plist_path = get_launchd_plist_path()
    if not plist_path:
        print("[Autostart] 跳过: LaunchAgent 仅支持 macOS。")
        return

    if not (_launchctl("bootout", f"{_launchd_domain()}/{LAUNCHD_LABEL}")
            or _launchctl("unload", "-w", plist_path)):
        print("[Autostart] launchctl 卸载未成功 (可能本就未加载)。")

    if os.path.exists(plist_path):
        try:
            os.remove(plist_path)
            print(f"[Autostart] 已移除 LaunchAgent: {plist_path}")
        except Exception as e:
            print(f"[Autostart] 移除异常: {e}")
    else:
        print("[Autostart] 未检测到 LaunchAgent plist。")


def install_windows_startup_task():
    """将守护进程注册为 Windows 开机计划任务。"""
    if sys.platform != "win32":
        print("[Task] 该功能仅支持 Windows 系统。")
        return

    py_exe = sys.executable
    args = f'-m telemetry.cli daemon --foreground'
    task_name = "TraeWorkTelemetryDaemon"
    cmd = f'schtasks /create /tn "{task_name}" /tr "\"{py_exe}\" {args}" /sc onlogon /rl highest /f'
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            print(f"[Task] 成功注册 Windows 开机自启计划任务: {task_name}")
        else:
            print(f"[Task] 注册失败: {res.stderr}")
    except Exception as e:
        print(f"[Task] 注册异常: {e}")
