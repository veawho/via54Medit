#!/usr/bin/env python3
"""P28-1: 固定句子定义, 自动定位页并 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P28-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P28-1/P28-1_highlight.pdf"

SENTENCES = [
    'Thrombosis constitutes the leading cause of death, occurring in up to 50% of PNH patients.',
    'Early diagnosis and treatment of an acute hemolytic process is critical, as hemolysis itself is a risk factor for thrombosis and organ damage'
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
