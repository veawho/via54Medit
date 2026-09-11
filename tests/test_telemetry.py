"""Unit and integration tests for telemetry module."""

import json
import os
import shutil
import sys
import tempfile
import unittest
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
        company_names = {
            "记录标识", "统计周次", "提交成员", "统计日期", "文献检索量",
            "成功下载量", "高亮标注量", "解析物理总页数", "节省工时(小时)",
            "Token消耗量", "项目任务类型", "数据状态", "备注说明",
        }
        self.assertEqual(company_names, COMPANY_TABLE_FIELDS)
        self.assertEqual(detect_schema_profile(company_names), SCHEMA_COMPANY)
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
        self.assertEqual(payload["项目任务类型"], "via54Medit")
        self.assertEqual(payload["数据状态"], "已自动同步")
        # 日期字段必须是毫秒时间戳：ISO 字符串会被飞书拒绝 (1254064)
        self.assertIsInstance(payload["统计日期"], int)
        self.assertEqual(payload["统计日期"], 1788710400000)  # 2026-09-07 00:00 +08:00
        for absent in ("成员OpenID", "检索节约工时(h)", "API调用次数", "汇报周期"):
            self.assertNotIn(absent, payload)

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
        """测试：本地备份固定 15 列标准字段名，兼容并修复历史错位行。"""
        import csv as _csv
        from telemetry.bitable_sync import (
            FeishuBitableManager, BACKUP_FIELDS, COMPANY_PAYLOAD_ORDER,
            SCHEMA_COMPANY, SCHEMA_STANDARD,
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

            # 1) 公司 schema 落盘后仍是 15 列标准表头，不再产生 13 列错位行
            mgr._record_local_csv(mgr.build_company_payload(rep, "Devin"), SCHEMA_COMPANY)
            with open(path, encoding="utf-8-sig", newline="") as f:
                rows = list(_csv.reader(f))
            self.assertEqual(rows[0], BACKUP_FIELDS)
            self.assertEqual(len(rows[0]), 15)
            self.assertEqual(len(rows[1]), 15)
            self.assertEqual(
                rows[0][:4], ["汇报周期", "成员花名", "成员OpenID", "上报时间"])

            # 2) 标准 schema 落盘后列语义不变，同一文件可混写
            mgr._record_local_csv(
                mgr.build_standard_payload(rep, "Devin", "ou_x"), SCHEMA_STANDARD)
            with open(path, encoding="utf-8-sig", newline="") as f:
                rows = list(_csv.reader(f))
            self.assertTrue(all(len(r) == 15 for r in rows), "所有行必须与表头等宽")

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
            self.assertEqual(len(COMPANY_PAYLOAD_ORDER), 13)
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
            mgr._api_request = lambda *a, **k: calls.append(a) or {"code": 0}

            ok, msg = mgr.sync_weekly_report(rep, "Devin", dry_run=True)

            self.assertTrue(ok, msg)
            payload = json.loads(msg)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(set(payload["fields"].keys()), COMPANY_TABLE_FIELDS)
            self.assertFalse(os.path.exists(path), "dry-run 不应写本地备份")
            self.assertEqual(calls, [], "dry-run 不应发起任何 API 请求")

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


if __name__ == "__main__":
    unittest.main()
