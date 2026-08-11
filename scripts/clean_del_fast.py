#!/usr/bin/env python3
"""快速全删 DEL 27 个 Pn-x 的所有冗余 - 用 glob + rm 加快"""
import os, json, sys, subprocess, glob

TMA = '/Users/david/Desktop/TMA_文献整理'
DECISION = json.load(open('/tmp/clean_hash_dup_decision.json', encoding='utf-8'))
DEL = DECISION['TMA']['del']

count = 0
for pn in DEL:
    # 1. 源 PDF
    src = f'{TMA}/_2_pdfs/{pn}_main.pdf'
    if os.path.exists(src):
        os.remove(src)
        count += 1
    # 2. _downloads 备份
    for f in [f'{TMA}/_downloads/_pdfs_real/{pn}.pdf',
              f'{TMA}/_downloads/_pdfs_real/{pn}.pdf.verify.json',
              f'{TMA}/_downloads/_pdfs_real/{pn}.verify.json',
              f'{TMA}/_downloads/{pn}_main.pdf']:
        if os.path.exists(f):
            os.remove(f)
            count += 1
    # 3. _3_highlight_v*_jpgs/ 目录
    for jpg_dir in glob.glob(f'{TMA}/_3_highlight_v*/{pn}_jpgs'):
        import shutil
        shutil.rmtree(jpg_dir)
        count += 1

print(f'Deleted {count} items')
