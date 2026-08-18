#!/usr/bin/env python3
"""P8-1: slide 8 引用1 (Laurence Clin Adv Hematol Oncol 2016 aHUS) TMA三联征应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P8-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P8-1/P8-1_highlight.pdf"

SENTENCES = [
    # 摘要
    "aHUS results from chronic, uncontrolled activity of the alternative complement pathway, which activates platelets and damages the endothelium.",
    "The signs and symptoms of all the TMAs overlap, complicating the differential diagnosis.",
    "Clinical identiﬁcation of a TMA requires documentation of micro-angiopathic hemolysis accompanied by thrombocytopenia.",
    # 正文 TMA 识别
    "clinical recognition of a TMA involves documentation of the principle laboratory criteria for microangiopathic hemolytic anemia—schistocytes on peripheral blood smear, elevated LDH, low haptoglobin, elevated indirect bilirubin, and a decline in baseline hemoglobin—accompanied by thrombocytopenia.",
    # 末端补体后果
    "The consequences are massive terminal complement pathway activation with generation of C5a (a potent anaphylatoxin) and C5b-9 (known as membrane attack complex [MAC]), triggering inﬂammation, platelet activation, platelet aggregation, erythrocyte lysis, endothelial cell injury, and ﬁbrin microthrombus formation throughout the microvasculature",
    # two-thirds 诱因
    "In approximately two-thirds of aHUS cases, the TMA is manifested by a recognized complement-activating condition, which causes endothelial cell damage in concert with complement activation, in a person with the congenital inability to control complement.",
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
