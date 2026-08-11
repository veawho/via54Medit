#!/usr/bin/env python3
"""找出 _2_pdfs (90) 和理论 106 PDF 的差异"""
import os, json

plans = json.load(open('/Users/david/Desktop/TMA_文献整理/_3_highlight_vision/_highlight_plans.json', encoding='utf-8'))
plans = plans if isinstance(plans, list) else plans['plans']
plan_pn = set(p['pn_x'] for p in plans)
src_pn = set(f.replace('_main.pdf', '') for f in os.listdir('/Users/david/Desktop/TMA_文献整理/_2_pdfs') if f.endswith('.pdf'))

# 11 不可救
UNREC = {'P5-1', 'P30-4', 'P14-1', 'P19-1',
         'P23-22', 'P28-1', 'P31-4', 'P31-5', 'P31-6', 'P31-8', 'P4-3'}

recoverable = plan_pn - UNREC
print(f'plan unique: {len(plan_pn)}')
print(f'UNREC (11 不可救): {len(UNREC)}')
print(f'理论可救: {len(recoverable)} = 117 - 11 = 106 ✓ (用户记的 106)')
print(f'_2_pdfs 实际: {len(src_pn)}')
print(f'\\n理论可救 ∩ _2_pdfs: {len(recoverable & src_pn)}')
print(f'理论可救 ∖ _2_pdfs (差): {len(recoverable - src_pn)}')

print(f'\\n=== 理论可救但 _2_pdfs 缺的 15 个 Pn-x ===')
for p in sorted(recoverable - src_pn):
    print(f'  {p}')

# UNREC 但 _2_pdfs 有
print(f'\\n=== UNREC 但 _2_pdfs 有 (8 个) ===')
for p in sorted(UNREC & src_pn):
    print(f'  {p}')

# KEEP/DEL 状态
DECISION = json.load(open('/tmp/clean_hash_dup_decision.json', encoding='utf-8'))
KEEP = set(DECISION['TMA']['keep'])
DEL = set(DECISION['TMA']['del'])
print(f'\\nUNREC ∩ KEEP: {sorted(UNREC & KEEP)}')
print(f'UNREC ∩ DEL: {sorted(UNREC & DEL)}')

# 15 缺里在 KEEP / DEL
miss = recoverable - src_pn
print(f'\\n15 缺里 KEEP: {sorted(miss & KEEP)}')
print(f'15 缺里 DEL: {sorted(miss & DEL)}')
print(f'15 缺里 既不是 KEEP 也不是 DEL (unique): {sorted(miss - KEEP - DEL)}')
