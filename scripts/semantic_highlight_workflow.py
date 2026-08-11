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

from sensenova_vision import vision_analyze, get_api_key, encode_image, get_image_mime


TMA_ROOT = "/Users/david/Desktop/TMA_文献整理"
LEIDA_ROOT = "/Users/david/Desktop/雷管方案_文献整理"
RENDER_ZOOM = 1.5  # 渲染 PDF 时放大 1.5x (与 sensenova 看图一致)
THREAD_WORKERS = 4  # sensenova 并发数


# === sensenova 统一调用 ===
def sensenova_call(image_paths, prompt, json_mode=True, timeout=30):
    """支持单图或多图"""
    if isinstance(image_paths, str):
        image_paths = [image_paths]
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
        "temperature": 0.1,
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
        return result.get("choices", [{}])[0].get("message", {}).get("content", "")
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

    # 准备临时文件
    tmp_dir = f"/tmp/_semantic_{plan['pn_x']}"
    os.makedirs(tmp_dir, exist_ok=True)

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

        prompt = f"""你是医学/生物学文献语义匹配专家。

PPT 引用标号 {plan.get('mark', '?')} 在 PPT 上的内容是: "{target}"
关键数据: {data_points}
关键词: {keywords}

提供 2 张图:
- 图 1: PPT slide 渲染图 (标号 {plan.get('mark', '?')} 在哪)
- 图 2: PDF 第 {p+1} 页渲染图 (宽高 {img.size[0]}x{img.size[1]})

请判断图 2 (PDF 第 {p+1} 页) 是否包含与 PPT 标号 {plan.get('mark', '?')} 语义对应的内容。
"语义对应" 意味着: PDF 段落/图/表 的主题/数据/结论 与 PPT 引用的内容匹配 (即使文字不直接重叠)。

⚠️ 是找 PDF 第 {p+1} 页 (图 2) 里的内容, 不是 PPT (图 1) 里的.

如果图 2 包含, 给出:
1. found: true
2. matches: 列表, 每个元素:
   {{
     "bbox": [x1, y1, x2, y2],          // 像素坐标 (在图 2 上)
     "content_type": "paragraph" / "figure" / "table" / "icon" / "image" / "title" / "author" / "reference" / "header" / "footer",
     "semantic_description": "图 2 该区域讲什么",
     "relevance": "图 2 该区域与 PPT 标号的关系"
   }}
3. overall_confidence: 0.0-1.0

如果图 2 不包含, 给出:
{{
  "found": false,
  "reason": "图 2 未找到与 PPT 标号语义对应的内容"
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
            os.remove(os.path.join(tmp_dir, f))
        os.rmdir(tmp_dir)
    except Exception:
        pass

    return matches


# === Stage 3: Highlight using bbox (新版本) ===
# 禁止高亮的 content_type (per user feedback 2026-08-11)
FORBIDDEN_CONTENT_TYPES = {
    "title",          # 文章标题
    "author",         # 作者信息
    "authors",
    "affiliation",
    "reference",      # PDF 末尾的文献引用部分 (References/Bibliography)
    "references",
    "bibliography",
    "cited",
    "literature",     # Literature cited
    "acknowledgment",  # 致谢
    "header",         # 页眉 (期刊名, 卷号等)
    "footer",         # 页脚
    "running_head",
    "journal_info",   # 期刊信息
}


def _is_reference_or_bibliography_page(page, page_idx: int) -> bool:
    """检测是否是 PDF 的 reference/bibliography 页 (整页都是引用)"""
    try:
        text = page.get_text().lower()
    except Exception:
        return False
    # 关键 reference 信号
    signals = [
        "references", "bibliography", "literature cited",
        "cited literature", "参考文献", "引用文献",
    ]
    for sig in signals:
        if sig in text:
            # 出现信号词 + 后跟大量 [数字] 引用格式, 判定为 reference 页
            if re.search(r'\[\d+\]', text) or re.search(r'\d+\.\s+[A-Z][a-z]+', text):
                return True
    return False


def _is_in_skip_zone(bbox_pdf: List[float], page, content_type: str,
                     page_idx: int, total_pages: int) -> bool:
    """判断 bbox 是否在禁止高亮区域 (title/author/reference/header/footer)"""
    x1, y1, x2, y2 = bbox_pdf
    page_h = page.rect.height
    page_w = page.rect.width

    # 1. sensenova 标了禁止 content_type
    if content_type.lower() in FORBIDDEN_CONTENT_TYPES:
        return True

    # 2. 几何启发: page 0 top 22% 可能是 title+author 区域
    if page_idx == 0 and y1 < page_h * 0.22:
        return True

    # 3. 几何启发: 任何页 bottom 8% 可能是 footer
    if y1 > page_h * 0.92:
        return True

    # 4. 整页都是 reference (page_idx 在末尾 1/3, 文字特征匹配)
    if page_idx >= total_pages - max(2, total_pages // 3):
        if _is_reference_or_bibliography_page(page, page_idx):
            return True

    # 5. bbox 在最底部 30% + 是引用列表特征 (有 [n] 或 n. Author 格式)
    if y1 > page_h * 0.70:
        try:
            text_in_bbox = page.get_text("text", clip=fitz.Rect(x1, y1, x2, y2)).strip()
            # 短文本 (1-2 行) + 引用格式
            if len(text_in_bbox) < 200 and (
                re.search(r'\[\d+\]', text_in_bbox) or
                re.search(r'^\s*\d+\.\s+[A-Z]', text_in_bbox) or
                re.search(r'et al\.', text_in_bbox) or
                re.search(r'\d{4}\)\.|\d{4}\.', text_in_bbox)
            ):
                # 但要排除 normal body 段 (有完整句子)
                if not re.search(r'[a-z]{3,}\s+[a-z]{3,}', text_in_bbox):  # 不是 normal sentence
                    return True
        except Exception:
            pass

    return False


def stage3_highlight_bbox(plan: Dict, matches: List[Dict], out_path: str,
                          mode: str = "line") -> Dict:
    """
    直接用 sensenova 返回的 bbox 画黄线, 不依赖 text search.
    **禁止高亮**: title / author / affiliation / reference / bibliography / header / footer.
    """
    if not matches:
        return {"ok": False, "reason": "no_matches"}

    # 过滤 confidence 太低的
    matches = [m for m in matches if m.get("confidence", 0) >= 0.4]
    if not matches:
        return {"ok": False, "reason": "all_low_confidence"}

    pdf_path = plan["pdf_path"]
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        return {"ok": False, "reason": f"open_err: {e}"}

    total_pages = doc.page_count
    highlight_count = 0
    filtered_count = 0  # 被禁止区域过滤的
    filter_reasons = []

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

        # 过滤禁止区域 (title/author/reference/header/footer)
        content_type = m.get("content_type", "paragraph")
        if _is_in_skip_zone(bbox, page, content_type, page_idx, total_pages):
            filtered_count += 1
            filter_reasons.append(f"page {page_idx} type={content_type} bbox=({x1:.0f},{y1:.0f})-({x2:.0f},{y2:.0f})")
            continue

        # 画黄线
        try:
            if mode == "line" or mode == "both":
                line_y = y2 + 0.5
                page.draw_line(
                    fitz.Point(x1, line_y),
                    fitz.Point(x2, line_y),
                    color=(1, 1, 0),
                    width=1.2,
                    overlay=True,
                )
                highlight_count += 1
            if mode == "fill" or mode == "both":
                page.draw_rect(
                    fitz.Rect(x1, y1, x2, y2),
                    fill=(1, 1, 0),
                    color=(1, 1, 0),
                    width=0,
                    overlay=True,
                    fill_opacity=0.3,
                )
                highlight_count += 1
        except Exception as e:
            print(f"  ⚠ draw err on page {page_idx}: {e}")
            continue

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    try:
        doc.save(out_path)
    except Exception as e:
        return {"ok": False, "reason": f"save_err: {e}"}
    finally:
        doc.close()

    if highlight_count == 0 and filtered_count > 0:
        reason = f"all_{filtered_count}_matches_in_forbidden_zones (title/author/reference)"
    else:
        reason = ""

    return {
        "ok": highlight_count > 0,
        "highlight_count": highlight_count,
        "filtered_count": filtered_count,
        "method": "semantic_bbox_v11",
        "matches_used": len(matches),
        "filter_reasons": filter_reasons[:5],
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
    """纯 semantic matching. 禁止 keyword 兜底. 禁止高亮 title/author/reference."""
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
    # Stage 2: semantic search (sensenova vision) - 纯语义, 不 fallback
    print(f"  [{idx}/{total}] {pn_x}: stage 2 (sensenova vision)...", flush=True)
    matches = stage2_semantic_search(plan, ppt_render, max_pages=4, vision_timeout=30)
    method = "semantic_bbox_v11"

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
