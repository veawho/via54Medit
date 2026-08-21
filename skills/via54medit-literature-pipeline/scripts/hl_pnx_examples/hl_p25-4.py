#!/usr/bin/env python3
"""P25-4 = Yerigeri K, et al. J Multidiscip Healthc. 2023;16:2233-2249 (aHUS review)
slide 25 aHUS 列: 核心发病机制(补体旁路失调→MAC→微血栓)、血小板轻-中度减少<150、肾损伤重(AKI)、
ADAMTS13≥10%(通常正常)、补体检测价值低、确诊靠排除TTP/STEC-HUS+基因检测"""
import sys, os
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = '/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P25-4_main.pdf'
OUT = '/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P25-4/P25-4_highlight.pdf'

SENTENCES = [
    # 核心发病机制: 补体旁路失调→补体损伤+微血栓(肾小球毛细血管)
    ("Mutant FH molecules do not bind to the cell surface and, in turn, cannot "
     "regulate alternative complement activation. This leads to complement-induced "
     "damage and microthrombi in the microvasculature, especially the glomerular capillaries."),
    # 血小板减少(轻-中度 <150)+ 肾损伤(AKI) + 溶贫: 诊断三联征
    "Diagnosis is dependent on lab values demonstrating hemolytic anemia (hemoglobin "
    "<10 g/dL), thrombocytopenia (platelet count <150,000 mm3), and acute kidney injury (AKI).",
    # 补体蛋白不是可靠诊断标志物(补体检测价值低)
    "Despite the importance of complement proteins in aHUS pathogenesis, they are not reliable diagnostic markers.",
    # ADAMTS13 活性检测以排除 TTP
    "Urgent measurement of ADAMTS13 activity is indicated to assess for TTP.",
    # 确诊: 基因检测(无突变不排除诊断)
    "The absence of identifiable mutations does not preclude a diagnosis of aHUS.",
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

sentences = build()

ok = highlight_sentences(SRC, OUT, sentences, verbose=True)
sys.exit(0 if ok else 1)
