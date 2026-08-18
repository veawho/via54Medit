#!/usr/bin/env python3
"""P9-1: slide 9 引用1 (George NEJM 2014 TMA) 遗传/获得性分类应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P9-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P9-1/P9-1_highlight.pdf"

SENTENCES = [
    "The thrombotic microangiopathy (TMA) syndromes are extraordinarily diverse.",
    "They may be hereditary or acquired.",
    "Despite their diversity, TMA syndromes are united by common, deﬁning clinical and pathological features.",
    "The clinical features include microangiopathic hemolytic anemia, thrombocytopenia, and organ injury.",
    "The pathological features are vascular damage that is manifested by arteriolar and capillary thrombosis with characteristic abnormalities in the en-dothelium and vessel wall.",
    "we retain the common names of thrombotic thrombocytopenic purpura (TTP) for ADAMTS13 deﬁciency–mediated TMA and the hemolytic–uremic syndrome for Shiga toxin–mediated TMA (ST-HUS) because these names are familiar.",
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
