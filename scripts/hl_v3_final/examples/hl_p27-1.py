#!/usr/bin/env python3
"""P27-1: 固定句子定义, 自动定位页并 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P27-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P27-1/P27-1_highlight.pdf"

SENTENCES = [
    'Over 450 clinicians, from 16 countries were invited to complete an online survey.',
    'Responses indicate that a differential diagnosis of TMA is usually made within 1–2 (53%) or 3–4 days (26%) of presentation.',
    'Similarly, therapy is usually initiated within the first 4 days (74%), however 13% report treatment initiation >1-week post-presentation.',
    'In practice however, approximately half of clinicians state a diagnosis of TMA takes more than 3 days.',
    'Similarly, therapeutic strategies are initiated after 3 days or more in the majority of cases (57%).'
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
