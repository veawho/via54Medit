#!/usr/bin/env python3
"""P23-3: slide 23 引用3 (Ho BBMT 2005 TA-TMA共识) 应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P23-3_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P23-3/P23-3_highlight.pdf"

SENTENCES = [
    "The syndrome of microangiopathic hemolysis associated with renal failure, neurologic impairment, or both is a recognized complication of hematopoietic stem cell transplantation.",
    "The reported incidence of TMA after allogeneic HSCT varies from 0.5% to 76%",
    "identiﬁed 447 (8.2%) cases of posttransplantation TMA, with a me-dian mortality of 75% within 3 months of the diag-nosis.",
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
