#!/usr/bin/env python3.11
"""
nct_fetcher.py - ClinicalTrials.gov 数据抓取 → fallback PDF 生成

用户 2026-08-01 实战沉淀 (P30-1 AHELP 修复).

用法:
  python3.11 nct_fetcher.py <NCT_ID> <output.pdf>

  python3.11 nct_fetcher.py NCT02329860 P30-1_fallback_NCT02329860_ClinTrials.pdf
"""
import json
import sys
import urllib.request
from pathlib import Path
from datetime import datetime

import fitz  # PyMuPDF


def fetch_nct_data(nct_id: str) -> dict:
    """从 ClinicalTrials.gov API v2 拉数据."""
    url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}?format=json"
    req = urllib.request.Request(url, headers={"User-Agent": "via54Medit/4.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def extract_ae_table(d: dict) -> tuple:
    """提取 any-grade AE 表 + SAE 表."""
    ae = d.get("resultsSection", {}).get("adverseEventsModule", {})

    any_grade = []
    for e in ae.get("otherEvents", []):
        term = e.get("term", "")
        stats = e.get("stats", [])
        if len(stats) >= 2:
            apa = stats[0]
            pla = stats[1]
            any_grade.append({
                "term": term,
                "apatinib_n": apa.get("numAffected"),
                "apatinib_total": apa.get("numAtRisk"),
                "placebo_n": pla.get("numAffected"),
                "placebo_total": pla.get("numAtRisk"),
            })

    sae = []
    for e in ae.get("seriousEvents", []):
        term = e.get("term", "")
        stats = e.get("stats", [])
        if len(stats) >= 2:
            apa = stats[0]
            pla = stats[1]
            sae.append({
                "term": term,
                "apatinib_n": apa.get("numAffected"),
                "apatinib_total": apa.get("numAtRisk"),
                "placebo_n": pla.get("numAffected"),
                "placebo_total": pla.get("numAtRisk"),
            })

    return any_grade, sae


def build_pdf(nct_id: str, data: dict, out_path: str):
    """生成 4 页 fallback PDF: Info + Any-Grade AE + SAE + PPT-对照."""
    yellow = (1, 0.92, 0)
    any_grade, sae = extract_ae_table(data)
    ps = data.get("protocolSection", {})
    idm = ps.get("identificationModule", {})
    desc = ps.get("descriptionModule", {})
    outcomes = ps.get("outcomesModule", {}).get("primaryOutcomes", [])

    doc = fitz.open()

    def add_text(page, pos, text, size=10, color=(0, 0, 0)):
        return page.insert_text(pos, text, fontsize=size, color=color)

    def new_page():
        return doc.new_page(width=595, height=842)

    # Page 1: Study Info
    page = new_page()
    y = 50
    add_text(page, (40, y), f"{nct_id} - Study Detail", size=18, color=(0, 0, 0.5))
    y += 10
    add_text(page, (40, y), f"Source: ClinicalTrials.gov (posted {idm.get('nctId', '')})", size=10, color=(0.3, 0.3, 0.3))
    y += 25
    add_text(page, (40, y), f"Title: {idm.get('briefTitle', '')}", size=12)
    y += 14
    add_text(page, (40, y), f"NCT ID: {idm.get('nctId', '')}", size=10)
    y += 14
    brief = desc.get("briefSummary", "")
    for line in [brief[i:i+90] for i in range(0, len(brief), 90)]:
        add_text(page, (40, y), line, size=9)
        y += 11
    y += 10
    add_text(page, (40, y), "Primary Outcomes:", size=11)
    y += 14
    for om in outcomes[:3]:
        add_text(page, (40, y), f"  - {om.get('measure', '')}", size=9)
        y += 11

    # Page 2: Any-Grade AE Table
    page = new_page()
    y = 50
    add_text(page, (40, y), f"{nct_id} - Any-Grade AE (frequency >= 5%)", size=16, color=(0, 0, 0.5))
    y += 25
    add_text(page, (40, y), "Term", size=10)
    add_text(page, (220, y), "Apatinib n/N", size=10)
    add_text(page, (330, y), "Placebo n/N", size=10)
    add_text(page, (430, y), "Apatinib %", size=10)
    add_text(page, (520, y), "Placebo %", size=10)
    y += 15
    add_text(page, (40, y), "-" * 100, size=10)
    y += 12

    highlight_terms = {"Hypertension", "Proteinuria", "Protein urine present", "Blood pressure increased"}
    for a in any_grade:
        apa_pct = round(a["apatinib_n"] / a["apatinib_total"] * 100, 1) if a["apatinib_total"] else 0
        pla_pct = round(a["placebo_n"] / a["placebo_total"] * 100, 1) if a["placebo_total"] else 0
        line_y = y
        add_text(page, (40, line_y), a["term"], size=9)
        add_text(page, (220, line_y), f"{a['apatinib_n']}/{a['apatinib_total']}", size=9)
        add_text(page, (330, line_y), f"{a['placebo_n']}/{a['placebo_total']}", size=9)
        add_text(page, (430, line_y), f"{apa_pct}%", size=9)
        add_text(page, (520, line_y), f"{pla_pct}%", size=9)
        if a["term"] in highlight_terms:
            page.draw_line(fitz.Point(40, line_y + 12), fitz.Point(540, line_y + 12),
                           color=yellow, width=2.5)
        y += 12

    # Page 3: SAE
    page = new_page()
    y = 50
    add_text(page, (40, y), f"{nct_id} - Serious AE", size=16, color=(0, 0, 0.5))
    y += 25
    add_text(page, (40, y), "Term", size=10)
    add_text(page, (220, y), "Apatinib n/N", size=10)
    add_text(page, (330, y), "Placebo n/N", size=10)
    add_text(page, (430, y), "Apatinib %", size=10)
    add_text(page, (520, y), "Placebo %", size=10)
    y += 15
    add_text(page, (40, y), "-" * 100, size=10)
    y += 12
    for a in sae[:25]:
        apa_pct = round(a["apatinib_n"] / a["apatinib_total"] * 100, 1) if a["apatinib_total"] else 0
        pla_pct = round(a["placebo_n"] / a["placebo_total"] * 100, 1) if a["placebo_total"] else 0
        add_text(page, (40, y), a["term"], size=9)
        add_text(page, (220, y), f"{a['apatinib_n']}/{a['apatinib_total']}", size=9)
        add_text(page, (330, y), f"{a['placebo_n']}/{a['placebo_total']}", size=9)
        add_text(page, (430, y), f"{apa_pct}%", size=9)
        add_text(page, (520, y), f"{pla_pct}%", size=9)
        y += 12

    # Page 4: PPT 需求对照 (placeholder)
    page = new_page()
    y = 50
    add_text(page, (40, y), "PPT Needs vs NCT Evidence (template)", size=16, color=(0, 0, 0.5))
    y += 25
    add_text(page, (40, y), "(Fill in PPT requirements before generation)", size=10, color=(0.3, 0.3, 0.3))

    doc.save(out_path)
    doc.close()
    print(f"✓ Generated: {out_path}")
    print(f"  pages: 4 (Info + Any-Grade AE + SAE + PPT-对照)")
    print(f"  any-grade AE: {len(any_grade)} 项")
    print(f"  SAE: {len(sae)} 项")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    nct_id = sys.argv[1]
    out_path = sys.argv[2]
    print(f"Fetching {nct_id}...")
    data = fetch_nct_data(nct_id)
    build_pdf(nct_id, data, out_path)


if __name__ == "__main__":
    main()
