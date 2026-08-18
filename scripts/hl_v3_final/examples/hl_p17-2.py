#!/usr/bin/env python3
"""P17-2: slide 17 引用2 (Zheng JTH 2020 ISTH TTP指南) ADAMTS13诊断应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P17-2_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P17-2/P17-2_highlight.pdf"

SENTENCES = [
    "Thrombotic thrombocytopenic purpura (TTP) is a rare but poten-tially fatal blood disorder.",
    "More than 95% of all TTP cases are iTTP, whereas cTTP accounts for <5% of cases.",
    "The distinction between TTP and HUS relies on the test of plasma ADAMTS13 activity.",
    "A plasma ADAMTS13 activity of less than 10 IU/dL (often referred to as 10% of normal ADAMTS13 activity) is the hallmark of TTP",
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
