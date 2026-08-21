#!/usr/bin/env python3
"""
verify_highlight_calibration.py — via54Medit 高亮图与 PDF 数据点覆盖度校准

功能:
1. 扫描所有有 highlight 图的 Pn-x
2. 用 PyMuPDF 在 main PDF 中搜索 C 列提取的数据点
3. 比对 highlight 页数 vs 数据点出现页数
4. 列出缺失页
5. 可选: 自动补缺失页 highlight 图

Usage:
    # 全量校准 (只报告, 不补图)
    python3 verify_highlight_calibration.py

    # 全量校准 + 自动补缺失页
    python3 verify_highlight_calibration.py --auto-fix

    # 单 Pn-x 校准
    python3 verify_highlight_calibration.py --pn-x P3-3
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

LIT_BASE = "/Users/david/Desktop/雷管方案_文献整理/_literature_citation_index"
CSV_PATH = "/Users/david/Desktop/雷管方案_文献整理/_citation_table/citation_table.csv"

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERROR: PyMuPDF not installed. pip install pymupdf")
    sys.exit(1)


def parse_c_field_simple(c_raw: str):
    """简单提取 C 列的数字数据点"""
    text = ' '.join(c_raw.split())
    nums = re.findall(r'\b(\d+\.?\d*)\s*%?', text)
    # 过滤太短 + 试验名噪声 (如 RATIONALE-301, IMbrave150)
    nums = [n for n in nums if len(n) >= 2 and n not in {'01', '02', '03'}]
    # 限制前 10 个
    return nums[:10]


def list_highlight_pages(pn_path: str):
    """列出 Pn-x 目录里的 highlight 图对应页号"""
    pages = []
    for f in os.listdir(pn_path):
        if 'highlight' in f.lower() and f.endswith('.jpg'):
            m = re.search(r'_page(\d+)_', f)
            if m:
                pages.append(int(m.group(1)))
    return sorted(pages)


def find_main_pdf(pn_path: str, pn_x: str):
    """找 main PDF"""
    for f in os.listdir(pn_path):
        if f.startswith(pn_x) and '_main_' in f and f.endswith('.pdf'):
            return f
    return None


def find_data_point_pages(pdf_path: str, data_points: list, max_pages: int = 15):
    """在 main PDF 中搜索数据点, 返回出现页号"""
    if not data_points:
        return []
    doc = fitz.open(pdf_path)
    found = set()
    try:
        for pi, page in enumerate(doc[:max_pages]):
            text = page.get_text()
            for dp in data_points:
                if dp and dp in text:
                    found.add(pi + 1)
    finally:
        doc.close()
    return sorted(found)


def generate_highlight_image(pdf_path: str, page_num: int, output_path: str):
    """生成缺失页的 highlight 图 (整页渲染)"""
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_num - 1]  # 0-indexed
        mat = fitz.Matrix(2, 2)  # 2x 放大
        pix = page.get_pixmap(matrix=mat)
        pix.save(output_path)
        return True
    finally:
        doc.close()


def verify_pn_x(pn_x: str, lit_base: str = LIT_BASE, auto_fix: bool = False):
    """校准单个 Pn-x"""
    pn_path = f"{lit_base}/{pn_x}"
    if not os.path.isdir(pn_path):
        return None

    hl_pages = list_highlight_pages(pn_path)
    main_pdf = find_main_pdf(pn_path, pn_x)
    if not main_pdf:
        return {
            'pn_x': pn_x,
            'main_pdf': None,
            'hl_pages': hl_pages,
            'data_pages': [],
            'missing': [],
            'ok': None,
            'note': 'no main PDF',
        }

    # 从 CSV 读 C 列
    import csv
    c_raw = ''
    with open(CSV_PATH, newline='') as f:
        rows = list(csv.DictReader(f))
        cols = list(rows[0].keys())
        for r in rows:
            if f"P{page}-{pn}" == f"P{r[cols[0]]}-{r[cols[1]]}" if False else False:
                pass
        # 找匹配
        for r in rows:
            pn_x_csv = f"P{r[cols[0]]}-{r[cols[1]]}"
            if pn_x_csv == pn_x:
                c_raw = r[cols[2]]
                break

    data_points = parse_c_field_simple(c_raw)
    pdf_path = f"{pn_path}/{main_pdf}"
    data_pages = find_data_point_pages(pdf_path, data_points)

    missing = sorted(set(data_pages) - set(hl_pages))

    result = {
        'pn_x': pn_x,
        'main_pdf': main_pdf,
        'hl_pages': hl_pages,
        'data_pages': data_pages,
        'missing': missing,
        'ok': len(missing) == 0,
    }

    if auto_fix and missing:
        for page_num in missing:
            output_path = f"{pn_path}/{pn_x}_page{page_num}_highlight.jpg"
            if not os.path.isfile(output_path):
                try:
                    generate_highlight_image(pdf_path, page_num, output_path)
                    result.setdefault('generated', []).append(output_path)
                except Exception as e:
                    result.setdefault('errors', []).append(f"page {page_num}: {e}")

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pn-x', help='校准单个 Pn-x (e.g. P3-3)')
    parser.add_argument('--auto-fix', action='store_true',
                        help='自动补缺失页 highlight 图')
    parser.add_argument('--lit-base', default=LIT_BASE)
    args = parser.parse_args()

    if args.pn_x:
        # 单个校准
        result = verify_pn_x(args.pn_x, args.lit_base, args.auto_fix)
        if result is None:
            print(f"❌ {args.pn_x}: directory not found")
            return 1
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result['ok'] else 1

    # 全量扫描
    pn_dirs = sorted([d for d in os.listdir(args.lit_base) if d.startswith('P')])
    print(f"=== 校准 {len(pn_dirs)} 个 Pn-x 目录 ===\n")

    fail = 0
    pass_n = 0
    skip = 0

    for pn_x in pn_dirs:
        result = verify_pn_x(pn_x, args.lit_base, auto_fix=args.auto_fix)
        if result is None:
            continue
        if result.get('main_pdf') is None:
            skip += 1
            continue
        if result['ok']:
            pass_n += 1
        else:
            fail += 1
            print(f"❌ {pn_x}: hl={result['hl_pages']} data={result['data_pages']} missing={result['missing']}")
            if args.auto_fix and 'generated' in result:
                for g in result['generated']:
                    print(f"   + {os.path.basename(g)}")

    print(f"\n✅ Pass: {pass_n}")
    print(f"❌ Fail: {fail}")
    print(f"⏭️ Skip (no main PDF): {skip}")
    return 0 if fail == 0 else 1


if __name__ == '__main__':
    sys.exit(main())