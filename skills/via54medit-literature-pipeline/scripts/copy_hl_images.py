#!/usr/bin/env python3
"""把有 highlight 的页面图片复制到 Pn-x 根目录(仅高亮页, 命名 {Pn-x}_highlight_pNNN.png)
用法: python3 copy_hl_images.py [Pn-x ...]   (省略参数=全部)"""
import fitz, os, sys, glob, shutil

BASE = '/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI'

def process(pn, dry=False):
    d = os.path.join(BASE, pn)
    hp = os.path.join(d, f'{pn}_highlight.pdf')
    pages = os.path.join(d, f'{pn}_highlight_pages')
    if not os.path.exists(hp) or not os.path.isdir(pages):
        return f'{pn}: skip (no pdf/pages)'
    # 高亮页号
    doc = fitz.open(hp)
    hl = sorted(pi + 1 for pi in range(len(doc)) if len(list(doc[pi].annots() or [])) > 0)
    doc.close()
    # 清理根目录旧图
    for f in glob.glob(os.path.join(d, f'{pn}_highlight_p*.png')):
        os.remove(f)
    # 复制高亮页
    n = 0
    for pg in hl:
        src = os.path.join(pages, f'page_{pg:03d}.png')
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(d, f'{pn}_highlight_p{pg:03d}.png'))
            n += 1
    return f'{pn}: {n} images (pages {hl})'

if __name__ == '__main__':
    targets = sys.argv[1:] or sorted(os.listdir(BASE))
    for pn in targets:
        if os.path.isdir(os.path.join(BASE, pn)) and pn.startswith('P'):
            print(process(pn))
