#!/usr/bin/env python3
"""Step 1: 新 PPT → 全页 PDF + 每页图片(导出 PPT 图片)
用法: python3 step1_export_slides.py <ppt_path> <out_dir> [dpi]
输出: <out_dir>/<base>_expanded.pdf, <out_dir>/images/slide_pp_NNN.jpg

渲染通道: **只走 Microsoft PowerPoint** —— 见同目录 ``ppt_to_pdf.py``。
原版 PPT 是 PowerPoint 做的, Keynote / LibreOffice / WPS / python-pptx 打开后
字体与布局和原版不一致, 按 2026-08-05 用户硬规则 (2026-09-11 重申) 禁用, **不 fallback**。
本文件原先直接调用 LibreOffice 的 headless 转换, 已按规范改掉。
"""
import os
import sys
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ppt_to_pdf import export_ppt_to_pdf  # noqa: E402


def export(ppt_path, out_dir, dpi=100):
    os.makedirs(out_dir, exist_ok=True)
    img_dir = os.path.join(out_dir, 'images')
    os.makedirs(img_dir, exist_ok=True)
    for f in glob.glob(os.path.join(img_dir, 'slide_pp_*.jpg')):
        os.remove(f)

    # 1) PowerPoint → PDF (唯一通道; 失败直接抛错, 不换渲染器)
    base = os.path.splitext(os.path.basename(ppt_path))[0]
    pdf_path = os.path.join(out_dir, f'{base}_expanded.pdf')
    export_ppt_to_pdf(ppt_path, pdf_path)

    # 2) fitz 渲染每页为 jpg
    try:
        import pymupdf as fitz  # PyMuPDF >= 1.24 的正式导入名
    except ImportError:  # 旧版只有 fitz (写 import fitz 会打弃用警告)
        import fitz
    doc = fitz.open(pdf_path)
    scale = dpi / 72.0
    mat = fitz.Matrix(scale, scale)
    n = len(doc)
    for pi in range(n):
        pix = doc[pi].get_pixmap(matrix=mat)
        pix.save(os.path.join(img_dir, f'slide_pp_{pi+1:03d}.jpg'))
    doc.close()
    print(f'PPT → {pdf_path} ({n} pages)')
    print(f'images → {img_dir} ({n} jpg)')
    return pdf_path, n


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('usage: step1_export_slides.py <ppt> <out_dir> [dpi]')
        sys.exit(1)
    dpi = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    export(sys.argv[1], sys.argv[2], dpi)
