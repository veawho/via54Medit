#!/usr/bin/env python3
"""P25-5: 固定句子定义, 自动定位页并 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P25-5_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P25-5/P25-5_highlight.pdf"

SENTENCES = [
    'A disintegrin and metalloproteinase with a thrombospondin type 1 motif member 13 (ADAMTS13) activity was evaluated by the application of the fluorogenic substrate FRETS-VWF73',
    'All acute phase-TMA patients presented with laboratory signs of hemolysis and thrombocytopenia (<150 G/L), with the lowest median platelet count (i.e., 16 G/L) in the TTP subgroup.',
    'Laboratory signs of kidney damage were also absent in 70% of the TTP patients, while most patients with other forms of TMA presented with a varying degree of kidney injury.'
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
