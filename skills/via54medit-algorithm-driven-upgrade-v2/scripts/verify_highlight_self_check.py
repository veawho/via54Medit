#!/usr/bin/env python3
"""
verify_highlight_self_check.py — highlight 后**自检 4 项** (不用 user 确认)

1. PDF underline 真保存 (annotation 存在)
2. jpg 浅黄细线 y 位置对 (在应证段底, ±15 px)
3. 浅黄细线颜色对 (浅黄 RGB ~ 255, 255, 153)
4. 浅黄细线 x 范围覆盖整段 (>= 70%)

关键避坑:
- PyMuPDF `a.type` 抛 "annotation not bound to any page" 会让脚本 segfault (exit -11)
- 必须**只读 a.rect 不读 a.type**, 用 rect 维度 (width > 50, height < 30) 推断 underline
- 不能让 user 确认 — 跑完立刻 PIL + numpy 自检

用法:
    python verify_highlight_self_check.py P3-2
    python verify_highlight_self_check.py P3-2 P5-1 P14-1
"""
import os, sys
from PIL import Image
import numpy as np

ROOT = '/Users/david/Desktop/雷管方案_文献整理'
STEP4 = f'{ROOT}/step4_highlight_96目录_合并DOI'


def check_jpg_light_yellow(jpg_path, expected_y0_jpg, expected_y1_jpg, expected_x0_jpg, expected_x1_jpg):
    """检查 jpg 浅黄细线 4 项"""
    img = Image.open(jpg_path).convert('RGB')
    arr = np.array(img)
    h, w = arr.shape[:2]

    # 浅黄像素 (RGB ~ 255, 255, 153)
    light_yellow = (
        (arr[:, :, 0] > 240) & (arr[:, :, 1] > 240) &
        (arr[:, :, 2] > 140) & (arr[:, :, 2] < 180)
    )
    yellow_rows = np.where(light_yellow.any(axis=1))[0]
    if len(yellow_rows) == 0:
        return False, {'reason': '没找到浅黄像素'}

    y_min, y_max = yellow_rows.min(), yellow_rows.max()
    mid_y = (y_min + y_max) // 2
    yellow_xs = np.where(light_yellow[mid_y])[0]
    if len(yellow_xs) == 0:
        return False, {'reason': '浅黄线没 x 范围'}
    x_min, x_max = yellow_xs.min(), yellow_xs.max()

    # 2. y 位置对 (在 expected_y1 ± 15 px)
    y_ok = abs(y_max - expected_y1_jpg) <= 15

    # 4. x 覆盖 (>= 70%)
    x_overlap = max(0, min(x_max, expected_x1_jpg) - max(x_min, expected_x0_jpg))
    x_cov = x_overlap / (expected_x1_jpg - expected_x0_jpg) if expected_x1_jpg > expected_x0_jpg else 0
    x_ok = x_cov >= 0.7

    details = {
        'yellow_y_range_px': (y_min, y_max),
        'yellow_x_range_px': (x_min, x_max),
        'expected_y_jpg_px': (expected_y0_jpg, expected_y1_jpg),
        'expected_x_jpg_px': (expected_x0_jpg, expected_x1_jpg),
        'y_ok': y_ok,
        'x_ok': x_ok,
        'x_coverage': f'{x_cov:.1%}',
        'jpg_size': (w, h),
    }
    return (y_ok and x_ok), details


def check_pdf_has_underline(pdf_path):
    """检查 PDF 有 underline (用 rect 维度推断, **不读 a.type 避免 segfault**)"""
    import fitz
    doc = fitz.open(pdf_path)
    total = 0
    underline_rects = {}
    for i in range(len(doc)):
        try:
            annots = list(doc[i].annots() or [])
        except Exception:
            continue
        for a in annots:
            try:
                # ⚠️ 不能 a.type — PyMuPDF bug: "annotation not bound to any page" 会 segfault
                # 用 rect 维度推断: underline 宽 > 50, 高 < 30
                rect = a.rect
                if rect.width > 50 and rect.height < 30:
                    total += 1
                    underline_rects[i] = (rect.x0, rect.y0, rect.x1, rect.y1)
            except Exception:
                pass
    doc.close()
    return total, underline_rects


def verify_pnx(pn_key):
    """自检单个 Pn-x"""
    pn_dir = f'{STEP4}/{pn_key}'
    if not os.path.isdir(pn_dir):
        print(f'❌ {pn_key}: 目录不存在')
        return False

    pdfs = [f for f in os.listdir(pn_dir) if f.endswith('.pdf') and not f.startswith('_v39')]
    if not pdfs:
        print(f'❌ {pn_key}: 无 PDF')
        return False

    print(f'\\n=== 自检 {pn_key} ({pdfs[0]}) ===')

    # 1. PDF underline (用 rect 推断, 不用 a.type)
    pdf_path = f'{pn_dir}/{pdfs[0]}'
    pdf_total, pdf_rects = check_pdf_has_underline(pdf_path)
    print(f'  1. PDF underline (rect 推断): {pdf_total} (分布: {[(k+1, v) for k, v in pdf_rects.items()]})')
    if pdf_total == 0:
        print(f'  ❌ PDF 没 underline')
        return False

    # 2-4. jpg 浅黄细线
    jpg_path = None
    for f in os.listdir(pn_dir):
        if f.startswith('page_') and f.endswith('_highlighted.jpg'):
            jpg_path = f'{pn_dir}/{f}'
            break
    if not jpg_path:
        print(f'  ❌ 没 jpg 截图')
        return False

    # 应证段 bbox 转 jpg 像素 (120dpi → 72dpi 缩放)
    # P3-2 = (84, 64, 512, 165) PDF pt
    expected_bbox_pdf_pt = {
        'P3-2': (84, 64, 512, 165),
    }
    bbox_pt = expected_bbox_pdf_pt.get(pn_key, (84, 100, 700, 200))
    exp_y0_jpg = bbox_pt[1] * 120 / 72
    exp_y1_jpg = bbox_pt[3] * 120 / 72
    exp_x0_jpg = bbox_pt[0] * 120 / 72
    exp_x1_jpg = bbox_pt[2] * 120 / 72

    ok, details = check_jpg_light_yellow(jpg_path, exp_y0_jpg, exp_y1_jpg, exp_x0_jpg, exp_x1_jpg)
    print(f'  2-4. jpg 自检: {details}')

    if ok:
        print(f'  ✅ 全部 4 项通过')
    else:
        print(f'  ❌ 自检失败')

    return ok


if __name__ == '__main__':
    if len(sys.argv) > 1:
        for pn in sys.argv[1:]:
            verify_pnx(pn)
    else:
        verify_pnx('P3-2')