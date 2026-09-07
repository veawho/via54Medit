# -*- coding: utf-8 -*-
"""真实整句定位成功率严格评估 (29 句 OCR 通道).

对每个 OCR 文件在候选页上, 用与 sentence_band_highlight 相同的词流
(layout.reading_columns flows), 复刻 locate_in_ocr 四级回退并记录命中级:
  L1 精确 / L2 连字符自愈 / L3 标点脱敏 -> strong
  L4 首尾双锚点 (窗口可能含 OCR 噪声/跨词) -> weak
统计: strong / weak / miss 与逐句明细, 供与 21/29 声明口径对比.
"""
import csv, json, os, re, sys
sys.path.insert(0, r'G:\agent\ai\projects\via54Medit\scripts\hl_v3_final')
import layout, hl_ocr_band as ob, hl_lib

WORK = r'c:\Users\via54\.trae-cn\work\6a9e448884fcf10fc666920a\rsv_hl'
TMPD = os.path.join(os.path.dirname(WORK), '_regress_tmp')
SN = os.path.join(WORK, '_sentences')
FLAT = os.path.join(WORK, '_flat_official')
# 候选页 = 回归 CAND (句子分布的真实页)
CAND = {
    'P3-2': ([2], 'chi_sim+eng'), 'P3-3': ([2], 'chi_sim+eng'), 'P6-1': ([3, 7], 'chi_sim+eng'),
    'P8-4': ([7], 'chi_sim+eng'), 'P8-10': ([1, 2], 'eng'), 'P9-10': ([2], 'eng'),
    'P15-3': ([2, 8], 'eng'), 'P15-4': ([1], 'eng'), 'P21-3': ([6], 'eng'),
    'P23-3': ([8], 'eng'), 'P27-2': ([1, 2], 'eng'), 'P27-3': ([1], 'eng'),
}
_P = re.compile(r'[^\w\u4e00-\u9fff]')


def norm_cn(s):
    s = re.sub(r'\s+', '', s)
    s = _P.sub('', s)
    return s.lower()


def read_ws(tsv):
    rows = list(csv.reader(open(tsv, encoding='utf-8'), delimiter='\t'))
    ci = {c: i for i, c in enumerate(rows[0])}
    ws = []
    for r in rows[1:]:
        if len(r) > 11 and r[ci['level']] == '5' and r[ci['text']].strip():
            try:
                if float(r[ci['conf']]) > 20:
                    ws.append(dict(x=int(r[ci['left']]), y=int(r[ci['top']]),
                                   w=int(r[ci['width']]), h=int(r[ci['height']]),
                                   ln=r[ci['line_num']], t=r[ci['text']]))
            except Exception:
                pass
    return ws


def locate_leveled(flow, sentence):
    """复刻 locate_in_ocr 并返回 (level, (si,ei)) 或 None.
    level: 1 exact / 2 hyphen / 3 punct / 4 anchor."""
    ns, wmap = ob.flow_norm(flow)
    sk = ob.sent_norm(sentence)
    n = len(sk)
    if n == 0 or n > len(ns):
        return None
    i = ns.find(sk)
    if i >= 0:
        return (1, (wmap[i], wmap[i + n - 1]))
    if '-' in sk or '-' in ns:
        keep = [j for j, ch in enumerate(ns) if ch != '-']
        ns2 = ''.join(ns[j] for j in keep)
        sk2 = sk.replace('-', '')
        if sk2 and len(sk2) <= len(ns2):
            j = ns2.find(sk2)
            if j >= 0:
                i0, i1 = keep[j], keep[j + len(sk2) - 1]
                return (2, (wmap[i0], wmap[i1]))
    sk_pure = _P.sub('', sk)
    keep = [j for j, ch in enumerate(ns) if not _P.match(ch)]
    ns_pure = ''.join(ns[j] for j in keep)
    if len(sk_pure) >= 6 and len(ns_pure) >= len(sk_pure):
        j = ns_pure.find(sk_pure)
        if j >= 0:
            i0, i1 = keep[j], keep[j + len(sk_pure) - 1]
            return (3, (wmap[i0], wmap[i1]))
    if len(sk_pure) >= 20 and len(ns_pure) >= len(sk_pure):
        head, tail = sk_pure[:12], sk_pure[-12:]
        h = ns_pure.find(head)
        if h >= 0:
            t = ns_pure.find(tail, h + len(head))
            if t >= 0 and (t + len(tail) - h) <= int(len(sk_pure) * 2.2) + 20:
                i0, i1 = keep[h], keep[t + len(tail) - 1]
                return (4, (wmap[i0], wmap[i1]))
    return None


def window_quality(flow, si, ei, sentence):
    """窗口词序列纯度: 窗口内与句共享的连续命中比例.
    返回 (overlap_ratio, window_words_joined)."""
    sel = flow[si:ei + 1]
    wj = ' '.join(w['t'] for w in sel)
    wn = norm_cn(wj)
    sn = norm_cn(sentence)
    # 用最长公共子串近似连续覆盖率
    best = 0
    for st in range(max(1, len(sn) - 80), 0, -1):
        pass
    return None, wj[:150]


def lcs_frac(sn, wn):
    """wn 中能匹配 sn 的最长连续段长度 / len(sn)"""
    if not sn:
        return 0.0
    # 简化: 逐子串 (sn 的连续片段) 是否在 wn 中
    lo, hi = 0, min(len(sn), len(wn))
    best = 0
    # 二分找最长连续片段
    while lo <= hi:
        mid = (lo + hi) // 2
        ok = False
        if mid == 0:
            ok = True
        else:
            for k in range(0, len(sn) - mid + 1):
                if sn[k:k + mid] in wn:
                    ok = True
                    break
        if ok:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best / max(1, len(sn))


def run():
    rows = []
    for pnx in sorted(CAND):
        pages, lang = CAND[pnx]
        sents = json.load(open(os.path.join(SN, f'{pnx}.json'), encoding='utf-8'))['sentences']
        # 页词流缓存
        page_flows = {}
        for pno in pages:
            tsv = os.path.join(TMPD, f'{pnx}_p{pno}.tsv')
            if not os.path.exists(tsv):
                continue
            ws = read_ws(tsv)
            if not ws:
                continue
            import fitz
            d = fitz.open(os.path.join(FLAT, f'{pnx}.pdf'))
            hpx = d[pno - 1].rect.height * (300 / 72.0)
            d.close()
            flows, _ = layout.reading_columns(ws, hpx, lang)
            if not flows:
                flows = [sorted(ws, key=lambda w: (w['y'] // 8, w['x']))]
            page_flows[pno] = flows
        if not page_flows:
            continue
        for i, s in enumerate(sents):
            best = None
            for pno, flows in page_flows.items():
                for flow in flows:
                    r = locate_leveled(flow, s)
                    if r:
                        lv, (si, ei) = r
                        if best is None or lv < best[0]:
                            best = (lv, pno, flow, si, ei)
            if best is None:
                rows.append(dict(pnx=pnx, idx=i, level=0, page=None, text=s))
                continue
            lv, pno, flow, si, ei = best
            sel = flow[si:ei + 1]
            wj = ' '.join(w['t'] for w in sel)
            frac = lcs_frac(norm_cn(s), norm_cn(wj))
            rows.append(dict(pnx=pnx, idx=i, level=lv, page=pno,
                             frac=round(frac, 2), window=wj[:160], text=s))
    return rows


rows = run()
# 汇总
from collections import Counter
lv_c = Counter(r['level'] for r in rows)
strong = sum(1 for r in rows if r['level'] in (1, 2, 3))
weak = sum(1 for r in rows if r['level'] == 4)
miss = sum(1 for r in rows if r['level'] == 0)
lowq = [r for r in rows if r['level'] in (1, 2, 3, 4) and r.get('frac', 0) < 0.5]
print(f'=== 真实整句定位分级 (n={len(rows)}) ===')
print(f'L1精确/L2连字符/L3标点脱敏 (strong): {strong}')
print(f'L4首尾锚点 (weak): {weak}')
print(f'MISS: {miss}')
print(f'命中但窗口覆盖率<0.5 (noisy): {len(lowq)}')
print('\n--- 逐句 ---')
for r in rows:
    nm = {1: 'L1', 2: 'L2', 3: 'L3', 4: 'L4-weak', 0: 'MISS'}[r['level']]
    extra = f" frac={r['frac']} p{r['page']} win={r['window'][:90]}" if r['level'] else ''
    print(f"  {r['pnx']}#{r['idx']} [{nm}]{extra}")
out = r'c:\Users\via54\.trae-cn\work\6a9e448884fcf10fc666920a\strict_eval_rows.json'
json.dump(rows, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('wrote', out)
