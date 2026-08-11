#!/usr/bin/env python3
"""
rerun_keep_pn_x.py — 校准重跑 KEEP 19 + m3 目录非冲突 Pn-x.

输入: _highlight_plans.json (117 plans)
过滤:
  1. 在 KEEP 列表 (19) 的 → 必跑
  2. 不在 KEEP 也不在 DEL 列表 → m3 已有的非冲突 Pn-x (30+)
  3. 在 DEL 列表 → 跳过 (已被 clean_hash_dup_strict.py 删)
输出: m3_vision_highlight.py 5 类难 case filter + phrase 模式
"""
import json, os, sys, re, fitz, shutil, subprocess, time
from collections import defaultdict

TMA = '/Users/david/Desktop/TMA_文献整理'
PLANS_FILE = f'{TMA}/_3_highlight_vision/_highlight_plans.json'
OUT_DIR = f'{TMA}/_3_highlight_semantic_m3'
os.makedirs(OUT_DIR, exist_ok=True)

# 加载 keep/del 决策
DECISION = json.load(open('/tmp/clean_hash_dup_decision.json', encoding='utf-8'))
KEEP = set(DECISION['TMA']['keep'])
DEL = set(DECISION['TMA']['del'])

# 加载 plans
plans = json.load(open(PLANS_FILE, encoding='utf-8'))
plans = plans if isinstance(plans, list) else plans['plans']

# m3 目录里现存的 Pn-x (非冲突 = 之前已 highlight 的)
m3_existing = set()
for f in os.listdir(OUT_DIR):
    if f.endswith('_semantic_highlight.pdf'):
        pn = f.replace('_semantic_highlight.pdf', '')
        m3_existing.add(pn)

# 决定要跑的 Pn-x
to_run = set()
# 1. KEEP 19 必跑
to_run.update(KEEP)
# 2. m3 现有非冲突 Pn-x
for pn in m3_existing:
    if pn not in DEL and pn not in KEEP:
        to_run.add(pn)

print(f'KEEP: {len(KEEP)}')
print(f'DEL: {len(DEL)}')
print(f'm3 existing (non-DEL): {len(m3_existing - DEL)}')
print(f'要跑 (KEEP ∪ m3 non-DEL): {len(to_run)}')
print()


def extract_anchor_from_target(target: str) -> str:
    if not target:
        return ''
    t = target.strip()
    t = re.sub(r'\d+[a-z]?\d*$', '', t).strip()
    t = re.sub(r'\[\d+\]|\(\d+\)', '', t).strip()
    if 'http' in t:
        t = t.split('http')[0].strip()
    for sep in ['。', '. ', '，', ', ', '; ', '；']:
        if sep in t:
            t = t.split(sep)[0].strip()
            break
    if len(t) > 60:
        t = t[:60].strip()
    return t


def find_anchor_in_pdf(anchor: str, doc):
    if not anchor or len(anchor) < 4:
        return None
    for pi in [1, 2, 3, 0]:  # 优先 body pages
        if pi >= doc.page_count:
            break
        page = doc[pi]
        min_len = 4 if re.search(r'[\u4e00-\u9fa5]', anchor) else 5
        if len(anchor) < min_len:
            continue
        hits = page.search_for(anchor, quads=False)
        if hits:
            return (pi, hits[0], anchor)
    if len(anchor) > 20:
        short = anchor[:20].strip()
        for pi in [1, 2, 0]:
            if pi >= doc.page_count:
                break
            page = doc[pi]
            hits = page.search_for(short, quads=False)
            if hits:
                return (pi, hits[0], short)
    if len(anchor) > 10:
        short = anchor[:10].strip()
        for pi in [1, 2, 0]:
            if pi >= doc.page_count:
                break
            page = doc[pi]
            hits = page.search_for(short, quads=False)
            if hits:
                return (pi, hits[0], short)
    return None


def run_highlight(pn, pi, anchor):
    """调 m3_vision_highlight.py 应用 underline"""
    cmd = [
        '/Users/david/.hermes/hermes-agent/venv/bin/python',
        '/Users/david/Desktop/developments/via54Medit/scripts/m3_vision_highlight.py',
        '--pn-x', pn,
        '--entries', f'[[{pi}, {json.dumps(anchor)}, "phrase"]]',
        '--out-dir', OUT_DIR,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True,
                        cwd='/Users/david/Desktop/developments/via54Medit',
                        timeout=30)
    ok = 0
    skip = 0
    for line in r.stdout.split('\n'):
        if 'OK=' in line and 'SKIP=' in line:
            m = re.search(r'OK=(\d+).*SKIP=(\d+)', line)
            if m:
                ok, skip = int(m.group(1)), int(m.group(2))
    if r.returncode != 0:
        print(f'    STDERR: {r.stderr[-200:]}')
    return ok, skip


# 主循环
results = defaultdict(list)
plan_by_pn = {p['pn_x']: p for p in plans}

t0 = time.time()
for i, pn in enumerate(sorted(to_run), 1):
    plan = plan_by_pn.get(pn, {})
    pdf = plan.get('pdf_path', '')
    if not pdf or not os.path.isfile(pdf):
        results['no_pdf'].append(pn)
        continue
    target = plan.get('target_text', '') or ''
    anchor = extract_anchor_from_target(target)
    if not anchor:
        results['no_anchor'].append(pn)
        continue

    # 确保 output 存在
    out = f'{OUT_DIR}/{pn}_semantic_highlight.pdf'
    if not os.path.exists(out):
        shutil.copy2(pdf, out)

    # search
    doc = fitz.open(pdf)
    found = find_anchor_in_pdf(anchor, doc)
    doc.close()

    if not found:
        results['no_match'].append((pn, anchor[:40]))
        continue

    pi, rect, hit_text = found
    ok, skip = run_highlight(pn, pi, hit_text)
    if ok > 0:
        results['ok'].append((pn, ok, hit_text[:30]))
    else:
        results['forbidden'].append((pn, hit_text[:30]))

    if i % 10 == 0:
        print(f'  [{i}/{len(to_run)}] done in {time.time()-t0:.1f}s')

# 报告
print(f'\n=== 跑完 ({time.time()-t0:.1f}s) ===')
print(f'OK (成功标): {len(results["ok"])}')
print(f'Forbidden (filter 拒): {len(results["forbidden"])}')
print(f'No match: {len(results["no_match"])}')
print(f'No PDF: {len(results["no_pdf"])}')
print(f'No anchor: {len(results["no_anchor"])}')

if results['forbidden']:
    print(f'\n=== Forbidden (filter 拒的, 需要单独看) ===')
    for pn, txt in results['forbidden']:
        print(f'  {pn:18s} anchor={txt!r}')

if results['no_match']:
    print(f'\n=== No match (需要 M3 vision 单独处理) ===')
    for pn, anc in results['no_match']:
        print(f'  {pn:18s} anchor={anc!r}')

# 保存
with open('/tmp/rerun_keep_pn_x_results.json', 'w', encoding='utf-8') as f:
    json.dump({k: v for k, v in results.items()}, f, ensure_ascii=False, indent=2)
