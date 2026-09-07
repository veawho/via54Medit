#!/usr/bin/env python3
"""
layout.py — OCR 版面分析 (乱码 / 纯图像 PDF 通道)

对 tesseract TSV 词级结果 (words_tsv 输出的 dict 列表, 像素坐标) 建立页面区域模型:
  - 页眉/页脚行剔除 (running head / 页码 / 文档编号)
  - 双栏阅读序 (eng 按词 x 中点间隙; 含 CJK 时按字符级 x 聚类)
  - 区域产出: zones 列表, 每 zone 为 {kind, words, x0,y0,x1,y1}
    阅读序: 正文左栏 -> 正文右栏 (kind='body'), 页边词 (kind='margin') 单列。

本模块只做版面/阅读序推断, 不做匹配与标注; 供 hl_ocr_band 整句定位使用。
"""
import re

CJK_RE = re.compile(r'[\u4e00-\u9fff]')
PAGE_NUM_RE = re.compile(r'^[\d\-–—\s]*\d[\d\-–—\s]*$')


def has_cjk(words):
    """词流中是否含中文字符 (用于 chi_sim 分栏启发式)"""
    return any(CJK_RE.search(w['t']) for w in words)


def _yc(w):
    return w['y'] + w['h'] / 2.0


def _xc(w):
    return w['x'] + w['w'] / 2.0


def group_lines(words, tol=None):
    """按 y 中心聚行, 返回 [{y0,y1,yc,x0,x1,words:[...排序后]}], 行内按 x 排序."""
    if not words:
        return []
    if tol is None:
        hs = sorted(w['h'] for w in words)
        tol = max(4.0, hs[len(hs) // 2] * 0.9)
    lines = []
    for w in sorted(words, key=lambda z: (_yc(z), z['x'])):
        yc = _yc(w)
        if lines and abs(yc - lines[-1]['yc']) <= tol:
            L = lines[-1]
        else:
            L = dict(y0=w['y'], y1=w['y'] + w['h'], yc=yc,
                     x0=w['x'], x1=w['x'] + w['w'], words=[])
            lines.append(L)
        L['y0'] = min(L['y0'], w['y'])
        L['y1'] = max(L['y1'], w['y'] + w['h'])
        L['x0'] = min(L['x0'], w['x'])
        L['x1'] = max(L['x1'], w['x'] + w['w'])
        L['words'].append(w)
    for L in lines:
        L['words'].sort(key=lambda z: z['x'])
    return lines


def is_page_number_line(L):
    """整行仅数字/短横 -> 页码行 (页眉页脚候选)"""
    toks = [w['t'] for w in L['words']]
    if not toks or len(toks) > 3:
        return False
    joined = ' '.join(toks).strip()
    if not joined:
        return False
    return bool(PAGE_NUM_RE.match(joined)) and len(joined) <= 12


def margin_classify(words, page_h_px, top_frac=0.06, bottom_frac=0.06):
    """按 y 位置剔除页眉/页脚行 (含页码行与边缘短行), 返回 (body_lines, margin_lines).

    仅当整行落在极边带且满足启发式(页码行 或 行宽不足版心一半)才剔除,
    避免误删顶部的正文标题; 版心半宽取该行所在列宽不确定时以全页词 x 分布计.
    """
    lines = group_lines(words)
    body, margin = [], []
    all_x1 = [L['x1'] for L in lines] or [1]
    span = max(all_x1) - min(L['x0'] for L in lines)
    for L in lines:
        yc = L['yc']
        frac_top = yc / page_h_px if page_h_px else 1
        frac_bot = (page_h_px - yc) / page_h_px if page_h_px else 1
        in_band = frac_top < top_frac or frac_bot < bottom_frac
        if not in_band:
            body.append(L)
            continue
        narrow = (L['x1'] - L['x0']) < span * 0.5 if span else True
        if is_page_number_line(L) or narrow:
            margin.append(L)
        else:
            body.append(L)
    return body, margin


def column_split_words(lines, min_gap_px=90, vote_frac=0.35, min_count=8):
    """把物理行按全局栏间隙切成词级列流 (真正双栏版面, 不把整行归入单侧).

    对每个物理行取「最大相邻词间隙」作为该行候选 cut; 若间隙够大且左右两段词数均 >= 2,
    记录 (cut, 该行词数). 全局对 cut 做一维聚类, 取支持词数最多的 cut 簇;
    只有得票比例(支持词数/总词数)达到 vote_frac 才视为双栏, 否则返回单栏。

    Returns [[word,...]列流按阅读序, ...]: 每列词已按 (y,x) 排序。
    """
    total_words = sum(len(L['words']) for L in lines)
    if total_words < min_count:
        return [[w for L in lines for w in L['words']]]
    votes = []
    for L in lines:
        ws = sorted(L['words'], key=lambda z: z['x'])
        if len(ws) < 4:
            continue
        best, bgap = None, 0
        for a, b in zip(ws, ws[1:]):
            g = b['x'] - (a['x'] + a['w'])
            if g > bgap:
                bgap = g
                best = (a['x'] + a['w'] + b['x']) // 2
        if best is not None and bgap > min_gap_px:
            lc = sum(1 for w in ws if _xc(w) < best)
            rc = len(ws) - lc
            if lc >= 2 and rc >= 2:
                votes.append((best, len(ws)))
    if not votes:
        return [[w for L in lines for w in L['words']]]
    # cut 一维聚类 (容差 60px), 取支持词数最多的簇中点
    vs = sorted(votes, key=lambda t: t[0])
    clusters = []
    for cut, nw in vs:
        if clusters and abs(cut - clusters[-1]['cut']) <= 60:
            clusters[-1]['nw'] += nw
            clusters[-1]['items'].append(cut)
        else:
            clusters.append(dict(cut=cut, nw=nw, items=[cut]))
    best = max(clusters, key=lambda c: c['nw'])
    cut = int(sum(best['items']) / len(best['items']))
    if best['nw'] < total_words * vote_frac:
        return [[w for L in lines for w in L['words']]]
    left, right = [], []
    for L in lines:
        ws = sorted(L['words'], key=lambda z: z['x'])
        lw = [w for w in ws if _xc(w) < cut]
        rw = [w for w in ws if _xc(w) >= cut]
        if lw:
            left.append((min(w['y'] for w in lw), lw))
        if rw:
            right.append((min(w['y'] for w in rw), rw))
    cols = []
    for side in (left, right):
        if not side:
            continue
        # 行级排序 (按行 y0), 行内保持 x 阅读序; 不做逐词 y 重排, 避免同一视觉行
        # tesseract 词 bbox y 抖动(descender 等)把行内词打散到相邻桶
        side.sort(key=lambda t: t[0])
        colw = [w for _, row in side for w in row]
        cols.append(colw)
    return cols if len(cols) == 2 else [[w for L in lines for w in L['words']]]


def page_zones(words, page_h_px, lang='eng', top_frac=0.06, bottom_frac=0.06):
    """版面主入口.

    返回 dict:
      zones: [{kind:'body'|'margin', x0,y0,x1,y1, words:[词...阅读序]}...]
             body 列按左->右、栏内按 y 排序; margin 为剔除的页眉页脚行 (单列, 便于兜底重试)。
      header_words / footer_words: 便于诊断。
    阅读序词流由调用方从 zone['words'] 直接取 (已按 (y, x) 排序)。
    """
    body_lines, margin_lines = margin_classify(words, page_h_px, top_frac, bottom_frac)
    cols = column_split_words(body_lines)
    zones = []
    for ci, col in enumerate(cols):
        zones.append(dict(kind='body', x0=min(w['x'] for w in col),
                          y0=min(w['y'] for w in col),
                          x1=max(w['x'] + w['w'] for w in col),
                          y1=max(w['y'] + w['h'] for w in col),
                          words=col))
    if margin_lines:
        mw = [w for L in margin_lines for w in L['words']]
        zones.append(dict(kind='margin', x0=min(L['x0'] for L in margin_lines),
                          y0=min(L['y0'] for L in margin_lines),
                          x1=max(L['x1'] for L in margin_lines),
                          y1=max(L['y1'] for L in margin_lines),
                          words=mw))
    return dict(zones=zones,
                header_words=[],
                footer_words=[])


def reading_columns(words, page_h_px, lang='eng', top_frac=0.06, bottom_frac=0.06):
    """便捷接口: 返回 列词流列表 (body 列优先 + margin 单列兜底, 均按阅读序)"""
    info = page_zones(words, page_h_px, lang, top_frac, bottom_frac)
    flows = [z['words'] for z in info['zones'] if z['kind'] == 'body']
    flows += [z['words'] for z in info['zones'] if z['kind'] == 'margin']
    return flows, info
