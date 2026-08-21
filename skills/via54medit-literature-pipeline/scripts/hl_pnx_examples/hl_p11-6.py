#!/usr/bin/env python3
"""P11-6: slide 11 引用6 (Cappellini Lancet 2008 G6PD) G6PD应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P11-6_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P11-6/P11-6_highlight.pdf"

SENTENCES = [
    "The most frequent clinical manifestations of G6PD deﬁ ciency are neonatal jaundice, and acute haemolytic anaemia, which is usually triggered by an exogenous agent.",
    "neonatal jaundice and acute haemolytic anaemia, which in most patients is triggered by an exogenous agent.",
    "A pathological disorder linked to ingestion of fava beans (Vicia faba), later identiﬁ ed as G6PD deﬁ ciency, has been recognised for centuries.",
    "At the beginning of the 20th century, several doctors in southern Italy and Sardinia drew a clinical picture of so-called favism.",
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
