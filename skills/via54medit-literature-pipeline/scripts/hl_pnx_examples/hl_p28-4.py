#!/usr/bin/env python3
"""P28-4: 固定句子定义, 自动定位页并 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P28-4_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P28-4/P28-4_highlight.pdf"

SENTENCES = [
    'Overall, a ≥2 days delay from admission to starting TPE was more prevalent in the older age groups (31.9% vs. 34.4% vs. 47.6%, p-value of <.001; Table 1A).',
    'A ≥2 days delay from admission to starting TPE was independently associated with higher in-hospital mortality (adjusted OR, 1.615; 95% CI, 1.220–2.138, p-value of .001; Figure 1).'
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
