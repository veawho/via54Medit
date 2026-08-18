#!/usr/bin/env python3
"""P9-3: slide 9 引用3 (戴艳玲 中华医学杂志 2018) TMA分类应证句 (含PDF编码)"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P9-3_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P9-3/P9-3_highlight.pdf"

SENTENCES = [
    "血栓性微血管病#?@A$是由各种原因所致的一组以微血管病性溶血性贫血#@ABA$'血小板减少'缺血性器官受累为特征的急性临床病理综合征",
    "则将?@A分为原发性?@A'感染相关?@A和继发性?@A%其中原发性?@A又分为遗传性和获得性?@A%前者因基因突变致病%包括原发性-BCD'遗传性??E等%后者存在自身抗体%包括继发性-BCD'继发性??E",
    "临床上将??E分为遗传性#先天性$和获得性??E",
    "获得性??E又可分为特发性与继发性??E%特发性??E多因体内存在A!A@?D$' 自身抗体#酶抑制物$导致A!A@?D$' 活性下降#活性[$%P$%",
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
        print(f'p{found if found else "?"}: {s[:50]}...')
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
            print(f'NOT FOUND: {s[:50]}')
    doc.close()
    highlight_sentences(PDF, OUT, S)
    print('saved:', OUT)

if __name__ == "__main__":
    if sys.argv[1] == 'test':
        scan()
    else:
        run()
