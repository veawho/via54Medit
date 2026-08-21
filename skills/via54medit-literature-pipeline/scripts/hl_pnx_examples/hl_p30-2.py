#!/usr/bin/env python3
"""P30-2: 固定句子定义, 自动定位页并 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P30-2_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P30-2/P30-2_highlight.pdf"

SENTENCES = [
    '本共识由非典型溶血尿毒综合征多学科共识协作组基于最新的文献和指南制订，讨论了aHUS的发病机制、诊断、鉴别诊断及治疗策略，旨在为中国aHUS的规范化诊疗提供指导和参考。',
    '鉴于我国aHUS治疗尚缺乏规范化流程，为此，非典型溶血尿毒综合征多学科共识协作组积极组织跨学科专家制订本共识，旨在推动我国aHUS的诊断和治疗，以改善患者预后。'
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
