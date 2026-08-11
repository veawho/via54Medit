#!/usr/bin/env python3.11
"""
L0 扫描: 列出所有 Pn-x main PDF 的 metadata,
快速检测哪些是 placeholder (untitled / anonymous / unspecified).

Usage:
    python3.11 l0_screen_scan.py <root_dir>

Output: JSON 数组 [{pnx, pdf, title, author, subject, creator, is_placeholder}, ...]
"""
import sys
import json
import re
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


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "missing root_dir"}))
        sys.exit(1)

    root = Path(sys.argv[1])
    if not root.exists():
        print(json.dumps({"error": f"root not found: {root}"}))
        sys.exit(1)

    results = []
    # 扫描所有 Pn-x 目录
    pn_dirs = sorted([d for d in root.iterdir() if d.is_dir() and d.name.startswith("P")])
    for pn_dir in pn_dirs:
        # 找 main PDF
        main_pdfs = sorted(pn_dir.glob("*main*.pdf"))
        if not main_pdfs:
            continue
        for pdf in main_pdfs:
            try:
                doc = fitz.open(pdf)
                m = doc.metadata
                title = m.get("title", "") or ""
                author = m.get("author", "") or ""
                subject = m.get("subject", "") or ""
                creator = m.get("creator", "") or ""
                creation = m.get("creationDate", "") or ""

                # 统计 placeholder 字段数
                ph_count = sum([
                    is_placeholder(title),
                    is_placeholder(author),
                    is_placeholder(subject),
                    is_placeholder(creator),
                ])

                # 关键: 4 字段都 placeholder 就是包壳 PDF
                is_suspicious = ph_count >= 3

                results.append({
                    "pnx": pn_dir.name,
                    "pdf": str(pdf),
                    "title": title[:80] + ("..." if len(title) > 80 else ""),
                    "author": author,
                    "subject": subject[:80] + ("..." if len(subject) > 80 else ""),
                    "creator": creator,
                    "creation": creation,
                    "placeholder_count": ph_count,
                    "is_suspicious": is_suspicious,  # 关键标记
                })
            except Exception as e:
                results.append({
                    "pnx": pn_dir.name,
                    "pdf": str(pdf),
                    "error": f"open failed: {e}",
                })

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
