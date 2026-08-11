#!/usr/bin/env python3
"""run_missing_v2.py — 多线程跑 TMA missing plans, 用 fixed targets"""
import os, sys, json, time
sys.path.insert(0, '/Users/david/Desktop/developments/via54Medit/scripts')
from semantic_highlight_workflow import _process_one
from concurrent.futures import ThreadPoolExecutor, as_completed

# 加载 plans
plans_path = '/Users/david/Desktop/TMA_文献整理/_3_highlight_vision/_highlight_plans.json'
plans = json.load(open(plans_path))['plans']

# 找 missing
v141_dir = '/Users/david/Desktop/TMA_文献整理/_3_highlight_semantic_v141'
out_dir = '/Users/david/Desktop/TMA_文献整理/_3_highlight_semantic_v142'
os.makedirs(out_dir, exist_ok=True)
project_root = '/Users/david/Desktop/TMA_文献整理'

done = set()
for f in os.listdir(v141_dir):
    if f.endswith('.pdf'):
        done.add(f.replace('_semantic_highlight.pdf', ''))
for f in os.listdir(out_dir):
    if f.endswith('.pdf'):
        done.add(f.replace('_semantic_highlight.pdf', ''))

missing = [p for p in plans if p.get('pn_x') not in done]
print(f'v141+v142 done: {len(done)}')
print(f'Missing: {len(missing)}')

# 写 summary
summary = []

# 4 worker 并行
workers = 4
def process(idx_total):
    i, p = idx_total
    pn_x = p.get('pn_x')
    r = _process_one(p, project_root, out_dir, 'line', i, len(missing))
    r['pn_x'] = pn_x
    r['target_text'] = p.get('target_text', '')[:80]
    return r

print(f'Running with {workers} workers...')
start = time.time()
with ThreadPoolExecutor(max_workers=workers) as executor:
    futures = {executor.submit(process, (i, p)): p for i, p in enumerate(missing, 1)}
    for future in as_completed(futures):
        try:
            r = future.result()
            summary.append(r)
            elapsed = time.time() - start
            print(f'  [{len(summary)}/{len(missing)}] {r["pn_x"]}: ok={r.get("ok")} matches={r.get("matches")} hl={r.get("highlight_count", 0)} reason={r.get("reason", "")[:50]} | {elapsed:.0f}s', flush=True)
        except Exception as e:
            p = futures[future]
            print(f'  ERR {p.get("pn_x")}: {e}', flush=True)
            summary.append({'pn_x': p.get('pn_x'), 'ok': False, 'reason': f'err: {e}'})

# 写 summary
ok = sum(1 for r in summary if r.get('ok'))
print(f'\n=== DONE: {ok}/{len(summary)} OK in {time.time()-start:.0f}s ===')
json.dump(summary, open(out_dir + '/_semantic_summary.json', 'w'), ensure_ascii=False, indent=2)
print(f'→ Summary: {out_dir}/_semantic_summary.json')
