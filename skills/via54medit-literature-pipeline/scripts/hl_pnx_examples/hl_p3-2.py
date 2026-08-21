#!/usr/bin/env python3
"""P3-2: slide 3 引用2 (Luzzatto Br J Haematol 2020 PNH综述) 应证句逐行 highlight"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, canon_keys, canon

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P3-2_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P3-2/P3-2_highlight.pdf"

S = {
    0: [  # 第1页 Summary
        "In view of the fact that these agents are associated with C3-dependent extravas-cular haemolysis, it is important that a number of inhibitors of the proximal complement pathway are now in the offing and may further improve the life of patients with PNH.",
    ],
    1: [  # 第2页
        "In the 1970s and 1980s, as the complexities of the C cascade and of the C-regulatory proteins were being unravelled, a para-dox emerged.",
    ],
    4: [  # 第5页 Complement inhibitors + Fig 3
        "Anti-C5 therapy in the form of the humanised monoclonal antibody (mAb) eculizumab (Fig 3) has been a life-changer for many patients with PNH.",
        "However, most patients while trea-ted with eculizumab develop C3-mediated opsonisation of red blood cells and consequent extravascular haemolysis (not a feature of untreated PNH).",
        "Fig 3. Anti-complement therapy can target different components of the complement system. Right: a diagram of the complement cascade; Left: drugs currently at various stages of development",
    ],
    5: [  # 第6页
        "This finding has added stimulus to the notion that inter-ference with the function of C3 convertase, upstream of C5 (Fig 3) would result in an even more effective inhibition of the C5-dependent terminal attack complex, without the unwanted side-effect of iatrogenic extravascular haemolysis.",
        "Another approach for C3 inhibition involves targeting of the complement factors D and B (Fig 3) that are required for the convertase function of C3.",
    ],
}

if __name__ == "__main__":
    import fitz
    if sys.argv[1] == 'test':
        doc = fitz.open(PDF)
        for pi, sents in S.items():
            chars, text = page_char_stream(doc[pi])
            for s in sents:
                from hl_lib import locate_sentence
                hit = locate_sentence(text, s) is not None
                print(f'p{pi+1} [{"OK " if hit else "FAIL"}] {s[:50]}...')
        doc.close()
    else:
        report = highlight_sentences(PDF, OUT, S)
        print('saved:', OUT)
