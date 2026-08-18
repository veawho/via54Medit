#!/usr/bin/env python3
"""P23-19: slide 23 引用19 (Li BBMT 2019) 应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P23-19_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P23-19/P23-19_highlight.pdf"

SENTENCES = [
    "Among 2145 patients in this study, 192 developed TA-TMA with a cumulative incidence of 7.6% by 100 days post-transplant.",
    "Among TA-TMA patients 27% achieved hematologic resolution and 57% remained alive as of 90 days after diagnosis.",
    "Independent pretransplant risk factors included the receipt of a second (or third) allogeneic HCT, HLA-mismatched donor, and myeloablative conditioning with or without total body irradia-tion; post-transplant risk factors included the antecedent development of acute graft-versus-host disease, diffuse alveolar hemorrhage, bacteremia, invasive aspergillosis, BK viremia, and higher sirolimus trough level.",
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
