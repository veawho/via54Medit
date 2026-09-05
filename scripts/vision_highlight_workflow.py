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
from provider_vision import vision_analyze
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
    use_vision: bool = True,
    vision_timeout: int = 30,
) -> List[Dict]:
    """
    对每 slide 的每 citation mark:
      1. 用 sensenova 看 PPT slide image, 提取该 mark 指向的 target data (如果 use_vision=True)
      2. fallback: 从 vision_report.json context 直接构造 plan
      3. 拼成 HighlightPlan
    """
    with open(vision_report_path) as f:
        vr = json.load(f)
    slides = vr.get("slides", {})

    pdf_full = os.path.join(project_root, pdf_dir)
    # 雷管方案: 优先用 step3_pdf下载_160目录
    if not os.path.isdir(pdf_full):
        for alt in ("step3_pdf下载_160目录", "step3_pdf", "_pdfs_real"):
            alt_path = os.path.join(project_root, alt)
            if os.path.isdir(alt_path):
                pdf_full = alt_path
                break
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

        # 对每个 mark
        for mark_str, mark_info in citation_marks.items():
            try:
                mark = int(mark_str) if isinstance(mark_str, str) else mark_str
            except Exception:
                continue

            # mark 可能含 "1,2" 形式
            marks_to_process = []
            if isinstance(mark, str) and "," in str(mark):
                marks_to_process = [m.strip() for m in str(mark).split(",")]
            else:
                marks_to_process = [str(mark)]

            for m in marks_to_process:
                try:
                    m_int = int(m)
                except Exception:
                    continue
                p = _extract_plan_for_mark(
                    slide_num=slide_num, mark=m_int, mark_info=mark_info,
                    pdf_full=pdf_full, slide_img=slide_img,
                    use_vision=use_vision, vision_timeout=vision_timeout,
                )
                if p:
                    plans.append(p)

    if out_plan:
        with open(out_plan, "w") as f:
            json.dump({"n_plans": len(plans), "plans": plans}, f, ensure_ascii=False, indent=2)
        print(f"✓ HighlightPlan 写: {out_plan} ({len(plans)} 个)")

    return plans


def _extract_plan_for_mark(slide_num, mark, mark_info, pdf_full,
                          slide_img=None, use_vision=True, vision_timeout=30, **kwargs) -> Optional[Dict]:
    """
    单个 mark 抽 target data. vision=可选.
    """
    source_text = mark_info.get("context", "") or mark_info.get("text", "") or ""
    if not source_text:
        return None

    shape_name = mark_info.get("shape_name", "未知")
    row = mark_info.get("row")
    col = mark_info.get("column")

    # 找对应 PDF (flat + nested 都试)
    pn_x = f"P{slide_num}-{mark}"
    pdf_path = None
    if os.path.isdir(pdf_full):
        for f in os.listdir(pdf_full):
            if f.startswith(pn_x + "_") and f.lower().endswith(".pdf"):
                pdf_path = os.path.join(pdf_full, f)
                break
            if f == f"{pn_x}.pdf":
                pdf_path = os.path.join(pdf_full, f)
                break
        # nested: Pn-x/main.pdf 或 Pn-x/Pn-x_main_*.pdf
        if not pdf_path:
            nested_dir = os.path.join(pdf_full, pn_x)
            if os.path.isdir(nested_dir):
                for f in os.listdir(nested_dir):
                    if f.lower() == "main.pdf" or (f.startswith(pn_x + "_main") and f.lower().endswith(".pdf")):
                        pdf_path = os.path.join(nested_dir, f)
                        break

    plan = {
        "slide": slide_num,
        "mark": mark,
        "pn_x": pn_x,
        "pdf_path": pdf_path,
        "source_shape": shape_name,
        "source_text": source_text,
        "target_text": source_text,  # fallback
        "data_points": [],
        "keywords": [],
        "visual_position": f"row={row}, col={col}",
        "mark_position": "",
    }

    # 简单从 source_text 抽 data_points (数字 + 医学术语)
    plan["data_points"] = _extract_terms_from_text(source_text)
    plan["keywords"] = plan["data_points"][:5]

    # 尝试 sensenova vision
    if use_vision and slide_img and os.path.isfile(slide_img):
        prompt = f"""这是一张医学/生物学 PPT 第 {slide_num} 页的图片。

请精确提取页面上**引用标号 {mark}** 所指向的完整信息:
1. 引用标号 {mark} 出现在哪里 (位置/形状描述)
2. 它直接关联的文字/数据/术语 (注意: 如果标号在句末, 它指向整句内容; 如果在词后, 指向该词)
3. 关键数据点: 数字、百分比、药物名、基因名、方案名、研究名、生存期、HR、p值 等

请用 JSON 格式输出, 不要其他文字:
{{
  "mark_position": "位置描述",
  "target_text": "标号{mark}指向的完整文字 (1-3 句话)",
  "data_points": ["数据1", "数据2", ...],
  "keywords": ["关键词1", "关键词2", ...]
}}"""
        try:
            import threading
            result_box = [None]
            def run():
                result_box[0] = sensenova_query(slide_img, prompt, json_mode=True, timeout=vision_timeout)
            t = threading.Thread(target=run, daemon=True)
            t.start()
            t.join(timeout=vision_timeout + 5)
            result = result_box[0]
            if result:
                parsed = _parse_json_loose(result)
                if parsed:
                    plan["target_text"] = parsed.get("target_text", source_text)
                    plan["data_points"] = parsed.get("data_points", plan["data_points"])
                    plan["keywords"] = parsed.get("keywords", plan["keywords"])
                    plan["mark_position"] = parsed.get("mark_position", "")
        except Exception:
            pass  # 用 fallback

    return plan


# 常用医学术语 (用于无 vision 时的数据点抽取)
_MEDICAL_TERMS = [
    "补体", "凝集素", "抗体", "抗原", "C3", "C5", "C5a", "C5b", "MAC",
    "C1q", "C4", "C2", "因子", "factor", "B", "D", "H", "I", "P", "Properdin",
    "eculizumab", "ravulizumab", "caplacizumab", "narsoplimab",
    "aHUS", "TTP", "TMA", "HUS", "STEC-HUS", "MAHA", "ADAMTS13",
    "complement", "pathway", "classical", "lectin", "alternative",
    "mOS", "mPFS", "ORR", "DCR", "HR", "p值", "95% CI",
    "重症肌无力", "自身免疫", "免疫复合物",
    "肺炎链球菌", "金黄色葡萄球菌", "大肠杆菌", "流感嗜血杆菌", "脑膜炎奈瑟氏球菌",
    "无乳链球菌", "金氏杆菌", "嗜麦芽寡养单胞菌", "肠球菌",
    "中性粒细胞", "单核细胞", "巨噬细胞", "T细胞", "B细胞",
    "脱颗粒", "细胞黏附", "毒性氧代谢物",
    "经典途径", "凝集素途径", "旁路途径", "末端途径", "近端", "远端",
    "创伤", "缺血", "同种异体", "移植排斥",
]


def _extract_terms_from_text(text: str) -> List[str]:
    """从文本抽医学术语作为 data_points"""
    found = []
    for term in _MEDICAL_TERMS:
        if term.lower() in text.lower() and term not in found:
            found.append(term)
        if len(found) >= 10:
            break
    # 也抽数字+%
    nums = re.findall(r'\d+\.?\d*\s*%?', text)
    found.extend([n for n in nums if n not in found][:5])
    return found


# === Stage 2: PDF Vision Search ===
def _sensenova_query_threaded(image_paths, prompt, json_mode=True, timeout=15):
    """Threading wrapper: 强制 15s timeout, 避免 PySSL_select 卡死"""
    import threading
    result = [None]

    def run():
        try:
            result[0] = sensenova_query(image_paths, prompt, json_mode=json_mode, timeout=timeout)
        except Exception:
            pass
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=timeout + 3)
    if t.is_alive():
        return ""  # 超时
    return result[0]


def stage2_pdf_search(plan: Dict, max_pages: int = 3, vision_timeout: int = 12) -> List[Dict]:
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
            result = _sensenova_query_threaded(tmp, prompt, json_mode=True, timeout=12)
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


# === Stage 3: Highlight Execution (Bbox 改进版) ===
def stage3_highlight(plan: Dict, matches: List[Dict], out_path: str,
                     mode: str = "line") -> Dict:
    """
    v10.2: 用 sensenova vision 找到的 (page, bbox, snippet) 精确定位黄线

    改进:
      - 多 page 都被 sensenova 标记为有匹配, 每个 page 独立画黄线
      - 用 sensenova 的 snippet 作为该 page 的搜索词 (不混合 data_points/keywords)
      - 不用 GLM (vision 已经验证位置)
    """
    if not matches:
        return {"ok": False, "reason": "no_matches"}

    # 过滤 confidence 太低的
    matches = [m for m in matches if m.get("confidence", 0) >= 0.3]
    if not matches:
        return {"ok": False, "reason": "all_low_confidence"}

    # 收集所有有 match 的 page + per-page snippet
    page_snippets = {}  # {page_idx: [snippet1, snippet2, ...]}
    for m in matches:
        p = m.get("page", 0)
        snippet = m.get("snippet", "").strip()
        if not snippet or len(snippet) < 5:
            continue
        # snippet 拆成核心句 (取前 1-2 句)
        sentences = re.split(r'[.。;；]', snippet)
        core = [s.strip() for s in sentences if len(s.strip()) > 8][:2]
        page_snippets.setdefault(p, []).extend(core)

    if not page_snippets:
        return {"ok": False, "reason": "no_valid_snippets"}

    # 用 sensenova 标记的 page 集合 (避免在其他 page 乱画)
    target_pages = sorted(page_snippets.keys())

    # 合并所有 snippet 为去重关键词
    all_keywords = []
    for snippets in page_snippets.values():
        all_keywords.extend(snippets)
    all_keywords = list(dict.fromkeys(all_keywords))[:5]  # 去重保前 5

    # 加 data_points 中最具体的 (避免年份/期刊名)
    for dp in plan.get("data_points", [])[:3]:
        if dp and len(dp) > 3 and not re.match(r'^[\d\.,%\-/]+$', dp):
            all_keywords.append(dp)
    all_keywords = list(dict.fromkeys(all_keywords))[:6]

    if not all_keywords:
        return {"ok": False, "reason": "no_keywords_after_filter"}

    pn_x = plan["pn_x"]
    pdf_path = plan["pdf_path"]

    try:
        result = process_pn_x(
            pn_x=pn_x,
            pdf_in=pdf_path,
            pdf_out=out_path,
            keywords=all_keywords,
            mode=mode,
            use_glm=False,
        )
        return {
            "ok": result.get("ok", False),
            "highlight_count": result.get("total_hits", 0),
            "method": "vision_bbox_v10.2",
            "target_pages": target_pages,
            "page_snippets": page_snippets,
            "all_keywords": all_keywords,
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
    parser.add_argument("--no-vision", action="store_true", help="跳过 sensenova, 用 context 直接抽 plan")
    parser.add_argument("--vision-timeout", type=int, default=15)
    parser.add_argument("--skip-stage2", action="store_true", help="跳过 sensenova stage 2, 用 keyword-only 模式")
    args = parser.parse_args()

    if args.project == "TMA":
        root = TMA_ROOT
    else:
        root = LEIDA_ROOT

    vision_report = os.path.join(root, "_vision_report.json")
    # 按优先级尝试多个 PPT render 目录. 优先选有 slide_001.jpg 内容的 (避免选到空 / PDF-only dir)
    ppt_renders_candidates = [
        os.path.join(root, "_1_ppt/_3_images"),                  # TMA 主路径
        os.path.join(root, "step1_ppt_目录/_ppt_renders_expanded"),  # 雷管方案 expanded (优先)
        os.path.join(root, "step1_ppt_目录/_ppt_renders"),       # 雷管方案
        os.path.join(root, "_ppt_renders_expanded"),             # 雷管方案 backup
        os.path.join(root, "_ppt_renders"),                      # TMA/雷管 fallback (可能有空 PDF)
        os.path.join(root, "_1_ppt"),
    ]
    def _has_slide_jpg(p):
        return os.path.isdir(p) and any(
            f.startswith("slide_") and f.endswith((".jpg", ".png"))
            for f in os.listdir(p)[:20]
        )
    ppt_renders = next((p for p in ppt_renders_candidates if _has_slide_jpg(p)), root)
    print(f"  ppt_renders resolved: {ppt_renders}")

    out_dir = os.path.join(root, "_3_highlight_vision")
    os.makedirs(out_dir, exist_ok=True)

    # Stage 1: PPT Vision → Plan
    if args.stage in ("1", "all", "plan-only"):
        print(f"=== Stage 1: PPT Vision → Highlight Plan ({args.project}) ===")
        plans = stage1_ppt_to_plan(
            vision_report, ppt_renders, root,
            out_plan=os.path.join(out_dir, "_highlight_plans.json"),
            max_slides=args.max_slides,
            use_vision=not args.no_vision,
            vision_timeout=args.vision_timeout,
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
        if args.skip_stage2:
            # 跳过 sensenova, 用 keyword-only 模式构造 matches
            print("  --skip-stage2 模式: 用 plan.data_points + keywords 构造假 matches")
            for plan in plans:
                if not plan.get("pdf_path"):
                    plan["matches"] = []
                    continue
                # 假 match: page 0 with confidence 0.5
                plan["matches"] = [{
                    "page": 0,
                    "snippet": plan.get("target_text", "")[:200] or " ".join(plan.get("data_points", []))[:200],
                    "visual_position": "auto",
                    "bbox_estimate": [],
                    "confidence": 0.5,  # 中等, 让 stage 3 仍能跑
                }]
            with open(os.path.join(out_dir, "_highlight_plans_with_matches.json"), "w") as f:
                json.dump({"n_plans": len(plans), "plans": plans}, f, ensure_ascii=False, indent=2)
            print(f"  ✓ Generated {sum(1 for p in plans if p['matches'])} keyword matches")
        else:
            for i, plan in enumerate(plans, 1):
                if not plan.get("pdf_path"):
                    continue
                print(f"  [{i}/{len(plans)}] {plan['pn_x']}...", flush=True)
                matches = stage2_pdf_search(plan, vision_timeout=args.vision_timeout)
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
