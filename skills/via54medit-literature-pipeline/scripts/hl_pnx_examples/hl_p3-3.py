#!/usr/bin/env python3
"""P3-3: slide 3 引用3 (West & Kemper Nat Rev Nephrol 2023 补体综述) 应证句逐行 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P3-3_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P3-3/P3-3_highlight.pdf"

S = {
    0: [  # 第1页 Abstract
        "The complement system is a recognized pillar of host defence against infection and noxious self-derived antigens.",
        "Complement is traditionally known as a serum-effective system, whereby the liver expresses and secretes most complement components, which participate in the detection of bloodborne pathogens and drive an inflammatory reaction to safely remove the microbial or antigenic threat.",
    ],
    1: [  # 第2页 Classical functions
        "The human complement system comprises >50 proteins that either cir-culate in blood (specifically, core components and some complement regulators) or lymph, or exist as cell membrane-bound proteins (regula-tors and receptors)",
        "C3 and C5 are major effector molecules that are mostly secreted by the liver in a pro-enzymatic form.",
        "Complement C3 and C5 activation is initiated when one or several activation pathways is triggered by pathogen- or damage-associated molecular patterns (Fig. 1a).",
        "This recognition leads to the formation of C3 and C5 con-vertases, which then cleavage-activate C3 into C3a and C3b, and C5 into C5a and C5b, respectively.",
        "C5b combines with serum C6–C9 to form the membrane attack complex (MAC), which induces direct lytic killing of pathogens or noxious target cells.",
        "C3b opsonizes microbes and noxious host cells, which induces scavenger cells to phagocytose and destroy C3b-tagged targets",
        "Receptors for the anaphylatoxins C3a and C5a — C3a receptor (C3aR) and C5aR1 and 2, respectively — are expressed by most host immune and non-immune cells",
        "The importance of liver-derived circulating complement to the detection and containment of bloodborne pathogens is under-pinned by the recurrent bacterial infections that affect individuals with deficiencies in either C3 or C5",
    ],
    2: [  # 第3页 Fig 1 图注
        "Fig. 1 | The complement system and its functional compartmentalization. a, Circulating liver-produced complement can be activated through three pathways that result in the formation of C3 and C5 convertases, which cleavage-activate C3 into C3a and C3b, and C5 into C5a and C5b, respectively.",
    ],
}

if __name__ == "__main__":
    import fitz
    if sys.argv[1] == 'test':
        doc = fitz.open(PDF)
        for pi, sents in S.items():
            chars, text = page_char_stream(doc[pi])
            for s in sents:
                hit = locate_sentence(text, s) is not None
                print(f'p{pi+1} [{"OK " if hit else "FAIL"}] {s[:55]}...')
        doc.close()
    else:
        report = highlight_sentences(PDF, OUT, S)
        print('saved:', OUT)
