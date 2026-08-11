#!/usr/bin/env python3
"""
test_pdf_understand.py — pdf_understand.py 单测

覆盖:
  - docling parse 缓存
  - find_data_point_in_doc (table cell + text)
  - extract_ppt_data_points (数字+百分比变体)
  - semantic_match_ppt_to_pdf (综合应证)
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, "/Users/david/Desktop/developments/via54Medit/scripts")

from pdf_understand import (
    parse_pdf_with_docling,
    find_data_point_in_doc,
    extract_ppt_data_points,
    semantic_match_ppt_to_pdf,
)


P4_1 = "/Users/david/Desktop/雷管方案_文献整理/P4-1/P4-1_main_Lin_FrontOncol_2022.pdf"
P3_1 = "/Users/david/Desktop/雷管方案_文献整理/P3-1/P3-1_main_GLOBOCAN_2022_Liver_IARC.pdf"


class TestParsePdfWithDocling(unittest.TestCase):
    """docling parse 缓存"""

    def test_parse_p4_1(self):
        doc = parse_pdf_with_docling(P4_1)
        self.assertGreater(len(doc.get("tables", [])), 0)
        self.assertGreater(len(doc.get("pages", {})), 0)

    def test_parse_cache(self):
        # 第二次 parse 应该用缓存 (快速)
        import time
        t1 = time.time()
        parse_pdf_with_docling(P4_1)
        t2 = time.time()
        # 缓存应该 < 0.5s
        self.assertLess(t2 - t1, 0.5)


class TestFindDataPointInDoc(unittest.TestCase):
    """find_data_point_in_doc 数据点搜索"""

    def test_find_bclc(self):
        doc = parse_pdf_with_docling(P4_1)
        matches = find_data_point_in_doc(doc, "BCLC")
        self.assertGreater(len(matches), 5)
        # 至少有一个 table_cell 类型
        types = set(m["type"] for m in matches)
        self.assertIn("table_cell", types)

    def test_find_36_7(self):
        doc = parse_pdf_with_docling(P4_1)
        matches = find_data_point_in_doc(doc, "36.7")
        self.assertEqual(len(matches), 1)
        # page 4
        self.assertEqual(matches[0]["page_no"], 4)
        # 含 "36.7"
        self.assertIn("36.7", matches[0]["text"])
        # 含 bbox
        self.assertIn("bbox", matches[0])

    def test_find_17_6(self):
        doc = parse_pdf_with_docling(P4_1)
        matches = find_data_point_in_doc(doc, "17.6")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["page_no"], 4)

    def test_find_87_0(self):
        doc = parse_pdf_with_docling(P4_1)
        matches = find_data_point_in_doc(doc, "87.0")
        # page 4 + page 8
        pages = set(m["page_no"] for m in matches)
        self.assertIn(4, pages)
        self.assertIn(8, pages)


class TestExtractPptDataPoints(unittest.TestCase):
    """extract_ppt_data_points 智能抽取"""

    def test_extract_percent_with_and_without(self):
        ppt = "BCLC B 36.7%, BCLC C 17.6%"
        points = extract_ppt_data_points(ppt)
        self.assertIn("36.7", points)
        self.assertIn("36.7%", points)
        self.assertIn("17.6", points)
        self.assertIn("17.6%", points)

    def test_extract_decimal(self):
        ppt = "Tumor ≥3cm 87.0%, Thrombus 34.5%"
        points = extract_ppt_data_points(ppt)
        self.assertIn("87.0", points)
        self.assertIn("34.5", points)

    def test_extract_medical_terms(self):
        ppt = "BCLC B 中期 36.7%, HBV 高感染率, HCC 占比"
        points = extract_ppt_data_points(ppt)
        self.assertIn("BCLC B", points)
        self.assertIn("BCLC", points)
        self.assertIn("HBV", points)
        self.assertIn("HCC", points)


class TestSemanticMatchPptToPdf(unittest.TestCase):
    """semantic_match_ppt_to_pdf 综合应证"""

    def test_p4_1_match(self):
        ppt = """标号 1: 「中国的HCC患者初诊时候大部分都是中晚期」
PPT 数据: BCLC B (中期) 36.7%, BCLC C (晚期) 17.6%, Tumor ≥3cm 87.0%, Thrombus 34.5%"""
        result = semantic_match_ppt_to_pdf(ppt, P4_1)
        # 关键数据点全找到
        for dp in ["36.7", "17.6", "87.0", "34.5", "BCLC B", "BCLC C"]:
            self.assertGreater(
                len(result["matches"][dp]), 0,
                f"{dp} 应找到但没找到"
            )
        # 得分 > 0.5
        self.assertGreater(result["score"], 0.5)


class TestDoclingStructure(unittest.TestCase):
    """docling 输出结构"""

    def test_p4_1_has_5_tables(self):
        doc = parse_pdf_with_docling(P4_1)
        tables = doc["tables"]
        self.assertEqual(len(tables), 5)
        # Table 0 在 page 4
        prov = tables[0]["prov"][0]
        self.assertEqual(prov["page_no"], 4)
        # Table 0 含 43 行 x 7 列
        data = tables[0]["data"]
        self.assertEqual(data["num_rows"], 43)
        self.assertEqual(data["num_cols"], 7)

    def test_table_cell_has_bbox(self):
        doc = parse_pdf_with_docling(P4_1)
        cells = doc["tables"][0]["data"]["table_cells"]
        # 每个 cell 都有 bbox
        for c in cells:
            self.assertIn("bbox", c)
            self.assertIn("l", c["bbox"])
            self.assertIn("t", c["bbox"])
            self.assertIn("r", c["bbox"])
            self.assertIn("b", c["bbox"])


if __name__ == "__main__":
    unittest.main(verbosity=2)