#!/usr/bin/env python3
"""
semantic_highlight_workflow.py — 真正的 semantic matching pipeline

设计原则 (user feedback 2026-08-11):
- 先推理 PPT slide 的视觉语义 (sensenova 看 slide 抽 data_points/keywords)
- 然后用 sensenova 同时看 PPT slide + PDF page, 找语义对应的段落/图片/图标
- 直接用 sensenova 返回的 bbox 画黄线, **不用文本搜索** (避免 keyword 误匹配)

与 vision_highlight_workflow.py 的区别:
- stage 2 prompt 让 sensenova 同时看 PPT + PDF, 给 semantic bbox
- stage 3 直接在 PDF bbox 上画线, 不调 process_pn_x (无 text search)
- 多线程 + 缓存
"""
import os, sys, json, time, re, threading, queue
from pathlib import Path
from typing import Dict, List, Optional
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fitz
fitz.TOOLS.mupdf_display_warnings(False)

from provider_vision import vision_analyze, get_api_key, encode_image, get_image_mime


TMA_ROOT = "/Users/david/Desktop/TMA_文献整理"
LEIDA_ROOT = "/Users/david/Desktop/雷管方案_文献整理"
RENDER_ZOOM = 1.5  # 渲染 PDF 时放大 1.5x (与 sensenova 看图一致)
THREAD_WORKERS = 4  # sensenova 并发数


# === sensenova 统一调用 ===
import hashlib

_sensenova_cache = {}
_cache_path = "/tmp/_sensenova_cache.json"


def _cache_key(image_paths, prompt):
    """生成 cache key: 图像 paths + prompt hash"""
    img_part = "|".join(sorted(image_paths))
    prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:16]
    img_hash = hashlib.md5(img_part.encode()).hexdigest()[:16]
    return f"{prompt_hash}_{img_hash}"


def _load_cache():
    global _sensenova_cache
    if not _sensenova_cache and os.path.isfile(_cache_path):
        try:
            with open(_cache_path) as f:
                _sensenova_cache = json.load(f)
        except Exception:
            _sensenova_cache = {}
    return _sensenova_cache


def _save_cache():
    try:
        with open(_cache_path, "w") as f:
            json.dump(_sensenova_cache, f, ensure_ascii=False)
    except Exception:
        pass


def sensenova_call(image_paths, prompt, json_mode=True, timeout=30):
    """支持单图或多图. 加 cache 保证 consistency."""
    if isinstance(image_paths, str):
        image_paths = [image_paths]
    cache = _load_cache()
    key = _cache_key(image_paths, prompt)
    if key in cache:
        return cache[key]

    api_key = get_api_key()
    if not api_key:
        return ""
    content = [{"type": "text", "text": prompt}]
    for p in image_paths:
        if not os.path.isfile(p):
            continue
        b64 = encode_image(p)
        mime = get_image_mime(p)
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    messages = [{"role": "user", "content": content}]
    data = {
        "model": "sensenova-6.7-flash-lite",
        "messages": messages,
        "temperature": 0.05,  # 更低温度, 更稳定
    }
    if json_mode:
        data["response_format"] = {"type": "json_object"}
    import urllib.request
    req = urllib.request.Request(
        "https://token.sensenova.cn/v1/chat/completions",
        data=json.dumps(data).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            result = json.loads(r.read().decode())
        content_str = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        cache[key] = content_str
        _save_cache()
        return content_str
    except Exception as e:
        return ""


def _parse_json_loose(text: str) -> Optional[dict]:
    if not text:
        return None
    # 先去 markdown code block 包装
    text_clean = re.sub(r'^```(?:json)?\s*\n?', '', text.strip(), flags=re.MULTILINE)
    text_clean = re.sub(r'\n?```\s*$', '', text_clean, flags=re.MULTILINE).strip()
    try:
        return json.loads(text_clean)
    except Exception:
        pass
    # 找最外层 {...}
    m = re.search(r'\{[\s\S]*\}', text_clean)
    if m:
        # 找 balanced {}
        depth = 0
        start = m.start()
        for i in range(start, len(text_clean)):
            if text_clean[i] == '{':
                depth += 1
            elif text_clean[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text_clean[start:i+1])
                    except Exception:
                        pass
                    break
    return None


# === 渲染 PDF 页为 jpg ===
def render_pdf_page(doc, page_idx, out_path, zoom=RENDER_ZOOM):
    page = doc[page_idx]
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    pix.save(out_path)


# === Stage 2: Semantic PDF Search (新版本) ===
def stage2_semantic_search(plan: Dict, ppt_render_path: str,
                            max_pages: int = 4, vision_timeout: int = 30) -> List[Dict]:
    """
    对每个 plan, 用 sensenova 同时看 PPT slide + 1 个 PDF 页面, 找语义对应的 bbox
    每次 query 1 页 (sensenova 单次 query 解析 per_page 不可靠)

    Returns: [{page, bbox_pdf, bbox_image, semantic_match, content_type, confidence}]
    """
    pdf_path = plan.get("pdf_path")
    if not pdf_path or not os.path.isfile(pdf_path):
        return []

    target = plan.get("target_text", "")
    data_points = plan.get("data_points", [])
    keywords = plan.get("keywords", [])

    if not target and not data_points:
        return []

    # 渲染 PDF 前 N 页
    doc = fitz.open(pdf_path)
    n_pages = min(max_pages, doc.page_count)
    matches = []

    # 准备临时文件 (加 process id 避免多线程 race)
    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix=f"_semantic_{plan['pn_x']}_{os.getpid()}_")

    for p in range(n_pages):
        pdf_img = os.path.join(tmp_dir, f"page_{p}.png")
        render_pdf_page(doc, p, pdf_img, RENDER_ZOOM)
        from PIL import Image
        img = Image.open(pdf_img)
        max_dim = 1500
        if max(img.size) > max_dim:
            ratio = max_dim / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img.thumbnail(new_size, Image.LANCZOS)
            img.save(pdf_img)
            actual_zoom = RENDER_ZOOM * ratio
        else:
            actual_zoom = RENDER_ZOOM

        prompt = f"""你是医学/生物学文献**视觉语义匹配**专家。

【任务】
PPT 引用标号 {plan.get('mark', '?')} 在 PPT 上的内容是: "{target}"
关键数据: {data_points}
关键词: {keywords}

提供 2 张图:
- 图 1: PPT slide 渲染图 (标号 {plan.get('mark', '?')} 在哪)
- 图 2: PDF 第 {p+1} 页渲染图 (宽高 {img.size[0]}x{img.size[1]})

请**只**在图 2 (PDF 第 {p+1} 页) 中找与 PPT 标号 {plan.get('mark', '?')} 语义对应的内容 (段落/图/表)。

⚠️ 是找 PDF (图 2) 里的内容, 不是 PPT (图 1) 里的.

**严格禁止高亮以下区域** (你必须用 content_type 标识, 不返回 bbox):
- "title" / "article_title" / "section_title" - 文章标题 / 章节标题
- "author" / "authors" / "affiliation" - 作者名 / 单位 / 通信作者
- "reference" / "references" / "bibliography" / "cited" - PDF 末尾的文献引用列表
- "header" / "footer" / "running_head" / "journal_info" - 页眉页脚 (期刊名/卷号/页码)
- "acknowledgment" / "acknowledgements" - 致谢

如果图 2 包含与 PPT 标号语义对应的 body 段落, 给出:
1. found: true
2. matches: 列表, 每个元素:
   {{
     "bbox": [x1, y1, x2, y2],          // 像素坐标 (在图 2 上), 覆盖完整匹配区域
     "content_type": "paragraph" (段落/正文) | "figure" (图) | "table" (表) | "image" (图) | "icon" (图标),
     "semantic_description": "该区域讲什么 (1 句)",
     "relevance": "该区域与 PPT 标号的关系 (1 句)"
   }}
3. overall_confidence: 0.0-1.0

如果图 2 没有 body 段落与 PPT 标号语义对应 (或所有匹配都在禁止区域), 给出:
{{
  "found": false,
  "reason": "图 2 (PDF 第 {p+1} 页) 没有 body 段落与 PPT 标号语义对应"
}}

请严格用 JSON 输出:
{{
  "found": true/false,
  "matches": [...],
  "overall_confidence": 0.0-1.0,
  "reason": "..."
}}"""

        try:
            result = sensenova_call(
                [ppt_render_path, pdf_img],
                prompt,
                json_mode=True,
                timeout=vision_timeout,
            )
            if not result:
                continue
            parsed = _parse_json_loose(result)
            if not parsed or not parsed.get("found"):
                continue
            for m in parsed.get("matches", []):
                bbox_img = m.get("bbox", [])
                if not bbox_img or len(bbox_img) != 4:
                    continue
                bbox_pdf = [
                    bbox_img[0] / actual_zoom,
                    bbox_img[1] / actual_zoom,
                    bbox_img[2] / actual_zoom,
                    bbox_img[3] / actual_zoom,
                ]
                matches.append({
                    "page": p,
                    "bbox_pdf": bbox_pdf,
                    "bbox_image": bbox_img,
                    "content_type": m.get("content_type", "paragraph"),
                    "semantic_description": m.get("semantic_description", ""),
                    "relevance": m.get("relevance", ""),
                    "confidence": parsed.get("overall_confidence", 0.5),
                })
        except Exception as e:
            print(f"  ⚠ sensenova page {p} err: {e}")
            continue

    doc.close()
    try:
        for f in os.listdir(tmp_dir):
            try:
                os.remove(os.path.join(tmp_dir, f))
            except Exception:
                pass
        os.rmdir(tmp_dir)
    except Exception:
        pass

    return matches


# === Stage 3: Highlight using bbox (v1.4 - 实际修复版) ===

# 禁高亮区 (sensenova 自标 + 几何 + 文字特征 三重判断)
FORBIDDEN_CONTENT_TYPES = {
    "title", "article_title", "section_title",  # 标题
    "author", "authors", "affiliation", "correspondence",  # 作者
    "reference", "references", "bibliography", "cited", "literature_cited",  # 引用
    "header", "footer", "running_head", "journal_info",  # 页眉页脚
    "acknowledgment", "acknowledgements",  # 致谢
}

# 段落类 (用下划线 - PDF 原生 UNDERLINE 注释, 不遮字)
PARAGRAPH_TYPES = {"paragraph", "body", "text", "section", "subsection"}
# 图表类 (用黄线框)
FIGURE_TYPES = {"figure", "image", "diagram", "chart", "table", "icon", "graph", "illustration"}


# Author/affiliation 文字特征 (sensenova 永远不标这些, 必须自己判断)
_AUTHOR_TEXT_PATTERNS = [
    r"M\.?D\.?", r"Ph\.?D\.?", r"Professor", r"Departments?\s+of\b", r"Department\s+of\b",
    r"University\s+of\b", r"Medical\s+Center", r"College\s+of\b", r"Hospital\b",
    r"Institute\s+of\b", r"^Correspondence", r"\*Correspondence", r"@[\w.]+\.[a-z]{2,}",  # email
    r"et\s+al\.?$", r"^\d+[\s,]+[A-Z][a-z]+\s+[A-Z]",  # 多个 "M.D.," 紧邻
    r"^From\s+the\b", r"^Affiliations?\b", r"^Author\s+contributions", r"^Authors?\b",
]
# Reference 文字特征
_REFERENCE_TEXT_PATTERNS = [
    r"^\d+\.\s+[A-Z]", r"^\[\d+\]",  # "1. Smith" or "[1]"
    r"doi:\s*10\.\d+", r"^References\b", r"^REFERENCES\b", r"^Bibliography\b",
    r"vol\.\s*\d+", r"^N\s+Engl\s+J\s+Med", r"^Frontiers\b", r"^Lancet\b",
    r"\d{4}\s*;\s*\d+",  # 2020; 1234 期刊格式
]
# Header/footer 文字特征
_HEADER_FOOTER_PATTERNS = [
    r"^Vol\.?\s+\d+", r"^N\s+Engl\s+J\s+Med", r"^Page\s+\d+", r"^www\.",
    r"^Downloaded\s+from", r"^Copyright\s", r"^©",
]
# Declaration / competing interests 文字特征 (不应 highlight)
_DECLARATION_PATTERNS = [
    r"^Competing\s+interests", r"^Declaration\s+of\s+(competing\s+)?interests",
    r"^Conflicts?\s+of\s+interest", r"^Funding", r"^Funding\s+statement",
    r"^Author\s+contributions", r"^Authors'\s+contributions",
    r"^Data\s+availability", r"^Data\s+availability\s+statement",
    r"^Additional\s+information", r"^Supplementary\s+",
    r"^Ethics\s+(approval|statement|consent)",
    r"^Patient\s+consent", r"^Informed\s+consent",
]


def _is_forbidden_text(text: str, content_type: str, page_idx: int, page_rect) -> tuple:
    """
    三重判断是否禁高亮区:
    1. sensenova 标的 content_type
    2. 几何 (page 0 top 22% / any page bottom 8% / any page top 5%)
    3. 文字特征 (author/affiliation/reference/header 模式)
    返回: (is_forbidden, reason)
    """
    page_h = page_rect.height
    page_w = page_rect.width

    # 1. sensenova 标的 content_type
    if content_type in FORBIDDEN_CONTENT_TYPES:
        return True, f"sensenova_type={content_type}"

    # 2. 几何判断
    # 从 m 抽 bbox 在 stage3 调, 这里不传, 用 text 判
    # 实际 stage3_highlight_bbox 会先调 _is_geometry_forbidden
    # 这里只判断 text 特征

    # 3. 文字特征 - author/affiliation
    if text:
        # author 多 M.D./Ph.D. 或 Department of / University of / email
        import re
        md_count = sum(1 for p in _AUTHOR_TEXT_PATTERNS if re.search(p, text, re.MULTILINE))
        # author 区典型: "X, M.D., Y, Ph.D., and Z, M.D." 或 "Department of..."
        if md_count >= 2:
            return True, f"text_pattern=author_pattern_hits_{md_count}"
        # email 在 text 里基本 100% 是 author/affiliation
        if re.search(r"@[\w.]+\.[a-z]{2,}", text):
            return True, "text_pattern=email"
        # "Department of" / "University of" / "From the Department" 多次出现
        if re.search(r"Department\s+of\s+[A-Z]", text) and re.search(r"University\s+of\s+[A-Z]", text):
            return True, "text_pattern=affiliation_keywords"
        # "Correspondence" / "Affiliations"
        if re.search(r"^\s*\*?Correspondence\b", text, re.MULTILINE):
            return True, "text_pattern=correspondence_header"

        # Reference 文字特征
        ref_count = sum(1 for p in _REFERENCE_TEXT_PATTERNS if re.search(p, text, re.MULTILINE))
        # 参考文典型: "1. Smith J, et al. Nature. 2020; 123: 45-50." 或 "[1] ..."
        # 多个 [n] 引用格式
        bracket_refs = len(re.findall(r"\[\d+\]", text))
        if bracket_refs >= 3:
            return True, f"text_pattern=bracket_refs_{bracket_refs}"
        if re.search(r"^References\s*$", text, re.MULTILINE | re.IGNORECASE):
            return True, "text_pattern=references_header"
        # doi + journal 格式
        if re.search(r"doi:\s*10\.\d+", text, re.IGNORECASE) and re.search(r"\d{4}\s*;\s*\d+", text):
            return True, "text_pattern=doi_journal_format"

        # Declaration / Competing interests / Funding / Author contributions 段
        for p in _DECLARATION_PATTERNS:
            if re.search(p, text, re.MULTILINE | re.IGNORECASE):
                return True, f"text_pattern=declaration_{p[:20]}"

        # Header/footer 文字特征
        # page header 典型: "N Engl J Med" / "Vol. 344" / "www.nejm.org"
        if re.search(r"^N\s+Engl\s+J\s+Med\b", text) or re.search(r"^www\.\w+\.\w+", text, re.MULTILINE):
            return True, "text_pattern=journal_header"
        if re.search(r"^Downloaded\s+from\s+\w+\.\w+", text, re.MULTILINE):
            return True, "text_pattern=downloaded_from"

    return False, ""


def _is_geometry_forbidden(x1, y1, x2, y2, page_idx, page_rect) -> tuple:
    """几何判断禁高亮区 (sensenova 不可靠, 必须自己判断)"""
    page_h = page_rect.height
    page_w = page_rect.width

    # 1. page bottom 8% = footer
    if y1 > page_h * 0.92:
        return True, "geometry=page_bottom_8%"

    # 2. page top 5% (任何页) = page header
    if y2 < page_h * 0.05:
        return True, "geometry=page_top_5%"

    # 3. page 0 top 22% = title/author/affiliation 区
    if page_idx == 0 and y2 < page_h * 0.22:
        return True, "geometry=page0_top_22%"

    # 4. bbox 跨整页 (太宽+太高) = 几乎肯定是 sensenova 瞎圈
    width_ratio = (x2 - x1) / page_w
    height_ratio = (y2 - y1) / page_h
    if width_ratio > 0.7 and height_ratio > 0.3:
        return True, f"geometry=too_large_{width_ratio:.0%}x{height_ratio:.0%}"

    # 5. bbox 覆盖 page 一半以上 height (单独) - 也太大
    if height_ratio > 0.5:
        return True, f"geometry=height_too_large_{height_ratio:.0%}"

    return False, ""


def stage3_highlight_bbox(plan: Dict, matches: List[Dict], out_path: str,
                          mode: str = "line") -> Dict:
    """
    v1.4 严格版:
    - 段落下划线: page.add_underline_annot(rect) (PDF 原生, 仅 baseline 画线, 不遮字)
    - 图表黄线框: page.draw_rect(rect, stroke=yellow, width=2) (无 fill)
    - 禁高亮区: sensenova content_type + 几何 + 文字特征 三重判断
    - bbox 大小 sanity check (太宽+太高 → 拒)
    - confidence ≥ 0.7

    位置 0 偏移: add_underline_annot 自动用 PDF 文字 baseline 定位.
    """
    if not matches:
        return {"ok": False, "reason": "no_matches"}

    # 提严 confidence 阈值
    matches = [m for m in matches if m.get("confidence", 0) >= 0.7]
    if not matches:
        return {"ok": False, "reason": "all_low_confidence_lt_0.7"}

    pdf_path = plan["pdf_path"]
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        return {"ok": False, "reason": f"open_err: {e}"}

    total_pages = doc.page_count
    highlight_count = 0
    filtered_count = 0
    demoted_count = 0
    filter_reasons = []
    processed_bboxes = []

    for m in matches:
        page_idx = m.get("page", 0)
        if page_idx >= total_pages:
            continue
        bbox = m.get("bbox_pdf", [])
        if not bbox or len(bbox) != 4:
            continue
        x1, y1, x2, y2 = bbox
        if x1 >= x2 or y1 >= y2:
            continue
        page = doc[page_idx]
        page_rect = page.rect
        # 裁剪到页面范围
        x1 = max(0, min(x1, page_rect.x1))
        x2 = max(0, min(x2, page_rect.x1))
        y1 = max(0, min(y1, page_rect.y1))
        y2 = max(0, min(y2, page_rect.y1))
        if x1 >= x2 or y1 >= y2:
            continue

        # 去重
        bbox_key = (page_idx, round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1))
        if bbox_key in processed_bboxes:
            continue
        processed_bboxes.append(bbox_key)

        content_type = m.get("content_type", "paragraph").lower()

        # === 禁高亮区判断 (三重) ===
        # 1. 几何 (sensenova 不可靠, 必须自己判断)
        geo_forbid, geo_reason = _is_geometry_forbidden(x1, y1, x2, y2, page_idx, page_rect)
        if geo_forbid:
            filtered_count += 1
            filter_reasons.append(f"p{page_idx} {geo_reason}")
            continue

        # 2. sensenova 标 content_type
        if content_type in FORBIDDEN_CONTENT_TYPES:
            filtered_count += 1
            filter_reasons.append(f"p{page_idx} type={content_type}")
            continue

        # 3. 文字特征 (抽 bbox 内文字)
        rect = fitz.Rect(x1, y1, x2, y2)
        try:
            text_in_bbox = page.get_text("text", clip=rect).strip()
        except Exception:
            text_in_bbox = ""

        text_forbid, text_reason = _is_forbidden_text(text_in_bbox, content_type, page_idx, page_rect)
        if text_forbid:
            filtered_count += 1
            filter_reasons.append(f"p{page_idx} {text_reason}")
            continue

        # === bbox 内文字 sanity (防 sensenova 标 figure 实际是段落) ===
        if content_type in FIGURE_TYPES:
            if len(text_in_bbox) > 80:  # >80 chars 几乎肯定是正文
                content_type = "paragraph"
                demoted_count += 1
                filter_reasons.append(f"p{page_idx} demoted figure→paragraph ({len(text_in_bbox)} chars)")

        # === 画高亮 ===
        try:
            if content_type in FIGURE_TYPES:
                # 图表: 黄色边框, 无 fill, 2pt 粗
                page.draw_rect(
                    rect,
                    color=(1, 1, 0),
                    fill=None,
                    width=2,
                    overlay=True,
                )
                highlight_count += 1
            else:
                # 段落: PDF 原生下划线 (UNDERLINE 注释, 只在文字 baseline 画线, 不遮字)
                annot = page.add_underline_annot(rect)
                if annot:
                    annot.set_colors(stroke=(1, 1, 0))  # 黄色
                    annot.update()
                    highlight_count += 1
                else:
                    # fallback: draw_line under text
                    line_y = y2 + 0.5
                    page.draw_line(
                        fitz.Point(x1, line_y),
                        fitz.Point(x2, line_y),
                        color=(1, 1, 0),
                        width=1.2,
                        overlay=True,
                    )
                    highlight_count += 1
        except Exception as e:
            print(f"  ⚠ draw err on page {page_idx}: {e}")
            continue

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    try:
        doc.save(out_path, garbage=4, deflate=True)
    except Exception as e:
        return {"ok": False, "reason": f"save_err: {e}"}
    finally:
        doc.close()

    if highlight_count == 0 and filtered_count > 0:
        reason = f"all_{filtered_count}_matches_in_forbidden_zones"
    else:
        reason = ""

    return {
        "ok": highlight_count > 0,
        "highlight_count": highlight_count,
        "filtered_count": filtered_count,
        "demoted_count": demoted_count,
        "method": "semantic_bbox_v14_underline_strict",
        "matches_used": len(matches),
        "filter_reasons": filter_reasons[:8],
        "reason": reason,
    }


# === Main pipeline ===
def find_pdf(project_root, pn_x):
    """找 Pn-x 的 main PDF (flat + nested)"""
    for d in [os.path.join(project_root, "_2_pdfs"),
              os.path.join(project_root, "step3_pdf下载_160目录")]:
        flat = os.path.join(d, f"{pn_x}_main.pdf")
        if os.path.isfile(flat):
            return flat
        nested = os.path.join(d, pn_x, f"{pn_x}_main.pdf")
        if os.path.isfile(nested):
            return nested
    return None


def find_ppt_renders(project_root, slide_num):
    """找 PPT slide 渲染图 (多个候选)"""
    candidates = [
        os.path.join(project_root, "_1_ppt/_3_images", f"slide_pp_{slide_num:03d}.jpg"),
        os.path.join(project_root, "_1_ppt/_3_images", f"slide_{slide_num:03d}.jpg"),
        os.path.join(project_root, "step1_ppt_目录/_ppt_renders_expanded", f"slide_{slide_num:03d}.jpg"),
        os.path.join(project_root, "step1_ppt_目录/_ppt_renders", f"slide_{slide_num:03d}.jpg"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def _process_one(plan, project_root, out_dir, mode, idx, total):
    """纯 semantic matching. 禁止 keyword 兜底. 禁止高亮 title/author/reference.
    v1.4.1: 在 stage 2 之前注入 PDF 摘要反向抽英文 keyword (TMA 4 轮验证 +33x hit 率)
    """
    pn_x = plan.get("pn_x")
    slide = plan.get("slide")
    # 找 PDF
    if not plan.get("pdf_path") or not os.path.isfile(plan["pdf_path"]):
        pdf = find_pdf(project_root, pn_x)
        if pdf:
            plan["pdf_path"] = pdf
    # 找 PPT render
    ppt_render = find_ppt_renders(project_root, slide)
    if not ppt_render:
        return {"pn_x": pn_x, "ok": False, "reason": "no_ppt_render"}

    # === v1.4.1: 注入 PDF 摘要反向抽英文 keyword (TMA 4 轮验证) ===
    # 复用 vision_stage3_keyword_boost._extract_keywords_from_pdf
    if plan.get("pdf_path") and os.path.isfile(plan["pdf_path"]):
        try:
            from vision_stage3_keyword_boost import _extract_keywords_from_pdf
            pdf_kw = _extract_keywords_from_pdf(plan["pdf_path"])
            if pdf_kw:
                # PDF keyword 优先 (前置, 优先被 sensenova 看到)
                existing_kw = plan.get("keywords", []) or []
                # 合并去重, PDF 关键词在前
                merged = list(dict.fromkeys(pdf_kw + existing_kw))[:30]
                plan["keywords"] = merged
        except Exception as e:
            print(f"  ⚠ kw inject err {pn_x}: {e}", flush=True)

    # Stage 2: semantic search (sensenova vision) - 纯语义, 不 fallback
    print(f"  [{idx}/{total}] {pn_x}: stage 2 (sensenova vision)...", flush=True)
    matches = stage2_semantic_search(plan, ppt_render, max_pages=8, vision_timeout=30)
    method = "semantic_bbox_v141"

    if not matches:
        return {"pn_x": pn_x, "ok": False, "reason": "no_semantic_match", "matches": 0, "method": method}

    # Stage 3: bbox highlight (filter title/author/reference)
    out_pdf = os.path.join(out_dir, f"{pn_x}_semantic_highlight.pdf")
    result = stage3_highlight_bbox(plan, matches, out_pdf, mode=mode)
    print(f"    → matches={len(matches)}, highlight_count={result.get('highlight_count', 0)}, ok={result.get('ok')}")
    result["pn_x"] = pn_x
    result["matches"] = len(matches)
    result["method"] = method
    return result


def run_project(project_root, plans, out_dir, max_plans=0, mode="line", workers=4):
    """对每个 plan 跑 stage 2 + 3 (多线程并行)"""
    os.makedirs(out_dir, exist_ok=True)
    plans = plans[:max_plans] if max_plans else plans
    print(f"=== Semantic highlight: {len(plans)} plans, mode={mode}, workers={workers} ===")

    # 过滤有 PDF 和 PPT 的
    valid_plans = []
    for plan in plans:
        pn_x = plan.get("pn_x")
        slide = plan.get("slide")
        if not pn_x or not slide:
            continue
        if not plan.get("pdf_path") or not os.path.isfile(plan["pdf_path"]):
            pdf = find_pdf(project_root, pn_x)
            if pdf:
                plan["pdf_path"] = pdf
        if find_ppt_renders(project_root, slide):
            valid_plans.append(plan)
        else:
            print(f"  skip {pn_x}: no PPT render")

    print(f"Valid plans: {len(valid_plans)}")

    # 多线程
    from concurrent.futures import ThreadPoolExecutor, as_completed
    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_process_one, plan, project_root, out_dir, mode, i, len(valid_plans)): plan
            for i, plan in enumerate(valid_plans, 1)
        }
        for future in as_completed(futures):
            try:
                r = future.result()
                results.append(r)
            except Exception as e:
                plan = futures[future]
                results.append({"pn_x": plan.get("pn_x", "?"), "ok": False, "reason": f"err: {e}"})

    return results


# === Main pipeline ===

    return results


# === CLI ===
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", choices=["TMA", "雷管方案"], default="TMA")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--mode", default="line", choices=["line", "fill", "both"])
    parser.add_argument("--out-dir", default="")
    args = parser.parse_args()

    if args.project == "TMA":
        root = TMA_ROOT
        plans_path = os.path.join(TMA_ROOT, "_3_highlight_vision", "_highlight_plans.json")
        out_dir = args.out_dir or os.path.join(TMA_ROOT, "_3_highlight_semantic")
    else:
        root = LEIDA_ROOT
        plans_path = os.path.join(LEIDA_ROOT, "_3_highlight_vision", "_highlight_plans.json")
        out_dir = args.out_dir or os.path.join(LEIDA_ROOT, "_3_highlight_semantic")

    with open(plans_path) as f:
        d = json.load(f)
    plans = d.get("plans", [])
    print(f"Loaded {len(plans)} plans from {plans_path}")

    if args.limit:
        plans = plans[:args.limit]

    results = run_project(root, plans, out_dir, mode=args.mode, workers=4)

    # Summary
    n_ok = sum(1 for r in results if r.get("ok"))
    print(f"\n=== Summary: {n_ok}/{len(results)} semantic highlights ===")
    out_json = os.path.join(out_dir, "_semantic_summary.json")
    with open(out_json, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Log: {out_json}")


if __name__ == "__main__":
    main()
