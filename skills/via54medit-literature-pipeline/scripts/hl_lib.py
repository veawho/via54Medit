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
    """规范化匹配(去空白+全角半角统一+连字展开+€变音归一+连字符自愈+标点脱敏+双锚点自愈),
    返回句子在 text 中的原始 (start, end) char 索引; 找不到返回 None.
    occurrence: 页面出现多次时取第 occurrence 次(0-based), 默认第一个"""
    ns, ridx = canon_keys(text)
    sk, _ = canon_keys(sentence)
    n = len(sk)
    if n == 0 or n > len(ns):
        return None
        
    # 1. 精确规范化查找
    i = ns.find(sk)
    k = 0
    while i >= 0:
        if k == occurrence:
            return ridx[i], ridx[i + n - 1] + 1
        k += 1
        i = ns.find(sk, i + 1)
        
    # 2. 连字符回退匹配: 应对 PDF 跨行断字 (如 'trans-missibility' vs 'transmissibility')
    if '-' in sk or '-' in text:
        sk_nohyphen = sk.replace('-', '')
        ns_nohyphen = ns.replace('-', '')
        if len(sk_nohyphen) > 0 and sk_nohyphen in ns_nohyphen:
            raw_map = []
            for char_idx, ch in enumerate(ns):
                if ch != '-':
                    raw_map.append(ridx[char_idx])
            sub_idx = ns_nohyphen.find(sk_nohyphen)
            if sub_idx >= 0 and sub_idx + len(sk_nohyphen) - 1 < len(raw_map):
                return raw_map[sub_idx], raw_map[sub_idx + len(sk_nohyphen) - 1] + 1

    # 3. 标点脱敏回退匹配 (Punctuation-Agnostic Matching):
    # 处理 OCR/扫描件中逗号/句号/顿号/括号全半角差异或漏标点
    _PUNCT_REGEX = r'[^\w\u4e00-\u9fff]'
    sk_pure = re.sub(_PUNCT_REGEX, '', sk)
    if len(sk_pure) >= 6:
        ns_pure_chars = []
        pure_to_ridx = []
        for char_idx, ch in enumerate(ns):
            if not re.match(_PUNCT_REGEX, ch):
                ns_pure_chars.append(ch)
                pure_to_ridx.append(ridx[char_idx])
        ns_pure = ''.join(ns_pure_chars)
        
        pure_idx = ns_pure.find(sk_pure)
        if pure_idx >= 0 and pure_idx + len(sk_pure) - 1 < len(pure_to_ridx):
            return pure_to_ridx[pure_idx], pure_to_ridx[pure_idx + len(sk_pure) - 1] + 1

    # 4. 首尾双锚点自愈匹配 (Head-Tail Anchor Matching):
    # 处理超长句子尾部被省略号截断、中间插入置信区间 (95% CI) 或少量 OCR 错字的情况
    if len(sk) >= 16:
        ns_pure_chars = []
        pure_to_ridx = []
        for char_idx, ch in enumerate(ns):
            if not re.match(_PUNCT_REGEX, ch):
                ns_pure_chars.append(ch)
                pure_to_ridx.append(ridx[char_idx])
        ns_pure = ''.join(ns_pure_chars)
        
        sk_pure = re.sub(_PUNCT_REGEX, '', sk)
        if len(sk_pure) >= 12 and len(ns_pure) >= len(sk_pure):
            head_anchor = sk_pure[:8]
            tail_anchor = sk_pure[-8:]
            h_idx = ns_pure.find(head_anchor)
            if h_idx >= 0:
                t_idx = ns_pure.find(tail_anchor, h_idx + len(head_anchor))
                # 距离限制: 首尾距离合理扩展 (应对中段插入置信区间或统计注释)
                if t_idx > 0 and (t_idx + len(tail_anchor) - h_idx) <= int(len(sk_pure) * 2.2):
                    return pure_to_ridx[h_idx], pure_to_ridx[t_idx + len(tail_anchor) - 1] + 1
                    
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

def add_context_box(page, rect, color=(0.9, 0.1, 0.1), width=1.5, label=None, label_color=(0.9, 0.1, 0.1)):
    """为图表、表格或关键证据段落添加 Square 矩形边框与可选的 FreeText 字母角标 (如人工标杆)"""
    r = fitz.Rect(rect)
    annot = page.add_rect_annot(r)
    annot.set_colors(stroke=color)
    annot.set_border(width=width)
    annot.update()
    if label:
        # 在边框右上角外侧生成角标框
        badge_rect = fitz.Rect(r.x1 + 2.0, r.y0 - 4.0, r.x1 + 22.0, r.y0 + 14.0)
        txt_annot = page.add_freetext_annot(badge_rect, str(label), fontsize=11, fontname="helv", text_color=label_color)
        txt_annot.update()
    return annot

def add_freetext_badge(page, rect, label, fontsize=11, fontname="helv", text_color=(0.9, 0.1, 0.1), placement="right"):
    """在指定位置添加 FreeText 证据映射角标 (A, B, C...) 与 PPT 论点对应"""
    r = fitz.Rect(rect)
    if placement == "right":
        badge_rect = fitz.Rect(r.x1 + 2.0, r.y0 - 2.0, r.x1 + 20.0, r.y0 + 14.0)
    elif placement == "left":
        badge_rect = fitz.Rect(max(0, r.x0 - 20.0), r.y0 - 2.0, r.x0 - 2.0, r.y0 + 14.0)
    else:  # top_right
        badge_rect = fitz.Rect(r.x1 - 15.0, r.y0 - 15.0, r.x1 + 10.0, r.y0 + 5.0)
    txt_annot = page.add_freetext_annot(badge_rect, str(label), fontsize=fontsize, fontname=fontname, text_color=text_color)
    txt_annot.update()
    return txt_annot

# 常见医学术语中英映射库 (用于 Slide 中文论点与英文文献证据句的跨语言相关性匹配)
_MED_SYNONYMS = {
    '剂量': ['dose', 'dosage', 'mg', 'administration'],
    '规格': ['specification', 'formulation', 'mg'],
    '注射': ['injection', 'intramuscular', 'im', 'subcutaneous'],
    '给药': ['administered', 'administration', 'dosing'],
    '机制': ['mechanism', 'moa', 'action', 'binding'],
    '靶点': ['target', 'epitope', 'site', 'protein'],
    '单抗': ['antibody', 'mab', 'monoclonal'],
    '疗效': ['efficacy', 'effective', 'reduction', 'prevention'],
    '保护率': ['efficacy', 'reduction', 'protection', '%'],
    '疫苗': ['vaccine', 'vaccines', 'vaccination', 'immunization'],
    '联合': ['co-administration', 'coadministration', 'concomitant', 'combination'],
    '安全性': ['safety', 'tolerability', 'adverse', 'ae', 'trae'],
    '不良反应': ['adverse', 'reaction', 'event', 'side effect'],
    '婴儿': ['infant', 'infants', 'baby', 'pediatric'],
    '重症': ['severe', 'hospitalization', 'icu', 'lri', 'malri'],
    '感染': ['infection', 'infected', 'rsv'],
    '临床试验': ['trial', 'phase', 'study', 'randomized', 'rct', 'cleopatra'],
    '终点': ['endpoint', 'primary', 'secondary']
}

def filter_sentences_by_slide_context(candidates, slide_context, top_k=3, min_score=0.01):
    """基于 Slide 论点 Context 对候选证据句进行相关性过滤与打分排序，消除全量复制污染.
    candidates: [str, ...] 或 [{'text': ..., 'page': ...}, ...]
    返回最贴近当前 Slide 论点的 Top-K 候选项。"""
    if not candidates or not slide_context:
        return candidates[:top_k]
    
    ctx_lower = slide_context.lower()
    # 提取英文/数字 tokens (同时将 105mg 拆为 105, mg)
    raw_tokens = re.findall(r'[a-zA-Z]+|\d+(?:\.\d+)?%?', ctx_lower)
    tokens = set(raw_tokens)
    
    # 扩展中英同义词映射
    for cn_term, en_syns in _MED_SYNONYMS.items():
        if cn_term in slide_context:
            tokens.update(en_syns)
            
    # 提取中文 2-gram 关键词 (当文献本身也是中文时)
    cn_tokens = set(re.findall(r'[\u4e00-\u9fff]{2,}', slide_context))
    tokens.update(cn_tokens)
    
    if not tokens:
        return candidates[:top_k]
        
    scored = []
    for item in candidates:
        text = item if isinstance(item, str) else item.get('text', '')
        text_lower = text.lower()
        
        # 计算关键词覆盖度与加权分
        hits = 0
        for t in tokens:
            if t in text_lower:
                # 关键数字和专有名词加权
                if re.match(r'^\d', t) or len(t) >= 5:
                    hits += 2.0
                else:
                    hits += 1.0
                    
        score = hits / max(1.0, len(tokens))
        if hits > 0:
            scored.append((score, item))
            
    scored.sort(key=lambda x: x[0], reverse=True)
    if scored:
        return [x[1] for x in scored[:top_k]]
    return candidates[:top_k]

def highlight_sentences(pdf_path, out_path, sentences, verbose=True, offset=(0.0, 0.0)):
    """sentences: {page_idx(0-based): [sentence, ...]}, sentence 可为 str 或 (str, occurrence) 元组.
    清除已有 annot 后重加. offset: 已弃用, 恒为 (0,0) (fitz 渲染零补偿)"""
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

def annotate_document(pdf_path, out_path, config, verbose=True):
    """三元综合标注引擎 (Tri-Modal Annotator):
    config 格式:
    {
      'highlights': {page_idx: [sentence, ...]},
      'boxes': [{'page': page_idx, 'rect': [x0, y0, x1, y1], 'color': (r,g,b), 'width': 1.5, 'label': 'A'}, ...],
      'badges': [{'page': page_idx, 'rect': [x0, y0, x1, y1], 'label': 'A', 'placement': 'right'}, ...]
    }
    """
    doc = fitz.open(pdf_path)
    # 1. 清除旧标注
    for pi in range(len(doc)):
        for a in list(doc[pi].annots() or []):
            try:
                doc[pi].delete_annot(a)
            except Exception:
                pass
    
    # 2. 生成 Highlight
    hl_cfg = config.get('highlights', {})
    for pi, sents in hl_cfg.items():
        if pi < 0 or pi >= len(doc):
            continue
        page = doc[pi]
        chars, text = page_char_stream(page)
        for item in sents:
            s, occ = item if isinstance(item, tuple) else (item, 0)
            loc = locate_sentence(text, s, occ)
            if loc is None:
                continue
            rects = sentence_rects(chars, *loc)
            if not rects:
                continue
            # 末行收窄: 句子结尾非句末标点时精准对齐末尾字符
            last_ch = norm(s)[-1] if norm(s) else ''
            if last_ch not in '。！？!?.' and last_ch != '.':
                r = rects[-1]
                endr = None
                for j in range(loc[1] - 1, loc[0] - 1, -1):
                    if chars[j][0].strip():
                        endr = chars[j][1]
                        break
                if endr is not None:
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
                r2 = fitz.Rect(r)
                if ri == 0:
                    yc = (r.y0 + r.y1) / 2
                    lefts = [c[1] for c in chars
                             if abs((c[1].y0 + c[1].y1) / 2 - yc) < 4
                             and c[1].x1 < r.x0 - 1
                             and r.x0 - c[1].x1 < 50]
                    if lefts:
                        nearest_x1 = max(c.x1 for c in lefts)
                        if nearest_x1 > r.x0 - 3:
                            fr = None
                            for j in range(loc[0], loc[1]):
                                if chars[j][0].strip():
                                    fr = chars[j][1]
                                    break
                            if fr is not None:
                                r2 = fitz.Rect(fr.x0 - 0.5, r.y0, r.x1, r.y1)
                            else:
                                r2 = fitz.Rect(r.x0 + 0.6, r.y0, r.x1, r.y1)
                r3 = fitz.Rect(r2.x0 + 0.6, r2.y0, r2.x1 - 0.6, r2.y1)
                hl = page.add_rect_annot(r3)
                hl.set_colors(stroke=(1.0, 0.85, 0.0), fill=(1.0, 0.85, 0.0))
                hl.set_border(width=0)
                hl.set_opacity(0.45)
                hl.update()
                
    # 3. 生成 Square 边框
    for box in config.get('boxes', []):
        pi = box.get('page', 0)
        if 0 <= pi < len(doc):
            add_context_box(
                doc[pi], box['rect'],
                color=box.get('color', (0.9, 0.1, 0.1)),
                width=box.get('width', 1.5),
                label=box.get('label')
            )
            
    # 4. 生成 FreeText 角标
    for badge in config.get('badges', []):
        pi = badge.get('page', 0)
        if 0 <= pi < len(doc):
            add_freetext_badge(
                doc[pi], badge['rect'],
                label=badge['label'],
                fontsize=badge.get('fontsize', 11),
                text_color=badge.get('text_color', (0.9, 0.1, 0.1)),
                placement=badge.get('placement', 'right')
            )
            
    doc.save(str(out_path), garbage=4, deflate=True)
    doc.close()
    if verbose:
        print(f'Annotated {pdf_path} -> {out_path}')

