#!/usr/bin/env python3
"""
highlight_pdfs.py — 步骤 4: PDF highlight + 提图

跑通结果 (2026-08-05):
- 160 Pn-x 目录 → 159 高亮 (P30-4 repaired file 1 错)
- 226 PDF → 160 主 PDF 复制到 _highlight/Pn-x/
- 每 PDF 提 5 页 PNG 到 _highlight/Pn-x/page_NNN.png
- PyMuPDF search_for + add_highlight_annot (黄色 RGB 1,1,0)

用法:
    /Users/david/.hermes/hermes-agent/venv/bin/python scripts/highlight_pdfs.py

输入: 8 列 CSV (PPT_citations_8col.csv) + 226 PDF (Pn-x/) + 真值 citation_table.csv
输出: _highlight/Pn-x/<main_pdf>.pdf + page_NNN.png

关键词提取 (extract_d_keywords):
- 数字 + % / 月 / 万
- HR 数字 + n=
- 作者姓 (Yau T, Sangro B, etc.)
- 年份 2024/2025
- 期刊: Lancet, Hepatol, NEJM, JCO, ASCO, ESMO, APASL, HBSN
- 关键术语: STRIDE, HIMALAYA, T+A, O+Y, CheckMate, IMbrave, ORIENT, TREMENDOUS

Pitfall:
- P30-4 PDF 是 repaired file, PyMuPDF 报 "Can't do incremental writes on a repaired file"
  → 解决: 提前 fitz.open 自动 repair 失败时跳过, 不重新保存
- MuPDF "format error: non-page object in page tree" 警告 → 不影响渲染
- 160 个 Pn-x 跑完约 5-8 min (foreground), background 跑用 process tool 避免 timeout
"""
import os, csv, re, shutil
from pathlib import Path
import fitz  # PyMuPDF

ROOT = '/Users/david/Desktop/雷管方案_文献整理'
CSV_8COL = f'{ROOT}/PPT_citations_8col.csv'
HL_BASE = f'{ROOT}/_highlight'
os.makedirs(HL_BASE, exist_ok=True)

HIGHLIGHT_COLOR = (1, 1, 0)

def extract_d_keywords(d_text, c_text=''):
    keywords = set()
    full = f'{d_text} {c_text}'
    for m in re.finditer(r'(\d+\.?\d*)\s*%', full):
        keywords.add(f'{m.group(1)}%')
    for m in re.finditer(r'(\d+\.?\d*)\s*月', full):
        keywords.add(f'{m.group(1)}月')
    for m in re.finditer(r'(\d+\.?\d*)\s*万', full):
        keywords.add(f'{m.group(1)}万')
    for m in re.finditer(r'HR\s*(\d+\.?\d*)', full):
        keywords.add(f'HR {m.group(1)}')
        keywords.add(m.group(1))
    for m in re.finditer(r'n\s*=\s*(\d+)', full):
        keywords.add(f'n={m.group(1)}')
    for m in re.finditer(r'([A-Z][a-zA-Z\-]{2,})\s+[A-Z]{1,2}', c_text or ''):
        author = m.group(0).strip()
        if len(author) > 3:
            keywords.add(author)
    for m in re.finditer(r'20\d{2}', c_text or ''):
        keywords.add(m.group(0))
    for kw in ['Lancet', 'Hepatol', 'NEJM', 'JCO', 'ASCO', 'ESMO', 'APASL', 'HBSN', 'JAMA', 'Cancer Discov', 'Anticancer']:
        if kw in full:
            keywords.add(kw)
    for kw in ['STRIDE', 'HIMALAYA', 'T+A', 'O+Y', 'CheckMate', 'IMbrave', 'ORIENT', 'TREMENDOUS']:
        if kw in full:
            keywords.add(kw)
    return list(keywords)


def highlight_pdf(pdf_path, keywords, max_pages=20):
    if not os.path.exists(pdf_path):
        return None, 0
    doc = fitz.open(pdf_path)
    matches = []
    for page_num in range(min(max_pages, len(doc))):
        page = doc[page_num]
        for kw in keywords:
            text_instances = page.search_for(kw)
            for inst in text_instances:
                highlight = page.add_highlight_annot(inst)
                highlight.set_colors(stroke=HIGHLIGHT_COLOR)
                highlight.update()
                matches.append((page_num + 1, kw, inst))
    try:
        doc.saveIncr()
    except Exception:
        # repaired file 错误: P30-4 等
        pass
    doc.close()
    return pdf_path, len(matches)


def render_highlighted_pages(pdf_path, out_dir, max_pages=5, dpi=120):
    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    pages_saved = []
    for page_num in range(min(max_pages, len(doc))):
        page = doc[page_num]
        mat = fitz.Matrix(dpi/72, dpi/72)
        pix = page.get_pixmap(matrix=mat)
        out_path = f'{out_dir}/page_{page_num+1:03d}.png'
        pix.save(out_path)
        pages_saved.append(out_path)
    doc.close()
    return pages_saved


def main():
    with open(CSV_8COL) as f:
        rows = list(csv.DictReader(f))

    truth = {}
    with open(f'{ROOT}/_citation_table/citation_table.csv') as f:
        for r in csv.DictReader(f):
            truth[(r['﻿PPT页'], r['第几条'])] = r

    total = 0
    hl_done = 0
    no_pdf = 0
    no_keyword = 0

    for r in rows:
        a = r['A_slide']; n = r['B_mark']
        total += 1
        truth_row = truth.get((a, n), {})
        truth_d = truth_row.get('引用语义（上下文）', '')
        truth_c = truth_row.get('PPT中的文献引用 完整字段', '')
        d_ppt = r.get('D_ppt_visual', '')

        keywords = extract_d_keywords(d_ppt, truth_c + ' ' + truth_d)
        if not keywords:
            no_keyword += 1
            continue

        pn_dir = f'{ROOT}/P{a}-{n}'
        if not os.path.isdir(pn_dir):
            no_pdf += 1
            continue

        pdfs = [f for f in os.listdir(pn_dir) if f.endswith('.pdf')]
        if not pdfs:
            no_pdf += 1
            continue

        main_pdf = None
        for p in pdfs:
            if 'main' in p.lower() and 'fallback' not in p.lower():
                main_pdf = p
                break
        if not main_pdf:
            main_pdf = pdfs[0]

        pdf_path = f'{pn_dir}/{main_pdf}'
        hl_dir = f'{HL_BASE}/P{a}-{n}'
        try:
            hl_pdf = f'{hl_dir}/{main_pdf}'
            os.makedirs(hl_dir, exist_ok=True)
            shutil.copy(pdf_path, hl_pdf)
            highlight_pdf(hl_pdf, keywords, max_pages=20)
            render_highlighted_pages(hl_pdf, hl_dir, max_pages=5, dpi=120)
            hl_done += 1
        except Exception as e:
            print(f'P{a}-{n} 错误: {e}')

    print(f'总标号: {total}')
    print(f'highlight 完成: {hl_done} = {hl_done/total*100:.1f}%')
    print(f'无 PDF: {no_pdf}')
    print(f'无关键词: {no_keyword}')


if __name__ == '__main__':
    main()
