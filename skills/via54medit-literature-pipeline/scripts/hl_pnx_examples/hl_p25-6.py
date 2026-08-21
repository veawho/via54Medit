#!/usr/bin/env python3
"""P25-6: 固定句子定义, 自动定位页并 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P25-6_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P25-6/P25-6_highlight.pdf"

SENTENCES = [
    'Patients with TTP present with thrombocyto-penia, microangiopathic hemolytic anemia, and various degrees of organ damage.',
    'A plasma ADAMTS13 activity of less than 10 IU/dL (often referred to as 10% of normal ADAMTS13 activity) is the hallmark of TTP; when plasma ADAMTS13 activity is greater than 10 IU/dL, the diagnosis of HUS should be considered after excluding other secondary causes of thrombotic microangiopathy.',
    'The population of interest would therefore be defined as: patients with thrombocytopenia (<100 × 109/L), microangiopathic hemolytic ane-mia (eg, hemoglobin and hematocrit below the lower limit of the ref-erence range, low haptoglobin, elevated lactate dehydrogenase, the presence of schistocytes in peripheral blood smear), and relatively preserved renal function.'
]

def build():
    import fitz
    doc = fitz.open(SRC)
    n = len(doc)
    S = {}
    for s in SENTENCES:
        for pi in range(n):
            chars, text = page_char_stream(doc[pi])
            if locate_sentence(text, s) is not None:
                S.setdefault(pi, []).append(s)
                break
        else:
            print('NOT FOUND:', s[:55])
    doc.close()
    return S

if __name__ == "__main__":
    sentences = build()
    highlight_sentences(SRC, OUT, sentences, verbose=True)
    print('saved:', OUT)
