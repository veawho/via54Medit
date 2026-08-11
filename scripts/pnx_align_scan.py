#!/usr/bin/env python3.11
"""
全量扫描所有 Pn-x main PDF vs D 列引文对齐检查.

用法:
    python3.11 pnx_align_scan.py <doc_root> [--output report.json]

输出:
    - 每个 Pn-x 的状态 (OK / MISMATCH / MISSING)
    - 不匹配项清单 (PDF 文件名不匹配 D 列引文的作者/期刊)
    - 汇总统计
"""
import sys
import re
import json
import time
from pathlib import Path
import fitz

# ========== 1. 解析 CSV ==========

def parse_csv(csv_path):
    """解析 CSV 提取每个 Pn-x 的 D 列引文 + DOI + 类型."""
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        raw = f.read()

    # 找所有 row 起始: 数字,数字,"PPT标号
    row_starts = []
    for m in re.finditer(r'(?<![,\d])(\d+,\d+),"PPT标号', raw):
        row_starts.append((m.group(1), m.start()))

    pns = {}
    for i, (row_id, start) in enumerate(row_starts):
        end = row_starts[i+1][1] if i+1 < len(row_starts) else len(raw)
        chunk = raw[start:end]

        parts = row_id.split(",")
        if len(parts) != 2:
            continue
        pnx = f"P{parts[0]}-{parts[1]}"

        # --- DOI ---
        doi_m = re.search(r'(10\.\d{4,9}/[^\s",]+)', chunk)
        doi = doi_m.group(1).rstrip(".") if doi_m else None

        # --- D 列引文 ---
        # 格式: "PPT标号...\n\n\引文 N: 作者, 期刊. 年份..."
        # 找 "引文 N:" 后面的内容
        citations = []
        for cm in re.finditer(r'引文\s*\d+:?\s*(.+?)(?:[,。，]|\n|$)', chunk):
            c = cm.group(1).strip()
            if c and len(c) > 5:
                citations.append(c)

        # 如果没找到引文格式, 找 "D 列" 字段
        # 格式: 跳过行号, 找 "PPT标号..." 后下一个引号字段
        if not citations:
            after_rowid = chunk[len(row_id)+1:]
            # 找 "PPT标号..." 字段
            pm = re.search(r'"(PPT标号[^"]*)"', after_rowid)
            if pm:
                rest = after_rowid[pm.end():]
                # 下一个逗号后的字段可能是引文
                rest = rest.lstrip(",")
                dm = re.match(r'"([^"]*)"', rest)
                if dm:
                    c_text = dm.group(1)[:100]
                    if c_text and len(c_text) > 10:
                        citations.append(c_text)

        # --- 类型 ---
        type_m = re.search(r'(会议摘要|期刊论文|会议论文|综述|政府文件|指南|书籍|学位论文|其他)', chunk)
        ref_type = type_m.group(1) if type_m else "未知"

        # --- PDF 路径 ---
        # 找 P{row_id}/P{row_id}_main_xxx.pdf
        pdf_m = re.search(r'(P\d+(?:-\d+)+)/P\1_main_[^"\s,]+\.pdf', chunk)
        csv_pdf = pdf_m.group(0) if pdf_m else None

        pns[pnx] = {
            "doi": doi,
            "citations": citations,
            "type": ref_type,
            "csv_pdf": csv_pdf,
            "row_id": row_id,
        }

    return pns


# ========== 2. 扫描 PDF ==========

def scan_pdf(pdf_path):
    """扫描一个 PDF 文件的基本信息."""
    try:
        doc = fitz.open(pdf_path)
        m = doc.metadata
        info = {
            "pages": doc.page_count,
            "title": (m.get("title") or "").strip(),
            "author": (m.get("author") or "").strip(),
            "creator": (m.get("creator") or "").strip()[:30],
            "producer": (m.get("producer") or "").strip()[:30],
            "subject": (m.get("subject") or "").strip()[:60],
            "first_text": doc[0].get_text()[:80] if doc.page_count > 0 else "",
            "file_size": pdf_path.stat().st_size,
        }
        doc.close()
        return info
    except Exception as e:
        return {"error": str(e)}


# ========== 3. 对齐检查 ==========

def check_alignment(pnx, pdf_info, csv_info):
    """检查 PDF 是否对齐 D 列引文.

    返回: {"status": "OK"/"MISMATCH"/"WARNING", "reason": str}
    """
    # 3.1 ReportLab 截图包壳检测
    producer = pdf_info.get("producer", "")
    creator = pdf_info.get("creator", "")
    is_reportlab = "reportlab" in producer.lower() or "reportlab" in creator.lower()
    is_chromium = "skia" in producer.lower() or "chromium" in creator.lower()
    pages = pdf_info.get("pages", 0)
    file_size = pdf_info.get("file_size", 0)

    if is_reportlab and pages <= 2:
        return {"status": "MISMATCH", "reason": f"ReportLab 截图包壳 ({pages}页, {file_size//1024}KB)"}

    if is_chromium and pages <= 2:
        return {"status": "MISMATCH", "reason": f"Chrome 截屏包壳 ({pages}页, {file_size//1024}KB)"}

    # 3.2 文件名 vs D 列引文检查
    csv_pdf = csv_info.get("csv_pdf", "")
    citations = csv_info.get("citations", [])

    if not citations:
        return {"status": "WARNING", "reason": "无 D 列引文数据"}

    # 从引文中提取关键词
    keywords = set()
    for c in citations:
        # 提取作者姓氏 (首词)
        author = c.split()[0] if c.split() else ""
        if author and len(author) > 2:
            keywords.add(author.lower())
        # 提取期刊名常见模式
        for j in ["lancet", "hepatology", "liver", "cancer", "asco", "esmo", "jco",
                  "clinical", "oncology", "hepatobiliary", "surgery", "nutrition",
                  "gastroenterology", "journal", "annals", "medicine", "nccn",
                  "guideline", "review", "editorial"]:
            if j in c.lower():
                keywords.add(j)

    # 从 PDF 文件名提取关键词
    fname = Path(str(csv_pdf)).stem.lower() if csv_pdf else ""
    if not fname:
        # fallback: 从 pnx 目录找
        pdf_path = pdf_info.get("_path", "")
        fname = Path(str(pdf_path)).stem.lower() if pdf_path else ""

    # 检查文件名是否包含引文关键词
    matched = []
    for kw in keywords:
        if kw in fname:
            matched.append(kw)

    if len(matched) == 0 and keywords:
        return {"status": "WARNING", "reason": f"文件名不含引文关键词 ({', '.join(list(keywords)[:3])})"}

    # 3.3 检查 PDF 文字层是否包含引文关键词
    first_text = pdf_info.get("first_text", "").lower()
    text_matched = []
    for kw in keywords:
        if kw in first_text:
            text_matched.append(kw)

    if len(text_matched) == 0 and keywords:
        return {"status": "WARNING", "reason": f"文字层不含引文关键词 (文件名含{', '.join(matched[:2])})"}

    return {"status": "OK", "reason": ""}


# ========== 4. 主逻辑 ==========

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "usage: pnx_align_scan.py <doc_root> [--output report.json]"}))
        sys.exit(1)

    doc_root = Path(sys.argv[1])
    output_path = None
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output_path = sys.argv[idx + 1]

    # 1. 解析 CSV
    csv_path = doc_root / "_citation_table" / "citation_table.csv"
    if not csv_path.exists():
        print(json.dumps({"error": f"CSV not found: {csv_path}"}))
        sys.exit(1)

    print(f"CSV: {csv_path}")
    pns = parse_csv(csv_path)
    print(f"CSV 解析: {len(pns)} 个 Pn-x")

    # 2. 扫描所有 Pn-x 源目录
    pn_dirs = sorted([d for d in doc_root.iterdir()
                      if d.is_dir() and d.name.startswith("P") and not d.name.startswith("P_")])
    print(f"源目录: {len(pn_dirs)} 个")

    results = []
    ok_count = 0
    mismatch_count = 0
    warning_count = 0
    missing_count = 0

    for pn_dir in pn_dirs:
        pnx = pn_dir.name

        # 找 main PDF (排除 wrong/backup)
        main_pdfs = sorted(pn_dir.glob("*main*.pdf"))
        main_pdf = None
        for p in main_pdfs:
            if "backup" not in p.name and "wrong" not in p.name and "deprecated" not in p.name:
                main_pdf = p
                break

        if not main_pdf:
            results.append({"pnx": pnx, "status": "MISSING", "reason": "无 main PDF"})
            missing_count += 1
            continue

        # 扫描 PDF
        pdf_info = scan_pdf(main_pdf)
        pdf_info["_path"] = str(main_pdf)

        if "error" in pdf_info:
            results.append({"pnx": pnx, "status": "ERROR", "reason": pdf_info["error"]})
            continue

        # 获取 CSV 信息
        csv_info = pns.get(pnx, {})

        # 对齐检查
        result = check_alignment(pnx, pdf_info, csv_info)
        result["pnx"] = pnx
        result["pdf_name"] = main_pdf.name
        result["pages"] = pdf_info.get("pages", 0)
        result["creator"] = pdf_info.get("creator", "")
        result["producer"] = pdf_info.get("producer", "")
        result["first_text"] = pdf_info.get("first_text", "")[:60]
        result["citations"] = csv_info.get("citations", [])
        result["doi"] = csv_info.get("doi", "")
        result["type"] = csv_info.get("type", "")

        if result["status"] == "OK":
            ok_count += 1
        elif result["status"] == "MISMATCH":
            mismatch_count += 1
        elif result["status"] == "WARNING":
            warning_count += 1

        results.append(result)

    # 3. 输出报告
    print(f"\n{'='*70}")
    print(f"扫描结果: {len(results)} 个 Pn-x")
    print(f"  ✅ OK:       {ok_count}")
    print(f"  ⚠️ WARNING:  {warning_count}")
    print(f"  ❌ MISMATCH: {mismatch_count}")
    print(f"  ❓ MISSING:  {missing_count}")
    print(f"{'='*70}")

    if mismatch_count > 0:
        print(f"\n=== ❌ MISMATCH (需要修复) ===")
        for r in results:
            if r["status"] == "MISMATCH":
                print(f"  {r['pnx']:15s} pages={r['pages']}  {r['reason']}")
                print(f"    producer={r['producer'][:30]}")
                print(f"    citations={r['citations']}")
                print(f"    first_text={r['first_text'][:40]}")

    if warning_count > 0:
        print(f"\n=== ⚠️ WARNING (需人工确认) ===")
        for r in results:
            if r["status"] == "WARNING":
                print(f"  {r['pnx']:15s} pages={r['pages']}  {r['reason']}")
                print(f"    citations={r['citations'][:2] if r['citations'] else 'N/A'}")
                print(f"    first_text={r['first_text'][:40]}")

    # 4. 输出 JSON
    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "summary": {"total": len(results), "ok": ok_count, "warning": warning_count,
                            "mismatch": mismatch_count, "missing": missing_count},
                "results": results,
            }, f, ensure_ascii=False, indent=2)
        print(f"\n详细报告已保存到: {output_path}")


if __name__ == "__main__":
    main()