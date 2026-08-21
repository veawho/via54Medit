#!/usr/bin/env python3
"""P23-15: slide 23 引用15 (Schoettler BBMT 2019) 应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P23-15_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P23-15/P23-15_highlight.pdf"

SENTENCES = [
    "Transplantation-associated thrombotic microangiopathy (TA-TMA) is a known complication of autologous hematopoi-etic cell transplantation (aHCT), particularly in children with neuroblastoma.",
    "Overall, 318 aHCTs were performed in 243 patients.",
    "Nine patients (3.7%) were diagnosed with TA-TMA.",
    "TA-TMA occurred most frequently in children with neuroblastoma (n = 7; 78%), all of whom were conditioned with carboplatin, etoposide, and melphalan.",
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
