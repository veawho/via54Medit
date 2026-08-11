#!/usr/bin/env python3
"""
m3_vision_highlight.py — M3 vision + page.search_for() 做精确 highlight (v3)

解决问题: 之前 find_paragraph_rect 强制撑到行宽 (过长), 且不支持完整句子
v3 新增 3 mode:
  - phrase:  只标 search 命中的实际 bbox 宽度 (适合关键词)
  - line:    整行宽度 (page margin 内) - 适合占整行的 abstract
  - sentence: anchor + end_phrase, 标完整句子 (anchor 到 end_phrase 之间的所有 line)

工作流:
1. M3 vision 读 PPT slide jpg, 决定 highlight 模式
2. 把 anchor (和可选 end_phrase) 传给 page.search_for() 拿真实 Rect
3. 应用 underline_annot (PDF native, 不遮字)
"""
import os, sys, json, fitz
from typing import List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


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
    """找包含 anchor 的 line index; fallback 用 y 中点最近"""
    for i, lb in enumerate(all_lines):
        if lb.y0 - 5 <= anchor.y0 <= lb.y1 + 5 or lb.y0 - 5 <= anchor.y1 <= lb.y1 + 5:
            return i
    return min(range(len(all_lines)),
               key=lambda i: abs((all_lines[i].y0 + all_lines[i].y1)/2 - (anchor.y0 + anchor.y1)/2))


# === 3 个核心 mode ===

def find_phrase_rect(page, phrase: str) -> Optional[fitz.Rect]:
    """phrase 模式: 只标 search 命中的实际 bbox 宽度 (不展宽)
    适合: PPT 引用就是某几个关键词 (如 "complement-mediated TMA")
    """
    rects = find_text_rects(page, phrase, max_hits=1)
    if not rects:
        return None
    return rects[0]


def find_line_rect(page, phrase: str) -> Optional[fitz.Rect]:
    """line 模式: 标 phrase 所在那行, 整行宽度 (page margin 内)
    适合: phrase 所在行就是 PPT 引用的整行 (如 abstract 第 1 行)
    """
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
    """sentence 模式: 从 anchor 起到 end_phrase (或 max_lines) 之间的完整句子
    适合: PPT 引用是完整句子 (如 "Eculizumab... blocks the formation of C5a and lytic C5b")
    """
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


# === 兼容旧 API: find_paragraph_rect = find_line_rect (整行宽度) ===
def find_paragraph_rect(page, anchor_phrase: str, end_phrase: str = None,
                        max_lines: int = 8) -> Optional[fitz.Rect]:
    """兼容旧 API, 等同于 find_line_rect 或 find_sentence_rect"""
    if end_phrase:
        return find_sentence_rect(page, anchor_phrase, end_phrase, max_lines)
    return find_line_rect(page, anchor_phrase)


def apply_underline(page, rect, color=(1, 1, 0), expand=0):
    """应用 underline 到 rect. expand 可微调宽度 (默认 0)"""
    r = fitz.Rect(rect.x0 - expand, rect.y0, rect.x1 + expand, rect.y1)
    annot = page.add_underline_annot(r)
    if annot:
        annot.set_colors(stroke=color)
        annot.update()
        return True
    return False


def highlight_phrase_in_pdf(pdf_path: str, out_path: str,
                              entries: List[Tuple],
                              max_pages: int = 8) -> dict:
    """
    在 PDF 中 search 并 underline 每个 entry.
    entry 格式:
      [page_idx, phrase, mode]  - mode: phrase/line/sentence
      [page_idx, phrase, mode, end_phrase]  - sentence 模式必填
      [page_idx, phrase]  - 兼容旧 API, 默认 line 模式
    """
    doc = fitz.open(pdf_path)
    n_total = 0
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
    return {"ok": n_total, "total": len(entries), "details": results}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--pn-x', required=True)
    parser.add_argument('--entries', required=True,
                        help='JSON: [[page, phrase, mode, end_phrase?], ...] 或旧格式 [[page, phrase]]')
    parser.add_argument('--out-dir', default='/Users/david/Desktop/TMA_文献整理/_3_highlight_semantic_m3')
    parser.add_argument('--mode', default=None, help='全局 mode 覆盖 (phrase/line/sentence)')
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
    # 兼容旧格式 [[page, phrase]]: 加默认 mode
    if args.mode:
        new_entries = []
        for e in entries:
            if len(e) == 2:
                new_entries.append([e[0], e[1], args.mode])
            else:
                new_entries.append(e)
        entries = new_entries

    result = highlight_phrase_in_pdf(pdf, out, entries)
    print(f'\n{args.pn_x}: {result["ok"]}/{result["total"]} OK (out: {out})')
    for d in result['details']:
        print(f'  {d}')


if __name__ == '__main__':
    main()
