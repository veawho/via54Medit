#!/usr/bin/env python3
"""P17-1: slide 17 引用1 (中华血液学杂志 2022 vWD指南) VWF应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P17-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P17-1/P17-1_highlight.pdf"

SENTENCES = [
    "血管性血友病（von Willebrand disease, VWD）是最常见的遗传性出血性疾病。血管性血友病因子（von Willebrand Factor, VWF）基因突变引起血浆VWF 数量减少或质量异常是VWD 的主要致病机制",
    "VWF由血管内皮细胞与巨核细胞合成。VWF的主要作用：①与血小板膜糖蛋白Ⅰb（GPⅠb）及内皮下胶原结合，介导血小板黏附至血管损伤部位；②作为凝血因子Ⅷ（FⅧ）的载体，具有稳定FⅧ的作用。",
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
