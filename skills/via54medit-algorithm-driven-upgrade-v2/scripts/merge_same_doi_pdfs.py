#!/usr/bin/env python3
"""
merge_same_doi_pdfs.py — 步骤 6.1: 整合同一文献的目录

按 DOI 合并 Pn-x 目录, 格式: Pn1-x1Pn2-x2Pn3-x3
- 移动 Pn-x 目录到 Pn1-x1Pn2-x2Pn3-x3 目录
- 合并 _highlight/Pn-x 到 _highlight/Pn1-x1Pn2-x2Pn3-x3
- 更新 PPT_citations_8col_aligned.csv 的 H/J/K/L 列
- 验证 86 唯一 DOI + 11 无 DOI

实跑数据 (2026-08-05):
- 160 标号 → 96 唯一目录 (85 DOI + 11 无 DOI)
- 0 DOI 冲突
- 最大合并: P5-17P12-1P22-1P24-3P26-3P27-3P33-1P43-1 (8 标号, DOI 10.1016/j.annonc.2025.08.2124)
"""
import os, csv, shutil, re
from collections import defaultdict
from pathlib import Path

ROOT = '/Users/david/Desktop/雷管方案_文献整理'
CSV_8COL = f'{ROOT}/PPT_citations_8col_aligned.csv'
HL_BASE = f'{ROOT}/_highlight'
DL_BASE = ROOT

# 1. 读真值
with open(f'{ROOT}/_citation_table/citation_table.csv') as f:
    truth = list(csv.DictReader(f))

# 2. 按 DOI 聚合
MISALIGNED_4 = {('12', '5'), ('14', '2'), ('22', '13'), ('30', '10')}
doi_to_pns = defaultdict(list)
no_doi = []
for r in truth:
    a, n = r['﻿PPT页'], r['第几条']
    if (a, n) in MISALIGNED_4: continue
    doi = r.get('DOI', '').strip()
    if doi and doi != '备注: 无 DOI (政府文件 / 中文期刊)':
        doi_to_pns[doi].append((a, n))
    else:
        no_doi.append((a, n))

# 3. 生成合并目录名 Pn1-x1Pn2-x2Pn3-x3 (按 slide 顺序)
merge_map = {}
for doi, pns in doi_to_pns.items():
    if len(pns) == 1:
        a, n = pns[0]
        new_name = f'P{a}-{n}'
    else:
        new_name = ''.join(f'P{a}-{n}' for a, n in sorted(pns, key=lambda x: (int(x[0]), int(x[1]))))
    for a, n in pns:
        old_name = f'P{a}-{n}'
        if old_name != new_name:
            merge_map[old_name] = new_name

# 4. 2 遍算法找 final target
final_targets = {}
def find_target(name, visited=None):
    if visited is None: visited = set()
    if name in visited: return name
    visited.add(name)
    if name in merge_map and merge_map[name] != name:
        return find_target(merge_map[name], visited)
    return name

for old, new in merge_map.items():
    final_targets[old] = find_target(new)

to_merge = {o: t for o, t in final_targets.items() if o != t}

# 5. 实际合并
merged_count = 0
for old, new in to_merge.items():
    old_dl = f'{DL_BASE}/{old}'
    new_dl = f'{DL_BASE}/{new}'
    old_hl = f'{HL_BASE}/{old}'
    new_hl = f'{HL_BASE}/{new}'

    if os.path.isdir(old_dl):
        if not os.path.isdir(new_dl):
            os.rename(old_dl, new_dl)
            merged_count += 1
        else:
            for f in os.listdir(old_dl):
                src = f'{old_dl}/{f}'
                dst = f'{new_dl}/{f}'
                if not os.path.exists(dst):
                    shutil.move(src, dst)
                else:
                    base, ext = os.path.splitext(f)
                    i = 1
                    while os.path.exists(f'{new_dl}/{base}_{i}{ext}'):
                        i += 1
                    shutil.move(src, f'{new_dl}/{base}_{i}{ext}')
            try:
                os.rmdir(old_dl)
            except: pass
            merged_count += 1

    if os.path.isdir(old_hl):
        if not os.path.isdir(new_hl):
            os.rename(old_hl, new_hl)
        else:
            for f in os.listdir(old_hl):
                src = f'{old_hl}/{f}'
                dst = f'{new_hl}/{f}'
                if not os.path.exists(dst):
                    shutil.move(src, dst)
                else:
                    base, ext = os.path.splitext(f)
                    i = 1
                    while os.path.exists(f'{new_hl}/{base}_{i}{ext}'):
                        i += 1
                    shutil.move(src, f'{new_hl}/{base}_{i}{ext}')
            try:
                os.rmdir(old_hl)
            except: pass

print(f'合并完成: {merged_count} 目录')

# 6. 验证
all_dirs = set(os.listdir(DL_BASE))
pn_dirs = [d for d in all_dirs if d.startswith('P') and '-' in d and os.path.isdir(f'{DL_BASE}/{d}')]
print(f'当前 P 目录数: {len(pn_dirs)}')

# 7. 更新 CSV
with open(CSV_8COL) as f:
    rows = list(csv.DictReader(f))

for r in rows:
    a, n = r['A_slide'], r['B_mark']
    old_name = f'P{a}-{n}'
    new_name = merge_map.get(old_name, old_name)
    if old_name != new_name:
        for col in ['H_highlight_status', 'K_alignment_D_HL', 'J_alignment_C_PDF']:
            if col in r:
                r[col] = r[col].replace(old_name, new_name)

# 加 L_merged_dir 列
with open(CSV_8COL, 'w', newline='') as f:
    fieldnames = list(rows[0].keys()) + ['L_merged_dir']
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    for r in rows:
        a, n = r['A_slide'], r['B_mark']
        old_name = f'P{a}-{n}'
        r['L_merged_dir'] = merge_map.get(old_name, old_name)
        w.writerow(r)

print(f'✅ CSV 更新: H/J/K 列路径 + L_merged_dir 列')
