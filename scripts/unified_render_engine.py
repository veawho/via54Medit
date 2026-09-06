#!/usr/bin/env python3
"""
unified_render_engine.py — Step 1: 源文件全格式统一分页渲染器

支持格式:
  - PPT / PPTX : Microsoft PowerPoint COM (Windows) / macOS 原生 AppleScript / LibreOffice / python-pptx
  - Word (DOC / DOCX) : Microsoft Word COM / macOS AppleScript / LibreOffice headless / docx2pdf
  - PDF : PyMuPDF (fitz) 高精度渲染
  - 图片 (PNG / JPG / JPEG / WEBP / TIFF / BMP) : 直接转换为标准 RGB PNG

输出: 标准分页图像序列 (page_001.png, page_002.png, ...) 及元数据清单
"""
import os
import sys
import shutil
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import fitz
from PIL import Image
from ppt_render_engine import render_ppt_slides_auto


def render_pdf_to_images(pdf_path: str, out_dir: str, dpi: int = 150) -> List[str]:
    """将 PDF 渲染为分页 PNG 图像"""
    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    img_paths = []
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    for pi in range(len(doc)):
        page = doc[pi]
        pix = page.get_pixmap(matrix=mat)
        out_img = os.path.join(out_dir, f"page_{pi+1:03d}.png")
        pix.save(out_img)
        img_paths.append(out_img)
    doc.close()
    return img_paths


def render_image_file_to_page(img_path: str, out_dir: str) -> List[str]:
    """将单张或多张静态图片规范化为标准分页图"""
    os.makedirs(out_dir, exist_ok=True)
    out_img = os.path.join(out_dir, "page_001.png")
    with Image.open(img_path) as im:
        im.convert("RGB").save(out_img, "PNG")
    return [out_img]


def render_docx_to_images(docx_path: str, out_dir: str, dpi: int = 150) -> List[str]:
    """将 Word (DOCX/DOC) 转换为 PDF 后渲染为分页图片"""
    os.makedirs(out_dir, exist_ok=True)
    tmp_pdf_dir = tempfile.mkdtemp(prefix="docx_render_")
    
    # 策略 1: LibreOffice 转 PDF
    soffice_bin = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice_bin and sys.platform == "darwin":
        cand = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
        if os.path.exists(cand):
            soffice_bin = cand
            
    if soffice_bin:
        try:
            r = subprocess.run([
                soffice_bin, "--headless", "--convert-to", "pdf",
                "--outdir", tmp_pdf_dir, docx_path
            ], capture_output=True, timeout=90)
            if r.returncode == 0:
                pdfs = list(Path(tmp_pdf_dir).glob("*.pdf"))
                if pdfs:
                    res = render_pdf_to_images(str(pdfs[0]), out_dir, dpi=dpi)
                    shutil.rmtree(tmp_pdf_dir, ignore_errors=True)
                    return res
        except Exception:
            pass

    # 策略 2: macOS Word AppleScript
    if sys.platform == "darwin":
        try:
            tmp_pdf = os.path.join(tmp_pdf_dir, "doc.pdf")
            scpt = f'''
            tell application "Microsoft Word"
                set myDoc to open file (POSIX file "{os.path.abspath(docx_path)}")
                save as myDoc file name (POSIX file "{os.path.abspath(tmp_pdf)}") file format format PDF
                close myDoc saving no
            end tell
            '''
            r = subprocess.run(["osascript", "-e", scpt], capture_output=True, timeout=60)
            if r.returncode == 0 and os.path.exists(tmp_pdf):
                res = render_pdf_to_images(tmp_pdf, out_dir, dpi=dpi)
                shutil.rmtree(tmp_pdf_dir, ignore_errors=True)
                return res
        except Exception:
            pass

    # 策略 3: python-docx 提取段落生成简易 PDF (兜底)
    try:
        from docx import Document
        doc = Document(docx_path)
        pdf_doc = fitz.open()
        page = pdf_doc.new_page(width=595, height=842)
        y = 50
        for p in doc.paragraphs:
            txt = p.text.strip()
            if not txt:
                continue
            if y > 780:
                page = pdf_doc.new_page(width=595, height=842)
                y = 50
            page.insert_text(fitz.Point(50, y), txt[:120], fontsize=11)
            y += 18
        tmp_pdf = os.path.join(tmp_pdf_dir, "doc_fallback.pdf")
        pdf_doc.save(tmp_pdf)
        pdf_doc.close()
        res = render_pdf_to_images(tmp_pdf, out_dir, dpi=dpi)
        shutil.rmtree(tmp_pdf_dir, ignore_errors=True)
        return res
    except Exception as e:
        shutil.rmtree(tmp_pdf_dir, ignore_errors=True)
        print(f"  [render] DOCX 渲染遇到错误: {e}")
        return []


def render_source_file(source_path: str, out_dir: str, dpi: int = 150) -> Dict[str, Any]:
    """
    Step 1 统一入口: 传入任意源文件 (PPT/DOCX/PDF/图片)，统一渲染为分页图片序列。
    
    返回:
    {
        "success": bool,
        "source_path": str,
        "file_type": "pptx|docx|pdf|image",
        "page_count": int,
        "page_images": ["path/to/page_001.png", ...],
        "engine": str
    }
    """
    if not os.path.exists(source_path):
        return {"success": False, "error": f"File not found: {source_path}", "page_images": [], "page_count": 0}

    os.makedirs(out_dir, exist_ok=True)
    ext = os.path.splitext(source_path)[1].lower()

    # 1. PPT / PPTX
    if ext in (".pptx", ".ppt"):
        count, engine = render_ppt_slides_auto(source_path, out_dir)
        # 获取生成的标准 slide_*.png 并重命名或映射为 page_*.png
        page_imgs = []
        for i in range(1, count + 1):
            s_img = os.path.join(out_dir, f"slide_{i:03d}.png")
            p_img = os.path.join(out_dir, f"page_{i:03d}.png")
            if os.path.exists(s_img):
                if not os.path.exists(p_img):
                    shutil.copy2(s_img, p_img)
                page_imgs.append(p_img)
        return {
            "success": len(page_imgs) > 0,
            "source_path": source_path,
            "file_type": "pptx",
            "page_count": len(page_imgs),
            "page_images": page_imgs,
            "engine": engine
        }

    # 2. PDF
    if ext == ".pdf":
        page_imgs = render_pdf_to_images(source_path, out_dir, dpi=dpi)
        return {
            "success": len(page_imgs) > 0,
            "source_path": source_path,
            "file_type": "pdf",
            "page_count": len(page_imgs),
            "page_images": page_imgs,
            "engine": "PyMuPDF"
        }

    # 3. Word DOCX / DOC
    if ext in (".docx", ".doc"):
        page_imgs = render_docx_to_images(source_path, out_dir, dpi=dpi)
        return {
            "success": len(page_imgs) > 0,
            "source_path": source_path,
            "file_type": "docx",
            "page_count": len(page_imgs),
            "page_images": page_imgs,
            "engine": "Word/LibreOffice"
        }

    # 4. 图片格式
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"):
        page_imgs = render_image_file_to_page(source_path, out_dir)
        return {
            "success": len(page_imgs) > 0,
            "source_path": source_path,
            "file_type": "image",
            "page_count": len(page_imgs),
            "page_images": page_imgs,
            "engine": "PIL"
        }

    return {"success": False, "error": f"Unsupported format: {ext}", "page_images": [], "page_count": 0}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 unified_render_engine.py <source_file> <out_dir>")
        sys.exit(1)
    res = render_source_file(sys.argv[1], sys.argv[2])
    print(f"Rendered {res.get('page_count')} pages with engine {res.get('engine')}")
