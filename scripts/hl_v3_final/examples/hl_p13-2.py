#!/usr/bin/env python3
"""P13-2: slide 13 引用2 (Martinez BMT 2005 TAM) 裂红细胞与预后应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P13-2_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P13-2/P13-2_highlight.pdf"

SENTENCES = [
    "TAM is deﬁned as evidence of hemolysis and schistocytes in the ﬁrst 100 days.",
    "In patients with TAM, 1-year survival was lower than in patients without TAM (27718% for TAM with high schistocyte counts; 53715% for TAM with low schistocyte counts; vs 7877% in patients without TAM; Po0.0001).",
    "Given the uncertainty of diagnosis of TAM we used evidence of hemolysis, and of red cell fragmentation to deﬁne TAM for this study.",
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
