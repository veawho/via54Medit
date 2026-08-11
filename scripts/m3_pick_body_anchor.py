#!/usr/bin/env python3
"""
m3_pick_body_anchor.py — 不信 plan.target_text, 直接从 PDF 抽 body 段 anchor.

策略:
1. 打开 PDF
2. 抽 page 1 (或 0) 第一个非禁高亮区的"实质 line"
3. 选最长 / 含关键词 (TF-IDF) 的 line 作 anchor
4. 全角英文转半角 (中文 PDF 常见)
5. 直接调 m3_vision_highlight 内部函数 (不 subprocess, 避免 timeout)
"""
import json, os, sys, re, fitz, shutil, time
from collections import defaultdict

sys.path.insert(0, '/Users/david/Desktop/developments/via54Medit/scripts')
import m3_vision_highlight as mv3

TMA = '/Users/david/Desktop/TMA_文献整理'
LEIGUAN = '/Users/david/Desktop/雷管方案_文献整理'

# 全角转半角
def fullwidth_to_halfwidth(s: str) -> str:
    result = []
    for c in s:
        code = ord(c)
        if 0xFF01 <= code <= 0xFF5E:
            result.append(chr(code - 0xFEE0))
        elif c == '\u3000':
            result.append(' ')
        else:
            result.append(c)
    return ''.join(result)

# 关键词: TMA 领域高频, 优先选含关键词的 line
DOMAIN_KEYWORDS = [
    'aHUS', 'TMA', 'TTP', 'HUS', 'C3', 'C5', 'eculizumab', 'complement',
    'ravulizumab', 'ADAMTS13', 'alternative pathway', 'thrombotic',
    'microangiopathy', 'hemolytic', 'uremic',
    '补体', '血栓性', '微血管', '溶血', '尿毒', '肾',
    '血小板', '凝血', '替代途径', '经典途径', '凝集素',
]

# 评分函数: line 长度 + 关键词数 + 是否在禁高亮区
def score_line(line_text: str, page, rect, page_idx: int) -> tuple:
    """返回 (score, is_bad, reason)"""
    # 禁高亮区检测
    is_bad, reason = mv3.is_forbidden_zone(page, rect, page_idx)
    if is_bad:
        return (-1, True, reason)
    # 长度 (太短不要)
    if len(line_text) < 25:
        return (-1, True, 'too_short')
    if len(line_text) > 350:
        return (-1, True, 'too_long')
    # 关键词加分
    kw = sum(1 for k in DOMAIN_KEYWORDS if k in line_text)
    # 长度分
    len_score = min(len(line_text) / 30, 10)  # cap 10
    return (kw * 5 + len_score, False, '')


def find_best_anchor(pdf_path: str, max_pages: int = 3) -> tuple:
    """返回 (page_idx, anchor, line_rect) 或 None"""
    doc = fitz.open(pdf_path)
    candidates = []
    for pi in range(min(doc.page_count, max_pages + 1)):
        page = doc[pi]
        d = page.get_text("dict")
        page_h = page.rect.height
        # 抽所有 line
        for block in d.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                line_text = ''.join(s.get("text", "") for s in spans).strip()
                if not line_text:
                    continue
                line_rect = fitz.Rect(line["bbox"])
                score, is_bad, reason = score_line(line_text, page, line_rect, pi)
                if not is_bad:
                    candidates.append((score, pi, line_text, line_rect))
    doc.close()
    if not candidates:
        return None
    # 选 score 最高
    candidates.sort(key=lambda x: -x[0])
    best = candidates[0]
    # 抽 anchor: line text 前 25-40 字符 (避免太长 search_for 失败)
    txt = best[2]
    if len(txt) > 50:
        # 截到第一个 ". " 或 ", " 之前
        for sep in ['. ', ', ', '; ', '。', '，', '；']:
            if sep in txt[:80]:
                anchor = txt.split(sep)[0].strip()[:50]
                break
        else:
            anchor = txt[:50].strip()
    else:
        anchor = txt
    return (best[1], anchor, best[3])


def process_pn_x(pn, pdf, out_dir, dry_run=False):
    """处理一个 Pn-x, 返回 (status, anchor_or_reason)"""
    if not os.path.isfile(pdf):
        return ('no_pdf', '')
    
    found = find_best_anchor(pdf)
    if not found:
        return ('no_body_line', '')
    
    pi, anchor, rect = found
    
    # 全角转半角 (中文 PDF 常见, PyMuPDF search_for 只认半角)
    anchor_hw = fullwidth_to_halfwidth(anchor)
    
    if dry_run:
        return ('dry_ok', f'p{pi}: {anchor_hw[:50]!r}')
    
    # 确保 output 存在 (从源 PDF 复制, 避免累积旧 annots)
    out = f'{out_dir}/{pn}_semantic_highlight.pdf'
    shutil.copy2(pdf, out)
    
    # 直接调内部函数, 不用 subprocess
    doc = fitz.open(out)
    page = doc[pi]
    
    # search halfwidth anchor
    rect_found = mv3.find_phrase_rect(page, anchor_hw, page_idx=pi)
    if not rect_found:
        # try original anchor
        rect_found = mv3.find_phrase_rect(page, anchor, page_idx=pi)
    if not rect_found:
        doc.close()
        return ('no_match', f'p{pi}: {anchor_hw[:60]!r}')
    
    # 检查禁高亮区
    is_bad, reason = mv3.is_forbidden_zone(page, rect_found, pi)
    if is_bad:
        doc.close()
        return ('forbidden', f'p{pi}: {reason}: {anchor_hw[:50]!r}')
    
    # 应用 underline
    if not mv3.apply_underline(page, rect_found):
        doc.close()
        return ('underline_fail', f'p{pi}: {anchor_hw[:50]!r}')
    
    doc.save(out + '.tmp', garbage=4, deflate=True)
    doc.close()
    shutil.move(out + '.tmp', out)
    return ('ok', f'p{pi}: {anchor_hw[:60]!r}')


def main():
    DECISION = json.load(open('/tmp/clean_hash_dup_decision.json', encoding='utf-8'))
    KEEP = set(DECISION['TMA']['keep'])
    DEL = set(DECISION['TMA']['del'])
    
    PLANS_FILE = f'{TMA}/_3_highlight_vision/_highlight_plans.json'
    plans = json.load(open(PLANS_FILE, encoding='utf-8'))
    plans = plans if isinstance(plans, list) else plans['plans']
    plan_by_pn = {p['pn_x']: p for p in plans}
    
    OUT_DIR = f'{TMA}/_3_highlight_semantic_m3'
    os.makedirs(OUT_DIR, exist_ok=True)
    
    # 跑所有 Pn-x (KEEP 19 + 非冲突)
    m3_existing = set()
    for f in os.listdir(OUT_DIR):
        if f.endswith('_semantic_highlight.pdf'):
            m3_existing.add(f.replace('_semantic_highlight.pdf', ''))
    
    to_run = set(KEEP)
    for pn in m3_existing:
        if pn not in DEL:
            to_run.add(pn)
    
    print(f'Total to run: {len(to_run)}')
    print()
    
    results = defaultdict(list)
    t0 = time.time()
    for i, pn in enumerate(sorted(to_run), 1):
        plan = plan_by_pn.get(pn, {})
        pdf = plan.get('pdf_path', '')
        status, detail = process_pn_x(pn, pdf, OUT_DIR)
        results[status].append((pn, detail))
        if i % 10 == 0:
            print(f'  [{i}/{len(to_run)}] done in {time.time()-t0:.1f}s')
    
    # 报告
    print(f'\n=== 跑完 ({time.time()-t0:.1f}s) ===')
    for k, v in results.items():
        print(f'{k}: {len(v)}')
    
    # 详细
    for k, v in results.items():
        if not v: continue
        print(f'\n=== {k} ===')
        for pn, d in v[:30]:
            print(f'  {pn:18s} {d!r}')
        if len(v) > 30:
            print(f'  ... +{len(v)-30} more')
    
    with open('/tmp/m3_pick_body_results.json', 'w', encoding='utf-8') as f:
        json.dump({k: v for k, v in results.items()}, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
