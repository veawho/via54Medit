#!/usr/bin/env python3
"""P11-7: slide 11 引用7 (Yerigeri J Multidiscip Healthc 2023 aHUS) 三联征应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P11-7_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P11-7/P11-7_highlight.pdf"

SENTENCES = [
    "Hemolytic uremic syndrome (HUS) is a thrombotic microangiopathy (TMA) deﬁned by the triad of hemolytic anemia, thrombocytopenia, and acute kidney injury.",
    "Thrombotic microangiopathies (TMA) are a constellation of disorders characterized by injury to the endothelium of micro-vessels, resulting sequentially in platelet activation, micro-thrombosis, Coombs-negative hemolytic anemia, and thrombocytopenia.",
    "Diagnosis is dependent on lab values demonstrating hemolytic anemia (hemoglobin <10 g/dL), thrombocytopenia (platelet count <150,000 mm3), and acute kidney injury (AKI).",
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
