#!/usr/bin/env python3
"""P11-1: slide 11 引用1 (任宏 中国小儿急救医学 2020 溶血危象) 溶血性贫血应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P11-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P11-1/P11-1_highlight.pdf"

SENTENCES = [
    "溶血性贫血是由于各种原因导致红细胞破坏加速，其严重程度取决于红细胞破坏的速率与骨髓造血代偿能力，从轻度贫血到危及生命的状态，临床表现呈多样性。",
    "溶血危象是危及生命的急性溶血性贫血或慢性溶血性贫血急性加重，以血管内溶血为主，血红蛋白水平急剧下降，黄疸明显加重，出现血红蛋白尿，甚至肾功能衰竭、休克。",
    "溶血尿毒综合征是血栓性微血管病（thrombotic microangiopathies，TMAs）的一种类型",
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
