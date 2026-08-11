#!/usr/bin/env python3
"""
batch_download_v2.py — 批量下 8 个 WRONG_PDF 替代 + verify title
"""
import os, sys, json, time, re, shutil
import urllib.request
import fitz

TMA_ROOT = "/Users/david/Desktop/TMA_文献整理"
REPLACE_DIR = os.path.join(TMA_ROOT, "_2_pdfs_replaced_v2")
BACKUP_DIR = os.path.join(TMA_ROOT, "_downloads/_pdfs_real")

# 最佳候选 (挑了 7 个, P28-3 单独处理)
TARGETS = [
    ("P4-5", "10.1016/j.coi.2012.06.001", "22999705", "complement opsonin lupus 2012"),
    ("P15-1", "10.1016/j.ekir.2021.08.004", "33102952", "complement secondary TMA 2021"),
    ("P17-1", "10.1001/jama.2025.7450", "40388146", "TTP review JAMA 2025"),
    ("P20-1", "10.3390/brainsci15070717", "40722309", "HUS neurological 2025"),
    ("P23-22", "10.1590/2175-8239-jbn-2024-u002en", "39918340", "aHUS recommendations 2025"),
    ("P25-7", "10.1182/hasheducation-2025.0001", "41347985", "complement-mediated TMA long-term"),
]


def try_scihub(doi: str, out_path: str, timeout: int = 30) -> bool:
    for base in ["https://sci.bban.top", "https://sci-hub.al"]:
        try:
            url = f"{base}/pdf/{doi}.pdf?download=true"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            if data[:4] == b"%PDF":
                with open(out_path, "wb") as f:
                    f.write(data)
                return True
        except Exception as e:
            continue
    return False


def verify_title(pdf_path: str) -> dict:
    try:
        doc = fitz.open(pdf_path)
        if doc.page_count < 1:
            return {"ok": False, "reason": "empty"}
        text = doc[0].get_text()[:600].replace("\n", " ")
        return {"ok": True, "pages": doc.page_count, "title": text[:300]}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def main():
    os.makedirs(REPLACE_DIR, exist_ok=True)
    log = []
    for pn_x, doi, pmid, hint in TARGETS:
        out = os.path.join(REPLACE_DIR, f"{pn_x}_replaced_PMID{pmid}.pdf")
        print(f"\n=== {pn_x}: PMID {pmid} DOI {doi} ===")
        ok = try_scihub(doi, out)
        if not ok:
            print(f"  ❌ Download failed")
            log.append({"pn_x": pn_x, "pmid": pmid, "ok": False})
            continue
        v = verify_title(out)
        print(f"  ✓ {v.get('pages')}p - {v.get('title', '')[:120]}")
        log.append({"pn_x": pn_x, "pmid": pmid, "ok": True, "path": out, "title": v.get("title", "")[:200]})

    out_json = os.path.join(REPLACE_DIR, "_download_v2_log.json")
    with open(out_json, "w") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    n = sum(1 for r in log if r["ok"])
    print(f"\n=== {n}/{len(TARGETS)} downloaded ===")


if __name__ == "__main__":
    main()
