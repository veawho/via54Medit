#!/usr/bin/env python3
"""P22-1: slide 22 引用1 (Laurence Clin Adv Hematol Oncol 2016) aHUS识别应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P22-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P22-1/P22-1_highlight.pdf"

SENTENCES = [
    "DIC must be recognized and treated before it is possible to discriminate among the other 3 major TMAs.",
    "STEC-HUS can be excluded through testing for Shiga toxin–producing E. coli.",
    "aHUS can be distinguished from TTP on the basis of ADAMTS13 (a disintegrin and metalloproteinase with a thrombos-pondin type 1 motif, member 13) activity, with a severe decrease characteristic of TTP.",
    "Finally, it is important to recognize that aHUS remains a clinical diagnosis, but in complex scenarios, tissue biopsy may be a useful adjunct in diagnosis.",
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
