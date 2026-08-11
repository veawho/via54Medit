#!/usr/bin/env python3
"""
semantic_v3_claim_extract.py — 2-stage vision pipeline (v3)

新思路 (2026-08-11):
1. Stage 1A: sensenova 看 PPT slide 单独抽"核心 claim/key claim" (1-3 句)
2. Stage 1B: 用抽出的 claim 作为 target_text, sensenova 同时看 PPT + PDF 找对应 bbox
3. Stage 3: highlight (复用 v1.4 严格版)

解决: auto_built Pn-x 缺 PPT 标号 → sensenova 帮我们从 PPT slide 提取
"""
import os, sys, json, time, re, tempfile
from typing import Dict, List, Optional
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fitz
fitz.TOOLS.mupdf_display_warnings(False)

# 复用
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
from semantic_v2_vision_only import sensenova_call_v2


def extract_claim_from_slide(plan: Dict, ppt_render_path: str) -> str:
    """
    Stage 1A: sensenova 看 PPT slide 单独抽"核心 claim"
    返回 1-3 句, 用作 target_text
    """
    if not os.path.isfile(ppt_render_path):
        return ""

    prompt = """你是医学/生物学 PPT 解读专家。

【任务】看这张 PPT slide 渲染图, 抽出这张 slide 想要表达的核心 claim (1-3 句话).

【背景】这张 slide 引用了一篇医学文献 (slide 上的某段文字/图/表). 这段引用的目的是支撑 slide 上的某个论点.

【需要回答】
1. 这张 slide 引用文献的**核心内容**是什么? (即文献讲什么)
2. 这段引用想支撑的**论点**是什么? (e.g. "TREATMENT IS EFFECTIVE", "MECHANISM IS X", "PROGNOSIS IS Y")

【输出】严格用 JSON:
{
  "key_claim": "1-3 句话, 描述这张 slide 引用的核心内容 (用中文或英文, 跟 slide 实际语言一致)",
  "supporting_point": "1 句话, slide 想支撑的论点",
  "key_data_points": ["数据点 1", "数据点 2", ...],
  "content_type_on_slide": "paragraph" | "figure" | "table" | "case_description" | "consensus_statement"
}

如果 slide 上有具体数字/百分比/药物名/疾病名, 必须包含在 key_claim 或 key_data_points."""

    result = sensenova_call_v2([ppt_render_path], prompt, json_mode=True, timeout=60)
    parsed = _parse_json_loose(result)
    if not parsed:
        return ""

    claim = parsed.get("key_claim", "")
    if not claim:
        return ""

    # 也合并 data_points
    data_points = parsed.get("key_data_points", [])
    if data_points:
        claim = claim + " | Data: " + ", ".join(data_points[:5])

    return claim


def stage2_with_claim(plan: Dict, claim: str, ppt_render_path: str,
                       max_pages: int = 4, vision_timeout: int = 60) -> List[Dict]:
    """
    Stage 1B: 用 claim 作为 target_text, sensenova 找 PDF 对应 bbox
    """
    pdf_path = plan.get("pdf_path")
    if not pdf_path or not os.path.isfile(pdf_path):
        return []
    if not os.path.isfile(ppt_render_path):
        return []

    doc = fitz.open(pdf_path)
    n_pages = min(max_pages, doc.page_count)
    matches = []

    tmp_dir = tempfile.mkdtemp(prefix=f"_v3_{plan['pn_x']}_{os.getpid()}_")

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

        # 类似 v1.4 prompt 但用新抽出的 claim
        prompt = f"""你是医学/生物学文献**视觉语义匹配**专家。

【任务】基于 PPT slide 抽出的核心 claim, 在 PDF 中找对应的 body 段落/图/表, 并返回 bbox.

【PPT slide 抽出的核心 claim】"{claim}"

提供 2 张图:
- 图 1: PPT slide 渲染图 (该 claim 在哪)
- 图 2: PDF 第 {p+1} 页渲染图 (宽高 {img.size[0]}x{img.size[1]})

请**只**在图 2 (PDF 第 {p+1} 页) 中找与该 claim 语义对应的 body 段落/图/表, 并给出 bbox.

⚠️ 是找 PDF (图 2) 里的内容, 不是 PPT (图 1) 里的.

【严格禁止高亮以下区域】 (必须用 content_type 标识, 不返回 bbox)
- "title" / "article_title" / "section_title" - 文章标题 / 章节标题
- "author" / "authors" / "affiliation" - 作者名 / 单位 / 通信作者
- "reference" / "references" / "bibliography" - 文献引用列表
- "header" / "footer" / "running_head" / "journal_info" - 页眉页脚
- "acknowledgment" / "acknowledgements" - 致谢
- "declaration" / "competing_interests" / "funding" / "author_contributions" - 利益声明/基金/作者贡献

如果图 2 包含与该 claim 对应的 body 段落, 给出:
{{
  "found": true,
  "matches": [
    {{
      "bbox": [x1, y1, x2, y2],
      "content_type": "paragraph" | "figure" | "table" | "image" | "icon",
      "semantic_description": "该区域讲什么 (1 句)",
      "relevance": "该区域与 claim 的关系 (1 句)"
    }}
  ],
  "overall_confidence": 0.0-1.0
}}

如果图 2 没有与 claim 对应的 body 内容:
{{
  "found": false,
  "reason": "图 2 没有与 claim 对应的 body 内容"
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
                    "semantic_description": m.get("semantic_description", ""),
                    "relevance": m.get("relevance", ""),
                    "confidence": parsed.get("overall_confidence", 0.5),
                })
        except Exception as e:
            print(f"  ⚠ sensenova page {p} err: {e}", flush=True)
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


def process_v3(plan: Dict, project_root: str, out_dir: str, idx: int, total: int) -> Dict:
    """v3 完整 pipeline: 抽 claim → 找 bbox → highlight"""
    pn_x = plan.get("pn_x", "?")
    slide = plan.get("slide", 0)

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

    # Stage 1A: 抽 claim
    claim = plan.get("target_text", "").strip()
    if not claim or len(claim) < 20:
        # target_text 太短/没意义, 用 sensenova 抽
        print(f"  [{idx}/{total}] {pn_x}: stage 1A (extract claim)...")
        claim = extract_claim_from_slide(plan, ppt_render)
        if not claim:
            return {"pn_x": pn_x, "ok": False, "reason": "no_claim_extracted", "matches": 0}
        plan["extracted_claim"] = claim

    # Stage 1B: 用 claim 找 bbox
    print(f"  [{idx}/{total}] {pn_x}: stage 1B (find bbox)...")
    matches = stage2_with_claim(plan, claim, ppt_render, max_pages=4)

    if not matches:
        return {"pn_x": pn_x, "ok": False, "reason": "no_semantic_match", "matches": 0}

    # Stage 3: highlight
    out_path = os.path.join(out_dir, f"{pn_x}_semantic_highlight.pdf")
    plan_for_stage3 = dict(plan)
    plan_for_stage3["pdf_path"] = pdf_path
    r = stage3_highlight_bbox(plan_for_stage3, matches, out_path, mode="line")

    r["pn_x"] = pn_x
    r["matches"] = len(matches)
    r["claim"] = claim[:100]
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
    out_dir = args.out_dir or os.path.join(project_root, '_3_highlight_semantic_v3')
    os.makedirs(out_dir, exist_ok=True)

    data = json.load(open(plans_path))
    plans = data['plans'] if isinstance(data, dict) else data

    # 找 missing (包括 v2 的产出)
    existing_dirs = [
        '_3_highlight_semantic_v141',
        '_3_highlight_semantic_v142',
        '_3_highlight_semantic_v14',
        '_3_highlight_semantic_v2',
    ]
    done = set()
    for d in existing_dirs:
        full = os.path.join(project_root, d)
        if os.path.isdir(full):
            for f in os.listdir(full):
                if f.endswith('.pdf'):
                    done.add(f.replace('_semantic_highlight.pdf', ''))
    missing = [p for p in plans if p.get('pn_x') not in done]
    if args.limit:
        missing = missing[:args.limit]
    print(f'Total plans: {len(plans)}, done: {len(done)}, missing: {len(missing)}', flush=True)

    # 4 worker
    from concurrent.futures import ThreadPoolExecutor, as_completed
    summary = []
    start = time.time()

    def process_one(idx_p):
        idx, p = idx_p
        return process_v3(p, project_root, out_dir, idx, len(missing))

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
    print(f'\n=== DONE: {ok}/{len(summary)} OK in {time.time()-start:.0f}s ===', flush=True)
    json.dump(summary, open(out_dir + '/_semantic_summary.json', 'w'), ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
