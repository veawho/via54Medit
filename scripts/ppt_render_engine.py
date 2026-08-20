#!/usr/bin/env python3
"""
ppt_render_engine.py — PPT → 图片 多引擎自动渲染 (部署新系统即用)

按优先级自动接入系统可用引擎:
  1. Microsoft PowerPoint COM   (ProgID: PowerPoint.Application)
  2. WPS 演示 COM                (ProgID: KWPP.Application, 接口兼容 PowerPoint)
  3. python-pptx + Pillow 近似渲染 (兜底, 任何平台可用)

Windows: COM 真实渲染 (保真度最高); 若系统有 PowerPoint/WPS 但缺 pywin32, 自动尝试 pip 安装。
macOS/Linux: 自动降级 python-pptx 近似渲染 (可自行扩展 soffice 分支)。

用法:
  from ppt_render_engine import render_ppt_slides_auto, detect_engines
  n, engine = render_ppt_slides_auto("D:/x.pptx", "D:/out")
"""
import os, io, sys, shutil, subprocess

# 引擎探测优先级
COM_ENGINES = [
    ("PowerPoint", "PowerPoint.Application"),
    ("WPS 演示", "KWPP.Application"),
]


def _progid_available(progid):
    """注册表检查 COM ProgID 是否已注册 (Windows)"""
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, progid):
            return True
    except OSError:
        return False
    except Exception:
        return False


def _ensure_pywin32(progid_hint=""):
    """确保 win32com 可用; 检测到 COM 引擎但缺 pywin32 时自动安装"""
    try:
        import win32com.client  # noqa: F401
        return True
    except ImportError:
        pass
    if os.name != "nt":
        return False
    if progid_hint and not _progid_available(progid_hint):
        return False
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "pywin32"],
                           capture_output=True, timeout=300)
        import win32com.client  # noqa: F401
        return True
    except Exception:
        return False


def _com_probe(progid):
    """COM 试连 (会短暂启动应用), 成功返回 True"""
    try:
        import win32com.client
        app = win32com.client.DispatchEx(progid)  # DispatchEx: 强制新实例 (Dispatch 对 PowerPoint 有连接残留问题)
        try:
            app.Quit()
        except Exception:
            pass
        return True
    except Exception:
        return False


def detect_engines():
    """返回可用引擎列表 [(name, kind), ...], kind: com | python_pptx"""
    out = []
    if os.name == "nt":
        for name, progid in COM_ENGINES:
            if _progid_available(progid):
                if _ensure_pywin32(progid) and _com_probe(progid):
                    out.append((name, "com", progid))
    out.append(("python-pptx 近似渲染", "python_pptx", ""))
    return out


# ============ COM 真实渲染 ============
def render_via_com(progid, pptx_path, out_dir, width_px=1600):
    """用 PowerPoint/WPS COM 把每页 slide 导出为 PNG"""
    import win32com.client
    app = win32com.client.DispatchEx(progid)
    pres = None
    n = 0
    try:
        try:
            app.Visible = False
        except Exception:
            pass
        try:
            app.DisplayAlerts = False
        except Exception:
            pass
        pres = app.Presentations.Open(pptx_path, ReadOnly=True, Untitled=False, WithWindow=False)
        slides = pres.Slides
        total = slides.Count
        # 按页面比例求高度
        try:
            w = pres.PageSetup.SlideWidth
            h = pres.PageSetup.SlideHeight
        except Exception:
            w, h = 12192000, 6858000  # 16:9 EMU 兜底
        height_px = int(width_px * h / w) if w else int(width_px * 9 / 16)
        for i in range(1, total + 1):
            out_png = os.path.join(out_dir, "slide_%03d.png" % i)
            slides(i).Export(out_png, "PNG", width_px, height_px)
            n += 1
    finally:
        try:
            if pres is not None:
                pres.Close()
        except Exception:
            pass
        try:
            app.Quit()
        except Exception:
            pass
    return n


# ============ python-pptx 近似渲染 (兜底) ============
def render_via_python_pptx(pptx_path, out_dir, dpi=120):
    os.makedirs(out_dir, exist_ok=True)
    try:
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as e:
        print("  [warn] render 依赖缺失: %s (跳过 slide 图导出)" % e)
        return 0
    font_path = None
    for cand in [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhl.ttc", r"C:\Windows\Fonts\simhei.ttf"]:
        if os.path.exists(cand):
            font_path = cand
            break
    prs = Presentation(pptx_path)
    EMU_IN = 914400.0
    n = 0
    for idx, slide in enumerate(prs.slides, start=1):
        w = int(prs.slide_width / EMU_IN * dpi)
        h = int(prs.slide_height / EMU_IN * dpi)
        img = Image.new("RGB", (max(w, 1), max(h, 1)), "white")
        draw = ImageDraw.Draw(img)
        for shape in slide.shapes:
            try:
                if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                    bio = io.BytesIO(shape.image.blob)
                    im = Image.open(bio).convert("RGB")
                    x0 = int(shape.left / EMU_IN * dpi); y0 = int(shape.top / EMU_IN * dpi)
                    x1 = int((shape.left + shape.width) / EMU_IN * dpi)
                    y1 = int((shape.top + shape.height) / EMU_IN * dpi)
                    if x1 > x0 and y1 > y0:
                        img.paste(im.resize((x1 - x0, y1 - y0)), (x0, y0))
                elif shape.has_table:
                    tbl = shape.table
                    x0 = int(shape.left / EMU_IN * dpi); y0 = int(shape.top / EMU_IN * dpi)
                    x1 = int((shape.left + shape.width) / EMU_IN * dpi)
                    y1 = int((shape.top + shape.height) / EMU_IN * dpi)
                    draw.rectangle([x0, y0, x1, y1], outline="black")
                    rows = len(tbl.rows); cols = len(tbl.columns)
                    rh = (y1 - y0) / rows if rows else 0
                    cw = (x1 - x0) / cols if cols else 0
                    for ri in range(rows):
                        for ci in range(cols):
                            cell = tbl.cell(ri, ci)
                            txt = (cell.text or "").strip()[:40]
                            cx0 = x0 + ci * cw; cy0 = y0 + ri * rh
                            draw.rectangle([cx0, cy0, cx0 + cw, cy0 + rh], outline="black")
                            if txt:
                                fnt = ImageFont.truetype(font_path, max(int(rh * 0.5), 8)) if font_path else ImageFont.load_default()
                                draw.text((cx0 + 2, cy0 + 2), txt, fill="black", font=fnt)
                elif shape.has_text_frame:
                    txt = (shape.text_frame.text or "").strip()
                    if not txt:
                        continue
                    x0 = int(shape.left / EMU_IN * dpi); y0 = int(shape.top / EMU_IN * dpi)
                    fnt = ImageFont.truetype(font_path, 12) if font_path else ImageFont.load_default()
                    draw.text((x0 + 2, y0 + 2), txt[:200], fill="black", font=fnt)
            except Exception:
                continue
        img.save(os.path.join(out_dir, "slide_%03d.png" % idx))
        n += 1
    return n


def render_ppt_slides_auto(pptx_path, out_dir, width_px=1600):
    """自动选择引擎渲染全部 slide, 返回 (count, engine_name)"""
    os.makedirs(out_dir, exist_ok=True)
    engines = detect_engines()
    for name, kind, progid in engines:
        try:
            if kind == "com":
                print("  [render] 引擎=%s (COM %s)" % (name, progid), flush=True)
                n = render_via_com(progid, pptx_path, out_dir, width_px)
                if n > 0:
                    return n, name
            else:
                print("  [render] 引擎=%s (兜底)" % name, flush=True)
                n = render_via_python_pptx(pptx_path, out_dir)
                if n > 0:
                    return n, name
        except Exception as e:
            print("  [render] %s 失败: %s (尝试下一引擎)" % (name, str(e)[:100]), flush=True)
    return 0, "none"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("pptx")
    parser.add_argument("out_dir")
    parser.add_argument("--width", type=int, default=1600)
    ns = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    n, engine = render_ppt_slides_auto(ns.pptx, ns.out_dir, ns.width)
    print("渲染 %d 页, 引擎: %s" % (n, engine))
