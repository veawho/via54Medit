#!/usr/bin/env python3
"""P12-1: slide 12 引用1 (Azoulay Chest 2017) MAHA血涂片应证句 + Table 1 Schistocytes 行
注: slide 11/12/22/25 均引用 Azoulay Chest 2017, 本 Pn-x 用 P12-1_main.pdf(King's Research Portal 版)"""
import sys
sys.path.insert(0, '/tmp')
import fitz
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P12-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P12-1/P12-1_highlight.pdf"

SENTENCES = [
    # p14 裂红细胞句 (slide12 血涂片核心)
    "Clinical suspicion of a TMA is based on clinical findings, including microangiopathic haemolytic anaemia, thrombocytopenia, low haptoglobin, elevated lactate dehydrogenase, elevated reticulocytes, fragmented red cells and schistocytes on peripheral blood smear.",
]

def build():
    doc = fitz.open(SRC)
    n = len(doc)
    S = {}
    for s in SENTENCES:
        for pi in range(n):
            chars, text = page_char_stream(doc[pi])
            if locate_sentence(text, s) is not None:
                S.setdefault(pi, []).append(s)
                break
        else:
            print('NOT FOUND:', s[:55])
    doc.close()
    return S

def add_table_row():
    """Table 1 的 Schistocytes 行高亮(0.45 opacity 与句子一致)"""
    doc = fitz.open(OUT)
    # 找句子所在页(用句子定位)
    chars, text = page_char_stream(doc[13])
    hit_page = None
    for pi in range(len(doc)):
        r = doc[pi].search_for('Schistocytes')
        if r and pi < 20:  # 正文表格(排除 p28 缩写表)
            hit_page = pi
            break
    if hit_page is None:
        doc.close()
        return None
    page = doc[hit_page]
    r0 = page.search_for('Schistocytes')[0]
    yc = (r0.y0 + r0.y1) / 2
    words = page.get_text('words')
    row_words = [w for w in words if abs((w[1] + w[3]) / 2 - yc) < 6]
    if not row_words:
        doc.close()
        return None
    x0 = min(w[0] for w in row_words) - 1
    x1 = max(w[2] for w in row_words) + 1
    y0 = min(w[1] for w in row_words) - 1
    y1 = max(w[3] for w in row_words) + 1
    hl = page.add_rect_annot(fitz.Rect(x0, y0, x1, y1))
    hl.set_colors(stroke=(1.0, 0.85, 0.0), fill=(1.0, 0.85, 0.0))
    hl.set_border(width=0)
    hl.set_opacity(0.45)
    hl.update()
    tmp = OUT.replace('.pdf', '.t.pdf')
    doc.save(tmp, garbage=4, deflate=True)
    doc.close()
    import shutil
    shutil.move(tmp, OUT)
    return (round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1))

if __name__ == "__main__":
    sentences = build()
    highlight_sentences(SRC, OUT, sentences, verbose=True)
    r = add_table_row()
    print('Table Schistocytes 行:', r)
    print('saved:', OUT)
