#!/usr/bin/env python3
"""P23-18: slide 23 引用18 (Kraft BMT 2019) 应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P23-18_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P23-18/P23-18_highlight.pdf"

SENTENCES = [
    "Transplant-associated thrombotic microangiopathy (TA-TMA) remains a major complication of allogeneic hematopoietic stem cell transplantation (allo-HSCT).",
    "Sixty-ﬁve (9.8%) of these patients matched the established diagnostic criteria for TA-TMA, and TA-TMA was shown to be a relevant independent risk factor for mortality (RR 3.27; 95% CI 2.07–5.16).",
    "Patients with TA-TMA and concomitant aGvHD had a markedly reduced OS compared to patients with TA-TMA or aGvHD alone (median 5.6 months vs. 7.6 months vs. 55.4 months, respectively; p < 0.0001).",
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
