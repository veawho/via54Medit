#!/usr/bin/env python3
"""P23-8: Lazana I. Transplant-Associated Thrombotic Microangiopathy... IJMS 2023;24:1159
slide 23: HSCT-TMA 发生率/多器官表现/三打击机制"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P23-8_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P23-8/P23-8_highlight.pdf"

SENTENCES = [
    # 发生率: 0.5%-76% (对应 slide "报道的HSCT-TMA发生率范围为1-20")
    "the precise incidence of TA-TMA remains largely unknown, varying between 0.5% and 76% in the allo-HSCT setting, whereas its incidence is slightly lower in the autologous setting",
    # 三特征/多器官 (对应 slide "临床表现复杂，可累及多个器官")
    "TA-TMA is a heterogenous disease, characterized by the triad of endothelial cell activation, complement dysregulation and microvascular hemolytic anemia, which may affect all organs.",
    # 一次打击
    "(1) An underlying predisposition to complement activation or endothelial injury (endothelial vulnerability) (hit 1).",
    # 二次打击
    "(2) A toxic event (such as the conditioning regimen), leading to the secretion of proinflammatory cytokines and procoagulant proteins and the loss of protective mechanisms (such as deple-tion of nitric oxide and vascular endothelial growth factor), that cause endothelial injury and initiate the complement cascade (hit 2).",
    # 三次打击
    "(3) Additional insults (such as infections, drugs/immunosuppressants, etc.) propagate the complement activation, leading to the subsequent microthrombi formation (hit 3).",
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
