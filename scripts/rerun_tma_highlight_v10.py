#!/usr/bin/env python3
"""
rerun_tma_highlight_v10.py — TMA 全量重生成 highlight (v10.1)

把 TMA _3_highlight/ 里所有 v9.7 生成的 highlight PDF 用 v10.1 重生成:
  - 修复 v9.7 annotation 颜色丢失 bug
  - 用 line 模式 (6 步规则要求)
  - 跳过 header/author/footer

输入:  TMA_文献整理/_2_pdfs/Pn-x_main.pdf  (源)
      TMA_文献整理/_3_highlight/Pn-x_highlight.pdf  (旧 v9.7)
      TMA_文献整理/_citation_table/tma_citation_table.csv  (关键词来源)
输出:  TMA_文献整理/_3_highlight_v10/Pn-x_highlight.pdf  (新 v10.1, 不覆盖旧)
      TMA_文献整理/_3_highlight_v10/Pn-x_page{N}.jpg  (渲染图)
      TMA_文献整理/_3_highlight_v10/_rerun_summary.csv  (新旧对比)

用法:  python3.11 rerun_tma_highlight_v10.py [--limit 10] [--mode line]
"""
import os, sys, csv, re, json, shutil
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


TMA_ROOT = "/Users/david/Desktop/TMA_文献整理"
PDF_DIR = os.path.join(TMA_ROOT, "_2_pdfs")
HIGHLIGHT_OLD_DIR = os.path.join(TMA_ROOT, "_3_highlight")
HIGHLIGHT_NEW_DIR = os.path.join(TMA_ROOT, "_3_highlight_v10")
CSV_PATH = os.path.join(TMA_ROOT, "_citation_table/tma_citation_table.csv")


def _yellow_max_pct(pdf_path: str, max_pages: int = 5) -> float:
    """测 PDF 黄色像素最大占比"""
    if not os.path.isfile(pdf_path):
        return -1.0
    try:
        doc = fitz.open(pdf_path)
        n = min(max_pages, len(doc))
        max_pct = 0.0
        for i in range(n):
            try:
                pix = doc[i].get_pixmap(matrix=fitz.Matrix(2, 2))
                arr = np.array(Image.open(__import__('io').BytesIO(pix.tobytes("png"))).convert("RGB"))
                yellow = (arr[:, :, 0] > 200) & (arr[:, :, 1] > 200) & (arr[:, :, 2] < 150)
                pct = yellow.sum() / yellow.size * 100
                max_pct = max(max_pct, pct)
            except Exception:
                pass
        doc.close()
        return max_pct
    except Exception:
        return -1.0


def _read_csv_kws(csv_path: str) -> Dict[str, Tuple[str, str, List[str]]]:
    """读 TMA CSV, 返回 {Pn-x: (c_cit, d_ppt, kws)}"""
    if not os.path.isfile(csv_path):
        return {}
    with open(csv_path, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    result = {}
    for r in rows:
        a, b = r.get('A_slide', '').strip(), r.get('B_mark', '').strip()
        if not a or not b:
            continue
        pn = f"P{a}-{b}"
        c_cit = r.get('C_citation', '') or ''
        d_ppt = r.get('D_ppt_content', '') or ''
        # 抽关键词
        kws = extract_keywords_from_d(c_cit, d_ppt)
        # 加 D 列里的中文 2-4 字词
        extra = [w for w in re.findall(r'[\u4e00-\u9fff]{2,4}', d_ppt) if len(w) >= 2][:5]
        kws = list(set(kws + extra))[:12]
        result[pn] = (c_cit, d_ppt, kws)
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="限制处理数量 (0=全部)")
    parser.add_argument("--mode", default=DEFAULT_HIGHLIGHT_MODE,
                        choices=["line", "fill", "both"])
    parser.add_argument("--out-dir", default=HIGHLIGHT_NEW_DIR)
    parser.add_argument("--use-glm", action="store_true", help="启用 GLM 应证段")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    csv_kws = _read_csv_kws(CSV_PATH)
    print(f"CSV 关键词: {len(csv_kws)} Pn-x, GLM: {args.use_glm}")

    # 找所有 main PDF
    pdfs = sorted(glob_pdfs(PDF_DIR))
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

        c_cit, d_ppt, kws = csv_kws.get(pn, ('', '', []))
        if not kws:
            # fallback: 用 D 列
            extra = [w for w in re.findall(r'[\u4e00-\u9fff]{2,4}', d_ppt) if len(w) >= 2][:5]
            kws = extra

        out_pdf = os.path.join(args.out_dir, f"{pn}_highlight.pdf")
        jpg_dir = os.path.join(args.out_dir, f"{pn}_jpgs")
        os.makedirs(jpg_dir, exist_ok=True)

        try:
            r = process_pn_x(
                pn, pdf_in, out_pdf, kws, jpg_dir, f"{pn}_page",
                mode=args.mode,
                use_glm=args.use_glm,
                glm_citation=c_cit,
                glm_visual=d_ppt,
            )
        except Exception as e:
            print(f"  ❌ {pn}: ERROR {e}")
            fail += 1
            continue

        # 测新旧
        old_pdf = os.path.join(HIGHLIGHT_OLD_DIR, f"{pn}_highlight.pdf")
        old_yellow = _yellow_max_pct(old_pdf)
        new_yellow = r["yellow_pct_estimate"]

        mark = "✓" if new_yellow > 0.01 else "❌"
        summary.append({
            "pn_x": pn,
            "old_yellow_pct": round(old_yellow, 4) if old_yellow >= 0 else None,
            "new_yellow_pct": round(new_yellow, 4),
            "delta": round(new_yellow - old_yellow, 4) if old_yellow >= 0 else None,
            "hits": r["total_hits"],
            "n_jpgs": len(r.get("jpg_files", [])),
            "matched_terms": len(r["matched_terms"]),
            "skipped_terms": len(r["skipped_terms"]),
            "mode": r.get("mode", "?"),
            "ok": r["ok"],
            "glm_evidence_count": len(r.get("glm_evidence", []) or []),
        })
        success += 1 if r["ok"] else 0
        fail += 0 if r["ok"] else 1
        delta_str = f"{new_yellow - old_yellow:+5.3f}%" if old_yellow >= 0 else "  N/A "
        glm_n = r.get("glm_evidence_count", 0)
        print(f"  {mark} {pn}: OLD={old_yellow:6.3f}%  NEW={new_yellow:6.3f}%  Δ={delta_str}  hits={r['total_hits']:3d}  glm_ev={glm_n}")

    # 写 summary
    summary_csv = os.path.join(args.out_dir, "_rerun_summary.csv")
    if summary:
        with open(summary_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
            writer.writeheader()
            writer.writerows(summary)
    summary_json = os.path.join(args.out_dir, "_rerun_summary.json")
    with open(summary_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print()
    print(f"=== 完成 ===")
    print(f"  成功 (yellow > 0.01%): {success}/{len(summary)}")
    print(f"  失败: {fail}")
    print(f"  Summary: {summary_csv}")
    print(f"  Output:  {args.out_dir}")


def glob_pdfs(dir_path: str) -> List[str]:
    import glob
    return glob.glob(os.path.join(dir_path, "P*-*_main.pdf"))


if __name__ == "__main__":
    main()
