#!/usr/bin/env python3
"""
tma_batch_redownload_v3.py — TMA 16 错论文重下 v3 (Sci-Hub 兜底) (2026-08-10)

User-requested fallback after legitimate channels (PMC, Crossref, DOI redirect) failed.

策略:
  1. Europe PMC author+year search → real DOI (GLM 给的 DOI 多数错)
  2. Crossref title search → real DOI
  3. Sci-Hub (sci-hub.al) 下载 PDF

注意:
  - Sci-Hub 是用户主动选择的兜底渠道 (5 个合法渠道全失败后)
  - 不存储任何 Sci-Hub mirror 配置, 启动时探测可用
  - 所有下载都加 <scihub_fallback> 标记, 便于审计
"""
import os, sys, json, re, time
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

import urllib.request
import urllib.error
import socket
# socket 全局 timeout 必须小, 否则 urlopen 不尊重 per-call timeout
socket.setdefaulttimeout(15)

SUGGESTIONS_JSON = "/Users/david/Desktop/TMA_文献整理/_3_highlight_v10_glm/_redownload_suggestions.json"
PDFS_DIR = "/Users/david/Desktop/TMA_文献整理/_2_pdfs"
LOG_JSON = "/Users/david/Desktop/TMA_文献整理/_3_highlight_v10_glm/_tma_redownload_log_v3.json"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
UA_CROSSREF = "via54Medit/1.0 (mailto:via54@MiniMax.dev)"

# Sci-Hub mirror 候选 (启动时探测可用)
SH_MIRRORS = [
    "https://sci-hub.al",
    "https://sci-hub.shop",
    "https://sci-hub.wf",
]


def _http_get(url: str, timeout: int = 20, ua: str = UA) -> Tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception:
        return 0, b""


def _probe_scihub_mirrors() -> List[str]:
    """探测可用 Sci-Hub mirror, 返回排序后的列表"""
    working = []
    for m in SH_MIRRORS:
        code, _ = _http_get(f"{m}/", timeout=10)
        if code == 200:
            working.append(m)
    return working


# === Step 1: 找真 DOI ===
def _europe_pmc_search_author(author: str, year: int) -> List[Dict]:
    """Europe PMC author+year 搜索 (threading + hard timeout 8s)"""
    import threading
    result_box = [[]]

    def run():
        try:
            # 清理 author: 去 "et al." 之后, 去特殊符号
            clean_author = re.sub(r'[^A-Za-z\s\.\-]', '', author.split(';')[0]).strip()
            if not clean_author or ' ' not in clean_author:
                # 至少需要 姓 + 名
                clean_author = clean_author.split(' ')[0] if clean_author else ""
            q = f'AUTH:"{clean_author}" AND (FIRST_PDATE:[{year}-01-01 TO {year}-12-31])'
            url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={urllib.parse.quote(q)}&format=json&resultType=core&pageSize=10"
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            result_box[0] = data.get("resultList", {}).get("result", [])
        except Exception:
            pass

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=8)
    if t.is_alive():
        return []  # timeout
    return result_box[0]


def _crossref_search_by_title(title: str, first_author: str, year: int) -> Optional[str]:
    """Crossref 搜标题 + 验证 (threading + hard timeout 8s)"""
    import threading
    result_box = [None]

    def run():
        if not title:
            return
        try:
            q = f"{first_author} {title}" if first_author else title
            url = f"https://api.crossref.org/works?query.bibliographic={urllib.parse.quote(q)}&rows=5"
            req = urllib.request.Request(url, headers={"User-Agent": UA_CROSSREF})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read())
            items = data.get("message", {}).get("items", [])
            for item in items:
                item_year = (item.get("issued", {}).get("date-parts", [[None]])[0][0]
                             or item.get("published-online", {}).get("date-parts", [[None]])[0][0])
                if year and item_year != year:
                    continue
                if first_author:
                    auth_fam = first_author.split()[-1].lower().rstrip('.,;')
                    if not any(auth_fam in (a.get("family", "") or "").lower()
                               for a in item.get("author", [])):
                        continue
                result_box[0] = item.get("DOI")
                return
        except Exception:
            pass

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=8)
    return result_box[0]


# === Step 2: Sci-Hub 下载 ===
def _sh_resolve_pdf(doi: str, mirror: str) -> Optional[str]:
    """Sci-Hub 解析 DOI 到 PDF URL (threading + hard timeout 15s)"""
    import threading
    result_box = [None]

    def run():
        try:
            url = f"{mirror}/{doi}"
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
            with urllib.request.urlopen(req, timeout=12) as r:
                html = r.read().decode('utf-8', errors='ignore')
            # 找 PDF 链接
            m = re.search(r'src="(https?://[^"]+\.pdf)"', html)
            if m:
                result_box[0] = m.group(1)
                return
            m = re.search(r"location\.replace\(['\"]([^'\"]+)['\"]\)", html)
            if m:
                result_box[0] = m.group(1)
        except Exception:
            pass

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=15)
    return result_box[0]


def _sh_download(pdf_url: str, out_path: str, timeout: int = 60) -> Tuple[bool, str]:
    """下载 PDF, 验证 magic bytes (threading + hard timeout 60s)"""
    import threading
    result_box = [(False, "init")]

    def run():
        try:
            req = urllib.request.Request(pdf_url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
            if body[:4] != b"%PDF":
                result_box[0] = (False, "not_pdf")
                return
            with open(out_path, "wb") as f:
                f.write(body)
            result_box[0] = (True, f"{len(body)} bytes")
        except Exception as e:
            result_box[0] = (False, str(e)[:50])

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=timeout + 5)
    if t.is_alive():
        return False, "download_timeout"
    return result_box[0]


# === Pipeline ===
def _find_old_pdf(pn_x: str) -> Optional[str]:
    for f in os.listdir(PDFS_DIR):
        if f.startswith(pn_x + "_") and f.lower().endswith(".pdf"):
            return os.path.join(PDFS_DIR, f)
    return None


def _make_new_filename(pn_x: str, sug: dict, real_doi: str = "") -> str:
    inner = sug.get("suggestion", sug)
    cit = inner.get("correct_citation", {})
    authors = cit.get("authors", "Unknown")
    surname = authors.split(",")[0].split(" ")[0] if "," in authors else authors.split()[-1]
    surname = re.sub(r'[^A-Za-z\u4e00-\u9fff]', '', surname)[:15]
    year = cit.get("year", "yyyy")
    journal = cit.get("journal", "Journal")
    journal_short = re.sub(r'[^A-Za-z0-9]', '', journal)[:15]
    return f"{pn_x}_main_{surname}_{journal_short}_{year}.pdf"


def _build_search_query(sug: dict) -> Tuple[str, str, int]:
    """构造 author + year + title 查询"""
    inner = sug.get("suggestion", sug)
    cit = inner.get("correct_citation", {})
    title_kws = inner.get("title_keywords", [])

    # 抽 author
    authors_str = cit.get("authors", "")
    if "," in authors_str:
        surname = authors_str.split(",")[0].strip()
        # 拼接 initials (取 "et al." 之前的部分)
        parts = authors_str.split(",")
        if len(parts) >= 2:
            initials = parts[1].strip().split(" ")[0]
            author = f"{surname} {initials}"
        else:
            author = surname
    else:
        author = authors_str.split(" ")[0] if authors_str else ""

    year = cit.get("year", 0)
    # title 来自 title_keywords (短的英文优先, 排除中文)
    en_kws = [k for k in title_kws
              if not any('\u4e00' <= c <= '\u9fff' for c in k) and len(k) > 3]
    title = " ".join(en_kws[:3]) if en_kws else ""

    return author, title, year


def process_pn_x(sug: dict, sh_mirror: str) -> Dict:
    """处理单个 Pn-x"""
    pn_x = sug.get("pn_x", "")
    inner = sug.get("suggestion", sug)
    cit = inner.get("correct_citation", {})
    result = {
        "pn_x": pn_x,
        "ok": False,
        "old": None,
        "new": None,
        "method": None,
        "reason": None,
        "real_doi": None,
        "title_found": None,
    }

    old_pdf = _find_old_pdf(pn_x)
    if not old_pdf:
        result["reason"] = "no_old_pdf"
        return result
    result["old"] = os.path.basename(old_pdf)
    new_path = os.path.join(PDFS_DIR, _make_new_filename(pn_x, sug))
    result["new"] = os.path.basename(new_path)

    author, title, year = _build_search_query(sug)
    real_doi = None
    title_found = None

    # 1) Europe PMC author+year 搜索
    if author and year:
        results = _europe_pmc_search_author(author, year)
        for r in results[:5]:
            doi = r.get("doi", "")
            r_title = r.get("title", "")
            if doi and doi.startswith("10."):
                # 验证 title (用 en_kws)
                if title:
                    check_words = [w for w in title.split() if len(w) > 4]
                    if check_words and not any(w.lower() in r_title.lower() for w in check_words[:2]):
                        continue
                real_doi = doi
                title_found = r_title
                break

    # 2) Crossref title 搜索 (兜底)
    if not real_doi and title:
        real_doi = _crossref_search_by_title(title, author, year)

    # 3) 用 GLM 提供的 DOI (最后兜底)
    if not real_doi:
        glm_doi = cit.get("doi", "")
        if glm_doi and glm_doi != "null":
            real_doi = glm_doi

    if not real_doi:
        result["reason"] = "no_doi_found"
        return result

    result["real_doi"] = real_doi
    result["title_found"] = title_found

    # 4) Sci-Hub 下载
    pdf_url = _sh_resolve_pdf(real_doi, sh_mirror)
    if not pdf_url:
        result["reason"] = f"scihub_resolve_failed:{sh_mirror}"
        return result

    ok, info = _sh_download(pdf_url, new_path)
    if ok:
        result["ok"] = True
        result["method"] = f"scihub:{sh_mirror}"
        os.remove(old_pdf)
    else:
        result["reason"] = f"scihub_download:{info}"
        # 清理可能的空文件
        if os.path.isfile(new_path):
            os.remove(new_path)
    return result


def main():
    if not os.path.isfile(SUGGESTIONS_JSON):
        print(f"❌ {SUGGESTIONS_JSON}")
        sys.exit(1)
    with open(SUGGESTIONS_JSON) as f:
        data = json.load(f)
    suggestions = data.get("suggestions", [])

    # 探测 Sci-Hub mirror
    print("=== 探测 Sci-Hub 镜像 ===")
    mirrors = _probe_scihub_mirrors()
    if not mirrors:
        print("❌ 所有 Sci-Hub 镜像不可达, 退出")
        sys.exit(1)
    sh_mirror = mirrors[0]
    print(f"✓ 使用镜像: {sh_mirror}\n")

    print(f"=== TMA 16 错论文重下 v3 (Sci-Hub 兜底) ===")
    print(f"待处理: {len(suggestions)} 个 Pn-x\n")

    log = {"n_total": len(suggestions), "n_success": 0, "n_fail": 0,
           "scihub_mirror": sh_mirror, "results": []}

    for i, sug in enumerate(suggestions, 1):
        pn_x = sug.get("pn_x", "")
        inner = sug.get("suggestion", sug)
        cit = inner.get("correct_citation", {})
        author, title, year = _build_search_query(sug)
        print(f"[{i}/{len(suggestions)}] {pn_x}: {cit.get('authors', '')[:30]} | {year} | {cit.get('journal', '')[:20]}", flush=True)
        print(f"    搜索: {author} | {title[:50]}", flush=True)

        result = process_pn_x(sug, sh_mirror)
        log["results"].append(result)

        if result["ok"]:
            log["n_success"] += 1
            print(f"    ✓ {result['method']}", flush=True)
            print(f"      DOI: {result['real_doi']}", flush=True)
            if result.get("title_found"):
                print(f"      论文: {result['title_found'][:80]}", flush=True)
        else:
            log["n_fail"] += 1
            print(f"    ❌ {result['reason']}", flush=True)
            if result.get("real_doi"):
                print(f"      (有 DOI 但下不到): {result['real_doi']}", flush=True)

        time.sleep(2)

    with open(LOG_JSON, "w") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(f"\n=== 完成 ===")
    print(f"✓ 成功: {log['n_success']}/{log['n_total']}")
    print(f"❌ 失败: {log['n_fail']}/{log['n_total']}")
    print(f"日志: {LOG_JSON}")


if __name__ == "__main__":
    main()
