#!/usr/bin/env python3
"""P16-1: slide 16 引用1 (Trojnar Front Immunol 2019) TMA分类应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P16-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P16-1/P16-1_highlight.pdf"

SENTENCES = [
    "We determined the PTX3 and CRP levels, complement factor and activation product concentrations in blood samples of 171 subjects with the diagnosis of typical hemolytic uremic syndrome (STEC-HUS) (N = 34), atypical HUS (aHUS) (N = 44), secondary TMA (N = 63), thrombotic thrombocytopenic purpura (TTP) (N = 30)",
    "All acute phase-TMA patients presented with laboratory signs of hemolysis and thrombocytopenia (<150 G/L), with the lowest median platelet count (i.e., 16 G/L) in the TTP subgroup.",
    "ADAMTS13 deﬁciency was present in all of the TTP patients.",
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
