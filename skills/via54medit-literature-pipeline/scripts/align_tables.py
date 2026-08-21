#!/usr/bin/env python3
"""TMA 本地表与在线表生成器: 两表与雷管方案(step4 目录)逻辑/列/规则完全一致
- 唯一数据源: step4_highlight_106目录_合并DOI/{Pn-x}/ 目录 + verify.json + 引用表
- 输出两张列完全相同的表: 本地表 tma_citation_table.csv 与 在线表(飞书回传) 同构
用法: python3 align_tables.py [--out-dir _citation_table]"""
import os, sys, json, csv, hashlib, re, glob

BASE = '/Users/david/Desktop/TMA_文献整理'
STEP4 = os.path.join(BASE, 'step4_highlight_106目录_合并DOI')
STEP3 = os.path.join(BASE, 'step3_pdf下载_106目录')
CIT_JSON = os.path.join(BASE, '_citation_table', 'tma_citation_table.json')

# 雷管方案列(A-H, 8 列): 本地表与在线表完全相同
COLUMNS = ['PN', '幻灯片', '引用序号', '引用', 'PDF大小', '已Highlight', 'MD5', '页数']

def load_citations():
    with open(CIT_JSON, encoding='utf-8') as f:
        return {f"P{r['slide']}-{r['num']}": r['text'] for r in json.load(f)}

def build_rows():
    cits = load_citations()
    rows = []
    for d in sorted(os.listdir(STEP4)):
        if not os.path.isdir(os.path.join(STEP4, d)) or not re.match(r'^P\d+-\d+$', d):
            continue
        pn = d
        vj = os.path.join(STEP4, d, f'{pn}_verify.json')
        v = json.load(open(vj, encoding='utf-8')) if os.path.exists(vj) else {}
        m = re.match(r'^P(\d+)-(\d+)$', pn)
        slide, num = int(m.group(1)), int(m.group(2))
        # main.pdf 实测
        main = os.path.join(STEP4, d, f'{pn}_main.pdf')
        md5 = ''; pages = ''; size_kb = ''
        if os.path.exists(main):
            md5 = hashlib.md5(open(main, 'rb').read()).hexdigest()
            size_kb = str(round(os.path.getsize(main) / 1024))
            try:
                import fitz
                doc = fitz.open(main)
                pages = str(len(doc))
                doc.close()
            except Exception:
                pages = v.get('pages', '')
        else:
            md5 = v.get('md5', '')
            pages = str(v.get('pages', ''))
        # 已Highlight: annots>0
        n_ann = v.get('annot_count', 0) or 0
        hl = '✅' if n_ann > 0 else '❌'
        rows.append({
            'PN': pn,
            '幻灯片': slide,
            '引用序号': num,
            '引用': cits.get(pn, ''),
            'PDF大小': f'{size_kb}KB' if size_kb else '',
            '已Highlight': hl,
            'MD5': md5,
            '页数': pages,
        })
    rows.sort(key=lambda r: (r['幻灯片'], r['引用序号']))
    return rows

def write_csv(path, rows):
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)

def main():
    out_dir = sys.argv[sys.argv.index('--out-dir') + 1] if '--out-dir' in sys.argv else os.path.join(BASE, '_citation_table')
    rows = build_rows()
    local = os.path.join(out_dir, 'tma_citation_table.csv')
    online = os.path.join(out_dir, 'tma_citation_table_feishu_ALIGNED.csv')
    write_csv(local, rows)
    write_csv(online, rows)  # 两表同列同数据
    print(f'本地表: {local} ({len(rows)} 行)')
    print(f'在线表: {online} ({len(rows)} 行, 与本地表同列同数据, 可直接回传飞书)')
    # 校验两表一致
    with open(local, encoding='utf-8-sig') as f1, open(online, encoding='utf-8-sig') as f2:
        r1, r2 = list(csv.DictReader(f1)), list(csv.DictReader(f2))
    print('两表逐行一致:', r1 == r2, '| 列:', list(r1[0].keys()) == COLUMNS)

if __name__ == '__main__':
    main()
