#!/usr/bin/env python3
"""表同步: step2 提取的引用 → 本地表(CSV/JSON)与在线表(飞书)对齐
用法: python3 sync_table.py <refs.json> <tma_citation.csv> [--feishu-out <csv>]
- 本地表: 更新引用文本列(以提取结果为准, 取更长更完整), 保留 MD5/页数/Highlight 等列
- 在线表(飞书): 生成 A_slide/B_mark/C_citation 格式同步 CSV(供回传飞书)"""
import sys, json, csv, re, os

def norm(t): return re.sub(r'[\s\u3000]+', '', t.lower())

def main():
    if len(sys.argv) < 3:
        print('usage: sync_table.py <refs.json> <tma_citation.csv> [--feishu-out <csv>]')
        sys.exit(1)
    refs = json.load(open(sys.argv[1], encoding='utf-8'))
    csv_path = sys.argv[2]
    feishu_out = None
    if '--feishu-out' in sys.argv:
        feishu_out = sys.argv[sys.argv.index('--feishu-out') + 1]

    # 同键多值(如 slide31 编号重复的 Laurence/Jiang): 保留首个(与 Pn-x 编号体系一致), 供诊断
    ref_map = {}
    for r in refs:
        ref_map.setdefault((r['slide'], r['num']), r['text'])
    with open(csv_path, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    fields = list(rows[0].keys())
    changed = []
    for r in rows:
        pn = r['PN'].strip()
        m = re.match(r'^P(\d+)-(\d+)$', pn)
        if not m:
            continue
        slide, num = int(m.group(1)), int(m.group(2))
        new_text = ref_map.get((slide, num))
        if new_text and len(norm(new_text)) > len(norm(r.get('引用', ''))):
            r['引用'] = new_text
            changed.append((pn, '引用'))
    with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f'本地表更新 {len(changed)} 行引用: {changed[:8]}...')

    if feishu_out:
        with open(feishu_out, 'w', encoding='utf-8-sig', newline='') as f:
            w = csv.writer(f)
            w.writerow(['A_slide', 'B_mark', 'C_citation'])
            for r in refs:
                w.writerow([r['slide'], r['num'], r['text']])
        print(f'飞书同步文件 → {feishu_out} ({len(refs)} 行)')

def align_online_table(online_csv, local_csv, out_csv):
    """在线表(飞书)对齐: C_citation 用本地表权威文本替换, 删除本地不存在的 Pn(如 P31-8/9), 保留全列"""
    with open(online_csv, encoding='utf-8-sig') as f:
        online = list(csv.DictReader(f))
    with open(local_csv, encoding='utf-8-sig') as f:
        local = list(csv.DictReader(f))
    local_map = {r['PN'].strip(): r for r in local}
    fields = list(online[0].keys())
    fixed = []
    kept = []
    for r in online:
        pn = f"P{r['A_slide']}-{r['B_mark']}"
        if pn not in local_map:  # 本地(雷管方案)不存在的 Pn 删除
            continue
        lc = local_map[pn].get('引用', '')
        if lc and norm(r.get('C_citation', '')) != norm(lc):
            r['C_citation'] = lc
            fixed.append(pn)
        if None in r:
            r.pop(None)
        for fld in fields:
            r.setdefault(fld, '')
        kept.append(r)
    with open(out_csv, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(kept)
    print(f'在线表对齐: 修正 {len(fixed)} 条引用, 输出 {len(kept)} 行 → {out_csv}')
    return kept

if __name__ == '__main__':
    main()
