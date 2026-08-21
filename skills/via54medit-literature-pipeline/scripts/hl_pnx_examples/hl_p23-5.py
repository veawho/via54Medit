#!/usr/bin/env python3
"""P23-5: slide 23 引用5 (Dvorak Front Pediatr 2019) 三次打击应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P23-5_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P23-5/P23-5_highlight.pdf"

SENTENCES = [
    "Transplant-associated thrombotic microangiopathy (TA-TMA) is an endothelial damage syndrome that is increasingly identiﬁed as a complication of both autologous and allogeneic hematopoietic cell transplantation (HCT) in children.",
    "The pathophysiology of TA-TMA is complex, resulting from a cycle of activation of endothelial cells to produce a pro-coagulant state, along with activation of antigen-presenting cells and lymphocytes, as well as activation of the complement cascade and microthrombi formation.",
    "This has led to the formulation of a “Three-Hit Hypothesis” in which patients with either an underlying predisposition to complement activation or pre-existing endothelial injury (Hit 1) undergo a toxic conditioning regimen causing endothelial injury (Hit 2), and then additional insults are triggered by medications, alloreactivity, infections, and/or antibodies (Hit 3).",
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
