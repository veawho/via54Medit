#!/usr/bin/env python3
"""P28-2: 固定句子定义, 自动定位页并 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P28-2_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P28-2/P28-2_highlight.pdf"

SENTENCES = [
    'Eighteen cases (47%) had a delayed diag-nosis (median: 5 days).',
    'Neurological events (stroke/TIA, seizure, altered mental status) occurred in 67% vs 30% patients in group 1 and 2, respectively (p = 0.04).',
    'Diagnostic delay is highly prevalent in iTTP, with a significant impact on short-term neurolog-ical outcome.'
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
