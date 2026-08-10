#!/usr/bin/env python3
"""
glm_integration.py — GLM 集成层 (2026-08-10)

包装 /Users/david/.hermes/skills/via54/glm_academic_official.py 的能力,
让 v10.1 highlight / l0 paper match / l4 keyword / step5 alignment
可以无缝调 GLM (默认 glm-4-flash-250414).

能力:
  - verify_paper_match_with_glm()  L0 兜底 (5 维 0.4-0.6 模糊区确认)
  - supplement_keywords_with_glm()  L4 补抽 (本地抽完后 GLM 加医学术语)
  - extract_evidence_for_highlight()  highlight 应证段 (返回页码 + 文本)
  - find_highlight_coordinates()     GLM 应证段 → PDF 坐标
  - semantic_align_step5()           step5 5#3 语义对齐 (PPT 视觉 vs highlight)

所有函数都接受 `use_glm: bool` 参数, 默认 False. True 时调 GLM,
False 时返回 None (让调用方回退到本地算法).

所有函数都接受 `client` 参数, None 时内部 get_glm_client() 创建.

用法:
  from glm_integration import verify_paper_match_with_glm
  result = verify_paper_match_with_glm(
      pdf_path='P11-1.pdf',
      expected_citation='任宏, 等. ...',
      local_score=0.45,  # 本地 5 维评分
      use_glm=True,
  )
  if result and result['confirmed']:
      print("GLM 确认: 论文匹配")
"""
import os, sys, json, re
from pathlib import Path
from typing import Dict, List, Optional

# 加载现有 GLM 模块
GLM_SCRIPTS = Path.home() / ".hermes" / "skills" / "via54"
if str(GLM_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(GLM_SCRIPTS))

# 默认模型
DEFAULT_MODEL = "glm-4-flash-250414"


def _get_client():
    """懒加载 GLM client (避免无谓启动)"""
    from glm_academic_official import get_glm_client
    return get_glm_client()


def _call_glm(client, model: str, prompt: str, max_retries: int = 2) -> Optional[str]:
    """封装 call_glm, 失败返回 None"""
    try:
        from glm_academic_official import call_glm
        result = call_glm(client, model, prompt, prompt, max_retries=max_retries)
        # call_glm 返回 parsed dict, 提取 content
        if isinstance(result, dict):
            return result.get("content", str(result))
        return str(result)
    except Exception as e:
        return None


# ════════════════════════════════════════════════════════════════
# L0 兜底: 论文匹配确认
# ════════════════════════════════════════════════════════════════

L0_VERIFY_PROMPT = """# 任务
你是医学文献审计专家。判断 PDF 是否与给定引用匹配。

# 引用期望
{citation}

# PDF 首 3 页文本
{pdf_text}

# 输出 (严格 JSON, 不含多余文字)
{{
  "matches": true/false,
  "confidence": 0.0-1.0,
  "reason_zh": "匹配/不匹配原因 (中文 1-2 句)",
  "key_match": "作者姓 / 期刊 / 年份 / DOI 哪个最匹配 (或都不匹配)"
}}"""


def verify_paper_match_with_glm(
    pdf_path: str,
    expected_citation: str,
    local_score: float = 0.5,
    use_glm: bool = False,
    client=None,
    model: str = DEFAULT_MODEL,
) -> Optional[Dict]:
    """
    L0 兜底: 本地 5 维评分模糊 (0.4-0.6) 时, 用 GLM 确认

    Args:
        pdf_path: PDF 路径
        expected_citation: D 列引文
        local_score: 本地 5 维评分
        use_glm: True 才调 GLM, False 直接返回 None
        client: GLM client (None 时内部创建)
        model: 模型名

    Returns:
        {
            'confirmed': bool,    # GLM 是否确认匹配
            'confidence': float,    # GLM 评分
            'reason_zh': str,       # 原因
            'key_match': str,        # 最匹配的特征
            'glm_called': bool,
        }
        None = use_glm=False 或调用失败
    """
    if not use_glm:
        return None

    # 只在模糊区调 GLM (省 token)
    if not (0.3 <= local_score <= 0.7):
        return None

    # 抽 PDF 文本
    try:
        import fitz
        doc = fitz.open(pdf_path)
        text = ""
        for i in range(min(3, len(doc))):
            text += doc[i].get_text() + "\n"
        doc.close()
        # 截 2000 字防超长
        text = text[:2000]
    except Exception:
        return None

    if client is None:
        try:
            client = _get_client()
        except Exception:
            return None

    prompt = L0_VERIFY_PROMPT.format(
        citation=expected_citation[:500],
        pdf_text=text,
    )
    response = _call_glm(client, model, prompt, max_retries=2)
    if not response:
        return None

    # 解析 JSON (response 可能是 markdown 包着的)
    try:
        m = re.search(r'\{[\s\S]*?\}', response)
        if not m:
            return None
        data = json.loads(m.group(0))
    except Exception:
        return None

    return {
        "confirmed": bool(data.get("matches")),
        "confidence": float(data.get("confidence", 0.0)),
        "reason_zh": data.get("reason_zh", ""),
        "key_match": data.get("key_match", ""),
        "glm_called": True,
    }


# ════════════════════════════════════════════════════════════════
# L4 补抽: 关键医学术语
# ════════════════════════════════════════════════════════════════

L4_SUPPLEMENT_PROMPT = """# 任务
你是医学文献关键词专家。给定 D 列引文 + 视觉分析, 补抽 5-10 个
**最可能在 PDF 正文出现**的关键词 (避免通用词如 '方法' '结果' '2020')。

# D 列引文
{citation}

# D 列视觉分析
{visual}

# 已知关键词 (不要再列)
{existing}

# 输出 (严格 JSON 列表, 不含多余文字)
{{"keywords": ["关键词1", "关键词2", "关键词3"]}}"""


def supplement_keywords_with_glm(
    citation: str,
    visual_context: str = "",
    existing_kws: List[str] = None,
    use_glm: bool = False,
    client=None,
    model: str = DEFAULT_MODEL,
) -> List[str]:
    """
    L4 补抽: GLM 在本地抽完后补充更精准的医学术语

    Returns: 额外关键词列表 (空表示未调 GLM 或失败)
    """
    if not use_glm:
        return []

    if client is None:
        try:
            client = _get_client()
        except Exception:
            return []

    existing = existing_kws or []
    prompt = L4_SUPPLEMENT_PROMPT.format(
        citation=citation[:500],
        visual=visual_context[:500],
        existing="、".join(existing) or "(无)",
    )
    response = _call_glm(client, model, prompt, max_retries=2)
    if not response:
        return []

    try:
        m = re.search(r'\{[\s\S]*?\}', response)
        if not m:
            return []
        data = json.loads(m.group(0))
        kws = data.get("keywords", [])
        # 过滤已有的
        return [k for k in kws if k and k not in existing_kws]
    except Exception:
        return []


# ════════════════════════════════════════════════════════════════
# Highlight 应证段提取
# ════════════════════════════════════════════════════════════════

HL_EXTRACT_PROMPT = """# 任务
你是医学文献应证段提取专家。从 PDF 中找出能应证 "{citation}" 引用的
**应证段 (具体段落/数据/图表说明)**, 并给出**页码**。

# D 列引文 (PPT 想引用的内容)
{citation}

# D 列视觉分析 (PPT 上的具体引用点)
{visual}

# PDF 全文 (按页分割)
{pdf_pages}

# 输出 (严格 JSON 列表, 每段一页)
{{"evidence": [
  {{"page": 页码 (1-based int), "text": "应证段原文 (中文优先, 截 200 字内)", "type": "text/table/figure"}}
]}}"""


def extract_evidence_for_highlight(
    pdf_path: str,
    citation: str,
    visual_context: str = "",
    use_glm: bool = False,
    client=None,
    model: str = DEFAULT_MODEL,
    max_pages: int = 15,
) -> List[Dict]:
    """
    用 GLM 提取应证段 (返回 [{page, text, type}])

    Args:
        pdf_path: PDF 路径
        citation: D 列引文
        visual_context: D 列视觉分析
        use_glm: True 才调 GLM
        max_pages: 最多扫几页 (避免 token 爆炸)

    Returns:
        [{'page': 3, 'text': '...', 'type': 'text'}, ...]
        空 = 未调 GLM 或失败
    """
    if not use_glm:
        return []

    if client is None:
        try:
            client = _get_client()
        except Exception:
            return []

    # 抽 PDF 文本
    try:
        import fitz
        doc = fitz.open(pdf_path)
        pages_text = []
        for i in range(min(max_pages, len(doc))):
            try:
                t = doc[i].get_text()
                # 截 500 字 / 页 (总共 7.5K 字符)
                pages_text.append(f"--- Page {i+1} ---\n{t[:500]}")
            except Exception:
                pass
        doc.close()
    except Exception:
        return []

    prompt = HL_EXTRACT_PROMPT.format(
        citation=citation[:300],
        visual=visual_context[:300] or "(无)",
        pdf_pages="\n\n".join(pages_text),
    )
    response = _call_glm(client, model, prompt, max_retries=2)
    if not response:
        return []

    try:
        m = re.search(r'\{[\s\S]+\}', response)
        if not m:
            return []
        data = json.loads(m.group(0))
        ev = data.get("evidence", [])
        # 验证 page 范围
        result = []
        for e in ev:
            if isinstance(e, dict) and "page" in e and "text" in e:
                p = int(e["page"])
                if 1 <= p <= max_pages + 5:  # 容差
                    result.append({
                        "page": p,
                        "text": str(e["text"])[:500],
                        "type": e.get("type", "text"),
                    })
        return result
    except Exception:
        return []


# ════════════════════════════════════════════════════════════════
# Highlight 应证段 → PDF 坐标
# ════════════════════════════════════════════════════════════════

def find_text_in_pdf_page(
    pdf_path: str,
    page_num: int,
    text_to_find: str,
    fuzzy: bool = True,
) -> List[Dict]:
    """
    在 PDF 指定页找 text_to_find, 返回 [{bbox: [x0,y0,x1,y1]}]
    用 PyMuPDF search_for + fuzzy 匹配
    """
    try:
        import fitz
        doc = fitz.open(pdf_path)
        if page_num > len(doc):
            doc.close()
            return []
        page = doc[page_num - 1]

        # 1. 精确 search_for
        rects = page.search_for(text_to_find[:80])

        # 2. Fuzzy: 拆词匹配 (e.g. 16.9% 找不到就找 16.9)
        if not rects and fuzzy:
            for fallback in [text_to_find[:30], text_to_find.split()[0] if text_to_find.split() else text_to_find]:
                if fallback and fallback != text_to_find:
                    rects = page.search_for(fallback)

        # 3. 拆字符
        if not rects and fuzzy and len(text_to_find) > 4:
            # 拆中文字符单独找
            for ch in text_to_find[:20]:
                if '\u4e00' <= ch <= '\u9fff':
                    rs = page.search_for(ch)
                    rects.extend(rs[:3])  # 限制

        # 去重
        seen = set()
        unique = []
        for r in rects:
            key = (round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1))
            if key not in seen:
                seen.add(key)
                unique.append({
                    "bbox": [r.x0, r.y0, r.x1, r.y1],
                })
        doc.close()
        return unique
    except Exception:
        return []


def find_highlight_coordinates(
    pdf_path: str,
    evidence_list: List[Dict],
) -> List[Dict]:
    """
    把 GLM 应证段 → PDF 实际坐标 (用 search_for)

    Args:
        pdf_path: PDF 路径
        evidence_list: extract_evidence_for_highlight() 返回

    Returns:
        [{'page': 3, 'bbox': [x0,y0,x1,y1], 'text': '...', 'type': 'text'}]
    """
    results = []
    for ev in evidence_list:
        page = ev.get("page")
        text = ev.get("text", "")
        if not page or not text:
            continue
        rects = find_text_in_pdf_page(pdf_path, page, text, fuzzy=True)
        for r in rects:
            results.append({
                "page": page,
                "bbox": r["bbox"],
                "text": text[:80],
                "type": ev.get("type", "text"),
            })
    return results


# ════════════════════════════════════════════════════════════════
# Step 5 语义对齐
# ════════════════════════════════════════════════════════════════

S5_ALIGN_PROMPT = """# 任务
你是医学文献对齐专家。判断 PPT slide 视觉内容 vs PDF highlight 是否真的应证。

# PPT slide 视觉内容 (D 列)
{visual}

# PDF highlight 内容 (GLM 提取的应证段)
{highlight_text}

# 输出 (严格 JSON)
{{
  "aligns": true/false,
  "confidence": 0.0-1.0,
  "reason_zh": "是否对齐 (中文 1-2 句)",
  "key_concept": "最对齐的概念 (1 个)"
}}"""


def semantic_align_step5(
    visual_context: str,
    highlight_text: str,
    use_glm: bool = False,
    client=None,
    model: str = DEFAULT_MODEL,
) -> Optional[Dict]:
    """
    Step 5 5#3 语义对齐 (PPT 视觉 vs highlight)
    Returns: {'aligns': bool, 'confidence': float, 'reason_zh': str} or None
    """
    if not use_glm:
        return None
    if client is None:
        try:
            client = _get_client()
        except Exception:
            return None

    prompt = S5_ALIGN_PROMPT.format(
        visual=visual_context[:500],
        highlight_text=highlight_text[:500],
    )
    response = _call_glm(client, model, prompt, max_retries=2)
    if not response:
        return None
    try:
        m = re.search(r'\{[\s\S]*?\}', response)
        if not m:
            return None
        data = json.loads(m.group(0))
        return {
            "aligns": bool(data.get("aligns")),
            "confidence": float(data.get("confidence", 0.0)),
            "reason_zh": data.get("reason_zh", ""),
            "key_concept": data.get("key_concept", ""),
        }
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    # verify
    p_v = sub.add_parser("verify", help="L0 论文匹配确认")
    p_v.add_argument("pdf")
    p_v.add_argument("citation")

    # supplement
    p_s = sub.add_parser("supplement", help="L4 补抽关键词")
    p_s.add_argument("citation")
    p_s.add_argument("visual", nargs="?", default="")

    # extract
    p_e = sub.add_parser("extract", help="Highlight 应证段提取")
    p_e.add_argument("pdf")
    p_e.add_argument("citation")
    p_e.add_argument("visual", nargs="?", default="")

    # align
    p_a = sub.add_parser("align", help="Step 5 语义对齐")
    p_a.add_argument("visual")
    p_a.add_argument("highlight_text")

    args = parser.parse_args()

    if args.cmd == "verify":
        result = verify_paper_match_with_glm(args.pdf, args.citation, local_score=0.5, use_glm=True)
        print(json.dumps(result, ensure_ascii=False, indent=2) if result else "FAIL")
    elif args.cmd == "supplement":
        result = supplement_keywords_with_glm(args.citation, args.visual, use_glm=True)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.cmd == "extract":
        evidence = extract_evidence_for_highlight(args.pdf, args.citation, args.visual, use_glm=True)
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
    elif args.cmd == "align":
        result = semantic_align_step5(args.visual, args.highlight_text, use_glm=True)
        print(json.dumps(result, ensure_ascii=False, indent=2) if result else "FAIL")


if __name__ == "__main__":
    main()
