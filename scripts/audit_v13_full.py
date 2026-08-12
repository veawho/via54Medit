#!/usr/bin/env python3
"""
audit_v13_full.py — Phase 3 v2 GLM semantic audit (改进版)

对每个 Pn-x:
  1. 拿 PDF 全文 (前 5000 字符)
  2. 拿 highlight 的 anchor + bbox
  3. 拿对应 slide 的所有 shape 文字
  4. 用 GLM 一次判断: PDF 跟 slide 是否相关, anchor 选得对不对

User 硬要求 (2026-08-12):
  - 必须 visual + semantic 匹配
  - 必须禁止 highlight 标题/作者/参考文献
"""
import os, sys, json, re, time, csv as csvmod
from pathlib import Path
from typing import List, Dict, Tuple
import fitz
import requests

# === 路径 ===
TMA_ROOT = "/Users/david/Desktop/TMA_文献整理"
STEP4_DIR = f"{TMA_ROOT}/step4_highlight_106目录_合并DOI"
PNX_DIR = f"{TMA_ROOT}/_pnx"
CSV_PATH = f"{TMA_ROOT}/_citation_table/tma_citation_table.csv"
PPT_SLIDES_JSON = f"{TMA_ROOT}/_citation_table/ppt_slides_analysis.json"

# === GLM config ===
with open('/Users/david/.hermes/.env') as f:
    for line in f:
        if 'GLM_API_KEY=' in line:
            GLM_API_KEY = line.split('=', 1)[1].strip()
GLM_BASE_URL = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'


def glm_call(prompt: str, model: str = "glm-4-flash-250414", timeout: int = 60) -> str:
    try:
        r = requests.post(
            GLM_BASE_URL,
            headers={'Authorization': f'Bearer {GLM_API_KEY}', 'Content-Type': 'application/json'},
            json={
                'model': model,
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': 0.0,
                'max_tokens': 1500,
            },
            timeout=timeout,
        )
        if r.status_code != 200:
            return f"[ERR {r.status_code}]: {r.text[:200]}"
        data = r.json()
        if 'error' in data:
            return f"[GLM_ERROR]: {data['error']}"
        return data['choices'][0]['message']['content']
    except Exception as e:
        return f"[EXCEPTION]: {str(e)[:200]}"


def extract_json(text: str) -> dict:
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except:
            pass
    m = re.search(r'\{[\s\S]*\}', text)
    if m:
        try:
            return json.loads(m.group(0))
        except:
            pass
    return {}


def get_pn_slide(pn: str) -> Tuple[int, str]:
    """拿 Pn-x 对应的 slide number + slide text"""
    with open(CSV_PATH, encoding='utf-8-sig') as f:
        for row in csvmod.DictReader(f):
            if row['PN'] == pn:
                slide_num = int(row['幻灯片'])
                citation = row.get('引用', '')
                break
        else:
            return 0, ""
    with open(PPT_SLIDES_JSON) as f:
        slides = json.load(f)
    if slide_num < 1 or slide_num > len(slides):
        return slide_num, ""
    slide = slides[slide_num - 1]
    texts = []
    for sh in slide.get('shapes', []):
        if sh.get('text'):
            texts.append(f"[top={sh['top']:.2f}] {sh['text']}")
    return slide_num, "\n".join(texts)


def get_pdf_text(pdf_path: str, max_chars: int = 4000) -> str:
    """拿 PDF 全文 (前 max_chars 字符)"""
    doc = fitz.open(pdf_path)
    full = ""
    for pno in range(min(doc.page_count, 3)):  # 前 3 页
        page = doc[pno]
        text = page.get_text("text")
        full += f"\n[Page {pno+1}]\n{text}"
    doc.close()
    return full[:max_chars]


def get_anchors(pdf_path: str) -> List[Dict]:
    doc = fitz.open(pdf_path)
    anchors = []
    for pno in range(doc.page_count):
        page = doc[pno]
        for annot in page.annots() or []:
            try:
                if annot.type[0] not in (8, 9):
                    continue
            except:
                continue
            rect = annot.rect
            text = page.get_text("text", clip=rect).strip()
            anchors.append({
                "page": pno + 1,
                "y_pct": f"{rect.y0/page.rect.height*100:.1f}-{rect.y1/page.rect.height*100:.1f}%",
                "text": text,
            })
    doc.close()
    return anchors


def audit_pn(pn: str, anchors: List[Dict], pdf_text: str, slide_text: str, slide_num: int, citation: str) -> Dict:
    """单个 Pn-x 完整 audit"""
    if not anchors:
        return {"pdf_match_slide": "no_anchor", "anchors_ok": [], "anchors_bad": []}

    anchor_list_str = "\n".join([f"  [{i+1}] page {a['page']} y={a['y_pct']}: {a['text'][:120]!r}"
                                  for i, a in enumerate(anchors)])

    prompt = f"""你是 TMA (血栓性微血管病) 文献审计专家. 严格评估一个 PDF highlight anchor 跟 slide 应证段是否语义匹配.

# 任务
- 评估 PDF 整体内容是否跟 slide 应证段 (除 reference list 外) 主题相关
- 评估每个 highlight anchor 是否选在该 PDF 的"应证段" (而非标题/作者/参考文献/缩写表/figure caption)
- 评估每个 anchor 文本是否真的跟 slide 应证段相关

# 元信息
- Pn-x: {pn}
- Slide {slide_num}
- 飞书表引用: {citation[:200]}

# Slide {slide_num} 文字 (PPT 实际内容, 排除 reference list 行):
{slide_text[:2000]}

# PDF 全文 (前 4000 字符):
{pdf_text[:4000]}

# PDF highlight anchors:
{anchor_list_str}

# 输出 (严格 JSON)
```json
{{
  "pdf_topic": "<1-2 词描述 PDF 主题>",
  "slide_topic": "<1-2 词描述 slide 主题>",
  "pdf_relevant_to_slide": "yes" | "no",
  "pdf_relevance_reason": "<30字内说明>",
  "anchors": [
    {{
      "i": 1,
      "in_forbidden_zone": "title" | "author" | "reference" | "abbreviation" | "figure_caption" | "no",
      "semantic_match": "match" | "partial" | "no_match",
      "is_evidence_for_slide": "yes" | "no",
      "reason": "<30字内说明>"
    }}
  ]
}}
```

判断原则:
- 标题 (title): PDF page 0 top 5-10% 区域, 大字短行
- 作者 (author): 含 "MD/PhD/Department/University" 等模式
- 参考文献 (reference): 含年份+期刊+页码, 如 "2020;191(4):579-586", 或 author list "Laurence J, Haller H, et al."
- 缩写 (abbreviation): 含 "TMA: 血栓性微血管病" 类定义行
- figure_caption: "Fig. 1" "Figure 2" "表1" 开头
"""

    response = glm_call(prompt, timeout=90)
    if response.startswith("[ERR") or response.startswith("[EXCEPTION") or response.startswith("[GLM_ERROR"):
        return {"error": response[:300], "raw": response[:500]}

    parsed = extract_json(response)
    if not parsed:
        return {"raw": response[:500]}
    return parsed


def main():
    pn_x = sorted([f.replace('_semantic_highlight.pdf', '')
                   for f in os.listdir(STEP4_DIR)
                   if f.endswith('_semantic_highlight.pdf')])
    SKIP_PN = {'P12-3'}

    # 读 CSV
    citations = {}
    with open(CSV_PATH, encoding='utf-8-sig') as f:
        for row in csvmod.DictReader(f):
            citations[row['PN']] = row.get('引用', '')

    targets = []
    for pn in pn_x:
        if pn in SKIP_PN:
            continue
        step4_pdf = f"{STEP4_DIR}/{pn}_semantic_highlight.pdf"
        if not os.path.exists(step4_pdf) or os.path.getsize(step4_pdf) < 5000:
            continue
        anchors = get_anchors(step4_pdf)
        if not anchors:
            continue
        # PDF 用 main.pdf (step3) 还是 highlight? 用 main 即可, content 相同
        pnx_pdf = f"{PNX_DIR}/{pn}/main.pdf"
        if not os.path.exists(pnx_pdf):
            pnx_pdf = step4_pdf
        pdf_text = get_pdf_text(pnx_pdf)
        slide_num, slide_text = get_pn_slide(pn)
        targets.append((pn, anchors, pdf_text, slide_text, slide_num, citations.get(pn, '')))

    print(f"📋 待 audit: {len(targets)} 个 Pn-x")

    results = {}
    for i, (pn, anchors, pdf_text, slide_text, slide_num, citation) in enumerate(targets):
        if i % 10 == 0:
            print(f"[{i+1}/{len(targets)}] {pn} slide={slide_num} anchors={len(anchors)}")
        audit = audit_pn(pn, anchors, pdf_text, slide_text, slide_num, citation)
        results[pn] = {
            "slide": slide_num,
            "citation": citation[:120],
            "anchors": anchors,
            "audit": audit,
        }
        time.sleep(0.3)

    with open("/tmp/audit_v13_full.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 /tmp/audit_v13_full.json")

    # 汇总
    violations = {
        "pdf_not_relevant": [],
        "anchors_in_forbidden": [],
        "anchors_no_match": [],
        "anchors_partial": [],
        "errors": [],
    }
    for pn, r in results.items():
        a = r['audit']
        if 'error' in a or 'raw' in a and 'pdf_topic' not in a:
            violations['errors'].append(pn)
            continue
        if a.get('pdf_relevant_to_slide') == 'no':
            violations['pdf_not_relevant'].append(pn)
        for anch in a.get('anchors', []):
            iz = anch.get('in_forbidden_zone', 'no')
            sm = anch.get('semantic_match', 'no_match')
            if iz != 'no':
                violations['anchors_in_forbidden'].append((pn, anch.get('i'), iz))
            if sm == 'no_match':
                violations['anchors_no_match'].append((pn, anch.get('i'), anch.get('reason')))
            elif sm == 'partial':
                violations['anchors_partial'].append((pn, anch.get('i'), anch.get('reason')))

    print(f"\n=== 审计汇总 ===")
    print(f"总 Pn-x: {len(targets)}")
    print(f"PDF 跟 slide 不相关: {len(violations['pdf_not_relevant'])} → {violations['pdf_not_relevant'][:10]}")
    print(f"Anchor 在 forbidden zone: {len(violations['anchors_in_forbidden'])} → {violations['anchors_in_forbidden'][:10]}")
    print(f"Anchor semantic no_match: {len(violations['anchors_no_match'])} → {violations['anchors_no_match'][:10]}")
    print(f"Anchor partial: {len(violations['anchors_partial'])}")
    print(f"GLM errors: {len(violations['errors'])} → {violations['errors'][:5]}")


if __name__ == "__main__":
    main()
