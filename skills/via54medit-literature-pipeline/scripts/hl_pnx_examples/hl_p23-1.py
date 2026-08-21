#!/usr/bin/env python3
"""P23-1: slide 23 引用1 (Jodele Semin Hematol 2018 TA-TMA) 应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P23-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P23-1/P23-1_highlight.pdf"

SENTENCES = [
    "Transplant-associated thrombotic microangiopathy (TA-TMA) is a form of microangiopathy speciﬁcally occurring in the context of hematopoietic stem cell transplantation (HSCT).",
    "Similarly, to other microangiopathies, TA-TMA is characterized by hemolytic anemia, thrombocytopenia, and endothelial injury related organ failure.",
    "reported an overall TA-TMA incidence of 39% (39/100) with 11 of these 39 patients (28%) having high-risk TA-TMA associated with MODS in a 100 patient prospective observational study.",
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
