#!/usr/bin/env python3
"""P17-3: slide 17 引用3 (George NEJM 2006 TTP) ADAMTS13机制应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P17-3_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P17-3/P17-3_highlight.pdf"

SENTENCES = [
    "reports describ-ing severe deﬁciency (<5 percent activity) of a von Willebrand factor–cleaving protease, termed “ADAMTS 13” (an acronym for a disintegrin and metalloprotease with thrombospondin-1–like do-mains), in patients with a diagnosis of throm-botic thrombocytopenic purpura but not in pa-tients with a diagnosis of the hemolytic–uremic syndrome.",
    "ADAMTS 13 cleaves the large von Willebrand factor multimers that are synthesized and secreted by endothelial cells.",
    "When ADAMTS 13 is not present, the resulting abnormally large von Willebrand factor multimers in plasma have a greater ability to react with platelets and cause the disseminated platelet thrombi characteristic of thrombotic thrombocytopenic purpura.",
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
