#!/usr/bin/env python3
"""P4-3: slide 4 引用3 (West & Kemper Complosome综述) 近端补体应证句 (按slide4重选)"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P4-3_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P4-3/P4-3_highlight.pdf"

SENTENCES = [
    # p1 Abstract - 补体宿主防御
    "The complement system is a recognized pillar of host defence against infection and noxious self-derived antigens.",
    # p2 - C3b调理吞噬 / C3a炎症 / 补体缺陷感染 / C3d-B细胞
    "C3b opsonizes microbes and noxious host cells, which induces scavenger cells to phagocytose and destroy C3b-tagged targets",
    "Receptors for the anaphylatoxins C3a and C5a — C3a receptor (C3aR) and C5aR1 and 2, respectively — are expressed by most host immune and non-immune cells",
    "Stimulation of these receptors induces a range of responses, including activation of the endothelium to support adherence and tissue influx of immune cells, smooth muscle cell contraction, and migration and activation of innate immune cells.",
    "The importance of liver-derived circulating complement to the detection and containment of bloodborne pathogens is under-pinned by the recurrent bacterial infections that affect individuals with deficiencies in either C3 or C5",
    "For example, the iC3b/C3dg/C3d-binding complement receptor 2 (CR2; also known as CD21) is an important co-stimulatory molecule for B cells and lowers the threshold of B cell receptor (BCR) signalling by up to 10,000-fold",
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
        print(f'p{found if found else "?"}: {s[:50]}...')
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
            print(f'NOT FOUND: {s[:50]}')
    doc.close()
    highlight_sentences(PDF, OUT, S)
    print('saved:', OUT)

if __name__ == "__main__":
    if sys.argv[1] == 'test':
        scan()
    else:
        run()
