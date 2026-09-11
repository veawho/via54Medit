"""PDF utility functions for extracting metadata and true page counts."""

import os
import re


def get_pdf_page_count(path: str) -> int:
    """获取指定 PDF 文献文件的真实总页数。

    按优先级尝试:
    1. PyMuPDF (fitz) —— 高亮 / 文档链路本就硬依赖它, 因此几乎总是可用, 读页数也最快
    2. pypdf —— 可选依赖 (pip install "medit-telemetry[pdf]"), 给没有 fitz 的精简环境兜底
    3. 二进制特征解析 (/Type /Pages /Count N)
    如果解析失败或文件不存在，安全回退为 1。

    注: 原先 fitz 与 pypdf 的次序相反, 而 pypdf 只是可选 extra, 于是在常规部署里首选
    分支从未命中 —— 一条不会执行的死代码。现改为「硬依赖优先, 可选依赖兜底」。
    """
    if not path or not os.path.exists(path):
        return 1

    # 1. PyMuPDF (fitz) —— 硬依赖, 通常可用
    try:
        import fitz
        with fitz.open(path) as doc:
            count = len(doc)
            if count > 0:
                return count
    except Exception:
        pass

    # 2. pypdf —— 可选依赖, 仅在 fitz 不可用时兜底
    try:
        import pypdf
        with open(path, "rb") as fp:
            reader = pypdf.PdfReader(fp, strict=False)
            count = len(reader.pages)
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
