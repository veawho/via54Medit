#!/usr/bin/env python3
"""P23-22: slide 23 引用22 (Chen Eur Radiol 2012) 应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P23-22_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P23-22/P23-22_highlight.pdf"

SENTENCES = [
    "A total of 128 patients had brain imaging in the ﬁrst post-HSCT year.",
    "Forty one of these 128 patients (32 %) had structural abnormalities on brain imaging: cerebrovascular complications (n010), central nervous system (CNS) infec-tion (n09), subdural ﬂuid collection (n06), CNS recurrence of haematological malignancy (n011), and drug toxicity abnormalities (n05).",
    "HSCT patients with cerebrovascular complica-tions have poor survival (P<0.05).",
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
