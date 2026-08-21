#!/usr/bin/env python3
"""精确逐行 highlight 工具:基于 rawdict 字符 bbox,按句子起止定位,每行一个精确 rect"""
import fitz, re

def norm(s):
    return re.sub(r'[\s\u3000]+', '', s)

_FW2HW = str.maketrans({
    '，': ',', '。': '.', '：': ':', '；': ';', '（': '(', '）': ')',
    '～': '~', '％': '%', '·': '·', '‘': "'", '’': "'", '“': '"', '”': '"',
    '、': ',', '＞': '>', '＜': '<', '＝': '=', '／': '/', '＋': '+', '－': '-',
    # 中文PDF字体编码变体标点 (常见于医学期刊扫描PDF)
    'ꎬ': ',', 'ꎮ': '.', 'ꎻ': ';', 'ꎺ': ':', 'ꎨ': '(', 'ꎩ': ')',
    'ꎰ': ',', 'ꎯ': '.', 'ꎭ': ':', 'ꎥ': '(', 'ꎦ': ')', 'ꎧ': ')',
})

def canon(c):
    """字符规范化: 全角标点/字母/数字->半角, 空白/软连字符去除, 连字展开; 返回规范键"""
    if c in ' \u3000\n\r\t\xa0\xad\u200b\u2009\u200a':
        return ''
    # 全角字母数字 -> 半角 (U+FF10-FF5A)
    if '\uff10' <= c <= '\uff5a':
        return chr(ord(c) - 0xfee0)
    # 连字展开
    lig = {'\ufb00': 'ff', '\ufb01': 'fi', '\ufb02': 'fl', '\ufb03': 'ffi', '\ufb04': 'ffl',
           '\ufb05': 'st', '\ufb06': 'st'}
    if c in lig:
        return lig[c]
    # PDF 编码控制字符: \x01 常见为 ≥ (部分期刊字体 ToUnicode 映射)
    if c == '\x01':
        return '≥'
    return c.translate(_FW2HW)

def canon_keys(text):
    """返回 (norm_str, raw_idx): norm_str=逐字符规范化(去空白/全角半角/连字展开/€变音归一),
    raw_idx[i]=norm_str[i] 在 text 中的原始索引(连字展开后多字符共享同一索引)"""
    # 德语PDF变音符号: €u→ü, €o→ö, €a→ä (rawdict 中的组合形式)
    for a, b in [('€u', 'ü'), ('€o', 'ö'), ('€a', 'ä'), ('€U', 'Ü'), ('€O', 'Ö'), ('€A', 'Ä')]:
        text = text.replace(a, b)
    parts = []
    ridx = []
    for i, c in enumerate(text):
        k = canon(c)
        if k:
            parts.append(k)
            ridx.extend([i] * len(k))
    return ''.join(parts), ridx

def page_char_stream(page):
    """返回 (chars, text): chars=[(c, rect), ...] 按阅读顺序, text=''.join(c)"""
    d = page.get_text('rawdict')
    chars = []
    for block in d['blocks']:
        if block['type'] != 0:
            continue
        for line in block['lines']:
            for span in line['spans']:
                for ch in span['chars']:
                    chars.append((ch['c'], fitz.Rect(ch['bbox'])))
    return chars, ''.join(c for c, _ in chars)

def locate_sentence_all(text, sentence):
    """规范化匹配,返回**所有**匹配的 (start, end) 原始索引列表(页面重复文本时用于消歧)"""
    ns, ridx = canon_keys(text)
    sk, _ = canon_keys(sentence)
    n = len(sk)
    if n == 0 or n > len(ns):
        return []
    out = []
    i = ns.find(sk)
    while i >= 0:
        out.append((ridx[i], ridx[i + n - 1] + 1))
        i = ns.find(sk, i + 1)
    return out

def locate_sentence(text, sentence, occurrence=0):
    """规范化匹配(去空白+全角半角统一+连字展开+€变音归一),返回句子在 text 中的原始 (start, end) char 索引;
    找不到返回 None. occurrence: 页面出现多次时取第 occurrence 次(0-based), 默认第一个"""
    ns, ridx = canon_keys(text)
    sk, _ = canon_keys(sentence)
    n = len(sk)
    if n == 0 or n > len(ns):
        return None
    i = ns.find(sk)
    k = 0
    while i >= 0:
        if k == occurrence:
            return ridx[i], ridx[i + n - 1] + 1
        k += 1
        i = ns.find(sk, i + 1)
    return None

def sentence_rects(chars, start, end, pad=0.35):
    """将 chars[start:end] 按行(y 中心相近)分组,返回每行合并后的 rect.
    高度 = 行距(下一行起点-本行起点),避免行间 bbox 重叠时黄色延伸盖住相邻行.
    过滤离群行: 孤立短行(<=2 字符)且与主体行 y 差>15pt (PDF 文本层错位字符, 如句号跳位)"""
    if start is None or end is None or end <= start:
        return []
    sel = chars[start:end]
    # 按 y0 排序后分行: 同行判定阈值 4.0pt (处理同视觉行 bbox 微差)
    sel.sort(key=lambda t: (t[1].y0, t[1].x0))
    lines = []
    cur = [sel[0]]
    for c, r in sel[1:]:
        if abs(r.y0 - cur[-1][1].y0) < 4.0:
            cur.append((c, r))
        else:
            lines.append(cur)
            cur = [(c, r)]
    lines.append(cur)
    # 过滤离群行: 孤立短行(<=2字符)且与主体行 y 差 > 15pt 视为文本层错位字符
    if len(lines) > 1:
        ys = [min(r.y0 for _, r in ln) for ln in lines]
        med = sorted(ys)[len(ys) // 2]
        lines = [ln for ln in lines
                 if len(ln) > 2 or abs(min(r.y0 for _, r in ln) - med) <= 15]
    rects = []
    for li, ln in enumerate(lines):
        x0 = min(r.x0 for _, r in ln) - pad
        y0 = min(r.y0 for _, r in ln) - pad
        x1 = max(r.x1 for _, r in ln) + pad
        # 行高: 本行 y0 与下一行(所有字符中大于本行的最小 y0)的差, 至少 8pt, 最多 20pt
        cur_y0 = min(r.y0 for _, r in ln)
        next_y0 = min((r.y0 for c, r in chars if r.y0 > cur_y0 + 6), default=None)
        if next_y0 and next_y0 - cur_y0 < 20:
            h = max(8.0, next_y0 - cur_y0 - 1.0)
        else:
            h = max(8.0, max(r.y1 for _, r in ln) - cur_y0)
        rects.append(fitz.Rect(x0, y0, x1, y0 + h))
    return rects

def highlight_sentences(pdf_path, out_path, sentences, verbose=True, offset=(0.0, 0.0)):
    """sentences: {page_idx(0-based): [sentence, ...]}, sentence 可为 str 或 (str, occurrence) 元组.
    清除已有 annot 后重加. offset: 已弃用, 恒为 (0,0) (fitz 渲染零补偿)"""
    import string
    doc = fitz.open(pdf_path)
    # 清除已有 annot
    for pi in range(len(doc)):
        for a in list(doc[pi].annots() or []):
            try:
                doc[pi].delete_annot(a)
            except Exception:
                pass
    report = []
    for pi, sents in sentences.items():
        if pi < 0 or pi >= len(doc):
            report.append((pi + 1, '(page out of range)', 'BAD PAGE'))
            continue
        page = doc[pi]
        chars, text = page_char_stream(page)
        for item in sents:
            # 支持 (sentence_text, occurrence) 元组消歧; 否则 occurrence=0
            if isinstance(item, tuple):
                s, occurrence = item[0], item[1]
            else:
                s, occurrence = item, 0
            loc = locate_sentence(text, s, occurrence)
            if loc is None:
                report.append((pi + 1, s[:25] + '...', 'NOT FOUND'))
                continue
            rects = sentence_rects(chars, *loc)
            if not rects:
                report.append((pi + 1, s[:25] + '...', 'NO RECTS'))
                continue
            # 末行收窄: 句子结尾非句末标点(后面紧跟引用编号等)时, 末行 x1 精确对齐:
            # 覆盖到句尾字符 x1+0.5, 且不超过同行下一非空格字符 x0-0.5 (避免盖到引用编号)
            # 预加 0.6pt 抵消下方统一 x1 收窄, 使渲染后正好到目标 x1
            last_ch = norm(s)[-1] if norm(s) else ''
            if last_ch not in '。！？!?.' and last_ch != '.':
                r = rects[-1]
                endr = None
                for j in range(loc[1] - 1, loc[0] - 1, -1):
                    if chars[j][0].strip():
                        endr = chars[j][1]
                        break
                if endr is not None:
                    # 只找同行(y0 接近)且位于句尾右侧的下一非空格字符, 避免取到下一行首字符
                    nx0 = None
                    for j in range(loc[1], len(chars)):
                        c, rr = chars[j]
                        if c in ' \t\u00a0':
                            continue
                        if rr.y0 > endr.y0 + 4 or rr.y1 < endr.y0 - 4:
                            break
                        if rr.x0 > endr.x1:
                            nx0 = rr.x0
                            break
                    cap = nx0 - 0.5 if nx0 is not None else endr.x1 + 1.0
                    target = min(endr.x1 + 0.5, cap)
                    rects[-1] = fitz.Rect(r.x0, r.y0, target + 0.6, r.y1)
            for ri, r in enumerate(rects):
                # 首行收窄左侧: 若句子从物理行中间开始且紧贴前句字符, 将 x0 对齐到首字符左缘-0.5
                r2 = fitz.Rect(r)
                if ri == 0:
                    yc = (r.y0 + r.y1) / 2
                    # 同行且位于句子首字符左侧、距离 < 50pt (同栏紧邻, 排除双栏另一栏的字符)
                    lefts = [c[1] for c in chars
                             if abs((c[1].y0 + c[1].y1) / 2 - yc) < 4
                             and c[1].x1 < r.x0 - 1
                             and r.x0 - c[1].x1 < 50]
                    if lefts:
                        nearest_x1 = max(c.x1 for c in lefts)
                        if nearest_x1 > r.x0 - 3:  # 紧贴(间距<3pt)才收窄
                            # 对齐到句子首字符左缘, 不吞掉首字符
                            fr = None
                            for j in range(loc[0], loc[1]):
                                if chars[j][0].strip():
                                    fr = chars[j][1]
                                    break
                            if fr is not None:
                                r2 = fitz.Rect(fr.x0 - 0.5, r.y0, r.x1, r.y1)
                            else:
                                r2 = fitz.Rect(r.x0 + 0.6, r.y0, r.x1, r.y1)
                # x 方向收窄(避免盖相邻字符/引用); y 方向保持行距高度(rect annot 无自动扩展)
                r3 = fitz.Rect(r2.x0 + 0.6 - offset[0], r2.y0 - offset[1],
                               r2.x1 - 0.6 - offset[0], r2.y1 - offset[1])
                hl = page.add_rect_annot(r3)
                hl.set_colors(stroke=(1.0, 0.85, 0.0), fill=(1.0, 0.85, 0.0))
                hl.set_border(width=0)
                hl.set_opacity(0.45)
                hl.update()
            report.append((pi + 1, s[:25] + '...', f'OK {len(rects)} lines'))
    doc.save(str(out_path), garbage=4, deflate=True)
    doc.close()
    if verbose:
        for r in report:
            print(f'p{r[0]}: {r[1]} -> {r[2]}')
    return report
