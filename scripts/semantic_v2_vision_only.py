#!/usr/bin/env python3
"""
semantic_v2_vision_only.py — vision-only pipeline (v2)

新设计 (2026-08-11):
- 不依赖 target_text (auto_built 35 Pn-x 没 PPT 标号)
- sensenova 看 PPT slide + PDF, 自己决定 highlight 哪些
- 用 PPT slide 当作 "instruction", 让 sensenova 找出 PDF 中对应的 body 内容

新 prompt 让 sensenova:
1. 看 PPT slide 了解被引用内容 (figure/table/data point)
2. 在 PDF 中找该内容对应段落/图/表
3. 返回 bbox (图 2 坐标)
4. 排除 title/author/ref/header/footer/declaration

预期: 35 auto_built Pn-x 中 25-30 个能成功 (75-85% 召回)
"""
import os, sys, json, time, re, tempfile
from typing import Dict, List, Optional
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fitz
fitz.TOOLS.mupdf_display_warnings(False)

# 复用 v1.4 的 stage3 + filter
from semantic_highlight_workflow import (
    stage3_highlight_bbox,
    _is_geometry_forbidden,
    _is_forbidden_text,
    FORBIDDEN_CONTENT_TYPES,
    FIGURE_TYPES,
    find_pdf,
    render_pdf_page,
    _parse_json_loose,
    _sensenova_cache,
    _load_cache,
    _save_cache,
    _cache_key,
    TMA_ROOT, LEIDA_ROOT, RENDER_ZOOM,
)
from provider_vision import vision_analyze, get_api_key, encode_image, get_image_mime
import urllib.request
import hashlib


def sensenova_call_v2(image_paths, prompt, json_mode=True, timeout=60):
    """支持 vision-only 模式"""
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
        "temperature": 0.05,
    }
    if json_mode:
        data["response_format"] = {"type": "json_object"}
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


def stage2_vision_only(plan: Dict, ppt_render_path: str,
                        max_pages: int = 6, vision_timeout: int = 60) -> List[Dict]:
    """
    Vision-only 模式: 不传 target_text, 让 sensenova 看 PPT slide + PDF 找对应内容.

    Returns: [{page, bbox_pdf, bbox_image, content_type, ...}]
    """
    pdf_path = plan.get("pdf_path")
    if not pdf_path or not os.path.isfile(pdf_path):
        return []

    if not os.path.isfile(ppt_render_path):
        return []

    doc = fitz.open(pdf_path)
    n_pages = min(max_pages, doc.page_count)
    matches = []

    tmp_dir = tempfile.mkdtemp(prefix=f"_v2_{plan['pn_x']}_{os.getpid()}_")

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

        # === VISION-ONLY PROMPT ===
        # 关键: 让 sensenova 看 PPT slide 决定 highlight 哪些
        # 不传 target_text, 避免短 target 失败
        prompt = f"""你是医学文献**视觉语义匹配**专家。

【任务】vision-only: 不用任何 target_text, 直接看 PPT slide 自己判断要 highlight PDF 哪部分。

提供 2 张图:
- 图 1: PPT slide 渲染图 (这是某个医学 PPT 的某一页, 标号 {plan.get('mark', '?')} 引用了一篇文献)
- 图 2: PDF 第 {p+1} 页渲染图 (宽高 {img.size[0]}x{img.size[1]})

【PPT slide (图 1) 解读指导】
PPT slide 通常是引用某篇 paper 的某张图/表/数据点, 用于支撑一个论点.
你需要:
1. 看 PPT slide 上的**主要内容** (figure/table/data point/case 描述)
2. 推断这篇 paper **在 PPT 上要表达什么** (e.g. "TREATMENT EFFICACY", "SAFETY PROFILE", "MECHANISM", "DIAGNOSIS")
3. 在 PDF (图 2) 中找**与该主题对应的 body 内容** (段落/图/表)

【PDF (图 2) 找什么】
- 段落: 描述 PPT slide 论点的 body text
- 图/表: PPT slide 引用的图/表的原文
- 数据点: PPT slide 引用的数据 (数字/百分比) 的来源

【严格禁止高亮以下区域】 (必须用 content_type 标识)
- "title" / "article_title" / "section_title" - 文章标题 / 章节标题
- "author" / "authors" / "affiliation" - 作者名 / 单位 / 通信作者
- "reference" / "references" / "bibliography" - 文献引用列表
- "header" / "footer" / "running_head" / "journal_info" - 页眉页脚
- "acknowledgment" / "acknowledgements" - 致谢
- "declaration" / "competing_interests" / "funding" - 利益声明/基金
- "supplementary" - 补充材料

如果图 2 包含与 PPT slide 主题对应的 body 段落, 给出:
{{
  "found": true,
  "matches": [
    {{
      "bbox": [x1, y1, x2, y2],
      "content_type": "paragraph" | "figure" | "table" | "image" | "icon",
      "topic": "该区域讲什么 (1 句)",
      "relevance": "该区域与 PPT slide 主题的关系 (1 句)"
    }}
  ],
  "overall_confidence": 0.0-1.0
}}

如果图 2 不包含与 PPT slide 主题对应的 body 内容 (或全部匹配在禁止区域):
{{
  "found": false,
  "reason": "图 2 没有与 PPT slide 主题对应的 body 内容"
}}

请严格用 JSON 输出。"""

        try:
            result = sensenova_call_v2(
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
                    "semantic_description": m.get("topic", ""),
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


def process_vision_only(plan: Dict, project_root: str, out_dir: str, idx: int, total: int) -> Dict:
    """vision-only 完整 pipeline"""
    pn_x = plan.get("pn_x", "?")
    slide = plan.get("slide", 0)
    mark = plan.get("mark", 1)

    # 找 PDF
    pdf_path = plan.get("pdf_path")
    if not pdf_path or not os.path.isfile(pdf_path):
        pdf_path = find_pdf(project_root, pn_x)
        if pdf_path:
            plan["pdf_path"] = pdf_path
    if not pdf_path or not os.path.isfile(pdf_path):
        return {"pn_x": pn_x, "ok": False, "reason": "no_pdf", "matches": 0}

    # 找 PPT render
    ppt_render = plan.get("ppt_render")
    if not ppt_render or not os.path.isfile(ppt_render):
        # 尝试从 project_root 找
        candidates = [
            os.path.join(project_root, "_1_ppt/_3_images", f"slide_pp_{slide:03d}.jpg"),
            os.path.join(project_root, "_1_ppt/_3_images", f"slide_{slide:03d}.jpg"),
            os.path.join(project_root, "step1_ppt_目录/_ppt_renders_expanded", f"slide_{slide:03d}.jpg"),
            os.path.join(project_root, "step1_ppt_目录/_ppt_renders", f"slide_{slide:03d}.jpg"),
        ]
        for c in candidates:
            if os.path.isfile(c):
                ppt_render = c
                plan["ppt_render"] = c
                break
    if not ppt_render or not os.path.isfile(ppt_render):
        return {"pn_x": pn_x, "ok": False, "reason": "no_ppt_render", "matches": 0}

    # Stage 2: vision-only
    print(f"  [{idx}/{total}] {pn_x}: vision-only stage 2 (no target_text)...")
    matches = stage2_vision_only(plan, ppt_render, max_pages=6)

    if not matches:
        return {"pn_x": pn_x, "ok": False, "reason": "no_semantic_match", "matches": 0}

    # Stage 3: highlight (复用 v1.4 严格版)
    out_path = os.path.join(out_dir, f"{pn_x}_semantic_highlight.pdf")
    # 先 copy 原 PDF 到 out_path, 再在 out_path 上加 annot
    import shutil
    shutil.copy2(pdf_path, out_path)
    # stage3_highlight_bbox 接受 plan["pdf_path"], 我们临时改成 out_path
    plan_for_stage3 = dict(plan)
    plan_for_stage3["pdf_path"] = out_path
    # 但 stage3 内部用 plan["pdf_path"] 打开 doc 然后 save, 我们需要让它 save 到 out_path
    # 简单方法: stage3 内部 doc.save(out_path) 用的是 out_path 参数, 不依赖 plan["pdf_path"]
    # 实际看代码: doc = fitz.open(pdf_path), doc.save(out_path)
    # 我们需要 plan["pdf_path"] = out_path 这样 doc 打开是 out_path
    # 但 doc.save(out_path) 会 save 到 out_path 参数, OK
    # 实际我们已经 cp 到 out_path, 再用 plan["pdf_path"] = out_path 打开会丢失原 PDF
    # 正确做法: 用 pdf_path 打开, save 到 out_path
    plan_for_stage3["pdf_path"] = pdf_path

    r = stage3_highlight_bbox(plan_for_stage3, matches, out_path, mode="line")

    r["pn_x"] = pn_x
    r["matches"] = len(matches)
    return r


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', choices=['TMA', '雷管方案'], default='TMA')
    parser.add_argument('--out-dir', default='')
    parser.add_argument('--limit', type=int, default=0)
    args = parser.parse_args()

    project_root = TMA_ROOT if args.project == 'TMA' else LEIDA_ROOT
    plans_path = os.path.join(project_root, '_3_highlight_vision', '_highlight_plans.json')
    out_dir = args.out_dir or os.path.join(project_root, '_3_highlight_semantic_v2')
    os.makedirs(out_dir, exist_ok=True)

    data = json.load(open(plans_path))
    plans = data['plans'] if isinstance(data, dict) else data

    # 找 missing
    v141_dir = os.path.join(project_root, '_3_highlight_semantic_v141')
    v142_dir = os.path.join(project_root, '_3_highlight_semantic_v142')
    v14_dir = os.path.join(project_root, '_3_highlight_semantic_v14')
    done = set()
    for d in [v141_dir, v142_dir, v14_dir]:
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith('.pdf'):
                    done.add(f.replace('_semantic_highlight.pdf', ''))
    missing = [p for p in plans if p.get('pn_x') not in done]
    if args.limit:
        missing = missing[:args.limit]
    print(f'Total plans: {len(plans)}, done: {len(done)}, missing: {len(missing)}')

    # 多线程 (sensenova 用 cache 避免重复调用, 4 worker)
    summary = []
    start = time.time()
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def process_one(idx_p):
        idx, p = idx_p
        return process_vision_only(p, project_root, out_dir, idx, len(missing))

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(process_one, (i, p)): p for i, p in enumerate(missing, 1)}
        for future in as_completed(futures):
            try:
                r = future.result()
                summary.append(r)
                elapsed = time.time() - start
                print(f'  → {r["pn_x"]}: ok={r.get("ok")} matches={r.get("matches")} hl={r.get("highlight_count", 0)} reason={r.get("reason", "")[:50]} | {elapsed:.0f}s', flush=True)
            except Exception as e:
                p = futures[future]
                print(f'  ERR {p.get("pn_x")}: {e}', flush=True)

    ok = sum(1 for r in summary if r.get('ok'))
    print(f'\n=== DONE: {ok}/{len(summary)} OK in {time.time()-start:.0f}s ===')
    json.dump(summary, open(out_dir + '/_semantic_summary.json', 'w'), ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
