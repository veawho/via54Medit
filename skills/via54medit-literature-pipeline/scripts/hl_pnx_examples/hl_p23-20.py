#!/usr/bin/env python3
"""P23-20: slide 23 引用20 (Postalcioglu BBMT 2018) 应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P23-20_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P23-20/P23-20_highlight.pdf"

SENTENCES = [
    "Transplantation-associated thrombotic microangiopathy (TA-TMA) is a serious complication of hematopoietic stem cell transplantation (HSCT).",
    "Using the City of Hope criteria, we identiﬁed 258 patients (13%) with “deﬁnite” TMA and 508 patients (26%) with “probable” TMA.",
    "In multivariable analyses, deﬁnite and probable TMA were each independently associated with higher mortality (HR, 5.24; 95% CI, 4.43 to 6.20 and HR, 2.12; 95% CI, 1.84 to 2.44, respectively), and long-term kidney dysfunction (HR, 5.43; 95% CI, 4.61 to 6.40 and HR, 2.20; 95% CI, 1.92 to 2.51, respectively).",
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
