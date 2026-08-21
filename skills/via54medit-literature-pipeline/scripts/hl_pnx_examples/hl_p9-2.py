#!/usr/bin/env python3
"""P9-2: slide 9 引用2 (Timmermans J Clin Med 2021) TMA分类应证句 (按slide9重选)"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P9-2_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P9-2/P9-2_highlight.pdf"

SENTENCES = [
    "Thrombotic microangiopathy (TMA) is a rare, potentially life-threatening condition that reﬂects tissue responses to severe endothelial damage caused by distinct disorders, including thrombotic thrombocytopenic purpura and hemolytic uremic syndrome (HUS).",
    "Despite heterogeneity, TMAs typically manifest with consumptive thrombocytopenia, microangiopathic hemolytic anemia, and ischemic organ damage, often affecting the brain and kidneys.",
    "TMAs should be classiﬁed according to etiology to indicate targets for treatment",
    "For example, thrombotic thrombocytopenic purpura is caused by a severe deﬁciency of von Willebrand cleaving protease (also known as a disintegrin and metalloproteinase with thrombospondin type 1 motif, member 13 (ADAMTS13))",
    "Secondary atypical HUS represents the majority of TMAs, that is, ~90%; Shiga toxin-producing E. coli (STEC)-HUS, thrombotic thrombocytopenic purpura (TTP), and primary atypical HUS are responsible for 6%, 3%, and 3% of TMAs",
    "The risk of TMA after kidney transplantation is >36 times higher in patients with C-TMA in the native kidney as compared to those with ESKD due to other causes",
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
        print(f'p{found if found else "?"}: {s[:55]}...')
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
            print(f'NOT FOUND: {s[:55]}')
    doc.close()
    highlight_sentences(PDF, OUT, S)
    print('saved:', OUT)

if __name__ == "__main__":
    if sys.argv[1] == 'test':
        scan()
    else:
        run()
