#!/usr/bin/env python3
"""P25-1: slide 25 引用1 (Jodele Blood 2014) HSCT-TMA鉴别应证句 (按slide25重选)"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P25-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P25-1/P25-1_highlight.pdf"

SENTENCES = [
    "Hematopoietic stem cell transplantationeassociated thrombotic microangiopathy (HSCT-TMA) is a challenging post-transplant complication associated with long-term morbidity and high mortality",
    "In the most severe form of HSCT-TMA, mortality rates approach 90%, whereas milder cases have an increased risk of chronic kidney disease",
    "HSCT-TMA is a multifactorial disease in which either the classical or alternative complement pathways may become activated, resulting in tissue damage from micro-vessel thrombosis",
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
