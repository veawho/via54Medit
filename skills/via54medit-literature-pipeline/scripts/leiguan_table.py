#!/usr/bin/env python3
"""TMA 在线表 → 雷管方案格式(对齐飞书上「雷管方案—逐页引用表」模板)
列: PPT页 | 第几条 | 引用语义（上下文） | PPT中的文献引用 完整字段 | DOI | 类型 | 对应PDF文件 | 来源链接 → 阅读全文
用法: python3 leiguan_table.py --write   (生成并写入飞书)
      python3 leiguan_table.py           (仅生成 /tmp/tma_leiguan_final.json)
数据源: 本地表 + verify slide_topic + CrossRef DOI(中文期刊/UpToDate 标无 DOI)"""
import sys, json, csv, re, os, glob, time

BASE = '/Users/david/Desktop/TMA_文献整理'
CIT = f'{BASE}/_citation_table/tma_citation_table.csv'

def clean_doi(cit, doi):
    if 'uptodate' in cit.lower():
        return None
    if re.search(r'[\u4e00-\u9fff]{3,}', cit):
        return None
    return doi

def ref_type(cit, title):
    t = (cit + ' ' + title).lower()
    if any(k in t for k in ['指南', '共识', 'guideline', 'consensus', '标准', '专家共识']): return '指南'
    if any(k in t for k in ['病例', 'case report']): return '病例报告'
    if any(k in t for k in ['rct', 'randomized']): return 'RCT 试验'
    if any(k in t for k in ['registry', 'survey', '调查']): return '数据'
    return '文献'

def load_doi():
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from step3_download import crossref_lookup
        out = {}
        with open(CIT, encoding='utf-8-sig') as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            hits = crossref_lookup(r['引用'])
            out[r['PN']] = next((h['doi'] for h in hits if h.get('doi')), None)
            time.sleep(0.4)
        return out
    except Exception as e:
        print('CrossRef 失败, 用空 DOI:', e)
        return {}

def load_topics():
    out = {}
    for vj in glob.glob(f'{BASE}/step4_highlight_106目录_合并DOI/*/*_verify.json'):
        pn = os.path.basename(vj).replace('_verify.json', '')
        try:
            v = json.load(open(vj))
            t = re.split(r'\s*##\s*', v.get('slide_topic', ''))[0].strip()
            if t: out[pn] = t
        except Exception:
            pass
    return out

def build():
    with open(CIT, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    doi_map = load_doi()
    topics = load_topics()
    out = []
    for r in rows:
        pn = r['PN']
        vj = f'{BASE}/step4_highlight_106目录_合并DOI/{pn}/{pn}_verify.json'
        title = json.load(open(vj)).get('title', '') if os.path.exists(vj) else ''
        doi = clean_doi(r['引用'], doi_map.get(pn))
        main = f'{BASE}/step4_highlight_106目录_合并DOI/{pn}/{pn}_main.pdf'
        out.append({
            'PPT页': r['幻灯片'], '第几条': r['引用序号'],
            '引用语义（上下文）': topics.get(pn, ''),
            'PPT中的文献引用 完整字段': r['引用'],
            'DOI': doi if doi else '备注: 无 DOI (中文期刊 / UpToDate / 未解析)',
            '类型': ref_type(r['引用'], title),
            '对应PDF文件': f'{pn}/{pn}_main.pdf' if os.path.exists(main) else f'{pn}/(缺 PDF)',
            '来源链接 → 阅读全文': f'🎯 {pn} — {title[:40]}' if title else f'🎯 {pn}',
        })
    json.dump(out, open('/tmp/tma_leiguan_final.json', 'w'), ensure_ascii=False, indent=1)
    return out

if __name__ == '__main__':
    rows = build()
    print(f'生成 {len(rows)} 行(雷管方案格式) → /tmp/tma_leiguan_final.json')
    if '--write' in sys.argv:
        sys.path.insert(0, os.path.dirname(__file__))
        from feishu_write import write_sheet_values
        write_sheet_values('Nf84sqBbqh0zcjtUCAZcGRkknMe', '4805fc', rows)
        print('已写入飞书在线表')

### v4 更新(2026-08-14)
- H 列补充: 主文件块含「📥 在线访问」(DOI 解析 / PMC / UpToDate; 中文期刊标暂无)
- DOI 列与 H 列用 Markdown 链接 [doi](https://doi.org/doi) → 飞书自动转可点击超链接
- 4-tier 二级: DOI/在线链接
- 注意: file:// 中文路径在飞书会被截断, 本地路径用反引号纯文本
