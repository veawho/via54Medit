#!/usr/bin/env python3
"""P11-4: slide 11 引用4 (浙江医学 2025 PNH共识) PNH症状应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P11-4_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P11-4/P11-4_highlight.pdf"

SENTENCES = [
    "阵发性睡眠性血红蛋白尿症（PNH）是一种中青年高发病率的后天获得性罕见溶血性疾病，以血管内溶血、潜在的骨髓造血功能衰竭和血栓形成为主要临床特征，严重影响患者的生活质量，甚至导致死亡。",
    "血管内溶血是PNH主要临床特点，患者伴发如贫血、疲劳、血栓、腹痛、胸痛和肾功能不全等临床表现",
    "（3）不明原因的吞咽困难、腹痛或勃起功能障碍，伴有溶血证据；",
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
