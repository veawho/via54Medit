#!/usr/bin/env python3
"""P28-3: 固定句子定义, 自动定位页并 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P28-3_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P28-3/P28-3_highlight.pdf"

SENTENCES = [
    'if the patient fails to receive timely treatment, the mortality rate can reach 80–90%.',
    'The prognosis of traditional treatment methods for TTP is not satisfactory.',
    'With the continuous application of plasma exchange, the prognosis of this disease can be significantly improved, and the mortality rate can be controlled at 10% to 20%.'
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
