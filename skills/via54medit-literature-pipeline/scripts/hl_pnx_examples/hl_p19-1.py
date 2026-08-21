#!/usr/bin/env python3
"""P19-1: slide 19 引用1 (Sukumar J Clin Med 2021 TTP) ADAMTS13检测应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P19-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P19-1/P19-1_highlight.pdf"

SENTENCES = [
    "Assaying the ADAMTS13 activity is the ﬁrst test which should be undertaken in pa-tients with a suspected TMA.",
    "Severe ADAMTS13 deﬁciency, which is deﬁned by an activity level <10%, is required to conﬁrm the diagnosis of TTP",
    "Congenital TTP, also known as Upshaw–Schulman syn-drome or hereditary TTP, is deﬁned by a persistent severe deﬁciency (<10%) in ADAMTS13 caused by biallelic pathogenic mutations in the ADAMTS13 gene",
    "Immune-mediated TTP, sometimes referred to as acquired TTP, is caused by ADAMTS13 deﬁciency mediated by autoantibodies",
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
