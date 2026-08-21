#!/usr/bin/env python3
"""P31-6: 固定句子定义, 自动定位页并 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P31-6_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P31-6/P31-6_highlight.pdf"

SENTENCES = [
    'Importantly, there were no meningococcal infections reported in eculizumab-experienced or C5i-naive patients during ravulizumab treatment.',
    'The latter may be attributable to mitigating strategies, such as meningococcal vaccination prior to ravulizumab therapy, in addition to reduced contact with individuals at high risk of infection because of greater infection awareness and COVID-19 pandemic measures'
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
