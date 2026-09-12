"""Unit and integration tests for telemetry module."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from datetime import datetime

from telemetry.models import TaskType, RetrievalItem, DownloadItem, HighlightItem, TaskRecord
from telemetry.db import TelemetryDB
from telemetry.tracker import TelemetryTracker
from telemetry.aggregator import (
    TelemetryAggregator,
    MANUAL_RETRIEVAL_SECONDS_PER_PAPER,
    MANUAL_DOWNLOAD_SECONDS_PER_PAPER,
    MANUAL_HIGHLIGHT_SECONDS_PER_PAPER,
)
from telemetry.feishu_sync import FeishuSyncClient


class TestTelemetry(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_telemetry.db")
        self.db = TelemetryDB(self.db_path)
        self.tracker = TelemetryTracker(self.db)
        self.aggregator = TelemetryAggregator(self.db)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_tracker_retrieval(self):
        with self.tracker.track_retrieval(project_name="test_proj") as col:
            col.add_item("P1-1", url="http://example.com/1", duration_seconds=5.0)
            col.add_item("P1-2", url="http://example.com/2", duration_seconds=5.0)
            col.add_tokens(prompt_tokens=100, completion_tokens=50)

        rows = self.db.query_retrievals()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["paper_id"], "P1-1")
        self.assertEqual(rows[1]["paper_id"], "P1-2")

        tasks = self.db.query_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_type"], "retrieval")
        self.assertEqual(tasks[0]["prompt_tokens"], 100)
        self.assertEqual(tasks[0]["completion_tokens"], 50)
        self.assertEqual(tasks[0]["total_tokens"], 150)

    def test_tracker_download(self):
        with self.tracker.track_download(project_name="test_proj") as col:
            col.add_item("P2-1", pdf_path="/path/to/p2_1.pdf", file_size_bytes=1024, duration_seconds=3.0, success=True)
            col.add_item("P2-2", pdf_path="", duration_seconds=2.0, success=False, error_msg="404")

        downloads = self.db.query_downloads()
        self.assertEqual(len(downloads), 2)
        success_dl = [d for d in downloads if d["success"]]
        self.assertEqual(len(success_dl), 1)

    def test_tracker_highlight(self):
        with self.tracker.track_highlight(project_name="test_proj") as col:
            col.add_item("P3-1", pdf_path="/p3.pdf", page_count=10, num_annots=4, 
                         highlight_duration_seconds=12.0, correction_duration_seconds=4.0)

        highlights = self.db.query_highlights()
        self.assertEqual(len(highlights), 1)
        self.assertEqual(highlights[0]["page_count"], 10)
        self.assertEqual(highlights[0]["num_annots"], 4)
        self.assertEqual(highlights[0]["highlight_duration_seconds"], 12.0)
        self.assertEqual(highlights[0]["correction_duration_seconds"], 4.0)

    def test_savings_formula(self):
        # 插入已知数据测试公式
        # 1 篇检索 (耗时 20s): 节约 = 1 * 420 - 20 = 400s
        with self.tracker.track_retrieval(project_name="test") as col:
            col.add_item("R1", duration_seconds=20.0)

        # 1 篇下载成功 (耗时 10s): 节约 = 1 * 120 - 10 = 110s
        with self.tracker.track_download(project_name="test") as col:
            col.add_item("D1", duration_seconds=10.0, success=True)

        # 1 篇高亮 (高亮耗时 30s, 修正 10s): 节约 = 1 * 240 - (30 + 10) = 200s
        with self.tracker.track_highlight(project_name="test") as col:
            col.add_item("H1", page_count=8, highlight_duration_seconds=30.0, correction_duration_seconds=10.0)

        rep = self.aggregator.get_all_time_report()
        self.assertEqual(rep.retrieval_count, 1)
        self.assertEqual(rep.retrieval_saved_seconds, 400.0)

        self.assertEqual(rep.download_count, 1)
        self.assertEqual(rep.download_saved_seconds, 110.0)

        self.assertEqual(rep.highlight_count, 1)
        self.assertEqual(rep.highlight_pages, 8)
        self.assertEqual(rep.highlight_saved_seconds, 200.0)

        # 总计节约
        expected_total_sec = 400.0 + 110.0 + 200.0  # 710s
        self.assertAlmostEqual(rep.total_saved_seconds, expected_total_sec, places=1)
        self.assertAlmostEqual(rep.total_saved_hours, 710.0 / 3600.0, places=3)

    def test_feishu_card_building(self):
        with self.tracker.track_retrieval() as col:
            col.add_item("R1", duration_seconds=10.0)
        rep = self.aggregator.get_weekly_report()
        client = FeishuSyncClient()
        card = client.build_card(rep)
        self.assertIn("header", card)
        self.assertIn("elements", card)
        self.assertEqual(card["header"]["template"], "turquoise")

    def test_schedule_parsers(self):
        from telemetry.config import parse_weekly_time, parse_monthly_time
        w_day, w_time = parse_weekly_time("Friday", "18:00")
        self.assertEqual(w_day, 4)
        self.assertEqual(w_time, "18:00")

        w_day_cn, w_time_cn = parse_weekly_time("周一", "09:30")
        self.assertEqual(w_day_cn, 0)
        self.assertEqual(w_time_cn, "09:30")

        m_day, m_time = parse_monthly_time("1", "09:00")
        self.assertEqual(m_day, 1)
        self.assertEqual(m_time, "09:00")

        m_last, m_last_time = parse_monthly_time("last", "18:00")
        self.assertEqual(m_last, -1)
        self.assertEqual(m_last_time, "18:00")

        with self.assertRaises(ValueError):
            parse_weekly_time("InvalidDay", "18:00")
        with self.assertRaises(ValueError):
            parse_weekly_time("Mon", "25:00")
        with self.assertRaises(ValueError):
            parse_monthly_time("35", "09:00")

    def test_daemon_helpers(self):
        from telemetry.daemon import get_daemon_status, get_startup_vbs_path
        from telemetry.platform_paths import windows_startup_dir
        st = get_daemon_status()
        self.assertIn("running", st)
        self.assertIn("pid", st)
        vbs_path = get_startup_vbs_path()
        if sys.platform == "win32":
            # Windows: 指向 Startup 目录下的静默自启脚本
            self.assertIsNotNone(vbs_path)
            self.assertTrue(vbs_path.endswith("traework_telemetry_silent.vbs"))
            self.assertTrue(vbs_path.startswith(windows_startup_dir()))
        else:
            # 非 Windows: 该能力不存在，必须显式返回 None 而不是伪路径
            self.assertIsNone(windows_startup_dir())
            self.assertIsNone(vbs_path)

    def test_launchd_agent_paths(self):
        """macOS LaunchAgent 路径与加载状态查询应按平台返回。"""
        from telemetry.daemon import (
            LAUNCHD_LABEL,
            get_launchd_plist_path,
            get_launchd_status,
        )

        plist = get_launchd_plist_path()
        status = get_launchd_status()
        if sys.platform == "darwin":
            self.assertIsNotNone(plist)
            self.assertTrue(os.path.isabs(plist))
            self.assertTrue(plist.endswith(f"LaunchAgents/{LAUNCHD_LABEL}.plist"))
            self.assertIn(status, (True, False), "macOS 下应为布尔加载状态")
        else:
            self.assertIsNone(plist, "非 macOS 不应返回 LaunchAgent 路径")
            self.assertIsNone(status, "非 macOS 不应返回 LaunchAgent 状态")

    def test_start_daemon_background_spawn(self):
        """后台启动分支必须真正走通到 Popen。

        回归防护: 该分支曾遗留一个未定义的 ``env=env``, 使函数在任何进程被拉起之前
        就抛 NameError —— 手动 ``daemon --start`` 与一键部署「启动后台守护」同时失效。
        当时两条运行路径 (LaunchAgent 以 ``--foreground`` 拉起) 恰好都绕过了这段代码,
        单测也未覆盖, 故障因此长期静默。

        本用例不产生真实进程: 打桩 subprocess.Popen, 并把 PID / 日志文件指向临时目录。
        """
        from unittest import mock
        from telemetry import daemon as daemon_mod

        spawned = {}

        class _FakeProc:
            pid = 424242

        def _fake_popen(cmd, **kwargs):
            spawned["cmd"] = cmd
            spawned["kwargs"] = kwargs
            return _FakeProc()

        pid_file = os.path.join(self.test_dir, "daemon.pid")
        log_file = os.path.join(self.test_dir, "daemon.log")

        with mock.patch.object(daemon_mod, "PID_FILE", pid_file), \
                mock.patch.object(daemon_mod, "LOG_FILE", log_file), \
                mock.patch.object(daemon_mod.subprocess, "Popen", _fake_popen):
            daemon_mod.start_daemon_process(foreground=False)

        self.assertTrue(spawned, "后台启动分支没有调用 subprocess.Popen")
        cmd = spawned["cmd"]
        self.assertIsInstance(cmd, list)
        self.assertIn("telemetry.cli", cmd)
        self.assertIn("--foreground", cmd, "子进程应以前台模式运行主循环")

        kwargs = spawned["kwargs"]
        self.assertTrue(os.path.isdir(kwargs.get("cwd") or ""), "cwd 必须是真实存在的项目根")
        env_kwarg = kwargs.get("env")
        self.assertTrue(
            env_kwarg is None or isinstance(env_kwarg, dict),
            "若传 env 必须是真实环境映射 (回归点: 曾遗留未定义的 env=env)",
        )

        # PID 正确落盘, 后续 --status / --stop 才能找到它
        with open(pid_file, encoding="utf-8") as fp:
            self.assertEqual(fp.read().strip(), "424242")

    def test_daemon_log_repeat_throttling(self):
        """同一消息连续重复时不得逐条落盘。

        现场曾因此把日志刷到 2 MB 且几乎全是同一条 EMFILE, 既膨胀日志又淹没有效信息。
        """
        from unittest import mock
        from telemetry import daemon as dm

        log_path = os.path.join(self.test_dir, "daemon.log")
        d = dm.TelemetryDaemon.__new__(dm.TelemetryDaemon)  # 不触发 __init__ 的 DB 副作用
        d._last_msg = ""
        d._repeat = 0

        with mock.patch.object(dm, "LOG_FILE", log_path), mock.patch("builtins.print"):
            for _ in range(250):
                d.log("同一条错误")

        with open(log_path, encoding="utf-8") as fp:
            lines = [ln for ln in fp.read().splitlines() if ln]
        # 首次 1 条 + 第 100 / 200 次各 1 条进行中汇总 = 3 条, 而非 250 条
        self.assertEqual(len(lines), 3, f"重复消息应被限流, 实际落了 {len(lines)} 条")
        self.assertIn("重复 100 次", lines[1])

    def test_daemon_log_rotation(self):
        """日志超过上限时留一份 .1 备份并清空当前文件。

        刻意用「复制 + 截断」而非改名: launchd 的 StandardOutPath 长期持有同一个 fd,
        改名会让它继续写旧 inode, 与按路径写新文件的进程分叉。
        """
        from unittest import mock
        from telemetry import daemon as dm

        log_path = os.path.join(self.test_dir, "daemon.log")
        backup_path = log_path + ".1"
        with open(log_path, "w", encoding="utf-8") as fp:
            fp.write("x" * 1024)

        with mock.patch.object(dm, "LOG_FILE", log_path), \
                mock.patch.object(dm, "LOG_BACKUP_FILE", backup_path), \
                mock.patch.object(dm, "LOG_MAX_BYTES", 512):
            dm.rotate_log_if_needed()

        self.assertTrue(os.path.exists(backup_path), "应留下 .1 备份")
        self.assertEqual(os.path.getsize(backup_path), 1024)
        self.assertEqual(os.path.getsize(log_path), 0, "当前日志应被清空 (同一 inode)")

        # 未超限时不应产生备份
        os.remove(backup_path)
        with open(log_path, "w", encoding="utf-8") as fp:
            fp.write("small")
        with mock.patch.object(dm, "LOG_FILE", log_path), \
                mock.patch.object(dm, "LOG_BACKUP_FILE", backup_path), \
                mock.patch.object(dm, "LOG_MAX_BYTES", 512):
            dm.rotate_log_if_needed()
        self.assertFalse(os.path.exists(backup_path), "未超限不应轮转")
        self.assertEqual(os.path.getsize(log_path), 5)

    def test_fd_usage_observation(self):
        """描述符观测应返回 (已用, 软上限), 且是"远未打满"的正常值。"""
        from telemetry.daemon import fd_usage

        info = fd_usage()
        if info is None:
            self.skipTest("当前平台无法读取 /dev/fd 或 /proc/self/fd")
        used, soft = info
        self.assertGreater(used, 0)
        if soft is not None:
            self.assertGreater(soft, used, "正常情况不应逼近描述符上限")

    def test_launchd_plist_template(self):
        """生成的 LaunchAgent plist 必须合法, 且申请了描述符软上限。

        launchd 默认只给 256 个描述符, 对长期常驻的扫描进程余量太薄 (曾在一上午耗尽)。
        """
        import plistlib
        from unittest import mock
        from telemetry import daemon as dm

        plist_path = os.path.join(self.test_dir, f"{dm.LAUNCHD_LABEL}.plist")
        with mock.patch.object(dm, "get_launchd_plist_path", return_value=plist_path), \
                mock.patch.object(dm, "_launchctl", return_value=True), \
                mock.patch.object(dm, "stop_daemon_process"), \
                mock.patch.object(dm, "LOG_FILE", os.path.join(self.test_dir, "d.log")), \
                mock.patch("builtins.print"):
            dm.install_launchd_agent()

        with open(plist_path, "rb") as fp:
            data = plistlib.load(fp)  # 解析失败即说明模板生成了非法 plist

        self.assertEqual(data["Label"], dm.LAUNCHD_LABEL)
        self.assertEqual(data["SoftResourceLimits"]["NumberOfFiles"], dm.LAUNCHD_MAX_OPEN_FILES)
        self.assertGreater(dm.LAUNCHD_MAX_OPEN_FILES, 256)
        self.assertEqual(data["ProgramArguments"][0], sys.executable)
        self.assertTrue(data["KeepAlive"])

    def test_alert_settings_defaults(self):
        """告警配置默认开启、静默期 60 分钟; 缺段或非法值都要退回默认。"""
        from telemetry.config import DEFAULT_CONFIG
        from telemetry import alerter

        self.assertTrue(DEFAULT_CONFIG["alerts"]["enabled"])
        self.assertEqual(DEFAULT_CONFIG["alerts"]["min_interval_minutes"], 60)

        # 已有配置只覆盖部分字段 -> 其余取默认
        partial = alerter.alert_settings({"alerts": {"min_interval_minutes": 15}})
        self.assertTrue(partial["enabled"])
        self.assertEqual(partial["min_interval_minutes"], 15)

        # 完全缺 alerts 段 / 非法值
        self.assertTrue(alerter.alert_settings({})["enabled"])
        self.assertEqual(
            alerter.alert_settings({"alerts": {"min_interval_minutes": "abc"}})["min_interval_minutes"],
            60,
        )
        self.assertEqual(
            alerter.alert_settings({"alerts": {"min_interval_minutes": 0}})["min_interval_minutes"], 1
        )

    def test_alert_rate_limit_windows(self):
        """限流窗口: 成功后有静默期; 失败只需等 10 分钟; 到期即可放行。"""
        import json
        from datetime import datetime, timedelta
        from unittest import mock
        from telemetry import alerter

        state = os.path.join(self.test_dir, "alerts_state.json")
        now = datetime(2026, 9, 11, 12, 0, 0)

        def seed(last_attempt, last_ok):
            with open(state, "w", encoding="utf-8") as fp:
                json.dump({"fd-80": {"last_attempt": last_attempt.isoformat(), "last_ok": last_ok}}, fp)

        with mock.patch.object(alerter, "STATE_FILE", state):
            # 无记录 -> 不限流
            self.assertIsNone(alerter.rate_limited_for("fd-80", 60, now))

            # 成功 + 30 分钟 -> 仍在 60 分钟静默期内
            seed(now - timedelta(minutes=30), True)
            self.assertIsNotNone(alerter.rate_limited_for("fd-80", 60, now))

            # 成功 + 61 分钟 -> 放行
            seed(now - timedelta(minutes=61), True)
            self.assertIsNone(alerter.rate_limited_for("fd-80", 60, now))

            # 失败 + 5 分钟 -> 仍在 10 分钟重试窗口内
            seed(now - timedelta(minutes=5), False)
            self.assertIsNotNone(alerter.rate_limited_for("fd-80", 60, now))

            # 失败 + 11 分钟 -> 放行 (不必等满 60 分钟)
            seed(now - timedelta(minutes=11), False)
            self.assertIsNone(alerter.rate_limited_for("fd-80", 60, now))

            # 状态文件损坏 -> 不限流, 而不是抛异常
            with open(state, "w", encoding="utf-8") as fp:
                fp.write("{ 这不是 json")
            self.assertIsNone(alerter.rate_limited_for("fd-80", 60, now))

    def test_send_alert_respects_switch_and_limit(self):
        """关闭时与限流中都不应真的发起推送。"""
        from unittest import mock
        from telemetry import alerter

        state = os.path.join(self.test_dir, "alerts_state.json")
        on = {"enabled": True, "min_interval_minutes": 60}

        with mock.patch.object(alerter, "STATE_FILE", state), \
                mock.patch.object(alerter, "_post_card", return_value=(True, "ok")) as post:
            # 关闭 -> 不推送
            ok, msg = alerter.send_alert("t", ["x"], key="k1",
                                         settings={"enabled": False, "min_interval_minutes": 60})
            self.assertFalse(ok)
            self.assertIn("关闭", msg)
            post.assert_not_called()

            # 首次 -> 发出
            ok, _ = alerter.send_alert("t", ["x"], key="k1", settings=on)
            self.assertTrue(ok)
            self.assertEqual(post.call_count, 1)

            # 紧接着再来 -> 被限流, 不再推送
            ok, msg = alerter.send_alert("t", ["x"], key="k1", settings=on)
            self.assertFalse(ok)
            self.assertIn("限流", msg)
            self.assertEqual(post.call_count, 1)

            # force=True 绕过开关与限流
            ok, _ = alerter.send_alert("t", ["x"], key="k1",
                                       settings={"enabled": False, "min_interval_minutes": 60},
                                       force=True)
            self.assertTrue(ok)
            self.assertEqual(post.call_count, 2)

    def test_alert_card_structure_and_fault_tolerance(self):
        """卡片结构正确; 且推送链路出问题时返回 False 而不是把调用方带崩。"""
        from unittest import mock
        from telemetry import alerter

        card = alerter.build_alert_card(
            "守护进程文件描述符吃紧", ["**占用**：`200/256`"], level="critical",
            nickname="Devin", host="mac-mini",
        )
        self.assertEqual(card["header"]["template"], "red")
        self.assertIn("守护进程文件描述符吃紧", card["header"]["title"]["content"])
        self.assertTrue(card["config"]["wide_screen_mode"])
        body = json.dumps(card, ensure_ascii=False)
        for expected in ("200/256", "Devin", "mac-mini"):
            self.assertIn(expected, body)
        # 未知 level 退回默认色, 而不是 KeyError
        self.assertEqual(alerter.build_alert_card("t", [], level="nope")["header"]["template"], "orange")

        # 传输层抛异常 -> 返回 False 并落一条"失败"记录 (否则限流形同虚设)
        state = os.path.join(self.test_dir, "alerts_state.json")
        with mock.patch.object(alerter, "STATE_FILE", state), \
                mock.patch.object(alerter, "_post_card", side_effect=RuntimeError("boom")):
            ok, msg = alerter.send_alert("t", ["x"], key="k9",
                                         settings={"enabled": True, "min_interval_minutes": 60})
        self.assertFalse(ok)
        self.assertIn("boom", msg)
        with open(state, encoding="utf-8") as fp:
            self.assertFalse(json.load(fp)["k9"]["last_ok"], "失败也要记一次尝试")

    def test_fd_health_triggers_alert(self):
        """描述符逼近上限时既要落日志, 也要推外部告警 (并按占用分档升级)。"""
        from unittest import mock
        from telemetry import daemon as dm
        from telemetry import alerter

        log_path = os.path.join(self.test_dir, "daemon.log")
        d = dm.TelemetryDaemon.__new__(dm.TelemetryDaemon)
        d._last_msg = ""
        d._repeat = 0
        d.last_fd = None

        # 95% -> critical, key 归到 90 档
        with mock.patch.object(dm, "LOG_FILE", log_path), \
                mock.patch.object(dm, "fd_usage", return_value=(95, 100)), \
                mock.patch.object(alerter, "send_alert", return_value=(True, "ok")) as alert, \
                mock.patch("builtins.print"):
            d._check_fd_health()
        self.assertEqual(d.last_fd, {"used": 95, "limit": 100})
        alert.assert_called_once()
        self.assertEqual(alert.call_args.kwargs["key"], "fd-90")
        self.assertEqual(alert.call_args.kwargs["level"], "critical")

        # 85% -> warning
        with mock.patch.object(dm, "LOG_FILE", log_path), \
                mock.patch.object(dm, "fd_usage", return_value=(85, 100)), \
                mock.patch.object(alerter, "send_alert", return_value=(True, "ok")) as alert2, \
                mock.patch("builtins.print"):
            d._check_fd_health()
        self.assertEqual(alert2.call_args.kwargs["level"], "warning")

        # 远未达阈值 -> 不告警
        with mock.patch.object(dm, "LOG_FILE", log_path), \
                mock.patch.object(dm, "fd_usage", return_value=(10, 100)), \
                mock.patch.object(alerter, "send_alert", return_value=(True, "ok")) as alert3, \
                mock.patch("builtins.print"):
            d._check_fd_health()
        alert3.assert_not_called()
        self.assertEqual(d.last_fd, {"used": 10, "limit": 100})

    def test_scanner_retrieval_from_highlight_reference_list(self):
        """高亮引用清单应折算为检索数, 且重复引用同一文献只计 1 篇 (唯一文献口径)。"""
        from telemetry.watcher import WorkspaceScanner

        project_dir = os.path.join(self.test_dir, "proj_rsv")
        hl_dir = os.path.join(project_dir, "高亮结果")
        os.makedirs(hl_dir)

        entries = [
            ("P1-1", "Zar HJ, et al. N Engl J Med. 2025;393(13):1292-1303.", "40000001"),
            # 同一篇文献被另一条 Pn-x 再次引用 -> 应被去重
            ("P1-2", "Zar HJ, et al. N Engl J Med. 2025;393(13):1292-1303.", ""),
            ("P1-3", "Georgakopoulou VE, et al. Microorganisms. 2025;13(8):1876.", ""),
        ]
        for pn_x, reference, pmid in entries:
            with open(os.path.join(hl_dir, f"{pn_x}_meta.json"), "w", encoding="utf-8") as fp:
                json.dump(
                    {"pn_x": pn_x, "reference_field": reference, "pmid": pmid or None},
                    fp, ensure_ascii=False,
                )

        stats = WorkspaceScanner(self.db).scan_project(project_dir, "RSV")
        self.assertEqual(stats["retrieval"], 2, "重复引用同一文献应只计 1 篇")
        self.assertEqual(self.aggregator.get_all_time_report().retrieval_count, 2)

    def test_scanner_retrieval_falls_back_to_tsv_list(self):
        """无 *_meta.json 时, 回退读取 高亮结果清单.tsv。"""
        from telemetry.watcher import WorkspaceScanner

        project_dir = os.path.join(self.test_dir, "proj_tsv")
        os.makedirs(os.path.join(project_dir, "高亮结果"))
        tsv = os.path.join(project_dir, "高亮结果清单.tsv")
        with open(tsv, "w", encoding="utf-8") as fp:
            fp.write("pn_x\treference_field\thighlights\tstatus\n")
            fp.write("P2-1\tKapikian AZ, et al. Am J Epidemiol. 1969;89(4):405-421.\t48\tok\n")
            fp.write("P2-2\tKapikian AZ, et al. Am J Epidemiol. 1969;89(4):405-421.\t12\tok\n")
            fp.write("P2-3\tTharmalingam T, et al. Hum Vaccin Immunother. 2022;18(2):1886560.\t70\tok\n")

        stats = WorkspaceScanner(self.db).scan_project(project_dir, "TSVProj")
        self.assertEqual(stats["retrieval"], 2)

    def test_retrieval_dedup_by_doi(self):
        """带 DOI 时按 DOI 精确去重: 著录写法不同但 DOI 相同只计 1 篇。"""
        from telemetry.watcher import WorkspaceScanner

        project_dir = os.path.join(self.test_dir, "proj_doi")
        hl_dir = os.path.join(project_dir, "高亮结果")
        os.makedirs(hl_dir)
        entries = [
            ("P1-1", "Zar HJ, et al. N Engl J Med. 2025;393(13):1292-1303.", "10.1056/NEJMoa2502600"),
            # 同一 DOI 的不同写法 (带 URL 前缀) -> 应去重
            ("P1-2", "Zar HJ et al. NEJM 2025", "https://doi.org/10.1056/NEJMoa2502600"),
            ("P1-3", "Fleming-Dutra KE, et al. MMWR. 2023;72(41):1115-1122.", "10.15585/mmwr.mm7241a1"),
        ]
        for pn_x, reference, doi in entries:
            with open(os.path.join(hl_dir, f"{pn_x}_meta.json"), "w", encoding="utf-8") as fp:
                json.dump(
                    {"pn_x": pn_x, "reference_field": reference, "doi": doi},
                    fp, ensure_ascii=False,
                )

        stats = WorkspaceScanner(self.db).scan_project(project_dir, "DoiProj")
        self.assertEqual(stats["retrieval"], 2, "同一 DOI 的不同著录写法应只计 1 篇")

    def test_retrieval_merges_noise_suffix_but_keeps_appendix(self):
        """尾部仅文号/日期噪声时归并; 补充附录属独立文献, 必须保持独立。"""
        from telemetry.watcher import WorkspaceScanner

        project_dir = os.path.join(self.test_dir, "proj_merge")
        hl_dir = os.path.join(project_dir, "高亮结果")
        os.makedirs(hl_dir)
        base = "Fleming-Dutra KE, et al. MMWR Morb Mortal Wkly Rep. 2023;72(41):1115-1122."
        zar = "Zar HJ, et al. N Engl J Med. 2025;393(13):1343-1345."
        entries = [
            ("P1-1", base),
            ("P1-2", base + "07-2028-CN-RSM-00086"),                      # 尾部文号 -> 归并
            ("P2-1", zar),
            ("P2-2", zar + " Supplementary Appendix."),                    # 独立文献 -> 不归并
        ]
        for pn_x, reference in entries:
            with open(os.path.join(hl_dir, f"{pn_x}_meta.json"), "w", encoding="utf-8") as fp:
                json.dump({"pn_x": pn_x, "reference_field": reference}, fp, ensure_ascii=False)

        stats = WorkspaceScanner(self.db).scan_project(project_dir, "MergeProj")
        # 1 (MMWR 两条归并) + 1 (正文) + 1 (补充附录独立) = 3
        self.assertEqual(stats["retrieval"], 3, "尾部噪声应归并, 补充附录应独立计一篇")

    def test_platform_paths(self):
        """路径解析必须跨平台正确，不得出现 Windows 反斜杠字面量。"""
        from telemetry import platform_paths as pp
        from telemetry.config import DEFAULT_CONFIG

        home = os.path.expanduser("~")
        expected_root = {
            "win32": os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming"),
            "darwin": os.path.join(home, "Library", "Application Support"),
        }.get(
            sys.platform,
            os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config"),
        )
        roots = pp.app_data_roots()
        self.assertTrue(roots, "应用数据根候选不得为空")
        self.assertEqual(roots[0], expected_root, "当前平台应优先使用本平台路径")

        # channel_config.json 候选必须落在本平台首个根之下
        self.assertTrue(pp.trae_work_config_candidates())
        self.assertTrue(pp.trae_work_config_path().startswith(roots[0]))

        # 默认监控目录必须是跨平台绝对路径，且不含 Windows 反斜杠
        watch_dirs = DEFAULT_CONFIG["watcher"]["watch_dirs"]
        self.assertTrue(watch_dirs)
        for d in watch_dirs:
            self.assertNotIn("\\", d, f"默认监控目录含 Windows 反斜杠: {d}")
            self.assertTrue(os.path.isabs(d), f"默认监控目录非绝对路径: {d}")

        self.assertTrue(os.path.isabs(pp.desktop_dir()))
        self.assertTrue(os.path.isabs(pp.trae_work_dir()))
        self.assertNotIn("\\", pp.trae_work_dir())

    def test_scanner_recognizes_chinese_highlight_dir(self):
        """高亮产物放在 高亮结果/ 目录 (RSV 布局) 时, 扫描器必须识别并计入。"""
        try:
            import fitz
        except ImportError:
            self.skipTest("PyMuPDF 不可用")

        from telemetry.watcher import WorkspaceScanner

        project_dir = os.path.join(self.test_dir, "proj_rsv")
        hl_dir = os.path.join(project_dir, "高亮结果")
        os.makedirs(hl_dir)

        pdf_path = os.path.join(hl_dir, "P1-1.pdf")
        doc = fitz.open()
        page = doc.new_page()
        page.add_rect_annot(fitz.Rect(50, 50, 200, 90))
        page.add_rect_annot(fitz.Rect(60, 120, 220, 160))
        doc.save(pdf_path)
        doc.close()

        stats = WorkspaceScanner(self.db).scan_project(project_dir, "RSV")
        self.assertEqual(stats["highlight"], 1, "高亮结果/ 下的 PDF 应计为 1 篇高亮")

        rep = self.aggregator.get_all_time_report()
        self.assertEqual(rep.highlight_count, 1)
        # 标注数应取 PDF 内真实标注数 (2), 而非固定基准值
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT num_annots FROM highlight_items WHERE pdf_path = ?", (pdf_path,)
            ).fetchall()
        self.assertEqual(rows[0][0], 2)

    def test_highlight_pdf_distinct_pages_and_count(self):
        """测试：完成标注多少篇对应多少个PDF文献文件；阅读页数对应所有高亮PDF文献文件的页数总和。"""
        with self.tracker.track_highlight(project_name="proj_a") as col:
            # 同一 PDF 文件 paper_1.pdf 发生两次高亮操作 (例如分段或不同幻灯片)
            col.add_item("P1", pdf_path="C:/docs/paper_1.pdf", page_count=12, highlight_duration_seconds=20.0)
            col.add_item("P1", pdf_path="C:/docs/paper_1.pdf", page_count=12, highlight_duration_seconds=15.0)
            # 另一个 PDF 文件 paper_2.pdf 高亮一次
            col.add_item("P2", pdf_path="C:/docs/paper_2.pdf", page_count=25, highlight_duration_seconds=30.0)

        rep = self.aggregator.get_all_time_report()
        # 完成标注应精确对应 2 个独立 PDF 文献文件
        self.assertEqual(rep.highlight_count, 2)
        # 阅读页数应精确对应 12 + 25 = 37 页 (所有高亮 PDF 文献文件的页数总和)
        self.assertEqual(rep.highlight_pages, 37)

    def test_exact_llm_token_recording(self):
        """测试：默认 exact 模式下 100% 对应真实服务商控制台 Token 日志。"""
        from telemetry.token_tracker import record_llm_usage

        # 模拟一次标准的 OpenAI/DeepSeek 响应结构
        mock_response = {
            "id": "chatcmpl-test-8899",
            "model": "deepseek-chat",
            "usage": {
                "prompt_tokens": 3200,
                "completion_tokens": 800,
                "total_tokens": 4000
            }
        }
        rec = record_llm_usage(
            response=mock_response,
            provider="deepseek",
            project_name="RSV",
            db=self.db
        )
        self.assertIsNotNone(rec)
        self.assertEqual(rec.total_tokens, 4000)
        self.assertEqual(rec.req_id, "chatcmpl-test-8899")

        # 验证聚合器在默认 exact 模式下精准对齐
        rep = self.aggregator.get_all_time_report()
        self.assertEqual(rep.total_prompt_tokens, 3200)
        self.assertEqual(rep.total_completion_tokens, 800)
        self.assertEqual(rep.total_tokens, 4000)
        self.assertEqual(rep.token_mode, "exact")
        self.assertEqual(rep.llm_call_count, 1)

    def test_mmx_quota_parsing(self):
        """测试：mmx-cli 账户级配额可真实读取(单位是次数, 不是 token)。"""
        from telemetry import llm_providers

        sample_stdout = json.dumps({
            "model_remains": [
                {
                    "model_name": "general",
                    "current_interval_total_count": 100,
                    "current_interval_usage_count": 23,
                    "current_weekly_total_count": 700,
                    "current_weekly_usage_count": 145,
                    "current_interval_remaining_percent": 77,
                    "current_weekly_remaining_percent": 79,
                },
                {
                    "model_name": "video",
                    "current_interval_total_count": 50,
                    "current_interval_usage_count": 5,
                    "current_weekly_total_count": 350,
                    "current_weekly_usage_count": 30,
                    "current_interval_remaining_percent": 90,
                    "current_weekly_remaining_percent": 91,
                },
            ]
        })

        def fake_run(cmd, **kwargs):
            self.assertEqual(cmd[:3], ["/fake/mmx", "quota", "show"])
            return mock.MagicMock(returncode=0, stdout=sample_stdout, stderr="")

        with mock.patch.object(llm_providers, "_which", return_value="/fake/mmx"), \
                mock.patch("subprocess.run", side_effect=fake_run):
            quota = llm_providers.read_mmx_quota()

        self.assertIsNotNone(quota)
        self.assertEqual(quota["units"], "count")
        self.assertEqual(len(quota["models"]), 2)
        general = quota["models"][0]
        self.assertEqual(general["name"], "general")
        self.assertEqual(general["interval_used"], 23)
        self.assertEqual(general["interval_total"], 100)
        self.assertEqual(general["weekly_used"], 145)
        self.assertEqual(general["weekly_total"], 700)
        self.assertEqual(general["weekly_remaining_percent"], 79)

    def test_mmx_quota_missing_binary_returns_none(self):
        """测试：未安装 mmx-cli 时配额读取诚实返回 None。"""
        from telemetry import llm_providers

        with mock.patch.object(llm_providers, "_which", return_value=""):
            self.assertIsNone(llm_providers.read_mmx_quota())

    def test_traework_state_detection(self):
        """测试：从 TraeWork renderer.log 识别当前 provider 与 model。"""
        from telemetry import llm_providers, platform_paths

        tmp_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_root, ignore_errors=True)
        app_dir = os.path.join(tmp_root, "TRAE SOLO CN")
        log_dir = os.path.join(app_dir, "logs", "20260912T120000", "window1")
        os.makedirs(log_dir)
        log_path = os.path.join(log_dir, "renderer.log")
        with open(log_path, "w", encoding="utf-8") as fh:
            fh.write('{"model_info": {"provider": "openai", "model_name": "gpt-4o"}}\n')
            fh.write('some prefix {"model_info": {"provider": "deepseek", "model_name": "deepseek-chat", "base_url": "https://api.deepseek.com"}} other text\n')

        with mock.patch.object(platform_paths, "app_data_roots", return_value=[tmp_root]):
            state = llm_providers.read_traework_state()

        self.assertTrue(state["installed"])
        self.assertTrue(state["running"])
        self.assertEqual(state["active_provider"], "deepseek")
        self.assertEqual(state["active_model"], "deepseek-chat")
        self.assertEqual(state["base_url"], "https://api.deepseek.com")
        self.assertIn("renderer.log", state["log_path"])

    def test_traework_state_no_installation(self):
        """测试：未安装 TraeWork 时状态识别返回未安装。"""
        from telemetry import llm_providers, platform_paths

        fake_root = os.path.join(self.test_dir, "no_trae")
        os.makedirs(fake_root)
        with mock.patch.object(platform_paths, "app_data_roots", return_value=[fake_root]):
            state = llm_providers.read_traework_state()

        self.assertFalse(state["installed"])
        self.assertIn("未找到", state["detail"])

    def test_traework_spool_ingestion(self):
        """测试：TraeWork 侧写入 spool 的真实用量能被摄入并读回。"""
        from telemetry import llm_spool

        spool_file = os.path.join(self.test_dir, "traework_spool.jsonl")
        db_path = os.path.join(self.test_dir, "traework.db")
        db = TelemetryDB(db_path)

        ok = llm_spool.write_spool_record({
            "provider": "traework",
            "model": "traework-deepseek-v4-flash",
            "prompt_tokens": 500,
            "completion_tokens": 120,
            "total_tokens": 620,
            "req_id": "tw-req-001",
            "source": "traework-extension",
            "project_name": "RSV",
        }, path=spool_file)
        self.assertTrue(ok)

        res = llm_spool.ingest(path=spool_file, db=db)
        self.assertEqual(res["imported"], 1)
        self.assertEqual(res["duplicated"], 0)
        self.assertEqual(res["invalid"], 0)

        rows = db.query_llm_tokens(provider="traework")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["provider"], "traework")
        self.assertEqual(rows[0]["model"], "traework-deepseek-v4-flash")
        self.assertEqual(rows[0]["prompt_tokens"], 500)
        self.assertEqual(rows[0]["completion_tokens"], 120)
        self.assertEqual(rows[0]["total_tokens"], 620)

        # 幂等：同一条记录再次写入 spool 后摄入应被去重
        ok2 = llm_spool.write_spool_record({
            "provider": "traework",
            "model": "traework-deepseek-v4-flash",
            "prompt_tokens": 500,
            "completion_tokens": 120,
            "total_tokens": 620,
            "req_id": "tw-req-001",
            "source": "traework-extension",
            "project_name": "RSV",
        }, path=spool_file)
        self.assertTrue(ok2)
        res2 = llm_spool.ingest(path=spool_file, db=db)
        self.assertEqual(res2["imported"], 0)
        self.assertEqual(res2["duplicated"], 1)

    def test_standalone_packaging_metadata(self):
        """测试：独立模块打包配置文件与元数据完整性。"""
        import telemetry
        telemetry_dir = os.path.dirname(os.path.abspath(telemetry.__file__))
        setup_py = os.path.join(telemetry_dir, "setup.py")
        pyproject = os.path.join(telemetry_dir, "pyproject.toml")
        readme = os.path.join(telemetry_dir, "README.md")
        deploy_py = os.path.join(telemetry_dir, "deploy.py")
        deploy_ps1 = os.path.join(telemetry_dir, "deploy.ps1")
        deploy_bat = os.path.join(telemetry_dir, "deploy.bat")

        self.assertTrue(os.path.exists(setup_py), "setup.py 必须存在于独立模块目录")
        self.assertTrue(os.path.exists(pyproject), "pyproject.toml 必须存在于独立模块目录")
        self.assertTrue(os.path.exists(readme), "README.md 必须存在于独立模块目录")
        self.assertTrue(os.path.exists(deploy_py), "deploy.py 必须存在于独立模块目录")
        self.assertTrue(os.path.exists(deploy_ps1), "deploy.ps1 必须存在于独立模块目录")
        self.assertTrue(os.path.exists(deploy_bat), "deploy.bat 必须存在于独立模块目录")

    def test_deploy_configuration_setup(self):
        """测试：一句话部署参数装配与配置固化。

        配置路径重定向到临时目录 —— 该用例原先会临时覆写**真实**配置、再在 finally 里
        还原; 一旦进程在两步之间被强杀 (Ctrl-C / 超时 / OOM), 用户的真实配置就会永久
        留在测试值上。现在完全不触碰真实文件。
        """
        from unittest import mock
        from telemetry.deploy import setup_configuration
        from telemetry import config as config_mod
        import argparse

        cfg_path = os.path.join(self.test_dir, "telemetry_config.json")

        fake_args = argparse.Namespace(
            silent=True,
            nickname="张三测试",
            openid="ou_test_12345",
            app_id="cli_test_app",
            app_secret="test_secret",
            sheet="sheet_token_abc",
            bitable="bascnTestToken12345",
            weekly="Friday 18:30",
            monthly="last 18:00",
            add_watch_dir=None,
        )
        with mock.patch.object(config_mod, "CONFIG_FILE_PATH", cfg_path):
            cfg = setup_configuration(fake_args)

        self.assertEqual(cfg["user"]["nickname"], "张三测试")
        self.assertEqual(cfg["user"]["open_id"], "ou_test_12345")
        self.assertEqual(cfg["feishu"]["app_id"], "cli_test_app")
        self.assertEqual(cfg["schedule"]["weekly"]["day_of_week"], 4)  # Friday = 4
        self.assertEqual(cfg["schedule"]["weekly"]["time"], "18:30")
        self.assertEqual(cfg["schedule"]["monthly"]["day_of_month"], -1)  # last = -1
        self.assertEqual(cfg["schedule"]["monthly"]["time"], "18:00")
        self.assertEqual(cfg["feishu"]["company_bitable_token"], "bascnTestToken12345")

        # 落盘确实发生在临时路径上, 且权限已收紧 (配置含 app_secret)
        self.assertTrue(os.path.exists(cfg_path), "配置应写入被重定向的临时路径")
        mode = os.stat(cfg_path).st_mode & 0o777
        self.assertEqual(mode, 0o600, f"含 app_secret 的配置权限应为 0600, 实际 {oct(mode)}")

    def test_natural_language_deploy_parser(self):
        """测试：自然语言部署指令提取与实体解析。"""
        from telemetry.nlp_deploy import parse_natural_language_instruction

        # 案例 1: 标准中文字符串带花名与周报时间
        r1 = parse_natural_language_instruction("在新设备上单独部署监控，花名是wtg，每周五下午6点汇报")
        self.assertEqual(r1["intent"], "deploy")
        self.assertTrue(r1["silent"])
        self.assertEqual(r1["nickname"], "wtg")
        self.assertEqual(r1["weekly"], "周五 18:00")

        # 案例 2: 复杂长句带 OpenID 与月末月报及多维表格链接
        r2 = parse_natural_language_instruction(
            "帮我安装文献监控并绑定飞书，花名星云，用户OpenID是ou_4366ab3e3c42c5e5d2a1fce4db0c4af7，月末18:00汇报，团队多维表格绑定 https://feishu.cn/base/bascnTeamBaseToken999"
        )
        self.assertEqual(r2["intent"], "deploy")
        self.assertEqual(r2["nickname"], "星云")
        self.assertEqual(r2["openid"], "ou_4366ab3e3c42c5e5d2a1fce4db0c4af7")
        self.assertEqual(r2["monthly"], "last 18:00")
        self.assertIn("bascnTeamBaseToken999", r2["bitable"])

        # 案例 3: 卸载指令
        r3 = parse_natural_language_instruction("卸载监控守护服务")
        self.assertEqual(r3["intent"], "uninstall")

        # 案例 4: 极简一句话
        r4 = parse_natural_language_instruction("在新设备上单独部署监控")
        self.assertEqual(r4["intent"], "deploy")
        self.assertTrue(r4["silent"])

    def test_bitable_sync_and_chart_aggregation(self):
        """测试：多维表格字段序列化、多人数据聚合与排行榜图表生成。"""
        from telemetry.chart_reporter import aggregate_team_metrics, build_team_weekly_card, render_html_dashboard

        records = [
            {
                "汇报周期": "2026年 第37周",
                "成员花名": "wtg",
                "成员OpenID": "ou_1",
                "文献检索篇数": 85,
                "检索节约工时(h)": 9.63,
                "文献下载篇数": 205,
                "下载节约工时(h)": 6.35,
                "Highlight阅读页数": 5231,
                "Highlight标注篇数": 175,
                "高亮节约工时(h)": 9.97,
                "总节约工时(h)": 25.95,
                "真实Token消耗": 0,
                "API调用次数": 0,
                "上报状态": "🟢 自动同步"
            },
            {
                "汇报周期": "2026年 第37周",
                "成员花名": "星云",
                "成员OpenID": "ou_2",
                "文献检索篇数": 50,
                "检索节约工时(h)": 5.5,
                "文献下载篇数": 100,
                "下载节约工时(h)": 3.0,
                "Highlight阅读页数": 2500,
                "Highlight标注篇数": 80,
                "高亮节约工时(h)": 5.0,
                "总节约工时(h)": 13.5,
                "真实Token消耗": 12000,
                "API调用次数": 10,
                "上报状态": "🟢 自动同步"
            }
        ]

        summary = aggregate_team_metrics(records)
        self.assertEqual(summary["team_size"], 2)
        self.assertEqual(summary["total_saved_hours"], 39.45)
        self.assertEqual(summary["total_pages"], 7731)
        self.assertEqual(summary["total_tokens"], 12000)
        self.assertEqual(summary["leaderboard"][0]["nickname"], "wtg")
        self.assertEqual(summary["leaderboard"][1]["nickname"], "星云")

        card = build_team_weekly_card(records, "2026年 第37周", "https://feishu.cn/base/test")
        self.assertIn("🏆 TraeWork 团队文献整理 AI 每周人效总榜", card["header"]["title"]["content"])
        self.assertIn("wtg", str(card["elements"]))

        out_html = render_html_dashboard(records, os.path.join(self.test_dir, "test_dash.html"))
        self.assertTrue(os.path.exists(out_html))

    def test_bitable_schema_adapter(self):
        """测试：多维表格 schema 自适应（探测、写入映射、读取归一化、周期标签）。"""
        from telemetry.bitable_sync import (
            FeishuBitableManager, detect_schema_profile, week_label,
            SCHEMA_STANDARD, SCHEMA_COMPANY, COMPANY_TABLE_FIELDS, TABLE_SCHEMA_FIELDS,
        )
        from telemetry.models import AggregateReport

        # 1) schema 探测：公司既有表 vs 自建标准表 vs 无法识别
        # 公司表原有 13 列 + v5.4.43 补齐的 8 个统计列 = COMPANY_TABLE_FIELDS
        company_names = {
            "记录标识", "统计周次", "提交成员", "统计日期", "文献检索量",
            "成功下载量", "高亮标注量", "解析物理总页数", "节省工时(小时)",
            "Token消耗量", "项目任务类型", "数据状态", "备注说明",
            "检索节约工时(h)", "下载节约工时(h)", "高亮节约工时(h)",
            "其他任务数", "其他工作时长(h)", "其他Token消耗", "其他未归属Token",
            "API调用次数",
        }
        self.assertEqual(company_names, COMPANY_TABLE_FIELDS)
        self.assertEqual(detect_schema_profile(company_names), SCHEMA_COMPANY)
        # 补列后两边名字开始交叠(21 列里有 8 列与标准表同名), 判定不能再靠"谁命中多":
        # 只要出现公司的**独有标记字段**(统计周次/提交成员/…), 就一定判成公司表 ——
        # 这条判据不随补列漂移; 只有交叠列时则退回兜底逻辑(此处不足 3 列 -> 识别不出)。
        self.assertEqual(detect_schema_profile({"检索节约工时(h)", "其他任务数"}), "")
        self.assertEqual(detect_schema_profile(
            {"统计周次", "提交成员", "检索节约工时(h)", "其他任务数"}), SCHEMA_COMPANY)
        standard_names = {f["field_name"] for f in TABLE_SCHEMA_FIELDS}
        self.assertEqual(detect_schema_profile(standard_names), SCHEMA_STANDARD)
        self.assertEqual(detect_schema_profile({"甲", "乙"}), "")

        # 2) 周期标签
        rep = AggregateReport(
            period_type="weekly", period_name="2026年 第37周",
            start_date="2026-09-07", end_date="2026-09-13",
            retrieval_count=44, download_count=215,
            highlight_count=150, highlight_pages=2917, total_saved_hours=20.19,
        )
        self.assertEqual(week_label(rep), "2026-W37")
        self.assertEqual(week_label(AggregateReport(
            period_type="monthly", period_name="2026年09月",
            start_date="2026-09-01", end_date="2026-09-30")), "2026-09")
        self.assertEqual(week_label(AggregateReport(
            period_type="all_time", period_name="历史累计",
            start_date="", end_date="")), "历史累计")

        # 3) 写入映射：payload 字段必须与目标表完全一致，多余字段被丢弃
        cfg = {
            "user": {"nickname": "Devin"},
            "feishu": {
                "company_bitable_schema": "company",
                "company_bitable_project": "via54Medit",
                "company_bitable_member": "Devin Wei",
            },
        }
        mgr = FeishuBitableManager(config=cfg)
        payload = mgr.build_company_payload(rep, "Devin")
        self.assertEqual(set(payload.keys()), COMPANY_TABLE_FIELDS)
        self.assertEqual(payload["记录标识"], "2026-W37_Devin_via54Medit")
        self.assertEqual(payload["统计周次"], "2026-W37")
        self.assertEqual(payload["提交成员"], "Devin Wei")
        self.assertEqual(payload["文献检索量"], 44)
        self.assertEqual(payload["成功下载量"], 215)
        self.assertEqual(payload["高亮标注量"], 150)
        self.assertEqual(payload["解析物理总页数"], 2917)
        self.assertEqual(payload["节省工时(小时)"], 20.19)
        # v5.4.43: 三个细分工时与其他类目现在都有专列, 不再是"被丢弃"
        self.assertEqual(payload["检索节约工时(h)"], 0.0)
        self.assertEqual(payload["高亮节约工时(h)"], 0.0)
        self.assertEqual(payload["其他任务数"], 0)
        self.assertIn("API调用次数", payload)
        self.assertEqual(payload["项目任务类型"], "via54Medit")
        self.assertEqual(payload["数据状态"], "已自动同步")
        # 日期字段必须是毫秒时间戳：ISO 字符串会被飞书拒绝 (1254064)
        self.assertIsInstance(payload["统计日期"], int)
        self.assertEqual(payload["统计日期"], 1788710400000)  # 2026-09-07 00:00 +08:00
        # 只有"身份标识"没有专列 —— 且是**显式**决策, 不是默默丢
        for absent in ("成员OpenID", "汇报周期", "成员花名"):
            self.assertNotIn(absent, payload)
        from telemetry.bitable_sync import INTENTIONALLY_NOT_A_COLUMN
        self.assertIn("成员OpenID", INTENTIONALLY_NOT_A_COLUMN,
                      "没列就必须有理由 —— 这是对齐契约的另一半")

        # 4) 标准表路径不受影响
        std_payload = mgr.build_standard_payload(rep, "Devin", "ou_x")
        self.assertEqual(set(std_payload.keys()), standard_names)
        self.assertEqual(std_payload["上报状态"], "🟢 自动同步")

        # 5) 读取归一化：公司表字段 -> 标准字段，未知字段原样保留
        norm = FeishuBitableManager.normalize_record_fields({
            "统计周次": "2026-W37", "提交成员": "Devin Wei",
            "文献检索量": 44, "成功下载量": 215, "自定义列": "保留",
        }, SCHEMA_COMPANY)
        self.assertEqual(norm["汇报周期"], "2026-W37")
        self.assertEqual(norm["成员花名"], "Devin Wei")
        self.assertEqual(norm["文献检索篇数"], 44)
        self.assertEqual(norm["文献下载篇数"], 215)
        self.assertEqual(norm["自定义列"], "保留")
        # 标准表记录不做改动
        raw = {"汇报周期": "2026年 第37周", "成员花名": "wtg"}
        self.assertEqual(
            FeishuBitableManager.normalize_record_fields(raw, SCHEMA_STANDARD), raw)

    def test_bitable_company_upsert_key_consistency(self):
        """测试：幂等查找键必须与写入值一致，否则同一周会重复新增记录。"""
        from telemetry.bitable_sync import FeishuBitableManager, SCHEMA_COMPANY
        from telemetry.models import AggregateReport

        cfg = {
            "user": {"nickname": "Devin"},
            "feishu": {
                "company_bitable_schema": "company",
                "company_bitable_project": "via54Medit",
                "company_bitable_member": "Devin Wei",
            },
        }
        rep = AggregateReport(
            period_type="weekly", period_name="2026年 第37周",
            start_date="2026-09-07", end_date="2026-09-13")
        mgr = FeishuBitableManager(config=cfg)

        # 写入用的是映射后的显示名
        self.assertEqual(mgr.build_company_payload(rep, "Devin")["提交成员"], "Devin Wei")
        # 显式传入其他成员名时不被本机映射覆盖
        self.assertEqual(mgr.build_company_payload(rep, "Sarah")["提交成员"], "Sarah")

        # 表中已存在同一周、成员显示名为 Devin Wei 的记录
        existing = [{
            "record_id": "rec_existing",
            "fields": {"统计周次": "2026-W37", "提交成员": "Devin Wei"},
        }]
        mgr._api_request = lambda *a, **k: {"code": 0, "data": {"items": existing}}
        found = mgr._find_existing_record(rep, "Devin", SCHEMA_COMPANY)
        self.assertIsNotNone(found, "同周同成员应命中已有记录，否则会重复新增")
        self.assertEqual(found[0], "rec_existing")
        # 其他成员不应命中
        self.assertIsNone(mgr._find_existing_record(rep, "Sarah", SCHEMA_COMPANY))

    def test_bitable_local_backup_is_schema_agnostic(self):
        """测试：本地备份固定为当前标准字段列序，兼容并修复历史错位行。"""
        import csv as _csv
        from telemetry.bitable_sync import (
            FeishuBitableManager, BACKUP_FIELDS, COMPANY_PAYLOAD_ORDER,
            COMPANY_PAYLOAD_ORDER_LEGACY, SCHEMA_COMPANY, SCHEMA_STANDARD,
        )
        from telemetry.models import AggregateReport

        cfg = {
            "user": {"nickname": "Devin"},
            "feishu": {"company_bitable_member": "Devin Wei",
                       "company_bitable_project": "via54Medit"},
        }
        rep = AggregateReport(
            period_type="weekly", period_name="2026年 第37周",
            start_date="2026-09-07", end_date="2026-09-13",
            retrieval_count=44, download_count=215,
            highlight_count=150, highlight_pages=2917, total_saved_hours=20.19)

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "backup.csv")
            mgr = FeishuBitableManager(config=cfg)
            mgr._backup_csv_path = lambda: path

            # 1) 公司 schema 落盘后仍是标准表头, 不再产生错位行。
            #    列数断言跟着 BACKUP_FIELDS 走 —— 写死 15 会随每次加字段而假红。
            ncols = len(BACKUP_FIELDS)
            mgr._record_local_csv(mgr.build_company_payload(rep, "Devin"), SCHEMA_COMPANY)
            with open(path, encoding="utf-8-sig", newline="") as f:
                rows = list(_csv.reader(f))
            self.assertEqual(rows[0], BACKUP_FIELDS)
            self.assertEqual(len(rows[0]), ncols)
            self.assertEqual(len(rows[1]), ncols)
            self.assertEqual(
                rows[0][:4], ["汇报周期", "成员花名", "成员OpenID", "上报时间"])

            # 2) 标准 schema 落盘后列语义不变，同一文件可混写
            mgr._record_local_csv(
                mgr.build_standard_payload(rep, "Devin", "ou_x"), SCHEMA_STANDARD)
            with open(path, encoding="utf-8-sig", newline="") as f:
                rows = list(_csv.reader(f))
            self.assertTrue(all(len(r) == ncols for r in rows), "所有行必须与表头等宽")

            # 3) 回读：两种 schema 的记录都归一化为标准字段名
            recs = mgr._load_local_csv_records()
            self.assertEqual(len(recs), 2)
            self.assertEqual({r.get("汇报周期") for r in recs}, {"2026-W37", "2026年 第37周"})
            for r in recs:
                self.assertIn("成员花名", r)
                self.assertNotIn("统计周次", r, "不应残留公司字段名")
                self.assertNotIn("提交成员", r, "不应残留公司字段名")

            # 4) 历史错位行：13 列公司数据被追加到 15 列标准表头下，按列序还原
            legacy = os.path.join(d, "legacy.csv")
            mgr._backup_csv_path = lambda: legacy
            # 13 列是**历史**列序, 已冻结为 COMPANY_PAYLOAD_ORDER_LEGACY。
            # 若让它跟着 COMPANY_FIELD_MAP 一起变长, 这些历史行就再也认不出来,
            # 回退路径会静默丢行 —— 所以这里同时钉住"两个列序"的关系。
            self.assertEqual(len(COMPANY_PAYLOAD_ORDER_LEGACY), 13)
            self.assertGreater(len(COMPANY_PAYLOAD_ORDER), 13,
                               "当前列序应随映射扩展而变长")
            legacy_values = [
                "2026-W37_Devin_via54Medit", "2026-W37", "Devin Wei",
                "2026-09-07T00:00:00.000+08:00", 44, 215, 150, 2917,
                20.19, 0, "via54Medit", "已自动同步", "自动同步",
            ]
            with open(legacy, "w", encoding="utf-8-sig", newline="") as f:
                w = _csv.writer(f)
                w.writerow(BACKUP_FIELDS)
                w.writerow(legacy_values)
            recs = mgr._load_local_csv_records()
            self.assertEqual(len(recs), 1)
            self.assertEqual(recs[0]["汇报周期"], "2026-W37")
            self.assertEqual(recs[0]["成员花名"], "Devin Wei")
            self.assertEqual(recs[0]["文献检索篇数"], "44")
            self.assertEqual(recs[0]["文献下载篇数"], "215")
            # 标注篇数 / 阅读页数是易错的一对，必须各归各位
            self.assertEqual(recs[0]["Highlight标注篇数"], "150")
            self.assertEqual(recs[0]["Highlight阅读页数"], "2917")
            self.assertEqual(recs[0]["总节约工时(h)"], "20.19")

            # 5) 追加写会留下重复行，回读时按 (周期, 成员) 折叠，避免图表数据翻倍
            with open(legacy, "a", encoding="utf-8-sig", newline="") as f:
                _csv.writer(f).writerow(legacy_values)
            self.assertEqual(len(mgr._load_local_csv_records()), 1)

            # 6) 完全无法对齐的脏行跳过，不猜测
            with open(legacy, "a", encoding="utf-8-sig", newline="") as f:
                _csv.writer(f).writerow(["只有", "三", "列"])
            self.assertEqual(len(mgr._load_local_csv_records()), 1)

    def test_bitable_dry_run_has_no_side_effect(self):
        """测试：dry-run 只输出 payload，不写本地备份、不发起 API 请求。"""
        from telemetry.bitable_sync import (
            FeishuBitableManager, SCHEMA_COMPANY, COMPANY_TABLE_FIELDS)
        from telemetry.models import AggregateReport

        cfg = {
            "user": {"nickname": "Devin"},
            "feishu": {"company_bitable_member": "Devin Wei",
                       "company_bitable_project": "via54Medit"},
        }
        rep = AggregateReport(
            period_type="weekly", period_name="2026年 第37周",
            start_date="2026-09-07", end_date="2026-09-13",
            retrieval_count=44, download_count=215,
            highlight_count=150, highlight_pages=2917, total_saved_hours=20.19)

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "backup.csv")
            mgr = FeishuBitableManager(config=cfg)
            mgr._backup_csv_path = lambda: path
            mgr.app_token, mgr.table_id = "bascn_test", "tbl_test"
            mgr.resolve_schema = lambda: (SCHEMA_COMPANY, "test")
            calls = []
            mgr._api_request = lambda *a, **k: calls.append((a, k)) or {"code": 0}

            ok, msg = mgr.sync_weekly_report(rep, "Devin", dry_run=True)

            self.assertTrue(ok, msg)
            payload = json.loads(msg)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(set(payload["fields"].keys()), COMPANY_TABLE_FIELDS)
            self.assertFalse(os.path.exists(path), "dry-run 不应写本地备份")
            # dry-run 允许**只读**探测 —— 它要告诉你"目标表缺哪些列"就必须读 schema,
            # 否则"这些值到底写不写得进去"在提交前根本无从得知。写入则一律禁止。
            mutations = [c for c in calls if (c[1].get("method") or "GET") != "GET"]
            self.assertEqual(mutations, [], "dry-run 绝不能发起写请求")
            # 缺列时把话说清楚, 而不是等提交后才发现值被丢了
            self.assertIn("missing_columns", payload)

    def test_bitable_note_protection_follows_custom_field_map(self):
        """测试：备注列被配置改名后，人工填写的备注仍受保护。"""
        from telemetry.bitable_sync import FeishuBitableManager, SCHEMA_COMPANY
        from telemetry.models import AggregateReport

        cfg = {
            "user": {"nickname": "Devin"},
            "feishu": {
                "company_bitable_member": "Devin Wei",
                "company_bitable_project": "via54Medit",
                "company_bitable_field_map": {"备注说明": "手工备注"},
            },
        }
        rep = AggregateReport(
            period_type="weekly", period_name="2026年 第37周",
            start_date="2026-09-07", end_date="2026-09-13",
            retrieval_count=44, download_count=215,
            highlight_count=150, highlight_pages=2917, total_saved_hours=20.19)
        mgr = FeishuBitableManager(config=cfg)

        payload = mgr.build_company_payload(rep, "Devin")
        self.assertIn("手工备注", payload, "写入侧应使用改名后的备注列")
        self.assertNotIn("备注说明", payload)

        captured = {}

        def fake_api(endpoint, method="GET", body=None):
            if method == "PUT":
                captured["fields"] = (body or {}).get("fields", {})
                return {"code": 0}
            return {"code": 0, "data": {"items": [{
                "record_id": "rec_note",
                "fields": {"统计周次": "2026-W37", "提交成员": "Devin Wei",
                           "手工备注": "人工填写的说明"},
            }]}}

        with tempfile.TemporaryDirectory() as d:
            mgr._backup_csv_path = lambda: os.path.join(d, "backup.csv")
            mgr.app_token, mgr.table_id = "bascn_test", "tbl_test"
            mgr.resolve_schema = lambda: (SCHEMA_COMPANY, "test")
            mgr._api_request = fake_api

            ok, msg = mgr.sync_weekly_report(rep, "Devin")

        self.assertTrue(ok, msg)
        self.assertIn("文献检索量", captured["fields"], "其他列应正常更新")
        self.assertNotIn("手工备注", captured["fields"], "人工备注不应被覆盖")

    def test_envcheck_detects_conflicting_python_env(self):
        """测试：环境自检识别 PYTHONHOME / PYTHONPATH 冲突并给出可复制的修复命令。"""
        import sys as _sys
        from telemetry import envcheck

        ver = envcheck.current_version()
        other = "3.10" if ver != "3.10" else "3.11"

        # 1) 干净环境 -> 无冲突
        self.assertEqual(envcheck.collect_issues({}), [])

        # 2) PYTHONHOME 指向别的解释器 -> 严重 (实测会导致解释器启动阶段崩溃)
        issues = envcheck.collect_issues({"PYTHONHOME": "/opt/other/python/3.10"})
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].level, "error")
        self.assertIn("PYTHONHOME", issues[0].title)

        # 3) PYTHONHOME 与本解释器前缀一致 -> 不误报
        self.assertEqual(envcheck.collect_issues({"PYTHONHOME": _sys.base_prefix}), [])

        # 4) PYTHONPATH 注入别的 Python 版本的库路径 -> 提示; 同版本 -> 不报
        foreign = f"/opt/other/python{other}/lib/python{other}/site-packages"
        issues = envcheck.collect_issues({"PYTHONPATH": foreign})
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].level, "warning")
        same = f"/opt/same/python{ver}/lib/python{ver}/site-packages"
        self.assertEqual(envcheck.collect_issues({"PYTHONPATH": same}), [])

        # 5) 渲染出人话提示与可直接复制的修复命令; 无冲突时渲染为空
        text = envcheck.render(
            envcheck.collect_issues({"PYTHONHOME": "/opt/other/python/3.10"}))
        self.assertIn("env -u PYTHONHOME -u PYTHONPATH", text)
        self.assertIn("unset PYTHONHOME PYTHONPATH", text)
        self.assertIn("后台守护进程", text)
        self.assertEqual(envcheck.render([]), "")

    def test_envcheck_warns_only_once(self):
        """测试：同一进程内只提示一次；显式自检无论如何都给出结论。"""
        import io
        from unittest import mock
        from telemetry import envcheck

        conflict = {"PYTHONHOME": "/opt/other/python/3.10"}
        with mock.patch.dict(os.environ, conflict, clear=False):
            envcheck.reset_warning_state()
            buf = io.StringIO()
            self.assertTrue(envcheck.warn_if_needed(stream=buf))
            self.assertIn("运行环境自检", buf.getvalue())
            # 第二次不再重复刷屏
            self.assertFalse(envcheck.warn_if_needed(stream=io.StringIO()))
            # 显式自检始终有结论
            report = envcheck.render_self_check()
            self.assertIn("medit-telemetry 运行环境自检", report)
            self.assertIn("检测到 Python 环境变量冲突", report)
            envcheck.reset_warning_state()

        # 外壳启动器已拦截并提示过时, 不再重复刷屏
        with mock.patch.dict(os.environ,
                             {**conflict, envcheck.ISOLATED_ENV_VAR: "1"}, clear=False):
            envcheck.reset_warning_state()
            self.assertFalse(envcheck.warn_if_needed(stream=io.StringIO(), force=True))
            # 但显式自检仍完整给出结论, 并标注本次已被启动器接管
            report = envcheck.render_self_check()
            self.assertIn("启动器", report)
            self.assertIn("本次已忽略 PYTHON* 变量执行", report)
            envcheck.reset_warning_state()

        # 无冲突时自检给出通过结论
        with mock.patch.dict(os.environ, {"PYTHONHOME": "", "PYTHONPATH": ""}, clear=False):
            self.assertIn("未发现冲突", envcheck.render_self_check())

        # 无冲突时不打印任何东西
        with mock.patch.dict(os.environ, {"PYTHONHOME": "", "PYTHONPATH": ""}, clear=False):
            envcheck.reset_warning_state()
            self.assertFalse(envcheck.warn_if_needed(stream=io.StringIO()))

    def test_guarded_launcher_template(self):
        """测试：外层启动器模板存在、shell 语法合法、占位符与兜底路径正确。"""
        import subprocess
        import sys as _sys
        from telemetry import deploy

        template = os.path.join(
            os.path.dirname(os.path.abspath(deploy.__file__)), "scripts", "medit-telemetry")
        self.assertTrue(os.path.exists(template), "启动器模板缺失")

        with open(template, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("__MEDITELEMETRY_PYTHON__", content)
        self.assertIn('exec "$PYTHON" -m telemetry.cli "$@"', content)
        # 冲突时才传 -E, 平静环境下不得改变行为
        self.assertIn('exec "$PYTHON" -E -m telemetry.cli "$@"', content)

        # shell 语法检查 (只解析, 不执行): 模板与替换解释器后的成品都要合法
        for payload in (content, content.replace("__MEDITELEMETRY_PYTHON__", _sys.executable)):
            with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False,
                                             encoding="utf-8") as tmp:
                tmp.write(payload)
                tmp_path = tmp.name
            try:
                res = subprocess.run(["sh", "-n", tmp_path],
                                     capture_output=True, text=True)
                self.assertEqual(res.returncode, 0, res.stderr)
            finally:
                os.unlink(tmp_path)

    def test_guarded_launcher_missing_template_is_graceful(self):
        """测试：模板缺失时给出可操作指引并优雅退出，不写任何文件。"""
        import contextlib
        import io
        from telemetry import deploy

        real_dir = deploy.TELEMETRY_DIR
        buf = io.StringIO()
        try:
            deploy.TELEMETRY_DIR = os.path.join(
                tempfile.gettempdir(), "medit-no-such-dir-for-test")
            with contextlib.redirect_stdout(buf):
                ok = deploy.install_guarded_launcher()
        finally:
            deploy.TELEMETRY_DIR = real_dir

        self.assertFalse(ok, "模板缺失时应返回 False 而不是抛异常")
        out = buf.getvalue()
        self.assertIn("未找到启动器模板", out)
        # 模板已随包分发, 缺失即提示重装, 而不是轻描淡写成「正常情况」
        self.assertIn("pip install -U medit-telemetry", out)

    def test_launcher_template_is_declared_as_package_data(self):
        """测试：启动器模板被声明为包数据。

        scripts/ 目录没有 __init__.py，setuptools 不会把它当包、也就不会自动打包其中的
        文件；若不显式声明 package-data，从 wheel / sdist 安装时模板会缺失，部署时就装不出
        环境自检启动器（这正是 5.4.0 的「已知边界」）。这里锁住声明，防止回归。
        """
        from telemetry import deploy

        pkg_dir = os.path.dirname(os.path.abspath(deploy.__file__))
        self.assertTrue(
            os.path.exists(os.path.join(pkg_dir, "scripts", "medit-telemetry")),
            "启动器模板缺失")
        # 前提条件：scripts/ 不是 Python 包，因此必须靠 package-data 显式声明
        self.assertFalse(
            os.path.exists(os.path.join(pkg_dir, "scripts", "__init__.py")),
            "scripts/ 若变为 Python 包，打包假设需重新评估")

        with open(os.path.join(pkg_dir, "pyproject.toml"), "r", encoding="utf-8") as f:
            pyproject = f.read()
        self.assertIn("[tool.setuptools.package-data]", pyproject)
        self.assertRegex(pyproject, r'telemetry\s*=\s*\[\s*"scripts/\*"\s*\]')

        with open(os.path.join(pkg_dir, "setup.py"), "r", encoding="utf-8") as f:
            setup_py = f.read()
        self.assertRegex(setup_py, r'package_data\s*=\s*\{\s*"telemetry"\s*:\s*\["scripts/\*"\]\s*\}')


    def test_deploy_pep668_not_bypassed_by_default(self):
        """测试：默认**不**绕过 PEP 668 —— 那是解释器管理方划下的边界。

        被拒时改为 .pth 注入（只保证可导入），命令由启动器落到 PATH，功能照常可用；
        同时必须明确告知显式开启逃生开关的方式。
        """
        import contextlib
        import io
        from unittest import mock
        from telemetry import deploy

        # 逃生开关绝不能出现在默认命令序列里
        for cmd in deploy._editable_install_cmds():
            self.assertNotIn("--break-system-packages", cmd)

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(list(cmd))
            return mock.Mock(returncode=1, stdout="",
                             stderr="error: externally-managed-environment")

        buf = io.StringIO()
        with mock.patch.object(deploy.subprocess, "run", side_effect=fake_run), \
                mock.patch.object(deploy, "_fallback_pth_install",
                                  return_value=True) as pth, \
                contextlib.redirect_stdout(buf):
            ok = deploy.install_package_locally()

        self.assertTrue(ok)
        pth.assert_called_once()
        self.assertTrue(all("--break-system-packages" not in c for c in calls),
                        "未经授权不得使用逃生开关")
        out = buf.getvalue()
        self.assertIn("PEP 668", out)
        self.assertIn("--allow-break-system-packages", out)

    def test_deploy_pep668_retries_only_when_allowed(self):
        """测试：显式授权后才追加 --break-system-packages 原地重试。"""
        from unittest import mock
        from telemetry import deploy

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(list(cmd))
            if "--break-system-packages" in cmd:
                return mock.Mock(returncode=0, stdout="Successfully installed", stderr="")
            return mock.Mock(returncode=1, stdout="",
                             stderr="error: externally-managed-environment")

        with mock.patch.object(deploy.subprocess, "run", side_effect=fake_run):
            ok = deploy.install_package_locally(allow_break_system_packages=True)

        self.assertTrue(ok)
        self.assertEqual(calls[0][:4], [sys.executable, "-m", "pip", "install"])
        self.assertNotIn("--break-system-packages", calls[0])
        self.assertIn("--break-system-packages", calls[1])

    def test_deploy_falls_back_to_pth_when_all_installs_fail(self):
        """测试：pip / uv 全部失败时才退回 .pth 注入（只保证可导入）。"""
        from unittest import mock
        from telemetry import deploy

        fail = mock.Mock(returncode=1, stdout="", stderr="boom: cannot install")
        with mock.patch.object(deploy.subprocess, "run", return_value=fail), \
                mock.patch.object(deploy, "_fallback_pth_install",
                                  return_value=True) as pth:
            ok = deploy.install_package_locally()

        self.assertTrue(ok)
        pth.assert_called_once()

    def test_launcher_targets_cover_both_command_names(self):
        """测试：命令不存在时落到可写 bin 目录新建，而不是放弃安装。"""
        from unittest import mock
        from telemetry import deploy

        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(deploy, "shutil") as fake_shutil, \
                    mock.patch.object(deploy, "_writable_bin_dir", return_value=d):
                fake_shutil.which.return_value = None
                targets = deploy._launcher_targets()

            self.assertEqual(len(targets), 2, "两个命令名都要有目标")
            self.assertEqual(
                {os.path.basename(p) for p in targets},
                {"medit-telemetry", "traework-telemetry"})
            self.assertTrue(all(os.path.dirname(p) == d for p in targets))

            # 已存在的命令优先复用（可能在软链后面）
            with mock.patch.object(deploy, "shutil") as fake_shutil, \
                    mock.patch.object(deploy, "_writable_bin_dir", return_value=d):
                fake_shutil.which.return_value = "/usr/local/bin/medit-telemetry"
                reused = deploy._launcher_targets()
            self.assertEqual(reused, ["/usr/local/bin/medit-telemetry"] * 2)

    def test_nlp_deploy_escape_hatch_intent(self):
        """测试：只有「强制安装」类表述才开启逃生开关，默认保持关闭。"""
        from telemetry.nlp_deploy import parse_natural_language_instruction as parse

        self.assertFalse(
            parse("在新设备上部署监控，花名叫星云")
            .get("allow_break_system_packages"),
            "普通部署不得默认开启逃生开关")
        self.assertTrue(
            parse("强制安装到系统解释器，花名叫星云")
            .get("allow_break_system_packages"))
        self.assertTrue(
            parse("部署监控 --break-system-packages")
            .get("allow_break_system_packages"))

    def test_platform_paths_user_bin_dirs_and_path_check(self):
        """测试：跨平台 bin 目录候选与 PATH 判定（命令装完能不能被找到）。"""
        from telemetry import platform_paths as pp

        dirs = pp.user_bin_dirs()
        self.assertTrue(dirs, "至少应给出一个候选目录")
        self.assertEqual(len(dirs), len(set(dirs)), "候选目录不应重复")
        if sys.platform == "win32":
            self.assertTrue(any(d.endswith("Scripts") for d in dirs))
        else:
            self.assertIn(
                os.path.join(os.path.expanduser("~"), ".local", "bin"), dirs)

        first_on_path = next(
            (p for p in (os.environ.get("PATH") or "").split(os.pathsep) if p), "")
        if first_on_path:
            self.assertTrue(pp.is_on_path(first_on_path))
        self.assertFalse(pp.is_on_path(
            os.path.join(tempfile.gettempdir(), "medit-definitely-not-on-path")))


class TestOtherCategory(unittest.TestCase):
    """「其他」类目: 与三类一样统计**工作时长**与 **Token 消耗**。

    口径(见 telemetry/models.py 的类目归类与 aggregator 的累加处):
      * 类目归属唯一事实来源是 ``classify_task_type``; **未知 task_type 一律兜底到 other**,
        免得将来多出一种任务类型就从战报里消失;
      * Token 与总量**同源同口径**算出, 因此 ``other.total_tokens ⊆ tokens.total_tokens``;
      * 其他类目**没有人工基准, 不产出"节约工时"** —— 宁可不给也不编。
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "t.db")
        self.db = TelemetryDB(self.db_path)
        self.tracker = TelemetryTracker(self.db)
        self.aggregator = TelemetryAggregator(self.db)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # ---- 归类 ----

    def test_unknown_task_type_falls_back_to_other(self):
        from telemetry.models import classify_task_type, CATEGORY_OTHER
        for raw in ("scan", "ppt_render", "whatever_new", "", None):
            self.assertEqual(classify_task_type(raw), CATEGORY_OTHER,
                             "%r 应兜底到 other, 不该从战报里消失" % (raw,))

    def test_known_task_types_keep_their_category(self):
        from telemetry.models import classify_task_type
        self.assertEqual(classify_task_type("retrieval"), "retrieval")
        self.assertEqual(classify_task_type("download"), "download")
        self.assertEqual(classify_task_type("highlight"), "highlight")
        self.assertEqual(classify_task_type(TaskType.RETRIEVAL), "retrieval")
        # 修正属于高亮质检环节
        self.assertEqual(classify_task_type("correction"), "highlight")

    # ---- 工时 ----

    def test_track_other_records_duration_and_tokens(self):
        with self.tracker.track_other(project_name="RSV", label="ppt_render") as col:
            col.add_tokens(prompt_tokens=1200, completion_tokens=300)

        tasks = [t for t in self.db.query_tasks() if str(t["task_id"]).startswith("other_")]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_type"], "other")
        self.assertGreater(tasks[0]["duration_seconds"], 0)
        self.assertEqual(tasks[0]["total_tokens"], 1500)

        rep = self.aggregator.get_all_time_report()
        self.assertEqual(rep.other_count, 1)
        self.assertGreater(rep.other_duration_seconds, 0)
        self.assertEqual(rep.other_total_tokens, 1500)

    def test_other_is_kept_out_of_the_three_business_categories(self):
        """其他工作不得漏进检索/下载/高亮 —— 归错类会让三类数字虚高。"""
        with self.tracker.track_other(project_name="X") as col:
            col.add_tokens(prompt_tokens=100, completion_tokens=100)

        rep = self.aggregator.get_all_time_report()
        self.assertEqual((rep.retrieval_count, rep.download_count, rep.highlight_count), (0, 0, 0))
        self.assertEqual(rep.total_saved_seconds, 0.0, "其他类目不产生节约工时")

    def test_track_other_marks_failure_and_still_records(self):
        with self.assertRaises(RuntimeError):
            with self.tracker.track_other(project_name="X"):
                raise RuntimeError("boom")
        rows = [t for t in self.db.query_tasks() if str(t["task_id"]).startswith("other_")]
        self.assertEqual(rows[0]["status"], "failed")

    # ---- Token 归口 ----

    def test_unattributed_llm_call_lands_in_other(self):
        """没有 task_id 归属的调用归入「其他」, 并单独计数 —— 否则这个数字没法解读。"""
        from telemetry.token_tracker import record_llm_usage

        record_llm_usage(response={"usage": {"prompt_tokens": 30, "completion_tokens": 10,
                                            "total_tokens": 40}},
                         provider="deepseek", db=self.db)
        rep = self.aggregator.get_all_time_report()
        self.assertEqual(rep.total_tokens, 40, "总量口径不变")
        self.assertEqual(rep.other_total_tokens, 40)
        self.assertEqual(rep.other_unattributed_tokens, 40)

    def test_llm_call_linked_to_a_highlight_task_is_not_other(self):
        """能按 task_id 归到三类工作的调用, 不算"其他"。"""
        from telemetry.token_tracker import record_llm_usage

        with self.tracker.track_highlight(project_name="RSV") as col:
            col.add_item("P1", page_count=5, highlight_duration_seconds=10.0)
        task_id = self.db.query_tasks()[0]["task_id"]

        record_llm_usage(response={"usage": {"prompt_tokens": 10, "completion_tokens": 5,
                                            "total_tokens": 15}},
                         provider="deepseek", task_id=task_id, db=self.db)
        rep = self.aggregator.get_all_time_report()
        self.assertEqual(rep.total_tokens, 15)
        self.assertEqual(rep.other_total_tokens, 0, "已归属高亮的调用不该算进其他")
        self.assertEqual(rep.other_unattributed_tokens, 0)

    def test_other_tokens_are_a_subset_of_total(self):
        """子集关系由构造保证 —— 这条不变量一旦破了, 报表口径就自相矛盾。"""
        from telemetry.token_tracker import record_llm_usage

        with self.tracker.track_highlight(project_name="RSV") as col:
            col.add_item("P1", page_count=5, highlight_duration_seconds=1.0)
            col.add_tokens(prompt_tokens=200, completion_tokens=100)
        with self.tracker.track_other(project_name="RSV") as col:
            col.add_tokens(prompt_tokens=50, completion_tokens=50)
        record_llm_usage(response={"usage": {"total_tokens": 999}}, provider="zhipu", db=self.db)

        rep = self.aggregator.get_all_time_report()
        self.assertLessEqual(rep.other_total_tokens, rep.total_tokens,
                             "其他 Token 必须是总量的子集")
        self.assertLessEqual(rep.other_prompt_tokens, rep.total_prompt_tokens)
        self.assertLessEqual(rep.other_completion_tokens, rep.total_completion_tokens)

    def test_scan_task_tokens_stay_out_of_other_in_exact_mode(self):
        """scan_ 任务的估算不进总量, 也就不能进「其他」—— 否则子集关系被破坏。"""
        self.db.record_task(TaskRecord(
            task_id="scan_proj_123", task_type=TaskType.OTHER, project_name="proj",
            start_time="2026-09-01T00:00:00", end_time="2026-09-01T00:01:00",
            duration_seconds=60.0, total_tokens=777))
        rep = self.aggregator.get_all_time_report()
        self.assertEqual(rep.token_mode, "exact")
        self.assertEqual(rep.total_tokens, 0)
        self.assertEqual(rep.other_total_tokens, 0, "scan_ 任务不该把其他 Token 顶到总量之上")
        self.assertEqual(rep.other_count, 1, "工时仍要计入其他")

    # ---- 展示与推送 ----

    def test_to_dict_exposes_other_block(self):
        rep = self.aggregator.get_all_time_report()
        d = rep.to_dict()["other"]
        self.assertIn("duration_seconds", d)
        self.assertIn("total_tokens", d)
        self.assertIs(d["has_saved_baseline"], False,
                      "其他类目必须明确声明没有节约基准, 免得调用方自己补一个")

    def test_feishu_card_has_a_fourth_block(self):
        with self.tracker.track_other(project_name="RSV") as col:
            col.add_tokens(prompt_tokens=500, completion_tokens=100)
        rep = self.aggregator.get_all_time_report()
        card = FeishuSyncClient().build_card(rep)
        blob = json.dumps(card, ensure_ascii=False)
        self.assertIn("4. 其他工作", blob)
        self.assertIn("600", blob, "卡片应带上其他类目的 Token 数")

    def test_public_sheet_row_matches_column_definition(self):
        from telemetry.feishu_sync import PUBLIC_SHEET_COLUMNS, build_public_sheet_row

        with self.tracker.track_other(project_name="RSV") as col:
            col.add_tokens(prompt_tokens=700, completion_tokens=300)
        rep = self.aggregator.get_all_time_report()
        row = build_public_sheet_row(rep, "wtg", "ou_x")

        self.assertEqual(len(row), len(PUBLIC_SHEET_COLUMNS),
                         "数据行必须与列定义等宽, 否则云端追加会错位")
        self.assertEqual(PUBLIC_SHEET_COLUMNS[-3:], ["其他任务数", "其他工作时长(秒)", "其他Token消耗"])
        # 与 to_dict 的舍入口径对齐 (行数据取自 to_dict)
        self.assertEqual(row[-3:], [1, rep.to_dict()["other"]["duration_seconds"], 1000])

    def test_public_csv_header_is_migrated_and_history_preserved(self):
        """升级到含「其他」的列定义时, 历史行按列名搬迁, 新列留空。"""
        import csv as _csv
        from telemetry.feishu_sync import migrate_public_csv_columns, PUBLIC_SHEET_COLUMNS

        legacy_cols = PUBLIC_SHEET_COLUMNS[:-3]      # 加「其他」之前的 18 列
        path = os.path.join(self.test_dir, "public.csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = _csv.writer(f)
            w.writerow(legacy_cols)
            w.writerow([f"v{i}" for i in range(len(legacy_cols))])

        ok, note = migrate_public_csv_columns(path)
        self.assertTrue(ok, note)
        self.assertIn("新增列", note)

        with open(path, encoding="utf-8-sig", newline="") as f:
            rows = list(_csv.reader(f))
        self.assertEqual(rows[0], PUBLIC_SHEET_COLUMNS)
        body = dict(zip(rows[0], rows[1]))
        self.assertEqual(body["上报时间"], "v0")
        # 未被新列挤位的旧列必须原样保留 (按列名搬迁, 不是按位置)
        self.assertEqual(body["Token总消耗"], "v16")
        self.assertEqual(body["状态"], "v17")
        self.assertEqual(body["其他任务数"], "")
        self.assertEqual(body["其他Token消耗"], "")

    def test_public_csv_migration_is_idempotent(self):
        from telemetry.feishu_sync import migrate_public_csv_columns, PUBLIC_SHEET_COLUMNS
        import csv as _csv

        path = os.path.join(self.test_dir, "public.csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            _csv.writer(f).writerow(PUBLIC_SHEET_COLUMNS)
        ok, note = migrate_public_csv_columns(path)
        self.assertTrue(ok)
        self.assertEqual(note, "", "已是当前列定义时不该有任何迁移动作")

    def test_bitable_standard_payload_carries_other_fields(self):
        from telemetry.bitable_sync import FeishuBitableManager

        with self.tracker.track_other(project_name="RSV") as col:
            col.add_tokens(prompt_tokens=600, completion_tokens=200)
        rep = self.aggregator.get_all_time_report()
        payload = FeishuBitableManager(config={"feishu": {}}).build_standard_payload(
            rep, "Devin", "ou_x")
        self.assertEqual(payload["其他任务数"], 1)
        self.assertEqual(payload["其他Token消耗"], 800)
        self.assertIn("其他工作时长(h)", payload)

    def test_company_payload_carries_other_columns(self):
        """公司表**有**「其他」专列 (v5.4.43 补齐) —— 统计项必须落到列里。

        在此之前它们只能挤进「备注说明」当一段纯文本: 看得到, 但筛选不了、分组不了、
        画不了图。现在改为逐项成列, 备注只留一句人读的摘要。
        """
        from telemetry.bitable_sync import FeishuBitableManager, COMPANY_TABLE_FIELDS

        with self.tracker.track_other(project_name="RSV") as col:
            col.add_tokens(prompt_tokens=600, completion_tokens=200)
        rep = self.aggregator.get_all_time_report()
        payload = FeishuBitableManager(config={"feishu": {}}).build_company_payload(rep, "Devin")

        # 统计项落到**列**里, 而不是只出现在备注文本中
        self.assertEqual(payload["其他任务数"], 1)
        self.assertEqual(payload["其他Token消耗"], 800)
        self.assertIn("其他工作时长(h)", payload)
        self.assertIn("其他未归属Token", payload)
        self.assertIn("API调用次数", payload)
        for key in payload:
            self.assertIn(key, COMPANY_TABLE_FIELDS,
                          "公司表 payload 不得写入它没有的列 (%s)" % key)
        # 备注只留人读的摘要: 其他类目已有专列, 再往备注里塞一遍数字就是同一份账记两次
        note = payload["备注说明"]
        self.assertIn("其他", note)
        self.assertNotIn("800", note, "备注不该重复承载已有专列的数值")

    def test_team_chart_aggregation_tolerates_missing_other_columns(self):
        """公司表 schema 读回来的记录没有「其他」三列, 不能因此被判成脏数据。"""
        from telemetry.chart_reporter import aggregate_team_metrics

        records = [
            {"成员花名": "A", "汇报周期": "2026-W37", "总节约工时(h)": "3.5",
             "文献检索篇数": "10", "文献下载篇数": "2",
             "Highlight阅读页数": "30", "Highlight标注篇数": "3", "真实Token消耗": "1000",
             "其他任务数": "4", "其他工作时长(h)": "1.5", "其他Token消耗": "250"},
            {"成员花名": "B", "汇报周期": "2026-W37", "总节约工时(h)": "1.0",
             "文献检索篇数": "5", "文献下载篇数": "1",
             "Highlight阅读页数": "10", "Highlight标注篇数": "1", "真实Token消耗": "500"},
        ]
        summary = aggregate_team_metrics(records)
        self.assertEqual(summary["team_size"], 2, "缺列不该让整条记录被丢弃")
        self.assertEqual(summary["total_other_count"], 4)
        self.assertAlmostEqual(summary["total_other_hours"], 1.5)
        self.assertEqual(summary["total_other_tokens"], 250)
        self.assertEqual(summary["total_saved_hours"], 4.5, "主口径不受影响")


class TestScheduleDefaults(unittest.TestCase):
    """默认排程: 周报每周一 10:30 / 月报每月 1 日 10:30。"""

    def test_default_config_uses_the_new_times(self):
        from telemetry.config import (
            DEFAULT_CONFIG, DEFAULT_MONTHLY_SCHEDULE, DEFAULT_REMINDER_SCHEDULE,
            DEFAULT_WEEKLY_SCHEDULE,
        )
        self.assertEqual(DEFAULT_WEEKLY_SCHEDULE["day_of_week"], 0)
        self.assertEqual(DEFAULT_WEEKLY_SCHEDULE["time"], "10:30")
        self.assertEqual(DEFAULT_MONTHLY_SCHEDULE["day_of_month"], 1)
        self.assertEqual(DEFAULT_MONTHLY_SCHEDULE["time"], "10:30")
        self.assertEqual(DEFAULT_CONFIG["schedule"]["weekly"]["time"], "10:30")
        self.assertEqual(DEFAULT_CONFIG["schedule"]["monthly"]["time"], "10:30")
        self.assertTrue(DEFAULT_CONFIG["schedule"]["reminder"]["enabled"])
        self.assertEqual(DEFAULT_CONFIG["schedule"]["reminder"]["time"],
                         DEFAULT_REMINDER_SCHEDULE["time"])

    def test_defaults_are_not_duplicated_as_literals(self):
        """回归: 默认时间曾散落在三处字面量里(09:00 抄三遍), 改一处就会漏另一处。

        这里直接查源码: daemon 的兜底取值与 nlp_deploy 的默认值都不得再写死 09:00。
        """
        import telemetry.daemon as daemon
        import telemetry.nlp_deploy as nlp_deploy

        for mod in (daemon, nlp_deploy):
            with open(mod.__file__, encoding="utf-8") as fh:
                src = fh.read()
            self.assertNotIn('"09:00"', src, "%s 里仍有写死的 09:00 兜底" % mod.__name__)

    def test_nlp_defaults_follow_config(self):
        from telemetry.nlp_deploy import parse_natural_language_instruction

        got = parse_natural_language_instruction("花名wtg，每周一汇报")
        self.assertEqual(got["weekly"], "周一 10:30", "未写明时间时应回退到默认排程")

    # ---- 默认值迁移 ----

    def _load(self, saved):
        from telemetry import config as cfgmod

        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        path = os.path.join(tmp, "telemetry_config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(saved, f, ensure_ascii=False)
        with mock.patch.object(cfgmod, "CONFIG_FILE_PATH", path), \
                mock.patch.object(cfgmod, "trae_work_config_candidates", return_value=[]):
            cfg = cfgmod.load_config()
        with open(path, encoding="utf-8") as f:
            return cfg, json.load(f)

    def test_old_default_is_upgraded(self):
        """已部署的设备把 09:00 写进了配置文件 —— 只改 DEFAULT_CONFIG 对它无效。"""
        cfg, on_disk = self._load({"schedule": {
            "weekly": {"enabled": True, "day_of_week": 0, "time": "09:00"},
            "monthly": {"enabled": True, "day_of_month": 1, "time": "09:00"}}})
        self.assertEqual(cfg["schedule"]["weekly"]["time"], "10:30")
        self.assertEqual(cfg["schedule"]["monthly"]["time"], "10:30")
        self.assertEqual(on_disk["schedule"]["weekly"]["time"], "10:30", "应已落盘")
        self.assertEqual(on_disk.get("schedule_defaults_version"), 2)

    def test_customised_schedule_is_never_touched(self):
        """用户自己设过的时间一律不碰 —— 迁移只针对"仍是旧默认值"的。"""
        cfg, _ = self._load({"schedule": {
            "weekly": {"enabled": True, "day_of_week": 4, "time": "18:00"},
            "monthly": {"enabled": True, "day_of_month": -1, "time": "20:15"}}})
        self.assertEqual(cfg["schedule"]["weekly"]["time"], "18:00")
        self.assertEqual(cfg["schedule"]["weekly"]["day_of_week"], 4)
        self.assertEqual(cfg["schedule"]["monthly"]["time"], "20:15")
        self.assertEqual(cfg["schedule"]["monthly"]["day_of_month"], -1)

    def test_deliberate_change_back_to_old_default_is_respected(self):
        """迁移只做一次: 否则用户将来**故意**改回 09:00 又会被悄悄顶掉。"""
        cfg, _ = self._load({"schedule_defaults_version": 2, "schedule": {
            "weekly": {"enabled": True, "day_of_week": 0, "time": "09:00"},
            "monthly": {"enabled": True, "day_of_month": 1, "time": "09:00"}}})
        self.assertEqual(cfg["schedule"]["weekly"]["time"], "09:00")
        self.assertEqual(cfg["schedule"]["monthly"]["time"], "09:00")

    def test_reminder_section_is_backfilled_for_old_configs(self):
        cfg, _ = self._load({"schedule": {"weekly": {"enabled": True, "day_of_week": 0,
                                                     "time": "09:00"}}})
        self.assertTrue(cfg["schedule"]["reminder"]["enabled"])
        self.assertEqual(cfg["schedule"]["reminder"]["time"], "18:00")


#: 2026 年法定节假日报文(完整) —— 摘自 国办发明电〔2025〕7 号
#: 《国务院办公厅关于2026年部分节假日安排的通知》
#: https://www.gov.cn/zhengce/zhengceku/202511/content_7047091.htm
#: 对应的 holiday-cn 报文。逐条核对过: 33 天放假 + 6 天补班。
#:
#: ⚠️ 这里必须是**完整**的一年, 不能只挑测试"用到的"几天: 顺延逻辑会往后找"下一个工作日",
#: 日历缺了几天就会被当成工作日, 于是顺延结果全错 —— 这正是本文件里的测试两次假红的原因。
_HOLIDAY_CN_2026 = {
    "year": 2026,
    "papers": ["https://www.gov.cn/zhengce/zhengceku/202511/content_7047091.htm"],
    "days": [
        {"name": "元旦", "date": "2026-01-01", "isOffDay": True},
        {"name": "元旦", "date": "2026-01-02", "isOffDay": True},
        {"name": "元旦", "date": "2026-01-03", "isOffDay": True},
        {"name": "元旦", "date": "2026-01-04", "isOffDay": False},
        {"name": "春节", "date": "2026-02-14", "isOffDay": False},
        {"name": "春节", "date": "2026-02-15", "isOffDay": True},
        {"name": "春节", "date": "2026-02-16", "isOffDay": True},
        {"name": "春节", "date": "2026-02-17", "isOffDay": True},
        {"name": "春节", "date": "2026-02-18", "isOffDay": True},
        {"name": "春节", "date": "2026-02-19", "isOffDay": True},
        {"name": "春节", "date": "2026-02-20", "isOffDay": True},
        {"name": "春节", "date": "2026-02-21", "isOffDay": True},
        {"name": "春节", "date": "2026-02-22", "isOffDay": True},
        {"name": "春节", "date": "2026-02-23", "isOffDay": True},
        {"name": "春节", "date": "2026-02-28", "isOffDay": False},
        {"name": "清明节", "date": "2026-04-04", "isOffDay": True},
        {"name": "清明节", "date": "2026-04-05", "isOffDay": True},
        {"name": "清明节", "date": "2026-04-06", "isOffDay": True},
        {"name": "劳动节", "date": "2026-05-01", "isOffDay": True},
        {"name": "劳动节", "date": "2026-05-02", "isOffDay": True},
        {"name": "劳动节", "date": "2026-05-03", "isOffDay": True},
        {"name": "劳动节", "date": "2026-05-04", "isOffDay": True},
        {"name": "劳动节", "date": "2026-05-05", "isOffDay": True},
        {"name": "劳动节", "date": "2026-05-09", "isOffDay": False},
        {"name": "端午节", "date": "2026-06-19", "isOffDay": True},
        {"name": "端午节", "date": "2026-06-20", "isOffDay": True},
        {"name": "端午节", "date": "2026-06-21", "isOffDay": True},
        {"name": "国庆节", "date": "2026-09-20", "isOffDay": False},
        {"name": "中秋节", "date": "2026-09-25", "isOffDay": True},
        {"name": "中秋节", "date": "2026-09-26", "isOffDay": True},
        {"name": "中秋节", "date": "2026-09-27", "isOffDay": True},
        {"name": "国庆节", "date": "2026-10-01", "isOffDay": True},
        {"name": "国庆节", "date": "2026-10-02", "isOffDay": True},
        {"name": "国庆节", "date": "2026-10-03", "isOffDay": True},
        {"name": "国庆节", "date": "2026-10-04", "isOffDay": True},
        {"name": "国庆节", "date": "2026-10-05", "isOffDay": True},
        {"name": "国庆节", "date": "2026-10-06", "isOffDay": True},
        {"name": "国庆节", "date": "2026-10-07", "isOffDay": True},
        {"name": "国庆节", "date": "2026-10-10", "isOffDay": False},
    ],
}


def _cal2026(holidays_mod):
    """由上面的报文 fixture 生成 2026 日历。

    **从报文派生**而不是手写第二份日期: 手写的那份两次漏掉国庆连休中间几天, 于是测试假红。
    日历本就是从报文解析出来的, 测试里也该保持同一条链路。
    """
    off, work = {}, {}
    for day in _HOLIDAY_CN_2026["days"]:
        (off if day["isOffDay"] else work)[day["date"]] = day["name"]
    return holidays_mod.HolidayCalendar(
        year=2026, off_days=off, work_days=work, source="holiday-cn",
        authoritative=True, papers=_HOLIDAY_CN_2026["papers"])


class TestHolidayCalendar(unittest.TestCase):
    """法定节假日日历 —— 提醒日按它推算, 所以它算错, 提醒就会提醒错日子。

    全部离线: 网络取数用真实报文(裁剪)打桩, 不依赖外网。
    """

    #: 完整 2026 报文见模块级 ``_HOLIDAY_CN_2026`` —— 只留一份, 避免手写第二份日期又漏几天。
    HOLIDAY_CN_2026 = _HOLIDAY_CN_2026

    def setUp(self):
        from telemetry import holidays

        self.holidays = holidays
        holidays.reset_cache()
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        for attr in ("HOLIDAY_DIR",):
            p = mock.patch.object(holidays, attr, self.tmp)
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.holidays.reset_cache()

    def _fetch_from_fixture(self, payload=None):
        """让主源返回 fixture(payload=None 表示取不到), 备源也取不到。"""
        return (mock.patch.object(self.holidays, "_fetch_holiday_cn",
                                  return_value=self._parsed(payload)),
                mock.patch.object(self.holidays, "_fetch_timor", return_value=None))

    def _parsed(self, payload):
        """复用真实解析器, 免得测试自己另写一份解析(那就测不到解析器了)。"""
        if payload is None:
            return None
        with mock.patch.object(self.holidays, "_http_json", return_value=payload):
            return self.holidays._fetch_holiday_cn(2026)

    def test_parser_reads_official_payload(self):
        parsed = self._parsed(self.HOLIDAY_CN_2026)
        self.assertEqual(parsed["source"], "holiday-cn")
        self.assertEqual(parsed["off_days"]["2026-10-01"], "国庆节")
        self.assertIn("2026-09-20", parsed["work_days"], "调休补班日必须被识别")
        self.assertNotIn("2026-09-20", parsed["off_days"])
        self.assertEqual(parsed["papers"], self.HOLIDAY_CN_2026["papers"])

    def test_workday_rules_with_real_calendar(self):
        p1, p2 = self._fetch_from_fixture(self.HOLIDAY_CN_2026)
        with p1, p2:
            cal = self.holidays.load_calendar(2026)
        from datetime import date

        self.assertTrue(cal.authoritative)
        # 调休补班: 周六上班
        self.assertTrue(cal.is_workday(date(2026, 9, 20)))
        self.assertIn("调休", cal.describe(date(2026, 9, 20)))
        # 法定假期: 连普通工作日也不是工作日
        self.assertFalse(cal.is_workday(date(2026, 10, 1)))
        self.assertIn("国庆", cal.describe(date(2026, 10, 1)))
        # 普通周末
        self.assertFalse(cal.is_workday(date(2026, 9, 26)))
        # 普通工作日
        self.assertTrue(cal.is_workday(date(2026, 9, 30)))

    def test_previous_workday_skips_holiday_block(self):
        """国庆连休时, "前一个工作日"要一直往前找到 09-30, 而不是简单减一天。"""
        p1, p2 = self._fetch_from_fixture(self.HOLIDAY_CN_2026)
        with p1, p2:
            cal = self.holidays.load_calendar(2026)
        from datetime import date

        self.assertEqual(cal.previous_workday(date(2026, 10, 1)), date(2026, 9, 30))
        self.assertEqual(cal.previous_workday(date(2026, 10, 5)), date(2026, 9, 30))
        # 周一的前一个工作日是上周五
        self.assertEqual(cal.previous_workday(date(2026, 9, 14)), date(2026, 9, 11))
        # 补班日之后按补班日算
        self.assertEqual(cal.previous_workday(date(2026, 10, 12)), date(2026, 10, 10))

    def test_previous_workday_crosses_year_boundary(self):
        """1 月 1 日的前一个工作日落在上一年 —— 必须能取到上一年日历, 否则会算错。"""
        from datetime import date

        def loader(year, allow_fetch=True, force=False):
            if year == 2026:
                return self.holidays.HolidayCalendar(
                    year=2026, off_days={"2026-01-01": "元旦"}, work_days={},
                    source="holiday-cn", authoritative=True)
            return self.holidays.HolidayCalendar(
                year=2025, off_days={}, work_days={}, source="holiday-cn", authoritative=True)

        with mock.patch.object(self.holidays, "load_calendar", side_effect=loader):
            self.holidays.reset_cache()
            self.assertEqual(
                self.holidays.calendar_for(2026).previous_workday(date(2026, 1, 1)),
                date(2025, 12, 31))

    def test_missing_data_degrades_honestly(self):
        """取不到数据时**如实降级**为"仅按周末判断", 不能装作有数据。"""
        p1, p2 = self._fetch_from_fixture(None)
        with p1, p2:
            cal = self.holidays.load_calendar(2026)
        from datetime import date

        self.assertFalse(cal.authoritative, "取不到数据必须标记为非权威")
        self.assertEqual(cal.source, "weekend-only")
        self.assertTrue(cal.note)
        # 降级后调休补班的周六会被当成休息日 —— 这正是要提醒用户的地方
        self.assertFalse(cal.is_workday(date(2026, 9, 20)))
        ok, text = (cal.is_workday(date(2026, 9, 20)), cal.describe(date(2026, 9, 20)))
        self.assertFalse(ok)
        self.assertIn("周末", text)

    def test_cache_roundtrip_avoids_refetch(self):
        p1, p2 = self._fetch_from_fixture(self.HOLIDAY_CN_2026)
        with p1, p2:
            self.holidays.load_calendar(2026, force=True)
        self.holidays.reset_cache()
        # 第二次不该再取数: 让 fetcher 直接抛异常, 仍应能读到缓存
        with mock.patch.object(self.holidays, "_fetch_holiday_cn",
                               side_effect=AssertionError("不该再取数")), \
                mock.patch.object(self.holidays, "_fetch_timor",
                                  side_effect=AssertionError("不该再取数")):
            cal = self.holidays.load_calendar(2026)
        self.assertTrue(cal.authoritative)
        self.assertIn("缓存", cal.note)

    def test_no_fetch_mode_is_offline_safe(self):
        cal = self.holidays.load_calendar(2026, allow_fetch=False)
        self.assertFalse(cal.authoritative)
        self.assertTrue(cal.note)

    def test_clear_cache_removes_files(self):
        p1, p2 = self._fetch_from_fixture(self.HOLIDAY_CN_2026)
        with p1, p2:
            self.holidays.load_calendar(2026, force=True)
        path = os.path.join(self.tmp, "2026.json")
        self.assertTrue(os.path.exists(path))
        with mock.patch.object(self.holidays, "_cache_path", return_value=path):
            self.holidays.clear_cache(2026)
        self.assertFalse(os.path.exists(path))

    def test_timor_fallback_shape(self):
        """备源报文形状与主源不同, 解析必须都对。"""
        payload = {"code": 0, "holiday": {
            "10-01": {"holiday": True, "name": "国庆节", "date": "2026-10-01"},
            "09-20": {"holiday": False, "name": "国庆节前补班", "date": "2026-09-20"},
        }}
        with mock.patch.object(self.holidays, "_http_json", return_value=payload):
            parsed = self.holidays._fetch_timor(2026)
        self.assertEqual(parsed["off_days"]["2026-10-01"], "国庆节")
        self.assertEqual(parsed["work_days"]["2026-09-20"], "国庆节前补班")


class TestReminder(unittest.TestCase):
    """推送日前一个工作日的「别关机」提醒。"""

    def setUp(self):
        from telemetry import holidays, reminders

        self.holidays, self.reminders = holidays, reminders
        holidays.reset_cache()
        self.cfg = {
            "schedule": {
                "weekly": {"enabled": True, "day_of_week": 0, "time": "10:30"},
                "monthly": {"enabled": True, "day_of_month": 1, "time": "10:30"},
                "reminder": {"enabled": True, "time": "18:00"},
                "defer_non_workday": True,
            },
        }
        # 用真实 2026 日历(国办发明电〔2025〕7 号), 避免依赖外网
        self.cal2026 = _cal2026(holidays)

    def setUpPatches(self):
        p = mock.patch.object(self.holidays, "calendar_for", return_value=self.cal2026)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.holidays.reset_cache()

    def test_next_weekly_is_monday_1030(self):
        from datetime import datetime

        self.setUpPatches()
        got = self.reminders.next_occurrence(self.cfg, datetime(2026, 9, 9, 8, 0), "weekly")
        self.assertEqual(got, datetime(2026, 9, 14, 10, 30))
        # 同一时刻之后(周一当天 11:00) 应顺延到下一周
        got = self.reminders.next_occurrence(self.cfg, datetime(2026, 9, 14, 11, 0), "weekly")
        self.assertEqual(got, datetime(2026, 9, 21, 10, 30))

    def test_next_monthly_handles_month_end_option(self):
        from datetime import datetime

        self.setUpPatches()
        # 10-01 是国庆假期 -> 顺延到假期后第一个工作日 10-08
        got = self.reminders.next_occurrence(self.cfg, datetime(2026, 9, 9), "monthly")
        self.assertEqual(got, datetime(2026, 10, 8, 10, 30), "遇法定假期应顺延")

        cfg = {"schedule": {"monthly": {"enabled": True, "day_of_month": -1, "time": "10:30"}}}
        got = self.reminders.next_occurrence(cfg, datetime(2026, 9, 9), "monthly")
        self.assertEqual(got, datetime(2026, 9, 30, 10, 30), "月末最后一天是工作日, 不顺延")

    def test_disabled_schedule_has_no_occurrence(self):
        from datetime import datetime

        cfg = {"schedule": {"weekly": {"enabled": False, "day_of_week": 0, "time": "10:30"}}}
        self.assertIsNone(self.reminders.next_occurrence(cfg, datetime(2026, 9, 9), "weekly"))

    def test_reminder_fires_on_previous_workday_after_configured_time(self):
        from datetime import datetime

        self.setUpPatches()
        # 09-11(周五) 是 09-14(周一) 的前一个工作日
        self.assertEqual(
            [i["kind"] for i in self.reminders.due_reminders(self.cfg, datetime(2026, 9, 11, 18, 0))],
            ["weekly"])
        # 到点之前不提醒
        self.assertEqual(self.reminders.due_reminders(self.cfg, datetime(2026, 9, 11, 17, 59)), [])
        # 当天更晚(机器晚开机)仍应补上 —— 当晚提醒依然有意义
        self.assertEqual(
            [i["kind"] for i in self.reminders.due_reminders(self.cfg, datetime(2026, 9, 11, 22, 30))],
            ["weekly"])
        # 非提醒日不提醒
        self.assertEqual(self.reminders.due_reminders(self.cfg, datetime(2026, 9, 12, 18, 0)), [])

    def test_national_day_merges_weekly_and_monthly_into_one(self):
        """2026-09-30 同时是「10-01 月报」与「10-05 周报」的前一个工作日 —— 必须合并成一次。

        两条都被顺延到 10-08(国庆假期后第一个工作日), 因此这一天的提醒是"假期前最后一次
        提醒", 文案不能说"今晚别关机"(中间隔着整段假期)。
        """
        from datetime import datetime

        self.setUpPatches()
        due = self.reminders.due_reminders(self.cfg, datetime(2026, 9, 30, 18, 0))
        self.assertEqual(sorted(i["kind"] for i in due), ["monthly", "weekly"])
        self.assertEqual(len({self.reminders.reminder_key(i["remind_date"]) for i in due}), 1,
                         "同一天只能有一个幂等 key, 否则会发两张卡")
        self.assertTrue(all(i["deferred"] for i in due), "两条都应标记为已顺延")

        lines = "\n".join(self.reminders.build_reminder_lines(due))
        self.assertIn("月报", lines)
        self.assertIn("周报", lines)
        self.assertIn("2026-10-08", lines, "应写明顺延后的实际推送日")
        self.assertIn("原定 `2026-10-01`", lines)
        self.assertIn("原定 `2026-10-05`", lines)
        self.assertEqual(lines.count("请在 `2026-10-08` 之前确保设备开机联网"), 1)
        self.assertNotIn("今晚请不要关机", lines,
                         "推送日与提醒日隔着整段假期, 不该说「今晚不要关机」")

    def test_next_day_push_keeps_the_tonight_wording(self):
        """提醒日与推送日只差一天时, 才说"今晚请不要关机"。"""
        from datetime import datetime

        self.setUpPatches()
        # 周报目标改为周三 -> 2026-09-16(周三) 的前一个工作日是 09-15(周二), 只差一天
        cfg = {"schedule": {"weekly": {"enabled": True, "day_of_week": 2, "time": "10:30"},
                            "reminder": {"enabled": True, "time": "18:00"},
                            "defer_non_workday": True}}
        due = self.reminders.due_reminders(cfg, datetime(2026, 9, 15, 18, 0))
        self.assertEqual([i["kind"] for i in due], ["weekly"])
        lines = "\n".join(self.reminders.build_reminder_lines(due))
        self.assertIn("今晚请不要关机", lines)

    def test_reminder_day_follows_the_deferred_date(self):
        """提醒日必须按**顺延后**的日期算, 否则会出现"提醒明天推、实际推到假期后"。"""
        from datetime import datetime

        self.setUpPatches()
        due = self.reminders.due_reminders(self.cfg, datetime(2026, 9, 30, 18, 0))
        for item in due:
            self.assertEqual(item["remind_date"].isoformat(), "2026-09-30")
            self.assertEqual(item["gap_days"], 8)
        # 假期期间(10-01)不该提醒
        self.assertEqual(self.reminders.due_reminders(self.cfg, datetime(2026, 10, 1, 18, 0)), [])

    def test_reminder_line_shows_correct_weekday(self):
        """回归: 星期文案曾差一位(周四显示成"三"、周一显示成"周")。"""
        from datetime import datetime

        self.setUpPatches()
        due = self.reminders.due_reminders(self.cfg, datetime(2026, 9, 11, 18, 0))
        text = "\n".join(self.reminders.build_reminder_lines(due))
        self.assertIn("2026-09-14（周一）10:30", text)

    def test_disabled_reminder_never_fires(self):
        from datetime import datetime

        self.setUpPatches()
        cfg = {"schedule": dict(self.cfg["schedule"],
                                reminder={"enabled": False, "time": "18:00"})}
        self.assertEqual(self.reminders.due_reminders(cfg, datetime(2026, 9, 11, 18, 0)), [])

    def test_send_due_is_idempotent_per_remind_date(self):
        """同一天的所有目标共用一个幂等 key —— 守护进程被反复拉起也不会重发。"""
        from datetime import date

        self.assertEqual(self.reminders.reminder_key(date(2026, 9, 30)),
                         "reminder:2026-09-30")

    def test_send_due_never_raises(self):
        """发送通道坏掉不能把守护进程带崩 —— 提醒是锦上添花, 不是主链路。"""
        from datetime import datetime

        self.setUpPatches()
        with mock.patch.object(self.reminders, "send_due", wraps=self.reminders.send_due), \
                mock.patch("telemetry.alerter.send_alert", side_effect=RuntimeError("boom")):
            ok, msg, key = self.reminders.send_due(self.cfg, datetime(2026, 9, 11, 18, 0))
        self.assertFalse(ok)
        self.assertIn("boom", msg)
        self.assertEqual(key, "reminder:2026-09-11")

    def test_send_due_reports_success_from_alerter(self):
        from datetime import datetime

        self.setUpPatches()
        with mock.patch("telemetry.alerter.send_alert", return_value=(True, "推送成功")) as sent:
            ok, msg, key = self.reminders.send_due(self.cfg, datetime(2026, 9, 11, 18, 0))
        self.assertTrue(ok)
        self.assertEqual(key, "reminder:2026-09-11")
        kwargs = sent.call_args.kwargs
        self.assertEqual(kwargs["key"], "reminder:2026-09-11")
        # 显式给出设置: 关掉资源告警(alerts.enabled)不该顺带关掉别关机提醒
        self.assertTrue(kwargs["settings"]["enabled"])

    def test_send_due_returns_none_when_not_due(self):
        from datetime import datetime

        self.setUpPatches()
        self.assertIsNone(self.reminders.send_due(self.cfg, datetime(2026, 9, 12, 18, 0)))

    def test_daemon_check_reminder_is_inert_everywhere_except_remind_day(self):
        """守护进程里这一步不该在任何非提醒时刻做动作, 更要绝不抛异常。"""
        from datetime import datetime

        from telemetry.daemon import TelemetryDaemon

        self.setUpPatches()
        daemon = TelemetryDaemon.__new__(TelemetryDaemon)   # 不碰真实 DB / 文件
        daemon._last_reminder_key = ""
        daemon._last_msg = ""
        daemon._repeat = 0
        messages = []
        daemon.log = messages.append
        with mock.patch("telemetry.alerter.send_alert", return_value=(True, "ok")) as sent:
            daemon._check_reminder(self.cfg, datetime(2026, 9, 12, 18, 0))
            sent.assert_not_called()
            daemon._check_reminder(self.cfg, datetime(2026, 9, 11, 18, 0))
            self.assertEqual(sent.call_count, 1)
            # 同一天再检查一次: 进程内拦掉, 不再发
            daemon._check_reminder(self.cfg, datetime(2026, 9, 11, 18, 5))
            self.assertEqual(sent.call_count, 1)


class TestDeferral(unittest.TestCase):
    """推送遇周末/法定节假日顺延到下一个工作日。

    为什么要它: 排程是"到点触发"的, 而目标日可能正好是周末或连休(2026 年周报目标 10-05
    是国庆假期、月报目标 10-01 也是)。顺延判断必须查法定节假日日历 —— 只按周末算会把
    连休中间的工作日误当成"该发就发", 也会漏掉"补班的周六其实是工作日"。
    """

    def setUp(self):
        from telemetry import holidays, schedule

        self.holidays, self.schedule = holidays, schedule
        holidays.reset_cache()
        self.cfg = {
            "schedule": {
                "weekly": {"enabled": True, "day_of_week": 0, "time": "10:30"},
                "monthly": {"enabled": True, "day_of_month": 1, "time": "10:30"},
                "defer_non_workday": True,
            },
        }
        p = mock.patch.object(holidays, "calendar_for", return_value=_cal2026(holidays))
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.holidays.reset_cache()

    def _eff(self, now, kind):
        got = self.schedule.next_occurrence(self.cfg, now, kind)
        return got.strftime("%Y-%m-%d %H:%M") if got else None

    # ---- 顺延规则 ----

    def test_weekly_on_a_holiday_monday_is_deferred(self):
        from datetime import datetime

        # 2026-10-05 是国庆假期(周一) -> 顺延到假期后第一个工作日 10-08(周四)
        self.assertEqual(self._eff(datetime(2026, 10, 4), "weekly"), "2026-10-08 10:30")

    def test_monthly_on_a_holiday_first_is_deferred(self):
        from datetime import datetime

        # 2026-10-01 国庆 -> 10-08
        self.assertEqual(self._eff(datetime(2026, 9, 20), "monthly"), "2026-10-08 10:30")

    def test_monthly_on_a_plain_weekend_is_deferred(self):
        from datetime import datetime

        # 2026-11-01 是周日 -> 顺延到 11-02(周一)
        self.assertEqual(self._eff(datetime(2026, 10, 20), "monthly"), "2026-11-02 10:30")

    def test_makeup_workday_saturday_is_not_deferred(self):
        """调休补班的周六**是**工作日 —— 不能被误顺延。

        2026-10-10(周六)与 09-20(周日)都是国务院公告里的补班日, 直接看 defer 的结果最清楚。
        """
        from datetime import datetime

        for ds in ("2026-10-10", "2026-09-20"):
            dt = datetime.strptime(ds + " 10:30", "%Y-%m-%d %H:%M")
            eff, reason = self.schedule.defer(dt)
            self.assertEqual(eff, dt, "%s 是补班日, 不该顺延" % ds)
            self.assertEqual(reason, "")

    def test_plain_weekend_is_deferred_by_defer(self):
        from datetime import datetime

        dt = datetime(2026, 10, 11, 10, 30)          # 周日
        eff, reason = self.schedule.defer(dt)
        self.assertEqual(eff.strftime("%Y-%m-%d"), "2026-10-12")
        self.assertIn("周末", reason)
        # 顺延只改日期, 时间不变
        self.assertEqual((eff.hour, eff.minute), (10, 30))

    def test_workday_target_is_untouched(self):
        from datetime import datetime

        # 2026-10-12 周一, 普通工作日 -> 不顺延
        self.assertEqual(self._eff(datetime(2026, 10, 9), "weekly"), "2026-10-12 10:30")

    def test_spring_festival_collapses_two_targets_into_one(self):
        """春节整周连休会让相邻两个周一(02-16 与 02-23)顺延到同一天 —— 必须去重。

        不去重的话提醒里会把"周报"列两遍; 守护进程那边则靠"当天只发一次"兜住。
        """
        from datetime import datetime

        occ = [o for o in self.schedule.occurrences(self.cfg, datetime(2026, 2, 15))
               if o["effective"].strftime("%m-%d") == "02-24"]
        self.assertEqual(len(occ), 1, "同一天只应有一条周报")
        self.assertEqual(occ[0]["raw"].strftime("%m-%d"), "02-16", "保留最早的原始目标日")
        self.assertEqual([d.strftime("%m-%d") for d in occ[0]["also_from"]], ["02-23"])

    def test_occurrences_are_sorted_and_unique(self):
        from datetime import datetime

        occ = self.schedule.occurrences(self.cfg, datetime(2026, 9, 12, 14, 0))
        keys = [(o["kind"], o["effective"]) for o in occ]
        self.assertEqual(len(keys), len(set(keys)), "同一(类型, 生效时刻)只能出现一次")
        self.assertEqual(occ, sorted(occ, key=lambda x: x["effective"]))

    def test_deferral_can_be_turned_off(self):
        """关掉顺延后应按固定日期 —— 保留这个开关是为了可覆盖(例如日历数据不可用时)。"""
        from datetime import datetime

        cfg = {"schedule": dict(self.cfg["schedule"], defer_non_workday=False)}
        got = self.schedule.next_occurrence(cfg, datetime(2026, 10, 4), "weekly")
        self.assertEqual(got.strftime("%Y-%m-%d %H:%M"), "2026-10-05 10:30")
        self.assertFalse(self.schedule.deferral_enabled(cfg))

    # ---- 触发判定 ----

    def test_push_fires_on_the_deferred_day_not_the_raw_day(self):
        from datetime import datetime

        # 原始目标日(假期)不触发
        for raw_day in ("2026-10-05 10:30", "2026-10-01 10:30"):
            n = datetime.strptime(raw_day, "%Y-%m-%d %H:%M")
            for kind in ("weekly", "monthly"):
                due, _why = self.schedule.push_due_now(self.cfg, n, kind)
                self.assertFalse(due, "%s 是假期, 不该触发 %s" % (raw_day, kind))

        # 顺延后的日子触发, 且说明里带上"原定"与原因
        n = datetime(2026, 10, 8, 10, 30)
        due, why = self.schedule.push_due_now(self.cfg, n, "weekly")
        self.assertTrue(due)
        self.assertIn("原定 2026-10-05", why)
        self.assertIn("国庆", why)
        due_m, why_m = self.schedule.push_due_now(self.cfg, n, "monthly")
        self.assertTrue(due_m)
        self.assertIn("原定 2026-10-01", why_m)

    def test_push_does_not_fire_at_the_wrong_minute(self):
        from datetime import datetime

        for stamp in ("2026-10-08 10:29", "2026-10-08 10:31", "2026-10-09 10:30"):
            n = datetime.strptime(stamp, "%Y-%m-%d %H:%M")
            due, _ = self.schedule.push_due_now(self.cfg, n, "weekly")
            self.assertFalse(due, "%s 不该触发" % stamp)

    def test_push_due_now_is_safe_with_broken_config(self):
        """畸形配置绝不能抛异常(守护进程每 5 秒调一次, 抛一次就整轮挂掉)。

        注意语义: 缺 ``schedule`` 段时**退回默认排程**(周一 10:30), 因此 10-08 这天
        作为 10-05 顺延后的生效日**仍会触发** —— 那是预期行为, 不是缺陷; 显式
        ``enabled: False`` 才是不触发。
        """
        from datetime import datetime

        n = datetime(2026, 10, 8, 10, 30)
        for cfg in ({}, {"schedule": None}):
            due, _why = self.schedule.push_due_now(cfg, n, "weekly")
            self.assertTrue(due, "缺配置段应退回默认排程")
        due, why = self.schedule.push_due_now(
            {"schedule": {"weekly": {"enabled": False}}}, n, "weekly")
        self.assertFalse(due)
        self.assertEqual(why, "")
        # 只关掉月报时, 周报仍按默认排程参与判断(各类型独立开关)
        due, why = self.schedule.push_due_now(
            {"schedule": {"monthly": {"enabled": False}}}, n, "monthly")
        self.assertFalse(due)
        self.assertEqual(why, "")
        # 畸形时间/日期不抛异常即可(退回默认值)
        for cfg in ({"schedule": {"weekly": {"time": "不是时间"}}},
                    {"schedule": {"weekly": {"day_of_week": "abc"}}},
                    {"schedule": {"monthly": {"day_of_month": "月末"}}}):
            self.schedule.push_due_now(cfg, n, "weekly")
            self.schedule.push_due_now(cfg, n, "monthly")

    def test_deferral_without_calendar_data_still_works(self):
        """日历降级(仅按周末)时顺延仍可用, 但要把"数据不权威"说出来。"""
        from datetime import datetime

        with mock.patch.object(self.holidays, "calendar_for",
                              return_value=self.holidays.HolidayCalendar(
                                  year=2026, source="weekend-only", authoritative=False,
                                  note="离线且无缓存, 仅按周末判断")):
            eff, reason = self.schedule.defer(datetime(2026, 10, 11, 10, 30))   # 周日
            self.assertEqual(eff.strftime("%Y-%m-%d"), "2026-10-12")
            self.assertIn("仅按周末判断", reason, "降级时要如实标注")

    def test_daemon_does_not_push_on_the_holiday_but_pushes_after(self):
        """守护进程视角: 假期当天不推, 顺延后的那一天推, 且当天只推一次。"""
        from datetime import datetime

        from telemetry.daemon import TelemetryDaemon

        daemon = TelemetryDaemon.__new__(TelemetryDaemon)
        daemon.last_weekly_sent = ""
        daemon.last_monthly_sent = ""
        daemon._last_reminder_key = ""
        daemon._last_msg = ""
        daemon._repeat = 0
        daemon.log = lambda *a, **k: None
        daemon.aggregator = mock.Mock()
        daemon.aggregator.get_weekly_report.return_value = mock.Mock()
        daemon.aggregator.get_monthly_report.return_value = mock.Mock()
        daemon.db = mock.Mock()

        fake_client = mock.Mock()
        fake_client.user_open_id = "ou_x"
        fake_client.sheet_token = ""
        fake_client.push_to_user_chat.return_value = (True, "ok")
        fake_client.sync_to_public_sheet.return_value = (True, "ok")
        fake_bmgr = mock.Mock()
        fake_bmgr.sync_weekly_report.return_value = (True, "ok")
        fake_bmgr.app_token = ""

        cfg = dict(self.cfg)
        cfg["schedule"] = dict(self.cfg["schedule"],
                               monthly=dict(self.cfg["schedule"]["monthly"], enabled=False),
                               reminder={"enabled": False, "time": "18:00"})

        with mock.patch("telemetry.daemon.FeishuSyncClient", return_value=fake_client), \
                mock.patch("telemetry.bitable_sync.FeishuBitableManager", return_value=fake_bmgr), \
                mock.patch("telemetry.reminders.due_reminders", return_value=[]):
            daemon._check_schedule(cfg, datetime(2026, 10, 5, 10, 30))   # 假期当天
            fake_client.push_to_user_chat.assert_not_called()
            daemon._check_schedule(cfg, datetime(2026, 10, 8, 10, 30))   # 顺延后的日子
            self.assertEqual(fake_client.push_to_user_chat.call_count, 1)
            daemon._check_schedule(cfg, datetime(2026, 10, 8, 10, 30))   # 同一分钟内再滴答
            self.assertEqual(fake_client.push_to_user_chat.call_count, 1, "当天只该推一次")


class TestDataFreshness(unittest.TestCase):
    """统计要准、要跟得上: 备份目录不计数 + 已收录条目不冻结 + 能证明"数据是最新的"。

    背景(实测): RSV 项目下存在 `_bak_20260906_201108/高亮结果/` 与
    `_bak2_20260906_205621/高亮结果/`, 被当作成果一起扫了进来 —— 同一篇文献在库里 3 行,
    报表因此虚高到 3 倍(150 篇 / 2917 页, 实际 50 篇 / 977 页; 节约工时 20.19h → 14.49h)。
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.test_dir, ignore_errors=True)
        self.db = TelemetryDB(os.path.join(self.test_dir, "t.db"))
        self.aggregator = TelemetryAggregator(self.db)

    # ---- 路径卫生 ----

    def test_ignored_path_rules(self):
        from telemetry.watcher import is_ignored_path

        base = "/Users/x/Desktop/RSV"
        for bad in ("_bak_20260906_201108/高亮结果/P1.pdf",
                    "_bak2_20260906_205621/高亮结果/P1.pdf",
                    "高亮结果/_bak/P1.pdf",
                    "_backup/P1.pdf", "_trash/P1.pdf", ".git/x/P1.pdf",
                    "node_modules/a/P1.pdf", "__pycache__/P1.pdf",
                    "_bak_x/_2_pdfs/a.pdf"):
            self.assertTrue(is_ignored_path(os.path.join(base, bad)),
                            "应视为备份/临时: %s" % bad)
        for good in ("高亮结果/P1.pdf", "_2_pdfs/a.pdf", "_highlight_nested/x/P1.pdf",
                     "rsv_hl/P1/P1_highlight.pdf"):
            self.assertFalse(is_ignored_path(os.path.join(base, good)),
                             "是真实产出物, 不该被忽略: %s" % good)

    def test_paper_name_containing_bak_is_not_ignored(self):
        """规则只比**片段前缀**: 文献名里恰好含 bak 不能被误伤。"""
        from telemetry.watcher import is_ignored_path

        self.assertFalse(is_ignored_path("/Users/x/RSV/高亮结果/Wang_bak_2020.pdf"))
        self.assertFalse(is_ignored_path("/Users/x/RSV/高亮结果/paper_old_version.pdf"))

    def _make_pdf(self, path, pages=1, annots=0):
        try:
            import fitz
        except ImportError:
            self.skipTest("PyMuPDF 不可用")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        doc = fitz.open()
        page = doc.new_page()
        for i in range(max(0, annots)):
            page.add_rect_annot(fitz.Rect(50, 50 + i * 20, 200, 90 + i * 20))
        for _ in range(max(0, pages - 1)):
            doc.new_page()
        doc.save(path)
        doc.close()

    def test_backup_copies_are_not_counted(self):
        from telemetry.watcher import WorkspaceScanner

        proj = os.path.join(self.test_dir, "RSV")
        self._make_pdf(os.path.join(proj, "高亮结果", "P1-1.pdf"), pages=3, annots=2)
        # 两个备份副本 —— 修复前会被当成成果, 于是这一篇被计 3 次
        self._make_pdf(os.path.join(proj, "_bak_2026", "高亮结果", "P1-1.pdf"), pages=3, annots=2)
        self._make_pdf(os.path.join(proj, "_bak2_2026", "高亮结果", "P1-1.pdf"), pages=3, annots=2)

        stats = WorkspaceScanner(self.db).scan_project(proj, "RSV")
        self.assertEqual(stats["highlight"], 1, "备份副本不该计入")

        rep = self.aggregator.get_all_time_report()
        self.assertEqual(rep.highlight_count, 1)
        self.assertEqual(rep.highlight_pages, 3, "页数也不该被备份副本放大")

    def test_download_dir_still_counted(self):
        """`_2_pdfs` 是真实下载产物目录, 不能被路径卫生规则误伤。"""
        from telemetry.watcher import WorkspaceScanner

        proj = os.path.join(self.test_dir, "DL")
        os.makedirs(os.path.join(proj, "_2_pdfs"))
        with open(os.path.join(proj, "_2_pdfs", "P9.pdf"), "wb") as fh:
            fh.write(b"%PDF-1.4 fake")

        stats = WorkspaceScanner(self.db).scan_project(proj, "DL")
        self.assertEqual(stats["download"], 1, "_2_pdfs 下的 PDF 应计入下载")

    # ---- 字段刷新(不冻结) ----

    def test_existing_highlight_is_refreshed_not_frozen(self):
        from telemetry.watcher import WorkspaceScanner

        proj = os.path.join(self.test_dir, "RSV2")
        pdf = os.path.join(proj, "高亮结果", "P2-1.pdf")
        self._make_pdf(pdf, pages=2, annots=1)
        scanner = WorkspaceScanner(self.db)

        first = scanner.scan_project(proj, "RSV2")
        self.assertEqual(first["highlight"], 1)
        with self.db.get_connection() as conn:
            got = conn.execute("SELECT page_count, num_annots FROM highlight_items"
                               ).fetchone()
        self.assertEqual((got["page_count"], got["num_annots"]), (2, 1))

        # 用户在同一个 PDF 上继续加标注、并增加了页 -> 再扫一次
        os.remove(pdf)
        self._make_pdf(pdf, pages=4, annots=3)
        second = scanner.scan_project(proj, "RSV2")

        self.assertEqual(second["highlight"], 0, "刷新 ≠ 新增: 篇数不该变")
        self.assertEqual(second["refreshed"], 1, "应记录一次字段刷新")
        with self.db.get_connection() as conn:
            got = conn.execute("SELECT page_count, num_annots FROM highlight_items").fetchone()
        self.assertEqual((got["page_count"], got["num_annots"]), (4, 3),
                         "页数与标注数应跟到最新观测值")
        self.assertEqual(self.aggregator.get_all_time_report().highlight_count, 1)

    def test_refresh_never_overwrites_with_nothing(self):
        """这次没观测到(None)时不许拿默认值覆盖 —— 那比不刷新更糟。"""
        from telemetry.models import HighlightItem

        self.db.record_highlight_item("t", HighlightItem(
            paper_id="P1", pdf_path="/x/P1.pdf", page_count=7, num_annots=4))
        self.assertEqual(self.db.refresh_highlight_item("/x/P1.pdf"), 0)
        with self.db.get_connection() as conn:
            got = conn.execute("SELECT page_count, num_annots FROM highlight_items").fetchone()
        self.assertEqual((got["page_count"], got["num_annots"]), (7, 4))

    def test_download_file_size_is_refreshed(self):
        from telemetry.watcher import WorkspaceScanner

        proj = os.path.join(self.test_dir, "DL2")
        os.makedirs(os.path.join(proj, "_2_pdfs"))
        f = os.path.join(proj, "_2_pdfs", "P1.pdf")
        with open(f, "wb") as fh:
            fh.write(b"x" * 10)
        scanner = WorkspaceScanner(self.db)
        self.assertEqual(scanner.scan_project(proj, "DL2")["download"], 1)

        with open(f, "wb") as fh:          # 重新下载了一个更大的 PDF
            fh.write(b"x" * 500)
        again = scanner.scan_project(proj, "DL2")
        self.assertEqual(again["download"], 0, "刷新 ≠ 新增")
        self.assertEqual(again["refreshed"], 1)
        with self.db.get_connection() as conn:
            size = conn.execute("SELECT file_size_bytes FROM download_items").fetchone()[0]
        self.assertEqual(size, 500)

    def test_moved_file_does_not_create_a_duplicate(self):
        """文件被移动/改名到别的子目录: 只按路径匹配会认不出来 -> 同一篇文献再加一行。"""
        from telemetry.watcher import WorkspaceScanner

        proj = os.path.join(self.test_dir, "MV")
        old = os.path.join(proj, "高亮结果", "P3-1.pdf")
        self._make_pdf(old, pages=2, annots=1)
        scanner = WorkspaceScanner(self.db)
        self.assertEqual(scanner.scan_project(proj, "MV")["highlight"], 1)

        new = os.path.join(proj, "高亮结果", "sub", "P3-1.pdf")
        os.makedirs(os.path.dirname(new), exist_ok=True)
        shutil.move(old, new)
        scanner.scan_project(proj, "MV")

        self.assertEqual(self.aggregator.get_all_time_report().highlight_count, 1,
                         "移动后仍是同一篇文献, 不该重复计数")

    # ---- 历史虚高数据的修复 ----

    def test_purge_removes_backup_rows_only_when_a_real_copy_exists(self):
        from telemetry.models import HighlightItem

        for pid, path in (("P1", "/real/高亮结果/P1.pdf"),
                          ("P1", "/real/_bak_x/高亮结果/P1.pdf"),      # 有真实副本 -> 删
                          ("P2", "/real/_bak_x/高亮结果/P2.pdf")):     # 只有备份 -> 保留
            self.db.record_highlight_item("t", HighlightItem(
                paper_id=pid, pdf_path=path, page_count=1, num_annots=1))

        removed = self.db.purge_ignored_path_items()
        self.assertEqual(removed["highlight_items"], 1, "只该删有真实副本的那一行")
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT paper_id, pdf_path FROM highlight_items ORDER BY id").fetchall()
        self.assertEqual([(r["paper_id"], r["pdf_path"]) for r in rows],
                         [("P1", "/real/高亮结果/P1.pdf"), ("P2", "/real/_bak_x/高亮结果/P2.pdf")],
                         "每一篇文献都必须仍有行 —— 绝不能把某篇整删掉")
        self.assertEqual(self.aggregator.get_all_time_report().highlight_count, 2)

    # ---- 新鲜度可观测 ----

    def test_freshness_helpers(self):
        self.assertIsNone(self.db.latest_ingest_at())
        from telemetry.models import HighlightItem

        self.db.record_highlight_item("t", HighlightItem(
            paper_id="P1", pdf_path="/x/P1.pdf", page_count=1))
        self.assertIsNotNone(self.db.latest_ingest_at())
        counts = self.db.table_counts()
        self.assertEqual(counts["highlight_items"], 1)
        self.assertIn("tasks", counts)

    def test_daemon_heartbeat_carries_freshness(self):
        """心跳要带"最近入库时间 + 各表行数" —— 否则"是不是实时"没有凭据。"""
        from telemetry.daemon import TelemetryDaemon
        from telemetry.models import HighlightItem

        self.db.record_highlight_item("t", HighlightItem(
            paper_id="P1", pdf_path="/x/P1.pdf", page_count=1))

        daemon = TelemetryDaemon.__new__(TelemetryDaemon)
        daemon.db = self.db
        daemon.last_fd = None
        hb_path = os.path.join(self.test_dir, "hb.json")
        cfg = {"schedule": {}, "user": {"nickname": "wtg", "open_id": "ou_x"}}

        with mock.patch("telemetry.daemon.HEARTBEAT_FILE", hb_path):
            daemon._update_heartbeat(cfg, datetime(2026, 9, 12, 10, 30))

        with open(hb_path, encoding="utf-8") as fh:
            hb = json.load(fh)
        self.assertIn("freshness", hb, "心跳必须带新鲜度凭据")
        self.assertEqual(hb["freshness"]["latest_ingest_at"], self.db.latest_ingest_at())
        self.assertEqual(hb["freshness"]["counts"]["highlight_items"], 1)
        self.assertIn("next_weekly", hb, "顺延后的下次推送时刻也应在心跳里")


class TestAutoSync(unittest.TestCase):
    """scripts/auto_sync.py 的同步 / 构建语义。

    该脚本是 LaunchAgent 定时任务的入口。过去"拉取一有风吹草动就中止整轮、构建没跑却
    照打 ✅"导致故障静默了数周, 所以这几条分支都要钉住。
    """

    def setUp(self):
        from pathlib import Path

        self.test_dir = tempfile.mkdtemp()
        self.mod = self._load_auto_sync()
        # 日志重定向到临时目录, 不碰真实的 ~/.medit/autosync.log
        self.mod.LOG_FILE = Path(self.test_dir) / "autosync.log"
        self.mod.LOG_BACKUP_FILE = Path(str(self.mod.LOG_FILE) + ".1")
        self.mod.PULL_RETRY_DELAY_SECONDS = 0  # 测试里别真等
        self.calls = []
        self.state = {"dirty": False, "pull_ok": True, "build_ok": True}
        self.mod.run_cmd = self._fake_run_cmd
        # 告警必须打桩 —— 否则跑单测会真的往飞书发卡片
        self.notifications = []
        self.mod.notify = self._fake_notify

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _fake_notify(self, title, lines, key, level="warning"):
        self.notifications.append(
            {"title": title, "lines": list(lines), "key": key, "level": level})
        return True

    @staticmethod
    def _load_auto_sync():
        """按文件路径加载 scripts/auto_sync.py。

        scripts/ 没有 __init__.py (且有一条测试断言它必须不存在, 见打包假设),
        因此不能用包导入。
        """
        import importlib.util

        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(repo, "scripts", "auto_sync.py")
        spec = importlib.util.spec_from_file_location("auto_sync_under_test", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _fake_run_cmd(self, cmd, cwd=None, timeout=300):
        self.calls.append(list(cmd))
        head = list(cmd[:2])
        if head == ["git", "status"]:
            return True, ("M x.py" if self.state["dirty"] else ""), ""
        if head == ["git", "pull"]:
            if self.state["pull_ok"]:
                return True, "Already up to date.", ""
            return False, "", ("fatal: unable to access 'https://github.com/x/y.git/': "
                               "LibreSSL SSL_connect: SSL_ERROR_SYSCALL")
        if cmd and cmd[0] == "make":
            return (True, "", "") if self.state["build_ok"] else (False, "", "make: *** boom")
        return True, "", ""

    def _pulled(self):
        return [c for c in self.calls if c[:2] == ["git", "pull"]]

    def _built(self):
        return [c for c in self.calls if c and c[0] == "make"]

    def test_dirty_worktree_skips_pull_but_still_builds(self):
        """工作区脏时跳过拉取 —— 但绝不因此放弃构建。"""
        self.state.update(dirty=True)
        updated, state = self.mod.pull_and_rebuild()
        self.assertTrue(updated)
        self.assertEqual(state, "skipped_dirty")
        self.assertEqual(self._pulled(), [],
                         "脏工作区不应尝试 pull (autostash 回放冲突风险)")
        self.assertTrue(self._built(), "跳过拉取不等于跳过构建")
        self.assertEqual(self.notifications, [], "脏工作区属预期状态, 不该告警")

    def test_pull_failure_is_transient_and_build_still_runs(self):
        """网络/代理抖动导致拉取失败: 重试若干次, 仍继续构建, 状态标为 failed 并告警。"""
        self.state.update(pull_ok=False)
        updated, state = self.mod.pull_and_rebuild()
        self.assertTrue(updated, "构建成功即视为部署已更新")
        self.assertEqual(state, "failed")
        self.assertEqual(len(self._pulled()), self.mod.PULL_ATTEMPTS, "应重试到上限")
        self.assertTrue(self._built(), "拉取失败不应中止整轮")

        self.assertEqual(len(self.notifications), 1, "代码未同步应告警一次")
        note = self.notifications[0]
        self.assertEqual(note["key"], "autosync-pull-failed")
        self.assertEqual(note["level"], "warning")
        self.assertIn("未同步", note["title"])

    def test_build_failure_means_not_updated(self):
        """只有构建失败才算部署未更新, 并以 critical 级别告警。"""
        self.state.update(build_ok=False)
        updated, _ = self.mod.pull_and_rebuild()
        self.assertFalse(updated)

        self.assertEqual(len(self.notifications), 1, "构建失败应告警一次")
        note = self.notifications[0]
        self.assertEqual(note["key"], "autosync-build-failed")
        self.assertEqual(note["level"], "critical")
        self.assertIn("构建失败", note["title"])
        self.assertTrue(any("boom" in ln for ln in note["lines"]),
                        "卡片正文应带上失败摘要, 便于直接判读")

    def test_success_path_is_silent(self):
        """成功时保持安静 —— 只有失败才打扰人。"""
        updated, state = self.mod.pull_and_rebuild()
        self.assertEqual((updated, state), (True, "ok"))
        self.assertEqual(self.notifications, [])

    def test_notify_never_breaks_the_job(self):
        """告警通道出问题时, notify 必须返回 False 而不是抛异常。

        告警失败不能把同步任务带崩 —— "发不出告警"不该升级成新的故障。
        """
        from unittest import mock

        # 重新加载一份模块, 拿到未被 setUp 打桩的真实 notify
        fresh = self._load_auto_sync()
        fresh.LOG_FILE = self.mod.LOG_FILE  # 别写到真实的 ~/.medit/autosync.log

        boom = mock.MagicMock(side_effect=RuntimeError("通道炸了"))
        with mock.patch.dict(sys.modules,
                             {"telemetry.alerter": mock.MagicMock(send_alert=boom)}):
            self.assertFalse(fresh.notify("t", ["x"], key="k"))

    def test_log_lines_are_timestamped(self):
        """日志每行都必须带时间戳。

        上一轮排查最大的障碍就是旧日志一行时间都没有, 失败无法与时刻对应。
        """
        self.mod.log("[auto_sync] 测试行")
        lines = [ln for ln in self.mod.LOG_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]
        self.assertTrue(lines)
        for ln in lines:
            self.assertRegex(ln, r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] ")

    def test_launchd_log_is_not_in_tmp(self):
        """日志默认必须落在 ~/.medit 下, 且 LaunchAgent 与脚本自身指向同一处。

        /tmp 会被 macOS 的 periodic(8) 回收 (3 天未访问即删除), 历史说没就没。
        """
        import plistlib
        from pathlib import Path
        from unittest import mock

        # 默认落点: 重新加载一份未被本次测试改写的模块
        fresh = self._load_auto_sync()
        self.assertEqual(fresh.LOG_FILE.parent, Path.home() / ".medit")
        self.assertNotIn("/tmp", str(fresh.LOG_FILE))

        with mock.patch("pathlib.Path.home", return_value=Path(self.test_dir)), \
                mock.patch.object(self.mod, "run_cmd", return_value=(True, "", "")):
            self.mod.install_launchd(6)

        plist_path = os.path.join(self.test_dir, "Library", "LaunchAgents",
                                  "com.via54medit.autosync.plist")
        self.assertTrue(os.path.exists(plist_path))
        with open(plist_path, "rb") as fp:
            data = plistlib.load(fp)
        for key in ("StandardOutPath", "StandardErrorPath"):
            self.assertEqual(data[key], str(self.mod.LOG_FILE),
                             f"{key} 应与脚本自身的日志目标一致, 否则 stdout 会跑到别处")
            self.assertNotIn("via54medit_sync", data[key])

    def test_exit_codes_distinguish_failure_modes(self):
        """退出码契约: 0=正常(含脏工作区跳过), 1=构建失败(部署未更新), 2=已重建但代码未同步。"""
        cases = [
            ((True, "ok"), 0),
            ((True, "skipped_dirty"), 0),
            ((True, "failed"), 2),
            ((False, "ok"), 1),
        ]
        for result, want in cases:
            with self.subTest(result=result):
                self.mod.check_updates = lambda: (False, 0)
                self.mod.pull_and_rebuild = lambda _r=result: _r
                old_argv = sys.argv
                sys.argv = ["auto_sync.py", "--pull"]
                try:
                    self.mod.main()
                    code = 0
                except SystemExit as e:
                    code = e.code if isinstance(e.code, int) else 0
                finally:
                    sys.argv = old_argv
                self.assertEqual(code, want, f"{result} 的退出码应为 {want}")


class TestPackageImportStrategy(unittest.TestCase):
    """telemetry 包的导入策略: 轻量子模块不应连带拉起重依赖。

    此前 ``__init__.py`` 是 eager 导入, 于是 ``import telemetry.envcheck`` 也会经
    watcher -> pdf_utils 拉起 PyMuPDF (实测连带 26 个模块), 既多付开销, 又让 fitz 的
    弃用警告污染 ``--env-check`` / ``--help`` 这些与 PDF 无关的命令输出。
    """

    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _run(self, code):
        import subprocess

        return subprocess.run([sys.executable, "-c", code], cwd=self.REPO,
                              capture_output=True, text=True, timeout=60)

    def test_light_submodule_does_not_drag_pdf_stack(self):
        """envcheck / db 这类子模块不得连带拉起 PDF 相关模块, 也不该打出弃用警告。"""
        code = (
            "import sys\n"
            "import telemetry.envcheck\n"
            "import telemetry.db\n"
            "heavy = sorted(m for m in sys.modules if m.startswith(\n"
            "    ('fitz', 'pymupdf', 'telemetry.watcher', 'telemetry.pdf_utils')))\n"
            "print('HEAVY=' + ','.join(heavy))\n"
        )
        r = self._run(code)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("HEAVY=", r.stdout)
        self.assertEqual(r.stdout.strip(), "HEAVY=",
                         "轻量子模块不该连带 PDF 依赖 (经 watcher -> pdf_utils -> fitz)")
        self.assertNotIn("deprecated", r.stderr, "不该出现 fitz 的弃用警告")

    def test_lazy_exports_still_resolve(self):
        """惰性化不能破坏既有的 from telemetry import X 写法。"""
        code = (
            "import telemetry\n"
            "from telemetry import (TelemetryDB, TelemetryTracker, TelemetryAggregator,\n"
            "                       FeishuSyncClient, WorkspaceScanner, AggregateReport,\n"
            "                       TaskType, record_llm_usage)\n"
            "print('V=' + telemetry.__version__)\n"
            "print('DIR=' + str(all(n in dir(telemetry) for n in\n"
            "    ['TelemetryDB', 'WorkspaceScanner', 'FeishuSyncClient', 'AggregateReport'])))\n"
        )
        r = self._run(code)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"V={self._version()}", r.stdout)
        self.assertIn("DIR=True", r.stdout)

    def test_unknown_attribute_still_raises(self):
        """未知属性仍应是 AttributeError, 而不是静默返回 None。"""
        code = (
            "import telemetry\n"
            "try:\n"
            "    telemetry.definitely_not_here\n"
            "except AttributeError:\n"
            "    print('OK')\n"
        )
        r = self._run(code)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OK", r.stdout)

    def test_cli_light_commands_carry_no_pdf_noise(self):
        """--env-check / --help 的输出不得出现 PDF 库的弃用警告。"""
        import subprocess

        for argv in (["--env-check"], ["--help"]):
            with self.subTest(argv=argv):
                r = subprocess.run([sys.executable, "-m", "telemetry.cli", *argv],
                                   cwd=self.REPO, capture_output=True, text=True, timeout=60)
                combined = r.stdout + r.stderr
                self.assertNotIn("deprecated", combined,
                                 f"{argv} 的输出不该带 PDF 库警告")

    @staticmethod
    def _version():
        import telemetry
        return telemetry.__version__

    def test_pdf_stack_import_carries_no_deprecation_warning(self):
        """导入 PDF 相关模块不得打 PyMuPDF 的弃用警告。

        写 ``import fitz`` 时 PyMuPDF 会往 stderr 打一行 "The `fitz` API is deprecated";
        改用 ``import pymupdf as fitz`` 才没有。这行警告会顺着导入链污染守护进程日志与
        CLI 输出, 所以要钉住。
        """
        code = (
            "from telemetry import WorkspaceScanner\n"
            "from telemetry.pdf_utils import get_pdf_page_count\n"
            "print('OK')\n"
        )
        r = self._run(code)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OK", r.stdout)
        self.assertNotIn("deprecated", r.stderr, "PDF 导入不该打弃用警告")

    def test_docs_cover_alert_channel_and_sync_exit_codes(self):
        """新增能力必须落到用户可见的文档里, 而不只是代码里。

        这一条本身就是为了一次真实疏漏: 告警通道与定时同步上线后, 根 README (中/英) 与
        完整指南三处都漏了, 只有模块 README 更新了 —— 补完文档再加这道防护。
        """
        targets = {
            "README.md": ["alert", "exit codes"],
            "README.zh-CN.md": ["alert", "退出码"],
            "docs/TELEMETRY_GUIDE.md": ["alert", "退出码"],
            "telemetry/README.md": ["alert", "退出码"],
        }
        for rel, needles in targets.items():
            with self.subTest(doc=rel):
                path = os.path.join(self.REPO, rel)
                self.assertTrue(os.path.exists(path), f"缺少文档 {rel}")
                with open(path, encoding="utf-8") as fp:
                    text = fp.read()
                for needle in needles:
                    self.assertIn(needle, text, f"{rel} 未提及 {needle}")


class TestBitableColumnAlignment(unittest.TestCase):
    """目标表的统计列必须与"最新统计项"对齐 —— 不允许默默少一列。

    由来: 代码里的统计项是**先加字段、后加列**的。新增一个统计项(如 v5.4.37 的"其他"
    三列)不会让已经建好的表自动长出列来, 于是那些值在写入时被静默丢弃, 只能挤进
    「备注说明」当一段纯文本: 看得到, 但筛选不了、分组不了、画不了图。实测公司表
    就这样少了 8 列 —— 而写入不报任何错, 所以没有任何东西会提醒你。

    对齐契约只有两种合法状态: **要么目标表里有同名列, 要么显式写明为什么不该有列**。
    没有第三种状态。这组测试就是把这条契约钉住。
    """

    def test_every_standard_field_is_mapped_or_explicitly_excluded(self):
        from telemetry.bitable_sync import unmapped_standard_fields
        self.assertEqual(unmapped_standard_fields(), [],
                         "这些统计项既没有列、也没写明理由 —— 它们会被静默丢弃")

    def test_exclusions_all_carry_a_reason(self):
        from telemetry.bitable_sync import INTENTIONALLY_NOT_A_COLUMN
        for name, reason in INTENTIONALLY_NOT_A_COLUMN.items():
            self.assertTrue(str(reason).strip(),
                            "%s 被排除但没写理由" % name)
            self.assertGreater(len(str(reason)), 10,
                               "%s 的理由太短, 看不出是为了什么" % name)

    def test_missing_columns_detects_the_real_gap(self):
        from telemetry.bitable_sync import (
            missing_target_columns, COMPANY_FIELD_MAP, SCHEMA_COMPANY,
            SCHEMA_STANDARD, TABLE_SCHEMA_FIELDS,
        )
        # 补齐前的公司表 (13 列) —— 正是用户报告"统计列没对齐"时的状态
        legacy = {
            "记录标识", "统计周次", "提交成员", "统计日期", "文献检索量",
            "成功下载量", "高亮标注量", "解析物理总页数", "节省工时(小时)",
            "Token消耗量", "项目任务类型", "数据状态", "备注说明",
        }
        missing = missing_target_columns(legacy, SCHEMA_COMPANY)
        self.assertEqual(sorted(missing), sorted([
            "检索节约工时(h)", "下载节约工时(h)", "高亮节约工时(h)",
            "其他任务数", "其他工作时长(h)", "其他Token消耗", "其他未归属Token",
            "API调用次数",
        ]))
        # 刻意不建列的字段不出现在"缺列"里(否则会天天误报)
        self.assertNotIn("成员OpenID", missing)
        # 补齐后不再缺
        all_cols = legacy | set(COMPANY_FIELD_MAP.values())
        self.assertEqual(missing_target_columns(all_cols, SCHEMA_COMPANY), [])
        # 标准表视角: 19 个字段一个不差
        std = {f["field_name"] for f in TABLE_SCHEMA_FIELDS}
        self.assertEqual(missing_target_columns(std, SCHEMA_STANDARD), [])

    def test_ensure_columns_creates_only_what_is_missing(self):
        from telemetry.bitable_sync import FeishuBitableManager, SCHEMA_COMPANY

        mgr = FeishuBitableManager(config={"feishu": {}})
        existing = ["记录标识", "统计周次", "提交成员", "统计日期", "文献检索量",
                    "成功下载量", "高亮标注量", "解析物理总页数", "节省工时(小时)",
                    "Token消耗量", "项目任务类型", "数据状态", "备注说明"]
        posts = []

        def fake_api(endpoint, method="GET", body=None):
            if method == "GET":
                return {"code": 0, "data": {"items": [{"field_name": n} for n in existing]}}
            posts.append(body)
            return {"code": 0}

        mgr._api_request = fake_api
        created = mgr.ensure_table_columns("bascn_x", "tbl_x", SCHEMA_COMPANY)

        self.assertEqual(len(created), 8)
        names = [p["field_name"] for p in posts]
        self.assertEqual(sorted(names), sorted(created))
        self.assertNotIn("成员OpenID", names, "身份字段不该被建列")
        self.assertNotIn("记录标识", names, "已有的列不该重复创建")
        # 数值统计项必须建为数字列(类型 2), 否则表格里没法求和
        self.assertTrue(all(p["type"] == 2 for p in posts), posts)

    def test_ensure_columns_dry_run_creates_nothing(self):
        from telemetry.bitable_sync import FeishuBitableManager, SCHEMA_COMPANY

        mgr = FeishuBitableManager(config={"feishu": {}})
        writes = []

        def fake_api(endpoint, method="GET", body=None):
            if method == "GET":
                return {"code": 0, "data": {"items": [{"field_name": "记录标识"}]}}
            writes.append(body)
            return {"code": 0}

        mgr._api_request = fake_api
        planned = mgr.ensure_table_columns("bascn_x", "tbl_x", SCHEMA_COMPANY, dry_run=True)
        self.assertEqual(writes, [], "dry-run 不能真的建列")
        # 公司表应有 21 列(13 原有 + 8 补齐), 已有 1 列 -> 计划 20 列。
        # 不写死数字: 列定义变了应当由 COMPANY_FIELD_MAP 带着走, 而不是让测试假红。
        from telemetry.bitable_sync import COMPANY_FIELD_MAP
        self.assertEqual(len(planned), len(COMPANY_FIELD_MAP) - 1)

    def test_legacy_thirteen_column_rows_survive_map_growth(self):
        """扩展映射后, 备份里 13 列的历史行必须还能读出来。

        这是最容易被忽略的一条: 历史行靠"列数 == 公司列序长度"被认出来。若列序跟着
        映射一起变长, 这些行就认不出来, 会被当作脏行**静默丢掉** —— 回退路径上少的就是它们。
        """
        import csv as _csv
        from telemetry.bitable_sync import (
            FeishuBitableManager, COMPANY_PAYLOAD_ORDER_LEGACY, BACKUP_FIELDS,
        )

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "backup.csv")
            mgr = FeishuBitableManager(config={"feishu": {}})
            mgr._backup_csv_path = lambda: path
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = _csv.writer(f)
                w.writerow(BACKUP_FIELDS)
                # 公司表 13 列 payload 被追加进标准表头的文件 (历史事故形态)
                w.writerow(["2026-W37_Devin_via54Medit", "2026-W37", "Devin Wei",
                            "", 44, 215, 150, 2917, 20.19, 1234, "via54Medit",
                            "已自动同步", "旧行"])
            recs = mgr._load_local_csv_records()
            self.assertEqual(len(recs), 1, "13 列历史行被丢掉了")
            self.assertEqual(recs[0]["汇报周期"], "2026-W37")
            self.assertEqual(recs[0]["成员花名"], "Devin Wei")
            # CSV 回读得到的是字符串(该路径不做类型强转, 与既有行为一致)
            self.assertEqual(recs[0]["文献检索篇数"], "44")
            self.assertEqual(recs[0]["总节约工时(h)"], "20.19")
            self.assertEqual(len(COMPANY_PAYLOAD_ORDER_LEGACY), 13)

    def test_sync_reports_missing_columns_instead_of_silently_dropping(self):
        """缺列时必须**说出来** —— 缺列不会让写入报错, 只会让值消失。"""
        from telemetry.bitable_sync import FeishuBitableManager, SCHEMA_COMPANY
        from telemetry.models import AggregateReport

        mgr = FeishuBitableManager(config={
            "user": {"nickname": "Devin"},
            "feishu": {"company_bitable_member": "Devin Wei"},
        })
        mgr.app_token, mgr.table_id = "bascn_test", "tbl_test"
        mgr.resolve_schema = lambda: (SCHEMA_COMPANY, "test")
        # 目标表只有公司表原有的 13 列
        legacy = ["记录标识", "统计周次", "提交成员", "统计日期", "文献检索量",
                  "成功下载量", "高亮标注量", "解析物理总页数", "节省工时(小时)",
                  "Token消耗量", "项目任务类型", "数据状态", "备注说明"]
        mgr._api_request = lambda *a, **k: (
            {"code": 0, "data": {"items": [{"field_name": n} for n in legacy]}}
            if (k.get("method") or (a[1] if len(a) > 1 else "GET")) == "GET"
            else {"code": 0, "data": {"record": {"record_id": "rec1"}}})
        mgr._find_existing_record = lambda *a, **k: None
        mgr._record_local_csv = lambda *a, **k: None

        ok, msg = mgr.sync_weekly_report(AggregateReport(
            period_type="weekly", period_name="2026年 第37周",
            start_date="2026-09-07", end_date="2026-09-13"), "Devin")

        self.assertTrue(ok, msg)
        self.assertIn("缺", msg, "缺列了却报成功 —— 那些统计项正在被静默丢弃")
        self.assertIn("其他任务数", msg)
        self.assertIn("--align-fields", msg, "应给出补齐办法")


if __name__ == "__main__":
    unittest.main()
