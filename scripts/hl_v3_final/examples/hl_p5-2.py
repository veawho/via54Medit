#!/usr/bin/env python3
"""P5-2: slide 5 引用2 (Skattum Mol Immunol 2011) 末端补体应证句 (按slide5重选)"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P5-2_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P5-2/P5-2_highlight.pdf"

SENTENCES = [
    # p2 Fig1 图注尾部: MAC 形成与裂解
    "All pathways lead to cleavage of C3 into C3a and C3b, which acts as an opsonin. Subsequently C5 is cleaved into C5a, which is an inﬂammatory mediator and C5b, resulting in formation of the membrane attack complex (MAC) C5b–C9 which may lyse Gram-negative bacteria.",
    # p2 正文: MAC 组成
    "The C5b fragment can then form a complex with C6, C7, C8 and a number of C9 molecules creating the membrane attack complex (MAC) C5b–C9 which may lyse Gram-negative bacteria",
    # p3: C5a 炎症
    "Decreased release of C3a and C5a will hamper the inﬂammatory response since these molecules are chemotactic to phagocytic cells and also are anaphylatoxins acting on mast cells and basophil granulocytes to release histamine and other inﬂam-matory mediators leading to increased capillary leakage at the site of inﬂammation.",
    # p4: 末端途径缺陷→奈瑟菌
    "The common clinical feature of human alternative and termi-nal pathway deﬁciencies is markedly increased susceptibility to Neisserial infections.",
    # p5: C5-C9 缺陷
    "Inherited deﬁciencies of each of the terminal complement components C5–C9 have been reported.",
    "Terminal complement component deﬁciency is associated only with meningococcal infec-tion with high recurrence rate, however rarely fatal.",
    "The reason for the milder form of disease is not entirely clear, but it has been argued that lack of membrane attack complex formation both directly and via less induction of LPS release would lead to less inﬂammation normally resulting from bacterial lysis",
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
