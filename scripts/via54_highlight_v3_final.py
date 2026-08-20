#!/usr/bin/env python3
"""
via54_highlight_v3_final.py — 集成 9 条铁律 + v3 FINAL rect 模式

完全符合 via54Medit ARCHITECTURE.md §23.2 的 9 条视觉铁律:

  规则 1: 视觉与 PPT 正文匹配 (整句匹配, 不关键词)
  规则 2: 禁止 highlight 作者
  规则 3: 禁止 highlight 文献标题 (字号 >= 14pt)
  规则 4: 禁止 highlight 期刊名/出版商
  规则 5: 禁止 highlight Abstract 标题
  规则 6: 禁止关键词匹配 (用整句/短语)
  规则 7: 不能串行 (每行 1 rect, 不延伸)
  规则 8: 不能遮盖文字 (rect 收窄 -0.6pt)
  规则 9: 不能偏移 (严格按 bbox)

集成到 via54Medit 仓库:
  scripts/via54_highlight_v3_final.py
"""
import os
import re
import sys
from typing import Dict, List

# 添加 hl_v3_final 路径
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "hl_v3_final"))

import fitz

# === 9 条铁律常量 ===

# 规则 2: 作者模式
AUTHOR_PATTERNS = [
    r"^[\w\s,\.]+(?:et al\.?|\*)?\s*[\d\*,\s]*(?:\([^)]+\))?$",
    r"^[A-Z][a-z]+\s+[A-Z][a-z]?[\d\*,\s]*$",
    r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s*[\d\*,]+",
]

# 规则 4: 出版商/期刊名
PUBLISHER_PATTERNS = [
    r"Frontiers in \w+", r"BMC \w+", r"Mayo Clinic Proceedings",
    r"Nature", r"Bone Marrow Transplantation", r"Blood Advances",
    r"Lancet", r"Cell", r"NEJM", r"JAMA",
    r"doi:?\s*10\.\d{4}/", r"doi\.org",
    r"Clin \w+", r"Transplant Cell Ther",
    r"Annals? of \w+", r"Journal of \w+",
    r"Br J \w+", r"Eur \w+", r"中华\w+",
]

# 规则 5: Abstract 标题
ABSTRACT_HEADERS = {
    "Abstract", "ABSTRACT", "Background", "BACKGROUND",
    "Methods", "METHODS", "Introduction", "INTRODUCTION",
    "Results", "RESULTS", "Conclusion", "CONCLUSION",
    "Discussion", "DISCUSSION", "Materials and Methods",
    "Aim", "Objective", "Case Report",
}

# 规则 3: 标题字号阈值
TITLE_FONT_SIZE = 14.0
METADATA_ZONE_RATIO = 0.40


def get_max_font_size(page, rect):
    """获取 rect 覆盖的字符最大字号"""
    sizes = []
    try:
        d = page.get_text("dict")
        for block in d.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    span_bbox = fitz.Rect(*span.get("bbox", [0, 0, 0, 0]))
                    if rect.intersects(span_bbox):
                        sizes.append(span.get("size", 0))
    except Exception:
        pass
    return max(sizes) if sizes else 0


def is_publisher_text(text):
    """规则 4: 期刊名/出版商"""
    text_stripped = text.strip()
    if not text_stripped:
        return False
    for p in PUBLISHER_PATTERNS:
        if re.search(p, text_stripped, re.IGNORECASE):
            return True
    return False


def is_author_text(text):
    """规则 2: 作者名段"""
    text_stripped = text.strip()
    if not text_stripped or len(text_stripped) < 3:
        return False
    for p in AUTHOR_PATTERNS:
        if re.match(p, text_stripped):
            if re.search(r"[A-Z][a-z]+", text_stripped):
                return True
    return False


def is_abstract_header(text):
    """规则 5: Abstract 标题"""
    text_stripped = text.strip().rstrip(":")
    if text_stripped in ABSTRACT_HEADERS:
        return True
    for h in ABSTRACT_HEADERS:
        if text_stripped.startswith(h) and len(text_stripped) < len(h) + 5:
            return True
    return False


def is_title_text(page, rect, rect_text):
    """规则 3: 文献标题"""
    if len(rect_text.strip()) < 10:
        return False
    if rect.y0 > page.rect.height * METADATA_ZONE_RATIO:
        return False
    max_size = get_max_font_size(page, rect)
    if max_size < TITLE_FONT_SIZE:
        return False
    return True


def is_metadata_rect(page, rect, rect_text):
    """综合检测: rect 是否在元数据区 (违规)"""
    if is_author_text(rect_text):
        return "RULE_2_AUTHOR"
    if is_title_text(page, rect, rect_text):
        return "RULE_3_TITLE"
    if is_publisher_text(rect_text):
        return "RULE_4_PUBLISHER"
    if is_abstract_header(rect_text):
        return "RULE_5_ABSTRACT_HEADER"
    return None


def highlight_with_v3_final(
    pdf_in,
    pdf_out,
    sentences,
    apply_9_rules=True,
):
    """
    用 v3 FINAL rect 模式 + 9 条铁律 跑高亮

    Args:
        pdf_in: 输入 PDF
        pdf_out: 输出 PDF
        sentences: {page_idx_0based: [句子1, 句子2, ...]}
        apply_9_rules: True 则删除违规 highlight
    """
    from hl_lib import highlight_sentences

    result = {
        "ok": False,
        "total_sentences": sum(len(v) for v in sentences.values()),
        "highlights_ok": 0,
        "highlights_removed": 0,
        "violations": [],
    }

    if not os.path.exists(pdf_in):
        result["error"] = f"PDF not found: {pdf_in}"
        return result

    # Step 1: v3 FINAL rect 高亮
    try:
        report = highlight_sentences(pdf_in, pdf_out, sentences, verbose=False)
        result["hl_lib_report"] = report
        result["highlights_ok"] = sum(1 for r in report if r[2].startswith("OK"))
    except Exception as e:
        result["error"] = f"hl_lib error: {e}"
        return result

    if not apply_9_rules:
        result["ok"] = True
        return result

    # Step 2: 应用 9 条铁律, 删除违规
    doc = fitz.open(pdf_out)
    for pi in range(len(doc)):
        page = doc[pi]
        annots = list(page.annots() or [])
        for annot in annots:
            if not annot.rect:
                continue
            rect = annot.rect
            try:
                text = page.get_textbox(rect).strip()
            except Exception:
                continue

            violation = is_metadata_rect(page, rect, text)
            if violation:
                try:
                    page.delete_annot(annot)
                    result["highlights_removed"] += 1
                    result["violations"].append((pi + 1, violation, text[:60]))
                except Exception:
                    pass

    # Step 3: 保存
    tmp_path = pdf_out + ".tmp"
    doc.save(tmp_path, garbage=4, deflate=True)
    doc.close()
    import shutil
    shutil.move(tmp_path, pdf_out)

    result["ok"] = True
    return result


if __name__ == "__main__":
    import argparse, json
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_in")
    parser.add_argument("pdf_out")
    parser.add_argument("--sentences-json", required=True)
    parser.add_argument("--no-rules", action="store_true")
    args = parser.parse_args()

    with open(args.sentences_json) as f:
        sentences = {int(k): v for k, v in json.load(f).items()}

    result = highlight_with_v3_final(
        args.pdf_in, args.pdf_out, sentences,
        apply_9_rules=not args.no_rules,
    )
    print(f"Total: {result['total_sentences']}")
    print(f"OK: {result['highlights_ok']}")
    print(f"Removed: {result['highlights_removed']}")
    for v in result.get("violations", [])[:10]:
        print(f"  p{v[0]}: {v[1]} - '{v[2]}'")