#!/usr/bin/env python3
"""P23-13: slide 23 引用13 (Jodele BMT 2018) 应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P23-13_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P23-13/P23-13_highlight.pdf"

SENTENCES = [
    "Transplant-associated thrombotic microangiopathy (TA-TMA) is an increasingly recognized complication of hematopoietic cell transplant that can result in multi-organ failure (MOF).",
    "TA-TMA with MOF was diagnosed in 13 patients (21.7%) at a median of 18 days after aHCT.",
    "Six of 13 patients with TA-TMA and MOF received terminal complement blocker eculizumab for therapy.",
]

def scan():
    import fitz
    doc = fitz.open(PDF)
    n = len(doc)
    for s in SENTENCES:
        found = None
        for pi in range(n):
            chars, text = page_char_stream(doc[pi])
            if locate_sentence(text, s) is not None:
                found = pi + 1
                break
        print(f'p{found if found else "?"}: {s[:55]}...')
    doc.close()

def run():
    import fitz
    doc = fitz.open(PDF)
    n = len(doc)
    S = {}
    for s in SENTENCES:
        for pi in range(n):
            chars, text = page_char_stream(doc[pi])
            if locate_sentence(text, s) is not None:
                S.setdefault(pi, []).append(s)
                break
        else:
            print(f'NOT FOUND: {s[:55]}')
    doc.close()
    highlight_sentences(PDF, OUT, S)
    print('saved:', OUT)

if __name__ == "__main__":
    if sys.argv[1] == 'test':
        scan()
    else:
        run()
