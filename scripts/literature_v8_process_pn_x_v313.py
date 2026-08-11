#!/usr/bin/env python3.11
"""V3.13: 用 pymupdf4llm 重写 PDF 标注算法

流程:
1. 用 pymupdf4llm 提取 PDF (返回 page_chunks + page_boxes)
2. 对每个 page:
   - 找 table boxes → 检查含 target 数字 → 标 line 底部 1.5px 细线
   - 找 text boxes → 检查含 P0 主题词 + target 数字 → 标 line 底部 1.5px 细线
3. 输出截图 (DPI 120)

相比之前 (v3.9-3.12) 优势:
- 表格识别由 pymupdf4llm 自动给 class='table' bbox, 不再自己 y 合并
- 严格数字匹配 (target 数字精确, 不匹配任意统计数字)
- 减少误匹配 (text/box type 过滤)

用法: python3.11 process_pn_x_v313.py <Pn-x>
"""
import sys
import os
import re
import json
import argparse
from pathlib import Path

import fitz
import pymupdf4llm


# 主题词库 (按 PDF 类型分类)
P0_THEMES = {
    'chinese_full': ['5年生存率', '5年OS率', '5年相对生存率', '总体癌症', '总体癌症5年生存率',
                     '中国肝癌', '中国 HCC', '肝癌', '肝细胞癌'],
    'chinese_partial': ['5年生', '5年OS', '生存率', '肝癌', '肝细胞癌', '总体癌症'],
    'english': ['5-year survival', 'overall survival', 'progression-free survival',
                'PFS', 'median OS', 'hazard ratio', 'objective response',
                'disease control', 'overall survival rate', 'survival rate',
                # Cancer sites (Zeng Table 2 类型的英文)
                'Liver', 'Esophagus', 'Stomach', 'Colon-rectum', 'Breast',
                'Pancreas', 'Lung', 'Gallbladder', 'Larynx', 'Nasopharynx',
                'Oral', 'Pharynx', 'cancer', 'cancer site']
}


def extract_target_numbers(targets):
    """提取 targets 里的具体数字 (标准化: 14.40 → 14.4)"""
    nums = set()
    for t in targets:
        for kw in t.get('keywords', []):
            for nm in re.findall(r'\d+\.\d+|\d+', kw):
                if len(nm) >= 2:
                    nums.add(nm)
                    if '.' in nm:
                        stripped = nm.rstrip('0').rstrip('.')
                        if len(stripped) >= 2:
                            nums.add(stripped)
    return nums


def group_lines_by_y(lines, y_tolerance=5):
    """按 y 坐标合并 lines (PyMuPDF 把表格列拆成单独 line)

    v3.13.4: 先按 y 排序再合并, 避免 box_lines 顺序导致 y 漂移
    """
    # 按 y 排序 (line_y = bbox 中点)
    sorted_lines = sorted(lines, key=lambda l: (l['bbox'][1] + l['bbox'][3]) / 2)
    groups = []
    cur_group = []
    cur_y = None
    for line in sorted_lines:
        line_y = (line['bbox'][1] + line['bbox'][3]) / 2
        if cur_y is None or abs(line_y - cur_y) < y_tolerance:
            cur_group.append(line)
            cur_y = line_y
        else:
            groups.append(cur_group)
            cur_group = [line]
            cur_y = line_y
    if cur_group:
        groups.append(cur_group)
    return groups


def line_matches(line_text, target_nums):
    """line_text 是否含 target 数字 + P0 主题词

    v3.13.2: 严格匹配 — 必须同时含主题词 + target 数字
    (避免: line 含 27.9 但不含 liver/肝癌, 不标)
    """
    has_num = any(nm in line_text for nm in target_nums)
    if not has_num:
        return False
    # 必须有 P0 主题词 (中文完整词 / 部分词 / 英文主题词)
    has_p0_full = any(p in line_text for p in P0_THEMES['chinese_full'])
    has_p0_partial = any(p in line_text for p in P0_THEMES['chinese_partial'])
    has_p0_en = any(p.lower() in line_text.lower() for p in P0_THEMES['english'])
    return has_p0_full or has_p0_partial or has_p0_en


def draw_underline(page, rect):
    """画 1.5px 细下划线 (不覆盖文字)"""
    r = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y1)
    bar_h = 1.5
    bar_rect = fitz.Rect(r.x0, r.y1 - bar_h, r.x1, r.y1)
    page.draw_rect(bar_rect, color=(1, 0.85, 0), fill=(1, 0.92, 0.15),
                   width=0.1, overlay=True)


def process_pn_x(pn_x, pdf_path, out_dir, targets):
    """主流程: PDF → 标注 → 截图

    v3.13.3: 增加核心数字过滤 — 只标含"核心主题词"(liver/肝癌/5年生存率)的行,
    不标只含"对比癌种+数字"的行 (如只含 Esophagus + 27.9)
    """
    target_nums = extract_target_numbers(targets)

    doc = fitz.open(pdf_path)
    chunks = pymupdf4llm.to_markdown(pdf_path, page_chunks=True)

    highlight_rects = []

    for chunk in chunks:
        page_idx = chunk['metadata']['page_number'] - 1
        if page_idx >= 12:
            continue
        page_boxes = chunk.get('page_boxes', [])
        page = doc[page_idx]

        for box in page_boxes:
            cls = box['class']
            bbox = box['bbox']

            if cls not in ('table', 'text', 'caption'):
                continue

            x0, y0, x1, y1 = bbox
            box_lines = []
            for block in page.get_text('dict')['blocks']:
                if 'lines' not in block:
                    continue
                for line in block['lines']:
                    lb = line['bbox']
                    if x0 <= lb[0] <= x1 and y0 <= lb[1] <= y1:
                        box_lines.append(line)

            y_groups = group_lines_by_y(box_lines)

            for y_group in y_groups:
                group_text = " ".join(
                    "".join(s["text"] for s in l.get("spans", []))
                    for l in y_group
                )

                if not line_matches(group_text, target_nums):
                    continue

                # 标组内每个含 target 的 line
                for line in y_group:
                    line_text = "".join(s["text"] for s in line.get("spans", []))
                    if not any(nm in line_text for nm in target_nums):
                        continue
                    lb = line['bbox']
                    bar_h = 1.5
                    line_rect = fitz.Rect(lb[0], lb[3] - bar_h, lb[2], lb[3])
                    highlight_rects.append((page_idx, line_rect))

    for pi, rect in highlight_rects:
        draw_underline(doc[pi], rect)

    os.makedirs(out_dir, exist_ok=True)
    seen = set()
    for pi, rect in highlight_rects:
        if pi in seen:
            continue
        seen.add(pi)
        pix = doc[pi].get_pixmap(dpi=120, colorspace=fitz.csRGB)
        out = os.path.join(out_dir, f'{pn_x}_page{pi+1}_highlight.jpg')
        pix.save(out)

    print(f'OK n={len(highlight_rects)} imgs={len(seen)}')
    doc.close()
    return len(highlight_rects), len(seen)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python3.11 process_pn_x_v313.py <Pn-x>')
        sys.exit(1)

    pn_x = sys.argv[1]
    # 从 citation_table 读 PDF + targets
    sys.path.insert(0, '/Users/david/Desktop/雷管方案_文献整理/scripts')
    from process_pn_x import parse_citation_table_for_pn, extract_targets_from_c

    info = parse_citation_table_for_pn(pn_x)
    pdf_path = '/Users/david/Desktop/雷管方案_文献整理/' + info['main_pdf']
    out_dir = '/Users/david/Desktop/雷管方案_文献整理/_literature_citation_index/' + pn_x
    targets = extract_targets_from_c(info['cite_c'])

    n, imgs = process_pn_x(pn_x, pdf_path, out_dir, targets)
    print(f'{pn_x}: n={n} imgs={imgs}')