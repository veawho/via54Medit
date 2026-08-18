#!/usr/bin/env python3
"""P24-1: slide 24 引用1 (Schoettler TCT 2023) 高危分层应证句 (按slide24重选)"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P24-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P24-1/P24-1_highlight.pdf"

SENTENCES = [
    "patients with any of the following features are at increased risk of nonrelapse mortality and should be stratiﬁed as high-risk TA-TMA: elevated sC5b-9, LDH 2 times the ULN, rUPCR 1 mg/mg, multiorgan dysfunction, concurrent grade II-IV acute graft-versus-host disease (GVHD), or infection (bacterial or viral)",
    "soluble C5b-9 (sC5b-9) exceeding the ULN; and proteinuria (1 mg/mg random urine protein-to-creatinine ratio [rUPCR])",
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
