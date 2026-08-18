#!/usr/bin/env python3
"""P14-2: slide 14 引用2 (Brocklebank CJASN 2018 TMA与肾脏) 血小板消耗应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P14-2_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P14-2/P14-2_highlight.pdf"

SENTENCES = [
    "The deﬁning laboratory features comprise thrombocyto-penia, resulting from platelet aggregation and consumption, and MAHA, identiﬁed by evidence of erythrocyte fragmen-tation on peripheral blood ﬁlm microscopy, which occurs in areas of turbulent ﬂow in the microcirculation due to partial occlusion by platelet aggregates",
    "TTP is characterized by unusually large multimers of vWf- and platelet-rich thrombi in capillaries and arterioles",
    "The pathologic ﬁnd-ings reﬂect tissue responses to endothelial injury, in-cluding endothelial swelling and mesangiolysis in active lesions, and double contours of the basement mem-brane in chronic lesions",
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
