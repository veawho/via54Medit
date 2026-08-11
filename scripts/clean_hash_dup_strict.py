#!/usr/bin/env python3
"""
彻底清理 hash 重复 Pn-x 的 highlight PDF (所有 _3_highlight* 目录).

规则:
1. 排除双 dash 伪名 (P23-24-P24-1)
2. cite 最多
3. tie → 命名 slide 编号最小
4. tie → lex first

输出:
- 删除所有 DEL Pn-x 的 highlight PDF
- 打印 KEEP 列表 (用于下一步重跑)
"""
import os, hashlib, json, re, sys
from collections import defaultdict

TMA = '/Users/david/Desktop/TMA_文献整理'
LEIGUAN = '/Users/david/Desktop/雷管方案_文献整理'


def get_hash_dup_groups(root_dir):
    src_dir = os.path.join(root_dir, '_2_pdfs')
    if not os.path.isdir(src_dir):
        return {}
    groups = defaultdict(list)
    for f in sorted(os.listdir(src_dir)):
        if not f.endswith('_main.pdf'):
            continue
        m = re.match(r'^(P\d+-\d+(?:-P\d+-\d+)?)_main\.pdf$', f)
        if not m:
            continue
        path = os.path.join(src_dir, f)
        h = hashlib.md5(open(path, 'rb').read()).hexdigest()
        groups[h].append(m.group(1))
    return {h: g for h, g in groups.items() if len(g) > 1}


def is_pseudo_name(pn):
    return bool(re.match(r'^P\d+-\d+-P\d+-\d+$', pn))


def slide_of(pn):
    m = re.match(r'^P(\d+)-', pn)
    return int(m.group(1)) if m else 999


def load_pn_slide_map(root_dir):
    pn_slide = defaultdict(set)
    skip_dirs = ['.git', '__pycache__', 'node_modules']
    for r, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            if not (f.endswith('.json') or f.endswith('.csv')):
                continue
            path = os.path.join(r, f)
            try:
                text = open(path, encoding='utf-8', errors='ignore').read()
            except Exception:
                continue
            for m in re.finditer(r'"pn_x"\s*:\s*"(P\d+-\d+(?:-P\d+-\d+)?)"[^}]*?"slide"\s*:\s*(\d+)', text):
                pn_slide[m.group(1)].add(int(m.group(2)))
            for m in re.finditer(r'"slide"\s*:\s*(\d+)[^}]*?"pn_x"\s*:\s*"(P\d+-\d+(?:-P\d+-\d+)?)"', text):
                pn_slide[m.group(2)].add(int(m.group(1)))
            for line in text.split('\n'):
                m = re.match(r'^\"?P(\d+)-(\d+(?:-P\d+-\d+)?)\"?\s*,\s*(\d+)\s*,', line)
                if m:
                    pn = f'P{m.group(1)}-{m.group(2)}'
                    pn_slide[pn].add(int(m.group(3)))
    return pn_slide


def select_keep(grp, pn_slide):
    real = [p for p in grp if not is_pseudo_name(p)]
    if not real:
        real = grp

    def score(pn):
        sl = sorted(pn_slide.get(pn, set()))
        return (-len(sl), slide_of(pn), pn)

    return min(real, key=score)


def parse_pn_from_filename(fname):
    """从 highlight PDF 文件名提取 Pn-x (支持 P3-1, P23-24-P24-1, P31-6 等)"""
    m = re.match(r'^(P\d+-\d+(?:-P\d+-\d+)?)_', fname)
    return m.group(1) if m else None


def clean_project(root_dir, project_name, dry_run=False):
    print(f'\n========== {project_name}: {root_dir} ==========')
    groups = get_hash_dup_groups(root_dir)
    pn_slide = load_pn_slide_map(root_dir)
    
    keep_all, del_all = set(), set()
    for h, grp in groups.items():
        keep = select_keep(grp, pn_slide)
        keep_all.add(keep)
        del_all.update(p for p in grp if p != keep)
    
    print(f'hash dup groups: {len(groups)}')
    print(f'KEEP: {sorted(keep_all)}')
    print(f'DEL: {sorted(del_all)}')
    
    # 找所有 _3_highlight* 目录
    highlight_dirs = []
    for d in sorted(os.listdir(root_dir)):
        if d.startswith('_3_highlight') and os.path.isdir(os.path.join(root_dir, d)):
            highlight_dirs.append(os.path.join(root_dir, d))
    
    n_deleted = 0
    n_kept = 0
    for hdir in highlight_dirs:
        for fname in sorted(os.listdir(hdir)):
            pn = parse_pn_from_filename(fname)
            if not pn or not fname.endswith('.pdf'):
                continue
            fp = os.path.join(hdir, fname)
            if pn in del_all:
                if dry_run:
                    print(f'  WOULD DEL  {os.path.relpath(fp, root_dir)}')
                else:
                    try:
                        os.remove(fp)
                        print(f'  DEL  {os.path.relpath(fp, root_dir)}')
                        n_deleted += 1
                    except Exception as e:
                        print(f'  ERR  {fp}: {e}')
            else:
                n_kept += 1
    
    if not dry_run:
        print(f'\nDeleted: {n_deleted}, Kept: {n_kept}')
    
    return keep_all, del_all


if __name__ == '__main__':
    dry = '--dry' in sys.argv
    keep_tma, del_tma = clean_project(TMA, 'TMA', dry_run=dry)
    keep_lg, del_lg = clean_project(LEIGUAN, '雷管方案', dry_run=dry)
    
    out = {
        'TMA': {'keep': sorted(keep_tma), 'del': sorted(del_tma)},
        '雷管方案': {'keep': sorted(keep_lg), 'del': sorted(del_lg)},
    }
    with open('/tmp/clean_hash_dup_decision.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f'\n=== Decision saved to /tmp/clean_hash_dup_decision.json ===')
