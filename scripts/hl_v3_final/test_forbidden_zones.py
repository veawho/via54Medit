#!/usr/bin/env python3
"""
test_forbidden_zones.py — verify_forbidden_zones.py 的单测

两类测试缺一不可:

1. **正向 (抓得到)**: 真的把高亮盖在页眉带 / 作者单位 / 页脚页码 / 参考文献条目上时,
   必须报违规。没有这一半, 一个"永远返回 0"的实现也能通过全部测试。

2. **负向 (不误报)**: 把移植过程中实测到的 6 个误报逐一钉住 ——
   `in-hospital` 被当机构名、`AMD3` 被当学位、`doctors` 被当 `Dr.`、
   `1980s` 被当年份、行文夹注被当参考文献条目、中文刊摘要被当作者区。
   这些是**原 v13 规则的真实缺陷**, 钉住它们才能防止有人把规则再改松回去。

用 pymupdf 现场生成 PDF 与 Square 注记, 不依赖任何外部数据。
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from verify_forbidden_zones import (  # noqa: E402
    audit_pdf,
    check_geometry_violations,
    check_hard_violations,
    check_soft_flags,
    is_page_furniture,
    is_ref_entry,
    iter_highlight_pdfs,
)


# ════════════════════════════════════════════════════════════════
# 构造用工具
# ════════════════════════════════════════════════════════════════

PAGE_W, PAGE_H = 595.0, 842.0  # A4


def _make_pdf(path, items):
    """建一个 PDF, 在给定位置插入文字并加 Square 注记。

    items: [(text, y0, x0)] —— 文字画在该 y 位置, 并在文字处加一个高亮注记。
    返回实际使用的 rect 列表 (顺序同 items)。
    """
    doc = fitz.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    rects = []
    for text, y0, x0 in items:
        page.insert_text((x0, y0), text, fontsize=9)
        rect = fitz.Rect(x0, y0 - 9, min(x0 + 220, PAGE_W - 20), y0 + 2)
        annot = page.add_rect_annot(rect)   # -> Square (type 4)
        annot.set_colors(stroke=(1.0, 0.85, 0.0), fill=(1.0, 0.85, 0.0))
        annot.set_opacity(0.45)
        annot.update()
        rects.append(rect)
    doc.save(path)
    doc.close()
    return rects


def _make_square_annot_page(doc, text, y0, x0=60.0):
    """在已有 doc 的最后一页加一条文字 + Square 注记, 返回 rect。"""
    page = doc[-1]
    page.insert_text((x0, y0), text, fontsize=9)
    rect = fitz.Rect(x0, y0 - 9, min(x0 + 220, PAGE_W - 20), y0 + 2)
    annot = page.add_rect_annot(rect)
    annot.set_colors(stroke=(1.0, 0.85, 0.0), fill=(1.0, 0.85, 0.0))
    annot.set_opacity(0.45)
    annot.update()
    return rect


# ════════════════════════════════════════════════════════════════
# 1. 正向: 必须抓得到
# ════════════════════════════════════════════════════════════════

class TestDetectsRealViolations(unittest.TestCase):

    def test_detects_header_zone(self):
        """注记完全落在页面最上沿 (5% 以内) -> top_5%_header。"""
        rect = fitz.Rect(60, 2, 260, 20)  # y1=20 < 842*0.05=42.1
        v = check_geometry_violations(rect, PAGE_W, PAGE_H)
        self.assertIn("top_5%_header", [k for k, _ in v])

    def test_detects_author_block_by_content(self):
        """作者单位标记 —— 按内容判定, 不靠几何位置。"""
        v = check_hard_violations(None, fitz.Rect(60, 400, 400, 415), PAGE_H,
                                  "Department of Nephrology, University of Tokyo")
        self.assertIn("author_block", [k for k, _ in v])

    def test_detects_chinese_author_block(self):
        v = check_hard_violations(None, fitz.Rect(60, 400, 400, 415), PAGE_H,
                                  "作者单位：中南大学湘雅医院肾内科")
        self.assertIn("author_block", [k for k, _ in v])

    def test_detects_footer_page_number(self):
        """页脚区 + 纯页码 -> footer_furniture。"""
        rect = fitz.Rect(300, 800, 320, 812)   # y0=800 > 842*0.92=774.6
        v = check_hard_violations(None, rect, PAGE_H, "1234")
        self.assertIn("footer_furniture", [k for k, _ in v])

    def test_detects_footer_download_watermark(self):
        rect = fitz.Rect(60, 800, 400, 812)
        v = check_hard_violations(None, rect, PAGE_H,
                                  "Downloaded from https://academic.oup.com/x")
        self.assertIn("footer_furniture", [k for k, _ in v])

    def test_detects_reference_entry(self):
        """真条目: 年份 + 两个标记 (et al. + 卷(期):页)。"""
        self.assertTrue(is_ref_entry(
            "Smith JA, et al. Blood 2019;134(2):123-130.", min_markers=2))

    def test_detects_reference_section_via_audit(self):
        """端到端: 在**最后一页下半页**把高亮盖在文献条目上 -> 报违规。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "t.pdf")
            doc = fitz.open()
            for _ in range(3):
                doc.new_page(width=PAGE_W, height=PAGE_H)
            _make_square_annot_page(
                doc, "Smith JA, et al. Blood 2019;134(2):123-130.", y0=700)
            doc.save(p)
            doc.close()

            r = audit_pdf(p, min_bytes=0)
            self.assertEqual(r["total"], 1)
            self.assertEqual(len(r["violations"]), 1)
            kinds = [k for k, _ in r["violations"][0]["violations"]]
            self.assertIn("reference_section", kinds)

    def test_detects_keywords_block(self):
        v = check_hard_violations(None, fitz.Rect(60, 200, 400, 215), PAGE_H,
                                  "关键词：血栓性微血管病；补体")
        self.assertIn("keywords_text", [k for k, _ in v])

    def test_detects_oversize_rect(self):
        rect = fitz.Rect(20, 100, PAGE_W - 20, 700)  # 宽>85% 且 高>25%
        v = check_geometry_violations(rect, PAGE_W, PAGE_H)
        self.assertIn("too_wide_and_tall", [k for k, _ in v])
        self.assertIn("too_tall", [k for k, _ in v])

    def test_end_to_end_flags_and_exit_semantics(self):
        """有真违规时 audit_pdf 必须报出来 (main 据此返回 1)。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "t.pdf")
            _make_pdf(p, [("Department of Nephrology, University of Tokyo", 400, 60)])
            r = audit_pdf(p, min_bytes=0)
            self.assertEqual(r["total"], 1)
            self.assertTrue(r["violations"], "作者单位被高亮却未报违规")

    def test_small_file_is_skipped_as_broken(self):
        """< min_bytes 视为错件/占位跳过 (真实数据里最小的是 4738 字节的 P12-3 占位)。

        这条保护是有意保留的, 否则一个 2KB 的错误页会被当成正常 highlight 审计。
        """
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "t.pdf")
            _make_pdf(p, [("Department of Nephrology, University of Tokyo", 400, 60)])
            self.assertLess(os.path.getsize(p), 2500)
            r = audit_pdf(p)          # 默认阈值 2500
            self.assertTrue(r["skipped"])
            self.assertEqual(r["total"], 0)


# ════════════════════════════════════════════════════════════════
# 2. 负向: 6 个实测误报, 一个都不许复活
# ════════════════════════════════════════════════════════════════

class TestNoFalsePositives(unittest.TestCase):
    """每一条都对应移植时在真实数据上核实过的一次误报。"""

    def _author_block(self, text):
        v = check_hard_violations(None, fitz.Rect(60, 400, 400, 415), PAGE_H, text)
        return [k for k, _ in v]

    def test_in_hospital_is_not_an_affiliation(self):
        """P28-4 实测: "in-hospital mortality" 被当成机构名 Hospital。"""
        self.assertNotIn("author_block",
                         self._author_block("with higher in-hospital mortality (adjusted OR, 1.615"))

    def test_AMD3_is_not_a_degree(self):
        """P6-1 实测: "AMD3" 里的 MD 被当成学位缩写。"""
        self.assertNotIn("author_block",
                         self._author_block("Alzheimer disease, atherosclerosis and AMD3"))

    def test_doctors_is_not_Prof_Dr(self):
        """P11-6 实测: 正文里的 "doctors" 被当成 "Dr."。"""
        self.assertNotIn("author_block",
                         self._author_block("several doctors in southern Italy and Sardinia drew a"))

    def test_1980s_is_not_a_year(self):
        """P3-2/P4-2/P7-1 实测: "In the 1970s and 1980s..." 被当成文献条目。

        \\b(19|20)\\d{2}\\b 不该命中 "1980s" —— 数字后紧跟 s, 没有词边界。
        """
        self.assertFalse(is_ref_entry("In the 1970s and 1980s, as the complexities of the C cascade"))

    def test_inline_citation_is_not_a_reference_entry(self):
        """P4-4 实测: 行文夹注只有 1 个标记, 高亮正文句子是合法的。"""
        text = ("will impair the antibody responses since C3d is a natural adjuvant,"
                "\net al., 2009).")
        self.assertFalse(is_ref_entry(text, min_markers=2))
        # 违规级的调用方也必须用 2 个标记的门槛 —— 否则这条正文夹注会被报成违规
        v = check_hard_violations(None, fitz.Rect(60, 400, 400, 415), PAGE_H, text)
        self.assertNotIn("reference_entry", [k for k, _ in v])
        # 但它仍应作为"待人工判断"被报出来, 不能被静默丢弃
        w = check_soft_flags(fitz.Rect(60, 400, 400, 415), PAGE_W, PAGE_H, 0, text)
        self.assertIn("ref_pattern_in_body", [k for k, _ in w])

    def test_chinese_abstract_is_not_author_block(self):
        """P9-3 实测: 该刊标题 13.9% / 作者 18.3% / 正文 22% 起, 规则却把摘要判成作者区。

        正文散文不应进违规级 —— 它至多是"待人工判断"。
        """
        text = "血栓性微血管病是由各种原因所致的一组以微血管病性溶血性贫血"
        v = check_hard_violations(None, fitz.Rect(60, 200, 300, 215), PAGE_H, text)
        self.assertNotIn("author_block", [k for k, _ in v])
        self.assertNotIn("reference_entry", [k for k, _ in v])

    def test_numbered_body_list_is_not_a_reference_entry(self):
        """P12-2 实测: 中文摘要里的 "4. 微血管病性溶血：..." 被当成文献条目。"""
        self.assertFalse(is_ref_entry("4. 微血管病性溶血：较少发生，表现为进行性"))

    def test_body_text_below_92pct_is_not_footer(self):
        """P14-2/P31-4/P4-4 实测: 正文排到 92% 以下不等于页脚。"""
        rect = fitz.Rect(60, 780, 400, 795)   # 在页脚区
        v = check_hard_violations(
            None, rect, PAGE_H,
            "The defining laboratory features comprise thrombocytopenia, resulting from platelet")
        self.assertNotIn("footer_furniture", [k for k, _ in v])

    def test_page_furniture_helper(self):
        self.assertTrue(is_page_furniture("1234"))
        self.assertTrue(is_page_furniture("Downloaded from https://x.org/a"))
        self.assertFalse(is_page_furniture(
            "The defining laboratory features comprise thrombocytopenia, resulting"))
        # 短且无句末标点 -> 视为附属物
        self.assertTrue(is_page_furniture("Vol. 134"))

    def test_figure_caption_is_warning_not_violation(self):
        """图表标题有规范例外 (图表即应证对象), 只能人工判断, 不进 gate。"""
        w = check_soft_flags(fitz.Rect(60, 700, 400, 715), PAGE_W, PAGE_H, 0,
                             "Fig 3. Anti-complement therapy can target different components")
        self.assertIn("figure_caption", [k for k, _ in w])

    def test_normal_body_sentence_is_clean(self):
        """完全正常的一条正文高亮 -> 零违规零警告。"""
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "t.pdf")
            _make_pdf(p, [("The defining laboratory features comprise thrombocytopenia.", 400, 60)])
            r = audit_pdf(p, min_bytes=0)
            self.assertEqual(r["total"], 1)
            self.assertEqual(r["violations"], [])
            self.assertEqual(r["warnings"], [])


# ════════════════════════════════════════════════════════════════
# 3. 发现逻辑
# ════════════════════════════════════════════════════════════════

class TestDiscovery(unittest.TestCase):

    def test_finds_nested_and_flat_and_skips_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            # 嵌套 (v3 FINAL): {Pn-x}/{PN}_highlight.pdf + {PN}_main.pdf
            d1 = os.path.join(tmp, "P1-1")
            os.makedirs(d1)
            open(os.path.join(d1, "P1-1_highlight.pdf"), "w").close()
            open(os.path.join(d1, "P1-1_main.pdf"), "w").close()
            # 扁平 (v13): {pn}_semantic_highlight.pdf
            open(os.path.join(tmp, "P2-1_semantic_highlight.pdf"), "w").close()
            # 干扰项: 页面 PNG 目录里不该有 PDF, 但也不许被当成 highlight
            os.makedirs(os.path.join(tmp, "P1-1", "P1-1_highlight_pages"))

            got = dict(iter_highlight_pdfs(tmp))
            self.assertEqual(sorted(got), ["P1-1", "P2-1"])
            self.assertTrue(got["P1-1"].endswith("P1-1_highlight.pdf"))
            self.assertTrue(got["P2-1"].endswith("P2-1_semantic_highlight.pdf"))

    def test_returns_empty_for_bare_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(iter_highlight_pdfs(tmp), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
