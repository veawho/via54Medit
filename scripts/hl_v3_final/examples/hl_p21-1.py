#!/usr/bin/env python3
"""P21-1: slide 21 引用1 (Praga Kidney Int 2019 aHUS) 二次打击机制应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P21-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P21-1/P21-1_highlight.pdf"

SENTENCES = [
    "However, differentiation may be difﬁcult in clinical practice considering that triggering factors like infections or drugs are frequently identiﬁed in pa-tients with primary aHUS and that in an important proportion (40%–60% in most cohorts) of primary aHUS patients, no complement genetic ab-normalities or autoantibodies against complement regulators are found.",
    "In primary atypical hemolytic uremic syndrome (aHUS), dysregulation and hyperactivity of complement alternative pathway (AP), caused by pathogenic variants in complement genes or anti-factor H autoantibodies, result in an excessive formation of C5b-9 (membrane attack complex [MAC]) that injures vascular endothelial cell (EC) surfaces initiating thrombotic microangiopathy (TMA).",
    "In secondary hemolytic uremic syndrome (HUS), TMA is caused by drugs, infectious agents, immune complexes, antibodies, and proinﬂammatory/procoagulant cytokines that directly damage EC.",
    "Genetic abnormalities or autoantibodies are not found in secondary HUS, but the activated procoagulant and proinﬂammatory phenotype of EC characteristic of TMA can induce a “second-hit” complement activation that perpetuates and aggravates TMA.",
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
