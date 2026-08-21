#!/usr/bin/env python3
"""P30-4: 固定句子定义, 自动定位页并 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P30-4_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P30-4/P30-4_highlight.pdf"

SENTENCES = [
    'Delays in diagnosis and initiation of therapy are common due to the low inci-dence, variable presentation, and poor awareness of these diseases, underscoring the need for interdisci-plinary approaches to clinical care for TMA.',
    'The TMA team consists of clinical faculty from different disciplines who together are charged with the responsibility to quickly analyze clinical presentations, guide laboratory testing, and streamline prompt institution of treatment.',
    'Early detection and diagnosis of TMA are essential to improve clinical outcomes.'
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
