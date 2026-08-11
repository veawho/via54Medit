#!/usr/bin/env python3
"""
rerun_tma_highlight_v104.py — TMA 全量 highlight v10.4 (关键词合并版)

v10.3 用 CSV keywords. v10.4 合并:
  - CSV keywords (D 列)
  - Vision plan.keywords (从 _3_highlight_vision/_highlight_plans.json)
  - Vision plan.data_points_boosted
  - Vision plan.target_text 拆出的中文 2-4 字词

v10.4 还自动跳过 header (STRICT_SKIP_HEADER=True).

输入:  TMA_文献整理/_2_pdfs/Pn-x_main.pdf
      TMA_文献整理/_citation_table/tma_citation_table.csv
      TMA_文献整理/_3_highlight_vision/_highlight_plans.json
输出:  TMA_文献整理/_3_highlight_v10_4/Pn-x_highlight.pdf
      TMA_文献整理/_3_highlight_v10_4/_rerun_summary.csv
"""
import os, sys, csv, re, json, shutil, glob
from pathlib import Path
from typing import Dict, List, Optional
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from via54_highlight_fix_v10 import process_pn_x, extract_keywords_from_d, DEFAULT_HIGHLIGHT_MODE
import fitz
fitz.TOOLS.mupdf_display_warnings(False)


TMA_ROOT = "/Users/david/Desktop/TMA_文献整理"
PDF_DIR = os.path.join(TMA_ROOT, "_2_pdfs")
HIGHLIGHT_NEW_DIR = os.path.join(TMA_ROOT, "_3_highlight_v10_4")
CSV_PATH = os.path.join(TMA_ROOT, "_citation_table/tma_citation_table.csv")
VISION_PLANS_PATH = os.path.join(TMA_ROOT, "_3_highlight_vision/_highlight_plans.json")


def _yellow_max_pct(pdf_path: str, max_pages: int = 5) -> float:
    if not os.path.isfile(pdf_path):
        return -1.0
    try:
        doc = fitz.open(pdf_path)
        n = min(max_pages, len(doc))
        max_y = 0.0
        for i in range(n):
            pix = doc[i].get_pixmap(matrix=fitz.Matrix(0.5, 0.5))
            img = __import__('PIL.Image', fromlist=['Image']).frombytes("RGB", (pix.width, pix.height), pix.samples)
            import numpy as np
            arr = np.array(img)
            yellow = ((arr[:,:,0] > 200) & (arr[:,:,1] > 200) & (arr[:,:,2] < 100)).sum()
            total = arr.shape[0] * arr.shape[1]
            pct = yellow / total * 100 if total else 0
            if pct > max_y:
                max_y = pct
        return max_y
    except Exception:
        return -1.0


def _read_csv_kws() -> Dict[str, tuple]:
    """读 CSV keywords, 返回 {pn_x: (citation, ppt_content, kws)}"""
    if not os.path.isfile(CSV_PATH):
        return {}
    with open(CSV_PATH, encoding="utf-8-sig") as f:  # 跳过 BOM
        rows = list(csv.DictReader(f))
    result = {}
    for r in rows:
        a, b = r.get('A_slide', '').strip(), r.get('B_mark', '').strip()
        if not a or not b:
            continue
        pn = f"P{a}-{b}"
        c_cit = r.get('C_citation', '') or ''
        d_ppt = r.get('D_ppt_content', '') or ''
        kws = extract_keywords_from_d(c_cit, d_ppt)
        extra = [w for w in re.findall(r'[\u4e00-\u9fff]{2,4}', d_ppt) if len(w) >= 2][:5]
        kws = list(set(kws + extra))[:12]
        result[pn] = (c_cit, d_ppt, kws)
    return result


def _read_vision_kws() -> Dict[str, List[str]]:
    """读 vision plan keywords + data_points_boosted + target_text 拆词"""
    if not os.path.isfile(VISION_PLANS_PATH):
        return {}
    with open(VISION_PLANS_PATH) as f:
        plans = json.load(f).get("plans", [])
    result = {}
    for p in plans:
        pn = p.get("pn_x")
        if not pn:
            continue
        ks = set()
        # 1. data_points_boosted (PDF 摘要反向抽的关键词, 高质量)
        for k in p.get("data_points_boosted", []) or []:
            if k and len(k) > 1:
                ks.add(k)
        # 2. keywords
        for k in p.get("keywords", []) or []:
            if k and len(k) > 1 and not re.match(r'^[\d\.,%\-/\s]+$', k):
                ks.add(k)
        # 3. target_text 拆中文 2-4 字
        target = p.get("target_text", "") or ""
        for w in re.findall(r'[\u4e00-\u9fff]{2,4}', target):
            if len(w) >= 2:
                ks.add(w)
        # 4. data_points
        for k in p.get("data_points", []) or []:
            if k and len(k) > 1 and not re.match(r'^[\d\.,%\-/\s]+$', k):
                ks.add(k)
        result[pn] = list(ks)[:25]  # cap 25
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--mode", default=DEFAULT_HIGHLIGHT_MODE,
                        choices=["line", "fill", "both"])
    parser.add_argument("--out-dir", default=HIGHLIGHT_NEW_DIR)
    parser.add_argument("--vision-boost", action="store_true",
                        help="合并 vision plan keywords (默认 True)")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    csv_kws = _read_csv_kws()
    vision_kws = _read_vision_kws()
    print(f"CSV keywords: {len(csv_kws)} Pn-x")
    print(f"Vision keywords: {len(vision_kws)} Pn-x")

    pdfs = sorted(glob.glob(os.path.join(PDF_DIR, "P*-*_main.pdf")))
    if args.limit:
        pdfs = pdfs[:args.limit]
    print(f"待处理 PDF: {len(pdfs)}")

    summary = []
    success = 0
    fail = 0
    for pdf_in in pdfs:
        m = re.match(r'.+/P(\d+)-(\d+)_main\.pdf', pdf_in)
        if not m:
            continue
        pn = f"P{m.group(1)}-{m.group(2)}"

        # 合并 keywords: CSV 优先 (广覆盖) + vision 补充 (高质量)
        kws_csv = csv_kws.get(pn, ('', '', []))[2]
        kws_vision = vision_kws.get(pn, [])
        # 拼接: csv 先, vision 后, 去重, cap 30
        kws = list(dict.fromkeys(kws_csv + kws_vision))[:30]

        # 如果都没, fallback: D 列中文
        if not kws:
            d_ppt = csv_kws.get(pn, ('', '', []))[1]
            kws = [w for w in re.findall(r'[\u4e00-\u9fff]{2,4}', d_ppt) if len(w) >= 2][:5]

        out_pdf = os.path.join(args.out_dir, f"{pn}_highlight.pdf")
        jpg_dir = os.path.join(args.out_dir, f"{pn}_jpgs")
        os.makedirs(jpg_dir, exist_ok=True)

        try:
            r = process_pn_x(
                pn, pdf_in, out_pdf, kws, jpg_dir, f"{pn}_page",
                mode=args.mode, use_glm=False,
            )
        except Exception as e:
            print(f"  ❌ {pn}: ERROR {e}")
            fail += 1
            continue

        mark = "✓" if r["yellow_pct_estimate"] > 0.01 else "❌"
        summary.append({
            "pn_x": pn,
            "kws_csv_n": len(kws_csv),
            "kws_vision_n": len(kws_vision),
            "kws_total": len(kws),
            "new_yellow_pct": round(r["yellow_pct_estimate"], 4),
            "hits": r["total_hits"],
            "matched_terms": len(r["matched_terms"]),
            "skipped_terms": len(r["skipped_terms"]),
            "mode": r.get("mode", "?"),
            "ok": r["ok"],
        })
        if r["ok"]:
            success += 1
        else:
            fail += 1
        print(f"  {mark} {pn}: kws={len(kws)} (csv={len(kws_csv)}+vis={len(kws_vision)}) hits={r['total_hits']:>4d} yellow={r['yellow_pct_estimate']:.3f}%")

    if summary:
        summary_csv = os.path.join(args.out_dir, "_rerun_summary.csv")
        with open(summary_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
            writer.writeheader()
            writer.writerows(summary)
    print(f"\n=== 完成 ===")
    print(f"  成功 (yellow > 0.01%): {success}/{len(summary)}")
    print(f"  失败: {fail}")
    print(f"  Output: {args.out_dir}")


if __name__ == "__main__":
    main()
