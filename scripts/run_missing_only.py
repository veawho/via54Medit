#!/usr/bin/env python3
"""run_missing_only.py — 只跑 missing plans (跳过已有 PDF)"""
import os, sys, json
sys.path.insert(0, '/Users/david/Desktop/developments/via54Medit/scripts')
from semantic_highlight_workflow import _process_one

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
print(f'Missing: {len(missing)}')

# 单线程跑
for i, p in enumerate(missing, 1):
    print(f'\n[{i}/{len(missing)}] {p.get("pn_x")}: target={p.get("target_text","")[:60]!r}')
    r = _process_one(p, project_root, out_dir, 'line', i, len(missing))
    print(f'  → ok={r.get("ok")} matches={r.get("matches")} highlights={r.get("highlight_count", 0)} reason={r.get("reason", "")[:60]}')
