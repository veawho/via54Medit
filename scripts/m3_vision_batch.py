#!/usr/bin/env python3
"""
m3_vision_batch.py — 批量用 m3_vision_highlight 跑 103 个 Pn-x (phrase 模式)

User 选 M3 vision 自动选 mode, 但 103 个太多
折中: 先用 phrase 模式批量 + plan.target_text 抽 anchor, 失败的单独处理
"""
import json, os, sys, re, fitz, shutil, subprocess

TMA = '/Users/david/Desktop/TMA_文献整理'
PLANS = f'{TMA}/_3_highlight_vision/_highlight_plans.json'
OUT_DIR = f'{TMA}/_3_highlight_semantic_m3'
os.makedirs(OUT_DIR, exist_ok=True)


def extract_anchor_from_target(target: str) -> str:
    """从 plan.target_text 提取合理的 anchor (英文关键词 / 中文短句)"""
    if not target:
        return ''
    t = target.strip()
    # 数字标号 (1a, 4b, 1) 等去掉
    t = re.sub(r'\d+[a-z]?\d*$', '', t).strip()
    # 引文编号 (e.g. [1], (2)) 去掉
    t = re.sub(r'\[\d+\]|\(\d+\)', '', t).strip()
    # DOI / URL 截断
    if 'http' in t:
        t = t.split('http')[0].strip()
    # 句号 / 逗号 截断到第一个
    for sep in ['。', '. ', '，', ', ', '; ', '；']:
        if sep in t:
            t = t.split(sep)[0].strip()
            break
    # 太长截到 60 字符
    if len(t) > 60:
        t = t[:60].strip()
    return t


def find_anchor_in_pdf(anchor: str, doc) -> tuple:
    """用 search_for 在 PDF 找 anchor, 返回 (page_idx, hit_rect, hit_text)
    跳过 page 0 (title/author), 优先 page 1-2
    """
    if not anchor or len(anchor) < 4:
        return None
    # 1. 短 anchor 直接 search
    for pi in [0, 1, 2, 3]:
        if pi >= doc.page_count: break
        page = doc[pi]
        # 短中文: 至少 4 字符
        # 短英文: 至少 5 字符
        min_len = 4 if re.search(r'[\u4e00-\u9fa5]', anchor) else 5
        if len(anchor) < min_len:
            # anchor 短, 取更长 substring
            continue
        hits = page.search_for(anchor, quads=False)
        if hits:
            return (pi, hits[0], anchor)
    # 2. 截短到 20 字符试
    if len(anchor) > 20:
        short = anchor[:20].strip()
        for pi in [1, 2, 0]:
            if pi >= doc.page_count: break
            page = doc[pi]
            hits = page.search_for(short, quads=False)
            if hits:
                return (pi, hits[0], short)
    # 3. 截短到 10 字符
    if len(anchor) > 10:
        short = anchor[:10].strip()
        for pi in [1, 2, 0]:
            if pi >= doc.page_count: break
            page = doc[pi]
            hits = page.search_for(short, quads=False)
            if hits:
                return (pi, hits[0], short)
    return None


def main():
    plans = json.load(open(PLANS))
    plans = plans if isinstance(plans, list) else plans['plans']
    plan_by_pn = {p['pn_x']: p for p in plans}

    # 找已 highlight 的 103 个 Pn-x
    dirs = [f'{TMA}/_3_highlight_semantic_v141',
            f'{TMA}/_3_highlight_semantic_v142',
            f'{TMA}/_3_highlight_semantic_v2',
            f'{TMA}/_3_highlight_semantic_v3',
            f'{TMA}/_3_highlight_semantic_m3']
    ok = set()
    for d in dirs:
        if not os.path.isdir(d): continue
        for f in os.listdir(d):
            if f.endswith('.pdf'):
                pn = f.replace('_semantic_highlight.pdf', '')
                p = os.path.join(d, f)
                try:
                    doc = fitz.open(p)
                    n = sum(len(list(pg.annots() or [])) for pg in doc)
                    doc.close()
                    if n > 0: ok.add(pn)
                except: pass

    print(f'要重做的 Pn-x: {len(ok)}')
    print()

    results = []
    for pn in sorted(ok):
        plan = plan_by_pn.get(pn, {})
        pdf = plan.get('pdf_path', '')
        if not pdf or not os.path.isfile(pdf):
            results.append((pn, 'no_pdf', 0, 0))
            continue
        target = plan.get('target_text', '') or ''
        anchor = extract_anchor_from_target(target)
        if not anchor:
            results.append((pn, 'no_anchor', 0, 0))
            continue

        doc = fitz.open(pdf)
        found = find_anchor_in_pdf(anchor, doc)
        if not found:
            doc.close()
            results.append((pn, 'no_match', 0, 0))
            continue
        pi, rect, hit_text = found
        doc.close()

        # 用 m3_vision_highlight.py 应用
        out = f'{OUT_DIR}/{pn}_semantic_highlight.pdf'
        if not os.path.exists(out):
            shutil.copy2(pdf, out)
        cmd = ['/Users/david/.hermes/hermes-agent/venv/bin/python',
               '/Users/david/Desktop/developments/via54Medit/scripts/m3_vision_highlight.py',
               '--pn-x', pn,
               '--entries', f'[[{pi}, {json.dumps(hit_text)}, "phrase"]]',
               '--out-dir', OUT_DIR]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd='/Users/david/Desktop/developments/via54Medit')
        # 解析输出
        ok_count = 0
        for line in r.stdout.split('\n'):
            if '/1 OK' in line or '/2 OK' in line or '/3 OK' in line:
                ok_count = int(line.split(':')[1].split('/')[0].strip())
        if r.returncode == 0 and ok_count > 0:
            results.append((pn, 'ok', ok_count, rect.width))
        else:
            results.append((pn, 'script_fail', 0, 0))

    # 统计
    n_ok = sum(1 for r in results if r[1] == 'ok')
    n_no_match = sum(1 for r in results if r[1] == 'no_match')
    n_no_pdf = sum(1 for r in results if r[1] == 'no_pdf')
    n_fail = sum(1 for r in results if r[1] in ('script_fail', 'no_anchor'))
    print(f'\n=== 批量结果 ===')
    print(f'ok: {n_ok}')
    print(f'no_match: {n_no_match}')
    print(f'no_pdf: {n_no_pdf}')
    print(f'fail: {n_fail}')
    print()
    print('no_match 详情 (需要 M3 vision 单独处理):')
    for pn, status, n, w in results:
        if status == 'no_match':
            t = plan_by_pn.get(pn, {}).get('target_text', '')[:50]
            print(f'  {pn:6s}: {t!r}')


if __name__ == '__main__':
    main()
