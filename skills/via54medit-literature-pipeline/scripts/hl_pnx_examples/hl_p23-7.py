#!/usr/bin/env python3
"""P23-7: slide 23 引用7 (Wanchoo AJKD 2018) 应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P23-7_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P23-7/P23-7_highlight.pdf"

SENTENCES = [
    "Thrombotic microangiopathy associated with hematopoietic stem cell transplantation (HSCT-TMA) is a well-recognized complication of HSCT that has a high risk for death.",
    "Renal manifestations of HSCT-TMA include reduced glomerular ﬁltration rate, proteinuria, and hypertension.",
    "Along with endothelial injury, there is also activation of the clotting cascade, leading to platelet consumption, ﬁbrin deposition, thrombosis, and microangiopathic hemolytic anemia",
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
