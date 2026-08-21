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
    'P4-4': '10.1016/j.molimm.2011.06.003',
    'P9-1': '10.1056/NEJMra1312353',
    'P11-6': '10.1016/S0140-6736(08)60073-2',
    'P13-2': '10.1038/sj.bmt.1705160',
    'P15-2': '10.1007/s00467-020-04515-5',
    'P17-3': '10.1056/NEJMra041413',
    'P21-1': '10.1016/j.kint.2019.04.020',
    'P23-1': '10.1053/j.seminhematol.2018.04.003',
    'P23-3': '10.1016/j.bbmt.2005.06.001',
    'P23-7': '10.1053/j.ajkd.2018.06.034',
    'P23-9': '10.1016/j.blre.2014.11.001',
    'P23-10': '10.1016/j.bbmt.2014.09.028',
    'P23-11': '10.1182/bloodadvances.2020003308',
    'P23-12': '10.1182/blood-2014-03-564930',
    'P23-13': '10.1038/s41409-018-0156-8',
    'P23-24': '10.1016/j.jtct.2022.11.014',
    'P23-25': '10.1016/j.jtct.2022.12.020',
    'P23-26': '10.1016/j.bbmt.2012.08.022',
    'P28-4': '10.1002/ajh.26926',
    'P29-1': '10.1016/j.mayocp.2016.05.015',
    'P31-4': '10.1053/j.ajkd.2015.12.034',
    'P29-2': '10.1002/ajh.25220',
}

def pm_search(term):
    return 'https://pubmed.ncbi.nlm.nih.gov/?term=' + urllib.parse.quote(term)

def main():
    # 缺失清单: 优先 _manual_download_list.json, 缺则从 _refs.json + PDF 目录自算 (全新项目兼容)
    if os.path.exists(MISSING):
        missing = json.load(open(MISSING, encoding='utf-8'))
    else:
        refs0 = json.load(open(REF_JSON, encoding='utf-8'))
        pdf_dir = os.path.join(T, "_2_pdfs")
        have = set(f[:-4] for f in os.listdir(pdf_dir)) if os.path.isdir(pdf_dir) else set()
        missing = [{"ref": k, "citation": v} for k, v in sorted(refs0.items()) if k not in have]
        json.dump(missing, open(MISSING, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    refs = json.load(open(REF_JSON, encoding='utf-8'))
    lines = []
    lines.append('# TMA 文献 — 人工下载清单 (自动下载截止后剩余 %d 篇)' % len(missing))
    lines.append('')
    lines.append('> 说明: 自动级联下载 (OpenAlex/Unpaywall/EuropePMC/PMC/Sci-Hub) 已于 1 小时内截止,')
    lines.append('> 以下文献为付费墙或中文期刊 (无开放 PDF), 请通过链接手动获取后放入 `_2_pdfs/Pn-Sx_y.pdf`。')
    lines.append('')
    # 引用关联映射 (完整引文编号 ↔ 下载状态), 用于人工清单展示建议引文
    assoc_path = os.path.join(T, "_ref_assoc_map.json")
    assoc_map = {}
    if os.path.exists(assoc_path):
        try:
            assoc_map = json.load(open(assoc_path, encoding="utf-8"))
        except Exception:
            assoc_map = {}
    full_path2 = os.path.join(T, "_references_full.json")
    full_refs = {}
    if os.path.exists(full_path2):
        try:
            full_refs = json.load(open(full_path2, encoding="utf-8"))
        except Exception:
            full_refs = {}
    pdf_dir2 = os.path.join(T, "_2_pdfs")
    rows = []
    for m in missing:
        ref = m['ref']
        cit = refs[ref]
        doi = KNOWN_DOI.get(ref) or m.get('doi') or ''
        links = []
        # 建议完整引文 (编号命中全文库时)
        try:
            _num = int(ref.split("-")[1])
        except Exception:
            _num = None
        if _num and str(_num) in full_refs:
            full_cit = str(full_refs[str(_num)])
            ref_pdf = os.path.join(pdf_dir2, "ref%s.pdf" % _num)
            ref_ok = os.path.exists(ref_pdf) and os.path.getsize(ref_pdf) > 5000
            ainfo = assoc_map.get(ref) or {}
            if ainfo.get("assoc") == "ok" and ref_ok:
                # 双核验通过: 确认该 ref = 全文库 ref{N}.pdf, 直接复用
                links.append("[复用全文库 ref%s.pdf (双核验通过)](local: _2_pdfs/ref%s.pdf)" % (_num, _num))
            elif ainfo.get("assoc") == "rejected":
                links.append("⚠️ 编号=全文库%s 但双核验未过, 需人工核对: %s" % (_num, full_cit[:70]))
            else:
                links.append("建议引文(编号=全文库%s): %s" % (_num, full_cit[:70]))
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
