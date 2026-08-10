#!/usr/bin/env python3
"""
test_via54_rules.py — 6 步规则校验模块单测

覆盖:
  T1: Step 1 — 目录结构 (3 个子目录)
  T2: Step 1b — PPT 扩页 + 图片导出
  T3: Step 2 — PPT 视觉分析结果
  T4: Step 3 — 文献下载 (Pn-x 归档)
  T5: Step 4 — Highlight (PDF + 图)
  T6: Step 5 — 三方对齐 (PPT/表格/PDF)
  T7: Step 6 — 目录合并格式
  T8: 完整 check_all 跑通
  T9: print_rules 输出完整
  T10: 真实 TMA 项目跑规则 (失败用例 + 通过用例)
"""
import os, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from via54_rules import (
    check_all,
    quick_check,
    print_report,
    _check_step1_dirs,
    _check_step1_ppt_expansion,
    _check_step2_ppt_analysis,
    _check_step3_download,
    _check_step4_highlight,
    _check_step5_alignment,
    _check_step6_merge,
    RULES_TEXT,
)


def _make_pseudo_project(root: str) -> str:
    """
    构造一个合规的假项目目录, 返回 root
    """
    # Step 1: 3 个子目录
    os.makedirs(os.path.join(root, "_ppt"), exist_ok=True)
    os.makedirs(os.path.join(root, "_download"), exist_ok=True)
    os.makedirs(os.path.join(root, "_highlight"), exist_ok=True)

    # Step 1b: PPT 扩页 + 图
    with open(os.path.join(root, "_ppt/original.pptx"), 'w') as f:
        f.write("dummy")
    with open(os.path.join(root, "_ppt/original_expanded.pptx"), 'w') as f:
        f.write("dummy")
    os.makedirs(os.path.join(root, "_ppt/_exported_images"), exist_ok=True)
    with open(os.path.join(root, "_ppt/_exported_images/slide1.jpg"), 'w') as f:
        f.write("dummy")

    # Step 2: PPT 视觉分析
    with open(os.path.join(root, "_ppt/_vision_report.json"), 'w') as f:
        f.write("{}")

    # Step 3 + 4: 5 个 Pn-x 都有 download + highlight
    for pn in ['P11-1', 'P11-2', 'P12-1', 'P12-2', 'P99-1']:
        # download
        os.makedirs(os.path.join(root, f"_download/{pn}"), exist_ok=True)
        with open(os.path.join(root, f"_download/{pn}/{pn}_main.pdf"), 'w') as f:
            f.write("dummy")
        # highlight
        os.makedirs(os.path.join(root, f"_highlight/{pn}"), exist_ok=True)
        with open(os.path.join(root, f"_highlight/{pn}/{pn}_main.pdf"), 'w') as f:
            f.write("dummy")
        with open(os.path.join(root, f"_highlight/{pn}/{pn}_page1_highlight.jpg"), 'w') as f:
            f.write("dummy")

    return root


class TestStep1Dirs(unittest.TestCase):
    """Step 1: 3 个子目录"""

    def test_all_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_pseudo_project(tmp)
            r = _check_step1_dirs(tmp)
            self.assertTrue(r["ok"])
            self.assertEqual(len(r["issues"]), 0)
            self.assertIsNotNone(r["found"]["ppt"])
            self.assertIsNotNone(r["found"]["download"])
            self.assertIsNotNone(r["found"]["highlight"])

    def test_missing_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "_ppt"))
            # 缺 download 和 highlight
            r = _check_step1_dirs(tmp)
            self.assertFalse(r["ok"])
            self.assertEqual(len(r["issues"]), 2)

    def test_alt_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 用 alt 名字
            os.makedirs(os.path.join(tmp, "ppt"))
            os.makedirs(os.path.join(tmp, "pdfs"))
            os.makedirs(os.path.join(tmp, "hl"))
            r = _check_step1_dirs(tmp)
            self.assertTrue(r["ok"])


class TestStep1bPptExpansion(unittest.TestCase):
    """Step 1b: PPT 扩页 + 图片"""

    def test_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            ppt_dir = os.path.join(tmp, "_ppt")
            os.makedirs(ppt_dir)
            with open(os.path.join(ppt_dir, "orig.pptx"), 'w') as f:
                f.write("x")
            with open(os.path.join(ppt_dir, "orig_expanded.pptx"), 'w') as f:
                f.write("x")
            with open(os.path.join(ppt_dir, "slide1.jpg"), 'w') as f:
                f.write("x")
            r = _check_step1_ppt_expansion(tmp, ppt_dir)
            self.assertTrue(r["ok"])

    def test_no_expanded(self):
        with tempfile.TemporaryDirectory() as tmp:
            ppt_dir = os.path.join(tmp, "_ppt")
            os.makedirs(ppt_dir)
            with open(os.path.join(ppt_dir, "orig.pptx"), 'w') as f:
                f.write("x")
            # 缺 expanded
            r = _check_step1_ppt_expansion(tmp, ppt_dir)
            self.assertFalse(r["ok"])
            self.assertTrue(any("扩尺寸" in i for i in r["issues"]))

    def test_no_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            ppt_dir = os.path.join(tmp, "_ppt")
            os.makedirs(ppt_dir)
            with open(os.path.join(ppt_dir, "orig.pptx"), 'w') as f:
                f.write("x")
            with open(os.path.join(ppt_dir, "orig_expanded.pptx"), 'w') as f:
                f.write("x")
            # 缺图片
            r = _check_step1_ppt_expansion(tmp, ppt_dir)
            self.assertFalse(r["ok"])
            self.assertTrue(any("导出图片" in i for i in r["issues"]))


class TestStep2PptAnalysis(unittest.TestCase):
    """Step 2: PPT 视觉分析"""

    def test_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            ppt_dir = os.path.join(tmp, "_ppt")
            os.makedirs(ppt_dir)
            with open(os.path.join(ppt_dir, "_vision_report.json"), 'w') as f:
                f.write("{}")
            os.makedirs(os.path.join(ppt_dir, "_exported_images"))
            r = _check_step2_ppt_analysis(ppt_dir)
            self.assertTrue(r["ok"])

    def test_no_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            ppt_dir = os.path.join(tmp, "_ppt")
            os.makedirs(ppt_dir)
            r = _check_step2_ppt_analysis(ppt_dir)
            self.assertFalse(r["ok"])


class TestStep3Download(unittest.TestCase):
    """Step 3: 文献下载"""

    def test_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            dl_dir = os.path.join(tmp, "_download")
            os.makedirs(dl_dir)
            for pn in ['P1-1', 'P2-1', 'P3-1']:
                d = os.path.join(dl_dir, pn)
                os.makedirs(d)
                with open(os.path.join(d, "main.pdf"), 'w') as f:
                    f.write("x")
            r = _check_step3_download(dl_dir)
            self.assertTrue(r["ok"])
            self.assertEqual(r["counts"]["pn_x_dirs"], 3)
            self.assertEqual(r["counts"]["with_pdf"], 3)

    def test_missing_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            dl_dir = os.path.join(tmp, "_download")
            os.makedirs(dl_dir)
            os.makedirs(os.path.join(dl_dir, "P1-1"))  # 空
            os.makedirs(os.path.join(dl_dir, "P2-1"))
            with open(os.path.join(dl_dir, "P2-1/main.pdf"), 'w') as f:
                f.write("x")
            r = _check_step3_download(dl_dir)
            self.assertFalse(r["ok"])

    def test_no_pn_x(self):
        with tempfile.TemporaryDirectory() as tmp:
            dl_dir = os.path.join(tmp, "_download")
            os.makedirs(dl_dir)
            r = _check_step3_download(dl_dir)
            self.assertFalse(r["ok"])


class TestStep4Highlight(unittest.TestCase):
    """Step 4: Highlight"""

    def test_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            hl_dir = os.path.join(tmp, "_highlight")
            os.makedirs(hl_dir)
            for pn in ['P1-1', 'P2-1']:
                d = os.path.join(hl_dir, pn)
                os.makedirs(d)
                with open(os.path.join(d, "main.pdf"), 'w') as f:
                    f.write("x")
                with open(os.path.join(d, "page1_highlight.jpg"), 'w') as f:
                    f.write("x")
            dl_dir = os.path.join(tmp, "_download")
            os.makedirs(dl_dir)
            for pn in ['P1-1', 'P2-1']:
                os.makedirs(os.path.join(dl_dir, pn))
            r = _check_step4_highlight(hl_dir, dl_dir)
            self.assertTrue(r["ok"])

    def test_no_highlight_jpg(self):
        with tempfile.TemporaryDirectory() as tmp:
            hl_dir = os.path.join(tmp, "_highlight")
            os.makedirs(hl_dir)
            d = os.path.join(hl_dir, "P1-1")
            os.makedirs(d)
            with open(os.path.join(d, "main.pdf"), 'w') as f:
                f.write("x")
            # 缺 highlight jpg
            r = _check_step4_highlight(hl_dir, None)
            self.assertFalse(r["ok"])


class TestStep5Alignment(unittest.TestCase):
    """Step 5: 三方对齐"""

    def test_aligned(self):
        with tempfile.TemporaryDirectory() as tmp:
            dl_dir = os.path.join(tmp, "_download")
            hl_dir = os.path.join(tmp, "_highlight")
            os.makedirs(dl_dir)
            os.makedirs(hl_dir)
            for pn in ['P1-1', 'P2-1', 'P3-1']:
                os.makedirs(os.path.join(dl_dir, pn))
                os.makedirs(os.path.join(hl_dir, pn))
            r = _check_step5_alignment(None, dl_dir, hl_dir, tmp)
            self.assertTrue(r["ok"])

    def test_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            dl_dir = os.path.join(tmp, "_download")
            hl_dir = os.path.join(tmp, "_highlight")
            os.makedirs(dl_dir)
            os.makedirs(hl_dir)
            for pn in ['P1-1', 'P2-1']:
                os.makedirs(os.path.join(dl_dir, pn))
            for pn in ['P2-1', 'P3-1']:
                os.makedirs(os.path.join(hl_dir, pn))
            r = _check_step5_alignment(None, dl_dir, hl_dir, tmp)
            self.assertFalse(r["ok"])
            # 应该有 missing_in_hl (P1-1) 和 extra_in_hl (P3-1)
            self.assertIn("P1-1", r["info"]["missing_in_hl"])
            self.assertIn("P3-1", r["info"]["extra_in_hl"])


class TestStep6Merge(unittest.TestCase):
    """Step 6: 目录合并"""

    def test_merged_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            hl_dir = os.path.join(tmp, "_highlight")
            os.makedirs(hl_dir)
            # 用不同 PDF 名, 避免冲突检测
            for merged, fname in [
                ('P15-1_P16-1_P17-1', 'rimassa.pdf'),
                ('P23-10_P23-11', 'dandoy.pdf'),
            ]:
                d = os.path.join(hl_dir, merged)
                os.makedirs(d)
                with open(os.path.join(d, fname), 'w') as f:
                    f.write("x")
            r = _check_step6_merge(hl_dir)
            self.assertEqual(len(r["info"]["merged_dirs"]), 2)
            self.assertEqual(len(r["info"]["single_dirs"]), 0)
            self.assertTrue(r["ok"])

    def test_single_dirs_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            hl_dir = os.path.join(tmp, "_highlight")
            os.makedirs(hl_dir)
            for pn in ['P15-1', 'P16-1', 'P17-1']:
                d = os.path.join(hl_dir, pn)
                os.makedirs(d)
                with open(os.path.join(d, "main.pdf"), 'w') as f:
                    f.write("x")
            r = _check_step6_merge(hl_dir)
            # 单目录应被识别, 但 ok=False (因为没合并)
            self.assertEqual(len(r["info"]["single_dirs"]), 3)

    def test_conflict_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            hl_dir = os.path.join(tmp, "_highlight")
            os.makedirs(hl_dir)
            for pn in ['P15-1', 'P16-1']:
                d = os.path.join(hl_dir, pn)
                os.makedirs(d)
                # 同名 PDF 在两个目录
                with open(os.path.join(d, "main.pdf"), 'w') as f:
                    f.write("x")
            r = _check_step6_merge(hl_dir)
            self.assertFalse(r["ok"])
            self.assertTrue(any("冲突" in i for i in r["issues"]))


class TestCheckAll(unittest.TestCase):
    """完整 check_all"""

    def test_complete_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_pseudo_project(tmp)
            r = check_all(tmp)
            self.assertTrue(r["overall_ok"], f"应 OK, 实际: {[s['issues'] for s in r['steps']]}")
            self.assertEqual(r["summary"]["n_steps_total"], 7)

    def test_missing_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = check_all(tmp)
            self.assertFalse(r["overall_ok"])

    def test_nonexistent_project(self):
        r = check_all("/tmp/nonexistent_xyz_zzz")
        self.assertFalse(r["overall_ok"])
        self.assertIn("error", r)

    def test_print_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_pseudo_project(tmp)
            r = check_all(tmp)
            # 不应抛异常
            print_report(r, verbose=False)

    def test_print_report_verbose(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_pseudo_project(tmp)
            r = check_all(tmp)
            print_report(r, verbose=True)


class TestRealProject(unittest.TestCase):
    """真实 TMA 项目跑规则"""

    PROJECT = "/Users/david/Desktop/TMA_文献整理"

    def test_tma_project(self):
        if not os.path.isdir(self.PROJECT):
            self.skipTest("TMA 项目不存在")
        r = check_all(self.PROJECT)
        # 真实项目可能不过 (因为还有 gap), 但不抛异常
        self.assertIn("overall_ok", r)
        self.assertIn("steps", r)
        # 打印报告 (让人能看到)
        print("\n=== TMA 项目规则校验 ===")
        print_report(r, verbose=True)


class TestRulesText(unittest.TestCase):
    """规则文本完整性"""

    def test_text_has_all_6_steps(self):
        # 规则文本用中文数字 【步骤一】...【步骤六】
        chinese_nums = ["一", "二", "三", "四", "五", "六"]
        for n in chinese_nums:
            self.assertIn(f"步骤{n}", RULES_TEXT, f"缺步骤{n}")

    def test_text_mentions_critical_concepts(self):
        for kw in ["DOI", "Pn-x", "highlight", "扩页", "细黄线", "三方对齐", "合并"]:
            self.assertIn(kw, RULES_TEXT, f"规则文本缺关键词: {kw}")


class TestQuickCheck(unittest.TestCase):
    """quick_check 入口"""

    def test_quick_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            _make_pseudo_project(tmp)
            code = quick_check(tmp)
            self.assertEqual(code, 0)

    def test_quick_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = quick_check(tmp)
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
