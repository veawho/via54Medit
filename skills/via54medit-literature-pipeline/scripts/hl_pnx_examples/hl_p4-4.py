#!/usr/bin/env python3
"""P4-4: slide 4 引用4 (Skattum Mol Immunol 2011 补体缺陷感染) 应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P4-4_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P4-4/P4-4_highlight.pdf"

SENTENCES = [
    # p1 Fig 1 图注整段
    "Fig. 1. Schematic presentation of complement activation and anti-microbial defense mechanisms. The lectin pathway (LP) may be initiated by the binding of mannan-binding lectin (MBL) to carbohydrates such as mannose or N-acetyl glucosamine. MBL is present in complex with MBL-associated serine protease (MASP) molecules and binding activates MASP-2 resulting in formation of the C3 convertase C4b2a, which is common to the classical pathway (CP) and the LP. The alternative pathway (AP) starts with binding of hydrolysed C3 (C3(H2O) or C3b which gives rise to the AP C3 convertase C3bBb. Properdin when bound to a surface may initiate AP activation. The AP also serves also as an amplification mechanism of complement activation. Once the adaptive immune defense has been activated specific antibodies can bind to the microorganisms forming binding sites for C1q. The CP activation starts when C1 with multiple binding is bound to IgM or IgG which leads to formation of the C3 convertase C4bC2a. All pathways lead to cleavage of C3 into C3a and C3b, which acts as an opsonin. Subsequently C5 is cleaved into C5a, which is an inflammatory mediator and C5b, resulting in formation of the membrane attack complex (MAC) C5b–C9 which may lyse Gram-negative bacteria.",
    # p2 Section 2
    "The three major activation pathways, the classical (CP), the alternative (AP) and the lectin pathway (LP) are summarized in Fig. 1 with the molecular mechanisms acting against the infection causing microorganism indicated.",
    "Activation leads to covalent anchoring of C4b and C3b to bacterial surfaces, which is critical to the cellular immune response since the complement-opsonized bacteria are taken up by phagocytic cells.",
    "The mechanism is of great importance in the defense against encapsulated bacteria.",
    # p2 C3 deficiency
    "Lack of C3d will impair the antibody responses since C3d is a natural adjuvant, which has been shown in several ways, including in vaccine design",
    "Decreased release of C3a and C5a will hamper the inflammatory response since these molecules are chemotactic to phagocytic cells and also are anaphylatoxins acting on mast cells and basophil granulocytes to release histamine and other inflam-matory mediators leading to increased capillary leakage at the site of inflammation.",
    # p2 receptors
    "Thus, complement-opsonized bacteria and antigens can bind to phagocytic cells by interactions between C3b and complement receptor (CR) 1, iC3b and CR3 and between C3d and CR2 on B cells.",
    # p3 alternative/terminal deficiencies
    "The common clinical feature of human alternative and termi-nal pathway deficiencies is markedly increased susceptibility to Neisserial infections.",
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
