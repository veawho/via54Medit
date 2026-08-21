#!/usr/bin/env python3
"""P4-1: slide 4 引用1 (PNH中国指南原文) 近端补体应证句逐行 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P4-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P4-1/P4-1_highlight.pdf"

SENTENCES = [
    "经典型PNH 一线治疗为补体抑制剂,可选择依库珠单抗、可伐利单抗、B 因子抑制剂。",
    "近端补体抑制剂使用中发生BTH,使用C5单抗等远端补体抑制剂挽救治疗。",
    "盐酸伊普可泮胶囊(Iptacopan)作为一种靶向B因子的近端补体抑制剂,可选择性抑制旁路途径,同时使凝集素途径和经典途径的直接信号传导保持完整,以控制末端补体介导的IVH 及C3b 介导的血管外溶血(EVH)",
    "新型抗C5 药物本质上不能满足C3 介导的EVH 的临床需求,针对C3 或替代途径(AP)的新型口服抗补体抑制剂逐渐问世,对未经治疗的PNH患者或对补体C5 抑制剂无效或仅部分应答的患者显示出良好效果",
    "Pegetacoplan可控制C5 介导的",
    "IVH,并预防C3 介导的EVH,于2021 年5 月被美国FDA批准治疗成人PNH患者及对C5抑制剂不耐受的PNH患者",
    "补体抑制增加了脑膜炎球菌(奈瑟球菌)感染的风险,所有患者均须在接受补体抑制剂治疗之前至少2 周进行疫苗接种,以降低感染风险,且每3年重复接种1次。",
    "C5补体抑制剂治疗期间,若出现持续贫血加重还需警惕红细胞C3 沉积增加导致的EVH,此时需完善溶血相关指标、Coombs 试验、腹部B 超等检查进行鉴别诊断。",
    "c由于C3调理素沉积导致血管外溶血时可考虑应用;",
    "PNH 患者应用补体抑制剂治疗会增加感染的概率,需接种相关疫苗;一旦合并感染,应积极寻找感染灶和病原体,并给予针对性抗感染治疗。",
    "流式细胞术或Coombs 试验检测C5 抑制剂治疗后红细胞膜表面C3片段沉积可作为EVH评价指标。",
]

def scan():
    """在所有页面中定位每个句子, 输出页面号"""
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
        print(f'p{found if found else "?"}: {s[:40]}...')
    doc.close()

def run():
    # 先扫描确定页面
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
            print(f'NOT FOUND: {s[:40]}')
    doc.close()
    report = highlight_sentences(PDF, OUT, S)
    print('saved:', OUT)

if __name__ == "__main__":
    if sys.argv[1] == 'test':
        scan()
    else:
        run()
