#!/usr/bin/env python3
"""P9-4: slide 9 引用4 (中华血液学杂志 2021 移植相关TMA共识) TA-TMA应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P9-4_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P9-4/P9-4_highlight.pdf"

SENTENCES = [
    "TA-TMA根据确诊时间，分为早发型TA-TMA（确诊于移植后100 d内）和迟发型TA-TMA（确诊于移植后100 d以后）两种类型",
    "目前认为预处理、免疫抑制剂、补体、感染、移植物抗宿主病（GVHD）、炎性细胞因子（TNF-α、IL-8等）和中性粒细胞胞外诱捕网（NET）等引起血管内皮细胞损伤，导致微血栓形成，最终引发TA-TMA",
    "二次打击是指在移植后造血重建阶段，在钙调磷酸酶抑制剂（CNI）和雷帕霉素靶蛋白（mTOR）抑制剂、GVHD 和感染等危险因素作用下，造成血管内皮细胞损伤，补体系统的异常活化在TA-TMA的发生中发挥重要作用，补体活化的经典途径参与了直接的血管内皮损伤，损伤的血管内皮激活了补体活化的旁路途径并介导了血管内皮的再损伤。",
    "最终，血小板聚集和微血栓形成导致了TA-TMA的发生",
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
        print(f'p{found if found else "?"}: {s[:45]}...')
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
            print(f'NOT FOUND: {s[:45]}')
    doc.close()
    highlight_sentences(PDF, OUT, S)
    print('saved:', OUT)

if __name__ == "__main__":
    if sys.argv[1] == 'test':
        scan()
    else:
        run()
