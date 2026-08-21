#!/usr/bin/env python3
"""
v6_vision_align_eval.py — D 列 ≥50% 命中度量 (v2.5.0)

评估算法 D 列视觉对齐 PPT 覆盖:
- 读真值 160 行 (164 - 4 错位)
- 读 vision D JSON
- 提真值 D 数据点 + 算法 D 数据点
- 度量每个标号 ≥50% 命中

用法:
  python v6_vision_align_eval.py
"""
import os, re, sys, json, csv

TRUTH = '/Users/david/Desktop/雷管方案_文献整理/_citation_table/citation_table.csv'
VISION_D = '/tmp/vision_d_merged.json'
MISALIGNED_4 = {('12', '5'), ('14', '2'), ('22', '13'), ('30', '10')}


def load_truth():
    with open(TRUTH) as f:
        truth = list(csv.DictReader(f))
    return [r for r in truth if (r['﻿PPT页'], r['第几条']) not in MISALIGNED_4]


def main():
    truth = load_truth()
    print(f'真值 {len(truth)} 行 (164 - 4 错位)')

    with open(VISION_D) as f:
        all_v = json.load(f)

    all_pct = all_yue = all_wan = 0
    all_hit_pct = all_hit_yue = all_hit_wan = 0
    all_hit_marks = 0
    miss_list = []

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

        all_pct += len(truth_pcts); all_hit_pct += len(truth_pcts & my_pcts)
        all_yue += len(truth_yue); all_hit_yue += len(truth_yue & my_yue)
        all_wan += len(truth_wan); all_hit_wan += len(truth_wan & my_wan)

        total_truth = len(truth_pcts) + len(truth_yue) + len(truth_wan)
        if total_truth > 0:
            total_hit = len(truth_pcts & my_pcts) + len(truth_yue & my_yue) + len(truth_wan & my_wan)
            if total_hit / total_truth >= 0.5:
                all_hit_marks += 1
            else:
                miss_list.append((a, n, total_truth, total_hit))
        else:
            all_hit_marks += 1

    print()
    print(f'=== D 列第一轮 (视觉对齐 PPT) 覆盖 ===')
    print(f'% 覆盖: {all_hit_pct}/{all_pct} = {all_hit_pct/max(1,all_pct)*100:.1f}%')
    print(f'月 覆盖: {all_hit_yue}/{all_yue} = {all_hit_yue/max(1,all_yue)*100:.1f}%')
    print(f'万 覆盖: {all_hit_wan}/{all_wan} = {all_hit_wan/max(1,all_wan)*100:.1f}%')
    print(f'≥50% 命中: {all_hit_marks}/{len(truth)} = {all_hit_marks/len(truth)*100:.1f}%')

    print(f'\n=== 漏的标号 (D 列 < 50% 命中, {len(miss_list)} 个) ===')
    for s, n, t, h in sorted(miss_list, key=lambda x: int(x[0]))[:30]:
        print(f'  P{s} #{n}: {h}/{t} 数据点命中')

    return all_hit_marks / len(truth) * 100


if __name__ == '__main__':
    main()