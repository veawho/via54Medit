#!/usr/bin/env python3
"""P15-1: slide 15 引用1 (Nadasdy 肾移植TMA 替代文献) 病因应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P15-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P15-1/P15-1_highlight.pdf"

SENTENCES = [
    "There is increasing evidence that most cases of recurrent TMA in renal allografts are secondary to mutations in genes encoding complement regulatory factors and complement components, such as factor H, factor I, membrane cofactor protein, C3, and others.",
    "Another important cause for recurrent TMA is the presence of autoantibodies, such as antibodies to factor H and antiphospholipid antibodies.",
    "TMA in a renal allog-raft can either be recurrent or de novo",
    "Genetic abnormalities, such as mutations in the genes encoding complement regulatory proteins and complement factors (e.g., factor H, factor I, membrane cofactor protein, and C3), ADAMTS13, coagulation factors (e.g., plas-minogen and thrombomodulin von Willebrand factor), and cobalamine-C deﬁciency",
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
