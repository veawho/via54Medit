#!/usr/bin/env python3
"""P31-4: 固定句子定义, 自动定位页并 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P31-4_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P31-4/P31-4_highlight.pdf"

SENTENCES = [
    'Forty patients (98%; 95% CI, 87%-100%; N 5 41) had platelet count normalization (Table 2) at a median',
    'Improvement in platelet counts from baseline was significant at 1 week (mean change, 104 6 115 3 103/mL) and was maintained to 26 weeks (mean change from baseline, 135 6 114 3 103/mL; n 5 27; P # 0.001 at all time points; Fig 2).',
    'Of the 24 patients on dialysis at baseline, 20 (83%) dis-continued dialysis.'
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
