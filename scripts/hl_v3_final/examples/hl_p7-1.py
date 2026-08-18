#!/usr/bin/env python3
"""P7-1: slide 7 引用1 (Timmermans J Clin Med 2021 TMA) 补体调控应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P7-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P7-1/P7-1_highlight.pdf"

SENTENCES = [
    "Host cells, including the endothelium, are protected from the harmful effects of complement activation by regulatory proteins.",
    "In the late 1980s, complement dysregulation (i.e., factor H deﬁciency) was found in two brothers with (primary atypical) HUS",
    "CFH, CFI, and CD46 variants lead to impaired protein synthesis or function, whereas C3 and CFB variants cause a gain-of-function protein, predisposing to unrestrained complement activation on the endothelium",
    "Host cells, including the endothelium, are protected from the harmful effects of complement activation by factor I, factor H, and CD46 (also known as membrane cofactor protein); these proteins have decay-accelerating and cofactor activities, leading to factor I-mediated cleavage of C3b into inactivated proteins.",
    "C5b can bind C6, C7, C8, and various C9 molecules to form the lytic C5b9 (i.e., membrane attack complex) on cells.",
    "In C-TMA, rare variants in complement genes (i.e., loss of function of factor I, factor H, or CD46 (thin red lines); gain of function of C3 or CFB (green lines)) and/or autoantibodies targeting complement regulatory proteins result in unrestrained complement activation, formation of C5b9 on the endothelium, and a procoagulant environment that triggers thrombosis.",
    "C5 activationon the endothelium leads to the expression and secretion of tissue factor via the insertion of sublytic C5b9",
    "and the interaction of C5a with its receptor",
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
