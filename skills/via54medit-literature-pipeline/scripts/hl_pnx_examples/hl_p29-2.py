#!/usr/bin/env python3
"""P29-2: 固定句子定义, 自动定位页并 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P29-2_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P29-2/P29-2_highlight.pdf"

SENTENCES = [
    'Although the sensitivity of this finding for the diagnosis of aHUS is 100%, the specificity is only 28%, with a positive likelihood ratio of 1.39.',
    'Patients with aHUS had lower CH50, C3, and CFB than did those with secondary non-aHUS TMA (all P<.01).',
    'A COMS abnormality should not be interpreted in isolation.',
    'In conjunction with clinical presentation, a decrease in both CFB and CH50 may be an important clue to support the diagnosis of aHUS.'
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
