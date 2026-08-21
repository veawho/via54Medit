#!/usr/bin/env python3
"""P23-26: slide 23 引用26 (Jodele Blood 2013) 应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P23-26_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P23-26/P23-26_highlight.pdf"

SENTENCES = [
    "We identiﬁed a high prevalence of deletions in CFH-related genes 3 and 1 (delCFHR3-CFHR1) and CFH autoantibodies in these patients with HSCT-TMA.",
    "Our observations suggest that complement alternative pathway dysregulation may be involved in the pathogenesis of post-HSCT TMA.",
    "In its most severe form mortality rates are very high (;90%), especially when dialysis is required.",
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
