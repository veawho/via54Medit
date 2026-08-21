#!/usr/bin/env python3
"""P22-2: slide 22 引用2 (Azoulay Chest 2017) aHUS识别应证句 (按slide22重选)"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P22-2_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P22-2/P22-2_highlight.pdf"

SENTENCES = [
    "Once suspicion of TMA has been established, further investigations, including a full patient medical and family history, are required to exclude other potential causes of TMA, including TTP, STEC-HUS, or TMA as a transient manifestation of another condition (eg, malignancy, autoimmune disease)",
    "The most critical and urgent differential diagnosis is to differentiate TTP from aHUS because of the urgency of speciﬁc treatment.",
    "Testing for ADAMTS13 (a disintegrin and metalloproteinase with thrombospondin motifs 13) activity is recommended to differentiate between TTP and aHUS",
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
