#!/usr/bin/env python3
"""m3_vision_6_mini_v2.py — 6 个 Pn-x 手工选 anchor + 跑 highlight (避免 find_best_anchor 慢)"""
import json, os, sys, shutil, time, re
from collections import defaultdict

sys.path.insert(0, '/Users/david/Desktop/developments/via54Medit/scripts')
import m3_vision_highlight as mv3
import fitz

TMA = '/Users/david/Desktop/TMA_文献整理'
OUT = f'{TMA}/step4_highlight_106目录_合并DOI'

# 6 个 Pn-x + 手工选 anchor (从 PDF page 0 text 抓)
# 选 page 0/1 第一个含 TMA/aHUS 关键词的 30-60 字符 anchor
ANCHORS = {
    # 中文 abstract 段 (page 0, 跳过 title/author/ref 禁高亮区)
    'P25-2': ('非典型溶血尿毒综合征（aHUS）是一种以微血管病性溶血性贫血', 0),
    'P30-2': ('非典型溶血尿毒综合征（aHUS）是一种以微血管病性溶血性贫血', 0),
    # 英文 abstract 段 (page 0)
    'P25-3': ('Thrombotic microangiopathy (TMA) is a rare and potentially', 0),
    'P9-2':  ('Thrombotic microangiopathy (TMA) is a rare and potentially', 0),
    # abstract 段 (P23-26 page 0, P24-1 page 1)
    'P23-26': ('Hematopoietic stem cell transplant (HSCT)-associated thrombotic', 0),
    'P24-1': ('TA-TMA is diagnosed when', 1),
}


def process_one(pn, anchor, page_idx, dry=False, mode='phrase', skip_forbidden=False):
    pdf = f'{TMA}/step3_pdf下载_106目录/{pn}_main.pdf'
    if not os.path.exists(pdf):
        return ('no_pdf', '')

    # 拷源 PDF 到 out
    out_path = f'{OUT}/{pn}_semantic_highlight.pdf'
    if not dry:
        shutil.copy2(pdf, out_path)
        doc = fitz.open(out_path)
        page = doc[page_idx]
        # 找 anchor (phrase / line mode)
        if mode == 'phrase':
            rect = mv3.find_phrase_rect(page, anchor, page_idx=page_idx)
        else:  # line
            rect = mv3.find_line_rect(page, anchor)
        if not rect:
            doc.close()
            return ('no_match', f'anchor={anchor[:50]!r}')

        # 禁高亮区检查 (可跳过: 大单页扫描件)
        if not skip_forbidden:
            is_bad, reason = mv3.is_forbidden_zone(page, rect, page_idx)
            if is_bad:
                doc.close()
                return ('forbidden', f'p{page_idx} {reason}')

        # apply underline
        if not mv3.apply_underline(page, rect):
            doc.close()
            return ('underline_fail', f'p{page_idx}')

        doc.save(out_path + '.tmp', garbage=4, deflate=True)
        doc.close()
        shutil.move(out_path + '.tmp', out_path)
        return ('ok', f'p{page_idx} rect={rect}')
    return ('dry', f'p{page_idx} mode={mode} anchor={anchor[:50]!r}')


def main():
    results = defaultdict(list)
    t0 = time.time()
    # P25-2 P30-2 是单页扫描大图 (page_h > 1000), 用 line mode + skip forbidden
    for pn, (anchor, pi) in ANCHORS.items():
        pdf = f'{TMA}/step3_pdf下载_106目录/{pn}_main.pdf'
        import fitz
        page_h = fitz.open(pdf)[0].rect.height
        mode = 'line' if page_h > 1000 else 'phrase'
        skip = page_h > 1000  # 单页扫描件无法分 title/body, 跳过禁高亮检查

        status, detail = process_one(pn, anchor, pi, dry=True, mode=mode, skip_forbidden=skip)
        print(f'  [DRY {pn}] mode={mode} skip={skip} {status}  {detail}')

        status, detail = process_one(pn, anchor, pi, dry=False, mode=mode, skip_forbidden=skip)
        results[status].append((pn, detail))
        print(f'  [RUN {pn}] mode={mode} skip={skip} {status}  {detail}')

    print(f'\n=== 跑完 ({time.time()-t0:.1f}s) ===')
    for k, v in sorted(results.items()):
        print(f'{k}: {len(v)}')
        for pn, d in v:
            print(f'  {pn}: {d}')


if __name__ == "__main__":
    main()
