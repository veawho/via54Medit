#!/usr/bin/env python3
"""P23-9: slide 23 引用9 (Jodele Blood Rev 2015) 应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P23-9_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P23-9/P23-9_highlight.pdf"

SENTENCES = [
    "Hematopoietic stem cell transplantation (HSCT)-associated thrombotic microangiopathy (TA-TMA) is now a well-recognized and potentially severe complication of HSCT that carries a high risk of death.",
    "Speciﬁcally, TA-TMA can manifest as a multi-system disease occurring after various triggers of small vessel endothelial injury, leading to subsequent tissue damage in different organs.",
    "While the kidney is most commonly affected, TA-TMA involving organs such as the lung, bowel, heart, and brain is now known to have speciﬁc clinical presentations.",
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
