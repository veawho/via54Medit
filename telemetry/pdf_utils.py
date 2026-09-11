"""PDF utility functions for extracting metadata and true page counts."""

import os
import re


def get_pdf_page_count(path: str) -> int:
    """获取指定 PDF 文献文件的真实总页数。

    按优先级尝试:
    1. pypdf (高效、Python 原生支持)
    2. fitz (PyMuPDF)
    3. 二进制特征解析 (/Type /Pages /Count N)
    如果解析失败或文件不存在，安全回退为 1。
    """
    if not path or not os.path.exists(path):
        return 1

    # 1. pypdf
    try:
        import pypdf
        with open(path, "rb") as fp:
            reader = pypdf.PdfReader(fp, strict=False)
            count = len(reader.pages)
            if count > 0:
                return count
    except Exception:
        pass

    # 2. PyMuPDF (fitz)
    try:
        import fitz
        with fitz.open(path) as doc:
            count = len(doc)
            if count > 0:
                return count
    except Exception:
        pass

    # 3. 二进制特征解析
    try:
        with open(path, "rb") as f:
            data = f.read(5 * 1024 * 1024)
            matches = re.findall(rb"/Count\s+(\d+)", data)
            if matches:
                valid_counts = [int(m) for m in matches if 0 < int(m) < 100000]
                if valid_counts:
                    return max(valid_counts)
    except Exception:
        pass

    return 1
