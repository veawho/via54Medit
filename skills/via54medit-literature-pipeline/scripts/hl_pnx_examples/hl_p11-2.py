#!/usr/bin/env python3
"""P11-2: slide 11 引用2 (Azoulay Chest 2017 aHUS) MAHA识别应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P11-2_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P11-2/P11-2_highlight.pdf"

SENTENCES = [
    "Thrombotic microangiopathies (TMAs) are a group of disorders characterised by thrombocytopenia, microangiopathic haemolytic anaemia and organ dysfunction in which ischaemic organ injury can occur to the brain, kidneys, heart, pancreas, liver, lungs, eyes and skin.",
    "These conditions have a similar clinical presentation of consumptive thrombocytopenia, mechanical haemolysis and organ failure, although with distinct causes, and are typically associated with thickening and inﬂammation of arterioles and capillaries, detachment and swelling of endothelial cells, subendothelial widening, accumulation of proteins and cellular debris, or platelet thrombi that obstruct the vascular lumen.",
    "Clinical suspicion of a TMA is based on clinical ﬁndings, including microangiopathic haemolytic anaemia, thrombocytopenia, low haptoglobin, elevated lactate dehydrogenase, elevated reticulocytes, fragmented red cells and schistocytes on peripheral blood smear.",
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
