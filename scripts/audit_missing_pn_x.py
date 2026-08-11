#!/usr/bin/env python3
"""审计 m3 目录 vs 总 Pn-x 数量, 列出缺失的"""
import json, os

TMA = '/Users/david/Desktop/TMA_文献整理'
DECISION = json.load(open('/tmp/clean_hash_dup_decision.json', encoding='utf-8'))
KEEP = set(DECISION['TMA']['keep'])
DEL = set(DECISION['TMA']['del'])

PLANS = json.load(open(f'{TMA}/_3_highlight_vision/_highlight_plans.json', encoding='utf-8'))
PLANS = PLANS if isinstance(PLANS, list) else PLANS['plans']
print(f'TOTAL plans: {len(PLANS)}')

all_pn = set(p['pn_x'] for p in PLANS)
print(f'UNIQUE Pn-x: {len(all_pn)}')
print(f'KEEP (hash dup): {len(KEEP)}')
print(f'DEL (hash dup): {len(DEL)}')
unique_only = all_pn - KEEP - DEL
print(f'Unique (not hash dup): {len(unique_only)}')

M3 = f'{TMA}/_3_highlight_semantic_m3'
m3_existing = set(f.replace('_semantic_highlight.pdf', '') for f in os.listdir(M3) if f.endswith('.pdf'))
print(f'm3 existing: {len(m3_existing)}')
print(f'm3 ∩ KEEP: {len(m3_existing & KEEP)}')
print(f'm3 ∩ unique_only: {len(m3_existing & unique_only)}')
print(f'm3 ∩ DEL (should be 0): {len(m3_existing & DEL)}')

missing = unique_only - m3_existing
print(f'\nMISSING unique Pn-x: {len(missing)}')
for pn in sorted(missing):
    plan = next(p for p in PLANS if p['pn_x'] == pn)
    pdf_exists = os.path.isfile(plan.get('pdf_path', ''))
    print(f'  {pn}: pdf={pdf_exists}, target={plan.get("target_text", "")[:50]!r}')
