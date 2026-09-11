#!/usr/bin/env python3
"""
unified_render_engine.py — Step 1: 源文件全格式统一分页渲染器

支持格式:
  - PPT / PPTX : **只用 Microsoft PowerPoint** —— Windows 走 COM, macOS 走原生 AppleScript。
    按 2026-08-05 用户硬规则 (2026-09-11 重申) 禁用其它渲染通道: Keynote / LibreOffice /
    WPS / python-pptx 会导致字体与布局和原版不一致, 故**不做默认也不做兜底**;
    PowerPoint 不可用时直接失败。实际渲染委托给 ppt_render_engine.render_ppt_slides_auto()。
  - Word (DOC / DOCX) : **只用 Microsoft Word** —— Windows 走 COM, macOS 走原生 AppleScript。
    同一条保真标准同样适用: 会改版式的 LibreOffice headless 与"python-docx 拼简易 PDF"
    都已按规范删除, 拿不到 Word 就失败。
  - PDF : PyMuPDF (fitz) 高精度渲染
  - 图片 (PNG / JPG / JPEG / WEBP / TIFF / BMP) : 直接转换为标准 RGB PNG

输出: 标准分页图像序列 (page_001.png, page_002.png, ...) 及元数据清单
"""
import os
import sys
import shutil
import tempfile
import subprocess
from typing import Dict, List, Tuple, Optional, Any

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import pymupdf as fitz
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


def _docx_to_pdf_macos(docx_path: str, pdf_path: str) -> bool:
    """macOS: 用**原生 Microsoft Word** 把文档导出为 PDF。"""
    scpt = f'''
    tell application "Microsoft Word"
        set myDoc to open file (POSIX file "{os.path.abspath(docx_path)}")
        save as myDoc file name (POSIX file "{os.path.abspath(pdf_path)}") file format format PDF
        close myDoc saving no
    end tell
    '''
    try:
        r = subprocess.run(["osascript", "-e", scpt], capture_output=True, timeout=90)
    except Exception as e:
        print(f"  [render] Word AppleScript 执行失败: {e}")
        return False
    if r.returncode != 0:
        err = (r.stderr or b"").decode("utf-8", "replace")[:200]
        print(f"  [render] Word AppleScript 失败: {err}")
        return False
    return os.path.exists(pdf_path)


def _docx_to_pdf_com(docx_path: str, pdf_path: str) -> bool:
    """Windows: 用 Word COM 导出 PDF (``wdFormatPDF`` = 17)。"""
    try:
        import win32com.client
    except ImportError:
        print("  [render] 缺 pywin32 —— 无法用 Word COM 导出 PDF。")
        return False
    try:
        app = win32com.client.DispatchEx("Word.Application")
        doc = None
        try:
            try:
                app.Visible = False
                app.DisplayAlerts = False
            except Exception:
                pass
            doc = app.Documents.Open(os.path.abspath(docx_path), ReadOnly=True)
            doc.SaveAs(os.path.abspath(pdf_path), 17)
        finally:
            try:
                if doc is not None:
                    doc.Close(False)
            except Exception:
                pass
            try:
                app.Quit()
            except Exception:
                pass
    except Exception as e:
        print(f"  [render] Word COM 导出失败: {e}")
        return False
    return os.path.exists(pdf_path)


def render_docx_to_images(docx_path: str, out_dir: str, dpi: int = 150) -> List[str]:
    """把 Word (DOCX/DOC) 渲染为分页图片 —— **版式只由 Microsoft Word 产出**。

    与 PPT 同一条判定标准(见 ``docs/ppt-render-fidelity.md``): 会**重新排版**的第三方引擎
    一律不用。Word 的"源应用本体"就是 Microsoft Word, 所以:

      * Windows -> Word COM 导出 PDF;
      * macOS   -> 原生 Word AppleScript 导出 PDF;
      * 其它平台 -> **直接失败**, 不退回 LibreOffice。

    原先这里还有两条会**改版式**的路, 已按规范删除:
      1. LibreOffice headless 转 PDF —— 换了个排版引擎;
      2. 用 python-docx 抽段落拼一张"简易 PDF" —— 版式与原文档完全不同, 比前者更不准。
    两者都是"近似渲染", 与"不改变原文档的版式与文字"冲突; 宁可失败也不产出近似品。
    """
    os.makedirs(out_dir, exist_ok=True)
    tmp_pdf_dir = tempfile.mkdtemp(prefix="docx_render_")
    tmp_pdf = os.path.join(tmp_pdf_dir, "doc.pdf")
    try:
        if os.name == "nt":
            ok = _docx_to_pdf_com(docx_path, tmp_pdf)
        elif sys.platform == "darwin":
            ok = _docx_to_pdf_macos(docx_path, tmp_pdf)
        else:
            print("  [render] 本平台没有 Microsoft Word 通道 —— 版式必须由 Word 本体产出、"
                  "不用会重排的第三方引擎, 故不降级。"
                  "(请在 Windows/macOS 上渲染, 或先用 Word 另存为 PDF 再传入。)")
            return []
        if not ok or not os.path.exists(tmp_pdf):
            print("  [render] Microsoft Word 未能导出 PDF —— 按规范不切换其它渲染方式。")
            return []
        return render_pdf_to_images(tmp_pdf, out_dir, dpi=dpi)
    finally:
        shutil.rmtree(tmp_pdf_dir, ignore_errors=True)


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
            "engine": "Microsoft Word"
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
