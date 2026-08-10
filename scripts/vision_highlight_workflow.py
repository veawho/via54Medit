#!/usr/bin/env python3
"""
vision_highlight_workflow.py — Vision-Driven Highlight Pipeline (2026-08-11)

4 阶段:
  1. PPT Vision → Highlight Plan: sensenova 看 PPT slide, 提取每 mark 的 target data
  2. PDF Vision Search: sensenova 找 PDF 中匹配内容
  3. Highlight Execution: v10.1 line 模式画细黄线
  4. Vision Verify: sensenova 对比 PPT vs highlighted PDF

输入: PPT vision_report.json + PDF 目录
输出: highlight 后的 PDF + verify 报告

依赖: sensenova_vision.py + via54_highlight_fix_v10.py
"""
import os, sys, json, re, time, base64
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sensenova_vision import vision_analyze
from via54_highlight_fix_v10 import process_pn_x, DEFAULT_HIGHLIGHT_MODE


def sensenova_query(image_paths, prompt, json_mode=True, timeout=60):
    """
    统一 sensenova 视觉调用接口, 支持单图或多图.
    image_paths: str 或 list[str]
    """
    if isinstance(image_paths, str):
        return vision_analyze(image_paths, prompt, json_mode=json_mode, timeout=timeout).get("content", "")
    # 多图: 拼 content
    import sensenova_vision
    api_key = sensenova_vision.get_api_key()
    if not api_key:
        return ""
    content = [{"type": "text", "text": prompt}]
    for p in image_paths:
        if not os.path.isfile(p):
            continue
        b64 = sensenova_vision.encode_image(p)
        mime = sensenova_vision.get_image_mime(p)
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
    try:
        req = urllib.request.Request(
            "https://token.sensenova.cn/v1/chat/completions",
            data=json.dumps(data).encode(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read())
            return result.get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as e:
        return ""

# === Util: 鲁棒 JSON 解析 ===
def _parse_json_loose(text: str) -> Optional[dict]:
    """从 sensenova 返回里抽 JSON, 支持多种包装"""
    if not text:
        return None
    text = text.strip()
    # 1) 完整 markdown ```json ... ``` 块
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # 2) 找第一个 { 到对应匹配的 }
    start = text.find('{')
    if start < 0:
        return None
    depth = 0
    end = -1
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                end = i
                break
    if end > 0:
        try:
            return json.loads(text[start:end+1])
        except Exception:
            pass
    # 3) 尝试直接 parse 整段
    try:
        return json.loads(text)
    except Exception:
        return None


# === Paths ===
TMA_ROOT = "/Users/david/Desktop/TMA_文献整理"
LEIDA_ROOT = "/Users/david/Desktop/雷管方案_文献整理"
DEFAULT_ROOT = TMA_ROOT


# === Stage 1: PPT Vision → Highlight Plan ===
def stage1_ppt_to_plan(
    vision_report_path: str,
    ppt_renders_dir: str,
    project_root: str,
    pdf_dir: str = "_2_pdfs",
    out_plan: Optional[str] = None,
    max_slides: int = 0,
) -> List[Dict]:
    """
    对每 slide 的每 citation mark:
      1. 用 sensenova 看 PPT slide image, 提取该 mark 指向的 target data
      2. 拼成 HighlightPlan: {slide, mark, target_data, keywords, pdf_path, source_text}
    """
    with open(vision_report_path) as f:
        vr = json.load(f)
    slides = vr.get("slides", {})

    pdf_full = os.path.join(project_root, pdf_dir)
    plans = []

    for slide_key, slide_data in slides.items():
        try:
            slide_num = int(slide_key) if isinstance(slide_key, str) else slide_key
        except Exception:
            continue
        if max_slides and slide_num > max_slides:
            break

        citation_marks = slide_data.get("citation_marks", {})
        if not citation_marks:
            continue

        # 找 slide 图片
        slide_img = None
        for ext in ("jpg", "png"):
            for name in (f"slide_{slide_num:03d}.{ext}", f"slide_pp_{slide_num:03d}.{ext}"):
                p = os.path.join(ppt_renders_dir, name)
                if os.path.isfile(p):
                    slide_img = p
                    break
            if slide_img:
                break

        if not slide_img:
            print(f"  ⚠ Slide {slide_num} 无图, 跳过")
            continue

        # 对每个 mark 单独 query sensenova
        for mark_str, mark_info in citation_marks.items():
            try:
                mark = int(mark_str) if isinstance(mark_str, str) else mark_str
            except Exception:
                continue

            # mark 可能含 "1,2" 形式
            if isinstance(mark, str) and "," in str(mark):
                # 拆分多 mark
                for m in str(mark).split(","):
                    p = _extract_plan_for_mark(
                        slide_num, m.strip(), mark_info, slide_img, pdf_full, citation_marks
                    )
                    if p:
                        plans.append(p)
            else:
                p = _extract_plan_for_mark(
                    slide_num, mark, mark_info, slide_img, pdf_full, citation_marks
                )
                if p:
                    plans.append(p)

    if out_plan:
        with open(out_plan, "w") as f:
            json.dump({"n_plans": len(plans), "plans": plans}, f, ensure_ascii=False, indent=2)
        print(f"✓ HighlightPlan 写: {out_plan} ({len(plans)} 个)")

    return plans


def _extract_plan_for_mark(slide_num, mark, mark_info, slide_img, pdf_full, all_marks) -> Optional[Dict]:
    """
    单个 mark 调 sensenova 抽 target data
    """
    # 拼 prompt
    source_text = mark_info.get("context", "") or mark_info.get("text", "") or ""
    if not source_text:
        return None

    # 看是否在某个 shape 内 (从 context 推)
    shape_name = mark_info.get("shape_name", "未知")
    row = mark_info.get("row")
    col = mark_info.get("column")

    # Sensenova query
    prompt = f"""这是一张医学/生物学 PPT 第 {slide_num} 页的图片。

请精确提取页面上**引用标号 {mark}** 所指向的完整信息:
1. 引用标号 {mark} 出现在哪里 (位置/形状描述)
2. 它直接关联的文字/数据/术语 (注意: 如果标号在句末, 它指向整句内容; 如果在词后, 指向该词)
3. 关键数据点: 数字、百分比、药物名、基因名、方案名、研究名、生存期、HR、p值 等
4. 这段内容在 PPT 上的视觉位置 (左侧/右侧/上方/下方/表格行X列Y)

请用 JSON 格式输出, 不要其他文字:
{{
  "mark_position": "位置描述",
  "target_text": "标号{mark}指向的完整文字 (1-3 句话)",
  "data_points": ["数据1", "数据2", ...],
  "keywords": ["关键词1", "关键词2", ...],
  "visual_position": "在 PPT 上的视觉位置"
}}"""

    try:
        result = sensenova_query(slide_img, prompt)
        if not result:
            return None
        parsed = _parse_json_loose(result)
        if not parsed:
            return None
    except Exception as e:
        print(f"  ⚠ Slide {slide_num} mark {mark} sensenova 解析失败: {e}")
        return None

    # 找对应 PDF
    pn_x = f"P{slide_num}-{mark}"
    pdf_path = None
    for f in os.listdir(pdf_full):
        if f.startswith(pn_x + "_") and f.lower().endswith(".pdf"):
            pdf_path = os.path.join(pdf_full, f)
            break
        if f == f"{pn_x}.pdf":
            pdf_path = os.path.join(pdf_full, f)
            break

    return {
        "slide": slide_num,
        "mark": mark,
        "pn_x": pn_x,
        "pdf_path": pdf_path,
        "source_shape": shape_name,
        "source_text": source_text,
        "target_text": parsed.get("target_text", ""),
        "data_points": parsed.get("data_points", []),
        "keywords": parsed.get("keywords", []),
        "visual_position": parsed.get("visual_position", ""),
        "mark_position": parsed.get("mark_position", ""),
    }


# === Stage 2: PDF Vision Search ===
def stage2_pdf_search(plan: Dict, max_pages: int = 3) -> List[Dict]:
    """
    对每个 plan, 渲染 PDF 前 N 页, 用 sensenova 找 target_data 出现的位置
    返回 [{page, bbox, snippet, confidence}]
    """
    pdf_path = plan.get("pdf_path")
    if not pdf_path or not os.path.isfile(pdf_path):
        return []

    target = plan.get("target_text", "")
    keywords = plan.get("keywords", [])
    data_points = plan.get("data_points", [])

    if not target and not keywords:
        return []

    # 渲染 PDF 前 N 页
    import fitz
    doc = fitz.open(pdf_path)
    n_pages = min(max_pages, doc.page_count)
    matches = []

    for p in range(n_pages):
        # 渲染 page 为 jpg
        page = doc[p]
        mat = fitz.Matrix(1.5, 1.5)  # 1.5x zoom
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        # 写到临时文件
        tmp = f"/tmp/_pdf_page_{plan['pn_x']}_{p}.png"
        with open(tmp, "wb") as f:
            f.write(img_data)

        # 拼 sensenova query
        prompt = f"""这是一页 PDF 文档 (来自引用 {plan['pn_x']})。

PPT 标号 {plan['mark']} 在 PPT 上的内容是: "{target}"
关键数据: {data_points}
关键词: {keywords}

请检查这页 PDF 是否包含以下内容:
- "{target}" (或其核心概念)
- 数据点: {data_points}
- 关键词: {keywords}

如果**包含**, 给出:
1. 包含的内容 (snippet, 引用原文)
2. 视觉位置 (页面上半/下半/左/右/中央, 或具体 bbox)
3. 置信度 0-1

如果**不包含**, 回答 "NO".

JSON 格式:
{{
  "found": true/false,
  "snippet": "原文片段",
  "visual_position": "页面位置",
  "bbox_estimate": [x1, y1, x2, y2],  // 像素坐标
  "confidence": 0.0-1.0
}}"""

        try:
            result = sensenova_query(tmp, prompt)
            if not result:
                continue
            parsed = _parse_json_loose(result)
            if not parsed:
                continue
            if parsed.get("found"):
                matches.append({
                    "page": p,
                    "snippet": parsed.get("snippet", ""),
                    "visual_position": parsed.get("visual_position", ""),
                    "bbox_estimate": parsed.get("bbox_estimate", []),
                    "confidence": parsed.get("confidence", 0.0),
                })
        except Exception as e:
            print(f"    ⚠ sensenova page {p} parse err: {e}")
            continue

        # 清理
        try:
            os.remove(tmp)
        except Exception:
            pass

        time.sleep(0.5)  # 避免被 ban

    doc.close()
    return matches


# === Stage 3: Highlight Execution ===
def stage3_highlight(plan: Dict, matches: List[Dict], out_path: str,
                     mode: str = "line") -> Dict:
    """
    用 v10.1 process_pn_x + 找到的 match 信息画细黄线

    注: v10.1 用关键词搜索, 这里用 sensenova vision 找到的 snippet 作为关键词
    """
    if not matches:
        return {"ok": False, "reason": "no_matches"}

    # 选 confidence 最高的 match
    best = max(matches, key=lambda m: m.get("confidence", 0))
    if best.get("confidence", 0) < 0.3:
        return {"ok": False, "reason": f"low_confidence:{best.get('confidence')}"}

    # 准备 v10.1 需要的关键词
    # 用 snippet 作为核心 (vision 找到的原文片段), 加 data_points 关键词
    # 避免用年份/期刊名等过宽的词 (会匹配 header/footer)
    keywords = []
    snippet = best.get("snippet", "").strip()
    if snippet and len(snippet) > 10:
        # 取 snippet 核心句 (按句号分)
        sentences = re.split(r'[.。;]', snippet)
        core = [s.strip() for s in sentences if len(s.strip()) > 5][:2]
        keywords.extend(core)
    # 加上 data_points (具体术语, 比 keywords 更精确)
    keywords.extend(plan.get("data_points", [])[:5])
    # 过滤空和过短的
    keywords = [k for k in keywords if k and len(k) > 2][:5]

    if not keywords:
        return {"ok": False, "reason": "no_keywords"}

    # 调 v10.1 process_pn_x
    pn_x = plan["pn_x"]
    pdf_path = plan["pdf_path"]

    try:
        result = process_pn_x(
            pn_x=pn_x,
            pdf_in=pdf_path,
            pdf_out=out_path,
            keywords=keywords,
            mode=mode,
            use_glm=False,  # 不用 GLM, vision 已经提供关键词
        )
        return {
            "ok": result.get("ok", False),
            "highlight_count": result.get("total_hits", 0),
            "method": "vision_search_v10.1",
            "best_match": best,
        }
    except Exception as e:
        return {"ok": False, "reason": f"process_pn_x_err: {e}"}


# === Stage 4: Vision Verify ===
def stage4_verify(plan: Dict, highlight_pdf_path: str, ppt_render_path: str) -> Dict:
    """
    渲染 highlight 后的 PDF 页 + PPT slide, sensenova 对比
    """
    import fitz

    if not os.path.isfile(highlight_pdf_path) or not os.path.isfile(ppt_render_path):
        return {"aligned": False, "reason": "missing_file"}

    # 找最可能对应的 page (vision search 时的 page)
    # 这里简化: 渲染第 1 页
    doc = fitz.open(highlight_pdf_path)
    if doc.page_count == 0:
        return {"aligned": False, "reason": "empty_pdf"}
    page = doc[0]
    mat = fitz.Matrix(1.5, 1.5)
    pix = page.get_pixmap(matrix=mat)
    pdf_img = f"/tmp/_verify_{plan['pn_x']}.png"
    with open(pdf_img, "wb") as f:
        f.write(pix.tobytes("png"))
    doc.close()

    # 拼 sensenova query
    target = plan.get("target_text", "")[:200]
    data_points = plan.get("data_points", [])
    keywords = plan.get("keywords", [])

    prompt = f"""这是两个图:
- 图 1 (PDF): 文献 PDF 的一页, 有黄色高亮标注
- 图 2 (PPT): 引用此文献的 PPT slide 一页

PPT 标号 {plan['mark']} 指向的内容是: "{target}"
关键数据点: {data_points}
关键词: {keywords}

请检查 PDF 上的**黄色高亮**内容是否与 PPT 标号 {plan['mark']} 的内容**语义对应**:
- 主题一致 (都讲同一件事)
- 关键数据/术语有重叠

JSON 格式:
{{
  "aligned": true/false,
  "alignment_score": 0.0-1.0,
  "highlighted_content_in_pdf": "PDF 黄线下的文字",
  "ppt_reference": "PPT 标号{plan['mark']}的文字",
  "issue": "如果不 aligned, 描述差异",
  "confidence": 0.0-1.0
}}"""

    try:
        # 用多图模式
        result = sensenova_query([pdf_img, ppt_render_path], prompt)
        if not result:
            return {"aligned": False, "reason": "sensenova_no_result"}
        parsed = _parse_json_loose(result)
        if not parsed:
            return {"aligned": False, "reason": "json_parse_fail"}
        return parsed
    except Exception as e:
        return {"aligned": False, "reason": f"sensenova_parse_err: {e}"}
    finally:
        try:
            os.remove(pdf_img)
        except Exception:
            pass


# === CLI ===
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", choices=["TMA", "雷管方案"], default="TMA")
    parser.add_argument("--stage", choices=["1", "2", "3", "4", "all", "plan-only"], default="plan-only")
    parser.add_argument("--max-slides", type=int, default=0)
    parser.add_argument("--max-marks", type=int, default=0)
    args = parser.parse_args()

    if args.project == "TMA":
        root = TMA_ROOT
    else:
        root = LEIDA_ROOT

    vision_report = os.path.join(root, "_vision_report.json")
    ppt_renders = os.path.join(root, "_1_ppt/_3_images")
    if not os.path.isdir(ppt_renders):
        ppt_renders = os.path.join(root, "_ppt_renders")
    if not os.path.isdir(ppt_renders):
        ppt_renders = os.path.join(root, "_1_ppt")

    out_dir = os.path.join(root, "_3_highlight_vision")
    os.makedirs(out_dir, exist_ok=True)

    # Stage 1: PPT Vision → Plan
    if args.stage in ("1", "all", "plan-only"):
        print(f"=== Stage 1: PPT Vision → Highlight Plan ({args.project}) ===")
        plans = stage1_ppt_to_plan(
            vision_report, ppt_renders, root,
            out_plan=os.path.join(out_dir, "_highlight_plans.json"),
            max_slides=args.max_slides,
        )
        if args.max_marks:
            plans = plans[:args.max_marks]
        print(f"  Plans: {len(plans)}")
        if args.stage == "plan-only":
            return

    # 加载 plans (from disk if stage 1 wasn't run)
    plans_path = os.path.join(out_dir, "_highlight_plans.json")
    if os.path.isfile(plans_path):
        with open(plans_path) as f:
            plans = json.load(f)["plans"]
    else:
        plans = []
    if args.max_marks:
        plans = plans[:args.max_marks]
    print(f"  Loaded {len(plans)} plans from disk")

    # Stage 2: PDF Search
    if args.stage in ("2", "all"):
        print(f"\n=== Stage 2: PDF Vision Search ({len(plans)} plans) ===")
        for i, plan in enumerate(plans, 1):
            if not plan.get("pdf_path"):
                continue
            print(f"  [{i}/{len(plans)}] {plan['pn_x']}...", flush=True)
            matches = stage2_pdf_search(plan)
            plan["matches"] = matches
            print(f"    matches: {len(matches)}", flush=True)
        with open(os.path.join(out_dir, "_highlight_plans_with_matches.json"), "w") as f:
            json.dump({"n_plans": len(plans), "plans": plans}, f, ensure_ascii=False, indent=2)

    # 加载 plans with matches
    matches_path = os.path.join(out_dir, "_highlight_plans_with_matches.json")
    if os.path.isfile(matches_path):
        with open(matches_path) as f:
            plans = json.load(f)["plans"]
    else:
        print("  No _highlight_plans_with_matches.json, run stage 2 first")
        return
    if args.max_marks:
        plans = plans[:args.max_marks]

    # Stage 3: Highlight
    if args.stage in ("3", "all"):
        print(f"\n=== Stage 3: Highlight Execution ===")
        for i, plan in enumerate(plans, 1):
            if not plan.get("pdf_path") or not plan.get("matches"):
                continue
            out_pdf = os.path.join(out_dir, f"{plan['pn_x']}_vision_highlight.pdf")
            result = stage3_highlight(plan, plan["matches"], out_pdf)
            plan["highlight_result"] = result
            print(f"  [{i}/{len(plans)}] {plan['pn_x']}: {result.get('ok')}", flush=True)
        with open(os.path.join(out_dir, "_highlight_plans_with_highlight.json"), "w") as f:
            json.dump({"n_plans": len(plans), "plans": plans}, f, ensure_ascii=False, indent=2)

    # Stage 4: Vision Verify
    if args.stage in ("4", "all"):
        print(f"\n=== Stage 4: Vision Verify ===")
        hl_path = os.path.join(out_dir, "_highlight_plans_with_highlight.json")
        if os.path.isfile(hl_path):
            with open(hl_path) as f:
                plans = json.load(f)["plans"]
        for i, plan in enumerate(plans, 1):
            if not plan.get("highlight_result", {}).get("ok"):
                continue
            out_pdf = os.path.join(out_dir, f"{plan['pn_x']}_vision_highlight.pdf")
            # PPT render path
            slide_num = plan["slide"]
            ppt_img = None
            for ext in ("jpg", "png"):
                for name in (f"slide_{slide_num:03d}.{ext}", f"slide_pp_{slide_num:03d}.{ext}"):
                    p = os.path.join(ppt_renders, name)
                    if os.path.isfile(p):
                        ppt_img = p
                        break
                if ppt_img:
                    break
            if not ppt_img:
                plan["verify"] = {"aligned": False, "reason": "no_ppt_img"}
                continue
            print(f"  [{i}/{len(plans)}] {plan['pn_x']}...", flush=True)
            verify = stage4_verify(plan, out_pdf, ppt_img)
            plan["verify"] = verify
            print(f"    aligned: {verify.get('aligned')} (score: {verify.get('alignment_score', '?')})", flush=True)
        with open(os.path.join(out_dir, "_verify_report.json"), "w") as f:
            json.dump({"n_plans": len(plans), "plans": plans}, f, ensure_ascii=False, indent=2)
        # Summary
        n_aligned = sum(1 for p in plans if p.get("verify", {}).get("aligned"))
        print(f"\n=== Verify 总结: {n_aligned}/{len(plans)} aligned ===")


if __name__ == "__main__":
    main()
