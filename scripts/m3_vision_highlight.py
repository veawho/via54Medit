#!/usr/bin/env python3
"""
m3_vision_highlight.py — M3 vision + page.search_for() 做精确 highlight (v4)

v4 新增禁高亮 filter (核心 - 之前缺失):
  - title: page 0 top 22% + 文字特征
  - author: M.D./Ph.D./Department of/University of/@/et al
  - reference: References 标题 + [n] 引用 + doi:
  - declaration: Competing interests / Funding / Declaration
  - figure/table caption: "Figure 1" / "Table 1"

3 个 mode (v3 保留):
  - phrase:  只标 search 命中的实际 bbox 宽度 (适合关键词)
  - line:    整行宽度 (page margin 内) - 适合占整行的 abstract
  - sentence: anchor + end_phrase, 标完整句子
"""
import os, sys, json, fitz, re
from typing import List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# === 禁高亮 filter (v4 新增) ===

# 文字特征 - author (英文 + 中文)
_AUTHOR_TEXT_PATTERNS = [
    # 英文
    r'M\.?D\.?', r'Ph\.?D\.?', r'MBBS', r'FRCP', r'FACP',
    r'Department of', r'University of', r'University,',
    r'Correspondence', r'Corresponding author',
    r'@[\w.]+',  # email
    r' et al\.?',
    r'College of', r'School of', r'Institute of',
    r'Hospital', r'Cleveland,', r'OH, USA', r'NY, USA', r'CA, USA',
    r'^[A-Z][a-z]+\s+[A-Z]\.[\s\.]*$',  # 短 author 名 "Erin E."
    r'^[A-Z][a-z]+,\s+[A-Z]\.',  # "Smith, J."
    r'^[A-Z]\.\s*[A-Z]\.\s+[A-Z][a-z]+',  # "J. K. Smith"
    # 中文
    r'通信作者', r'通讯作者', r'第一作者',
    r'基金项目', r'基金资助', r'作者简介',
    r'作者单位', r'工作单位',
    r'大学', r'医学院', r'医院', r'研究所',
    r'医学会', r'学组', r'工作组', r'协作组',
    r'E-?mail[\s:：]',
]

# 文字特征 - reference list (英文 + 中文)
_REFERENCE_TEXT_PATTERNS = [
    # 英文
    r'^\[\d+\]', r'^\d+\.\s+[A-Z][a-z]+',
    r'^References\b', r'^REFERENCES\b',
    r'doi:\s*10\.', r'DOI[\s:：]\s*10\.', r'https?://doi\.org',
    r'\([12][0-9]{3}\)\s',  # 英文引用 (2020) 后跟空白
    r'et al\.\s+\(?[12][0-9]{3}\)?',  # "Smith et al. (2020)"
    r'This article has been accepted',  # Wiley accepted manuscript header
    r'^Received\s+\d', r'^Accepted\s+\d',  # 期刊 footer "Received May 2020"
    # 中文
    r'^参考文献', r'参\s*考\s*文\s*献',
    r'[\u4e00-\u9fa5]+\(\d{4}\)',  # 中文年份引用 "(2020)"
    r'^\d+\s*[．\.\)]\s*[\u4e00-\u9fa5]',  # 1. 中文
]

# 文字特征 - declaration (作者信息冲突)
_DECLARATION_TEXT_PATTERNS = [
    r'Competing interests?', r'Conflict[s]? of interest',
    r'^Funding\b', r'^Author contributions?',
    r'^Data availability', r'^Ethics',
    r'^Patient consent', r'^Supplementary',
    r'^Acknowledg', r'Consent for publication',
    # 中文
    r'利益冲突', r'作者贡献', r'数据可用性',
    r'知情同意', r'补充材料',
]

# 文字特征 - figure/table caption (不是正文)
_FIGURE_CAPTION_PATTERNS = [
    r'^Figure\s*\d+', r'^Fig\.\s*\d+',
    r'^Table\s*\d+',
    r'Source data', r'Open access',
]


def _get_annot_text(page, rect: fitz.Rect) -> str:
    """拿 rect 附近文字"""
    page_h = page.rect.height
    page_w = page.rect.width
    try:
        return page.get_textbox(fitz.Rect(
            max(0, rect.x0 - 5), max(0, rect.y0 - 8),
            min(page_w, rect.x1 + 5), min(page_h, rect.y1 + 8)
        )).strip()
    except:
        return ''


def _matches_any_patterns(text: str, patterns: list) -> Optional[str]:
    """检查 text 是否匹配任一 pattern, 返回第一个匹配的 pattern"""
    if not text:
        return None
    for pat in patterns:
        if re.search(pat, text, re.IGNORECASE | re.MULTILINE):
            return pat
    return None


def is_forbidden_zone(page, rect: fitz.Rect, page_idx: int,
                       allow_first_page_top: float = 0.25) -> Tuple[bool, str]:
    """检测 annot rect 是否在禁高亮区
    返回 (is_forbidden, reason)
    中文 PDF 的 author/affiliation 区域比英文大, 用 0.25 默认
    """
    page_h = page.rect.height
    page_w = page.rect.width

    # 1. 几何 - page 0 top X% = title/author/affiliation
    if page_idx == 0 and rect.y0 < page_h * allow_first_page_top:
        return True, f'page0_top_{int(allow_first_page_top*100)}%'
    # 2. 几何 - 任何 page bottom 8% = footer
    if rect.y0 > page_h * 0.92:
        return True, 'bottom_8%_footer'
    # 3. 几何 - 任何 page top 5% = page header
    if rect.y1 < page_h * 0.05:
        return True, 'top_5%_page_header'
    # 4. 几何 - 太宽太高
    if rect.width / page_w > 0.85 and rect.height / page_h > 0.25:
        return True, 'too_wide_and_tall'
    if rect.height / page_h > 0.5:
        return True, 'too_tall'
    # 5. 几何 - 太小 (单字符)
    if rect.width < 8:
        return True, 'too_narrow'

    # 6. 文字 - author
    text = _get_annot_text(page, rect)
    if text:
        pat = _matches_any_patterns(text, _AUTHOR_TEXT_PATTERNS)
        if pat:
            return True, f'author_text:{pat}'

    # 7. 文字 - reference
    if text:
        pat = _matches_any_patterns(text, _REFERENCE_TEXT_PATTERNS)
        if pat:
            return True, f'ref_text:{pat}'

    # 8. 文字 - declaration
    if text:
        pat = _matches_any_patterns(text, _DECLARATION_TEXT_PATTERNS)
        if pat:
            return True, f'declaration_text:{pat}'

    # 9. 文字 - figure/table caption
    if text:
        pat = _matches_any_patterns(text, _FIGURE_CAPTION_PATTERNS)
        if pat:
            return True, f'figure_caption:{pat}'

    # 10. 文字 - 整段都是 reference 数字 [n]
    if text and re.search(r'\[\d+\]\s*\[\d+\]\s*\[\d+\]', text):
        return True, 'ref_numbers'

    return False, ''


# === 核心 find 函数 ===

def find_text_rects(page, search_text: str, max_hits: int = 5) -> List:
    """用 page.search_for() 找文字的真实 Rect"""
    if not search_text or len(search_text) < 5:
        return []
    try:
        return page.search_for(search_text, quads=False)[:max_hits]
    except:
        return []


def _all_lines(page) -> List:
    """返回 page 所有 line bbox 列表"""
    d = page.get_text("dict")
    lines = []
    for block in d.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            lines.append(fitz.Rect(line["bbox"]))
    return lines


def _line_index_containing(all_lines: List, anchor: fitz.Rect) -> int:
    for i, lb in enumerate(all_lines):
        if lb.y0 - 5 <= anchor.y0 <= lb.y1 + 5 or lb.y0 - 5 <= anchor.y1 <= lb.y1 + 5:
            return i
    return min(range(len(all_lines)),
               key=lambda i: abs((all_lines[i].y0 + all_lines[i].y1)/2 - (anchor.y0 + anchor.y1)/2))


def find_phrase_rect(page, phrase: str, page_idx: int = 0) -> Optional[fitz.Rect]:
    """phrase 模式: 只标 search 命中的实际 bbox 宽度 (不展宽)
    PyMuPDF search_for 可能返回 partial match hit (只匹配 phrase 一部分),
    filter 掉 title/author/ref 区域, 在剩下的里取最宽的 (最完整)
    """
    rects = find_text_rects(page, phrase, max_hits=5)
    if not rects:
        return None
    # filter 掉禁高亮区
    valid = []
    for r in rects:
        is_bad, _ = is_forbidden_zone(page, r, page_idx)
        if not is_bad:
            valid.append(r)
    if not valid:
        # 全部都在禁高亮区, 返回 None (caller 用 filter 拒)
        return None
    # 取最宽 (最可能是完整 phrase)
    return max(valid, key=lambda r: r.width)


def find_line_rect(page, phrase: str) -> Optional[fitz.Rect]:
    """line 模式: 标 phrase 所在行, 整行宽度"""
    rects = find_text_rects(page, phrase, max_hits=1)
    if not rects:
        return None
    anchor = rects[0]
    all_lines = _all_lines(page)
    if not all_lines:
        return anchor
    idx = _line_index_containing(all_lines, anchor)
    line_bbox = all_lines[idx]
    return fitz.Rect(page.rect.x0 + 25, line_bbox.y0, page.rect.x1 - 25, line_bbox.y1)


def find_sentence_rect(page, anchor_phrase: str, end_phrase: str = None,
                       max_lines: int = 6) -> Optional[fitz.Rect]:
    """sentence 模式: 从 anchor 起到 end_phrase (或 max_lines) 之间所有 line"""
    rects = find_text_rects(page, anchor_phrase, max_hits=1)
    if not rects:
        return None
    anchor = rects[0]
    all_lines = _all_lines(page)
    if not all_lines:
        return anchor
    start_idx = _line_index_containing(all_lines, anchor)

    end_idx = start_idx
    if end_phrase:
        end_rects = find_text_rects(page, end_phrase, max_hits=1)
        if end_rects:
            end = end_rects[0]
            for i, lb in enumerate(all_lines[start_idx:], start=start_idx):
                if lb.y0 - 5 <= end.y0 <= lb.y1 + 5 or lb.y0 - 5 <= end.y1 <= lb.y1 + 5:
                    end_idx = i
                    break
            else:
                end_idx = min(start_idx + max_lines - 1, len(all_lines) - 1)
        else:
            end_idx = min(start_idx + max_lines - 1, len(all_lines) - 1)
    else:
        end_idx = min(start_idx + max_lines - 1, len(all_lines) - 1)

    collected = all_lines[start_idx:end_idx + 1]
    if not collected:
        return anchor

    return fitz.Rect(
        page.rect.x0 + 25,
        min(r.y0 for r in collected),
        page.rect.x1 - 25,
        max(r.y1 for r in collected),
    )


# 兼容旧 API
def find_paragraph_rect(page, anchor_phrase, end_phrase=None, max_lines=8):
    if end_phrase:
        return find_sentence_rect(page, anchor_phrase, end_phrase, max_lines)
    return find_line_rect(page, anchor_phrase)


def apply_underline(page, rect, color=(1, 1, 0), expand=0):
    """应用 underline 到 rect"""
    r = fitz.Rect(rect.x0 - expand, rect.y0, rect.x1 + expand, rect.y1)
    annot = page.add_underline_annot(r)
    if annot:
        annot.set_colors(stroke=color)
        annot.update()
        return True
    return False


def highlight_phrase_in_pdf(pdf_path: str, out_path: str,
                              entries: List[Tuple],
                              max_pages: int = 8,
                              enforce_forbidden: bool = True) -> dict:
    """
    在 PDF 中 search 并 underline 每个 entry.
    enforce_forbidden=True 时, 跳过 title/author/ref/declaration/figure caption
    """
    doc = fitz.open(pdf_path)
    n_total = 0
    n_skipped = 0
    results = []
    for entry in entries:
        if len(entry) == 2:
            page_idx, phrase = entry
            mode = "line"
            end_phrase = None
        elif len(entry) == 3:
            page_idx, phrase, mode = entry
            end_phrase = None
        else:
            page_idx, phrase, mode, end_phrase = entry

        if page_idx >= doc.page_count:
            results.append({"phrase": phrase[:50], "mode": mode, "ok": False, "reason": "page_oor"})
            continue
        page = doc[page_idx]

        if mode == "phrase":
            rect = find_phrase_rect(page, phrase)
        elif mode == "sentence":
            rect = find_sentence_rect(page, phrase, end_phrase)
        elif mode == "line":
            rect = find_line_rect(page, phrase)
        else:
            results.append({"phrase": phrase[:50], "mode": mode, "ok": False, "reason": f"unknown_mode:{mode}"})
            continue

        if not rect:
            results.append({"phrase": phrase[:50], "mode": mode, "ok": False, "reason": "no_match"})
            continue

        # v4 新增: 禁高亮 filter
        if enforce_forbidden:
            is_bad, reason = is_forbidden_zone(page, rect, page_idx)
            if is_bad:
                n_skipped += 1
                results.append({
                    "phrase": phrase[:50], "mode": mode, "ok": False,
                    "reason": f"forbidden:{reason}",
                    "rect": [rect.x0, rect.y0, rect.x1, rect.y1],
                })
                continue

        if apply_underline(page, rect):
            n_total += 1
            results.append({
                "phrase": phrase[:50],
                "mode": mode,
                "ok": True,
                "rect": [rect.x0, rect.y0, rect.x1, rect.y1],
            })
        else:
            results.append({"phrase": phrase[:50], "mode": mode, "ok": False, "reason": "annot_failed"})

    doc.save(out_path)
    doc.close()
    return {"ok": n_total, "skipped": n_skipped, "total": len(entries), "details": results}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--pn-x', required=True)
    parser.add_argument('--entries', required=True,
                        help='JSON: [[page, phrase, mode, end_phrase?], ...]')
    parser.add_argument('--out-dir', default='/Users/david/Desktop/TMA_文献整理/_3_highlight_semantic_m3')
    parser.add_argument('--mode', default=None, help='全局 mode 覆盖')
    parser.add_argument('--no-filter', action='store_true', help='禁用禁高亮 filter')
    args = parser.parse_args()

    plans = json.load(open('/Users/david/Desktop/TMA_文献整理/_3_highlight_vision/_highlight_plans.json'))
    plans = plans if isinstance(plans, list) else plans['plans']
    pdf = None
    for p in plans:
        if p.get('pn_x') == args.pn_x:
            pdf = p.get('pdf_path')
            break
    if not pdf or not os.path.isfile(pdf):
        print(f'ERROR: no PDF for {args.pn_x}')
        sys.exit(1)

    os.makedirs(args.out_dir, exist_ok=True)
    out = f'{args.out_dir}/{args.pn_x}_semantic_highlight.pdf'
    import shutil
    shutil.copy2(pdf, out)

    entries = json.loads(args.entries)
    if args.mode:
        new_entries = []
        for e in entries:
            if len(e) == 2:
                new_entries.append([e[0], e[1], args.mode])
            else:
                new_entries.append(e)
        entries = new_entries

    result = highlight_phrase_in_pdf(pdf, out, entries, enforce_forbidden=not args.no_filter)
    print(f'\n{args.pn_x}: {result["ok"]}/{result["total"]} OK, {result["skipped"]} skipped (out: {out})')
    for d in result['details']:
        print(f'  {d}')


if __name__ == '__main__':
    main()
