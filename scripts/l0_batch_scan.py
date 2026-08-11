#!/usr/bin/env python3.11
"""
L0 批量扫描: 给可疑 Pn-x 拉 DOI, 调 Crossref 验证真实性.

Usage:
    python3.11 l0_batch_scan.py <doc_root> <output_json>

设计: 用户 2026-08-01 批评 v3.9 P22-1 main PDF 是截图包壳.
   本脚本扫描所有 placeholder_count >= 3 的 PDF, 然后对有 DOI 的
   调 Crossref API 做 L0 深度验证 (耗时约 0.5s/个).
"""
import sys
import json
import re
import time
import urllib.request
import urllib.error
from pathlib import Path
import fitz


def is_placeholder(s):
    """检查 metadata 字段是否被填充."""
    if not s or not s.strip():
        return True
    placeholders = {
        "untitled", "anonymous", "unspecified", "n/a", "na",
        "anon", "unknown", "test", "placeholder", "default",
        "匿名", "未指定", "无标题", "未知",
    }
    return s.strip().lower() in placeholders


def get_pdf_metadata(pdf_path):
    """抽 PDF metadata, 返回 dict."""
    try:
        doc = fitz.open(pdf_path)
        m = doc.metadata
        return {
            "title": m.get("title", "") or "",
            "author": m.get("author", "") or "",
            "subject": m.get("subject", "") or "",
            "creator": m.get("creator", "") or "",
            "creation": m.get("creationDate", "") or "",
        }
    except Exception as e:
        return {"error": str(e)}


def extract_pn_meta_from_csv(csv_path):
    """从 CSV 提取每个 Pn-x 的 DOI 和 main PDF.

    CSV 格式: '<ppt_id>,"<description>","<citation>","<doi>","<type>","<main_pdf>",...'
    但实际是单物理行, 字段用逗号分, 字段内换行用 \\n.
    """
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        raw = f.read()

    # 按 ',"PNcsvmark' 类似边界粗切, 不太可靠. 改用启发式:
    # 找所有 Pn-x/Pn-x_main_xxx.pdf 配对 + 紧随其前的 DOI
    # 但 pdf 命名差异大, 改用 '<row_id>,' 开头匹配.

    # 简单方案: 找规律 "P3-2,DOI10...," 类似, 但 ppt_id 实际是 "3,2"
    # 实际 row 起始: ^(\d+),(\d+),"PPT...
    # 我们要 Pn-x 形式, 即 <pn>-<x> = "P" + digit1 + "-" + digit2
    # PPT row 第一字段是 "3,2" = 3-2 = P3-2

    # 1. 找所有 row 起始
    row_starts = []
    pattern = re.compile(r'(?<![,\d])(\d+,\d+),"PPT标号', re.MULTILINE)
    for m in pattern.finditer(raw):
        row_starts.append((m.group(1), m.start()))

    # 2. 对每 row 提取 DOI 和 main PDF
    pns = {}  # Pn-x -> {doi, pdf}
    for i, (row_id, start) in enumerate(row_starts):
        end = row_starts[i+1][1] if i+1 < len(row_starts) else len(raw)
        chunk = raw[start:end]

        # DOI
        doi_match = re.search(r'(10\.\d{4,9}/[^\s",]+)', chunk)
        doi = doi_match.group(1).rstrip('.') if doi_match else None

        # main PDF (Pnx/pnx_main_xxx.pdf)
        pdf_match = re.search(r'(P\d+(?:-\d+)+)/P\1_main_[^"\s,]+\.pdf', chunk)
        pdf = pdf_match.group(0) if pdf_match else None

        # 构造 Pn-x
        parts = row_id.split(",")
        if len(parts) == 2:
            pnx = f"P{parts[0]}-{parts[1]}"
            pns[pnx] = {"doi": doi, "pdf": pdf, "row_id": row_id}

    return pns


def fetch_crossref(doi):
    """调 Crossref API 查 DOI 元数据."""
    cleaned = doi.replace("https://doi.org/", "").replace("http://doi.org/", "")
    url = f"https://api.crossref.org/works/{cleaned}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "via54Medit/0.1 (research)"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status != 200:
                return {"error": f"status {resp.status}"}
            data = json.loads(resp.read())
            msg = data.get("message", {})
            return {
                "title": (msg.get("title") or [""])[0],
                "authors": [a.get("family", "") for a in msg.get("author", []) if a.get("family")],
                "published": msg.get("published", {}).get("date-parts", [[None, None, None]])[0],
                "container": (msg.get("container-title") or [""])[0],
            }
    except urllib.error.URLError as e:
        return {"error": f"network: {e}"}
    except Exception as e:
        return {"error": str(e)}


def jaccard(a, b):
    """Jaccard 词集合相似度."""
    def tokenize(s):
        stop = {"a", "an", "the", "of", "in", "on", "and", "or", "is", "are", "was", "were",
                "with", "from", "for", "to", "by", "at", "的", "在", "和", "与", "是", "了"}
        s = re.sub(r'[^\w\s\u4E00-\u9FFF]', ' ', s.lower())
        return [w for w in s.split() if w and w not in stop and len(w) > 1]

    if not a or not b:
        return 0.0
    ta, tb = set(tokenize(a)), set(tokenize(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def l0_verify(pdf_meta, crossref):
    """L0 4 维评分."""
    if "error" in crossref:
        return {"score": 0.0, "verified": False, "issue": crossref["error"]}

    title_sim = jaccard(pdf_meta.get("title", ""), crossref.get("title", ""))

    # Author match
    pdf_author = pdf_meta.get("author", "").lower()
    ref_authors = [a.lower() for a in crossref.get("authors", []) if a]
    author_sim = 0.0
    for ref in ref_authors:
        if ref in pdf_author:
            author_sim = 1.0
            break

    # Date match
    creation = pdf_meta.get("creation", "")
    ref_date = crossref.get("published", [None, None, None])
    date_match = 0.5
    if ref_date[0] and creation:
        # PDF creation format: "D:20251106015129+05'30'"
        m = re.search(r'(\d{4})(\d{2})(\d{2})', creation)
        if m:
            try:
                pdf_year = int(m.group(1))
                ref_year = ref_date[0]
                if pdf_year >= ref_year:
                    date_match = 1.0
                else:
                    date_match = 0.0
            except Exception:
                pass

    # Meta completeness
    filled = 0
    total = 4
    for k in ["title", "author", "subject", "creator"]:
        v = pdf_meta.get(k, "")
        if v and not is_placeholder(v):
            filled += 1
    meta_compl = filled / total

    score = 0.45 * title_sim + 0.30 * author_sim + 0.15 * date_match + 0.10 * meta_compl
    verified = score >= 0.70

    issue = ""
    if title_sim < 0.30:
        issue = f"Title mismatch (sim={title_sim:.2f}): PDF={pdf_meta.get('title', '')[:50]!r} vs Ref={crossref.get('title', '')[:50]!r}"
    elif author_sim < 0.5 and ref_authors:
        issue = f"Author mismatch: PDF={pdf_meta.get('author', '')[:30]!r} vs Ref[0]={ref_authors[0]!r}"

    return {
        "score": score,
        "verified": verified,
        "title_sim": title_sim,
        "author_sim": author_sim,
        "date_match": date_match,
        "meta_compl": meta_compl,
        "issue": issue,
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "missing doc_root"}))
        sys.exit(1)

    doc_root = Path(sys.argv[1])
    csv_path = doc_root / "_citation_table" / "citation_table.csv"
    if not csv_path.exists():
        print(json.dumps({"error": f"csv not found: {csv_path}"}))
        sys.exit(1)

    print(f"## L0 批量扫描启动: {doc_root}")
    print(f"   CSV: {csv_path}")

    # 1. 解析 CSV -> Pn-x -> {doi, pdf}
    pns = extract_pn_meta_from_csv(csv_path)
    print(f"   解析 CSV: {len(pns)} 个 Pn-x")

    # 2. 扫描所有 main PDF
    pn_dirs = sorted([d for d in doc_root.iterdir() if d.is_dir() and d.name.startswith("P")])
    print(f"   扫描源目录: {len(pn_dirs)} 个 Pn-x 目录")

    # 3. 找出 placeholder 多的 PDF
    suspicious = []
    for pn_dir in pn_dirs:
        main_pdfs = sorted(pn_dir.glob("*main*.pdf"))
        for pdf in main_pdfs:
            meta = get_pdf_metadata(pdf)
            if "error" in meta:
                continue
            ph_count = sum([
                is_placeholder(meta.get("title", "")),
                is_placeholder(meta.get("author", "")),
                is_placeholder(meta.get("subject", "")),
                is_placeholder(meta.get("creator", "")),
            ])
            if ph_count >= 3:
                pnx = pn_dir.name
                doi = pns.get(pnx, {}).get("doi")
                suspicious.append({
                    "pnx": pnx,
                    "pdf": str(pdf),
                    "csv_doi": doi,
                    "csv_main_pdf": pns.get(pnx, {}).get("pdf"),
                    "ph_count": ph_count,
                    "title": meta.get("title", "")[:60],
                    "author": meta.get("author", "")[:30],
                    "creator": meta.get("creator", "")[:30],
                })

    print(f"   可疑 PDF: {len(suspicious)} 个 (placeholder_count >= 3)")

    # 4. 对有 DOI 的做 L0 深度验证
    with_doi = [s for s in suspicious if s.get("csv_doi")]
    print(f"   有 DOI 的: {len(with_doi)} 个, 开始 L0 深度验证 (Crossref API 调用)")

    for i, item in enumerate(with_doi):
        print(f"   [{i+1}/{len(with_doi)}] L0 verify {item['pnx']} (DOI: {item['csv_doi'][:30]})...", end=" ")
        meta = get_pdf_metadata(item["pdf"])
        crossref = fetch_crossref(item["csv_doi"])
        result = l0_verify(meta, crossref)
        item["l0_result"] = result
        if result["verified"]:
            print(f"✅ verified=True, score={result['score']:.2f}")
        else:
            print(f"❌ verified=False, score={result['score']:.2f}, issue={result['issue'][:60]!r}")
        time.sleep(0.2)  # Crossref 礼貌节流

    # 5. 报告
    print()
    print("=" * 70)
    print("## L0 验证结果")
    print("=" * 70)

    verified_count = sum(1 for s in with_doi if s.get("l0_result", {}).get("verified"))
    rejected_count = len(with_doi) - verified_count
    print(f"有 DOI 的 {len(with_doi)} 个: ✅ {verified_count} verified, ❌ {rejected_count} rejected")
    print(f"无 DOI 的 {len(suspicious) - len(with_doi)} 个: 需要人工判断 (可能是政府文件/中文期刊)")
    print()

    if rejected_count > 0:
        print("## ⚠️ 真正的 P22-1 同类陷阱 (L0 拒绝):")
        for s in with_doi:
            r = s.get("l0_result", {})
            if not r.get("verified"):
                print(f"  - {s['pnx']:15s} score={r['score']:.2f}  {r['issue'][:80]}")

    # 6. 输出 JSON
    if len(sys.argv) >= 3:
        out_path = sys.argv[2]
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(suspicious, f, ensure_ascii=False, indent=2)
        print(f"\n详细结果写入: {out_path}")


if __name__ == "__main__":
    main()
