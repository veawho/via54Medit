#!/usr/bin/env python3
"""
redo_highlight_v13.py — 用 v12.1 + GLM 修 7 个真违规 Pn-x
"""
import os, sys, json, csv as csvmod, time
import fitz
import requests

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

# === GLM config ===
with open('/Users/david/.hermes/.env') as f:
    for line in f:
        if 'GLM_API_KEY=' in line:
            GLM_API_KEY = line.split('=', 1)[1].strip()
GLM_BASE_URL = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'


def glm_call(prompt, timeout=60):
    try:
        r = requests.post(
            GLM_BASE_URL,
            headers={'Authorization': f'Bearer {GLM_API_KEY}', 'Content-Type': 'application/json'},
            json={'model': 'glm-4-flash-250414', 'messages': [{'role': 'user', 'content': prompt}], 'temperature': 0.1, 'max_tokens': 800},
            timeout=timeout,
        )
        if r.status_code != 200:
            return f"[ERR {r.status_code}]: {r.text[:200]}"
        return r.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"[EXCEPTION]: {e}"


def extract_json(text):
    import re
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if m:
        try: return json.loads(m.group(1))
        except: pass
    m = re.search(r'\[[\s\S]*?\]', text)
    if m:
        try: return json.loads(m.group(0))
        except: pass
    return None


def get_pdf_pages_text(pdf_path, max_pages=5):
    doc = fitz.open(pdf_path)
    out = []
    for pno in range(min(doc.page_count, max_pages)):
        out.append(f"[Page {pno+1}]\n{doc[pno].get_text('text')[:2500]}")
    doc.close()
    return "\n".join(out)


def get_pn_slide_text(pn):
    with open(CSV_PATH, encoding='utf-8-sig') as f:
        for row in csvmod.DictReader(f):
            if row['PN'] == pn:
                slide_num = int(row['幻灯片'])
                citation = row.get('引用', '')
                break
    with open(PPT_SLIDES_JSON) as f:
        slides = json.load(f)
    slide = slides[slide_num - 1]
    texts = [f"[top={sh['top']:.2f}] {sh['text']}" for sh in slide.get('shapes', []) if sh.get('text')]
    return slide_num, citation, "\n".join(texts)


def pick_anchors_for_pn(pn, pdf_text, slide_text, slide_num, citation, n=3):
    """GLM 选 N 个 verbatim quote (跟 slide 应证段最相关)"""
    prompt = f"""你是 TMA 文献审计专家. 对给定的 PDF 文本, 选出 {n} 个 verbatim quote 作为 highlight anchor.

【核心原则】你只能从下面 "# PDF 文本" 段落的文字里复制 quote, 不能用 "# Slide" 段落的文字! Slide 内容只用于判断相关性, 不作为 quote 来源.

要求:
- quote 必须 EXACT 来自 "# PDF 文本" 段, 字符与 PDF 文本一致 (含空格、标点、换行)
- 跟 slide {slide_num} 应证段强相关 (即 PDF 内容跟 slide 主题对应)
- 必须在 PDF body 段, 不要选 title / author / 参考文献 / 缩写表 / figure caption
- 长度 8-150 字符
- 优先选 slide 应证段重点的 keyword 或 term 所在的 body 句

# Slide {slide_num} 文字 (用于判断相关性, 不是 quote 来源):
{slide_text[:1000]}

# PDF 文本 (Pn-x: {pn}, 引用: {citation[:150]}) - 【quote 只能从这里复制】:
{pdf_text[:5000]}

# 输出 (严格 JSON 数组):
```json
[
  {{"page": 1, "quote": "<EXACT 复制自 PDF 文本, 8-150 字符>", "reason": "<30字内, 为什么选>"}},
  ...
]
```
"""
    resp = glm_call(prompt)
    parsed = extract_json(resp)
    if not parsed:
        print(f"  GLM parse fail: {resp[:300]}")
        return []
    if isinstance(parsed, dict):
        parsed = parsed.get('anchors', []) or parsed.get('quotes', []) or []
    return parsed[:n]


def apply_highlight_to_pn(pn, anchors, pdf_path, step4_path):
    """应用 anchor 到 PDF"""
    if not anchors:
        return False, "no_anchors"
    doc = fitz.open(pdf_path)
    n_applied = 0
    applied_log = []
    seen_pages = set()

    for anch in anchors:
        page_idx = anch.get('page', 1) - 1
        quote = anch.get('quote', '')
        reason = anch.get('reason', '')
        if page_idx < 0 or page_idx >= doc.page_count:
            continue
        if not quote:
            continue
        page = doc[page_idx]
        # validate quote in PDF
        valid, vreason = validate_quote_in_pdf(doc, quote, page_idx, min_len=4, max_len=200)
        if not valid:
            print(f'  validate FAIL: {vreason}, quote={quote[:60]!r}')
            continue
        # find rect
        rect = find_phrase_rect(page, quote, page_idx=page_idx)
        if not rect:
            # 试 line mode
            rect = find_line_rect(page, quote)
        if not rect:
            print(f'  no rect for {quote[:60]!r}')
            continue
        # check forbidden zone (page 0 top 8%, bottom 8%, too narrow)
        page_h = page.rect.height
        if page_idx == 0 and rect.y0 < page_h * 0.08:
            print(f'  skip page0_top_8% for {quote[:40]!r}')
            continue
        if rect.y0 > page_h * 0.92:
            print(f'  skip bottom_8% for {quote[:40]!r}')
            continue
        # 词是否是 reference (含 et al. 或 年份+;vol:pages)
        text = page.get_text("text", clip=rect).strip()
        import re
        if re.search(r'et al\.', text):
            print(f'  skip ref (et al.) for {text[:60]!r}')
            continue
        if re.search(r'\d{4}\s*;\s*\d+', text):
            print(f'  skip ref (year;vol) for {text[:60]!r}')
            continue
        # 是 abbreviations? (含 ¼ 或 =)
        if '¼' in text or re.search(r'^\s*[A-Z]{2,}\s*[:：]', text):
            print(f'  skip abbreviation for {text[:60]!r}')
            continue
        # 应用 underline
        apply_underline(page, rect, color=(1, 1, 0), expand=0, anchor_text=quote, reason=reason)
        applied_log.append({
            "page": page_idx + 1,
            "y_pct": f"{rect.y0/page_h*100:.1f}-{rect.y1/page_h*100:.1f}%",
            "quote": quote,
            "reason": reason,
        })
        n_applied += 1
        seen_pages.add(page_idx)

    if n_applied == 0:
        doc.close()
        return False, "no_applied"

    # save
    tmp = step4_path + '.tmp'
    doc.save(tmp, garbage=4, deflate=True)
    doc.close()
    import shutil
    shutil.move(tmp, step4_path)
    return True, {"n_applied": n_applied, "log": applied_log}


def main():
    targets = ['P3-1', 'P4-6', 'P9-3', 'P11-2', 'P16-1', 'P23-7', 'P29-1']
    results = {}
    for pn in targets:
        pdf_path = f"{PNX_DIR}/{pn}/main.pdf"
        step4_path = f"{STEP4_DIR}/{pn}_semantic_highlight.pdf"
        if not os.path.exists(pdf_path):
            print(f"❌ {pn} main.pdf not found")
            continue
        print(f"\n=== {pn} ===")
        pdf_text = get_pdf_pages_text(pdf_path)
        slide_num, citation, slide_text = get_pn_slide_text(pn)
        print(f"  slide={slide_num}, citation={citation[:60]}")
        anchors = pick_anchors_for_pn(pn, pdf_text, slide_text, slide_num, citation, n=3)
        print(f"  GLM picked {len(anchors)} anchors")
        for anch in anchors:
            print(f"    page {anch.get('page')}: {anch.get('quote', '')[:60]!r}")
        ok, log = apply_highlight_to_pn(pn, anchors, pdf_path, step4_path)
        results[pn] = {"ok": ok, "log": log, "anchors": anchors}
        time.sleep(0.3)

    # 同步到 _pnx/highlight.pdf
    print("\n=== Sync 到 _pnx/highlight.pdf ===")
    for pn in targets:
        src = f"{STEP4_DIR}/{pn}_semantic_highlight.pdf"
        dst = f"{PNX_DIR}/{pn}/highlight.pdf"
        if os.path.exists(src) and results.get(pn, {}).get('ok'):
            import shutil
            shutil.copy(src, dst)
            print(f"  {pn}: synced")

    # 保存结果
    with open("/tmp/redo_highlight_v13_results.json", "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 /tmp/redo_highlight_v13_results.json")

    # 汇总
    ok_count = sum(1 for r in results.values() if r['ok'])
    print(f"\n成功: {ok_count}/{len(targets)}")


if __name__ == "__main__":
    main()
