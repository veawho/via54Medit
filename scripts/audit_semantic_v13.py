#!/usr/bin/env python3
"""
audit_semantic_v13.py — Phase 3 GLM semantic match audit

对每个有 highlight 的 Pn-x:
  1. 拿 highlight 的 anchor text + bbox
  2. 拿对应 slide 的所有 shape 文字 (D_ppt_visual)
  3. 用 GLM 验证 anchor 跟 slide 应证段 semantic match
  4. 返回 match / partial / no_match + reason

User 硬要求:
  - 必须 visual + semantic 匹配
  - 必须禁止 highlight 标题/作者/参考文献
"""
import os, sys, json, re, time
from pathlib import Path
from typing import List, Dict, Tuple
import fitz
import requests

# === 路径 ===
TMA_ROOT = "/Users/david/Desktop/TMA_文献整理"
STEP4_DIR = f"{TMA_ROOT}/step4_highlight_106目录_合并DOI"
CSV_PATH = f"{TMA_ROOT}/_citation_table/tma_citation_table.csv"
PPT_SLIDES_JSON = f"{TMA_ROOT}/_citation_table/ppt_slides_analysis.json"
PPT_XML_JSON = f"{TMA_ROOT}/step2_标注分析/_pptx_xml_structured.json"

# === GLM config ===
with open(os.environ.get('HERMES_ENV', '/Users/david/.hermes/.env')) as f:
    for line in f:
        if 'GLM_API_KEY=' in line:
            GLM_API_KEY = line.split('=', 1)[1].strip()
        if 'GLM_BASE_URL=' in line:
            GLM_BASE_URL = line.split('=', 1)[1].strip()
if not GLM_BASE_URL.endswith('/chat/completions'):
    if GLM_BASE_URL.endswith('/v4'):
        GLM_BASE_URL = GLM_BASE_URL + '/chat/completions'
    elif GLM_BASE_URL.endswith('/anthropic'):
        # anthropic 兼容模式也是 /v1/messages 不是 /chat/completions
        # 但我们 glm-4-flash 不支持 anthropic 模式, 改用 paas 标准
        GLM_BASE_URL = 'https://open.bigmodel.cn/api/paas/v4/chat/completions'
    else:
        GLM_BASE_URL = GLM_BASE_URL + '/v4/chat/completions'


def glm_call(prompt: str, model: str = "glm-4-flash-250414", timeout: int = 60) -> str:
    """GLM API call"""
    try:
        r = requests.post(
            GLM_BASE_URL,
            headers={'Authorization': f'Bearer {GLM_API_KEY}', 'Content-Type': 'application/json'},
            json={
                'model': model,
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': 0.1,
            },
            timeout=timeout,
        )
        if r.status_code != 200:
            return f"[ERR {r.status_code}]: {r.text[:200]}"
        data = r.json()
        return data['choices'][0]['message']['content']
    except Exception as e:
        return f"[EXCEPTION]: {str(e)[:200]}"


def extract_json_from_glm(text: str) -> dict:
    """从 GLM 输出抽 JSON"""
    # 找 ```json ... ``` 块
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except:
            pass
    # 找 { ... } 第一对
    m = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except:
            pass
    return {}


def get_pn_slide_text(pn: str) -> Tuple[int, str]:
    """拿 Pn-x 对应的 slide number + slide text"""
    # 读 CSV
    import csv
    with open(CSV_PATH, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            if row['PN'] == pn:
                slide_num = int(row['幻灯片'])
                break
        else:
            return 0, ""

    # 拿 slide 所有 text
    with open(PPT_SLIDES_JSON) as f:
        slides = json.load(f)
    if slide_num < 1 or slide_num > len(slides):
        return slide_num, ""

    slide = slides[slide_num - 1]
    texts = []
    for sh in slide.get('shapes', []):
        if sh.get('text'):
            texts.append(sh['text'])
    return slide_num, "\n".join(texts)


def get_all_anchors_from_pdf(pdf_path: str) -> List[Dict]:
    """从 step4 PDF 抽所有 highlight 的 anchor + bbox"""
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
                "bbox": [rect.x0, rect.y0, rect.x1, rect.y1],
            })
    doc.close()
    return anchors


def audit_one_pn(pn: str, anchors: List[Dict], slide_text: str, slide_num: int) -> Dict:
    """对单个 Pn-x 跑 GLM semantic audit"""
    if not anchors:
        return {"match": "no_anchor", "reason": "no highlight in PDF"}

    # 组 prompt
    anchor_list_str = "\n".join([f"  [{i+1}] page {a['page']} y={a['y_pct']}: {a['text'][:80]!r}"
                                  for i, a in enumerate(anchors)])

    prompt = f"""你是 TMA (血栓性微血管病) 文献审核专家. 验证 PDF highlight anchor 是否跟 slide 应证段 semantic match.

# Slide {slide_num} 应证段 (PPT 上的内容):
{slide_text[:1500]}

# PDF 中的 highlight anchor (PDF: {pn}):
{anchor_list_str}

# 任务
对每个 anchor, 评估:
1. "match": 跟 slide 应证段主题直接相关 (描述同一概念/数据/结论)
2. "partial": 部分相关 (同一大方向但不是该 slide 重点)
3. "no_match": 跟 slide 应证段不相关, 或 anchor 像是标题/作者/参考文献

返回严格 JSON:
```json
{{
  "overall_match": "yes" | "partial" | "no",
  "anchors": [
    {{"i": 1, "match": "match/partial/no_match", "reason": "简短说明 (≤30字)"}},
    ...
  ]
}}
```
"""

    response = glm_call(prompt, timeout=90)
    if response.startswith("[ERR") or response.startswith("[EXCEPTION"):
        return {"match": "glm_error", "raw": response[:500], "anchors": []}
    parsed = extract_json_from_glm(response)
    if not parsed:
        return {"match": "glm_error", "raw": response[:500], "anchors": []}
    # 错误检查
    if "error" in parsed and isinstance(parsed.get("error"), dict):
        return {"match": "glm_error", "raw": str(parsed)[:500], "anchors": []}
    return parsed


def main():
    pn_x = sorted([f.replace('_semantic_highlight.pdf', '')
                   for f in os.listdir(STEP4_DIR)
                   if f.endswith('_semantic_highlight.pdf')])
    SKIP_PN = {'P12-3'}

    # 收集要 audit 的 Pn-x
    targets = []
    for pn in pn_x:
        if pn in SKIP_PN:
            continue
        step4_pdf = f"{STEP4_DIR}/{pn}_semantic_highlight.pdf"
        if not os.path.exists(step4_pdf) or os.path.getsize(step4_pdf) < 5000:
            continue
        anchors = get_all_anchors_from_pdf(step4_pdf)
        if not anchors:
            continue
        slide_num, slide_text = get_pn_slide_text(pn)
        targets.append((pn, anchors, slide_num, slide_text))

    print(f"📋 待 audit: {len(targets)} 个 Pn-x")

    results = {}
    for i, (pn, anchors, slide_num, slide_text) in enumerate(targets):
        if i % 5 == 0:
            print(f"[{i+1}/{len(targets)}] {pn} slide={slide_num} anchors={len(anchors)}")
        audit = audit_one_pn(pn, anchors, slide_text, slide_num)
        results[pn] = {
            "slide": slide_num,
            "anchors": anchors,
            "audit": audit,
        }
        time.sleep(0.5)  # 避免 GLM rate limit

    # 保存
    with open("/tmp/audit_v13_semantic.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n💾 /tmp/audit_v13_semantic.json")

    # 汇总
    no_match_pn = []
    partial_pn = []
    glm_err = []
    for pn, r in results.items():
        m = r['audit'].get('match') or r['audit'].get('overall_match')
        if m == 'no' or m == 'no_match':
            no_match_pn.append(pn)
        elif m == 'partial':
            partial_pn.append(pn)
        elif m == 'glm_error':
            glm_err.append(pn)

    print(f"\n=== Semantic Audit 汇总 ===")
    print(f"总 Pn-x: {len(targets)}")
    print(f"no_match: {len(no_match_pn)} → {no_match_pn[:10]}")
    print(f"partial: {len(partial_pn)} → {partial_pn[:10]}")
    print(f"glm_error: {len(glm_err)} → {glm_err[:5]}")


if __name__ == "__main__":
    main()
