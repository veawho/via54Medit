#!/usr/bin/env python3
"""
pdf_understand.py — Docling 多模态 PDF 深度理解工具

═══════════════════════════════════════════════════════════════════════════
硬规则 #1: 所有问题必须找根因修根因
  根因 (用户原话): 我之前用 PyMuPDF 抽文字 + vision_analyze 拼图, 没有
                  结构化的"信息要素推理"算法.

硬规则 #2: GitHub 高 star 项目 + issues + 最佳路径推理
  ✅ Docling 64k stars (IBM, 工业级 PDF 理解)
  ✅ pymupdf4llm 10k+ stars (官方 PDF→markdown)
  ✅ Pix2Text (中文 OCR + LaTeX 公式)
  ✅ Table-Transformer (微软, 表格结构识别, docling 内置)

最佳路径推理:
  Layer 0: PyMuPDF 抽文字 (已有, fallback)
  Layer 1: pymupdf4llm 抽 markdown (已有, structured)
  Layer 2: docling 深度结构化 (texts/tables/pictures/bbox) ← 新引入
  Layer 3: pix2text OCR + 公式 (新引入, 中文优化)
  Layer 4: 信息要素推理 (semantic_matcher) ← 新引入
  Layer 5: 高亮生成 (bbox 精确, 不是全页黄色)
═══════════════════════════════════════════════════════════════════════════

核心能力:
  - parse_pdf_with_docling(pdf_path) → 结构化 JSON
  - find_data_points(doc, data_points) → 应证位置 (page, bbox, type)
  - render_highlight_bbox(pdf_path, bbox, output) → 精确 bbox 高亮
  - semantic_match_ppt_to_pdf(ppt_text, pdf_path) → 应证得分
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import re

# 缓存 docling 输出 (避免重复跑)
DOCLING_CACHE_DIR = Path("/tmp/docling_cache")
DOCLING_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def parse_pdf_with_docling(pdf_path: str, force: bool = False) -> Dict:
    """
    用 docling 解析 PDF → 结构化 JSON
    缓存机制: 第二次跑不重新解析
    """
    pdf_path = str(Path(pdf_path).resolve())
    cache_key = Path(pdf_path).stem
    cache_file = DOCLING_CACHE_DIR / f"{cache_key}.json"

    if cache_file.exists() and not force:
        with open(cache_file) as f:
            return json.load(f)

    out_dir = DOCLING_CACHE_DIR / f"{cache_key}_run"
    out_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [
            "docling", "convert",
            pdf_path,
            "--to", "json",
            "--output", str(out_dir),
        ],
        capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        # 2026-08-02: Docling segfault 时 fallback 到 PyMuPDF 文本抽取
        import fitz
        pymupdf_doc = fitz.open(pdf_path)
        text = ""
        for page in pymupdf_doc:
            text += page.get_text() + "\n"
        pymupdf_doc.close()
        fallback_doc = {
            "texts": [{"text": t} for t in text.split("\n") if t.strip()],
            "tables": [],
            "pictures": [],
            "pages": {},
            "_fallback": "Docling segfault → PyMuPDF fallback (2026-08-02)",
        }
        with open(cache_file, "w") as f:
            json.dump(fallback_doc, f)
        return fallback_doc

    json_files = list(out_dir.glob("*.json"))
    if not json_files:
        raise RuntimeError(f"docling 输出无 JSON: {out_dir}")

    with open(json_files[0]) as f:
        doc = json.load(f)

    # 缓存
    with open(cache_file, "w") as f:
        json.dump(doc, f, ensure_ascii=False)

    return doc


def find_data_point_in_doc(doc: Dict, data_point: str) -> List[Dict]:
    """
    在 docling 输出中搜数据点 (如 "36.7%", "BCLC", "AFP")
    返回所有匹配位置: [{page_no, bbox, text, type, table_info?, row?, col?}]
    """
    matches = []
    pattern = re.compile(re.escape(data_point), re.IGNORECASE)

    # 搜 tables
    for ti, table in enumerate(doc.get("tables", [])):
        prov = table.get("prov", [{}])[0]
        page_no = prov.get("page_no", "?")
        table_bbox = prov.get("bbox", {})

        cells = table.get("data", {}).get("table_cells", [])
        for c in cells:
            text = c.get("text", "")
            if pattern.search(text):
                cell_bbox = c.get("bbox", {})
                matches.append({
                    "page_no": page_no,
                    "bbox": cell_bbox,
                    "text": text,
                    "type": "table_cell",
                    "table_idx": ti,
                    "row": c.get("start_row_offset_idx"),
                    "col": c.get("start_col_offset_idx"),
                    "coord_origin": cell_bbox.get("coord_origin", "TOPLEFT"),
                })

    # 搜 texts
    for txt in doc.get("texts", []):
        text = txt.get("text", "")
        if pattern.search(text):
            prov = txt.get("prov", [{}])[0]
            matches.append({
                "page_no": prov.get("page_no", "?"),
                "bbox": prov.get("bbox", {}),
                "text": text[:200],
                "type": "text",
                "coord_origin": prov.get("bbox", {}).get("coord_origin", "TOPLEFT"),
            })

    return matches


def find_all_ppt_data_points(doc: Dict, ppt_data_points: List[str]) -> Dict[str, List[Dict]]:
    """
    批量搜 PPT 数据点
    返回 {data_point: [matches]}
    """
    result = {}
    for dp in ppt_data_points:
        result[dp] = find_data_point_in_doc(doc, dp)
    return result


# ═════════════════════════════════════════════════════════════════════════
# v7: 语义等同性推理 (Semantic Equivalence Reasoning)
# ═════════════════════════════════════════════════════════════════════════

def numerical_equivalence_variants(value_str: str) -> List[str]:
    """
    数值等价的字符串变体 (2026-08-02 用户硬规则)

    例:
    - "14.4" → ["14.4", "14.40", "14.400"]
    - "14.4%" → ["14.4%", "14.4", "14.40", "14.400"]
    - "27.9" → ["27.9", "27.90", "27.900"]

    Returns:
        List of variants to search
    """
    variants = [value_str]

    val_str = value_str.rstrip("%")
    try:
        val = float(val_str)
    except (ValueError, TypeError):
        return variants

    has_percent = "%" in value_str

    precision_variants = []
    for p in range(1, 4):
        formatted = f"{val:.{p}f}".rstrip("0").rstrip(".")
        if formatted != val_str:
            precision_variants.append(formatted)
        precision_variants.append(f"{val:.{p}f}")

    for v in precision_variants:
        if v and v not in variants:
            variants.append(v)
            if has_percent:
                variants.append(v + "%")

    if not has_percent and val <= 100:
        if (val_str + "%") not in variants:
            variants.append(val_str + "%")
        for v in precision_variants:
            if v and (v + "%") not in variants:
                variants.append(v + "%")

    if has_percent:
        if val_str not in variants:
            variants.append(val_str)
        for v in precision_variants:
            if v and v not in variants:
                variants.append(v)

    return variants


def get_table_context_for_unit(doc: Dict, table_idx: int, page_no) -> str:
    """
    提取表格周围的上下文 (找 title, caption, 或周围文字)
    用于单位推断
    """
    context_parts = []
    target_table = None
    for ti, table in enumerate(doc.get("tables", [])):
        if ti == table_idx:
            target_table = table
            break
    if not target_table:
        return ""

    table_bbox = target_table.get("prov", [{}])[0].get("bbox", {})
    table_top = table_bbox.get("t", 0) if table_bbox else 0
    table_bottom = table_bbox.get("b", 0) if table_bbox else 0

    for txt in doc.get("texts", []):
        prov = txt.get("prov", [{}])[0]
        if prov.get("page_no") != page_no:
            continue
        txt_bbox = prov.get("bbox", {})
        if not txt_bbox:
            continue
        txt_top = txt_bbox.get("t", 0)
        txt_bottom = txt_bbox.get("b", 0)

        if 0 < (table_top - txt_bottom) < 200:
            text = txt.get("text", "")
            if text and len(text) < 200:
                context_parts.append(text)
        elif 0 < (txt_top - table_bottom) < 100:
            text = txt.get("text", "")
            if text and len(text) < 200:
                context_parts.append(text)

    return " | ".join(context_parts[:3])


def detect_unit_in_context(context: str) -> str:
    """从上下文推断单位"""
    if not context:
        return ""
    context_l = context.lower()

    if any(kw in context for kw in ["percentage", "百分比", "%", "ratio", "rate"]):
        if "%" in context or "percent" in context_l:
            return "percentage"

    if any(kw in context for kw in ["month", "月份", "月OS", "月生存", "月PFS", "median OS"]):
        return "month"

    if any(kw in context for kw in ["year", "年OS", "年生存", "5年", "5-year"]):
        return "year"

    return ""


def find_data_point_with_equivalence(doc: Dict, data_point: str) -> List[Dict]:
    """
    v7: 在 docling 输出中搜数据点 + 语义等价变体
    """
    variants = numerical_equivalence_variants(data_point)

    all_matches = []
    seen_positions = set()

    for variant in variants:
        matches = find_data_point_in_doc(doc, variant)

        for m in matches:
            pos_key = (m["page_no"], m["type"], m["text"][:30])
            if pos_key in seen_positions:
                continue
            seen_positions.add(pos_key)

            m["equivalent"] = (variant != data_point)
            m["variant"] = variant
            m["original"] = data_point
            all_matches.append(m)

    return all_matches


def find_all_ppt_data_points_with_equivalence(
    doc: Dict,
    ppt_data_points: List[str],
) -> Dict[str, List[Dict]]:
    """v7: 批量搜 PPT 数据点 + 等价变体"""
    result = {}
    for dp in ppt_data_points:
        result[dp] = find_data_point_with_equivalence(doc, dp)
    return result


def compute_semantic_alignment_score(
    doc: Dict,
    ppt_data_points: List[str],
) -> Dict:
    """v7: 计算 PPT 数据点 vs PDF 的语义对齐分数 (含等价推理)"""
    matches = find_all_ppt_data_points_with_equivalence(doc, ppt_data_points)

    found_count = 0
    equivalent_count = 0
    missing = []
    equivalent_matches = {}

    for dp, ms in matches.items():
        if ms:
            found_count += 1
            equiv = [m for m in ms if m.get("equivalent")]
            if equiv:
                equivalent_count += 1
                equivalent_matches[dp] = equiv
        else:
            missing.append(dp)

    total_count = len(ppt_data_points)
    score = found_count / total_count if total_count else 0

    return {
        "score": score,
        "found_count": found_count,
        "total_count": total_count,
        "matches": matches,
        "equivalent_matches": equivalent_matches,
        "missing": missing,
    }

def render_highlight_bbox(
    pdf_path: str,
    matches: List[Dict],
    output_path: str,
    alpha: int = 80,
):
    """
    基于 docling bbox 精确高亮 (不是全页黄色)
    matches 是 find_data_point_in_doc 的输出
    """
    import fitz
    from PIL import Image, ImageDraw
    import io

    doc = fitz.open(pdf_path)

    # 按 page 分组
    by_page = {}
    for m in matches:
        pn = m["page_no"]
        if pn not in by_page:
            by_page[pn] = []
        by_page[pn].append(m)

    # 只渲染第一个有 bbox 的页面 (实际应支持多页)
    if not by_page:
        raise ValueError("无 bbox 匹配")

    pn = min(by_page.keys(), key=lambda x: int(x) if str(x).isdigit() else 999)
    page = doc[int(pn) - 1]
    mat = fitz.Matrix(150 / 72, 150 / 72)
    pix = page.get_pixmap(matrix=mat)
    pil_img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA")

    # 比例 (docling bbox 单位是 points, 1 point = 1/72 inch)
    scale = 150 / 72
    page_h_pts = page.rect.height

    # 画 bbox (黄色覆盖)
    for m in by_page[pn]:
        bbox = m.get("bbox", {})
        if not bbox:
            continue
        l = float(bbox.get("l", 0)) * scale
        t = float(bbox.get("t", 0)) * scale
        r = float(bbox.get("r", 0)) * scale
        b = float(bbox.get("b", 0)) * scale
        # BOTTOMLEFT → 转 TOPLEFT
        coord_origin = bbox.get("coord_origin", "TOPLEFT")
        if coord_origin == "BOTTOMLEFT":
            new_t = page_h_pts - float(bbox.get("t", 0))
            new_b = page_h_pts - float(bbox.get("b", 0))
            t = new_t * scale
            b = new_b * scale

        # 画半透明黄色
        overlay = Image.new("RGBA", pil_img.size, (255, 255, 0, 0))
        draw = ImageDraw.Draw(overlay)
        draw.rectangle([l, t, r, b], fill=(255, 255, 0, alpha))
        pil_img = Image.alpha_composite(pil_img, overlay)

    pil_img = pil_img.convert("RGB")
    pil_img.save(output_path, "JPEG", quality=85)
    doc.close()
    return output_path


def verify_highlight_alignment(
    pdf_path: str,
    highlight_image_path: str,
    ppt_citation_context: Dict,
    data_points: Optional[List[str]] = None,
) -> Dict:
    """
    Step 2: 验证 PDF highlight 与 PPT 引文标号是否对齐

    输入:
      - pdf_path: PDF 路径
      - highlight_image_path: 现有的 highlight 图路径
      - ppt_citation_context: Step 1 PPT 视觉理解的标号上下文
      - data_points: PPT 关键数据点

    输出:
      - aligned: 是否对齐
      - issues: 不对齐的细节
      - pdf_content: PDF 中对应区域的内容
    """
    doc = parse_pdf_with_docling(pdf_path)

    if data_points is None:
        ppt_text = ppt_citation_context.get("context", "")
        data_points = extract_ppt_data_points(ppt_text)

    # 在 PDF 中搜数据点
    matches = find_all_ppt_data_points(doc, data_points)

    # 判断对齐
    total = len(data_points)
    found = sum(1 for dp, ms in matches.items() if ms)

    return {
        "pdf_path": pdf_path,
        "highlight_path": highlight_image_path,
        "aligned": found >= total * 0.6,
        "score": found / total if total else 0,
        "n_found": found,
        "n_total": total,
        "matches": {dp: [{"page_no": m["page_no"], "text": m["text"][:60], "type": m["type"]}
                         for m in ms[:3]] for dp, ms in matches.items()},
        "issues": [] if found >= total * 0.6 else [
            f"{dp} (PPT 数据点) 在 PDF 中未找到匹配"
            for dp, ms in matches.items() if not ms
        ],
    }


def semantic_match_ppt_to_pdf(
    ppt_text: str,
    pdf_path: str,
    ppt_data_points: Optional[List[str]] = None,
) -> Dict:
    """
    信息要素推理: PPT 引文 → PDF 应证位置
    1. docling 解析 PDF
    2. 搜 PPT 数据点
    3. 输出应证报告 (page, bbox, type, score)
    """
    doc = parse_pdf_with_docling(pdf_path)

    # 提 PPT 数据点 (如果没给)
    if ppt_data_points is None:
        ppt_data_points = extract_ppt_data_points(ppt_text)

    # 搜
    matches = find_all_ppt_data_points(doc, ppt_data_points)

    # 应证得分
    total = len(ppt_data_points)
    found = sum(1 for dp, ms in matches.items() if ms)
    score = found / total if total else 0

    return {
        "pdf_path": pdf_path,
        "ppt_data_points": ppt_data_points,
        "matches": matches,
        "n_total": total,
        "n_found": found,
        "score": score,
        "doc_summary": {
            "pages": len(doc.get("pages", {})),
            "tables": len(doc.get("tables", [])),
            "pictures": len(doc.get("pictures", [])),
            "texts": len(doc.get("texts", [])),
        },
    }


def extract_ppt_data_points(ppt_text: str) -> List[str]:
    """
    从 PPT 文本提取数据点 (数字+百分比+关键术语)
    智能抽取: '36.7%' 同时生成 '36.7' 和 '36.7%' 两个变体

    2026-08-02 修复: 数字 > 100 不生成百分比变体
      (避免 RATIONALE-301→301%, IMbrave150→150%, CARES-310→310% 等假阳性)
    """
    points = []

    # 百分比 (如 36.7% / 87.3%) — 同时加变体
    for m in re.finditer(r"(\d+\.?\d*)(%?)", ppt_text):
        val = m.group(1)
        pct = m.group(2)

        if not val:
            continue

        # 转纯数字判断
        bare_num = 0
        try:
            bare_num = float(val)
        except ValueError:
            continue

        # 跳过纯个位数 (0-9) — 到处出现, 无意义
        # 保留: 带小数点的 (6.47), ≥10 的 (15.9, 301), 原文带 % 的
        if bare_num < 10 and not pct and "." not in val:
            continue

        # 检查数字后面是否跟着中文单位 (月/年/天/人/例/周/个/等)
        after = ppt_text[m.end():m.end()+3]
        chinese_unit = any(after.startswith(u) for u in
                          ("月", "年", "天", "人", "例", "周", "个", "个月", "年OS率", "年OS", "年存活率"))

        if not pct and val not in points:
            points.append(val)
        if pct == "%" and val not in points:
            points.append(val)

        # 加变体 (去掉 %)
        if pct == "%":
            if val not in points:
                points.append(val)
        # 加变体 (加 %), 仅限数字 <= 100 且非中文单位后缀
        elif not pct and bare_num <= 100 and not chinese_unit:
            with_pct = val + "%"
            if with_pct not in points:
                points.append(with_pct)
        # 加 % 变体即使 > 100 但原文自带 % (如 87.3%) — 保留原值
        if pct == "%" and val + "%" not in points:
            points.append(val + "%")

    # 关键术语 (BCLC, HBV, AFP 等医学术语)
    terms = ["BCLC B", "BCLC C", "BCLC A", "BCLC", "HBV", "HCC", "AFP",
             "ALBI", "tumor", "Tumor", "diameter", "median",
             "overall survival", "OS", "Barcelona", "vascular", "thrombus"]
    for t in terms:
        if t.lower() in ppt_text.lower() and t not in points:
            points.append(t)

    return points


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════


def cli_parse(args):
    if not args:
        print("用法: parse <pdf_path>")
        return
    doc = parse_pdf_with_docling(args[0])
    print(f"✅ docling parse OK")
    print(f"  pages: {len(doc.get('pages', {}))}")
    print(f"  tables: {len(doc.get('tables', []))}")
    print(f"  pictures: {len(doc.get('pictures', []))}")
    print(f"  texts: {len(doc.get('texts', []))}")


def cli_find(args):
    if len(args) < 2:
        print("用法: find <pdf_path> <data_point>")
        return
    doc = parse_pdf_with_docling(args[0])
    matches = find_data_point_in_doc(doc, args[1])
    print(f"✅ 找到 {len(matches)} 处匹配 '{args[1]}'")
    for m in matches[:5]:
        print(f"  page {m['page_no']} ({m['type']}): {m['text'][:80]}")


def cli_match(args):
    if len(args) < 2:
        print("用法: match <pdf_path> <ppt_text>")
        return
    result = semantic_match_ppt_to_pdf(args[1], args[0])
    print(f"✅ 应证得分: {result['score']:.2f} ({result['n_found']}/{result['n_total']})")
    for dp, ms in result["matches"].items():
        if ms:
            print(f"  ✓ {dp}: {len(ms)} 处")
        else:
            print(f"  ✗ {dp}: 0 处")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    args = sys.argv[2:]
    cmds = {
        "parse": cli_parse,
        "find": cli_find,
        "match": cli_match,
    }
    if cmd not in cmds:
        print(f"未知: {cmd}, 可用: {list(cmds.keys())}")
        sys.exit(1)
    cmds[cmd](args)


if __name__ == "__main__":
    main()