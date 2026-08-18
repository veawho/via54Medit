#!/usr/bin/env python3
"""P4-5: slide 4 引用5 (Heesterbeek J Innate Immun 2018 补体与细菌感染) 应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P4-5_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P4-5/P4-5_highlight.pdf"

SENTENCES = [
    "The main effector functions of complement are driven by the cleavage of 2 central complement proteins: C3 and C5",
    "All recognition path-ways converge in the formation of convertase enzymes on the surface of the bacterium.",
    "First, C3 convertases cleave complement protein C3 to generate C3b that ex-poses a reactive thioester bond; this can covalently attach to hydroxyl groups of carbohydrates on the bacterial sur-face",
    "When C3b molecules are covalently deposited onto the bacterial surface, these efficiently trigger and facilitate phagocytosis by immune cells.",
    "C3b (and its breakdown product, iC3b) are recognized by comple-ment receptors (CR) on myeloid (CR1, CR3, and CR4) and Kupffer cells (CRIg), and enhance the engulfment of opsonized particles, leading to intracellular (microbial) killing",
    "Activation of C5 results in the release of peptide C5a, a strong chemoattractant that helps to recruit phagocytes towards the site of infection and induces an oxidative burst.",
    "Additionally, C5a-mediated stimulation of baso-phils and mast cells triggers the production of histamine and subsequent vasodilatation",
    "The importance of complement in the clear-ance of bacterial infections is clearly illustrated by the recurrent infections in patients with genetic comple-ment deficiencies",
    "b Complement labels bacteria with C3-derived products (C3b and C3bi; green) that stimulate engulf-ment of bacteria by phagocytes. Release of complement peptide C5a is crucial for attraction of phagocytes to the site of infection.",
    "the engulfment of bacterial cells is strongly enhanced in the presence of C3-derived opso-nization",
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
