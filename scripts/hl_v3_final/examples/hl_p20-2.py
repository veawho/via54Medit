#!/usr/bin/env python3
"""P20-2: slide 20 引用2 (Liu Toxins 2023 STEC-HUS) 临床特点与诊断应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P20-2_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P20-2/P20-2_highlight.pdf"

SENTENCES = [
    "A STEC infection initially presents with symptoms of hemorrhagic colitis, such as abdominal pain and hemorrhagic diarrhea, and vascular damage can cause hemolytic anemia, thrombosis, and kidney injury",
    "Extrarenal manifestations occur in around 20% of STEC-HUS patients, including hypertension and cardiac, neurological, gastrointestinal, and endocrinal complications, which are associated with an increased risk of death",
    "Clinically, the diagnosis of STEC-HUS mainly relies on prior potential infections or exposure history, corresponding clinical symptoms, and auxiliary examinations that indicate thrombotic microangiopathy, such as nonimmune hemolytic anemia (hematocrit < 30%, with fragmented erythrocytes in peripheral blood smear and a nega-tive Coombs test), thrombocytopenia (platelet count < 150,000 mm3), and abnormal renal function (a serum creatinine concentration that exceeds the upper limit of the reference range for age) with or without hypocomplementemia.",
    "If the occurrence of STEC-HUS is suspected, fecal and serological tests are required to determine whether there is evidence of a STEC infection",
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
