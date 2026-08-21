#!/usr/bin/env python3
"""P14-1: slide 14 引用1 (Nguyen Crit Care 2006 TAMOF) 血小板减少应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P14-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P14-1/P14-1_highlight.pdf"

SENTENCES = [
    "New onset thrombocytopenia in the critically ill patient has been established as an important independent risk factor for the development of multiple organ failure.",
    "Pro-thrombotic and anti-ﬁbrinolytic responses, which are helpful during focal injury, may be injurious in the setting of systemic endothelial injury and are manifested by thrombo-cytopenia, systemic thrombosis, and multiple organ failure.",
    "Critically ill patients develop systemic endothelial micro-angiopathic disease after many types of systemic insults",
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
