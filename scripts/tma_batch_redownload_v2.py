#!/usr/bin/env python3
"""
tma_batch_redownload_v2.py — TMA 16 错论文重下 v2 (2026-08-10)

GLM 给的 DOI 多数 404/403, 改用:
  1. Europe PMC 全文搜索 (用 title_keywords + author 拼查询)
  2. Crossref 标题搜索
  3. 找到 PMC ID → 下 OA PDF
  4. 找到 DOI 重定向到出版商 PDF
  5. 失败: 标 skip

输出: 替换 /Users/david/Desktop/TMA_文献整理/_2_pdfs/Pn-x_main_*.pdf
       写 _tma_redownload_log_v2.json
"""
import os, sys, json, re, time
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

import urllib.request
import urllib.error
import socket
socket.setdefaulttimeout(60)

SUGGESTIONS_JSON = "/Users/david/Desktop/TMA_文献整理/_3_highlight_v10_glm/_redownload_suggestions.json"
PDFS_DIR = "/Users/david/Desktop/TMA_文献整理/_2_pdfs"
LOG_JSON = "/Users/david/Desktop/TMA_文献整理/_3_highlight_v10_glm/_tma_redownload_log_v2.json"

UA_CHROME = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
UA_CROSSREF = "via54Medit/1.0 (mailto:via54@MiniMax.dev)"


def _http_get(url: str, timeout: int = 20, ua: str = UA_CHROME) -> Tuple[int, bytes]:
    req = urllib.request.Request(url, headers={
        "User-Agent": ua,
        "Accept": "*/*",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception:
        return 0, b""


def _europe_pmc_search(query: str, year: Optional[int] = None,
                       first_author: Optional[str] = None) -> List[Dict]:
    """Europe PMC 全文搜索, 返回结果列表"""
    q_parts = [query]
    if first_author:
        q_parts.append(f'AUTHOR:"{first_author}"')
    if year:
        q_parts.append(f'FIRST_PDATE:[{year}-01-01 TO {year}-12-31]')
    full_q = " AND ".join(f"({p})" for p in q_parts if p)
    url = (
        f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?"
        f"query={urllib.parse.quote(full_q)}"
        f"&format=json&resultType=core&pageSize=5"
    )
    code, body = _http_get(url, timeout=20)
    if code != 200:
        return []
    try:
        data = json.loads(body)
        return data.get("resultList", {}).get("result", [])
    except Exception:
        return []


def _try_pmc_pdf(pmcid: str, out_path: str) -> Tuple[bool, str]:
    """试 PMC OA PDF 下载"""
    bases = [
        (f"https://europepmc.org/articles/{pmcid}/pdf/main.pdf", "europepmc_pdf"),
        (f"https://europepmc.org/backend/ptpmcrender.fcgi?accid={pmcid}&blobtype=pdf", "europepmc_render"),
        (f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/", "ncbi_pdf"),
    ]
    for url, method in bases:
        code, body = _http_get(url, timeout=45)
        if code == 200 and body[:4] == b"%PDF":
            with open(out_path, "wb") as f:
                f.write(body)
            return True, method
    return False, "all_failed"


def _crossref_search(title: str, first_author: Optional[str] = None,
                     year: Optional[int] = None) -> Optional[str]:
    """Crossref 搜标题, 返回 DOI 或 None"""
    if not title:
        return None
    q = title
    if first_author:
        q = f"{first_author} {title}"
    url = (
        f"https://api.crossref.org/works?"
        f"query.bibliographic={urllib.parse.quote(q)}"
        f"&rows=3"
    )
    code, body = _http_get(url, timeout=20, ua=UA_CROSSREF)
    if code != 200:
        return None
    try:
        data = json.loads(body)
        items = data.get("message", {}).get("items", [])
        for item in items:
            # 验证: 第一作者姓 + 年份匹配
            authors = item.get("author", [])
            item_year = (item.get("issued", {}).get("date-parts", [[None]])[0][0]
                         or item.get("published-online", {}).get("date-parts", [[None]])[0][0])
            item_title = (item.get("title", [""])[0] or "").lower()
            if year and item_year != year:
                continue
            if first_author:
                auth_fam = first_author.split()[-1].lower()
                if not any(auth_fam in (a.get("family", "") or "").lower() for a in authors):
                    continue
            # 检查 title 重合度
            if title and any(w.lower() in item_title for w in title.split() if len(w) > 4):
                return item.get("DOI")
        # 兜底: 返回第一个 hit
        if items:
            return items[0].get("DOI")
    except Exception:
        pass
    return None


def _find_old_pdf(pn_x: str) -> Optional[str]:
    for f in os.listdir(PDFS_DIR):
        if f.startswith(pn_x + "_") and f.lower().endswith(".pdf"):
            return os.path.join(PDFS_DIR, f)
    return None


def _make_new_filename(pn_x: str, sug: dict) -> str:
    inner = sug.get("suggestion", sug)
    cit = inner.get("correct_citation", {})
    authors = cit.get("authors", "Unknown")
    surname = authors.split(",")[0].split(" ")[0] if "," in authors else authors.split()[-1]
    surname = re.sub(r'[^A-Za-z\u4e00-\u9fff]', '', surname)[:15]
    year = cit.get("year", "yyyy")
    journal = cit.get("journal", "Journal")
    journal_short = re.sub(r'[^A-Za-z0-9]', '', journal)[:15]
    return f"{pn_x}_main_{surname}_{journal_short}_{year}.pdf"


def _build_search_query(sug: dict) -> Tuple[str, Optional[str], Optional[int]]:
    """从 suggestion 构造搜索 query

    优先级:
    1. title_keywords (topic-level keywords, 来自 GLM 提炼)
    2. expected_visual (PPT 视觉内容, 含医学术语)
    3. expected_citation (引文字段, 抽 title)
    """
    inner = sug.get("suggestion", sug)
    cit = inner.get("correct_citation", {})
    title_kws = inner.get("title_keywords", [])
    expected_visual = sug.get("expected_visual", "")
    expected_quote = sug.get("expected_citation", "")

    # 1) 优先: title_keywords (拼成短语)
    if title_kws:
        # 过滤标点, 选 3-4 个最长的
        clean_kws = [re.sub(r'[^\w\s\u4e00-\u9fff-]', '', k) for k in title_kws if len(k) > 2]
        # 中文优先 (4+ 字符)
        cn_kws = [k for k in clean_kws if any('\u4e00' <= c <= '\u9fff' for c in k) and len(k) >= 4]
        en_kws = [k for k in clean_kws if not any('\u4e00' <= c <= '\u9fff' for c in k) and len(k) >= 4]
        if cn_kws:
            title = " ".join(cn_kws[:2])
        elif en_kws:
            title = " ".join(en_kws[:3])
        else:
            title = " ".join(clean_kws[:3])
    elif expected_visual:
        title = expected_visual[:80]
    else:
        title = ""

    # 抽第一作者姓
    first_author = cit.get("authors", "").split(",")[0].split(" ")[-1] if cit.get("authors") else None
    year = cit.get("year")
    return title, first_author, year


def process_pn_x(sug: dict) -> Dict:
    """处理单个 Pn-x, 返回结果 dict"""
    pn_x = sug.get("pn_x", "")
    inner = sug.get("suggestion", sug)
    cit = inner.get("correct_citation", {})
    search_queries = inner.get("search_queries", [])
    result = {
        "pn_x": pn_x,
        "ok": False,
        "old": None,
        "new": None,
        "method": None,
        "reason": None,
        "pmcid": None,
        "doi": None,
        "title_found": None,
    }

    old_pdf = _find_old_pdf(pn_x)
    if not old_pdf:
        result["reason"] = "no_old_pdf"
        return result
    result["old"] = os.path.basename(old_pdf)
    new_path = os.path.join(PDFS_DIR, _make_new_filename(pn_x, sug))
    result["new"] = os.path.basename(new_path)

    title, first_author, year = _build_search_query(sug)

    # 0) 先从 search_queries 抽 DOI/PMID 试一遍
    for sq in search_queries:
        # 抽 DOI (10.xxxx/...)
        m = re.search(r'(10\.\d{4,}/[^\s,;]+)', sq)
        if m:
            doi = m.group(1).rstrip('.,;')
            code, body = _http_get(f"https://doi.org/{doi}", timeout=15)
            if code == 200 and body[:4] == b"%PDF":
                with open(new_path, "wb") as f:
                    f.write(body)
                result["ok"] = True
                result["method"] = "search_query_doi"
                result["doi"] = doi
                os.remove(old_pdf)
                return result
        # 抽 PMID
        m = re.search(r'PMID[:\s]+(\d+)', sq, re.IGNORECASE)
        if m:
            pmid = m.group(1)
            # 用 PMID 查 Europe PMC → PMC ID → PDF
            url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:{pmid}&format=json&resultType=core"
            code, body = _http_get(url, timeout=15)
            if code == 200:
                try:
                    data = json.loads(body)
                    for r in data.get("resultList", {}).get("result", []):
                        pmcid = r.get("pmcid", "")
                        if pmcid and pmcid.startswith("PMC") and r.get("isOpenAccess") == "Y":
                            ok, method = _try_pmc_pdf(pmcid, new_path)
                            if ok:
                                result["ok"] = True
                                result["method"] = f"pmid:{method}"
                                result["pmcid"] = pmcid
                                result["title_found"] = r.get("title", "")
                                os.remove(old_pdf)
                                return result
                except Exception:
                    pass

    # 1) Europe PMC title search → PMC PDF
    if title and len(title) > 5:
        results = _europe_pmc_search(title, year=year, first_author=first_author)
        for r in results[:5]:
            pmcid = r.get("pmcid", "")
            r_title = r.get("title", "")
            r_year = r.get("pubYear", "")
            if pmcid and pmcid.startswith("PMC") and r.get("isOpenAccess") == "Y":
                # 验证 year
                if year and str(year) != str(r_year):
                    continue
                # 验证 title
                if title:
                    check_words = [w for w in title.split() if len(w) > 3]
                    if not any(w.lower() in r_title.lower() for w in check_words[:2]):
                        continue
                ok, method = _try_pmc_pdf(pmcid, new_path)
                if ok:
                    result["ok"] = True
                    result["method"] = f"pmc_search:{method}"
                    result["pmcid"] = pmcid
                    result["title_found"] = r_title
                    os.remove(old_pdf)
                    return result

    # 2) Crossref title search → DOI redirect → PDF
    doi_from_sug = cit.get("doi")
    if doi_from_sug and doi_from_sug != "null":
        code, body = _http_get(f"https://doi.org/{doi_from_sug}", timeout=15)
        if code == 200 and body[:4] == b"%PDF":
            with open(new_path, "wb") as f:
                f.write(body)
            result["ok"] = True
            result["method"] = "doi_redirect"
            result["doi"] = doi_from_sug
            os.remove(old_pdf)
            return result

    # 3) Crossref 标题搜索 → DOI
    if title and len(title) > 5:
        doi = _crossref_search(title, first_author, year)
        if doi:
            code, body = _http_get(f"https://doi.org/{doi}", timeout=15)
            if code == 200 and body[:4] == b"%PDF":
                with open(new_path, "wb") as f:
                    f.write(body)
                result["ok"] = True
                result["method"] = "crossref_doi"
                result["doi"] = doi
                os.remove(old_pdf)
                return result

    result["reason"] = "all_failed"
    return result


def main():
    import urllib.parse
    if not os.path.isfile(SUGGESTIONS_JSON):
        print(f"❌ {SUGGESTIONS_JSON} 不存在")
        sys.exit(1)
    with open(SUGGESTIONS_JSON) as f:
        data = json.load(f)
    suggestions = data.get("suggestions", [])
    print(f"=== TMA 16 错论文重下 v2 (title-based) ===")
    print(f"待处理: {len(suggestions)} 个 Pn-x\n")

    log = {"n_total": len(suggestions), "n_success": 0, "n_fail": 0, "results": []}

    for i, sug in enumerate(suggestions, 1):
        pn_x = sug.get("pn_x", "")
        inner = sug.get("suggestion", sug)
        cit = inner.get("correct_citation", {})
        title, author, year = _build_search_query(sug)
        print(f"[{i}/{len(suggestions)}] {pn_x}: {cit.get('authors', '')[:30]} | {year} | {cit.get('journal', '')[:20]}", flush=True)
        print(f"    搜索: {title[:60]} | {author}", flush=True)

        result = process_pn_x(sug)
        log["results"].append(result)

        if result["ok"]:
            log["n_success"] += 1
            print(f"    ✓ {result['method']} -> {result['new']}", flush=True)
            if result.get("title_found"):
                print(f"      找到: {result['title_found'][:80]}", flush=True)
        else:
            log["n_fail"] += 1
            print(f"    ❌ {result['reason']} (保留旧 PDF)", flush=True)

        time.sleep(1)  # 避免被 ban

    with open(LOG_JSON, "w") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(f"\n=== 完成 ===")
    print(f"✓ 成功: {log['n_success']}/{log['n_total']}")
    print(f"❌ 失败: {log['n_fail']}/{log['n_total']}")
    print(f"日志: {LOG_JSON}")


if __name__ == "__main__":
    main()
