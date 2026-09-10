"""Unit and integration tests for telemetry module."""

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
        """测试：一句话部署参数装配与配置固化。"""
        from telemetry.deploy import setup_configuration
        from telemetry.config import load_config, save_config
        import argparse

        # 备份真实配置
        real_cfg = load_config()

        try:
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
            cfg = setup_configuration(fake_args)
            self.assertEqual(cfg["user"]["nickname"], "张三测试")
            self.assertEqual(cfg["user"]["open_id"], "ou_test_12345")
            self.assertEqual(cfg["feishu"]["app_id"], "cli_test_app")
            self.assertEqual(cfg["schedule"]["weekly"]["day_of_week"], 4)  # Friday = 4
            self.assertEqual(cfg["schedule"]["weekly"]["time"], "18:30")
            self.assertEqual(cfg["schedule"]["monthly"]["day_of_month"], -1)  # last = -1
            self.assertEqual(cfg["schedule"]["monthly"]["time"], "18:00")
            self.assertEqual(cfg["feishu"]["company_bitable_token"], "bascnTestToken12345")
        finally:
            # 严格恢复真实环境配置
            save_config(real_cfg)

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


if __name__ == "__main__":
    unittest.main()
