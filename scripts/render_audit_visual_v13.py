#!/usr/bin/env python3
"""
render_audit_visual_v13.py — Phase 2 visual rendering

对每个 Pn-x 有 highlight 的页:
  1. 渲染 highlight PDF page 为 PNG
  2. 在 page 上画出 highlight bbox (红框)
  3. 同时渲染 step3 原始 PDF 同 page (作对比)
  4. 保存到 /tmp/audit_v13_visual/<pn>/page_<N>.png

主要给 user 人工检查用, 但也输出 structured summary。
"""
import os, sys, json, hashlib
from pathlib import Path
import fitz
fitz.TOOLS.mupdf_display_warnings(False)

TMA_ROOT = "/Users/david/Desktop/TMA_文献整理"
STEP4_DIR = f"{TMA_ROOT}/step4_highlight_106目录_合并DOI"
STEP3_DIR = f"{TMA_ROOT}/step3_pdf下载_106目录_合并DOI"
PNX_DIR = f"{TMA_ROOT}/_pnx"
OUT_DIR = "/tmp/audit_v13_visual"
os.makedirs(OUT_DIR, exist_ok=True)


def render_page_with_annots(doc, pno, out_path: str, render_dpi: int = 100):
    """渲染带 annotation 边框的 page"""
    page = doc[pno]
    mat = fitz.Matrix(render_dpi / 72, render_dpi / 72)

    # 先渲染 page
    pix = page.get_pixmap(matrix=mat, alpha=False)
    pix.save(out_path)

    # 再用 PIL 加红框 (annotations)
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.open(out_path)
        draw = ImageDraw.Draw(img)
        scale = render_dpi / 72
        for annot in page.annots() or []:
            try:
                if annot.type[0] not in (8, 9):
                    continue
            except:
                continue
            rect = annot.rect
            x0, y0, x1, y1 = rect.x0*scale, rect.y0*scale, rect.x1*scale, rect.y1*scale
            draw.rectangle([x0, y0, x1, y1], outline='red', width=3)
        img.save(out_path)
    except Exception as e:
        pass


def main():
    if not os.path.exists(STEP4_DIR):
        print(f"❌ {STEP4_DIR} 不存在")
        return

    pn_x = sorted([f.replace('_semantic_highlight.pdf', '')
                   for f in os.listdir(STEP4_DIR)
                   if f.endswith('_semantic_highlight.pdf')])
    SKIP_PN = {'P12-3'}
    print(f"📋 找到 {len(pn_x)} 个 Pn-x")

    summary = {}
    for pn in pn_x:
        if pn in SKIP_PN:
            continue
        step4_pdf = f"{STEP4_DIR}/{pn}_semantic_highlight.pdf"
        if not os.path.exists(step4_pdf) or os.path.getsize(step4_pdf) < 5000:
            continue
        try:
            doc = fitz.open(step4_pdf)
        except:
            continue

        # 找有 highlight 的 page
        pages_with_highlight = []
        for pno in range(doc.page_count):
            page = doc[pno]
            annots = list(page.annots() or [])
            n = 0
            for annot in annots:
                try:
                    if annot.type[0] in (8, 9):
                        n += 1
                except:
                    pass
            if n > 0:
                pages_with_highlight.append((pno + 1, n))

        if not pages_with_highlight:
            doc.close()
            continue

        # 渲染每页
        out_pn_dir = f"{OUT_DIR}/{pn}"
        os.makedirs(out_pn_dir, exist_ok=True)
        for page_num, n_hl in pages_with_highlight:
            pno = page_num - 1
            out_png = f"{out_pn_dir}/page_{page_num:02d}.png"
            render_page_with_annots(doc, pno, out_png)

        summary[pn] = {
            "pages_with_highlight": pages_with_highlight,
            "total_highlights": sum(n for _, n in pages_with_highlight),
        }
        doc.close()

    # 输出 summary
    with open(f"{OUT_DIR}/_summary.json", "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n💾 渲染: {OUT_DIR}/<Pn-x>/page_NN.png")
    print(f"💾 summary: {OUT_DIR}/_summary.json")
    print(f"\n总 Pn-x with highlights: {len(summary)}")
    total_hl = sum(s['total_highlights'] for s in summary.values())
    print(f"总 highlights: {total_hl}")


if __name__ == "__main__":
    main()
