#!/usr/bin/env python3
"""
rerun_tma_highlight_v3_final.py — TMA 专属 v3 FINAL 高亮脚本

完全替代 rerun_tma_highlight_v104.py, 使用 v3 FINAL rect 模式 + 9 条铁律

输入:  TMA_文献整理/_2_pdfs/Pn-x_main.pdf
      TMA_文献整理/_citation_table/tma_citation_table.csv
      TMA_文献整理/_3_highlight_vision/_highlight_plans.json
输出:  TMA_文献整理/_3_highlight_v3/Pn-x_highlight.pdf
      TMA_文献整理/_3_highlight_v3/_summary.csv

v3 FINAL 优势 vs v10.4:
  - 整句匹配, 不关键词
  - opacity 0.45 半透明黄色
  - 每行精确 rect, 不延伸
  - 9 条铁律自动应用 (删除标题/作者/期刊高亮)
"""
import os, sys, csv, re, json, shutil, glob
from pathlib import Path
from typing import Dict, List
import warnings
warnings.filterwarnings('ignore')

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "hl_v3_final"))

import fitz
fitz.TOOLS.mupdf_display_warnings(False)

# 集成 v3 FINAL + 9 条铁律
from via54_highlight_v3_final import (
    highlight_with_v3_final,
    is_metadata_rect,
    get_max_font_size,
    is_publisher_text,
    is_author_text,
    is_abstract_header,
    is_title_text,
)


# === 路径 ===
TMA_ROOT = "/Users/david/Desktop/TMA_文献整理"
PDF_DIR = os.path.join(TMA_ROOT, "_2_pdfs")
HIGHLIGHT_DIR = os.path.join(TMA_ROOT, "_3_highlight_v3")
CSV_PATH = os.path.join(TMA_ROOT, "_citation_table/tma_citation_table.csv")
VISION_PLANS_PATH = os.path.join(TMA_ROOT, "_3_highlight_vision/_highlight_plans.json")


def _read_csv_d_content() -> Dict[str, str]:
    """读 CSV D 列 (PPT 引文完整字段) 用于提取整句"""
    if not os.path.isfile(CSV_PATH):
        return {}
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    result = {}
    for r in rows:
        a, b = r.get('A_slide', '').strip(), r.get('B_mark', '').strip()
        if not a or not b:
            continue
        pn = f"P{a}-{b}"
        result[pn] = r.get('D_ppt_content', '') or ''
    return result


def _read_vision_plans() -> Dict[str, List[str]]:
    """读 vision plan 的 target_text (PPT 内容), 用于找 PDF 整句"""
    if not os.path.isfile(VISION_PLANS_PATH):
        return {}
    with open(VISION_PLANS_PATH) as f:
        plans = json.load(f).get("plans", [])
    result = {}
    for p in plans:
        pn = p.get("pn_x")
        if not pn:
            continue
        # 用 target_text 作为 PDF 搜索目标
        target = p.get("target_text", "")
        # 拆分成短句 (用句号/分号分)
        sentences = re.split(r'[。.!?;；]\s*', target)
        result[pn] = [s.strip() for s in sentences if len(s.strip()) > 15][:8]
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="处理前 N 个 PDF")
    parser.add_argument("--out-dir", default=HIGHLIGHT_DIR)
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    d_content = _read_csv_d_content()
    vision_plans = _read_vision_plans()
    print(f"CSV D 列: {len(d_content)} Pn-x")
    print(f"Vision plans: {len(vision_plans)} Pn-x")

    pdfs = sorted(glob.glob(os.path.join(PDF_DIR, "P*-*_main.pdf")))
    if args.limit:
        pdfs = pdfs[:args.limit]
    print(f"待处理 PDF: {len(pdfs)}")

    summary = []
    success, fail = 0, 0

    for pdf_in in pdfs:
        m = re.match(r'.+/P(\d+)-(\d+)_main\.pdf', pdf_in)
        if not m:
            continue
        pn = f"P{m.group(1)}-{m.group(2)}"

        # 准备句子: 优先用 vision plan 的 target_text, fallback D 列
        sentences_list = vision_plans.get(pn, [])
        if not sentences_list and pn in d_content:
            d_text = d_content[pn]
            sentences_list = re.split(r'[。.!?;；]\s*', d_text)
            sentences_list = [s.strip() for s in sentences_list if len(s.strip()) > 15][:8]

        # 转换为 sentences_map: {page_idx: [sentences]}
        # v3 FINAL 需要按页分配句子
        # 简化: 把所有句子放到 page 0 (hl_lib 会在所有页搜索)
        sentences_map = {}
        if sentences_list:
            sentences_map[0] = sentences_list

        out_pdf = os.path.join(args.out_dir, f"{pn}_highlight.pdf")

        try:
            result = highlight_with_v3_final(
                pdf_in, out_pdf, sentences_map,
                apply_9_rules=True,
            )
            mark = "✓" if result["ok"] else "❌"
            print(f"  {mark} {pn}: ok={result['highlights_ok']}/{result['total_sentences']} removed={result['highlights_removed']}")
            summary.append({
                "pn_x": pn,
                "sentences": result["total_sentences"],
                "ok": result["highlights_ok"],
                "removed": result["highlights_removed"],
                "violations": len(result.get("violations", [])),
            })
            if result["ok"]:
                success += 1
            else:
                fail += 1
        except Exception as e:
            print(f"  ❌ {pn}: ERROR {e}")
            fail += 1

    if summary:
        summary_csv = os.path.join(args.out_dir, "_summary.csv")
        with open(summary_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
            writer.writeheader()
            writer.writerows(summary)
    print(f"\n=== 完成 ===")
    print(f"  成功: {success}/{len(summary)}")
    print(f"  失败: {fail}")
    print(f"  Output: {args.out_dir}")


if __name__ == "__main__":
    main()