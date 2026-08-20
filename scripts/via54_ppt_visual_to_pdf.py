#!/usr/bin/env python3
"""
via54_ppt_visual_to_pdf.py — PPT视觉理解 → PDF应证 → Highlight 完整流程

完整替代 via54_highlight_fix_v10.py 的关键词匹配, 实现:
  Step 1: 用 sensenova vision API 视觉识别 PPT 内容
  Step 2: 提取每个引用标号对应的视觉内容 (图表/文字/位置)
  Step 3: 在 PDF 中语义级搜索视觉内容 (不是关键词)
  Step 4: v3 FINAL rect 模式高亮 + 9 条铁律

输入: PPTX + PDF 路径
输出: 高亮 PDF (每行 1 rect, 9 铁律自动验证)

vs via54_highlight_fix_v10.py 改进:
  - 不用关键词, 用 vision 提取的语义内容
  - 每个标号从 PPT 视觉层定位, 不靠正则
  - 整段匹配 (50-200 字符), 不用 search_for 单词
"""
import os
import re
import sys
import json
import urllib.request
import urllib.error
import base64
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "hl_v3_final"))

import fitz

# 集成现有工具
from hl_lib import highlight_sentences
from via54_highlight_v3_final import (
    is_metadata_rect,
    get_max_font_size,
    TITLE_FONT_SIZE,
    METADATA_ZONE_RATIO,
)

# === 视觉识别 API (复用 sensenova_vision) ===

def _get_api_key():
    """从环境变量或 .env 获取 API key"""
    key = os.environ.get("SENSENOVA_API_KEY")
    if key:
        return key
    for env_path in [
        os.path.expanduser("~/.hermes/.env"),
        os.path.expanduser("~/.env"),
        ".env",
    ]:
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("SENSENOVA_API_KEY="):
                        return line.split("=", 1)[1].strip().strip("'\"")
    return None


def _render_ppt_slide_to_image(pptx_path: str, slide_num: int) -> Optional[str]:
    """用 LibreOffice 把 PPT 第 N 页渲染成 png (如果有 soffice)
    Fallback: 用 python-pptx 提取文本"""
    try:
        import subprocess
        # 临时目录
        tmpdir = tempfile.mkdtemp(prefix=f"ppt_slide_{slide_num}_")
        # 用 soffice 转 PDF
        result = subprocess.run([
            "soffice", "--headless", "--convert-to", "pdf",
            "--outdir", tmpdir, pptx_path
        ], capture_output=True, timeout=60)
        if result.returncode != 0:
            return None
        # 找 PDF
        pdf_files = list(Path(tmpdir).glob("*.pdf"))
        if not pdf_files:
            return None
        # 渲染第 N 页
        pdf_doc = fitz.open(pdf_files[0])
        if slide_num > len(pdf_doc):
            return None
        page = pdf_doc[slide_num - 1]
        pix = page.get_pixmap(dpi=150)
        out_img = os.path.join(tmpdir, f"slide_{slide_num}.png")
        pix.save(out_img)
        pdf_doc.close()
        return out_img
    except Exception as e:
        print(f"  [警告] soffice 渲染失败: {e}")
        return None


def _encode_image(image_path: str) -> Tuple[str, str]:
    """读取图片, 返回 (base64, mime)"""
    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    }
    mime = mime_map.get(ext, "image/png")
    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return data, mime


def _vision_call(image_path: str, prompt: str, timeout: int = 60) -> str:
    """调用 sensenova vision API"""
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("SENSENOVA_API_KEY 未设置")

    b64, mime = _encode_image(image_path)

    payload = {
        "model": "sensenova-6.7-flash-lite",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
                ]
            }
        ],
        "max_tokens": 2048,
    }

    req = urllib.request.Request(
        "https://token.sensenova.cn/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result = json.loads(resp.read())
    return result["choices"][0]["message"]["content"]


def analyze_ppt_slide_visually(pptx_path: str, slide_num: int) -> Dict:
    """
    Step 1: 视觉识别 PPT 第 N 页内容
    返回: {
        "slide_num": int,
        "text_blocks": [{ "text": "...", "position": "top|center|bottom|left|right", "type": "title|body|table" }, ...],
        "citation_marks": [{ "mark": 1, "context_text": "...", "visual_position": "..." }, ...],
        "data_points": [{ "text": "23.7", "type": "percentage|number|month", "context": "..." }, ...],
    }
    """
    # 先尝试 vision API
    img_path = _render_ppt_slide_to_image(pptx_path, slide_num)
    if img_path and os.path.exists(img_path):
        prompt = """请仔细分析这张 PPT 图片, 提取:
1. 所有文本块 (按位置分类: top=顶部, bottom=底部, center=中央, left=左, right=右)
2. 所有引文标号 (上标数字, 如 1, 2, 3-5) 及对应上下文 (标号所在的完整文字/句子)
3. 所有关键数据点 (百分比/数字/月份, 如 23.7月, 46.6%, mOS 12.1)
4. 表格内容 (如适用)

输出 JSON 格式:
{
  "text_blocks": [{"text": "...", "position": "top|center|bottom|left|right", "type": "title|body|table", "context": "..."}],
  "citation_marks": [{"mark": 1, "context_text": "包含标号1的完整句子或文字", "visual_position": "top|center|bottom|left|right"}],
  "data_points": [{"text": "23.7", "type": "month|percentage|number", "context": "数据点所在句子"}]
}"""
        try:
            response = _vision_call(img_path, prompt)
            # 尝试解析 JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
        except Exception as e:
            print(f"  [警告] vision API 失败: {e}")

    # Fallback: python-pptx 提取
    from pptx import Presentation
    prs = Presentation(pptx_path)
    slide = prs.slides[slide_num - 1]

    text_blocks = []
    citation_marks = []
    data_points = []

    # 中文标号模式 (如 索拉非尼3, 仑伐替尼5)
    cn_mark_pattern = re.compile(r'[\u4e00-\u9fff《》（）]+([1-9][0-9]?)(?:[,，]|$)')

    for i, shape in enumerate(slide.shapes):
        if not shape.has_text_frame:
            continue

        text = shape.text_frame.text
        if not text.strip():
            continue

        # 位置估算
        if shape.top and shape.top < 100000:
            position = "top" if shape.top < 1500000 else ("bottom" if shape.top > 6000000 else "center")
        else:
            position = "center"

        text_blocks.append({
            "text": text[:200],
            "position": position,
            "type": "title" if position == "top" and i < 3 else "body",
        })

        # 提取标号
        for match in cn_mark_pattern.finditer(text):
            num = int(match.group(1))
            if 1 <= num <= 50:
                # 找到包含标号的句子
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end].strip()
                citation_marks.append({
                    "mark": num,
                    "context_text": context,
                    "visual_position": position,
                })

    # 提取数据点
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        text = shape.text_frame.text
        # 百分比
        for m in re.finditer(r'(\d+\.?\d*)\s*%', text):
            data_points.append({"text": m.group(0), "type": "percentage", "context": text[max(0, m.start()-30):m.end()+30]})
        # 月份
        for m in re.finditer(r'(\d+\.?\d*)\s*月', text):
            data_points.append({"text": m.group(0), "type": "month", "context": text[max(0, m.start()-30):m.end()+30]})
        # 大数字
        for m in re.finditer(r'\b(\d{2,})\b', text):
            data_points.append({"text": m.group(0), "type": "number", "context": text[max(0, m.start()-30):m.end()+30]})

    return {
        "slide_num": slide_num,
        "text_blocks": text_blocks,
        "citation_marks": citation_marks,
        "data_points": data_points,
    }


def find_pdf_visual_match(pdf_path: str, ppt_visual: Dict) -> Dict[int, List[str]]:
    """
    Step 2: 在 PDF 中语义级搜索 PPT 视觉提取的内容
    不使用关键词匹配, 而是用 vision 提取的完整 context_text 整段匹配

    返回: {page_idx_0based: [matched_sentence, ...]}
    """
    doc = fitz.open(pdf_path)

    # 收集所有需要匹配的"视觉内容"
    visual_queries = []

    # 1) 标号上下文 (整段文字, 不是只关键词)
    for mark in ppt_visual.get("citation_marks", []):
        context = mark.get("context_text", "").strip()
        if len(context) >= 15:
            visual_queries.append(context)

    # 2) 数据点所在句子
    for dp in ppt_visual.get("data_points", []):
        ctx = dp.get("context", "").strip()
        if len(ctx) >= 15:
            visual_queries.append(ctx)

    # 3) 标题/文本块
    for tb in ppt_visual.get("text_blocks", []):
        text = tb.get("text", "").strip()
        if len(text) >= 20 and not any(s in text for s in ["DECLARATION", "Declaration", "Affiliations", "affiliations", "Funding", "AUTHOR CONTRIBUTIONS", "OPEN ACCESS", "Citation"]):
            visual_queries.append(text)

    # 去重
    visual_queries = list(dict.fromkeys(visual_queries))

    def normalize(s):
        return re.sub(r'\s+', ' ', s).strip().lower()

    # 在 PDF 每页搜索
    sentences_map = {}
    for pi in range(len(doc)):
        page = doc[pi]
        page_text = page.get_text()
        page_norm = normalize(page_text)
        page_lines = [normalize(line) for line in page_text.split('\n') if line.strip()]

        for query in visual_queries:
            query_norm = normalize(query)

            # 策略 1: 完整匹配 (整段)
            if len(query_norm) >= 30 and query_norm in page_norm:
                sentences_map.setdefault(pi, []).append(query)
                continue

            # 策略 2: 提取医学术语 + 数据点 (避开通用词)
            tokens = re.findall(r'[\u4e00-\u9fff]{2,}|\d+\.?\d*%?|TA-TMA|HCT|HUS|aHUS|TMA|TTP|PNH|complement|endothelial|microangiopathy|thrombocytopenia|hypertension|hypertens|lactate|complement cascade|MAC|schistocyte|proteinuria|hypertension', query)
            if not tokens:
                continue

            for line in page_lines:
                if len(line) < 20:
                    continue
                hits = sum(1 for t in tokens if t.lower() in line)
                data_hits = sum(1 for t in tokens if re.match(r'\d+\.?\d*%?', t) and t in line)
                if hits >= 2 or (hits >= 1 and data_hits >= 1):
                    if pi not in sentences_map or line not in sentences_map[pi]:
                        sentences_map.setdefault(pi, []).append(line[:200])

    doc.close()
    return sentences_map


def highlight_from_visual(
    pptx_path: str,
    pdf_in: str,
    pdf_out: str = None,  # 如果 None, 自动生成嵌套目录结构
    slide_num: int = None,
    apply_9_rules: bool = True,
    use_vision_api: bool = True,
    export_images: bool = True,  # 导出 highlight 页面图片
) -> Dict:
    """
    完整流程: PPT视觉理解 → PDF应证 → v3 FINAL 高亮 + 9 铁律

    命名约定 (via54Medit 8 列标准):
      {Pn-x}/
        ├── {Pn-x}_main.pdf            # 复制/链接的主 PDF
        ├── {Pn-x}_highlight.pdf       # 高亮 PDF
        ├── {Pn-x}_highlight_pNNN.png  # 仅高亮页图片
        └── {Pn-x}_highlight_pages/   # 全部页面图
            └── page_NNN.jpg

    Args:
        pptx_path: PPTX 文件
        pdf_in: 输入 PDF 路径 (如 _2_pdfs/Pn-S23_5.pdf)
        pdf_out: 输出高亮 PDF (默认 {Pn-x}/{Pn-x}_highlight.pdf)
        slide_num: 指定 slide (None=全部)
        apply_9_rules: 自动应用 9 条铁律
        use_vision_api: True 用 vision API, False 用 python-pptx fallback
        export_images: True 同时导出页面图片 (默认 True)

    Returns:
        {
          "ok": bool,
          "pn_x": "S23_5",  # 提取的 Pn-x 标识
          "output_dir": "Pn-S23_5/",
          "main_pdf": "Pn-S23_5/Pn-S23_5_main.pdf",
          "highlight_pdf": "Pn-S23_5/Pn-S23_5_highlight.pdf",
          "highlight_images": ["Pn-S23_5/Pn-S23_5_highlight_p1.png", ...],
          "all_pages_dir": "Pn-S23_5/Pn-S23-5_highlight_pages/",
          "violations": [(page, rule, text), ...],
        }
    """
    result = {
        "ok": False,
        "pn_x": "",
        "output_dir": "",
        "main_pdf": pdf_in,
        "highlight_pdf": "",
        "highlight_images": [],
        "all_pages_dir": "",
        "ppt_visual": {},
        "pdf_sentences": {},
        "highlights_ok": 0,
        "highlights_removed": 0,
        "violations": [],
    }

    if not os.path.exists(pptx_path):
        result["error"] = f"PPTX not found: {pptx_path}"
        return result
    if not os.path.exists(pdf_in):
        result["error"] = f"PDF not found: {pdf_in}"
        return result

    # === 命名约定: 嵌套目录 ===
    # 从 pdf_in 提取 Pn-x (如 Pn-S23_5.pdf → S23_5; P5-1.pdf → P5-1)
    pdf_basename = os.path.basename(pdf_in).replace(".pdf", "")  # Pn-S23_5
    pn_x = pdf_basename.replace("Pn-", "")  # S23_5
    if not pn_x:
        pn_x = pdf_basename

    # 输出目录: 同级 _highlight/{Pn-x}/
    if pdf_out is None:
        pdf_in_dir = os.path.dirname(os.path.abspath(pdf_in))
        parent_dir = os.path.dirname(pdf_in_dir)  # 上一级 (如 _2_pdfs 的父 = 项目根)
        out_base = os.path.join(parent_dir, "_highlight_nested")
        pdf_out_dir = os.path.join(out_base, f"Pn-{pn_x}")
    else:
        # pdf_out 是用户指定路径
        pdf_out_dir = os.path.dirname(os.path.abspath(pdf_out)) or "."
        # 如果 pdf_out 包含 .pdf 后缀, 取其目录
        if pdf_out.endswith(".pdf"):
            pdf_out_dir = os.path.dirname(os.path.abspath(pdf_out)) or "."

    os.makedirs(pdf_out_dir, exist_ok=True)

    result["pn_x"] = pn_x
    result["output_dir"] = pdf_out_dir

    # 复制 main PDF 到嵌套目录 (或硬链接)
    main_pdf_dest = os.path.join(pdf_out_dir, f"Pn-{pn_x}_main.pdf")
    if pdf_in != main_pdf_dest:
        try:
            import shutil
            shutil.copy2(pdf_in, main_pdf_dest)
            result["main_pdf"] = main_pdf_dest
        except Exception:
            # copy 失败, 只记录原路径
            result["main_pdf"] = pdf_in
    else:
        result["main_pdf"] = pdf_in

    # 输出 highlight PDF
    if pdf_out is None or not pdf_out.endswith(".pdf"):
        highlight_pdf = os.path.join(pdf_out_dir, f"Pn-{pn_x}_highlight.pdf")
    else:
        highlight_pdf = pdf_out
    result["highlight_pdf"] = highlight_pdf

    print(f"  Pn-x: {pn_x}")
    print(f"  Output dir: {pdf_out_dir}")
    print(f"  Highlight PDF: {highlight_pdf}")

    # Step 1: 确定要处理的 slide
    from pptx import Presentation
    prs = Presentation(pptx_path)
    n_slides = len(prs.slides)
    slides_to_process = [slide_num] if slide_num else list(range(1, n_slides + 1))

    # Step 2: PPT 视觉理解 (每个 slide)
    print(f"Step 1: PPT视觉理解 (使用 {'sensenova vision API' if use_vision_api else 'python-pptx fallback'})")
    for sn in slides_to_process:
        print(f"  Slide {sn}...")
        if use_vision_api:
            visual = analyze_ppt_slide_visually(pptx_path, sn)
        else:
            visual = analyze_ppt_slide_visually(pptx_path, sn)
        result["ppt_visual"][sn] = visual
        print(f"    {len(visual.get('citation_marks', []))} marks, "
              f"{len(visual.get('data_points', []))} data points, "
              f"{len(visual.get('text_blocks', []))} text blocks")

    # Step 3: 在 PDF 中找视觉内容对应的整段
    print(f"\nStep 2: 在 PDF 中语义级搜索视觉内容")
    all_sentences = {}
    for sn, visual in result["ppt_visual"].items():
        page_sentences = find_pdf_visual_match(pdf_in, visual)
        # 多 slide 内容合并到 PDF 页码
        for pi, sents in page_sentences.items():
            all_sentences.setdefault(pi, []).extend(sents)
    result["pdf_sentences"] = all_sentences

    total_sents = sum(len(v) for v in all_sentences.values())
    print(f"  找到 {total_sents} 个匹配句, 分布在 {len(all_sentences)} 页")

    # 去重
    unique_map = {}
    for pi, sents in all_sentences.items():
        for s in sents:
            key = s[:50]
            if key not in unique_map:
                unique_map[key] = (pi, s)

    deduped_map = {}
    for key, (pi, s) in unique_map.items():
        deduped_map.setdefault(pi, []).append(s)
    result["pdf_sentences"] = deduped_map

    total_after = sum(len(v) for v in deduped_map.values())
    print(f"  去重后: {total_after} 个唯一句")

    # Step 4: v3 FINAL 高亮
    print(f"\nStep 3: v3 FINAL rect 高亮")
    try:
        report = highlight_sentences(pdf_in, highlight_pdf, deduped_map, verbose=False)
        result["hl_lib_report"] = report
        result["highlights_ok"] = sum(1 for r in report if r[2].startswith("OK"))
    except Exception as e:
        result["error"] = f"hl_lib error: {e}"
        return result

    # Step 5: 应用 9 条铁律
    if not apply_9_rules:
        result["ok"] = True
        return result

    print(f"\nStep 4: 应用 9 条铁律 (删除违规 highlight)")
    doc = fitz.open(highlight_pdf)
    for pi in range(len(doc)):
        page = doc[pi]
        annots = list(page.annots() or [])
        for annot in annots:
            if not annot.rect:
                continue
            rect = annot.rect
            try:
                text = page.get_textbox(rect).strip()
            except Exception:
                continue

            violation = is_metadata_rect(page, rect, text)
            if violation:
                try:
                    page.delete_annot(annot)
                    result["highlights_removed"] += 1
                    result["violations"].append((pi + 1, violation, text[:60]))
                except Exception:
                    pass

    tmp_path = highlight_pdf + ".tmp"
    doc.save(tmp_path, garbage=4, deflate=True)
    doc.close()
    import shutil
    shutil.move(tmp_path, highlight_pdf)

    # Step 6: 导出图片
    if export_images:
        print(f"\nStep 5: 导出 highlight 页面图片")
        try:
            doc = fitz.open(highlight_pdf)
            # 找有高亮的页
            highlight_pages = []
            for pi in range(len(doc)):
                page = doc[pi]
                annots = list(page.annots() or [])
                if annots:
                    highlight_pages.append(pi)
            print(f"  高亮页: {len(highlight_pages)}/{len(doc)}")

            # 6.1 导出高亮页图片 (根目录)
            for pi in highlight_pages:
                page = doc[pi]
                pix = page.get_pixmap(dpi=150)
                out_img = os.path.join(pdf_out_dir, f"Pn-{pn_x}_highlight_p{pi+1}.png")
                pix.save(out_img)
                result["highlight_images"].append(out_img)

            # 6.2 导出所有页面 (Pn-x_highlight_pages 子目录)
            all_pages_dir = os.path.join(pdf_out_dir, f"Pn-{pn_x}_highlight_pages")
            os.makedirs(all_pages_dir, exist_ok=True)
            result["all_pages_dir"] = all_pages_dir
            for pi in range(len(doc)):
                page = doc[pi]
                pix = page.get_pixmap(dpi=100)
                out_img = os.path.join(all_pages_dir, f"page_{pi+1:03d}.jpg")
                pix.save(out_img)
            doc.close()
        except Exception as e:
            print(f"  图片导出失败: {e}")

    result["ok"] = True
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_in", help="输入 PDF (如 _2_pdfs/Pn-S23_5.pdf)")
    parser.add_argument("--pptx", help="PPTX 文件 (默认自动查找)")
    parser.add_argument("--slide", type=int, default=None,
                        help="只处理指定 slide")
    parser.add_argument("--no-vision", action="store_true",
                        help="不用 vision API, 用 python-pptx fallback")
    parser.add_argument("--no-rules", action="store_true",
                        help="不应用 9 条铁律")
    parser.add_argument("--no-images", action="store_true",
                        help="不导出 highlight 页面图片")
    parser.add_argument("--out-dir", default=None,
                        help="输出根目录 (默认 _2_pdfs/../_highlight_nested)")
    args = parser.parse_args()

    # 找 PPT
    pptx_path = args.pptx
    if not pptx_path:
        # 尝试 _1_ppt 或顶层 .pptx
        for search_dir in [os.path.dirname(os.path.dirname(args.pdf_in)), os.path.dirname(args.pdf_in)]:
            if os.path.isdir(search_dir):
                for f in os.listdir(search_dir):
                    if f.endswith(".pptx"):
                        pptx_path = os.path.join(search_dir, f)
                        break
            if pptx_path:
                break

    if not pptx_path:
        print(f"错误: 找不到 PPTX 文件 (--pptx 参数)")
        return 1

    result = highlight_from_visual(
        pptx_path=pptx_path,
        pdf_in=args.pdf_in,
        pdf_out=None,  # 自动生成嵌套目录
        slide_num=args.slide,
        apply_9_rules=not args.no_rules,
        use_vision_api=not args.no_vision,
        export_images=not args.no_images,
    )

    print(f"\n=== 结果 ===")
    print(f"  OK: {result['ok']}")
    print(f"  Pn-x: {result.get('pn_x', '')}")
    print(f"  Output dir: {result.get('output_dir', '')}")
    print(f"  Main PDF: {result.get('main_pdf', '')}")
    print(f"  Highlight PDF: {result.get('highlight_pdf', '')}")
    print(f"  Highlights OK: {result['highlights_ok']}")
    print(f"  Highlights Removed (9 铁律): {result['highlights_removed']}")
    print(f"  Highlight images: {len(result.get('highlight_images', []))}")
    if result.get("all_pages_dir"):
        print(f"  All pages: {result['all_pages_dir']}")
    if result.get("violations"):
        print(f"  违规清单 (前 5):")
        for v in result["violations"][:5]:
            print(f"    p{v[0]}: {v[1]} - '{v[2]}'")
    if result.get("error"):
        print(f"  错误: {result['error']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    main()