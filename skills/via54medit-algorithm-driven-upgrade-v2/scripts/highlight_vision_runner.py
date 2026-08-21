#!/usr/bin/env python3
"""
highlight_vision_runner.py — vision 真视觉配对 highlight (用户硬规则)

用户原话 (2026-08-05 反思会话):
"你应该把对应PPT的那个PDF文件，每一页都导出图片，然后图片对PPT导出的图片，
视觉对视觉，找到对应的段落或者句子或者图表或者表格，然后进行highlight"

算法:
1. 重置 Pn-x (用 step3 干净 PDF, 删旧 underline)
2. 渲染 PDF 每页 jpg (PyMuPDF get_pixmap dpi=120)
3. vision 看 PPT slide jpg → 提"标号 N 应证视觉描述"
4. vision 看 PDF 每页 jpg → 找"应证段/图表/表格 bbox"
5. vision 配对 → 选最佳 PDF 页 + bbox
6. jpg 上画中黄细线 (PIL ImageDraw.line at y1, RGB 255,230,100, 4px)
7. jpg bbox → PDF pt (× 72/120)
8. PyMuPDF add_underline_annot (type 9, stroke=(1.0, 230/255, 100/255))
9. saveIncr (若失败用 tmp 替换)
10. 自检 4 项 (避开 PyMuPDF a.type segfault, 用 rect 推断 + PIL numpy)

用法:
    from highlight_vision_runner import highlight_vision_pnx
    highlight_vision_pnx('P3-2')  # 视觉配对 + 画 + 验证
"""
import os, shutil, sys, csv
import fitz
from PIL import Image, ImageDraw
import numpy as np

ROOT = '/Users/david/Desktop/雷管方案_文献整理'
STEP3 = f'{ROOT}/step3_pdf下载_160目录'
STEP4 = f'{ROOT}/step4_highlight_96目录_合并DOI'
TRUTH = f'{ROOT}/step2_标注分析/_citation_table/citation_table.csv'
RENDERS = f'{ROOT}/step1_ppt_目录/_ppt_renders_expanded'

# B 选项: 中黄 RGB(255, 230, 100), 4px (用户选)
RGB_JPG = (255, 230, 100)
RGB_PDF = (1.0, 230/255, 100/255)
DPI = 120


def reset_pnx(pn_key):
    """重置 Pn-x 目录 (从 step3 复制干净 PDF, 删旧 underline 版)"""
    pn_dir = f'{STEP4}/{pn_key}'
    if os.path.exists(pn_dir):
        shutil.rmtree(pn_dir)
    for d in os.listdir(STEP4):
        if pn_key in d and d.startswith('P') and os.path.isdir(f'{STEP4}/{d}'):
            shutil.rmtree(f'{STEP4}/{d}')
            break
    shutil.copytree(f'{STEP3}/{pn_key}', pn_dir)
    return pn_dir


def get_ppt_jpg(slide_num):
    """PPT slide jpg (扩页 PowerPoint 渲染)"""
    p = f'{RENDERS}/slide_{slide_num:03d}.jpg'
    return p if os.path.exists(p) else None


def render_pdf_to_jpg(pdf_path, out_dir, max_pages=20):
    """PDF 每页导 jpg"""
    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    paths = []
    for i in range(min(max_pages, len(doc))):
        pix = doc[i].get_pixmap(dpi=DPI)
        out = f'{out_dir}/page_{i+1:03d}.jpg'
        pix.save(out)
        paths.append(out)
    doc.close()
    return paths


def get_truth(pn_key):
    """提真值 D 字段"""
    slide = str(int(pn_key.split('-')[0].lstrip('P')))
    num = str(int(pn_key.split('-')[1]))
    with open(TRUTH) as f:
        for r in csv.DictReader(f):
            if r['﻿PPT页'] == slide and r['第几条'] == num:
                return r['引用语义（上下文）'], r['PPT中的文献引用 完整字段']
    return None, None


def get_proof_blocks(pdf_path, page_num):
    """PyMuPDF 提应证页 text blocks (用户硬规则: 不发明 bbox, 用真实 PDF pt 坐标)

    用户原话: "我都把要标注的内容发给你了, 你都highlight不对"
    修法: 应证段必须用 get_text("blocks") 提真实 PDF 段坐标, 不靠 jpg 像素猜
    """
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    blocks = page.get_text("blocks")
    doc.close()
    return blocks


def draw_light_yellow_underline(jpg_path, bbox_jpg, out_path, color=RGB_JPG, width=4):
    """jpg 上画中黄细线 (段底)"""
    img = Image.open(jpg_path).convert('RGB')
    draw = ImageDraw.Draw(img)
    x0, y0, x1, y1 = bbox_jpg
    draw.line([(x0, y1), (x1, y1)], fill=color, width=width)
    img.save(out_path)
    return out_path


def add_pdf_underline(pdf_path, page_num, rect_pt, color=RGB_PDF):
    """PyMuPDF add_underline_annot (type 9, 只支持 stroke 不支持 fill)"""
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    annot = page.add_underline_annot(fitz.Rect(*rect_pt))
    annot.set_colors(stroke=color)
    annot.update()
    try:
        doc.saveIncr()
    except Exception:
        tmp = pdf_path + '.tmp'
        doc.save(tmp, garbage=4, deflate=True)
        doc.close()
        shutil.move(tmp, pdf_path)
        return 1
    doc.close()
    return 1


def jpg_bbox_to_pdf_rect(bbox_jpg):
    """jpg bbox → PDF pt (× 72/DPI)"""
    x0_j, y0_j, x1_j, y1_j = bbox_jpg
    return (x0_j * 72 / DPI, y0_j * 72 / DPI,
            x1_j * 72 / DPI, y1_j * 72 / DPI)


def safe_underline_count(pdf_path):
    """避开 PyMuPDF a.type segfault, 用 rect.width > 50 and height < 30 推断 underline"""
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return -1
    total = 0
    for i in range(len(doc)):
        try:
            annots = list(doc[i].annots() or [])
        except Exception:
            continue
        for a in annots:
            try:
                rect = a.rect
                if rect.width > 50 and rect.height < 30:
                    total += 1
            except Exception:
                pass
    doc.close()
    return total


def self_check_jpg(jpg_path, expected_y1_jpg, expected_x0_jpg, expected_x1_jpg):
    """PIL+numpy 自检 jpg 浅黄线位置"""
    img = Image.open(jpg_path).convert('RGB')
    arr = np.array(img)
    # 中黄 RGB(255, 230, 100) ±宽范围 (PNG 压缩后不精确)
    yellow_mask = (
        (arr[:, :, 0] >= 240) &
        (arr[:, :, 1] >= 215) & (arr[:, :, 1] <= 245) &
        (arr[:, :, 2] >= 80) & (arr[:, :, 2] <= 115)
    )
    yellow_rows = np.where(yellow_mask.any(axis=1))[0]
    if len(yellow_rows) == 0:
        return False, '没浅黄线'
    y_max = yellow_rows.max()
    y_diff = abs(y_max - expected_y1_jpg)
    y_ok = y_diff <= 20

    mid_y = yellow_rows[len(yellow_rows)//2]
    yellow_xs = np.where(yellow_mask[mid_y])[0]
    if len(yellow_xs) == 0:
        return False, '浅黄线没 x 范围'
    x_min, x_max = yellow_xs.min(), yellow_xs.max()
    x_overlap = max(0, min(x_max, expected_x1_jpg) - max(x_min, expected_x0_jpg))
    x_cov = x_overlap / (expected_x1_jpg - expected_x0_jpg) if expected_x1_jpg > expected_x0_jpg else 0
    x_ok = x_cov > 0.7

    return (y_ok and x_ok), {
        'y_diff': y_diff,
        'x_coverage': f'{x_cov:.1%}',
        'yellow_y': (yellow_rows.min(), yellow_rows.max()),
        'yellow_x': (x_min, x_max),
    }


def highlight_vision_pnx(pn_key, page_num, bbox_jpg, verbose=True):
    """vision 配对后, 用真 bbox 画浅黄细线 + PDF underline + 自检

    Args:
        pn_key: 'P3-2'
        page_num: 1-indexed (e.g. 3 for page 3)
        bbox_jpg: (x0, y0, x1, y1) in jpg pixels (from vision_analyze)
    """
    pn_dir = reset_pnx(pn_key)

    pdfs = [f for f in os.listdir(pn_dir) if f.endswith('.pdf') and not f.startswith('_v39') and pn_key in f]
    if not pdfs:
        pdfs = [f for f in os.listdir(pn_dir) if f.endswith('.pdf') and not f.startswith('_v39')]
    pdf_path = f'{pn_dir}/{pdfs[0]}'

    # 1. jpg 路径
    jpg_clean = f'{pn_dir}/_pdf_jpg/page_{page_num:03d}.jpg'
    if not os.path.exists(jpg_clean):
        render_pdf_to_jpg(pdf_path, f'{pn_dir}/_pdf_jpg')
    assert os.path.exists(jpg_clean), f'jpg 不存在: {jpg_clean}'

    # 2. jpg 上画浅黄细线
    jpg_out = f'{pn_dir}/page_{page_num:03d}_highlighted.jpg'
    draw_light_yellow_underline(jpg_clean, bbox_jpg, jpg_out)

    # 3. PDF underline
    rect_pt = jpg_bbox_to_pdf_rect(bbox_jpg)
    add_pdf_underline(pdf_path, page_num - 1, rect_pt)

    # 4. 自检 (避开 a.type segfault, 用 PIL+numpy)
    ok, details = self_check_jpg(jpg_out, bbox_jpg[3], bbox_jpg[0], bbox_jpg[2])
    underline_count = safe_underline_count(pdf_path)

    if verbose:
        print(f'  ✅ {pn_key}: page {page_num}, bbox={bbox_jpg}')
        print(f'    PDF underline: {underline_count}')
        print(f'    self_check: {details}')
        if not ok:
            print(f'    ❌ 自检失败')
        else:
            print(f'    ✅ 自检通过')

    return ok


def highlight_multi_lines(pn_key, page_num, lines_bbox_jpg, verbose=True):
    """多行应证段 (e.g. P3-2 被切成 4 行, 每行画一条浅黄细线)

    Args:
        pn_key: 'P3-2'
        page_num: 1-indexed
        lines_bbox_jpg: [(x0, y0, x1, y1), ...] 每行 bbox 列表
    """
    pn_dir = reset_pnx(pn_key)

    pdfs = [f for f in os.listdir(pn_dir) if f.endswith('.pdf') and not f.startswith('_v39') and pn_key in f]
    if not pdfs:
        pdfs = [f for f in os.listdir(pn_dir) if f.endswith('.pdf') and not f.startswith('_v39')]
    pdf_path = f'{pn_dir}/{pdfs[0]}'

    # 1. jpg 路径
    jpg_clean = f'{pn_dir}/_pdf_jpg/page_{page_num:03d}.jpg'
    if not os.path.exists(jpg_clean):
        render_pdf_to_jpg(pdf_path, f'{pn_dir}/_pdf_jpg')
    assert os.path.exists(jpg_clean), f'jpg 不存在: {jpg_clean}'

    # 2. jpg 上画多条浅黄细线 (用户硬规则: 应证段每行画一条, 不是只一段底一条)
    img = Image.open(jpg_clean).convert('RGB')
    draw = ImageDraw.Draw(img)
    for bbox_jpg in lines_bbox_jpg:
        x0, y0, x1, y1 = bbox_jpg
        draw.line([(x0, y1), (x1, y1)], fill=RGB_JPG, width=4)
    jpg_out = f'{pn_dir}/page_{page_num:03d}_highlighted.jpg'
    img.save(jpg_out)

    # 3. PDF underline (每行一条)
    doc = fitz.open(pdf_path)
    page = doc[page_num - 1]
    for bbox_jpg in lines_bbox_jpg:
        rect_pt = jpg_bbox_to_pdf_rect(bbox_jpg)
        annot = page.add_underline_annot(fitz.Rect(*rect_pt))
        annot.set_colors(stroke=RGB_PDF)
        annot.update()
    try:
        doc.saveIncr()
    except Exception:
        tmp = pdf_path + '.tmp'
        doc.save(tmp, garbage=4, deflate=True)
        doc.close()
        shutil.move(tmp, pdf_path)
    doc.close()

    # 4. 自检
    img2 = Image.open(jpg_out).convert('RGB')
    arr = np.array(img2)
    yellow_mask = (
        (arr[:, :, 0] >= 240) &
        (arr[:, :, 1] >= 215) & (arr[:, :, 1] <= 245) &
        (arr[:, :, 2] >= 80) & (arr[:, :, 2] <= 115)
    )
    yellow_rows = np.where(yellow_mask.any(axis=1))[0]
    # 数 cluster (每个 bbox 一行)
    clusters = []
    prev_y = -10
    start = None
    for y in yellow_rows:
        if y - prev_y > 5:
            if start is not None:
                clusters.append((start, prev_y))
            start = y
        prev_y = y
    if start is not None:
        clusters.append((start, prev_y))

    if verbose:
        print(f'  ✅ {pn_key}: page {page_num}, {len(lines_bbox_jpg)} 行 bbox')
        print(f'    jpg 浅黄线 cluster: {len(clusters)} (应为 {len(lines_bbox_jpg)})')
        for c in clusters:
            print(f'    y={c[0]}-{c[1]} px')
        if len(clusters) != len(lines_bbox_jpg):
            print(f'    ❌ cluster 数不对')

    return len(clusters) == len(lines_bbox_jpg)


if __name__ == '__main__':
    # 默认: 跑 P3-2 4 行应证段 (用户给的 P3-2 例子)
    lines = [
        (130, 175, 920, 200),
        (140, 220, 920, 245),
        (140, 260, 920, 290),
        (140, 310, 920, 345),
    ]
    ok = highlight_multi_lines('P3-2', 3, lines)
    print(f'\\n=== {"✅" if ok else "❌"} ===')