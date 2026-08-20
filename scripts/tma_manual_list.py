import os
# -*- coding: utf-8 -*-
"""tma_manual_list.py — 生成人工下载清单 (含访问链接)"""
import json, os, re, io, sys, urllib.parse

T = os.environ.get('TMA_PROJECT') or r'C:\\Users\\via54\\Desktop\\TMA_test'
MISSING = os.path.join(T, '_manual_download_list.json')
REF_JSON = os.path.join(T, '_references_FINAL.json')
OUT_MD = os.path.join(T, '_人工下载清单.md')
OUT_CSV = os.path.join(T, '_manual_download_list.csv')

# 已知的正确 DOI (round2 CrossRef 确认或人工核实)
KNOWN_DOI = {
    'S4_4': '10.1016/j.molimm.2011.06.003',
    'S9_1': '10.1056/NEJMra1312353',
    'S11_6': '10.1016/S0140-6736(08)60073-2',
    'S13_2': '10.1038/sj.bmt.1705160',
    'S15_2': '10.1007/s00467-020-04515-5',
    'S17_3': '10.1056/NEJMra041413',
    'S21_1': '10.1016/j.kint.2019.04.020',
    'S23_1': '10.1053/j.seminhematol.2018.04.003',
    'S23_3': '10.1016/j.bbmt.2005.06.001',
    'S23_7': '10.1053/j.ajkd.2018.06.034',
    'S23_9': '10.1016/j.blre.2014.11.001',
    'S23_10': '10.1016/j.bbmt.2014.09.028',
    'S23_11': '10.1182/bloodadvances.2020003308',
    'S23_12': '10.1182/blood-2014-03-564930',
    'S23_13': '10.1038/s41409-018-0156-8',
    'S23_24': '10.1016/j.jtct.2022.11.014',
    'S23_25': '10.1016/j.jtct.2022.12.020',
    'S23_26': '10.1016/j.bbmt.2012.08.022',
    'S28_4': '10.1002/ajh.26926',
    'S29_1': '10.1016/j.mayocp.2016.05.015',
    'S31_4': '10.1053/j.ajkd.2015.12.034',
    'S29_2': '10.1002/ajh.25220',
}

def pm_search(term):
    return 'https://pubmed.ncbi.nlm.nih.gov/?term=' + urllib.parse.quote(term)

def main():
    missing = json.load(open(MISSING, encoding='utf-8'))
    refs = json.load(open(REF_JSON, encoding='utf-8'))
    lines = []
    lines.append('# TMA 文献 — 人工下载清单 (自动下载截止后剩余 %d 篇)' % len(missing))
    lines.append('')
    lines.append('> 说明: 自动级联下载 (OpenAlex/Unpaywall/EuropePMC/PMC/Sci-Hub) 已于 1 小时内截止,')
    lines.append('> 以下文献为付费墙或中文期刊 (无开放 PDF), 请通过链接手动获取后放入 `_2_pdfs/Pn-Sx_y.pdf`。')
    lines.append('')
    rows = []
    for m in missing:
        ref = m['ref']
        cit = refs[ref]
        doi = KNOWN_DOI.get(ref) or m.get('doi') or ''
        links = []
        if doi.startswith('10.'):
            links.append('[DOI: %s](https://doi.org/%s)' % (doi, doi))
            links.append('[PubMed](%s)' % pm_search(doi))
            links.append('[EuropePMC](https://europepmc.org/search?query=%s)' % urllib.parse.quote(doi))
        else:
            # 无 DOI: 用题录关键词搜索
            kw = cit[:80].split(';')[0].strip()[:60]
            links.append('[PubMed 搜索](%s)' % pm_search(kw))
            links.append('[Google 学术](https://scholar.google.com/scholar?q=%s)' % urllib.parse.quote(cit[:100]))
        if '中华' in cit or '浙江' in cit or '中国小儿' in cit or '现代肿瘤' in cit or '自身免疫' in cit:
            links.append('[万方](https://s.wanfangdata.com.cn/paper?q=%s)' % urllib.parse.quote(cit[:50]))
            links.append('[知网](https://kns.cnki.net/kns8s/defaultresult/index?kw=%s)' % urllib.parse.quote(cit[:50]))
        if 'UpToDate' in cit:
            links = ['[UpToDate](https://www.uptodate.com/contents/diagnosis-of-hemolytic-anemia-in-adults) (在线内容, 无 PDF)']
        lines.append('### %s' % ref)
        lines.append('- 引文: %s' % cit)
        lines.append('- 链接: ' + ' | '.join(links))
        lines.append('')
        rows.append([ref, cit, doi, ' '.join(re.sub(r'\[|\]\([^)]*\)', ' ', l) for l in links).replace('  ', ' ').strip()])
    with open(OUT_MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    import csv
    with open(OUT_CSV, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['引用', '引文', 'DOI', '链接'])
        w.writerows(rows)
    print('written:', OUT_MD)
    print('rows:', len(rows))

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    main()
