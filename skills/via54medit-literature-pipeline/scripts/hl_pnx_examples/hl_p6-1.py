#!/usr/bin/env python3
"""P6-1: slide 6 引用1 (Ricklin Nat Rev Nephrol 2018 补体治疗) 疾病应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P6-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P6-1/P6-1_highlight.pdf"

SENTENCES = [
    "Unfortunately, however, vulnerability to erroneous activation and dysregulation renders the complement system an important risk factor for many diseases",
    "Any disruption of this balance that leads to improperly controlled opsonization and effector generation may have severe adverse clinical consequences",
    "Some cells and organs, including the eyes and kidneys, seem to be particularly affected by complement-mediated damage, with implications for diseases ranging from aHUS and C3 glomerulopathy (C3G) to lupus nephritis (LN) and IgA nephropathy.",
    "disorders with known or suspected complement involvement cover an exceptionally broad range, including tissue-speciﬁc, systemic, acute and chronic disorders of the inﬂammatory, autoimmune, age-related, biomaterial-induced and neurodegenerative spectrum",
    "An overwhelming number of activating triggers, such as PAMPs in the case of sepsis or DAMPs in trauma, can lead to systemic inﬂammatory response syndrome (SIRS), in which the severe and sudden reaction of complement and other defence pathways causes homeostatic imbalance, hyper-acute inﬂammation and tissue damage that can lead to organ dysfunction and death.",
    "In transplant-induced and bio-material-induced inﬂammation, complement recognizes non-self surfaces that are exposed to blood or tissue ﬂuid and invokes an appropriate but unwanted response",
    "In addition to acute inﬂammatory conditions, complement drives several chronic disorders, such as PNH, aHUS and age-related macular degeneration (AMD).",
    "Prominent examples of this principle are age-related disorders such as Alzheimer disease, atherosclerosis and AMD",
    "In addition, insufﬁcient clearance of apoptotic cells and/or immune complexes owing to deﬁciencies in early complement components is considered to be a key contributor to autoimmune diseases such as systemic lupus erythematosus (SLE)",
    "Haemolytic uraemic syndrome—aHUS is a rare, severe form of thrombotic microangiopathy (TMA) that is characterized by thrombocytopenia, haemolytic anaemia and acute kidney injury with endothelial lesions that often lead to end-stage renal disease",
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
