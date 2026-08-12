#!/usr/bin/env python3
"""
fix_phase1_violations.py — 修 Phase 1 audit 新违规
"""
import os, sys, json, re, csv as csvmod, shutil
import fitz
fitz.TOOLS.mupdf_display_warnings(False)

TMA_ROOT = "/Users/david/Desktop/TMA_文献整理"
PNX_DIR = f"{TMA_ROOT}/_pnx"
STEP4_DIR = f"{TMA_ROOT}/step4_highlight_106目录_合并DOI"
CSV_PATH = f"{TMA_ROOT}/_citation_table/tma_citation_table.csv"
PPT_SLIDES_JSON = f"{TMA_ROOT}/_citation_table/ppt_slides_analysis.json"

sys.path.insert(0, '/Users/david/Desktop/developments/via54Medit/scripts')
from m3_vision_highlight import (
    find_phrase_rect, find_line_rect, find_sentence_rect, apply_underline
)


def find_better_anchors(pn, n=3):
    """找更好的 anchor (跳过已违规的)"""
    pdf_path = f"{PNX_DIR}/{pn}/main.pdf"
    doc = fitz.open(pdf_path)

    # 拿 slide 应证段
    with open(CSV_PATH, encoding='utf-8-sig') as f:
        slide_num = None
        for row in csvmod.DictReader(f):
            if row['PN'] == pn:
                slide_num = int(row['幻灯片'])
                break
    with open(PPT_SLIDES_JSON) as f:
        slides = json.load(f)
    slide_text = "\n".join(sh['text'] for sh in slides[slide_num - 1].get('shapes', []) if sh.get('text'))

    # 中文 + 英文 TMA 关键词
    keywords = [
        'TMA', 'thrombotic microangiopathy', 'aHUS', 'TTP', 'HUS',
        'MAHA', 'ADAMTS13', 'complement', 'C3', 'C5', 'eculizumab',
        'platelet', 'schistocyte', 'endothelial', 'HSCT-TMA', 'TA-TMA',
        'plasma exchange', 'rituximab', 'caplacizumab', 'narsoplimab',
        '补体', '血栓性微血管病', '微血管病', '内皮', '血小板', '裂红细胞',
        '溶血尿毒综合征', '血栓性血小板减少性紫癜', '血浆置换',
        '造血干细胞移植', '感染', '诊断', '治疗', '机制', '病理',
    ]

    # 抽所有 line
    candidates = []
    seen_text = set()
    for pno in range(doc.page_count):
        page = doc[pno]
        page_h = page.rect.height
        blocks = page.get_text("blocks")
        for b in blocks:
            x0, y0, x1, y1, text, bno, btype = b
            text = text.strip()
            if not text or len(text) < 5:
                continue
            # forbidden zone
            if pno == 0 and y0 < page_h * 0.08:  # title
                continue
            if y0 > page_h * 0.92:  # footer
                continue
            if y1 < page_h * 0.05:  # header
                continue
            # author / ref
            if re.search(r'(MD|PhD|M\.D|Ph\.D|BSc|MSc)\s*;?\s*$', text):
                continue
            if re.search(r'et al\.', text):
                continue
            if re.search(r'\d{4}\s*;\s*\d+', text):
                continue
            if '¼' in text:
                continue
            if re.search(r'^[A-Z]{2,}\s*[:：]\s*[a-zA-Z\u4e00-\u9fff]', text):
                continue
            if re.search(r'^\s*(Fig|Figure|FIGURE|表|图|Table|TABLE)\s*\.?\s*\d+', text):
                continue
            if re.search(r'^\s*Figure\s+\d+\s*\|', text):
                continue
            # 中文 author
            if pno == 0 and y0 < page_h * 0.30 and re.search(r'[\u4e00-\u9fff]', text):
                # 中文 PDF 标题 + author 区 - 但只跳 author, 不跳 body
                if '通信作者' in text or 'Email' in text or '教授' in text or re.search(r'[\u4e00-\u9fff]{2,4}\u3000[\u4e00-\u9fff]{2,4}\u3000[\u4e00-\u9fff]{2,4}', text):
                    continue
            # 编号列表段
            if re.match(r'^\d+[\.\)]\s+(EVH|FIG|Table|Fig|图|表)', text):
                continue
            # 评分
            score = 0
            for kw in keywords:
                if kw in text:
                    score += len(kw)
            n_chars = len(text)
            if 20 <= n_chars <= 150:
                score += 8
            elif 150 < n_chars <= 250:
                score += 5
            elif n_chars > 400:
                score -= 5
            # 跟 slide 应证段相关
            for kw in keywords:
                if kw in slide_text and kw in text:
                    score += 3
            if score < 8:
                continue
            key = text[:50].lower()
            if key in seen_text:
                continue
            seen_text.add(key)
            candidates.append({
                "page_idx": pno,
                "text": text,
                "rect": (x0, y0, x1, y1),
                "score": score,
            })

    candidates.sort(key=lambda x: -x['score'])
    doc.close()
    return candidates[:n]


def reset_and_apply(pn, anchors):
    """清空 PDF 所有 highlight, 然后应用新 anchor"""
    pdf_path = f"{PNX_DIR}/{pn}/main.pdf"
    step4_path = f"{STEP4_DIR}/{pn}_semantic_highlight.pdf"
    # 从 main 重新开始
    shutil.copy(pdf_path, step4_path)
    doc = fitz.open(step4_path)
    n_applied = 0
    log = []
    for anch in anchors:
        page = doc[anch['page_idx']]
        rect = fitz.Rect(*anch['rect'])
        # 二次过滤
        page_h = page.rect.height
        if anch['page_idx'] == 0 and rect.y0 < page_h * 0.08:
            continue
        if rect.y0 > page_h * 0.92:
            continue
        if rect.height / page_h > 0.4:
            continue
        if rect.width / page.rect.width > 0.85 and rect.height / page_h > 0.2:
            continue
        a_text = page.get_text("text", clip=rect).strip()
        if re.search(r'et al\.', a_text) or re.search(r'\d{4}\s*;\s*\d+', a_text):
            continue
        if re.search(r'^\s*(Fig|Figure|FIGURE|表|图|Table|TABLE)\s*\.?\s*\d+', a_text):
            continue
        apply_underline(page, rect, color=(1, 1, 0), expand=0, anchor_text=anch['text'][:80], reason=f"slide-specific (score={anch['score']})")
        log.append({"page": anch['page_idx'] + 1, "y_pct": f"{rect.y0/page_h*100:.1f}-{rect.y1/page_h*100:.1f}%", "text": anch['text'][:80], "score": anch['score']})
        n_applied += 1

    if n_applied == 0:
        doc.close()
        return False, "no_applied"

    tmp = step4_path + '.tmp'
    doc.save(tmp, garbage=4, deflate=True)
    doc.close()
    shutil.move(tmp, step4_path)
    shutil.copy(step4_path, f"{PNX_DIR}/{pn}/highlight.pdf")
    return True, {"n_applied": n_applied, "log": log}


def main():
    targets = ['P11-2', 'P16-1', 'P3-1', 'P9-3', 'P23-9']  # 4 新违规 + P23-9 false positive 重做 (避免 RN 误判)
    for pn in targets:
        print(f"\n=== {pn} ===")
        anchors = find_better_anchors(pn, n=3)
        for a in anchors:
            print(f"  page {a['page_idx']+1} score={a['score']} y={a['rect'][1]:.0f}: {a['text'][:80]!r}")
        ok, log = reset_and_apply(pn, anchors)
        if ok:
            print(f"  ✓ applied {log['n_applied']} anchors")
        else:
            print(f"  ✗ fail: {log}")


if __name__ == "__main__":
    main()
