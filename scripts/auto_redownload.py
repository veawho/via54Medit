#!/usr/bin/env python3
"""
auto_redownload.py — L0 错论文自动重下 (2026-08-10)

读 l0_glm_redownload.py 生成的 _redownload_suggestions.json,
对每个 fail 案例自动去 GLM 给的 URL 重下 PDF, 替换错的.

输入: redownload_suggestions.json
策略:
  1. 用 GLM 给的 DOI 调 via54_pdf_download.download_pdf (5 策略: Direct / PubMed PMC / Europe PMC / Scholar / Sci-Hub)
  2. 试 GLM 给的 pdf_urls (可能已含 PDF 链接)
  3. 验证下载: GLM verify 5 维评分 >= 0.7 才认

输出: 替换的 PDF + _redownload_log.json
"""
import os, sys, csv, json, re, shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

# 让 v10 模块可 import
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)


PROJECTS = {
    "TMA": {
        "root": "/Users/david/Desktop/TMA_文献整理",
        "suggestions_json": "/Users/david/Desktop/TMA_文献整理/_3_highlight_v10_glm/_redownload_suggestions.json",
        "pdf_dir": "/Users/david/Desktop/TMA_文献整理/_2_pdfs",
        "old_highlight_dir": "/Users/david/Desktop/TMA_文献整理/_3_highlight",
        "new_highlight_dir": "/Users/david/Desktop/TMA_文献整理/_3_highlight_v10_glm",
    },
    "雷管方案": {
        "root": "/Users/david/Desktop/雷管方案_文献整理",
        "suggestions_json": "/Users/david/Desktop/雷管方案_文献整理/step4_highlight_v10_glm/_redownload_suggestions.json",
        "pdf_dir": "/Users/david/Desktop/雷管方案_文献整理/step3_pdf下载_160目录",
        "old_highlight_dir": "/Users/david/Desktop/雷管方案_文献整理/step4_highlight_96目录_合并DOI",
        "new_highlight_dir": "/Users/david/Desktop/雷管方案_文献整理/step4_highlight_v10_glm",
    },
}


def _try_download_from_url(url: str, output_path: str, timeout: int = 30) -> bool:
    """
    直接从 GLM 给的 URL 下载 PDF
    """
    import subprocess
    # 真实浏览器 UA (避免 403)
    user_agents = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    for ua in user_agents:
        try:
            result = subprocess.run(
                ["curl", "-sL", "--max-time", str(timeout),
                 "-A", ua,
                 "-H", "Accept: application/pdf,*/*",
                 "-H", "Accept-Language: en-US,en;q=0.9",
                 "-e", "https://www.google.com/",  # referer
                 "-o", output_path, url],
                capture_output=True, timeout=timeout + 5
            )
            if result.returncode != 0:
                continue
            # 验证是 PDF (magic bytes %PDF)
            if os.path.getsize(output_path) < 5000:
                continue
            with open(output_path, "rb") as f:
                header = f.read(5)
            if header[:4] != b"%PDF":
                # 检查是否 HTML 重定向到 PDF
                with open(output_path, "rb") as f:
                    head = f.read(2048).decode("utf-8", errors="ignore")
                # 看是 HTML 但有 PDF link?
                if "<html" in head.lower():
                    # 找 /pdf 链接
                    m = re.search(r'href="([^"]+/pdf[^"]*)"', head, re.IGNORECASE)
                    if m:
                        pdf_url = m.group(1)
                        if not pdf_url.startswith("http"):
                            from urllib.parse import urljoin
                            pdf_url = urljoin(url, pdf_url)
                        if _try_download_from_url(pdf_url, output_path, timeout):
                            return True
                os.remove(output_path)
                continue
            return True
        except Exception:
            continue
    return False


def _try_doi_resolve(doi: str, output_path: str, timeout: int = 30) -> bool:
    """
    用 doi.org 重定向找 PDF
    """
    if not doi or doi == "null" or not doi.strip():
        return False
    # 试 unpaywall (找 OA PDF)
    import subprocess
    try:
        # unpaywall API (免费, 无 key)
        email = "via54@example.com"
        r = subprocess.run(
            ["curl", "-sL", "--max-time", str(timeout),
             f"https://api.unpaywall.org/v2/{doi}?email={email}"],
            capture_output=True, text=True, timeout=timeout + 5
        )
        if r.returncode == 0 and r.stdout:
            data = json.loads(r.stdout)
            for loc in data.get("oa_locations", []):
                pdf_url = loc.get("url_for_pdf") or loc.get("url")
                if pdf_url:
                    if _try_download_from_url(pdf_url, output_path, timeout):
                        return True
    except Exception:
        pass
    return False


def _try_pubmed_pmc(pmid: str, output_path: str, timeout: int = 30) -> bool:
    """
    PubMed → PMC → PDF
    """
    if not pmid or not pmid.strip() or pmid == "null":
        return False
    import subprocess
    try:
        # ESearch: PMID → PMCID
        time_sleep = 0.4
        import time
        time.sleep(time_sleep)
        r = subprocess.run(
            ["curl", "-sL", "--max-time", str(timeout),
             f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pmc&term={pmid}[pmid]&retmode=json"],
            capture_output=True, text=True, timeout=timeout + 5
        )
        if r.returncode != 0:
            return False
        data = json.loads(r.stdout)
        ids = data.get("esearchresult", {}).get("idlist", [])
        if not ids:
            return False
        pmcid = f"PMC{ids[0]}"
        # 下载 PMC PDF
        return _try_download_from_url(
            f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/main.pdf",
            output_path, timeout
        )
    except Exception:
        return False


def _try_doi_pdf(doi: str, output_path: str, timeout: int = 30) -> bool:
    """
    试 doi.org 直接 (有些出版社会 redirect 到 PDF)
    """
    return _try_download_from_url(f"https://doi.org/{doi}", output_path, timeout)


def _verify_pdf(pdf_path: str, expected_citation: str) -> Tuple[bool, float]:
    """
    验证下载的 PDF 是否真的是 expected_citation
    Returns: (ok, score)
    """
    try:
        from l0_paper_match import verify_paper_match
        result = verify_paper_match(pdf_path, expected_citation, min_score=0.5)
        return result["ok"], result["score"]
    except Exception:
        return False, 0.0


def process_one(pn_x: str, suggestion: Dict, pdf_dir: str, log: List) -> bool:
    """
    处理一个 Pn-x: 尝试下载并验证
    Returns: True if successful
    """
    expected = suggestion.get("expected_citation", "")
    s = suggestion.get("suggestion", {})
    if not s:
        return False
    correct = s.get("correct_citation", {})
    doi = correct.get("doi", "")
    pmid = correct.get("pmid", "")
    pdf_urls = s.get("pdf_urls", [])

    # 输出路径
    out_pdf = os.path.join(pdf_dir, f"{pn_x}_main.pdf")
    backup_pdf = out_pdf + ".old_bak"

    # 备份旧 PDF
    if os.path.isfile(out_pdf) and not os.path.isfile(backup_pdf):
        shutil.copy(out_pdf, backup_pdf)

    print(f"  [{pn_x}] 试 GLM 建议: DOI={doi or '?'} PMID={pmid or '?'} urls={len(pdf_urls)}")

    # 策略 1: GLM 给的 PDF URLs
    for url in pdf_urls:
        # 加 .pdf 变体 (MDPI 经常)
        urls_to_try = [url]
        if "mdpi.com" in url.lower() and "/pdf" not in url.lower():
            # MDPI 论文页 → 加 /pdf 或 /pdf?...
            base = url.rstrip("/")
            urls_to_try.extend([f"{base}/pdf", f"{base}/pdf?version=2"])
        if "frontiersin" in url.lower() and "/pdf" not in url.lower():
            base = url.rstrip("/")
            urls_to_try.append(f"{base}/pdf")
        for u in urls_to_try:
            if _try_download_from_url(u, out_pdf):
                ok, score = _verify_pdf(out_pdf, expected)
                if ok and score >= 0.5:
                    log.append({"pn_x": pn_x, "method": "url", "url": u, "score": score, "ok": True})
                    print(f"    ✓ URL 下载成功 (score={score:.2f}): {u[:60]}")
                    return True
                else:
                    # 验证失败, 删除
                    if os.path.isfile(out_pdf):
                        os.remove(out_pdf)

    # 策略 2: DOI → unpaywall → PDF
    if doi and doi != "null":
        if _try_doi_resolve(doi, out_pdf):
            ok, score = _verify_pdf(out_pdf, expected)
            if ok and score >= 0.5:
                log.append({"pn_x": pn_x, "method": "unpaywall", "doi": doi, "score": score, "ok": True})
                print(f"    ✓ Unpaywall 成功 (score={score:.2f})")
                return True
            if os.path.isfile(out_pdf):
                os.remove(out_pdf)

        # 策略 3: doi.org 直链
        if _try_doi_pdf(doi, out_pdf):
            ok, score = _verify_pdf(out_pdf, expected)
            if ok and score >= 0.5:
                log.append({"pn_x": pn_x, "method": "doi", "doi": doi, "score": score, "ok": True})
                print(f"    ✓ DOI 成功 (score={score:.2f})")
                return True
            if os.path.isfile(out_pdf):
                os.remove(out_pdf)

    # 策略 4: PubMed → PMC
    if pmid and pmid != "null":
        if _try_pubmed_pmc(pmid, out_pdf):
            ok, score = _verify_pdf(out_pdf, expected)
            if ok and score >= 0.5:
                log.append({"pn_x": pn_x, "method": "pmc", "pmid": pmid, "score": score, "ok": True})
                print(f"    ✓ PMC 成功 (score={score:.2f})")
                return True
            if os.path.isfile(out_pdf):
                os.remove(out_pdf)

    # 策略 5: Sci-Hub (DOI → sci-hub 镜像)
    if doi and doi != "null":
        for mirror in ["https://sci-hub.se/", "https://sci-hub.st/", "https://sci-hub.ru/"]:
            sci_url = f"{mirror}{doi}"
            if _try_download_from_url(sci_url, out_pdf):
                ok, score = _verify_pdf(out_pdf, expected)
                if ok and score >= 0.5:
                    log.append({"pn_x": pn_x, "method": "scihub", "doi": doi, "score": score, "ok": True})
                    print(f"    ✓ Sci-Hub 成功 (score={score:.2f})")
                    return True
                if os.path.isfile(out_pdf):
                    os.remove(out_pdf)

    # 全部失败, 恢复 backup
    if os.path.isfile(backup_pdf):
        shutil.move(backup_pdf, out_pdf)

    log.append({"pn_x": pn_x, "method": "all_failed", "ok": False})
    print(f"    ❌ 所有策略失败")
    return False


def process_project(name: str, cfg: dict, limit: int = 0,
                    use_glm_verify: bool = True) -> Dict:
    """
    处理一个项目的所有 fail 案例
    """
    print(f"\n=== {name} ===")
    sug_path = cfg["suggestions_json"]
    if not os.path.isfile(sug_path):
        print(f"  无建议文件: {sug_path}")
        return {"project": name, "n_total": 0, "n_success": 0}

    with open(sug_path) as f:
        data = json.load(f)
    suggestions = data.get("suggestions", [])
    print(f"  GLM 建议: {len(suggestions)}")
    if limit:
        suggestions = suggestions[:limit]

    log = []
    success = 0
    fail = 0
    for s in suggestions:
        if process_one(s["pn_x"], s, cfg["pdf_dir"], log):
            success += 1
        else:
            fail += 1

    # 写 log
    log_path = os.path.join(cfg["new_highlight_dir"], "_redownload_log.json")
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump({
            "project": name,
            "n_total": len(suggestions),
            "n_success": success,
            "n_fail": fail,
            "log": log,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n  ✓ {success}/{len(suggestions)} 成功")
    print(f"  ✓ 日志: {log_path}")

    return {"project": name, "n_total": len(suggestions), "n_success": success}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", choices=list(PROJECTS.keys()) + ["all"], default="all")
    parser.add_argument("--limit", type=int, default=0, help="限制处理数量")
    args = parser.parse_args()

    targets = list(PROJECTS.keys()) if args.project == "all" else [args.project]
    results = []
    for name in targets:
        r = process_project(name, PROJECTS[name], limit=args.limit)
        results.append(r)

    # 总览
    print(f"\n=== 汇总 ===")
    for r in results:
        print(f"  {r['project']}: {r['n_success']}/{r['n_total']} 成功")


if __name__ == "__main__":
    main()
