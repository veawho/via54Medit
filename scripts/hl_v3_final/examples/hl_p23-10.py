#!/usr/bin/env python3
"""P23-10: slide 23 引用10 (Dandoy BBMT 2015) 应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P23-10_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P23-10/P23-10_highlight.pdf"

SENTENCES = [
    "Cardiac complications after hematopoietic stem cell transplantation (HSCT) can lead to signiﬁcant morbidity and mortality.",
    "At least 1 abnormality was identiﬁed in 30% of cases.",
    "Seventeen children had a pericardial effusion, 13 elevated right ventricular pressure, and 3 reduced left ventricular function.",
    "Moreover, raised right ventricular pressure at day þ7 was signiﬁcantly associated with transplant-associated thrombotic microangiopathy (TA-TMA; P ¼ .004) and may indicate early vascular injury in the lungs.",
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
