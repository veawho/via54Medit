#!/usr/bin/env python3
"""补跑 36 个 MISSING unique Pn-x (m3_pick_body_anchor)"""
import project_paths
import json, os, sys, time, tempfile
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import m3_pick_body_anchor as mpb

TMA = project_paths.TMA_ROOT
DECISION = json.load(open(os.path.join(tempfile.gettempdir(), 'clean_hash_dup_decision.json'), encoding='utf-8'))
KEEP = set(DECISION['TMA']['keep'])
DEL = set(DECISION['TMA']['del'])

PLANS = json.load(open(f'{TMA}/_3_highlight_vision/_highlight_plans.json', encoding='utf-8'))
PLANS = PLANS if isinstance(PLANS, list) else PLANS['plans']
all_pn = set(p['pn_x'] for p in PLANS)
unique_only = all_pn - KEEP - DEL

M3 = f'{TMA}/_3_highlight_semantic_m3'
m3_existing = set(f.replace('_semantic_highlight.pdf', '') for f in os.listdir(M3) if f.endswith('.pdf'))
missing = unique_only - m3_existing

print(f'MISSING to run: {len(missing)}')

plan_by_pn = {p['pn_x']: p for p in PLANS}
results = defaultdict(list)
t0 = time.time()
for i, pn in enumerate(sorted(missing), 1):
    plan = plan_by_pn.get(pn, {})
    pdf = plan.get('pdf_path', '')
    if not os.path.isfile(pdf):
        results['no_pdf'].append(pn)
        continue
    status, detail = mpb.process_pn_x(pn, pdf, M3)
    results[status].append((pn, detail))
    if i % 5 == 0:
        print(f'  [{i}/{len(missing)}] done in {time.time()-t0:.1f}s')

print(f'\n=== 跑完 ({time.time()-t0:.1f}s) ===')
for k, v in results.items():
    print(f'{k}: {len(v)}')

results_path = os.path.join(tempfile.gettempdir(), 'rerun_missing_unique.json')
with open(results_path, 'w', encoding='utf-8') as f:
    json.dump({k: v for k, v in results.items()}, f, ensure_ascii=False, indent=2)
