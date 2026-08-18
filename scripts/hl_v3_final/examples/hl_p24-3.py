#!/usr/bin/env python3
"""P24-3: slide 24 引用3 (张赵光 临床医学进展 2022) 应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P24-3_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P24-3/P24-3_highlight.pdf"

SENTENCES = [
    "组织学检查是诊断TA-TMA的金标准，但在移植后患者中操作较为困难。",
    "因此2021 年我国针对TA-TMA 诊断提出了专家共识，其诊断标准为：(1) 乳酸脱氢酶超过正常值上限；(2) 蛋白尿(随机蛋白尿超过正常值上限或随机蛋白尿/肌酐 ≥ 2 mg/mg)；(3) 高血压(年龄 < 18 岁：血压高于同年龄、性别和身高的健康人群血压正常参考值上限；年龄 ≥ 18 岁：血压 ≥ 140/90 mmhg)；(4) 新发的血小板减少(血小板计数 < 50 × 10^9/L 或血小板计数较基线水平减少≥50%)；(5) 新发的贫血(血红蛋白值低于正常参考值下限或输血需求增加)；(6) 微血管病变证据(外周血中存在破碎红细胞或组织标本的病理学结果提示微血管病)；(7) 终末补体活化(血浆sC5b-9 值高于健康人群正常值上限)。",
    "蛋白尿、高血压以及乳酸脱氢酶升高可以作为早期出现TA-TMA 的标志物，尽早进行干预，可改善预后。",
    "当蛋白尿 > 30 mg/dL 和sC5b-9 升高的患者应考虑临床干预",
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
