#!/usr/bin/env python3
"""P23-25: slide 23 引用25 (Dandoy TCT 2023) 应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P23-25_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P23-25/P23-25_highlight.pdf"

SENTENCES = [
    "HSCT-TMA was associated with renal dysfunction (odds ratio [OR], 11.04 for adult, allogeneic and 7.35 for pediatric, all transplanta-tions), renal failure (OR, 2.41 for adult and pediatric, allogeneic), renal replacement therapy (OR, 6.99 for pediatric, all transplantations and 60.85 for adult, allogeneic), and hypertension (OR, 5.44 for adult, allogeneic).",
    "HSCT-TMA was asso-ciated with respiratory failure (OR, 8.00 for adult and pediatric, allogeneic), pulmonary hypertension (OR, 9.86 for adult and pediatric, allogeneic), need for pleurocentesis (OR, 5.45 for pediatric, all transplantations), noninvasive ventilation (OR, 6.15 for pediatric, all transplantations), and invasive mechanical ventilation (OR, 5.18 for pediatric, all transplanta-tions).",
    "Additionally, HSCT-TMA was associated with neurologic symptoms (OR, 2.28 for adult and pediatric, allogeneic), pericardial effusion (OR, 2.56 for adult and pediatric, allogeneic and 8.76 for pediatric, all transplantations), liver injury (OR, 3.87 for adult, allogeneic), infection (OR, 9.25 for adult, allogeneic; 2.06 for pediatric, all transplantations), gastroin-testinal (GI) bleeding (OR, 7.78 for adult and pediatric, allogeneic), and acute graft-versus-host disease grade III-IV (OR, 3.29 for adult and pediatric, allogeneic).",
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
