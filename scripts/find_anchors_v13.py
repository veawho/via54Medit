#!/usr/bin/env python3
"""
find_anchors_v13.py — 用 keyword 匹配 + 文本相似度找 PDF anchor (不依赖 GLM)

方法:
1. 拿 PDF 全文 (按 page + line 切分)
2. 拿 slide 应证段 keyword (高频词 + 关键术语)
3. 计算每行的 keyword 命中分
4. 选 top N 行作为 anchor

比 GLM 可靠, 不 hallucinate。
"""
import os, sys, json, re, csv as csvmod
from collections import Counter
import fitz

# === 路径 ===
TMA_ROOT = "/Users/david/Desktop/TMA_文献整理"
PNX_DIR = f"{TMA_ROOT}/_pnx"
STEP4_DIR = f"{TMA_ROOT}/step4_highlight_106目录_合并DOI"
CSV_PATH = f"{TMA_ROOT}/_citation_table/tma_citation_table.csv"
PPT_SLIDES_JSON = f"{TMA_ROOT}/_citation_table/ppt_slides_analysis.json"

sys.path.insert(0, '/Users/david/Desktop/developments/via54Medit/scripts')
from m3_vision_highlight import (
    find_phrase_rect, find_line_rect, find_sentence_rect, apply_underline,
    validate_quote_in_pdf, rect_to_normalized
)
fitz.TOOLS.mupdf_display_warnings(False)


# 中文 + 英文 TMA 关键词
TMA_KEYWORDS = [
    # 核心 TMA
    'TMA', 'thrombotic microangiopathy', '血栓性微血管病', '微血管病',
    # 分类
    'aHUS', 'atypical HUS', 'TTP', 'HSCT-TMA', 'TA-TMA', 'MAHA',
    'STEC-HUS', 'HUS', '溶血尿毒综合征', '血栓性血小板减少性紫癜',
    '非典型溶血尿毒综合征', '微血管病性溶血性贫血',
    # 补体
    'complement', '补体', 'C3', 'C5', 'eculizumab', '依库珠单抗', 'ravulizumab',
    'alternative pathway', '替代途径', 'classical pathway', '经典途径',
    'lectin pathway', '凝集素途径', 'MAC', 'C5b-9', 'C3b',
    # 病理
    'endothelial', '内皮', 'platelet', '血小板', 'schistocyte', '裂红细胞', '头盔细胞',
    'microvascular', '微血管', 'thrombosis', '血栓', 'fibrin', '纤维蛋白',
    # 临床
    'AKI', 'renal', '肾', 'neurologic', '神经', 'cardiac', '心脏',
    'proteinuria', '尿蛋白', 'hypertension', '高血压',
    # 治疗
    'plasma exchange', '血浆置换', 'rituximab', '利妥昔', 'corticosteroid', '激素',
    'caplacizumab', 'anaphylatoxin', 'narsoplimab',
    # 诊断
    'ADAMTS13', 'vWF', 'CFH', 'CFI', 'CFB', 'THBD', 'MCP', 'DI',
    'biomarker', '生物标志物', 'diagnosis', '诊断', 'prognosis', '预后',
    # 中文补充
    '造血干细胞移植', '器官', '感染', '多学科', '共识', '指南',
    '鉴别', '分类', '病因', '病理', '机制',
]


def extract_keywords_from_slide(slide_text, n=20):
    """从 slide 文字提 keyword (高频 + TMA 词命中)"""
    # 提取 TMA 关键词命中
    found = []
    for kw in TMA_KEYWORDS:
        if kw in slide_text:
            found.append(kw)
    return found[:n]


def get_pdf_lines(pdf_path, skip_top_pct=0.15, skip_bot_pct=0.08):
    """拿 PDF 所有行 (按 page, line) + 过滤 forbidden zone"""
    doc = fitz.open(pdf_path)
    all_lines = []  # (page_idx, line_text, rect)
    for pno in range(doc.page_count):
        page = doc[pno]
        page_h = page.rect.height
        skip_y_top = page_h * skip_top_pct if pno == 0 else page_h * 0.05
        skip_y_bot = page_h * (1 - skip_bot_pct)

        # 按行抽文字
        blocks = page.get_text("blocks")
        for b in blocks:
            x0, y0, x1, y1, text, bno, btype = b
            text = text.strip()
            if not text or len(text) < 3:
                continue
            # 跳过 title/author/footer
            if y0 < skip_y_top or y1 > skip_y_bot:
                continue
            # 跳过 author 模式
            if re.search(r'(MD|PhD|M\.D|Ph\.D|BSc|MSc)\s*;?\s*$', text):
                continue
            # 跳过 reference 模式
            if re.search(r'et al\.', text):
                continue
            if re.search(r'\d{4}\s*;\s*\d+', text):
                continue
            # 跳过 abbreviations (含 ¼ 或 =)
            if '¼' in text:
                continue
            if re.search(r'^[A-Z]{2,}\s*[:：]\s*[a-zA-Z\u4e00-\u9fff]', text):
                continue
            all_lines.append({
                "page_idx": pno,
                "text": text,
                "rect": (x0, y0, x1, y1),
            })
    doc.close()
    return all_lines


def score_line(line_text, keywords):
    """对一行文字打分 (基于 keyword 命中)"""
    score = 0
    for kw in keywords:
        if kw in line_text:
            score += len(kw)  # 长 keyword 权重高
    # 长度 bonus (5-100 字符最佳)
    n = len(line_text)
    if 5 <= n <= 100:
        score += 5
    elif 100 < n <= 200:
        score += 3
    elif n > 300:
        score -= 5  # 太长可能含太多无关内容
    return score


def find_anchors_in_pdf(pdf_path, slide_text, n=3, min_score=5):
    """用 keyword 匹配找 PDF 里跟 slide 最相关的 N 行"""
    keywords = extract_keywords_from_slide(slide_text, n=20)
    lines = get_pdf_lines(pdf_path)
    if not lines:
        return []

    # 评分
    scored = []
    for ln in lines:
        s = score_line(ln['text'], keywords)
        if s >= min_score:
            scored.append((s, ln))

    scored.sort(key=lambda x: -x[0])

    # 去重 (相邻 page 同样内容)
    seen_text = set()
    result = []
    for score, ln in scored:
        # 简化 text 用于 dedup
        key = ln['text'][:50].lower()
        if key in seen_text:
            continue
        seen_text.add(key)
        result.append({
            "page": ln['page_idx'] + 1,
            "text": ln['text'],
            "rect": ln['rect'],
            "score": score,
        })
        if len(result) >= n:
            break
    return result


def apply_anchors(pn, anchors, pdf_path, step4_path):
    """应用 anchor 到 PDF (line mode)"""
    if not anchors:
        return False, "no_anchors"
    doc = fitz.open(pdf_path)
    n_applied = 0
    log = []
    for anch in anchors:
        text = anch['text']
        page_idx = anch['page'] - 1
        page = doc[page_idx]
        # find line rect (用 line mode, 不严格 verify)
        rect = find_line_rect(page, text)
        if not rect:
            # try find_phrase_rect with first 30 chars
            rect = find_phrase_rect(page, text[:30], page_idx=page_idx)
        if not rect:
            continue
        # forbidden zone check
        page_h = page.rect.height
        if page_idx == 0 and rect.y0 < page_h * 0.08:
            continue
        if rect.y0 > page_h * 0.92:
            continue
        # 文字是 ref / abbr
        a_text = page.get_text("text", clip=rect).strip()
        if re.search(r'et al\.', a_text):
            continue
        if re.search(r'\d{4}\s*;\s*\d+', a_text):
            continue
        if '¼' in a_text:
            continue
        if re.search(r'^[A-Z]{2,}\s*[:：]', a_text):
            continue
        # apply
        apply_underline(page, rect, color=(1, 1, 0), expand=0, anchor_text=text[:80], reason=f"slide-specific keyword match (score={anch['score']})")
        log.append({"page": page_idx + 1, "y_pct": f"{rect.y0/page_h*100:.1f}-{rect.y1/page_h*100:.1f}%", "text": text[:80]})
        n_applied += 1

    if n_applied == 0:
        doc.close()
        return False, "no_applied"

    tmp = step4_path + '.tmp'
    doc.save(tmp, garbage=4, deflate=True)
    doc.close()
    import shutil
    shutil.move(tmp, step4_path)
    return True, {"n_applied": n_applied, "log": log}


def main():
    targets = ['P3-1', 'P4-6', 'P9-3', 'P11-2', 'P16-1', 'P23-7', 'P29-1']
    with open(CSV_PATH, encoding='utf-8-sig') as f:
        slides = json.load(open(PPT_SLIDES_JSON))

    for pn in targets:
        pdf_path = f"{PNX_DIR}/{pn}/main.pdf"
        step4_path = f"{STEP4_DIR}/{pn}_semantic_highlight.pdf"
        if not os.path.exists(pdf_path):
            continue

        # 拿 slide 文字
        with open(CSV_PATH, encoding='utf-8-sig') as f:
            slide_num = None
            for row in csvmod.DictReader(f):
                if row['PN'] == pn:
                    slide_num = int(row['幻灯片'])
                    break
        if slide_num is None:
            continue
        slide_text = "\n".join(sh['text'] for sh in slides[slide_num - 1].get('shapes', []) if sh.get('text'))

        print(f"\n=== {pn} slide={slide_num} ===")
        anchors = find_anchors_in_pdf(pdf_path, slide_text, n=3, min_score=5)
        for a in anchors:
            print(f"  page {a['page']} score={a['score']}: {a['text'][:80]!r}")
        ok, log = apply_anchors(pn, anchors, pdf_path, step4_path)
        if ok:
            print(f"  ✓ applied {log['n_applied']} anchors")
            # sync
            import shutil
            shutil.copy(step4_path, f"{PNX_DIR}/{pn}/highlight.pdf")
        else:
            print(f"  ✗ fail: {log}")


if __name__ == "__main__":
    main()
