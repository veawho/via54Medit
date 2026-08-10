#!/usr/bin/env python3
"""
rerun_leidafang_highlight_v10.py — 雷管方案 step4 v9.7 → v10.1 全量迁移

把 step3 里 160 个 Pn-x 的 main.pdf 用 v10.1 重做 highlight:
  - line 模式 (6 步规则要求)
  - 跳 header/author/footer
  - 走内容流画黄, 颜色持久

输入:  雷管方案/step3_pdf下载_160目录/Pn-x/*main*.pdf
       雷管方案/step2_标注分析/PPT_citations_8col_aligned.csv (D 列作分析参考)
输出:  雷管方案/step4_highlight_v10/Pn-x/*main*.pdf (新)
       雷管方案/step4_highlight_v10/Pn-x/page_NNN.jpg (新)
       雷管方案/step4_highlight_v10/_rerun_summary.csv (对比)

用法:  python3.11 rerun_leidafang_highlight_v10.py [--limit 5] [--mode line]
"""
import os, sys, csv, re, json, shutil, glob
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from via54_highlight_fix_v10 import (
    process_pn_x,
    extract_keywords_from_d,
    DEFAULT_HIGHLIGHT_MODE,
)
from PIL import Image
import numpy as np
import fitz
fitz.TOOLS.mupdf_display_warnings(False)


LEIDA_ROOT = "/Users/david/Desktop/雷管方案_文献整理"
STEP3_DIR = os.path.join(LEIDA_ROOT, "step3_pdf下载_160目录")
STEP4_OLD_DIR = os.path.join(LEIDA_ROOT, "step4_highlight_96目录_合并DOI")
STEP4_NEW_DIR = os.path.join(LEIDA_ROOT, "step4_highlight_v10")
CSV_PATH = os.path.join(LEIDA_ROOT, "step2_标注分析/PPT_citations_8col_aligned.csv")


def _read_csv_kws(csv_path: str) -> Dict[str, List[str]]:
    """
    读雷管方案 12 列 CSV, 返回 {Pn-x: keywords}
    D 列 (D_ppt_visual) 是视觉分析, 包含位置/数据点描述, 适合抽关键词
    """
    if not os.path.isfile(csv_path):
        return {}
    with open(csv_path, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    result = {}
    for r in rows:
        a = r.get('A_slide', '').strip()
        b = r.get('B_mark', '').strip()
        if not a or not b:
            continue
        pn = f"P{a}-{b}"

        c_cit = r.get('C_citation', '') or ''
        d_visual = r.get('D_ppt_visual', '') or ''
        g_pdf = r.get('G_actual_pdf', '') or ''

        kws = extract_keywords_from_d(c_cit, d_visual)
        # D 列是视觉分析 (含 [数据点: ...] [位置: ...]), 抽数据点
        data_points = re.findall(r'(\d+\.?\d*\s*%)', d_visual)
        for dp in data_points[:5]:
            kws.append(dp)
        # 抽 D 列里的中文 2-4 字词
        extra = [w for w in re.findall(r'[\u4e00-\u9fff]{2,4}', d_visual) if len(w) >= 2]
        kws.extend(extra[:8])
        # 抽 D 列里的英文词
        extra_en = re.findall(r'\b[A-Z][a-zA-Z]{3,}\b', d_visual)
        kws.extend(extra_en[:5])

        # 抽 G_actual_pdf 文件名里的关键词 (如 Rimassa_JHepatol_2025_HIMALAYA)
        if g_pdf:
            fname_kws = re.findall(r'[A-Z][a-zA-Z]+|20\d{2}', g_pdf)
            kws.extend(fname_kws[:5])

        kws = list(set(kws))[:15]  # 限制 15 个, 避免噪音
        result[pn] = kws
    return result


def _old_yellow_stats(dir_path: str) -> float:
    """看一个 Pn-x 旧目录里 highlight jpg 的最大黄占比"""
    max_pct = -1.0
    if not os.path.isdir(dir_path):
        return max_pct
    jpgs = [f for f in os.listdir(dir_path) if f.lower().endswith('.jpg') and 'highlight' in f.lower()]
    for j in jpgs[:3]:
        p = os.path.join(dir_path, j)
        try:
            arr = np.array(Image.open(p).convert("RGB"))
            yellow = (arr[:, :, 0] > 200) & (arr[:, :, 1] > 200) & (arr[:, :, 2] < 150)
            pct = yellow.sum() / yellow.size * 100
            max_pct = max(max_pct, pct)
        except Exception:
            pass
    return max_pct


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--mode", default=DEFAULT_HIGHLIGHT_MODE, choices=["line", "fill", "both"])
    parser.add_argument("--out-dir", default=STEP4_NEW_DIR)
    parser.add_argument("--skip-existing", action="store_true", help="跳过已生成的")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    csv_kws = _read_csv_kws(CSV_PATH)
    print(f"CSV 关键词: {len(csv_kws)} Pn-x")

    # 扫描 step3 Pn-x
    pn_x_dirs = sorted([d for d in os.listdir(STEP3_DIR)
                        if os.path.isdir(os.path.join(STEP3_DIR, d)) and d.startswith('P')])
    if args.limit:
        pn_x_dirs = pn_x_dirs[:args.limit]
    print(f"待处理 Pn-x: {len(pn_x_dirs)}")

    summary = []
    success = 0
    fail = 0
    skipped = 0
    for pn in pn_x_dirs:
        pn_path = os.path.join(STEP3_DIR, pn)
        out_pn_dir = os.path.join(args.out_dir, pn)
        out_pdf_marker = os.path.join(out_pn_dir, "_v10_done.marker")

        if args.skip_existing and os.path.isfile(out_pdf_marker):
            skipped += 1
            continue

        # 找 main PDF
        main_pdfs = [f for f in os.listdir(pn_path)
                     if f.lower().endswith('.pdf') and 'main' in f.lower()
                     and 'fallback' not in f.lower() and 'v39' not in f.lower()]
        if not main_pdfs:
            print(f"  ❌ {pn}: no main PDF")
            fail += 1
            continue
        main_pdf = os.path.join(pn_path, main_pdfs[0])

        kws = csv_kws.get(pn, [])
        if not kws:
            # fallback: 从 PDF 文件名抽
            kws = re.findall(r'[A-Z][a-zA-Z]+|20\d{2}', main_pdfs[0])[:5]

        # 输出目录 = Pn-x (nested 跟原 step4 一致)
        os.makedirs(out_pn_dir, exist_ok=True)
        out_pdf = os.path.join(out_pn_dir, main_pdfs[0].replace('.pdf', '_v10.pdf'))
        jpg_dir = out_pn_dir  # jpg 也在同一目录

        try:
            r = process_pn_x(pn, main_pdf, out_pdf, kws, jpg_dir, f"{pn}_page", mode=args.mode)
        except Exception as e:
            print(f"  ❌ {pn}: ERROR {e}")
            fail += 1
            continue

        # 旧版黄占比
        old_pn_dir = os.path.join(STEP4_OLD_DIR, pn)
        old_yellow = _old_yellow_stats(old_pn_dir)

        # 标记完成
        with open(out_pdf_marker, "w") as f:
            f.write("ok")

        mark = "✓" if r["ok"] else "❌"
        summary.append({
            "pn_x": pn,
            "old_yellow_pct": round(old_yellow, 4) if old_yellow >= 0 else None,
            "new_yellow_pct": round(r["yellow_pct_estimate"], 4),
            "delta": round(r["yellow_pct_estimate"] - old_yellow, 4) if old_yellow >= 0 else None,
            "hits": r["total_hits"],
            "matched_terms": len(r["matched_terms"]),
            "skipped_terms": len(r["skipped_terms"]),
            "mode": r.get("mode", "?"),
            "ok": r["ok"],
        })
        success += 1 if r["ok"] else 0
        fail += 0 if r["ok"] else 1

        # 进度
        if (success + fail) % 10 == 0 or not r["ok"]:
            old_str = f"{old_yellow:6.3f}%" if old_yellow >= 0 else "  N/A "
            print(f"  [{success+fail}/{len(pn_x_dirs)}] {mark} {pn}: OLD={old_str} NEW={r['yellow_pct_estimate']:6.3f}%  hits={r['total_hits']:3d}  kws={len(kws)}")

    # 写 summary
    if summary:
        summary_csv = os.path.join(args.out_dir, "_rerun_summary.csv")
        with open(summary_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
            writer.writeheader()
            writer.writerows(summary)
        print(f"\n✓ Summary: {summary_csv}")

    print(f"\n=== 雷管方案 step4 v10.1 迁移完成 ===")
    print(f"  成功: {success}/{len(summary)}")
    print(f"  失败: {fail}")
    print(f"  跳过: {skipped}")


if __name__ == "__main__":
    main()
