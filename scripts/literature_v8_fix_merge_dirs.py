#!/usr/bin/env python3
"""
V4-26-fix: 整合 _literature_citation_index/ 下散乱的单 Pn-x 目录到合并目录
========================================================

问题: process_pn_x.py 第一版每个 Pn-x 单独建目录, 没合并到 P4-1_P36-1 等合并目录

修法:
1. 扫描所有 Pn-x 单独目录 (无 _ 的)
2. 计算每个 PDF 的 md5
3. 找出该 md5 在 CSV 中所有 row, 按 row order 算合并目录名
4. 把散乱的 Pn-x 目录内容合并到正确合并目录
5. 删除散乱的空目录
"""

import os, csv, hashlib, shutil

BASE = '/Users/david/Desktop/雷管方案_文献整理'
CSV = os.path.join(BASE, '_citation_table', 'citation_table.csv')
ARCHIVE = os.path.join(BASE, '_literature_citation_index')


def md5_of(p):
    try:
        with open(p, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except:
        return None


def main():
    with open(CSV, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))

    # 1. 按 md5 找所有 Pn-x
    md5_groups = {}
    for i, r in enumerate(rows):
        pf = r['对应PDF文件']
        if not pf: continue
        full_p = os.path.join(BASE, pf)
        if not os.path.exists(full_p): continue
        m = md5_of(full_p)
        if not m: continue
        pn = f"P{r['PPT页']}-{r['第几条']}"
        md5_groups.setdefault(m, []).append((i, pn, full_p))

    # 2. 按 CSV row order 算每个 md5 的合并目录名
    group_dirs = {}
    for m, items in md5_groups.items():
        items.sort()  # CSV row order
        pns = [x[1] for x in items]
        group_dirs[m] = '_'.join(pns)

    # 3. 看 ARCHIVE 现状
    print('=== ARCHIVE 当前目录 ===')
    existing = set(os.listdir(ARCHIVE))
    for dn in sorted(existing):
        if os.path.isdir(os.path.join(ARCHIVE, dn)):
            print(f'  {dn}')

    # 4. 处理每个合并目录
    print('\n=== 整合散乱目录 ===')
    moved = 0
    deleted = 0
    for m, target_name in group_dirs.items():
        target_dir = os.path.join(ARCHIVE, target_name)
        items = md5_groups[m]
        # 找出所有散乱的单 Pn-x 目录 (target_name 不含 '_' 时跳过)
        if '_' not in target_name:
            # 单 Pn-x, 不需要合并
            # 但可能之前有同名目录
            continue

        # 找 items 里每个 Pn-x 的散乱目录
        for i, pn, src_pdf in items:
            single_dir = os.path.join(ARCHIVE, pn)
            if not os.path.isdir(single_dir):
                continue
            # 合并文件
            os.makedirs(target_dir, exist_ok=True)
            for f in os.listdir(single_dir):
                src = os.path.join(single_dir, f)
                dst = os.path.join(target_dir, f)
                if not os.path.exists(dst):
                    shutil.move(src, dst)
                    moved += 1
                else:
                    os.remove(src)  # 重复, 删
            # 删空目录
            try:
                os.rmdir(single_dir)
                deleted += 1
                print(f'  ✓ {pn}/ → {target_name}/')
            except:
                pass

    print(f'\n=== 完成 ===')
    print(f'移动文件: {moved}')
    print(f'删除目录: {deleted}')
    print(f'\n=== 最终目录 ===')
    final = [d for d in sorted(os.listdir(ARCHIVE)) if os.path.isdir(os.path.join(ARCHIVE, d))]
    for dn in final:
        n_pdf = sum(1 for f in os.listdir(os.path.join(ARCHIVE, dn)) if f.endswith('.pdf'))
        n_jpg = sum(1 for f in os.listdir(os.path.join(ARCHIVE, dn)) if f.endswith('.jpg'))
        print(f'  {dn}: {n_pdf} PDFs, {n_jpg} JPGs')


if __name__ == '__main__':
    main()