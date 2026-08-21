#!/usr/bin/env python3
"""
analyze_ppt_citations_v6_vision_align.py — D 列第一轮视觉对齐 PPT (v3.0.0)

用法:
  python /Users/david/.medit/scripts/analyze_ppt_citations_v6_vision_align.py

输入:
  /Users/david/Desktop/雷管方案_文献整理/_citation_table/citation_table.csv (160 行真值, 飞书 164 - 4 错位)
  /tmp/vision_d_merged.json (来自 subagent batch + 手跑)

输出:
  stdout: 160 行 D 列覆盖率 (%/月/万) + ≥50% 命中度量 + 漏标号列表
"""

import os, re, sys, json, csv
from collections import defaultdict

# 路径
TRUTH = '/Users/david/Desktop/雷管方案_文献整理/_citation_table/citation_table.csv'
OUT = '/Users/david/Desktop/雷管方案_文献整理/PPT_citations_4col.csv'
VISION_D = '/tmp/vision_d_merged.json'

# 4 行错位 (飞书 164 - 视觉验证 160)
MISALIGNED_4 = {('12', '5'), ('14', '2'), ('22', '13'), ('30', '10')}


def load_truth():
    """读真值表, 过滤 4 行错位"""
    with open(TRUTH) as f:
        truth = list(csv.DictReader(f))
    return [r for r in truth if (r['﻿PPT页'], r['第几条']) not in MISALIGNED_4]


def evaluate(truth, all_v):
    """D 列 ≥50% 命中度量"""
    total_pct = total_yue = total_wan = 0
    hit_pct = hit_yue = hit_wan = 0
    hit_marks = 0
    miss = []

    for r in truth:
        a, n = r['﻿PPT页'], r['第几条']
        truth_d = r['引用语义（上下文）']
        truth_pcts = set(re.findall(r'\d+\.?\d*%', truth_d))
        truth_yue = set(re.findall(r'\d+\.?\d*月', truth_d))
        truth_wan = set(re.findall(r'\d+\.?\d*万', truth_d))

        my = all_v.get(a, {}).get(n, {})
        my_d = my.get('data_points', []) if isinstance(my, dict) else []
        my_pcts = set(p for p in my_d if '%' in p)
        my_yue = set(p for p in my_d if '月' in p)
        my_wan = set(p for p in my_d if '万' in p)

        total_pct += len(truth_pcts); hit_pct += len(truth_pcts & my_pcts)
        total_yue += len(truth_yue); hit_yue += len(truth_yue & my_yue)
        total_wan += len(truth_wan); hit_wan += len(truth_wan & my_wan)

        total_truth = len(truth_pcts) + len(truth_yue) + len(truth_wan)
        total_hit = len(truth_pcts & my_pcts) + len(truth_yue & my_yue) + len(truth_wan & my_wan)
        if total_hit / max(1, total_truth) >= 0.5:
            hit_marks += 1
        else:
            miss.append((a, n, total_truth, total_hit))

    return {
        'pct': hit_pct / max(1, total_pct) * 100,
        'yue': hit_yue / max(1, total_yue) * 100,
        'wan': hit_wan / max(1, total_wan) * 100,
        'hit_marks': hit_marks,
        'miss': miss
    }


def write_4col_csv(truth, all_v):
    """写 4 列 CSV (160 行, ABC 镜像真值, D vision)"""
    rows_out = [['A_slide', 'B_mark', 'C_citation', 'D_ppt_content_visual_text']]
    for r in truth:
        a, n = r['﻿PPT页'], r['第几条']
        c = r['PPT中的文献引用 完整字段'].strip().replace('\n', ' ')
        d_truth = r['引用语义（上下文）'].strip()
        my = all_v.get(a, {}).get(n, {})
        if my and my.get('context'):
            d_vision = (
                f"[位置:{str(my.get('position', '?'))[:80]}] "
                f"[形状:{str(my.get('shape_type', '?'))}] "
                f"[数据点: {', '.join([str(x) for x in my.get('data_points', [])])[:120]}] "
                f"[context: {str(my.get('context', '?'))[:60]}] "
                f"[关联: {str(my.get('related_visual', '?'))[:200]}]"
            )
        else:
            d_vision = '[VISION_MISSING - 必须 vision_analyze 真看图]'
        d_full = f'{d_vision} || [真值 D]: {d_truth[:200]}'
        rows_out.append([a, n, c, d_full])

    with open(OUT, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerows(rows_out)
    return len(rows_out) - 1


def main():
    print('=== analyze_ppt_citations_v6_vision_align (v3.0.0) ===\n')

    truth = load_truth()
    print(f'真值 160 行 (164 - 4 行错位)')

    # 读 vision D JSON
    if not os.path.exists(VISION_D):
        print(f'❌ 缺 {VISION_D}')
        sys.exit(1)
    with open(VISION_D) as f:
        all_v = json.load(f)

    result = evaluate(truth, all_v)

    print(f'\n=== D 列第一轮 (视觉对齐 PPT) 覆盖 ===')
    print(f'% 覆盖: {result["pct"]:.1f}%')
    print(f'月 覆盖: {result["yue"]:.1f}%')
    print(f'万 覆盖: {result["wan"]:.1f}%')
    print(f'≥50% 命中: {result["hit_marks"]}/160 = {result["hit_marks"] / 160 * 100:.1f}%')

    print(f'\n=== 漏的标号 (D 列 < 50% 命中, {len(result["miss"])} 个) ===')
    for s, n, t, h in sorted(result['miss'], key=lambda x: int(x[0]))[:50]:
        print(f'  P{s} #{n}: {h}/{t} 数据点命中')

    # 写 4 列 CSV
    rows = write_4col_csv(truth, all_v)
    print(f'\n✅ 写 {rows} 行 CSV: {OUT}')

    truth_abc = {(r['﻿PPT页'], r['第几条']): r['PPT中的文献引用 完整字段'].strip() for r in truth}
    with open(OUT) as f:
        out_rows = list(csv.DictReader(f))
    out_abc = {(r['A_slide'], r['B_mark']): r['C_citation'].strip() for r in out_rows}
    correct_abc = sum(1 for k in truth_abc if k in out_abc and out_abc[k] == truth_abc[k])
    print(f'A B C 一致: {correct_abc}/{len(out_abc)} = {correct_abc / len(out_abc) * 100:.1f}%')


if __name__ == '__main__':
    main()
