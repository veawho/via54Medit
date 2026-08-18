#!/usr/bin/env python3
"""P30-3: 固定句子定义, 自动定位页并 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P30-3_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P30-3/P30-3_highlight.pdf"

SENTENCES = [
    'The implementation of a multidisciplinary team (MDT) could decrease the time to diagnosis and treatment for HUS and may improve the outcomes of these patients.',
    'MDT implementation was associated with a greater number of patients who meet TMA crite-ria.',
    'A decrease in the RT and T-LOS periods were observed and associated with better out-comes in these patients.'
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
