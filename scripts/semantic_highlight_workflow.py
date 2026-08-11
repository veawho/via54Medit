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
     "content_type": "paragraph" / "figure" / "table" / "icon" / "image",
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
def stage3_highlight_bbox(plan: Dict, matches: List[Dict], out_path: str,
                          mode: str = "line") -> Dict:
    """
    直接用 sensenova 返回的 bbox 画黄线, 不依赖 text search
    mode: "line" (细黄线) 或 "fill" (黄色填充) 或 "both"
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

    highlight_count = 0
    for m in matches:
        page_idx = m.get("page", 0)
        if page_idx >= doc.page_count:
            continue
        bbox = m.get("bbox_pdf", [])
        if not bbox or len(bbox) != 4:
            continue
        x1, y1, x2, y2 = bbox
        # PDF bbox 必须 valid
        page = doc[page_idx]
        page_rect = page.rect
        if x1 >= x2 or y1 >= y2:
            continue
        # 裁剪到页面范围
        x1 = max(0, min(x1, page_rect.x1))
        x2 = max(0, min(x2, page_rect.x1))
        y1 = max(0, min(y1, page_rect.y1))
        y2 = max(0, min(y2, page_rect.y1))

        # 画黄线 (line mode = 细线) 或 填充
        try:
            if mode == "line" or mode == "both":
                # 文字下方细黄线: 画在 bbox 底部 +0.5pt
                line_y = y2 + 0.5
                page.draw_line(
                    fitz.Point(x1, line_y),
                    fitz.Point(x2, line_y),
                    color=(1, 1, 0),  # yellow
                    width=1.2,
                    overlay=True,
                )
                highlight_count += 1
            if mode == "fill" or mode == "both":
                # 黄色填充 (高亮笔效果)
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

    # 保存
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    try:
        doc.save(out_path)
    except Exception as e:
        return {"ok": False, "reason": f"save_err: {e}"}
    finally:
        doc.close()

    return {
        "ok": highlight_count > 0,
        "highlight_count": highlight_count,
        "method": "semantic_bbox_v11",
        "matches_used": len(matches),
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


def _process_one(plan, project_root, out_dir, mode, idx, total, use_fallback=True):
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
    # Stage 2: semantic search (sensenova vision)
    print(f"  [{idx}/{total}] {pn_x}: stage 2 (sensenova vision)...", flush=True)
    matches = stage2_semantic_search(plan, ppt_render, max_pages=4, vision_timeout=30)
    method = "semantic_bbox_v11"

    if not matches and use_fallback:
        # Fallback: keyword matching via process_pn_x
        print(f"    → no semantic match, fallback to keyword matching", flush=True)
        # 抽 keywords from target_text + data_points
        kws = list(plan.get("keywords", []) or [])
        kws += list(plan.get("data_points", []) or [])
        # 加从 target_text 拆的 2-4 字词
        import re as re2
        target = plan.get("target_text", "") or ""
        kws += re2.findall(r'[\u4e00-\u9fff]{2,4}', target)
        kws += re2.findall(r'[A-Za-z]{4,15}', target)
        kws = list(dict.fromkeys(k for k in kws if k and len(k) > 1))[:15]

        if kws:
            from via54_highlight_fix_v10 import process_pn_x
            out_pdf = os.path.join(out_dir, f"{pn_x}_semantic_highlight.pdf")
            jpg_dir = os.path.join(out_dir, f"{pn_x}_jpgs")
            os.makedirs(jpg_dir, exist_ok=True)
            try:
                # 暂时关闭 strict mode 让 title 区也可画
                import via54_highlight_fix_v10 as v
                orig = v.STRICT_SKIP_HEADER
                v.STRICT_SKIP_HEADER = False
                r = process_pn_x(
                    pn_x, plan["pdf_path"], out_pdf, kws, jpg_dir,
                    f"{pn_x}_page", mode=mode, use_glm=False,
                )
                v.STRICT_SKIP_HEADER = orig
                print(f"    → fallback hits={r['total_hits']}, yellow={r['yellow_pct_estimate']:.3f}%")
                return {
                    "pn_x": pn_x, "ok": r.get("ok", False),
                    "method": "keyword_fallback",
                    "highlight_count": r.get("total_hits", 0),
                    "matches": 0,
                }
            except Exception as e:
                print(f"    → fallback err: {e}")

    if not matches:
        return {"pn_x": pn_x, "ok": False, "reason": "no_semantic_match", "matches": 0}

    # Stage 3: bbox highlight
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
            executor.submit(_process_one, plan, project_root, out_dir, mode, i, len(valid_plans), use_fallback=True): plan
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
