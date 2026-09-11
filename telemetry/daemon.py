"""Background proactive daemon and scheduler engine for via54Medit telemetry."""

import os
import shutil
import sys
import time
import json
import signal
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

from .aggregator import TelemetryAggregator
from .config import (
    DEFAULT_MONTHLY_SCHEDULE,
    DEFAULT_WEEKLY_SCHEDULE,
    WEEKDAY_NAMES,
    load_config,
)
from .db import TelemetryDB
from .feishu_sync import FeishuSyncClient
from .platform_paths import desktop_dir, trae_work_exe, windows_startup_dir
from .watcher import WorkspaceScanner

PID_FILE = os.path.expanduser(r"~/.medit/daemon.pid")
HEARTBEAT_FILE = os.path.expanduser(r"~/.medit/daemon_heartbeat.json")
LOG_FILE = os.path.expanduser(r"~/.medit/daemon.log")

# 日志上限与备份文件: 超过上限时留一份 .1 再就地清空 (见 rotate_log_if_needed)。
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_FILE = LOG_FILE + ".1"

# 同一条消息累计重复多少次才补一条汇总 (其余重复一律不再落盘)。
REPEAT_SUMMARY_EVERY = 100

# 文件描述符占用达到软上限的这个比例即告警。
FD_WARN_RATIO = 0.8

# LaunchAgent 为守护进程申请的文件描述符软上限。
LAUNCHD_MAX_OPEN_FILES = 4096


def rotate_log_if_needed():
    """日志超过上限时保留一份 .1 备份并就地清空。

    刻意用「复制 + 截断」而不是「改名 + 新建」: launchd 的 StandardOutPath 只在启动时
    打开文件一次并长期持有该 fd, 改名会让它继续写进旧 inode (也就是备份文件), 而本进程
    按路径写的是新文件 —— 两边就此分叉。截断保持同一个 inode, 双方都继续落在 daemon.log。
    """
    try:
        if os.path.getsize(LOG_FILE) <= LOG_MAX_BYTES:
            return
    except OSError:
        return
    try:
        shutil.copy2(LOG_FILE, LOG_BACKUP_FILE)
        with open(LOG_FILE, "w", encoding="utf-8"):
            pass
    except Exception:
        pass


def fd_usage() -> Optional[Tuple[int, int]]:
    """返回当前进程的 (已用文件描述符, 软上限); 无法确定的部分为 None。

    "资源耗尽但不崩溃"这类故障 (进程假死, KeepAlive 无从感知) 只能靠主动观测提前暴露。
    """
    used = None
    for fd_dir in ("/dev/fd", "/proc/self/fd"):
        try:
            used = len(os.listdir(fd_dir))
            break
        except OSError:
            continue
    if used is None:
        return None

    soft = None
    try:
        import resource

        limit = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
        if limit != resource.RLIM_INFINITY and limit > 0:
            soft = int(limit)
    except Exception:
        pass
    return used, soft


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
        # 已处理过的"别关机提醒"幂等 key (按提醒日分桶)。跨重启的幂等由 alerter
        # 落盘的状态保证, 这里只是避免同一天里每 5 秒反复走一遍判断。
        self._last_reminder_key = ""
        self.last_scan_time = 0.0
        # Go 侧 LLM 用量 spool 的上次摄入时刻
        self.last_spool_time = 0.0
        # 重复消息限流状态 (见 log)
        self._last_msg = ""
        self._repeat = 0
        # 最近一次观测到的描述符占用, 供心跳与 daemon --status 展示
        self.last_fd: Optional[Dict[str, Any]] = None

    def _write(self, line: str):
        """落盘一行日志 (含轮转)。

        stdout 与文件写的是同一份内容: 守护进程由 launchd 拉起时 stdout 也重定向到
        LOG_FILE, 若只限流其中一边, 另一边照样会把日志刷爆。
        """
        print(line)
        try:
            os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
            rotate_log_if_needed()
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def log(self, message: str):
        """写日志, 并对连续重复的消息限流。

        同一句错误在 5 秒滴答的循环里会原地刷屏 —— 现场曾因此把日志刷到 2 MB 且几乎全是
        同一条 EMFILE, 既快速膨胀日志又淹没有效信息。这里只在"换消息时"补一条累计次数
        汇总, 并在重复途中每隔 REPEAT_SUMMARY_EVERY 次补一条进行中汇总。
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if message == self._last_msg:
            self._repeat += 1
            if self._repeat % REPEAT_SUMMARY_EVERY == 0:
                self._write(
                    f"[{now_str}] [TelemetryDaemon] ↑ 上一条消息已重复 {self._repeat} 次: {message}"
                )
            return

        if self._repeat:
            self._write(
                f"[{now_str}] [TelemetryDaemon] ↑ 上一条消息共重复 {self._repeat} 次: {self._last_msg}"
            )
        self._last_msg = message
        self._repeat = 0
        self._write(f"[{now_str}] [TelemetryDaemon] {message}")

    def _check_fd_health(self):
        """观测文件描述符占用, 逼近软上限时告警。

        告警文案按 10% 分档而不是带精确数字 —— 否则每次占用量变化都会被当成"新消息",
        绕开上面的限流, 又变回刷屏。精确数字放在心跳文件与 `daemon --status` 里。
        """
        info = fd_usage()
        if not info:
            return
        used, soft = info
        self.last_fd = {"used": used, "limit": soft}
        if not soft or used < soft * FD_WARN_RATIO:
            return
        bucket = min(used * 100 // soft, 100) // 10 * 10
        self.log(
            f"文件描述符吃紧: 已达软上限的约 {bucket}% (疑似句柄泄漏), "
            f"详情见心跳文件中的 fd 占用"
        )
        # 同时推到外部告警通道。key 按 10% 分档, 于是 80/90/100 各告警一次,
        # 既随占用升高逐步升级, 又不会每 5 秒刷一条。
        from .alerter import send_alert

        send_alert(
            "守护进程文件描述符吃紧",
            [
                f"**占用**：`{used}/{soft}` (约 {bucket}%)",
                "**判读**：疑似句柄泄漏。该故障不会让进程退出, KeepAlive 无从感知, "
                "持续下去会导致目录扫描与配置读取全面失败。",
                "**排查**：`medit-telemetry daemon --status` 可查实时占用; "
                "日志见 `~/.medit/daemon.log`。",
            ],
            key=f"fd-{bucket}",
            level="critical" if bucket >= 90 else "warning",
        )

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
                        from .watcher import is_ignored_path

                        for entry in os.listdir(wdir):
                            full_p = os.path.join(wdir, entry)
                            # 备份/临时目录(`_bak*` 等)不是产出物 —— 扫进去会让同一篇文献
                            # 被重复计数(实测过 3 倍虚高)。
                            if os.path.isdir(full_p) and not is_ignored_path(full_p):
                                self.scanner.scan_project(full_p, entry)
                    except Exception as e:
                        self.log(f"扫描目录 {wdir} 异常: {e}")

        # 2. 摄入 Go 侧 LLM 用量 spool
        #    Go 没有 SQLite 驱动(见 internal/foundation/llm_usage.go), 用量先落盘到
        #    JSONL 再由这里摄入。不做这一步的话, medit ask / medplan / docproc 的
        #    token 会永远停在 spool 里进不了报表 —— 而调用本身一切正常, 不报任何错。
        self._drain_llm_spool(cfg)

        # 3. 定时排程检查
        self._check_schedule(cfg, now)

        # 4. 描述符占用观测 (资源耗尽型故障的唯一抓手)
        self._check_fd_health()

        # 5. 刷新心跳
        self._update_heartbeat(cfg, now)

    def _drain_llm_spool(self, cfg: Dict[str, Any]):
        """按间隔把 Go 侧 spool 摄入 telemetry.db。只在真的导入/出错时写日志。"""
        interval = cfg.get("telemetry", {}).get("llm_spool_interval_seconds", 60)
        if time.time() - getattr(self, "last_spool_time", 0.0) < interval:
            return
        self.last_spool_time = time.time()
        try:
            from .llm_spool import ingest

            res = ingest()
            if res.get("imported"):
                self.log("LLM 用量 spool 摄入: 导入 %d 行(重复跳过 %d)"
                         % (res["imported"], res.get("duplicated", 0)))
            if res.get("invalid"):
                self.log("LLM 用量 spool 有 %d 行无法解析: %s"
                         % (res["invalid"], "; ".join(res.get("problems") or [])[:200]))
        except Exception as e:                              # noqa: BLE001
            # 记账是旁路, 绝不能把守护进程搞挂
            self.log("LLM 用量 spool 摄入异常: %s" % e)

    def _check_schedule(self, cfg: Dict[str, Any], now: datetime):
        today_str = now.strftime("%Y-%m-%d")
        month_str = now.strftime("%Y-%m")

        # 触发条件一律走 schedule 模块 —— 那里是"遇周末/法定节假日顺延到下一个工作日"
        # 的唯一实现, 提醒模块用的是同一份, 因此"提醒哪一天"与"实际哪一天推"不会分叉。
        from .schedule import push_due_now

        # --- A. 周报排程 ---
        weekly_cfg = cfg.get("schedule", {}).get("weekly", {})
        if weekly_cfg.get("enabled", True):
            target_weekday = weekly_cfg.get("day_of_week", 0)  # 0=Monday
            target_time = weekly_cfg.get("time", DEFAULT_WEEKLY_SCHEDULE["time"])
            due, why = push_due_now(cfg, now, "weekly")
            if due:
                if self.last_weekly_sent != today_str:
                    self.last_weekly_sent = today_str
                    if why:
                        self.log(f"⏰ {why}")
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
            target_time = monthly_cfg.get("time", DEFAULT_MONTHLY_SCHEDULE["time"])

            # "是不是今天触发"以及"月末(-1)"与"顺延"都在 schedule.push_due_now 里,
            # 这里不再自己算日期 —— 之前那段 is_month_trigger 与提醒模块各算一遍, 正是
            # 顺延功能一上线就会分叉的地方。
            due_m, why_m = push_due_now(cfg, now, "monthly")
            if due_m:
                if self.last_monthly_sent != month_str:
                    self.last_monthly_sent = month_str
                    if why_m:
                        self.log(f"⏰ {why_m}")
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

        # --- C. 推送日的前一个工作日提醒 ("别关机") ---
        self._check_reminder(cfg, now)

    def _check_reminder(self, cfg: Dict[str, Any], now: datetime):
        """在推送日的**前一个工作日**提醒用户别关机。

        为什么需要: 推送是到点触发的 —— 机器关机或休眠, 那一次周报/月报就静默丢失,
        不报错也不补发。提前提醒是唯一能在事前降低这种概率的手段。

        "前一个工作日"必须查法定节假日安排(春节连休、国庆调休都会让简单加减一天失效),
        见 reminders / holidays 两个模块。

        本方法只为记录**进程内**幂等 key; 跨重启的幂等由 alerter 落盘的状态保证,
        因此守护进程被反复拉起也不会重复打扰。
        """
        try:
            from .reminders import due_reminders, reminder_key, send_due

            items = due_reminders(cfg, now)
            if not items:
                return
            key = reminder_key(items[0]["remind_date"])
            if key == self._last_reminder_key:
                return                      # 本进程今天已经处理过, 不必再走一遍发送判断
            result = send_due(cfg, now, logger=self.log)
            if result:
                self._last_reminder_key = result[2]
        except Exception as e:                              # noqa: BLE001
            # 提醒失败绝不能影响守护进程本身 —— 它是"锦上添花", 不是主链路。
            self.log(f"提醒检查异常(已忽略): {e}")

    def _update_heartbeat(self, cfg: Dict[str, Any], now: datetime):
        weekly = (cfg.get("schedule") or {}).get("weekly") or {}
        monthly = (cfg.get("schedule") or {}).get("monthly") or {}
        try:
            widx = int(weekly.get("day_of_week", DEFAULT_WEEKLY_SCHEDULE["day_of_week"]))
        except (TypeError, ValueError):
            widx = DEFAULT_WEEKLY_SCHEDULE["day_of_week"]
        # 下次推送时刻与提醒设置也写进心跳: 推送是到点触发的, "下次什么时候推"
        # 是排查"为什么这次没推"时的第一个问题, 不该只能靠读配置去猜。
        next_at: Dict[str, str] = {}
        try:
            from .reminders import reminder_settings, upcoming_pushes

            for kind, when in upcoming_pushes(cfg, now):
                next_at[kind] = when.strftime("%Y-%m-%d %H:%M")
            rconf = reminder_settings(cfg)
        except Exception:                                   # noqa: BLE001
            rconf = {"enabled": False, "time": ""}
        # 实时性证据也写进心跳: "数据是不是最新的"要有可查的凭据, 而不是靠感觉。
        # 取明细表的最近入库时间 + 各表行数 —— 这两项能直接回答"统计有没有跟上"。
        freshness: Dict[str, Any] = {}
        try:
            freshness["latest_ingest_at"] = self.db.latest_ingest_at() or ""
            freshness["counts"] = self.db.table_counts()
        except Exception:                                   # noqa: BLE001
            pass
        # LLM 用量 spool 的积压量也进心跳: "待摄入一直不为 0" 就是摄入挂了或
        # 两端字段约定漂了的第一信号, 不该等到月底对账才发现。
        try:
            from .llm_spool import spool_status

            st = spool_status()
            freshness["llm_spool"] = {
                "pending": st.get("pending", 0),
                "last_write": st.get("mtime", ""),
            }
        except Exception:                                   # noqa: BLE001
            pass
        hb = {
            "pid": os.getpid(),
            "last_tick": now.strftime("%Y-%m-%d %H:%M:%S"),
            "weekly_schedule": "%s %s" % (
                WEEKDAY_NAMES[widx] if 0 <= widx < len(WEEKDAY_NAMES) else "?",
                weekly.get("time", DEFAULT_WEEKLY_SCHEDULE["time"])),
            "monthly_schedule": "每月%s日 %s" % (
                monthly.get("day_of_month", DEFAULT_MONTHLY_SCHEDULE["day_of_month"]),
                monthly.get("time", DEFAULT_MONTHLY_SCHEDULE["time"])),
            "next_weekly": next_at.get("weekly", ""),
            "next_monthly": next_at.get("monthly", ""),
            "reminder": {"enabled": rconf.get("enabled", False), "time": rconf.get("time", "")},
            "freshness": freshness,
            "user": cfg["user"]["nickname"],
            "open_id": cfg["user"]["open_id"],
            "fd": self.last_fd,
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
    with open(LOG_FILE, "a", encoding="utf-8") as log_fp:
        # 不传 env: 子进程继承当前环境。
        # 此处曾遗留一个把未定义变量 env 直接传进 Popen 的写法, 会让本函数在
        # 后台启动分支直接抛 NameError —— 手动 `daemon --start` 与一键部署
        # 「启动后台守护」两步都因此失败。子进程以 cwd=project_root 配合
        # `-m telemetry.cli` 运行, 标准做法即可定位模块, 无需注入 PYTHONPATH。
        proc = subprocess.Popen(
            cmd,
            cwd=project_root,
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
        res = subprocess.run(["launchctl", *args], capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
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
            capture_output=True, text=True, encoding="utf-8", errors="replace",
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
        <string>{escape(py_exe)}</string>
        <string>-m</string>
        <string>telemetry.cli</string>
        <string>daemon</string>
        <string>--foreground</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{escape(project_root)}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>{escape(project_root)}</string>
        <key>HOME</key>
        <string>{escape(os.path.expanduser("~"))}</string>
    </dict>
    <key>SoftResourceLimits</key>
    <dict>
        <key>NumberOfFiles</key>
        <integer>{LAUNCHD_MAX_OPEN_FILES}</integer>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{escape(LOG_FILE)}</string>
    <key>StandardErrorPath</key>
    <string>{escape(LOG_FILE)}</string>
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
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        if res.returncode == 0:
            print(f"[Task] 成功注册 Windows 开机自启计划任务: {task_name}")
        else:
            print(f"[Task] 注册失败: {res.stderr}")
    except Exception as e:
        print(f"[Task] 注册异常: {e}")
