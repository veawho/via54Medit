#!/usr/bin/env python3
"""P31-5: 固定句子定义, 自动定位页并 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P31-5_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P31-5/P31-5_highlight.pdf"

SENTENCES = [
    'Thus, a 2-year analysis found that the earlier clinical benefits achieved by eculizumab treatment of aHUS were maintained at 2 years of follow-up.',
    'Complete TMA response was achieved by 11 patients (65%) at week 26 and by 13 patients (76%) at the 1- and 2-year cutoffs.'
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
