#!/usr/bin/env python3
"""P13-1: slide 13 引用1 (替代: Cureus 2026 流感相关TMA) 血涂片应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P13-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P13-1/P13-1_highlight.pdf"

SENTENCES = [
    "Thrombotic microangiopathy (TMA) is a life-threatening syndrome characterized by microangiopathichemolytic anemia, thrombocytopenia, and end-organ injury resulting from widespread microvascularthrombosis.",
    "Peripheral blood smear demonstrated two+ schistocytes, conﬁrming microangiopathic hemolysis.",
    "TMA is a syndrome characterized by the triad of thrombocytopenia, microangiopathic hemolytic anemia, and organ damage resulting from platelet-rich thrombi in the microvasculature.",
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
