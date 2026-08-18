#!/usr/bin/env python3
"""P4-2: slide 4 引用2 (Luzzatto PNH综述) 近端补体应证句 (按slide4重选, 非复制P3-2)"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P4-2_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P4-2/P4-2_highlight.pdf"

SENTENCES = [
    # p1 Summary - 近端补体途径抑制剂
    "In view of the fact that these agents are associated with C3-dependent extravas-cular haemolysis, it is important that a number of inhibitors of the proximal complement pathway are now in the offing and may further improve the life of patients with PNH.",
    # p2 - C级联
    "In the 1970s and 1980s, as the complexities of the C cascade and of the C-regulatory proteins were being unravelled, a para-dox emerged.",
    # p5 - Anti-C5 / C3调理素
    "Anti-C5 therapy in the form of the humanised monoclonal antibody (mAb) eculizumab (Fig 3) has been a life-changer for many patients with PNH.",
    "However, most patients while trea-ted with eculizumab develop C3-mediated opsonisation of red blood cells and consequent extravascular haemolysis (not a feature of untreated PNH).",
    "Fig 3. Anti-complement therapy can target different components of the complement system. Right: a diagram of the complement cascade; Left: drugs currently at various stages of development",
    # p6 - C3转化酶/近端补体抑制剂
    "This finding has added stimulus to the notion that inter-ference with the function of C3 convertase, upstream of C5 (Fig 3) would result in an even more effective inhibition of the C5-dependent terminal attack complex, without the unwanted side-effect of iatrogenic extravascular haemolysis.",
    "John Lambris in the 1990s identified compstatin, a cyclic peptide that inhibits the convertase activity of C3.",
    "In early phase clinical studies, subcutaneously administered pegceta-coplan, a pegylated compstatin analogue, demonstrated effi-cacy equivalent to that of eculizumab and no safety signals in untreated patients with PNH and in those with breakthrough or marked extravascular haemolysis while on eculizumab",
    "Another approach for C3 inhibition involves targeting of the complement factors D and B (Fig 3) that are required for the convertase function of C3.",
    "In a Phase II study, the factor D orally bioavailable inhibitor danicopan in combina-tion with eculizumab showed improvement of anaemia and reduction in blood transfusion requirements in patients with PNH who had inadequate response to C5 monotherapy.",
    "LNP023, a small molecule inhibitor of factor B is also under clinical development.",
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
        print(f'p{found if found else "?"}: {s[:48]}...')
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
            print(f'NOT FOUND: {s[:48]}')
    doc.close()
    highlight_sentences(PDF, OUT, S)
    print('saved:', OUT)

if __name__ == "__main__":
    if sys.argv[1] == 'test':
        scan()
    else:
        run()
