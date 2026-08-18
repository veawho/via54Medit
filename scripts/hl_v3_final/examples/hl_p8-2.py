#!/usr/bin/env python3
"""P8-2: slide 8 引用2 (Palma Kidney Int Rep 2021 继发TMA) TMA三联征应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P8-2_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P8-2/P8-2_highlight.pdf"

SENTENCES = [
    "Thrombotic microangiopathy (TMA) is a condition characterized by thrombocytopenia and micro-angiopathic hemolytic anemia (MAHA) with varying degrees of organ damage in the setting of normal international normalized ratio and activated partial thromboplastin time.",
    "or secondary TMA, when complement activation occurs in the context of other disease processes, such as infection, malignant hypertension, autoimmune disease, malignancy, trans-plantation, pregnancy, and drugs",
    "Although microthrombi in tissue specimens, mainly kidney biopsies, is the hallmark of TMA (Figure 1), TMA is often inferred from the observation of thrombocytopenia and MAHA in the appropriate clinical setting.",
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
