#!/usr/bin/env python3
"""P3-1: slide 3 (补体系统三大途径) 应证句逐行 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence, norm

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P3-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P3-1/P3-1_highlight.pdf"

S = {
    1: [  # 第2页
        "经典型PNH 一线治疗为补体通路抑制剂,目前C5 补体抑制剂(依库珠单抗、可伐利单抗)及B因子抑制剂(伊普可泮)均在我国获批治疗新诊断PNH,疗效佳者建议规律用药及随访。",
        "补体通路抑制剂的应用是近年来我国PNH 患者治疗取得的最大进展。",
        "以依库珠单抗为代表的远端补体抑制剂应用于PNH 治疗已累积十余年的治疗经验,国外多项临床研究及大型回顾性研究均证实依库珠单抗可减轻慢性溶血、减少输血,显著减少血栓等并发症事件,同时显著改善生活质量,实现生存获益",
    ],
    2: [  # 第3页
        "尽管C5 补体抑制剂开创了PNH 靶向治疗新时代,仍有高达88％接受 C5 补体抑制剂治疗的患者持续性贫血,且一半以上存在输血依赖",
        "近年针对补体通路活化的新药研发成为热点。",
        "伊普可泮作为补体旁路B因子抑制剂的代表,作用于C5 末端通路的上游,不仅可控制PNH 的IVH,还可阻止其EVH。",
        "Pegcetacoplan(Empaveli、APL-2)是C3 靶向抑制剂,可特异性地与补体C3 和C3b 结合,从而控制末端补体介导的IVH 和C3b 介导的EVH,成为首个批准用于成人PNH(美国)、对C5 抑制剂反应不足或不耐受(澳大利亚)及C5 靶向治疗持续时间超过3 个月仍贫血的成人PNH(欧盟)的C3 靶向治疗",
        "补体系统作为机体重要的免疫效应及其链式放大系统,是连接固有免疫和适应性免疫的重要桥梁,在维持机体免疫自稳方面发挥重要作用。",
        "经典途径补体成分缺陷(C1～C4)者易感染荚膜菌,旁路途径和终末途径补体成分缺陷者则主要感染奈瑟菌,尤其是对危及生命的脑膜炎奈瑟菌(N.meningitidis)的易感性增加。",
    ],
    3: [  # 第4页
        "虽然C5 补体抑制剂可通过阻断末端补体激活有效控制IVH,但补体替代途径持续激活,C3 片段持续在GPI缺陷红细胞上积累,并通过肝脾巨噬系统在血管外被破坏,发生EVH。",
        "补体抑制剂通过抑制末端补体活性,降低血管内皮活化;减少凝血酶生成,降低凝血酶-抗凝血酶复合物水平,有效抑制PNH 血栓形成并预防血栓复发,血栓年发生率从7.37/100 例降低至1.07/100 例,显著延长患者生存期",
    ],
}

if __name__ == "__main__":
    import fitz
    # 先只测定位
    if sys.argv[1] == 'test':
        doc = fitz.open(PDF)
        for pi, sents in S.items():
            chars, text = page_char_stream(doc[pi])
            for s in sents:
                loc = locate_sentence(text, s)
                ns = norm(s)
                hit = loc is not None
                print(f'p{pi+1} [{"OK " if hit else "FAIL"}] {ns[:40]}...')
        doc.close()
    else:
        report = highlight_sentences(PDF, OUT, S)
        print('saved:', OUT)
