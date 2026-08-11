#!/usr/bin/env python3
"""全删 DEL 27 个 Pn-x 的所有冗余文件 (源 PDF / _downloads / _3_highlight_v*_jpgs)"""
import os, json, sys

TMA = '/Users/david/Desktop/TMA_文献整理'
DECISION = json.load(open('/tmp/clean_hash_dup_decision.json', encoding='utf-8'))
DEL = DECISION['TMA']['del']

# 找要删的文件
to_delete = []
for pn in DEL:
    # 1. 源 PDF
    src = f'{TMA}/_2_pdfs/{pn}_main.pdf'
    if os.path.exists(src): to_delete.append(src)
    # 2. _downloads 备份
    for sub in [f'{TMA}/_downloads/_pdfs_real/{pn}.pdf',
                f'{TMA}/_downloads/_pdfs_real/{pn}.pdf.verify.json',
                f'{TMA}/_downloads/_pdfs_real/{pn}.verify.json',
                f'{TMA}/_downloads/{pn}_main.pdf']:
        if os.path.exists(sub): to_delete.append(sub)
    # 3. _3_highlight_v10/*/{pn}_jpgs/ 目录
    for d in os.listdir(TMA):
        if d.startswith('_3_highlight_v') and os.path.isdir(f'{TMA}/{d}/{pn}_jpgs'):
            to_delete.append(f'{TMA}/{d}/{pn}_jpgs')

print(f'TOTAL to delete: {len(to_delete)}')
for p in to_delete: print(f'  {p}')

# 用 mavis-trash
import subprocess
for p in to_delete:
    if os.path.isdir(p):
        subprocess.run(['mavis-trash', '--recursive', p], capture_output=True)
    else:
        subprocess.run(['mavis-trash', p], capture_output=True)
    print(f'  DELETED: {p}')

print(f'\n=== Deleted {len(to_delete)} items ===')
