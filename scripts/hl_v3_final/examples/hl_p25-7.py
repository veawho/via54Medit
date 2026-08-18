#!/usr/bin/env python3
"""P25-7: 固定句子定义, 自动定位页并 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P25-7_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P25-7/P25-7_highlight.pdf"

SENTENCES = [
    'aHUS results from chronic, uncontrolled activity of the alternative complement pathway, which activates platelets and damages the endothelium.',
    'STEC-HUS can be excluded through testing for Shiga toxin–producing E. coli.',
    'aHUS can be distinguished from TTP on the basis of ADAMTS13 (a disintegrin and metalloproteinase with a thrombos-pondin type 1 motif, member 13) activity, with a severe decrease characteristic of TTP.',
    'In contrast, plasma ADAMTS13 activity may be reduced from the normal range of 67% to 120% in aHUS or STEC-HUS, but should still remain greater than 5% to 10%, with the exact cut-off value dependent upon the assay used.'
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
