#!/usr/bin/env python3
"""P31-2: 固定句子定义, 自动定位页并 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P31-2_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P31-2/P31-2_highlight.pdf"

SENTENCES = [
    'Unlike TTP, plasma therapy has no role in the long-term management of aHUS.',
    'If a putative TTP patient is not responding to plasma therapy by all clinical criteria, or requires prolonged PE to effect or maintain a remission, reevaluate the diagnosis and consider aHUS.'
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
