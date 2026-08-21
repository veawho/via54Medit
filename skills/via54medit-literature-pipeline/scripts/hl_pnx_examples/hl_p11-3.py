#!/usr/bin/env python3
"""P11-3: slide 11 引用3 (Brodsky Blood 2014 PNH) 溶血性贫血应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P11-3_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P11-3/P11-3_highlight.pdf"

SENTENCES = [
    "Paroxysmal nocturnal hemoglobinuria (PNH) is a clonal hemato-poietic stem cell disorder that manifests with hemolytic anemia, bone marrow failure, and thrombosis.",
    "The absence of two glycosylphos-phatidylinositol (GPI)-anchored proteins, CD55 and CD59, leads to uncontrolled complement activation that accounts for hemolysis and other PNH manifestations.",
    "Abdominal pain, esophageal spasm, dysphagia, and erectile dys-function are common symptoms associated with classical PNH and are a direct consequence of intravascular hemolysis and the release of free hemoglobin.",
    "Eculizumab, a ﬁrst-in-class monoclonal antibody that inhibits terminal complement, is the treatment of choice for patients with severe manifes-tations of PNH.",
    "Free hemoglobin is a potent NO scavenger; the 2 molecules undergo a fast and irreversible reaction that results in the production of nitrate and methemoglobin.",
    "The deﬁciency of NO as a result of scavenging by free hemoglobin contributes to deregulation of smooth muscle tone and platelet activation.",
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
