#!/usr/bin/env python3
"""P4-6: slide 4 引用6 (Figueroa Clin Microbiol Rev 1991 补体缺陷感染) 应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P4-6_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P4-6/P4-6_highlight.pdf"

SENTENCES = [
    "These individuals exhibit pro-found defects in complement-mediated functions as a con-sequence of the crucial position of C3 in the complement cascade and the resultant inability to use either the classical or the alternative pathway.",
    "Impaired immune complex sol-ubilization, altered immune responses, defective comple-ment-dependent opsonophagocytosis and chemotaxis, and absent complement-dependent bactericidal activity contrib-ute to the clinical manifestations of this condition",
    "Typically, these infections are recurrent and severe; involve the sinopulmonary tree, meninges, and bloodstream; and are caused by encapsulated bacteria including Neisseria meningitidis, Streptococcus pneumoniae, and H. influenzae",
    "By comparison, 70% of individuals with primary or secondary C3 deficiency acquire systemic disease.",
    "In addition, opsonization of these infectious agents by antibodies and complement leads to more efficient ingestion and killing of the organisms by phagocytic cells than does opsonization with either system alone.",
    "In vitro studies have dem-onstrated that these cells can synthesize sufficient amounts of the complement proteins to promote opsonization, inges-tion, and killing of bacteria or other target cells",
    "Individuals with C3 deficiency are unable to recruit any complement-dependent functions, but vaccination may enhance complement-independent, antibody-mediated phagocytic killing.",
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
