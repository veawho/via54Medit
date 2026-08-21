#!/usr/bin/env python3
"""P18-1: slide 18 引用1 (Zheng JTH 2020 ISTH) PLASMIC/French评分应证句"""
import sys
sys.path.insert(0, '/tmp')
import fitz, shutil
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P18-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P18-1/P18-1_highlight.pdf"

SENTENCES = {
    6: [  # p7
        "PLASMIC score or the French score may be used.",
    ],
}

def run():
    import fitz
    doc = fitz.open(PDF)
    S = {}
    for pi, sents in SENTENCES.items():
        chars, text = page_char_stream(doc[pi])
        for s in sents:
            if locate_sentence(text, s) is not None:
                S.setdefault(pi, []).append(s)
            else:
                print(f'NOT FOUND p{pi+1}: {s[:45]}')
    doc.close()
    report = highlight_sentences(PDF, OUT, S, verbose=False)
    for r in report:
        print(f'p{r[0]}: {r[1]} -> {r[2]}')
    # Table 1 标题行 highlight (p5)
    doc = fitz.open(OUT)
    page = doc[4]
    r_t = page.search_for('PLASMIC score or French score predicts')
    print('Table1 标题位置:', [(round(x.x0,1), round(x.y0,1), round(x.x1,1), round(x.y1,1)) for x in r_t])
    if r_t:
        r0 = r_t[0]
        yc = (r0.y0 + r0.y1) / 2
        words = page.get_text('words')
        row_words = [w for w in words if abs((w[1]+w[3])/2 - yc) < 6]
        if row_words:
            x0 = min(w[0] for w in row_words) - 2
            x1 = max(w[2] for w in row_words) + 2
            y0 = min(w[1] for w in row_words) - 2
            y1 = max(w[3] for w in row_words) + 2
            hl = page.add_rect_annot(fitz.Rect(x0, y0, x1, y1))
            hl.set_colors(stroke=(1.0, 0.85, 0.0), fill=(1.0, 0.85, 0.0))
            hl.set_border(width=0)
            hl.set_opacity(0.8)
            hl.update()
            print(f'Table1 标题行: ({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f})')
    tmp = OUT.replace('.pdf', '.t.pdf')
    doc.save(tmp, garbage=4, deflate=True)
    doc.close()
    shutil.move(tmp, OUT)
    print('saved:', OUT)

if __name__ == "__main__":
    run()
