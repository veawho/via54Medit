#!/usr/bin/env python3
"""P19-2: slide 19 引用2 (Fox Intern Med J 2018 澳新TMA共识) 立即ADAMTS13检测应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P19-2_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P19-2/P19-2_highlight.pdf"

SENTENCES = [
    "TMA should be considered in all patients with thrombocytopenia and anaemia, with an immediate request to the haematology laboratory to look for red cell fragments on a blood ﬁlm.",
    "In all adults, urgent, empirical plasma exchange (PE) should be started within 4–8 h of presentation for a possible diagnosis of TTP, pending a result for ADAMTS13 (a disintegrin and metalloprotease thrombospondin, number 13) activity.",
    "A sodium cit-rate plasma sample should be collected for ADAMTS13 testing prior to any plasma ther-apy.",
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
