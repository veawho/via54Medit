#!/usr/bin/env python3
"""P23-16: slide 23 引用16 (Schoettler Blood Adv 2020) 应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P23-16_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P23-16/P23-16_highlight.pdf"

SENTENCES = [
    "Eight patients (2.6%) were diagnosed with TA-TMA by their provider.",
    "Overall survival was signiﬁcantly worse (P , .0001) and TRM was signiﬁcantly higher in patients who met criteria for TA-TMA (MC-TA-TMA) (P , .0001).",
    "After controlling for comorbid conditions, MC-TA-TMA (hazard ratio [HR], 10.9; P 5 .0001) and grade 3/4 acute graft-versus-host-disease (aGVHD) (HR 3.5; P 5 .01) remained independently associated with increased TRM.",
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
