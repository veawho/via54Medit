#!/usr/bin/env python3
"""Step 1: 新 PPT → 全页 PDF + 每页图片(导出 PPT 图片)
用法: python3 step1_export_slides.py <ppt_path> <out_dir> [dpi]
输出: <out_dir>/ppt_expanded.pdf, <out_dir>/images/slide_pp_NNN.jpg
依赖: LibreOffice(soffice) 转 PDF + PyMuPDF 渲染"""
import subprocess, sys, os, glob, tempfile, shutil

def export(ppt_path, out_dir, dpi=100):
    os.makedirs(out_dir, exist_ok=True)
    img_dir = os.path.join(out_dir, 'images')
    os.makedirs(img_dir, exist_ok=True)
    for f in glob.glob(os.path.join(img_dir, 'slide_pp_*.jpg')):
        os.remove(f)
    # 1) soffice → PDF
    base = os.path.splitext(os.path.basename(ppt_path))[0]
    pdf_path = os.path.join(out_dir, f'{base}_expanded.pdf')
    tmpdir = tempfile.mkdtemp()
    try:
        r = subprocess.run(['soffice', '--headless', '--convert-to', 'pdf',
                            '--outdir', tmpdir, ppt_path],
                           capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            print('soffice stderr:', r.stderr[-500:])
            raise RuntimeError('soffice convert failed')
        cand = glob.glob(os.path.join(tmpdir, '*.pdf'))
        if not cand:
            raise RuntimeError('soffice produced no pdf')
        shutil.move(cand[0], pdf_path)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    # 2) fitz 渲染每页为 jpg
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
