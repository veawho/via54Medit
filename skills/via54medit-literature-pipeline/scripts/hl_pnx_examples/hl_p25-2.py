#!/usr/bin/env python3
"""P25-2: slide 25 引用2 (aHUS共识2025) aHUS鉴别应证句 (按slide25重选)"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P25-2_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P25-2/P25-2_highlight.pdf"

SENTENCES = [
    "TMA的临床表现主要包括微血管病性溶血性贫血（MAHA）、血小板减少和多器官损伤，包括肾、脑、眼、心脏、胃肠系统等器官，而aHUS以肾脏受累最为显著",
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
