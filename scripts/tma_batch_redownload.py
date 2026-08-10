#!/usr/bin/env python3
"""
tma_batch_redownload.py — TMA 16 个错论文批量重下 (2026-08-10)

读 _redownload_suggestions.json, 对每个 Pn-x 试:
  1. PMC OA PDF (europepmc.org/articles/PMC.../pdf)
  2. Europe PMC OA PDF
  3. DOI 主链接重定向 + 出版商直链
  4. 跳过 (需付费墙 / CNKI 登录)

输出: 替换 /Users/david/Desktop/TMA_文献整理/_2_pdfs/Pn-x_main_<old>.pdf
       写 _redownload_log.json
"""
import os, sys, json, re, time, hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

import urllib.request
import urllib.error
import socket

# 长超时
socket.setdefaulttimeout(60)

SUGGESTIONS_JSON = "/Users/david/Desktop/TMA_文献整理/_3_highlight_v10_glm/_redownload_suggestions.json"
PDFS_DIR = "/Users/david/Desktop/TMA_文献整理/_2_pdfs"
LOG_JSON = "/Users/david/Desktop/TMA_文献整理/_3_highlight_v10_glm/_tma_redownload_log.json"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _http_get(url: str, timeout: int = 30) -> Tuple[int, bytes]:
    """GET URL, 跟随重定向, 返回 (status, body)"""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "*/*",
    })
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        return 0, str(e).encode()


def _resolve_doi_to_pmc(doi: str) -> Optional[str]:
    """DOI → PMC ID via Europe PMC resolver"""
    # Europe PMC DOI lookup
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{doi}&format=json&resultType=core"
    code, body = _http_get(url, timeout=20)
    if code != 200:
        return None
    try:
        data = json.loads(body)
        results = data.get("resultList", {}).get("result", [])
        for r in results:
            pmcid = r.get("pmcid", "")
            if pmcid and pmcid.startswith("PMC"):
                return pmcid
    except Exception:
        pass
    return None


def _try_pmc_pdf(pmcid: str, out_path: str) -> bool:
    """试 PMC OA PDF 下载"""
    # Europe PMC PDF: /articles/PMCxxxx/pdf
    for base in [
        f"https://europepmc.org/articles/{pmcid}/pdf/main.pdf",
        f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf",
        f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/main.pdf",
    ]:
        code, body = _http_get(base, timeout=45)
        if code == 200 and body[:4] == b"%PDF":
            with open(out_path, "wb") as f:
                f.write(body)
            return True
    return False


def _try_doi_pdf(doi: str, out_path: str) -> bool:
    """DOI 主链接重定向到出版商, 抓 PDF"""
    if not doi or doi == "null":
        return False
    doi_url = f"https://doi.org/{doi}"
    code, body = _http_get(doi_url, timeout=30)
    if code != 200 or not body:
        return False
    # 检查是否是 PDF
    if body[:4] == b"%PDF":
        with open(out_path, "wb") as f:
            f.write(body)
        return True
    # 不是 PDF, 是 HTML, 跳
    return False


def _find_old_pdf(pn_x: str) -> Optional[str]:
    """找 Pn-x 目录下的旧 PDF (flat 约定)"""
    for f in os.listdir(PDFS_DIR):
        if f.startswith(pn_x + "_") and f.lower().endswith(".pdf"):
            return os.path.join(PDFS_DIR, f)
    return None


def _make_new_filename(pn_x: str, suggestion: dict) -> str:
    """生成新文件名, 包含作者+年份+期刊"""
    cit = suggestion.get("correct_citation", {})
    authors = cit.get("authors", "Unknown").split(",")[0].split(" ")[0]  # 姓
    year = cit.get("year", "yyyy")
    journal = cit.get("journal", "Journal").split(".")[0]
    # 清理
    journal = re.sub(r'[^A-Za-z0-9]', '', journal)[:20]
    return f"{pn_x}_main_{authors}_{journal}_{year}.pdf"


def main():
    if not os.path.isfile(SUGGESTIONS_JSON):
        print(f"❌ 找不到 {SUGGESTIONS_JSON}")
        sys.exit(1)
    with open(SUGGESTIONS_JSON) as f:
        data = json.load(f)
    suggestions = data.get("suggestions", [])
    print(f"=== TMA 16 错论文批量重下 ===")
    print(f"待处理: {len(suggestions)} 个 Pn-x")
    print()

    log = {"n_total": len(suggestions), "n_success": 0, "n_fail": 0, "results": []}

    for i, sug in enumerate(suggestions, 1):
        pn_x = sug.get("pn_x", "")
        cit = sug.get("correct_citation", {})
        doi = cit.get("doi", "")
        title = cit.get("title", cit.get("authors", ""))
        print(f"[{i}/{len(suggestions)}] {pn_x}: {title[:60]}...")
        print(f"    DOI: {doi}")

        old_pdf = _find_old_pdf(pn_x)
        if not old_pdf:
            print(f"    ⚠ 找不到旧 PDF")
            log["results"].append({"pn_x": pn_x, "ok": False, "reason": "no_old_pdf"})
            log["n_fail"] += 1
            continue

        new_name = _make_new_filename(pn_x, sug)
        new_path = os.path.join(PDFS_DIR, new_name)
        result = {"pn_x": pn_x, "ok": False, "old": os.path.basename(old_pdf),
                  "new": new_name, "method": "", "doi": doi}

        # 1) DOI → PMC
        if doi and doi != "null":
            print(f"    试 DOI → PMC...")
            pmcid = _resolve_doi_to_pmc(doi)
            if pmcid:
                print(f"    PMC: {pmcid}")
                if _try_pmc_pdf(pmcid, new_path):
                    result["ok"] = True
                    result["method"] = f"pmc:{pmcid}"
                    print(f"    ✓ 下载成功 ({os.path.getsize(new_path)} bytes)")
                    # 替换
                    os.remove(old_pdf)
                    log["n_success"] += 1
                    log["results"].append(result)
                    continue
                else:
                    print(f"    ✗ PMC PDF 不可用")
            else:
                print(f"    ✗ 无 PMC ID")

            # 2) DOI 直链
            print(f"    试 DOI 直链...")
            if _try_doi_pdf(doi, new_path):
                result["ok"] = True
                result["method"] = "doi_redirect"
                print(f"    ✓ 下载成功 ({os.path.getsize(new_path)} bytes)")
                os.remove(old_pdf)
                log["n_success"] += 1
                log["results"].append(result)
                continue
            else:
                print(f"    ✗ DOI 直链不是 PDF")

        # 全部失败
        result["reason"] = "all_failed"
        log["n_fail"] += 1
        log["results"].append(result)
        print(f"    ❌ 该 Pn-x 全部失败 (需要付费墙 / CNKI 登录)")
        time.sleep(1)  # 避免被 ban

    # 写 log
    with open(LOG_JSON, "w") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print()
    print(f"=== 完成 ===")
    print(f"✓ 成功: {log['n_success']}/{log['n_total']}")
    print(f"❌ 失败: {log['n_fail']}/{log['n_total']}")
    print(f"日志: {LOG_JSON}")


if __name__ == "__main__":
    main()
