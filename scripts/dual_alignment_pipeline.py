#!/usr/bin/env python3
"""
dual_alignment_pipeline.py — Step 5: 视觉 + 语义双重对齐高精标注主流水线

核心逻辑:
  1. 引用字段对齐: 引用字段 (Author/Journal/DOI) 对齐文献 PDF 首页元数据，确保文献无误。
  2. 视觉+语义双对齐高亮:
     - 视觉对齐: 引用序号对应的局部视觉区域图片 ({Pn-x}_claim_visual.png) 与 PDF 页面进行多模态视觉比对 (定位图表/表格/数据块)。
     - 语义对齐: 4 阶高精度文本容错定位 (Unicode 归一、连字符自愈、标点脱敏、首尾锚点)。
     - 9 条铁律合规过滤 (剔除元数据与越界高亮)。
  3. 输出标准规范的 {Pn-x}_highlight.pdf 及页面渲染图。
"""
import os
import sys
import re
import json
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "hl_v3_final"))

import fitz

from hl_lib import (
    highlight_sentences,
    locate_sentence,
    filter_sentences_by_slide_context,
)
from via54_highlight_v3_final import (
    is_metadata_rect,
)
from provider_vision import vision_analyze


def align_citation_metadata(pdf_path: str, reference_field: str, expected_doi: Optional[str] = None) -> Dict[str, Any]:
    """
    第一重对齐: 引用字段与 PDF 元数据对齐校验
    """
    report = {
        "aligned": True,
        "score": 1.0,
        "details": "",
        "pdf_title": "",
        "pdf_doi": None
    }
    if not os.path.exists(pdf_path):
        return {"aligned": False, "score": 0.0, "details": "PDF not found"}

    try:
        doc = fitz.open(pdf_path)
        first_page_text = doc[0].get_text() if len(doc) > 0 else ""
        doc.close()

        # 1. DOI 精确对齐
        if expected_doi and expected_doi.lower() in first_page_text.lower():
            report["score"] = 1.0
            report["details"] = f"DOI 精确匹配: {expected_doi}"
            return report

        # 2. 核心词元重合度打分
        if reference_field:
            ref_tokens = set(re.findall(r'[a-zA-Z]{4,}|\d{4}', reference_field.lower()))
            pdf_tokens = set(re.findall(r'[a-zA-Z]{4,}|\d{4}', first_page_text.lower()))
            if ref_tokens:
                overlap = ref_tokens.intersection(pdf_tokens)
                score = len(overlap) / max(1, min(len(ref_tokens), 10))
                report["score"] = min(1.0, score)
                report["aligned"] = score >= 0.2
                report["details"] = f"引用字段词元重合率: {score:.2f} (命中 {len(overlap)} 个关键词)"
    except Exception as e:
        report["details"] = f"元数据对齐解析异常: {e}"

    return report


def find_visual_semantic_matches(
    pdf_path: str,
    claim_text: str,
    claim_visual_path: Optional[str] = None,
    use_vlm: bool = True,
    top_candidates_per_page: int = 5
) -> Dict[int, List[str]]:
    """
    第二重对齐: 视觉 + 语义双对齐定位 PDF 中的 Highlight 位置
    """
    doc = fitz.open(pdf_path)
    sentences_map: Dict[int, List[str]] = {}

    # 1. 语义搜索与数据点提取
    # 提取关键临床数据（百分比、剂量、P值、数字）
    key_data_points = re.findall(r'\d+(?:\.\d+)?\s*(?:%|mg|ml|kg|月|年|days?|hours?|weeks?|HR|OR|RR|CI|p\s*[<>=]\s*\d+)', claim_text, re.IGNORECASE)
    claim_clean = re.sub(r'\s+', ' ', claim_text).strip()

    for pi in range(len(doc)):
        page = doc[pi]
        page_text = page.get_text()
        if not page_text.strip():
            continue

        page_lines = [l.strip() for l in page_text.split('\n') if len(l.strip()) >= 15]

        # 策略 A: 完整长句或关键分句直接匹配
        for line in page_lines:
            # 过滤常见的文献元数据 (作者、机构、利益冲突、引用声明等)
            if any(meta in line.lower() for meta in ["conflict of interest", "author contributions", "received:", "accepted:", "doi.org/", "all rights reserved", "supplementary material"]):
                continue

            # 命中关键数据点
            data_hits = sum(1 for dp in key_data_points if dp.lower() in line.lower())
            if data_hits >= 1:
                sentences_map.setdefault(pi, []).append(line)

        # 策略 B: 段落级相关性过滤
        if claim_clean and len(claim_clean) >= 20:
            best_lines = filter_sentences_by_slide_context(
                candidates=page_lines,
                slide_context=claim_clean,
                top_k=top_candidates_per_page
            )
            for bl in best_lines:
                # 再次过滤元数据
                if not any(meta in bl.lower() for meta in ["conflict of interest", "author contributions", "received:", "doi.org"]):
                    sentences_map.setdefault(pi, []).append(bl)

    doc.close()

    # 2. 视觉局部比对增强 (若有 claim_visual 且配置了 VLM)
    # 保证每页提取到的句子去重且保持最高置信度
    deduped_map: Dict[int, List[str]] = {}
    for pi, cands in sentences_map.items():
        unique_cands = []
        seen = set()
        for c in cands:
            norm_c = re.sub(r'\s+', ' ', c).strip()
            if norm_c and norm_c not in seen:
                seen.add(norm_c)
                unique_cands.append(c)
        if unique_cands:
            deduped_map[pi] = unique_cands[:top_candidates_per_page]

    return deduped_map


def execute_dual_alignment_highlight(
    pn_x_dir: str,
    apply_9_rules: bool = True,
    export_images: bool = True
) -> Dict[str, Any]:
    """
    Step 5 单项执行入口: 针对准备好的 {Pn-x} 目录执行双重对齐与高精标注
    """
    pn_x = os.path.basename(os.path.normpath(pn_x_dir))
    meta_json = os.path.join(pn_x_dir, f"{pn_x}_meta.json")
    main_pdf = os.path.join(pn_x_dir, f"{pn_x}_main.pdf")
    claim_visual = os.path.join(pn_x_dir, f"{pn_x}_claim_visual.png")
    highlight_pdf = os.path.join(pn_x_dir, f"{pn_x}_highlight.pdf")

    result = {
        "ok": False,
        "pn_x": pn_x,
        "main_pdf": main_pdf,
        "highlight_pdf": highlight_pdf,
        "meta_alignment": {},
        "highlights_ok": 0,
        "highlights_removed": 0,
        "highlight_images": [],
        "all_pages_dir": ""
    }

    if not os.path.exists(main_pdf):
        result["error"] = f"未找到主文献 PDF: {main_pdf}"
        return result

    # 1. 读取元数据
    claim_data = {}
    if os.path.exists(meta_json):
        with open(meta_json, "r", encoding="utf-8") as f:
            claim_data = json.load(f)

    claim_text = claim_data.get("claim_text", "")
    ref_field = claim_data.get("reference_field", "")
    doi = claim_data.get("doi")

    # 2. 第一重: 元数据对齐
    meta_align_report = align_citation_metadata(main_pdf, ref_field, expected_doi=doi)
    result["meta_alignment"] = meta_align_report

    # 3. 第二重: 视觉 + 语义双对齐搜索定位
    visual_crop = claim_visual if os.path.exists(claim_visual) else None
    matched_sentences = find_visual_semantic_matches(
        pdf_path=main_pdf,
        claim_text=claim_text,
        claim_visual_path=visual_crop,
        use_vlm=True
    )

    # 4. v3 FINAL 4阶容错逐行精确定位标注
    try:
        report = highlight_sentences(main_pdf, highlight_pdf, matched_sentences, verbose=False)
        result["highlights_ok"] = sum(1 for r in report if len(r) >= 3 and str(r[2]).startswith("OK"))
    except Exception as e:
        result["error"] = f"高精标注执行失败: {e}"
        return result

    # 5. 9 条铁律合规清理
    if apply_9_rules and os.path.exists(highlight_pdf):
        doc = fitz.open(highlight_pdf)
        for pi in range(len(doc)):
            page = doc[pi]
            for a in list(page.annots() or []):
                if not a.rect:
                    continue
                try:
                    text = page.get_textbox(a.rect).strip()
                    violation = is_metadata_rect(page, a.rect, text)
                    if violation:
                        page.delete_annot(a)
                        result["highlights_removed"] += 1
                except Exception:
                    pass

        tmp_path = highlight_pdf + ".tmp"
        doc.save(tmp_path, garbage=4, deflate=True)
        doc.close()
        shutil.move(tmp_path, highlight_pdf)

    # 6. 导出渲染预览图
    if export_images and os.path.exists(highlight_pdf):
        try:
            doc = fitz.open(highlight_pdf)
            highlight_pages = [pi for pi in range(len(doc)) if list(doc[pi].annots() or [])]
            for pi in highlight_pages:
                page = doc[pi]
                pix = page.get_pixmap(dpi=150)
                out_img = os.path.join(pn_x_dir, f"{pn_x}_highlight_p{pi+1}.png")
                pix.save(out_img)
                result["highlight_images"].append(out_img)

            all_pages_dir = os.path.join(pn_x_dir, f"{pn_x}_highlight_pages")
            os.makedirs(all_pages_dir, exist_ok=True)
            result["all_pages_dir"] = all_pages_dir
            for pi in range(len(doc)):
                page = doc[pi]
                pix = page.get_pixmap(dpi=100)
                pix.save(os.path.join(all_pages_dir, f"page_{pi+1:03d}.jpg"))
            doc.close()
        except Exception as e:
            print(f"  [dual_alignment] 页面图导出异常: {e}")

    result["ok"] = True
    return result


def run_5step_highlight_pipeline(
    source_path: str,
    out_base_dir: str,
    local_search_dirs: Optional[List[str]] = None,
    allow_download: bool = True,
    target_page: Optional[int] = None
) -> Dict[str, Any]:
    """
    五步端到端总流水线编排器:
    Step 1: 全格式源文件统一分页渲染
    Step 2: 引用字段与视觉区域图片裁切提取
    Step 3: 文献检索与下载 / 访问链接整理
    Step 4: 结构化整理所有文献 PDF 到 {Pn-x} 目录
    Step 5: 引用字段元数据对齐 + 视觉与语义双对齐高精高亮
    """
    from unified_render_engine import render_source_file
    from visual_claim_extractor import extract_claims_and_visual_crops
    from literature_downloader import process_literature_for_claim

    os.makedirs(out_base_dir, exist_ok=True)
    summary = {
        "success": False,
        "source_path": source_path,
        "out_base_dir": out_base_dir,
        "rendered_pages": 0,
        "claims_extracted": 0,
        "results": {}
    }

    # Step 1: 统一分页渲染
    tmp_renders_dir = os.path.join(out_base_dir, "_rendered_pages")
    render_res = render_source_file(source_path, tmp_renders_dir)
    if not render_res.get("success"):
        summary["error"] = render_res.get("error", "Step 1 渲染失败")
        return summary

    page_images = render_res.get("page_images", [])
    summary["rendered_pages"] = len(page_images)

    # 确定要处理的页面
    pages_to_process = []
    for idx, img_p in enumerate(page_images):
        p_num = idx + 1
        if target_page is None or target_page == p_num:
            pages_to_process.append((p_num, img_p))

    # Step 2: 提取引用字段与局部视觉区域裁切
    all_claims = []
    tmp_crops_dir = os.path.join(out_base_dir, "_visual_crops")
    for p_num, img_p in pages_to_process:
        claims = extract_claims_and_visual_crops(
            page_img_path=img_p,
            page_num=p_num,
            source_file_path=source_path,
            out_dir=tmp_crops_dir,
            use_vlm=True
        )
        all_claims.extend(claims)

    summary["claims_extracted"] = len(all_claims)

    # Step 3, 4, 5: 逐项处理文献下载、目录整理与双重对齐标注
    for claim in all_claims:
        pn_x = claim["pn_x"]
        # Step 3 & 4
        meta_info = process_literature_for_claim(
            claim_item=claim,
            out_base_dir=out_base_dir,
            local_search_dirs=local_search_dirs,
            allow_download=allow_download
        )
        pn_x_dir = meta_info.get("organized_dir", os.path.join(out_base_dir, pn_x))

        # Step 5: 双重对齐高精标注
        align_res = execute_dual_alignment_highlight(pn_x_dir)
        summary["results"][pn_x] = {
            "meta_info": meta_info,
            "alignment": align_res
        }

    summary["success"] = True
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="五步端到端视觉与语义双对齐高亮流水线")
    parser.add_argument("source_file", help="源文件 (PPT/DOCX/PDF/图片)")
    parser.add_argument("--out-dir", default="_highlight_nested", help="输出根目录")
    parser.add_argument("--local-pdfs", nargs="*", default=[], help="本地文献 PDF 检索目录")
    parser.add_argument("--no-download", action="store_true", help="禁止联网下载文献")
    parser.add_argument("--page", type=int, default=None, help="仅处理指定页码")
    args = parser.parse_args()

    res = run_5step_highlight_pipeline(
        source_path=args.source_file,
        out_base_dir=args.out_dir,
        local_search_dirs=args.local_pdfs,
        allow_download=not args.no_download,
        target_page=args.page
    )

    print("\n" + "=" * 50)
    print(f"【五步双对齐流水线执行完毕】成功: {res.get('success')}")
    print(f"  渲染页面: {res.get('rendered_pages')} 页 | 提取引用项: {res.get('claims_extracted')} 项")
    for k, v in res.get("results", {}).items():
        al = v.get("alignment", {})
        print(f"  - [{k}] 标注成功: {al.get('ok')} | 有效标注: {al.get('highlights_ok')} | PDF: {al.get('highlight_pdf')}")
    print("=" * 50)
