#!/usr/bin/env python3.11
"""
L0 PDF metadata extraction for via54Medit.

Usage:
    python3.11 l0_extract_pdf_meta.py <pdf_path>

Output: JSON to stdout with keys: title, author, subject, creator, creation

Used by: medit anno2ppt l0verify
"""
import sys
import json
import fitz


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "missing pdf_path argument"}))
        sys.exit(1)

    pdf_path = sys.argv[1]
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(json.dumps({"error": f"open failed: {e}"}))
        sys.exit(1)

    m = doc.metadata
    out = {
        "title": m.get("title", "") or "",
        "author": m.get("author", "") or "",
        "subject": m.get("subject", "") or "",
        "creator": m.get("creator", "") or "",
        "creation": m.get("creationDate", "") or "",
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
