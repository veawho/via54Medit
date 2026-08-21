#!/usr/bin/env python3
"""P20-1: slide 20 引用1 (Henrique Front Cell Infect Microbiol 2022) STEC应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P20-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P20-1/P20-1_highlight.pdf"

SENTENCES = [
    "Shiga toxin-producing Escherichia coli (STEC) is a family of bacteria that share the possibility to secrete Stx.",
    "STEC are foodborne pathogens that may colonize and damage the human colon, where they secrete Stx that gain access to the bloodstream and damage different target organs: mainly kidney and brain.",
    "Indeed, STEC infection may develop hemolytic uremic syndrome (HUS) because of Stx in the target organs.",
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
