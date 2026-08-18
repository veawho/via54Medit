#!/usr/bin/env python3
"""P25-8: 固定句子定义, 自动定位页并 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P25-8_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P25-8/P25-8_highlight.pdf"

SENTENCES = [
    'The most critical and urgent differential diagnosis is to differentiate TTP from aHUS owing to the urgency of specific treatment.',
    'Somewhat reduced ADAMTS13-activity levels (> 10% of normal) may also occur in aHUS, but such levels are sufficient to exclude TTP.',
    'Conversely, in TTP, reduced activity of ADAMTS13 results in platelet hyperadhesiveness and clumping within the microvasculature.',
    'If ADAMTS13 tests are not available within a few hours, a diagnostic algorithm developed by Coppo et al. – in which TTP is suggested by low platelet count (< 30 × 109/L), mildly elevated serum creatinine (≤ 200 µmol/L) and detectable antinuclear antibodies – could help form an initial differential diagnosis.'
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
