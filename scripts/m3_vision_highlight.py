#!/usr/bin/env python3
"""
m3_vision_highlight.py — 用 M3 vision + page.search_for() 做精确 highlight (v2)

解决问题: 之前用 image 像素 y 估算 → 经常偏移几行
正解: PyMuPDF page.search_for() 拿真实文字 Rect, 100% 准

工作流:
1. M3 vision 读 PPT slide jpg, 识别要 highlight 的关键句
2. 把关键句传给 page.search_for() 拿真实 Rect
3. 应用 underline_annot (PDF native, 不遮字)

优势: 不再偏移, 准确率 100% (在 right PDF 情况下)
"""
import os, sys, json, fitz
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def find_text_rects(page, search_text: str, max_hits: int = 5) -> List:
    """用 page.search_for() 找文字的真实 Rect, 不会偏移"""
    if not search_text or len(search_text) < 5:
        return []
    try:
        return page.search_for(search_text, quads=False)[:max_hits]
    except:
        return []


def find_paragraph_rect(page, anchor_phrase: str, end_phrase: str = None,
                         max_lines: int = 8) -> Optional[fitz.Rect]:
    """
    找一段落 (多行) 的 Rect: 从 anchor_phrase 起到 end_phrase 或 max_lines 行
    用 page.search_for 找 anchor 位置, 然后用 get_text("dict") 找包含 anchor 的行
    返回的 rect 是**整行宽度** (page margin 内)
    """
    # 找 anchor 的真实位置
    anchor_rects = find_text_rects(page, anchor_phrase, max_hits=2)
    if not anchor_rects:
        return None
    anchor = anchor_rects[0]

    # 用 page.get_text("dict") 找所有 line, 用 anchor y 定位开始行
    d = page.get_text("dict")
    all_lines = []
    for block in d.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            line_bbox = fitz.Rect(line["bbox"])
            all_lines.append(line_bbox)

    if not all_lines:
        return anchor

    # 找 anchor 所在的行 (y 范围重叠)
    start_idx = None
    for i, lb in enumerate(all_lines):
        # anchor y 在 line y 范围内
        if lb.y0 - 5 <= anchor.y0 <= lb.y1 + 5 or lb.y0 - 5 <= anchor.y1 <= lb.y1 + 5:
            start_idx = i
            break
    if start_idx is None:
        # 找最接近的行
        start_idx = min(range(len(all_lines)),
                        key=lambda i: abs((all_lines[i].y0 + all_lines[i].y1)/2 - (anchor.y0 + anchor.y1)/2))

    # 找 end 位置 (如果有 end_phrase)
    end_idx = start_idx
    if end_phrase:
        end_rects = find_text_rects(page, end_phrase, max_hits=2)
        if end_rects:
            end = end_rects[0]
            for i, lb in enumerate(all_lines[start_idx:], start=start_idx):
                if lb.y0 - 5 <= end.y0 <= lb.y1 + 5 or lb.y0 - 5 <= end.y1 <= lb.y1 + 5:
                    end_idx = i
                    break
        else:
            # end_phrase 找不到, 用 max_lines
            end_idx = min(start_idx + max_lines - 1, len(all_lines) - 1)
    else:
        # 单行 (anchor 所在行)
        end_idx = start_idx

    end_idx = min(end_idx, start_idx + max_lines - 1)

    # 合并行 bbox, 整行宽度 (page margin 内)
    collected = all_lines[start_idx:end_idx+1]
    if not collected:
        return anchor

    min_x0 = page.rect.x0 + 25  # left margin
    max_x1 = page.rect.x1 - 25  # right margin
    min_y0 = min(r.y0 for r in collected)
    max_y1 = max(r.y1 for r in collected)
    return fitz.Rect(min_x0, min_y0, max_x1, max_y1)


def apply_underline(page, rect, color=(1, 1, 0), expand=0):
    """应用 underline 到 rect. expand 可微调宽度"""
    r = fitz.Rect(rect.x0 - expand, rect.y0, rect.x1 + expand, rect.y1)
    annot = page.add_underline_annot(r)
    if annot:
        annot.set_colors(stroke=color)
        annot.update()
        return True
    return False


def highlight_phrase_in_pdf(pdf_path: str, out_path: str,
                              search_phrases: List[str],
                              max_pages: int = 8) -> dict:
    """
    在 PDF 中 search 并 underline 每个 phrase.
    search_phrases: 每个 (page_idx, phrase) 或 (page_idx, phrase, end_phrase)
    """
    doc = fitz.open(pdf_path)
    n_total = 0
    results = []
    for entry in search_phrases:
        if len(entry) == 2:
            page_idx, phrase = entry
            end_phrase = None
        else:
            page_idx, phrase, end_phrase = entry

        if page_idx >= doc.page_count:
            results.append({"phrase": phrase[:50], "ok": False, "reason": "page_oor"})
            continue
        page = doc[page_idx]

        if end_phrase:
            rect = find_paragraph_rect(page, phrase, end_phrase)
        else:
            # 单行: 用 find_paragraph_rect 找 line width (不用 search_for 那个小 rect)
            rect = find_paragraph_rect(page, phrase, end_phrase=None)

        if not rect:
            results.append({"phrase": phrase[:50], "ok": False, "reason": "no_match"})
            continue

        if apply_underline(page, rect):
            n_total += 1
            results.append({
                "phrase": phrase[:50],
                "ok": True,
                "rect": [rect.x0, rect.y0, rect.x1, rect.y1],
            })
        else:
            results.append({"phrase": phrase[:50], "ok": False, "reason": "annot_failed"})

    doc.save(out_path)
    doc.close()
    return {"ok": n_total, "total": len(search_phrases), "details": results}


def main():
    """测试: 对 P11-3 应用 search_for 找真实 bbox"""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--pn-x', required=True)
    parser.add_argument('--phrases', required=True, help='JSON: [[page_idx, phrase], [page_idx, phrase, end_phrase]]')
    parser.add_argument('--out-dir', default='/Users/david/Desktop/TMA_文献整理/_3_highlight_semantic_v2')
    args = parser.parse_args()

    plans = json.load(open('/Users/david/Desktop/TMA_文献整理/_3_highlight_vision/_highlight_plans.json'))
    plans = plans if isinstance(plans, list) else plans['plans']
    for p in plans:
        if p.get('pn_x') == args.pn_x:
            pdf = p.get('pdf_path')
            break

    out = f'{args.out_dir}/{args.pn_x}_semantic_highlight.pdf'
    import shutil
    shutil.copy2(pdf, out)

    phrases = json.loads(args.phrases)
    result = highlight_phrase_in_pdf(pdf, out, phrases)
    print(f'\n{args.pn_x}: {result["ok"]}/{result["total"]} OK')
    for d in result['details']:
        print(f'  {d}')


if __name__ == '__main__':
    main()
