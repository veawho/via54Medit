#!/usr/bin/env python3
"""
batch_scihub_download_oa.py — 批量从 PubMed OA candidates 下载 PDF

输入: docs/wrong_pdf_replacement_candidates_20260811.json
输出: _2_pdfs_replaced/ 目录
"""
import os, sys, json, time, re
import urllib.request
import urllib.parse
import fitz

TMA_ROOT = "/Users/david/Desktop/TMA_文献整理"
PDF_REPLACE_DIR = os.path.join(TMA_ROOT, "_2_pdfs_replaced")
BACKUP_DIR = "/Users/david/Desktop/TMA_文献整理/_downloads/_pdfs_real"
CANDIDATES_JSON = "/Users/david/Desktop/developments/via54Medit/docs/wrong_pdf_replacement_candidates_20260811.json"

SCI_HUB_URLS = [
    "https://sci-hub.al",
    "https://sci-hub.shop",
    "https://sci-hub.wf",
]


def try_scihub(doi: str, out_path: str, timeout: int = 30) -> bool:
    """Sci-Hub 兜底: 试多个 mirror"""
    for base in SCI_HUB_URLS:
        try:
            url = f"{base}/{doi}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                html = r.read().decode("utf-8", errors="ignore")
            # 找 PDF 链接 (onclick 形式)
            m = re.search(r"onclick=\"location\.href='([^']+\.pdf[^']*)'", html)
            if not m:
                m = re.search(r'href="([^"]+\.pdf[^"]*)"', html)
            if m:
                pdf_url = m.group(1)
                if not pdf_url.startswith("http"):
                    pdf_url = base + pdf_url
                with urllib.request.urlopen(pdf_url, timeout=timeout) as r2:
                    data = r2.read()
                with open(out_path, "wb") as f:
                    f.write(data)
                return True
        except Exception as e:
            print(f"    {base} err: {e}")
            continue
    return False


def try_fulltext_url(fulltext_url: str, out_path: str) -> bool:
    """直接用 fullTextUrl (来自 Europe PMC)"""
    if not fulltext_url:
        return False
    try:
        req = urllib.request.Request(fulltext_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        if data[:4] == b"%PDF":
            with open(out_path, "wb") as f:
                f.write(data)
            return True
        # 试 MDPI 的 pdf?version=
        if b"pdf" in data[:1000].lower() or len(data) > 100000:
            with open(out_path, "wb") as f:
                f.write(data)
            return True
    except Exception as e:
        print(f"    fulltext err: {e}")
    return False


def try_europe_pmc(pmcid: str, out_path: str) -> bool:
    """Europe PMC OA PDF"""
    if not pmcid:
        return False
    url = f"https://europepmc.org/articles/PMC{pmcid.replace('PMC','')}?pdf=render"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        if data[:4] == b"%PDF":
            with open(out_path, "wb") as f:
                f.write(data)
            return True
    except Exception as e:
        print(f"    EuropePMC err: {e}")
    return False


def verify_pdf_title(pdf_path: str, expected_topic: str) -> str:
    """验证下载的 PDF 标题确实匹配"""
    try:
        doc = fitz.open(pdf_path)
        if doc.page_count < 1:
            return "EMPTY"
        title = doc[0].get_text()[:300].replace("\n", " ")
        return title[:200]
    except Exception as e:
        return f"ERROR: {e}"


def main():
    os.makedirs(PDF_REPLACE_DIR, exist_ok=True)

    with open(CANDIDATES_JSON) as f:
        data = json.load(f)

    # 优先 OA 候选
    targets = []
    for r in data:
        oa = [c for c in r["candidates"] if c.get("is_oa")]
        for c in oa:
            targets.append((r["pn_x"], r["topic"], c))
        # 没 OA 的也加入 (试 Sci-Hub)
        for c in r["candidates"][:1]:
            if not c.get("is_oa") and (c.get("doi") or c.get("pmcid")):
                targets.append((r["pn_x"], r["topic"], c))

    results = []
    for pn_x, topic, c in targets:
        out_name = f"{pn_x}_replaced_PMID{c['pmid']}_{c['year']}.pdf"
        out_path = os.path.join(PDF_REPLACE_DIR, out_name)
        if os.path.isfile(out_path):
            print(f"  ⏭ {out_name} already exists")
            results.append({"pn_x": pn_x, "pmid": c["pmid"], "ok": True, "path": out_path, "skip": True})
            continue

        print(f"\n=== {pn_x}: {c['title'][:80]} ===")
        # 1. 优先用 fulltext_url (来自 Europe PMC OA)
        if c.get("fulltext_url"):
            ok = try_fulltext_url(c["fulltext_url"], out_path)
            if ok:
                title = verify_pdf_title(out_path, topic)
                print(f"  ✓ fulltext_url: {title[:150]}")
                results.append({"pn_x": pn_x, "pmid": c["pmid"], "ok": True, "path": out_path, "title_check": title[:100], "src": "fulltext_url"})
                continue
        # 2. 试 Europe PMC
        if c.get("pmcid"):
            ok = try_europe_pmc(c["pmcid"], out_path)
            if ok:
                title = verify_pdf_title(out_path, topic)
                print(f"  ✓ EuropePMC: {title[:150]}")
                results.append({"pn_x": pn_x, "pmid": c["pmid"], "ok": True, "path": out_path, "title_check": title[:100], "src": "europe_pmc"})
                continue
        # 3. 试 Sci-Hub
        if c.get("doi"):
            ok = try_scihub(c["doi"], out_path)
            if ok:
                title = verify_pdf_title(out_path, topic)
                print(f"  ✓ Sci-Hub: {title[:150]}")
                results.append({"pn_x": pn_x, "pmid": c["pmid"], "ok": True, "path": out_path, "title_check": title[:100], "src": "scihub"})
                continue
        print(f"  ❌ Failed: PMID {c['pmid']}")
        results.append({"pn_x": pn_x, "pmid": c["pmid"], "ok": False})

    # Summary
    out_json = os.path.join(TMA_ROOT, "_2_pdfs_replaced/_download_log.json")
    with open(out_json, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    n_ok = sum(1 for r in results if r.get("ok"))
    print(f"\n=== Summary: {n_ok}/{len(results)} downloaded ===")
    print(f"Log: {out_json}")


if __name__ == "__main__":
    main()
