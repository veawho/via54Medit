#!/usr/bin/env python3
"""
find_replacements_v2.py — 找剩下 8 个 TMA WRONG_PDF 的替代

策略:
1. 用 PubMed 搜每 Pn-x 的替换 (按 PPT 标号内容)
2. 优先 OA 候选 + DOI
3. 用 Sci-Hub 下载
"""
import os, sys, json, time, re
import urllib.request
import urllib.parse
from xml.etree import ElementTree as ET

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
EMAIL = "research@minimax.dev"


def esearch(term: str, retmax: int = 5) -> list:
    url = f"{EUTILS}/esearch.fcgi?db=pubmed&term={urllib.parse.quote(term)}&retmax={retmax}&retmode=json&email={EMAIL}&sort=relevance"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read().decode())
        return data.get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        return []


def esummary(pmids: list) -> list:
    if not pmids:
        return []
    url = f"{EUTILS}/esummary.fcgi?db=pubmed&id={','.join(pmids)}&retmode=json&email={EMAIL}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read().decode())
        result = data.get("result", {})
        return [result[u] for u in result.get("uids", []) if u in result]
    except Exception:
        return []


def get_doi(pmid: str) -> str:
    pmids = [pmid]
    s = esummary(pmids)
    if s:
        for aid in s[0].get("articleids", []):
            if aid.get("idtype") == "doi":
                return aid.get("value", "")
    return ""


# 8 个剩余的 TMA WRONG_PDF (按 vision verify 报告)
# ppt_content 来自 citation_table.csv D 列
TARGETS = [
    ("P4-5", "近端补体活化产物主要参与免疫复合物的清除和微生物的调理吞噬作用4-6",
     "complement opsonin clearance immune complex"),
    ("P12-2", "血小板减少是由于破坏增强所致",
     "thrombocytopenia destruction MAHA schistocyte blood smear"),
    ("P15-1", "引起TMA的病因众多,包括原发性病变或因感染、自身免疫疾病等因素引起的继发性病变;部分患者为特发性",
     "TMA thrombotic microangiopathy etiology classification review"),
    ("P17-1", "血栓性血小板减少性紫癜(TTP),是由于血管性血友病因子(vWF)裂解酶(ADAMTS13)活性缺乏",
     "TTP ADAMTS13 vWF thrombotic thrombocytopenic purpura review"),
    ("P20-1", "STEC-HUS临床表现:高血压、心脏、神经、胃肠道和内分泌并发症",
     "STEC-HUS hemolytic uremic syndrome extra-renal clinical manifestations"),
    ("P23-22", "TMA的诊断挑战和临床异质性",
     "TMA diagnosis clinical heterogeneity challenge"),
    ("P25-7", "aHUS 补体抑制剂 治疗",
     "aHUS atypical hemolytic uremic syndrome complement inhibitor eculizumab ravulizumab"),
    ("P28-3", "未及时接受治疗的TTP患者死亡",
     "TTP untreated mortality outcome historical"),
]


def main():
    results = []
    for pn_x, ppt, term in TARGETS:
        print(f"\n=== {pn_x}: {ppt[:60]} ===")
        # 加 filter: review, free full text
        full = f"({term}) AND (review[pt] OR systematic review[pt])"
        pmids = esearch(full, 8)
        print(f"  hits: {len(pmids)}")
        cands = []
        for pmid in pmids[:5]:
            s = esummary([pmid])
            if not s:
                continue
            info = s[0]
            title = info.get("title", "")
            journal = info.get("source", "")
            year = info.get("pubdate", "")[:4]
            doi = ""
            for aid in info.get("articleids", []):
                if aid.get("idtype") == "doi":
                    doi = aid.get("value", "")
                    break
            cands.append({
                "pmid": pmid,
                "title": title[:120],
                "journal": journal[:50],
                "year": year,
                "doi": doi,
            })
            print(f"  PMID {pmid} ({year}) {journal[:30]}: {title[:80]}")
        results.append({"pn_x": pn_x, "ppt": ppt, "candidates": cands})

    out = "/Users/david/Desktop/developments/via54Medit/docs/wrong_pdf_replacement_v2_20260811.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
