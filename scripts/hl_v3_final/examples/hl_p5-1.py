#!/usr/bin/env python3
"""P5-1: slide 5 引用1 (Kirschfink 德语书章) 末端补体应证句"""
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, locate_sentence, page_char_stream

PDF = "/Users/david/Desktop/TMA_文献整理/step3_pdf下载_106目录/P5-1_main.pdf"
OUT = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI/P5-1/P5-1_highlight.pdf"

SENTENCES = [
    "Jeder dieser auf unterschiedliche Weise initiierten Aktivierungswege mündet in eine gemeinsame Endstrecke, die mit der Bildung der sogenannten C3-Konvertase beginnt und über Zwischenstufen zum lytischen Membranangriffskomplex (membrane-attack complex, MAC) führt",
    "Alle drei Komplementaktivierungswege haben nach der C3-Aktivierung eine gemeinsame Endstrecke, die mit der Bildung des lytischen Membranangriffskomplexes (MAC) abschließt.",
    "Dieser setzt sich zusammen aus je einem Molekül C5b, C6, C7, C8 und bis zu 18 Molekülen C9 und hat die Form eines Kanals, der sich in die Lipiddoppelschicht der Zellmembran einlagert.",
    "Wenn eine ausreichende Anzahl an Poren an der Zellmembran gebildet wird, geht die Zelle durch Lyse zugrunde.",
    "Für Erythrozyten ist die Bildung von nur einer Pore schon ausreichend, um die Zellintegrität zu zerstören, was sich u. a. in Erkrankungen wie der paroxysmalen nächtlichen Hämoglobinurie (PNH) widerspiegelt",
    "Die nach Spaltung der dritten bzw. fünften Komponente freigesetzten Anaphylatoxine C3a und C5a zählen zu den stärksten Entzündungsmediatoren.",
    "Bei Patienten mit C5-C8-Defekten ist das Risiko einer Meningokokkenerkrankung gegenüber der Normalbevölkerung 1000- bis 10.000-fach erhöht",
    "Ein weiterer Defekt, der schon in partieller Ausprägung zu rezidivierenden Neisserieninfektionen führt, ist der des Regulators Properdin.",
    "Sie umfassen je nach nationaler Studie ca. 5–10 % aller primären Immundefekte und sind insbesondere beim Fehlen von C3–C8 mit rezidivierenden Infektionen verbun-den.",
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
