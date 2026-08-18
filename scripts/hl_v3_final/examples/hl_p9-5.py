#!/usr/bin/env python3
"""P9-5: slide 9 引用5 (aHUS多学科共识 2025) aHUS应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P9-5_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P9-5/P9-5_highlight.pdf"

SENTENCES = [
    "非典型溶血尿毒综合征（aHUS）是一种以微血管病性溶血性贫血、血小板减少和多器官损伤为特征的血栓性微血管病，肾脏受累最为显著。",
    "aHUS主要由补体旁路途径调控异常引起，触发因素包括感染、妊娠、手术等。",
    "目前认为aHUS是先天性或获得性补体旁路途径调控异常所致的TMA",
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
        print(f'p{found if found else "?"}: {s[:45]}...')
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
            print(f'NOT FOUND: {s[:45]}')
    doc.close()
    highlight_sentences(PDF, OUT, S)
    print('saved:', OUT)

if __name__ == "__main__":
    if sys.argv[1] == 'test':
        scan()
    else:
        run()
