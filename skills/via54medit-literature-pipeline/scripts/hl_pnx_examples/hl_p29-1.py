#!/usr/bin/env python3
"""P29-1: 固定句子定义, 自动定位页并 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P29-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P29-1/P29-1_highlight.pdf"

SENTENCES = [
    'Screening of the functional activity of the classic (total hemolytic complement assay [CH50]) and alternative (complement alternate pathway assay [AH50]) pathways can reveal whether recent complement activation has consumed the involved factors (low CH50 and/or AH50).',
    'Most patients with complement-mediated TMA will have low AH50 activity.',
    'A combination of low AH50, CFH, and complement factor B (CFB) levels in the presence of a normal C4 level and elevated complement factor Bb levels is a very strong indicator of alternative pathway dysfunction.',
    'Although serologic testing is commonly available, it is neither specific nor sensitive.'
]

def build():
    import fitz
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

if __name__ == "__main__":
    sentences = build()
    highlight_sentences(SRC, OUT, sentences, verbose=True)
    print('saved:', OUT)
