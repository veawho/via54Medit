#!/usr/bin/env python3
"""
test_h_column_builder.py — H 列构建器单元测试 (v9.7 模块化拆分后)

测试拆分后每个模块的核心功能:
- parse: D/C 列解析
- scan: Pn-x 目录扫描
- detect: main PDF 错位检测
- links: 链接生成
- markdown: markdown → rich_text
- builder: build_h_md_v6 / build_h_rich_text_v6
"""
import os, sys, unittest, json, subprocess, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import h_column_builder

LIT_BASE = "/Users/david/Desktop/雷管方案_文献整理/_literature_citation_index"


class TestParseDField(unittest.TestCase):
    """parse.py: D 列解析"""

    def test_parse_standard_d(self):
        """标准 D 列 (作者 + 期刊 + 年份)"""
        d = "Zeng H, et al. J Natl Cancer Cent. 2024;6(1):39-50."
        info = h_column_builder.parse_d_field(d)
        self.assertEqual(info["journal"], "J Natl Cancer Cent")
        self.assertEqual(info["year"], "2024")
        self.assertIn("Zeng", info["authors"])

    def test_parse_chinese_government(self):
        """中文政府文件 D 列"""
        d = "国务院. 关于印发健康中国行动—癌症防治行动实施方案 (2023-2030) 的通知. 国办发〔2023〕11号. 2023."
        info = h_column_builder.parse_d_field(d)
        self.assertEqual(info["year"], "2023")

    def test_parse_globocan(self):
        """GLOBOCAN PDF - parse_d_field 限制, 但至少能提取年份"""
        d = "The Global Cancer Observatory (GLOBOCAN 2024)"
        info = h_column_builder.parse_d_field(d)
        self.assertEqual(info["year"], "2024")

    def test_parse_4a_style_authors(self):
        """'Peter Robert Galle, Thomas Decaens' 形式作者"""
        d = "Peter Robert Galle, Thomas Decaens, Masatoshi Kudo. Lancet. 2025"
        info = h_column_builder.parse_d_field(d)
        self.assertEqual(info["year"], "2025")


class TestParseCField(unittest.TestCase):
    """parse.py: C 列解析 (PPT 标号位置 + 视觉内容)"""

    def test_parse_simple_c(self):
        c = "PPT标号3: 中国肝癌5年生存率仅14.4%, 远低于其他癌种"
        info = h_column_builder.parse_c_field(c)
        self.assertIn("data_alignment", info)
        self.assertIn("visual_alignment", info)


class TestIdentifyPublisher(unittest.TestCase):
    """links.py: 出版商识别"""

    def test_identify_lancet(self):
        self.assertIn("Elsevier", h_column_builder.identify_publisher("Lancet"))

    def test_identify_nejm(self):
        self.assertIn("Massachusetts", h_column_builder.identify_publisher("N Engl J Med"))

    def test_identify_jco(self):
        self.assertIn("ASCO", h_column_builder.identify_publisher("J Clin Oncol"))

    def test_identify_jama(self):
        self.assertIn("AMA", h_column_builder.identify_publisher("JAMA"))

    def test_identify_globocan(self):
        self.assertIn("IARC", h_column_builder.identify_publisher("GLOBOCAN"))

    def test_identify_unknown(self):
        self.assertEqual("", h_column_builder.identify_publisher(""))


class TestGetPublisherPdfUrls(unittest.TestCase):
    """links.py: URL 生成 (DOI 主链接 + PubMed + Europe PMC + verified URL)"""

    def test_get_urls_with_doi(self):
        urls = h_column_builder.get_publisher_pdf_urls("10.1056/NEJMoa1915745")
        labels = [u[0] for u in urls]
        self.assertIn("DOI 主链接", labels)
        self.assertIn("PubMed 搜索", labels)
        self.assertIn("Europe PMC 搜索", labels)

    def test_get_urls_with_verified(self):
        urls = h_column_builder.get_publisher_pdf_urls(
            "10.1056/NEJMoa1915745",
            verified_url="https://www.nejm.org/doi/full/10.1056/NEJMoa1915745"
        )
        # verified URL 会被推断为 NEJM 全文 (含 全文 后缀)
        self.assertIn("NEJM", urls[0][0])
        self.assertIn("全文", urls[0][0])

    def test_get_urls_empty_doi(self):
        self.assertEqual(h_column_builder.get_publisher_pdf_urls(""), [])

    def test_get_urls_note_doi(self):
        self.assertEqual(h_column_builder.get_publisher_pdf_urls("备注: 无 DOI"), [])


class TestDetectMainPdfMismatch(unittest.TestCase):
    """detect.py: main PDF 错位检测"""

    def test_detect_p33_9_mismatch(self):
        """P33-9 D 列 Cheng J Hepatol 2022, main 是 Galle Lancet 2025 - 错位"""
        scan = h_column_builder.scan_pn_x_dir("P33-9", LIT_BASE)
        info_d = h_column_builder.parse_d_field("Cheng AL, et al. J Hepatol. 2022;76(4):862-873.")
        mismatch = h_column_builder.detect_main_pdf_mismatch(
            "P33-9", info_d, scan, d_raw="Cheng AL, et al. J Hepatol. 2022;76(4):862-873."
        )
        self.assertIsNotNone(mismatch)
        self.assertEqual(mismatch["mismatch_type"], "无任何关键词匹配")

    def test_no_mismatch_p5_10(self):
        """P5-10 main 是 Qin LancetOncol 2025 - filename check 通过"""
        scan = h_column_builder.scan_pn_x_dir("P5-10", LIT_BASE)
        info_d = h_column_builder.parse_d_field("Qin S, et al. Lancet Oncol. 2025;26(12):1598-1611.")
        # filename check 会匹配, 但 content check 会发现是 Protocol
        mismatch_fname = h_column_builder.detect_main_pdf_mismatch(
            "P5-10", info_d, scan, d_raw="Qin S, et al. Lancet Oncol. 2025;26(12):1598-1611."
        )
        # 正常情况下 filename 匹配 (因为文件名含 Qin_LancetOncol_2025)
        # 但 content check 会发现是 Study Protocol
        mismatch_content = h_column_builder.detect_main_pdf_content_mismatch(
            "P5-10", info_d, scan, d_raw="Qin S, et al. Lancet Oncol. 2025;26(12):1598-1611."
        )
        # content check 必捕获 (是 Study Protocol)
        self.assertIsNotNone(mismatch_content)
        self.assertIn("Protocol", mismatch_content["mismatch_type"])


class TestScanPnXDir(unittest.TestCase):
    """scan.py: Pn-x 目录扫描"""

    def test_scan_p3_1(self):
        scan = h_column_builder.scan_pn_x_dir("P3-1", LIT_BASE)
        self.assertGreater(len(scan["main"]), 0)
        self.assertIn("manifest", scan)

    def test_scan_nonexistent(self):
        scan = h_column_builder.scan_pn_x_dir("P999-99", LIT_BASE)
        self.assertEqual(scan["main"], [])
        self.assertEqual(scan["fb"], [])


class TestBuildHMarkdown(unittest.TestCase):
    """markdown.py: build_h_md_v6 主入口"""

    def setUp(self):
        self.lit_base = LIT_BASE
        self.scan = h_column_builder.scan_pn_x_dir("P3-1", LIT_BASE)
        self.info_d = h_column_builder.parse_d_field("The Global Cancer Observatory (GLOBOCAN 2024)")
        self.info_c = h_column_builder.parse_c_field("PPT标号1: 中国肝癌新发和死亡病例占全球近半数1")

    def test_build_h_md_v6_p3_1(self):
        """P3-1 应该含 Vision OCR 段 (因为是图片层 PDF)"""
        md = h_column_builder.build_h_md_v6(
            "P3-1", self.info_d, self.info_c, "", self.scan, "", 2, self.lit_base,
            d="The Global Cancer Observatory (GLOBOCAN 2024)"
        )
        self.assertGreater(len(md), 500)
        self.assertIn("【🎯", md)
        self.assertIn("【📄 主文件】", md)
        self.assertIn("【📸 Vision OCR】", md)  # P3-1 有 vision OCR

    def test_build_h_md_v6_p33_9_mismatch(self):
        """P33-9 应该含 ⚠️ main PDF 错位"""
        scan = h_column_builder.scan_pn_x_dir("P33-9", LIT_BASE)
        info_d = h_column_builder.parse_d_field("Cheng AL, et al. J Hepatol. 2022;76(4):862-873.")
        md = h_column_builder.build_h_md_v6(
            "P33-9", info_d, {}, "", scan, "", 105, LIT_BASE,
            d="Cheng AL, et al. J Hepatol. 2022;76(4):862-873."
        )
        self.assertIn("main PDF 错位", md)


class TestMarkdownToRichText(unittest.TestCase):
    """markdown.py: markdown → rich_text 转换"""

    def test_simple_text(self):
        md = "Hello World"
        rt = h_column_builder.markdown_to_rich_text(md)
        self.assertEqual(len(rt), 1)
        self.assertEqual(rt[0]["type"], "text")
        self.assertIn("Hello", rt[0]["text"])

    def test_with_link(self):
        md = "Click [here](https://example.com)"
        rt = h_column_builder.markdown_to_rich_text(md)
        types = [seg["type"] for seg in rt]
        self.assertIn("link", types)
        link_seg = next(s for s in rt if s["type"] == "link")
        self.assertEqual(link_seg["link"], "https://example.com")

    def test_with_bare_url(self):
        md = "See https://example.com for details"
        rt = h_column_builder.markdown_to_rich_text(md)
        types = [seg["type"] for seg in rt]
        self.assertIn("link", types)

    def test_with_newlines(self):
        md = "Line 1\nLine 2\nLine 3"
        rt = h_column_builder.markdown_to_rich_text(md)
        # 飞书 rich_text 必须含 \n 保留换行
        self.assertIn("\n", rt[0]["text"])

    def test_empty_md(self):
        rt = h_column_builder.markdown_to_rich_text("")
        self.assertEqual(rt, [])


class TestIntegration(unittest.TestCase):
    """端到端集成测试"""

    def test_p5_18_full_flow(self):
        """P5-18 Lau J Hepatol 2025 完整流程"""
        scan = h_column_builder.scan_pn_x_dir("P5-18", LIT_BASE)
        info_d = h_column_builder.parse_d_field("Lau G, et al. J Hepatol, 2025, 82(2): 258-267.")
        info_c = h_column_builder.parse_c_field("PPT标号18: Lau G 等 J Hepatol 2025 5-year update")
        
        md = h_column_builder.build_h_md_v6(
            "P5-18", info_d, info_c, "10.1016/j.jhep.2024.10.009", scan, "", 30, LIT_BASE,
            d="Lau G, et al. J Hepatol, 2025, 82(2): 258-267."
        )
        rt = h_column_builder.markdown_to_rich_text(md)
        
        # 验证 rich_text 完整
        self.assertGreater(len(rt), 3)
        types = [seg.get("type") for seg in rt]
        self.assertIn("link", types)  # 含 DOI 链接


if __name__ == "__main__":
    unittest.main(verbosity=2)
