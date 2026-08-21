#!/usr/bin/env python3
"""P15-2: slide 15 引用2 (Prasad Pediatr Nephrol 2020) TMA病因分类应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P15-2_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P15-2/P15-2_highlight.pdf"

SENTENCES = [
    "Primary hereditary TMA (thrombotic thrombocyto-penic purpura (TTP) secondary to ADAMTS13 mu-tation, atypical hemolytic-uremic syndrome (aHUS) due to a complement gene mutation, diacylglycerol kinase epsilon (DGKE) TMA, Cobalamin C deﬁciency);",
    "Primary acquired TMA (TTP with ADAMTS13 au-toantibody, aHUS with Factor H autoantibody);",
    "Secondary TMA post solid-organ transplant, post hematopoietic stem cell transplant, drug-induced, pregnancy and HELLP (syndrome of hemolysis, el-evated liver enzymes, and low platelets) associated, glomerular disease associated with ANCA-associated vasculitis/membranous nephropathy/IgA nephropathy/C3 glomerulopathy etc., hypertension associated, autoimmune disease associated, i.e., with systemic lupus erythematosus (SLE), antiphospholipid antibody syndrome, and malignancy-associated TMA); and",
    "Infection-associated TMA (Shiga toxin-producing Escherichia coli-HUS (STEC-HUS), pneumococcal HUS, HIV associated, and other associated infections).",
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
