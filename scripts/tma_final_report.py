import os
# -*- coding: utf-8 -*-
"""tma_final_report.py — 生成 TMA 交付报告 markdown"""
import json, os, re, io, sys, csv, fitz

T = os.environ.get('TMA_PROJECT') or r'C:\\Users\\via54\\Desktop\\TMA_test'
REF_JSON = os.path.join(T, '_references_FINAL.json')
DOI_MAP = os.path.join(T, '_doi_map_full.json')
PDF_DIR = os.path.join(T, '_2_pdfs')
HL_BASE = os.path.join(T, '_highlight_nested')
OUT_MD = os.path.join(T, '_TMA_highlight_交付报告.md')
CSV_OUT = os.path.join(T, '_citations_89_8col.csv')

def main():
    refs = json.load(open(REF_JSON, encoding='utf-8'))
    doi_map = json.load(open(DOI_MAP, encoding='utf-8'))
    pdfs = set(f.replace('.pdf', '') for f in os.listdir(PDF_DIR) if f.endswith('.pdf'))
    hl_dirs = set()
    if os.path.isdir(HL_BASE):
        hl_dirs = set(d for d in os.listdir(HL_BASE) if os.path.isdir(os.path.join(HL_BASE, d)))
    hl_info = {}
    for d in sorted(hl_dirs):
        hl_pdf = os.path.join(HL_BASE, d, d + '_highlight.pdf')
        if os.path.exists(hl_pdf):
            try:
                doc = fitz.open(hl_pdf)
                n_annots = sum(len(list(doc[i].annots() or [])) for i in range(len(doc)))
                hl_info[d] = (len(doc), n_annots)
                doc.close()
            except Exception:
                pass

    # 8 列 CSV
    rows = []
    for ref_id in sorted(refs.keys(), key=lambda x: (int(re.match(r'P(\d+)-', x).group(1)), int(x.split('-')[1]))):
        m = re.match(r'P(\d+)-(\d+)', ref_id)
        slide, num = int(m.group(1)), int(m.group(2))
        d_field = refs[ref_id]
        info = doi_map.get(ref_id, {}) or {}
        doi = info.get('doi') or ''
        url = info.get('url') or ''
        ftype = info.get('type') or ('GUIDELINE' if ('共识' in d_field or '指南' in d_field) else 'LITERATURE')
        pdf_file = ('%s.pdf' % ref_id) if ref_id in pdfs else ''
        h_parts = []
        if doi and doi.startswith('10.'):
            h_parts.append('DOI: %s' % doi)
            h_parts.append('https://pubmed.ncbi.nlm.nih.gov/?term=%s' % doi)
            h_parts.append('https://europepmc.org/search?query=%s' % doi)
        if url and url not in h_parts:
            h_parts.append(url)
        rows.append([slide, num, '', d_field[:300], doi, ftype, pdf_file, ' | '.join(h_parts)])
    with open(CSV_OUT, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['A:PPT页', 'B:第几条', 'C:引用语义', 'D:PPT引文完整字段', 'E:DOI', 'F:类型', 'G:对应PDF文件', 'H:来源链接'])
        w.writerows(rows)

    # Markdown 报告
    lines = []
    lines.append('# TMA 文献整理 — Highlight 交付报告')
    lines.append('')
    lines.append('- 生成时间: %s' % '2026-08-20 (本次会话)')
    lines.append('- 引用总数: %d' % len(refs))
    lines.append('- 已有 PDF: %d' % len([r for r in refs if r in pdfs]))
    lines.append('- 缺失 PDF: %d (含付费墙/中文期刊需手动) ' % len([r for r in refs if r not in pdfs]))
    lines.append('- Highlight 目录: %d / %d' % (len(hl_dirs), len(pdfs)))
    lines.append('')
    lines.append('## 1. 引用 ↔ PDF ↔ Highlight 对照表')
    lines.append('')
    lines.append('| 引用 | 引文 (截断) | PDF | Highlight | annots |')
    lines.append('|---|---|---|---|---|')
    for ref_id in sorted(refs.keys(), key=lambda x: (int(re.match(r'P(\d+)-', x).group(1)), int(x.split('-')[1]))):
        cit = refs[ref_id][:55].replace('|', '/')
        has_pdf = ref_id in pdfs
        hl = hl_info.get(ref_id)
        hl_txt = '✅' if hl else ('—' if not has_pdf else '❌')
        annot_txt = str(hl[1]) if hl else ''
        lines.append('| %s | %s | %s | %s | %s |' % (ref_id, cit, '✅' if has_pdf else '❌', hl_txt, annot_txt))
    lines.append('')
    lines.append('## 2. 需手动获取 (付费墙 / 中文期刊无 OA)')
    lines.append('')
    lines.append('| 引用 | 引文 | 建议途径 |')
    lines.append('|---|---|---|')
    for ref_id in sorted(refs.keys(), key=lambda x: (int(re.match(r'P(\d+)-', x).group(1)), int(x.split('-')[1]))):
        if ref_id in pdfs:
            continue
        cit = refs[ref_id][:80]
        if 'UpToDate' in cit:
            way = 'UpToDate 网页内容, 无法下载 PDF; 保留 URL 引用即可'
        elif any('\u4e00' <= c <= '\u9fff' for c in cit[:60]):
            way = '中华医学会期刊 (rs.yiigle.com) / 万方 / CNKI 下载'
        else:
            way = '付费墙; 建议用机构订阅下载'
        lines.append('| %s | %s | %s |' % (ref_id, cit, way))
    lines.append('')
    lines.append('## 3. 目录结构')
    lines.append('')
    lines.append('```')
    lines.append('TMA_test/')
    lines.append('├── _2_pdfs/                     # 全部 main PDF (Pn-S{slide}_{num}.pdf)')
    lines.append('├── _2_pdfs_wrong/               # 被核验为错配的下载 (隔离)')
    lines.append('└── _highlight_nested/           # 每 Pn-x 一个目录 (v3 FINAL 标准)')
    lines.append('    └── Pn-S23_5/')
    lines.append('        ├── Pn-S23_5_main.pdf')
    lines.append('        ├── Pn-S23_5_highlight.pdf')
    lines.append('        ├── Pn-S23_5_highlight_pNNN.png   # 仅高亮页')
    lines.append('        └── Pn-S23_5_highlight_pages/     # 全部页')
    lines.append('```')
    lines.append('')
    with open(OUT_MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('written:', OUT_MD)
    print('CSV rows:', len(rows), '->', CSV_OUT)

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    main()
