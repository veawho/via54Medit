#!/usr/bin/env python3
"""用 fitz 渲染 highlight PDF 全部页面为 PNG (正确处理 cropbox, 无 pdftoppm 偏移)"""
import fitz, sys, os

def render_all(pdf_path, out_dir, dpi=100):
    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    # 清空旧图
    for f in os.listdir(out_dir):
        try:
            os.remove(os.path.join(out_dir, f))
        except OSError:
            pass
    scale = dpi / 72.0
    mat = fitz.Matrix(scale, scale)
    for pi in range(len(doc)):
        pix = doc[pi].get_pixmap(matrix=mat)
        pix.save(os.path.join(out_dir, f'page_{pi+1:03d}.png'))
    doc.close()
    print(f'rendered {len(os.listdir(out_dir))} pages -> {out_dir}')

if __name__ == '__main__':
    pdf, out = sys.argv[1], sys.argv[2]
    dpi = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    render_all(pdf, out, dpi)
