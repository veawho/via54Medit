#!/usr/bin/env python3
"""
test_ppt_understand.py — Step 1 PPT 视觉理解 + Step 2 PDF highlight 验证

覆盖:
  1) ppt_understand.py — find_citation_marks_v2 语义驱动
  2) pdf_understand.py — verify_highlight_alignment
  3) ppt_understand.py — build_ppt_vision_report / get_ppt_mark_context

共 8 个单测
"""
import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from ppt_understand import (
    extract_ppt_slide,
    find_citation_marks_v2,
    get_ppt_mark_context,
    build_ppt_vision_report,
    _extract_table_citation_marks,
    PPT_PATH,
)
from pdf_understand import (
    verify_highlight_alignment,
    extract_ppt_data_points,
    find_all_ppt_data_points,
    parse_pdf_with_docling,
)

P41_MAIN = (
    "/Users/david/Desktop/雷管方案_文献整理/"
    "_literature_citation_index/P4-1/"
    "P4-1_main_Lin_FrontOncol_2022.pdf"
)

# ═══════════════════════════════════════════════════════════════════════════


def test_extract_p5_structure():
    """P5 结构提取"""
    structures = extract_ppt_slide(PPT_PATH, 5)
    assert len(structures) > 0, "应有结构"
    tables = [s for s in structures if s["type"] == "table"]
    assert len(tables) > 0, "P5 应有表格"
    assert tables[0]["table_rows"] == 14, f"P5 表格应为 14 行, 实际 {tables[0]['table_rows']}"
    print("✅ P5 结构: 17 shapes, 1 表格 14x5")


def test_find_citation_marks_v2():
    """语义驱动引文标号 — 只从表格方案/药物列 + 标题提取"""
    marks = find_citation_marks_v2(PPT_PATH, 5)
    nums = sorted(marks.keys())
    expected = list(range(1, 19))  # 1-18
    assert nums == expected, f"预期 {expected}, 实际 {nums}"
    print(f"✅ v2 标号: {len(nums)} 个, {nums[0]}-{nums[-1]}")


def test_mark_1_title():
    """标号 1: 标题横幅"""
    ctx = get_ppt_mark_context(PPT_PATH, 5, 1)
    assert ctx["found"]
    assert "uHCC" in ctx.get("context", "")
    print("✅ 标号 1 (标题横幅)")


def test_mark_4_supplementary():
    """标号 4: 多引用场景 — 索拉非尼3,4"""
    ctx = get_ppt_mark_context(PPT_PATH, 5, 4)
    assert ctx["found"]
    assert "索拉非尼" in ctx.get("context", "")
    print("✅ 标号 4 (多引用 索拉非尼3,4)")


def test_mark_17_multi():
    """标号 17: 多引用 — 雷管方案17,18"""
    ctx = get_ppt_mark_context(PPT_PATH, 5, 17)
    assert ctx["found"]
    assert "雷管" in ctx.get("context", "")
    print("✅ 标号 17 (多引用 雷管方案17,18)")


def test_build_ppt_vision_report():
    """PPT 视觉理解报告"""
    report = build_ppt_vision_report(PPT_PATH, 5, list(range(1, 19)))
    assert report["slide_num"] == 5
    assert report["title_text"]  # 标题
    assert len(report["tables"]) > 0
    assert len(report["citation_marks"]) == 18, f"预期 18, 实际 {len(report['citation_marks'])}"
    assert len(report["missing_marks"]) == 0, f"missing: {report['missing_marks']}"
    print(f"✅ 视觉报告: 18/18 matched, {len(report['tables'])} 表格")


def test_verify_alignment():
    """Step 2: verify_highlight_alignment — PDF highlight vs PPT 对齐"""
    ppt_text = "奥沙利铂+5-FU+亚叶酸钙2 随访7个月 mOS 6.47月"
    data_points = extract_ppt_data_points(ppt_text)
    print(f"  数据点: {data_points[:5]}")

    result = verify_highlight_alignment(
        pdf_path=P41_MAIN,
        highlight_image_path="/tmp/dummy.jpg",
        ppt_citation_context={"context": ppt_text},
        data_points=data_points,
    )
    assert "aligned" in result
    assert "score" in result
    assert "matches" in result
    assert "issues" in result
    print(f"✅ 对齐: score={result['score']:.2f}, aligned={result['aligned']}, "
          f"found={result['n_found']}/{result['n_total']}")


def test_ppt_data_points_vs_pdf():
    """信息要素推理: PPT 数据点 vs PDF 全文"""
    ppt_text = (
        "奥沙利铂+5-FU+亚叶酸钙 随访7个月 mOS 6.47月 "
        "BCLC B C 87% 34.5% HCC HBV AFP ALBI"
    )
    pts = extract_ppt_data_points(ppt_text)

    doc = parse_pdf_with_docling(P41_MAIN)
    matches = find_all_ppt_data_points(doc, pts)

    found_pts = [k for k, v in matches.items() if v]
    print(f"  总数据点 {len(pts)}, 找到 {len(found_pts)}")
    assert len(found_pts) >= 5, "至少应找到关键数据点"
    print("✅ 信息要素推理: PPT → PDF")


# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        test_extract_p5_structure,
        test_find_citation_marks_v2,
        test_mark_1_title,
        test_mark_4_supplementary,
        test_mark_17_multi,
        test_build_ppt_vision_report,
        test_verify_alignment,
        test_ppt_data_points_vs_pdf,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"❌ {t.__name__}: {e}")
    print(f"\n{'='*50}")
    print(f"结果: {passed}/{len(tests)} 通过")