#!/usr/bin/env python3
"""
wrong_pdf_replacement_plan.py — 为 11 个 TMA WRONG_PDF 找正确替代论文

策略:
1. 用 PubMed E-utilities 搜替代论文 (按 PPT 标号内容关键词)
2. 找有 free full text / Europe PMC 链接的
3. 输出推荐列表 + 链接, 供人工确认
"""
import os, sys, json, time
import urllib.request
import urllib.parse
import re
from xml.etree import ElementTree as ET

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
EMAIL = "research@minimax.dev"

# WRONG_PDF 列表 (pn_x, expected topic for replacement, key search terms)
REPLACEMENTS = [
    ("P3-1", "补体系统三条活化途径综述", "complement system three activation pathways review"),
    ("P3-2", "补体激活和调节相关综述", "complement activation regulation review"),
    ("P4-5", "近端补体活化产物调理吞噬综述", "complement opsonization phagocytosis proximal review"),
    ("P8-2", "TMA 三联征综述 (MAHA, 血小板减少, 器官损伤)", "thrombotic microangiopathy triad review"),
    ("P12-1", "血涂片 schistocytes 裂红细胞综述", "schistocytes blood smear review MAHA"),
    ("P12-2", "MAHA 血涂片特征综述", "microangiopathic hemolytic anemia blood smear review"),
    ("P14-1", "TMA 内皮损伤血小板激活综述", "TMA endothelial injury platelet activation review"),
    ("P15-1", "TMA 病因分类 (原发/继发/特发) 综述", "TMA etiology classification primary secondary idiopathic"),
    ("P17-2", "ADAMTS13 检测 TTP 诊断综述", "ADAMTS13 assay TTP diagnosis review"),
    ("P20-1", "STEC-HUS 肾外表现综述", "STEC-HUS extra-renal manifestations review"),
    ("P28-3", "TTP 死亡率 治疗 综述", "TTP mortality untreated review"),
]


def esearch(term: str, retmax: int = 10) -> list:
    """PubMed esearch 返回 PMID 列表"""
    url = f"{EUTILS}/esearch.fcgi?db=pubmed&term={urllib.parse.quote(term)}&retmax={retmax}&retmode=json&email={EMAIL}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read().decode())
        return data.get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        print(f"    esearch err: {e}")
        return []


def esummary(pmids: list) -> list:
    """PubMed esummary 返回论文详情"""
    if not pmids:
        return []
    url = f"{EUTILS}/esummary.fcgi?db=pubmed&id={','.join(pmids)}&retmode=json&email={EMAIL}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read().decode())
        result = data.get("result", {})
        uids = result.get("uids", [])
        return [result[u] for u in uids if u in result]
    except Exception as e:
        print(f"    esummary err: {e}")
        return []


def has_free_fulltext(pmid: str) -> dict:
    """查 Europe PMC 是否有 free full text"""
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:{pmid}%20AND%20SRC:MED&resulttype=core&format=json"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read().decode())
        hits = data.get("resultList", {}).get("result", [])
        if not hits:
            return {}
        h = hits[0]
        return {
            "is_open_access": h.get("isOpenAccess", "N") == "Y",
            "fulltext_url": h.get("fullTextUrlList", {}).get("fullTextUrl", [{}])[0].get("url", ""),
            "pmcid": h.get("pmcid", ""),
            "doi": h.get("doi", ""),
        }
    except Exception as e:
        return {}


def find_replacement(pn_x: str, topic: str, term: str) -> dict:
    """为单个 WRONG_PDF 找替代"""
    print(f"\n=== {pn_x}: {topic} ===")
    print(f"  search: {term}")

    # 加 filter: review, recent (放宽 OA 让候选更多)
    full_term = f"({term}) AND (review[pt] OR systematic review[pt])"

    pmids = esearch(full_term, retmax=20)
    print(f"  PubMed hits: {len(pmids)}")

    candidates = []
    for pmid in pmids:
        time.sleep(0.4)  # rate limit
        summary = esummary([pmid])
        if not summary:
            continue
        s = summary[0]
        title = s.get("title", "")
        authors = ", ".join(a.get("name", "") for a in s.get("authors", [])[:3])
        journal = s.get("source", "")
        year = s.get("pubdate", "")[:4]
        # 过滤: 至少要 search term 里的 1-2 个关键词出现在 title (放宽匹配)
        term_words = [w.lower() for w in re.findall(r'\w+', term) if len(w) > 4][:5]
        title_lower = title.lower()
        # 至少有 1 个 term word 在 title, 或 topic word 匹配
        if term_words and not any(w in title_lower for w in term_words):
            # 再宽松: 检查 abstract words
            continue

        time.sleep(0.3)
        oa = has_free_fulltext(pmid)
        candidates.append({
            "pmid": pmid,
            "title": title[:120],
            "authors": authors,
            "journal": journal,
            "year": year,
            "pmcid": oa.get("pmcid", ""),
            "doi": oa.get("doi", ""),
            "is_oa": oa.get("is_open_access", False),
            "fulltext_url": oa.get("fulltext_url", ""),
        })
        if len(candidates) >= 3:
            break

    return {
        "pn_x": pn_x,
        "topic": topic,
        "search_term": term,
        "candidates": candidates,
    }


def main():
    all_results = []
    for pn_x, topic, term in REPLACEMENTS:
        try:
            r = find_replacement(pn_x, topic, term)
            all_results.append(r)
            print(f"  candidates: {len(r['candidates'])}")
            for c in r["candidates"][:3]:
                oa = "🟢 OA" if c["is_oa"] else "🔴 paywall"
                print(f"    [{oa}] PMID {c['pmid']} ({c['year']}) {c['journal'][:40]}")
                print(f"         {c['title'][:90]}")
        except Exception as e:
            print(f"  ERR: {e}")

    out_path = "/Users/david/Desktop/developments/via54Medit/docs/wrong_pdf_replacement_candidates_20260811.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n=== Saved {out_path} ===")

    # Summary
    print(f"\n=== Summary ===")
    n_oa = sum(1 for r in all_results for c in r["candidates"] if c.get("is_oa"))
    n_total = sum(len(r["candidates"]) for r in all_results)
    print(f"  Total candidates: {n_total}")
    print(f"  OA candidates: {n_oa}")


if __name__ == "__main__":
    main()
