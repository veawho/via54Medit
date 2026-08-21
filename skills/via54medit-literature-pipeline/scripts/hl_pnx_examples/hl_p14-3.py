#!/usr/bin/env python3
"""P14-3: slide 14 引用3 (Thompson Int J Lab Hematol 2022 TMA) 血小板消耗应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P14-3_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P14-3/P14-3_highlight.pdf"

SENTENCES = [
    "where vessels are occluded by platelet rich thrombi leading to throm-bocytopenia and microangiopathic haemolytic anaemia (MAHA).",
    "Thrombocytopenia, MAHA, and end organ damage are the common elements of all TMAs.",
    "Thrombocytopenia is due to platelet aggregation and thrombi formation.",
    "MAHA is caused by red blood cell fragmentation in the microvasculature, with schisto-cytes seen on peripheral blood ﬁlm.",
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
