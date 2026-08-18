#!/usr/bin/env python3
"""P30-1: 固定句子定义, 自动定位页并 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P30-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P30-1/P30-1_highlight.pdf"

SENTENCES = [
    'Thrombotic microangiopathy (TMA), a pathologic de-scription, is characterized by a clinical presentation with thrombocytopenia, microangiopathic hemolytic anemia (MAHA), and organ injury',
    'Current classifications describe primary TMAs, known as either acquired (e.g., factor H (FH) autoantibodies, ADAMTS13 autoantibodies) or inherited (e.g., complement mutations, ADAMTS13 mutations); secondary TMAs; and infection-associated TMAs',
    'In summary, TMA can manifest in a diverse range of diseases and can be associated with significant morbidity and mortality.'
]

def build():
    import fitz
    doc = fitz.open(SRC)
    n = len(doc)
    S = {}
    for s in SENTENCES:
        for pi in range(n):
            chars, text = page_char_stream(doc[pi])
            if locate_sentence(text, s) is not None:
                S.setdefault(pi, []).append(s)
                break
        else:
            print('NOT FOUND:', s[:55])
    doc.close()
    return S

if __name__ == "__main__":
    sentences = build()
    highlight_sentences(SRC, OUT, sentences, verbose=True)
    print('saved:', OUT)
