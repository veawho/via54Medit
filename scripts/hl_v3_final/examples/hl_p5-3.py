#!/usr/bin/env python3
"""P5-3: slide 5 引用3 (Figueroa Clin Microbiol Rev 1991) 末端补体应证句 (按P5-3实际文本)"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P5-3_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P5-3/P5-3_highlight.pdf"

SENTENCES = [
    "Assembly of the membrane attack complex. Incorporation of C3b into either the classical- or alternative-pathway C3 convertase creates the respective C5 convertases C4b2aC3b and C3bBbC3b.",
    "Its cleavage results in both the release of C5a, a potent anaphy-latoxin and phagocyte chemoattractant, and the noncovalent deposition of C5b at exposed hydrophobic sites on cell membranes",
    "In this location, C5b serves as the anchor for the formation of the membrane attack complex.",
    "The remainder of the terminal-complement components consti-tuting the membrane attack complex (C6, C7, C8, and C9) (Fig. 1) are structurally homologous amphipathic molecules",
    "C6 and C7 bind to CSb in sequence, creating a stable trimolecular complex, C5b67.",
    "In addition to defective complement-mediated bactericidal activity, serum from C5-deﬁcient persons also fails to sup-port complement-dependent chemotactic responses.",
    "Despite this additional abnormality, individuals with C5 deﬁciency do not differ from other persons with terminal-component defects with respect to the bacterial etiology of systemic infection (>95% Neisseria sp.), the frequency and severity of infection (77% meningitis), or the frequency of recurrent disease",
    "Thus, the ability of C9-deﬁcient sera to support limited meningococcal killing is associated with a 10-fold reduction in the risk of meningococcal disease com-pared with the risk for individuals missing one of the other terminal-complement components, whose sera completely lack the ability to kill meningococci",
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
