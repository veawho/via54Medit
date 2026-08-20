import os
"""tma_package.py — TMA 交付打包: 重建 89 行 8 列 CSV + 覆盖率报告

列: A:PPT页 B:第几条 C:引用语义 D:PPT引文完整字段 E:DOI F:类型 G:对应PDF文件 H:来源链接
输出: _citations_89_8col.csv + _tma_delivery_report.json
"""
import json, os, re, io, sys, csv, hashlib, fitz

T = os.environ.get('TMA_PROJECT') or r'C:\\Users\\via54\\Desktop\\TMA_test'
REF_JSON = os.path.join(T, '_references_FINAL.json')
DOI_MAP = os.path.join(T, '_doi_map_full.json')
VISION = os.path.join(T, '_vision_report.json')
PDF_DIR = os.path.join(T, '_2_pdfs')
HL_BASE = os.path.join(T, '_highlight_nested')
CSV_OUT = os.path.join(T, '_citations_89_8col.csv')
REPORT_OUT = os.path.join(T, '_tma_delivery_report.json')

def main():
    refs = json.load(open(REF_JSON, encoding='utf-8'))
    doi_map = json.load(open(DOI_MAP, encoding='utf-8'))
    vision = json.load(open(VISION, encoding='utf-8'))

    # vision context per ref
    ctx_map = {}
    for sk, sd in vision.get('slides', {}).items():
        for mid, mark in sd.get('citation_marks', {}).items():
            for part in mid.split(','):
                part = part.strip()
                if part.isdigit():
                    ctx_map['P%s-%s' % (sd['slide_num'], part)] = mark.get('context', '')

    rows = []
    for ref_id in sorted(refs.keys(), key=lambda x: (int(re.match(r'P(\d+)-', x).group(1)), int(x.split('-')[1]))):
        m = re.match(r'P(\d+)-(\d+)', ref_id)
        slide, num = int(m.group(1)), int(m.group(2))
        d_field = refs[ref_id]
        info = doi_map.get(ref_id, {}) or {}
        doi = info.get('doi') or ''
        url = info.get('url') or ''
        ftype = info.get('type') or ('GUIDELINE' if ('共识' in d_field or '指南' in d_field or 'consensus' in d_field.lower()) else 'LITERATURE')
        pdf_file = ('%s.pdf' % ref_id) if os.path.exists(os.path.join(PDF_DIR, '%s.pdf' % ref_id)) else ''
        context = (ctx_map.get(ref_id) or '')[:100]
        h_parts = []
        if doi:
            h_parts.append('DOI: %s' % doi)
            h_parts.append('https://pubmed.ncbi.nlm.nih.gov/?term=%s' % doi)
            h_parts.append('https://europepmc.org/search?query=%s' % doi)
        if url and url not in h_parts:
            h_parts.append(url)
        if pdf_file:
            h_parts.append('local: %s' % pdf_file)
        rows.append([slide, num, context, d_field[:300], doi, ftype, pdf_file, ' | '.join(h_parts)])

    with open(CSV_OUT, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['A:PPT页', 'B:第几条', 'C:引用语义', 'D:PPT引文完整字段', 'E:DOI', 'F:类型', 'G:对应PDF文件', 'H:来源链接'])
        w.writerows(rows)

    # 覆盖率报告
    pdfs = set(f.replace('.pdf', '') for f in os.listdir(PDF_DIR) if f.endswith('.pdf'))
    hl_dirs = set()
    if os.path.isdir(HL_BASE):
        hl_dirs = set(d for d in os.listdir(HL_BASE) if os.path.isdir(os.path.join(HL_BASE, d)))
    hl_ok = []
    for d in sorted(hl_dirs):
        hl_pdf = os.path.join(HL_BASE, d, d + '_highlight.pdf')
        if os.path.exists(hl_pdf) and os.path.getsize(hl_pdf) > 10000:
            try:
                doc = fitz.open(hl_pdf)
                n_annots = sum(len(list(doc[i].annots() or [])) for i in range(len(doc)))
                doc.close()
                hl_ok.append({'pn': d, 'annots': n_annots, 'pages': len(fitz.open(hl_pdf))})
            except Exception:
                pass
    report = {
        'refs_total': len(refs),
        'pdfs_present': len([r for r in refs if ('%s.pdf' % r) in pdfs]),
        'pdfs_missing': sorted([r for r in refs if ('%s.pdf' % r) not in pdfs]),
        'highlight_dirs': len(hl_dirs),
        'highlight_ok': len(hl_ok),
        'csv_rows': len(rows),
        'csv_path': CSV_OUT,
    }
    json.dump(report, open(REPORT_OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('CSV rows:', len(rows))
    print('refs:', len(refs), '| pdfs present:', report['pdfs_present'], '| missing:', len(report['pdfs_missing']))
    print('highlight dirs:', len(hl_dirs), 'ok:', len(hl_ok))
    print('missing pdfs:', ','.join(report['pdfs_missing']))

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    main()
