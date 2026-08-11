#!/usr/bin/env python3
"""
清理 hash 重复 Pn-x 的 highlight PDF.

规则: 在每个 hash 重复组里, 保留 cite 最多 + lex tie break 的 Pn-x, 其他全删.
"""
import os, hashlib, json, re, sys
from collections import defaultdict

TMA = '/Users/david/Desktop/TMA_文献整理'
LEIGUAN = '/Users/david/Desktop/雷管方案_文献整理'

# 从 _2_pdfs 算 hash 重复组
def get_hash_dup_groups(root_dir):
    src_dir = os.path.join(root_dir, '_2_pdfs')
    if not os.path.isdir(src_dir):
        return {}
    groups = defaultdict(list)
    for f in sorted(os.listdir(src_dir)):
        if not f.endswith('_main.pdf'): continue
        path = os.path.join(src_dir, f)
        h = hashlib.md5(open(path, 'rb').read()).hexdigest()
        # extract Pn-x from filename
        m = re.match(r'^(P\d+-\d+(?:-P\d+-\d+)?)_main\.pdf$', f)
        if m:
            groups[h].append(m.group(1))
    return {h: g for h, g in groups.items() if len(g) > 1}

# 解析 Pn-x 命名, 取 slide 数字
def slide_of(pn):
    # P3-1 → 3, P23-24-P24-1 → 23 (first segment)
    m = re.match(r'^P(\d+)-', pn)
    if m: return int(m.group(1))
    return 999

# 从 json/csv 里读 Pn-x → slide 映射
def load_pn_slide_map(root_dir):
    pn_slide = defaultdict(set)
    for r, _, files in os.walk(root_dir):
        if any(x in r for x in ['.git', '__pycache__', '_3_highlight_v10_glm/_jpgs']):
            continue
        for f in files:
            if not (f.endswith('.json') or f.endswith('.csv')): continue
            path = os.path.join(r, f)
            try:
                text = open(path, encoding='utf-8', errors='ignore').read()
            except: continue
            # 1. JSON style
            for m in re.finditer(r'"pn_x"\s*:\s*"(P\d+-\d+(?:-P\d+-\d+)?)"[^}]*?"slide"\s*:\s*(\d+)', text):
                pn_slide[m.group(1)].add(int(m.group(2)))
            for m in re.finditer(r'"slide"\s*:\s*(\d+)[^}]*?"pn_x"\s*:\s*"(P\d+-\d+(?:-P\d+-\d+)?)"', text):
                pn_slide[m.group(2)].add(int(m.group(1)))
            # 2. CSV
            for line in text.split('\n'):
                m = re.match(r'^\"?P(\d+)-(\d+(?:-P\d+-\d+)?)\"?\s*,\s*(\d+)\s*,', line)
                if m:
                    pn = f'P{m.group(1)}-{m.group(2)}'
                    pn_slide[pn].add(int(m.group(3)))
    return pn_slide

# 选 keep
def is_pseudo_name(pn):
    """双 dash 伪名 (build_missing_plans.py bug 造的), 一定不是规范 Pn-x"""
    # P23-24-P24-1 形式
    return bool(re.match(r'^P\d+-\d+-P\d+-\d+$', pn))

def select_keep(grp, pn_slide):
    """keep 规则:
    1. 排除双 dash 伪名 (P23-24-P24-1 之类, build_missing_plans.py 造的)
    2. cite 最多
    3. tie → 命名 slide 编号最小 (P5-x 比 P9-x 优先)
    4. tie → lex first
    """
    # 先排除伪名
    real = [p for p in grp if not is_pseudo_name(p)]
    if not real:
        real = grp  # 全是伪名则保留 lex first
    def score(pn):
        sl = sorted(pn_slide.get(pn, set()))
        # score: (cite 越多越优先, slide 越小越优先, lex first)
        return (-len(sl), slide_of(pn), pn)
    best = min(real, key=score)
    return best

def clean(root_dir, project_name):
    print(f'\n========== {project_name}: {root_dir} ==========')
    groups = get_hash_dup_groups(root_dir)
    pn_slide = load_pn_slide_map(root_dir)
    print(f'hash dup groups: {len(groups)}')
    
    keep_all, del_all = set(), set()
    for h, grp in sorted(groups.items(), key=lambda x: min(x[1])):
        keep = select_keep(grp, pn_slide)
        keep_all.add(keep)
        dels = [p for p in grp if p != keep]
        del_all.update(dels)
        cmt = []
        for p in grp:
            sl = sorted(pn_slide.get(p, set()))
            cmt.append(f'{p}(cite={len(sl)},min_slide={slide_of(p)})')
        print(f'  KEEP={keep}  DEL={dels}')
        print(f'    {" vs ".join(cmt)}')
    
    print(f'\nTotal keep: {len(keep_all)}, del: {len(del_all)}')
    
    # 删 highlight PDF
    highlight_dirs = []
    for d in os.listdir(root_dir):
        if d.startswith('_3_highlight') and os.path.isdir(os.path.join(root_dir, d)):
            highlight_dirs.append(os.path.join(root_dir, d))
    
    n_deleted = 0
    for hdir in highlight_dirs:
        for pn in del_all:
            for fname in os.listdir(hdir):
                # 匹配 Pn-x 开头
                if fname == f'{pn}_semantic_highlight.pdf' or fname == f'{pn}_highlight.pdf':
                    fp = os.path.join(hdir, fname)
                    try:
                        os.remove(fp)
                        n_deleted += 1
                        print(f'  DEL {os.path.relpath(fp, root_dir)}')
                    except Exception as e:
                        print(f'  ERR del {fp}: {e}')
                elif fname.startswith(pn + '_') and fname.endswith('.pdf'):
                    # 任何 Pn-x 开头的 PDF
                    fp = os.path.join(hdir, fname)
                    try:
                        os.remove(fp)
                        n_deleted += 1
                        print(f'  DEL {os.path.relpath(fp, root_dir)}')
                    except Exception as e:
                        print(f'  ERR del {fp}: {e}')
    
    print(f'\nTotal files deleted: {n_deleted}')
    return keep_all, del_all

if __name__ == '__main__':
    keep_tma, del_tma = clean(TMA, 'TMA')
    keep_lg, del_lg = clean(LEIGUAN, '雷管方案')
    
    # save lists
    out = {
        'TMA': {'keep': sorted(keep_tma), 'del': sorted(del_tma)},
        '雷管方案': {'keep': sorted(keep_lg), 'del': sorted(del_lg)},
    }
    with open('/tmp/clean_hash_dup_decision.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f'\n=== Decision saved to /tmp/clean_hash_dup_decision.json ===')
