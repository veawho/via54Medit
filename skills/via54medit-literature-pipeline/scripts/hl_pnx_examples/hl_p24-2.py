#!/usr/bin/env python3
"""P24-2: slide 24 引用2 (中华血液学杂志 2021 TA-TMA共识) 应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P24-2_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P24-2/P24-2_highlight.pdf"

SENTENCES = [
    "TA-TMA 的早期诊断：①高血压；②蛋白尿；③LDH 升高。这三项指标在TA-TMA 诊断前即可发生，可作为早期诊断指标指导早期干预，改善预后",
    "其中，蛋白尿和补体sC5b-9 升高的TA-TMA 患者预后较差（1 年生存率＜20％）",
    "满足TA-TMA 诊断标准且包含以下3 条中的2 条：①随机尿蛋白/肌酐≥2 mg/mg；②血浆sC5b-9水平超过正常参考值上限；③多器官功能衰竭综合征（MODS）。",
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
