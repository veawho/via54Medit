#!/usr/bin/env python3
"""
test_citation_sync.py — citation_sync.py + link_health.py 的单测

覆盖:
  1. classify_link 类型分类 (4 大类 + 白名单)
  2. lock_row_anchors 锚点正确性
  3. assert_no_collision 防错位
  4. detect_expiry_mismatch 时效检测
  5. get_pnx_expiry 白名单
  6. rich_text_to_markdown 反向解析
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, "/Users/david/Desktop/developments/via54Medit/scripts")

from citation_sync import (
    lock_row_anchors,
    read_truth_row,
    assert_no_collision,
    rich_text_to_markdown,
    CollisionError,
)
from link_health import (
    classify_link,
    detect_expiry_mismatch,
    get_pnx_expiry,
    extract_links_from_h,
)


class TestClassifyLink(unittest.TestCase):
    """classify_link 类型分类测试"""

    def test_a_frontiers_pdf(self):
        info = classify_link("https://www.frontiersin.org/articles/10.3389/fonc.2022.906778/pdf")
        self.assertEqual(info["type"], "A_OFFICIAL_PDF_OPEN")
        self.assertEqual(info["expected_status"], 200)

    def test_a_mdpi_pdf(self):
        info = classify_link("https://www.mdpi.com/1422-0067/25/13/7191/pdf")
        self.assertEqual(info["type"], "A_OFFICIAL_PDF_OPEN")

    def test_a_iarc_globocan_pdf(self):
        info = classify_link("https://gco.iarc.who.int/today/data/factsheets/cancers/11-Liver-fact-sheet.pdf")
        self.assertEqual(info["type"], "A_OFFICIAL_PDF")
        self.assertIn("GLOBOCAN", info["label"])

    def test_a_wiley_paywall(self):
        info = classify_link("https://onlinelibrary.wiley.com/doi/pdf/10.1111/liv.12818")
        self.assertEqual(info["type"], "A_OFFICIAL_PDF_PAYWALL")
        self.assertEqual(info["expected_status"], 403)

    def test_b_pmc_page(self):
        info = classify_link("https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11401485/")
        self.assertEqual(info["type"], "B_PMC_PAGE")

    def test_c_doi(self):
        info = classify_link("https://doi.org/10.3322/caac.21834")
        self.assertEqual(info["type"], "C_DOI")
        self.assertEqual(info["expected_status"], 302)

    def test_d_local(self):
        info = classify_link("file:///Users/david/test.pdf")
        self.assertEqual(info["type"], "D_LOCAL")
        self.assertEqual(info["expected_status"], None)

    def test_e_wayback(self):
        info = classify_link("https://web.archive.org/web/2023/https://example.com")
        self.assertEqual(info["type"], "E_WAYBACK")

    def test_gov_nhc(self):
        info = classify_link("http://www.nhc.gov.cn/yzygj/s7659/202302/test.shtml")
        self.assertEqual(info["type"], "G_GOV_PAGE")

    def test_empty(self):
        info = classify_link("")
        self.assertEqual(info["type"], "EMPTY")

    def test_unknown(self):
        info = classify_link("https://random-site.com/path/to/file")
        self.assertEqual(info["type"], "UNKNOWN")


class TestDetectExpiryMismatch(unittest.TestCase):
    """时效差异检测"""

    def test_globocan_2022(self):
        expiry = detect_expiry_mismatch(
            "https://gco.iarc.who.int/today/data/factsheets/2022/cancers.pdf", "IARC GLOBOCAN"
        )
        self.assertIsNotNone(expiry)
        self.assertEqual(expiry["type"], "EXPIRED_REPLACED")
        self.assertEqual(expiry["url_year"], "2022")
        self.assertEqual(expiry["current_year"], "2024")

    def test_globocan_2024_no_expiry(self):
        expiry = detect_expiry_mismatch(
            "https://gco.iarc.who.int/today/data/factsheets/cancers.pdf", "IARC GLOBOCAN"
        )
        self.assertIsNone(expiry)

    def test_non_globocan_2022(self):
        # URL 含 2022 但不是 IARC — 不触发
        expiry = detect_expiry_mismatch(
            "https://doi.org/2022/test", "DOI"
        )
        self.assertIsNone(expiry)


class TestPnxExpiryWhitelist(unittest.TestCase):
    """Pn-x 时效差异白名单"""

    def test_p3_1_globocan(self):
        expiry = get_pnx_expiry("P3-1")
        self.assertIsNotNone(expiry)
        self.assertEqual(expiry["type"], "EXPIRED_REPLACED")
        self.assertIn("GLOBOCAN 2022", expiry["reason"])
        self.assertIn("36.8万", expiry["annotation"])
        self.assertIn("35.4万", expiry["annotation"])

    def test_unknown_pnx(self):
        expiry = get_pnx_expiry("P99-99")
        self.assertIsNone(expiry)


class TestLockRowAnchors(unittest.TestCase):
    """lock_row_anchors 锚点"""

    def test_row_6_is_p4_1(self):
        anchors = lock_row_anchors(6, window=2)
        row_6 = anchors[6]
        self.assertEqual(row_6["A_ppt_page"], "4")
        self.assertEqual(row_6["B_mark"], "1")
        self.assertEqual(row_6["expected_pnx"], "P4-1")

    def test_row_2_is_p3_1(self):
        anchors = lock_row_anchors(2, window=2)
        row_2 = anchors[2]
        self.assertEqual(row_2["expected_pnx"], "P3-1")


class TestAssertNoCollision(unittest.TestCase):
    """assert_no_collision 防错位"""

    def test_correct_pnx_passes(self):
        anchors = {6: {"expected_pnx": "P4-1"}}
        # 应该不抛异常
        assert_no_collision(6, "P4-1", anchors)

    def test_wrong_pnx_raises(self):
        anchors = {6: {"expected_pnx": "P4-1"}}
        with self.assertRaises(CollisionError):
            assert_no_collision(6, "P5-1", anchors)


class TestRichTextToMarkdown(unittest.TestCase):
    """rich_text → markdown"""

    def test_text_only(self):
        rt = [{"type": "text", "text": "hello"}]
        self.assertEqual(rich_text_to_markdown(rt), "hello")

    def test_link(self):
        rt = [
            {"type": "text", "text": "DOI: "},
            {"type": "link", "text": "10.1234/abc", "link": "https://doi.org/10.1234/abc"},
        ]
        md = rich_text_to_markdown(rt)
        self.assertIn("DOI: ", md)
        self.assertIn("[10.1234/abc](https://doi.org/10.1234/abc)", md)

    def test_mixed(self):
        rt = [
            {"type": "text", "text": "title\n"},
            {"type": "link", "text": "link", "link": "https://example.com"},
            {"type": "text", "text": "\nend"},
        ]
        md = rich_text_to_markdown(rt)
        self.assertIn("[link](https://example.com)", md)
        self.assertIn("end", md)


class TestExtractLinks(unittest.TestCase):
    """从 markdown 提取 URL"""

    def test_https_link(self):
        h = "DOI: [10.1234/abc](https://doi.org/10.1234/abc)"
        urls = extract_links_from_h(h)
        self.assertEqual(urls, ["https://doi.org/10.1234/abc"])

    def test_mixed(self):
        h = "[Frontiers](https://frontiersin.org/x/pdf)\n本地: [file](file:///Users/x.pdf)"
        urls = extract_links_from_h(h)
        self.assertIn("https://frontiersin.org/x/pdf", urls)
        self.assertIn("file:///Users/x.pdf", urls)

    def test_no_link(self):
        urls = extract_links_from_h("no links here")
        self.assertEqual(urls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)