#!/usr/bin/env python3
"""
audit_all_pn_x_real_literature.py
=================================

全量审计 160 个 Pn-x 主 PDF 是否真文献, 找出所有"网页截图"伪装 PDF。

用法: python3 audit_all_pn_x_real_literature.py
输出: report.json (每 Pn-x 状态) + 控制台 summary
"""

import os, csv, json, sys

BASE = '/Users/david/Desktop/雷管方案_文献整理'
CSV = os.path.join(BASE, '_citation_table', 'citation_table.csv')


def verify_real_literature(pdf_path, expected_doi=None):
    """验证 PDF 是真文献"""
    try:
        import fitz
    except ImportError:
        return False, "no fitz", {}
    if not os.path.exists(pdf_path):
        return False, "no file", {}
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        return False, f"open err: {e}", {}
    n_pages = len(doc)
    meta = doc.metadata or {}
    title = meta.get('title') or ''
    author = meta.get('author') or ''
    text_p1 = doc[0].get_text().lower() if n_pages > 0 else ''
    doc.close()
    indicators = ['abstract', 'introduction', 'received', 'published',
                  'copyright', 'background', 'methods', 'references',
                  'department', 'university', 'institute', 'correspondence']
    n_ind = sum(1 for k in indicators if k in text_p1)
    real = n_pages >= 3 and n_ind >= 2
    info = {
        'pages': n_pages,
        'title': title[:60],
        'author': author[:60],
        'indicators': n_ind,
        'p1_first200': text_p1[:200].replace('\n', ' '),
    }
    if real:
        return True, 'OK', info
    return False, f'pages={n_pages}, indicators={n_ind}', info


def main():
    with open(CSV, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    report = {}
    fake_list = []
    for r in rows:
        pn = f"P{r['PPT页']}-{r['第几条']}"
        pdf_rel = r['对应PDF文件']
        if not pdf_rel:
            continue
        pdf_full = os.path.join(BASE, pdf_rel)
        real, reason, info = verify_real_literature(pdf_full, r.get('DOI', ''))
        report[pn] = {
            'pdf': pdf_rel,
            'doi': r.get('DOI', ''),
            'real': real,
            'reason': reason,
            'info': info,
        }
        if not real:
            fake_list.append((pn, reason, info))

    # 写报告
    out = os.path.join(BASE, '_audit_report', 'pn_x_real_literature_audit.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 控制台 summary
    n_real = sum(1 for v in report.values() if v['real'])
    n_fake = sum(1 for v in report.values() if not v['real'])
    print(f'== 审计结果 ==')
    print(f'总 Pn-x: {len(report)}')
    print(f'真文献: {n_real}')
    print(f'非真文献 (网页截图/失效): {n_fake}')
    print(f'\n报告写入: {out}')

    if fake_list:
        print(f'\n== 非真文献 Pn-x (需人工替换) ==')
        for pn, reason, info in fake_list:
            print(f'  {pn}: {reason}')
            print(f'    title: {info.get("title", "")[:60]}')
            print(f'    p1: {info.get("p1_first200", "")[:100]}')


if __name__ == '__main__':
    main()