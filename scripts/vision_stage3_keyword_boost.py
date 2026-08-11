#!/usr/bin/env python3
"""
vision_stage3_keyword_boost.py — PDF 摘要反向抽 keyword 改进 stage 3 (2026-08-11)

思路: 不用 PPT 短句抽 keyword (粒度太粗), 改用 L4 从 PDF 摘要/正文前几页
      反向抽 medical terms. 这样 v10.1 highlight 命中率更高.

用法:
  python3 vision_stage3_keyword_boost.py --project TMA [--max-plans 10]
"""
import os, sys, json, re
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from l4_keyword_extract import extract_keywords_v2

import fitz  # PyMuPDF


TMA_ROOT = "/Users/david/Desktop/TMA_文献整理"
LEIDA_ROOT = "/Users/david/Desktop/雷管方案_文献整理"


def _find_pdf(project_root: str, pn_x: str, pdf_dir: str = "_2_pdfs") -> Optional[str]:
    """兼容 flat + nested, 自动检测项目 PDF 目录"""
    # 优先 _2_pdfs (TMA flat)
    candidates = [pdf_dir, "step3_pdf下载_160目录", "step3_pdf", "_pdfs_real"]
    seen = set()
    for d in candidates:
        if d in seen:
            continue
        seen.add(d)
        full = os.path.join(project_root, d)
        if not os.path.isdir(full):
            continue
        # flat: Pn-x_main.pdf
        for f in os.listdir(full):
            if f.startswith(pn_x + "_") and f.lower().endswith(".pdf"):
                return os.path.join(full, f)
            if f == f"{pn_x}.pdf":
                return os.path.join(full, f)
        # nested: Pn-x/main.pdf 或 Pn-x/Pn-x_main_*.pdf
        nested_dir = os.path.join(full, pn_x)
        if os.path.isdir(nested_dir):
            # main.pdf
            for f in os.listdir(nested_dir):
                if f.lower() == "main.pdf" or (f.startswith(pn_x + "_main") and f.lower().endswith(".pdf")):
                    return os.path.join(nested_dir, f)
    return None


def _read_pdf_abstract(pdf_path: str, max_pages: int = 2, max_chars: int = 3000) -> str:
    """读 PDF 前 N 页作为摘要, 截断到 max_chars"""
    doc = fitz.open(pdf_path)
    text = ""
    for p in range(min(max_pages, doc.page_count)):
        text += doc[p].get_text() + "\n"
        if len(text) > max_chars:
            break
    doc.close()
    return text[:max_chars]


def _extract_keywords_from_pdf(pdf_path: str) -> List[str]:
    """从 PDF 摘要用 L4 抽 keyword"""
    abstract = _read_pdf_abstract(pdf_path, max_pages=2)
    if not abstract or len(abstract) < 50:
        return []

    # L4 extract_keywords_v2 需要 citation + visual_context
    # 用 PDF 摘要作为 citation (因为它本身就是关于这篇 paper 的描述)
    keywords_with_score = extract_keywords_v2(
        citation=abstract[:500],  # 用摘要前 500 字
        visual_context="",  # 没视觉
        min_confidence=0.3,
        max_keywords=10,
        use_glm=False,  # 不调 GLM, 纯 L4
    )
    return [k["term"] for k in keywords_with_score]


def boost_plans_with_pdf_keywords(plan_path: str, out_path: Optional[str] = None) -> Dict:
    """
    给 plans 里的每个 PDF 反向抽 keyword, 替换 plan.data_points/keywords
    """
    with open(plan_path) as f:
        d = json.load(f)
    plans = d.get("plans", [])

    n_boosted = 0
    n_no_pdf = 0
    n_no_kw = 0

    # 检测 project_root 从 plan_path 推断
    plan_path_norm = os.path.abspath(plan_path)
    # 路径格式: <root>/_3_highlight_vision/_highlight_plans.json
    if "_3_highlight_vision" in plan_path_norm:
        project_root = plan_path_norm.split("_3_highlight_vision")[0].rstrip("/")
    else:
        project_root = os.path.dirname(os.path.dirname(plan_path_norm))

    pdf_dir = "_2_pdfs"  # default

    for plan in plans:
        # 优先用 plan.pdf_path, 否则自己找
        pdf_path = plan.get("pdf_path")
        if not pdf_path or not os.path.isfile(pdf_path):
            pn_x = plan.get("pn_x", "")
            pdf_path = _find_pdf(project_root, pn_x, pdf_dir)
            if pdf_path:
                plan["pdf_path"] = pdf_path

        if not pdf_path or not os.path.isfile(pdf_path):
            n_no_pdf += 1
            continue

        # 抽 PDF keyword
        pdf_keywords = _extract_keywords_from_pdf(pdf_path)
        if not pdf_keywords:
            n_no_kw += 1
            continue

        # 合并: plan 原 keywords + PDF keywords (去重)
        plan_kw = plan.get("keywords", [])
        plan_dp = plan.get("data_points", [])

        # 优先 PDF 关键词 (它们是真匹配的)
        merged = list(dict.fromkeys(pdf_keywords + plan_kw + plan_dp))

        plan["data_points_boosted"] = pdf_keywords
        plan["data_points"] = pdf_keywords[:8]  # v10.1 限制
        plan["keywords"] = merged[:10]

        n_boosted += 1

    if out_path:
        with open(out_path, "w") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

    return {
        "n_plans": len(plans),
        "n_boosted": n_boosted,
        "n_no_pdf": n_no_pdf,
        "n_no_kw": n_no_kw,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", choices=["TMA", "雷管方案"], default="TMA")
    parser.add_argument("--plan-file", help="默认 _highlight_plans.json")
    parser.add_argument("--out-file", help="默认覆盖原 file")
    parser.add_argument("--max-plans", type=int, default=0)
    args = parser.parse_args()

    root = TMA_ROOT if args.project == "TMA" else LEIDA_ROOT
    plan_file = args.plan_file or os.path.join(root, "_3_highlight_vision", "_highlight_plans.json")
    out_file = args.out_file or plan_file

    if not os.path.isfile(plan_file):
        print(f"❌ {plan_file} 不存在")
        sys.exit(1)

    with open(plan_file) as f:
        d = json.load(f)
    if args.max_plans:
        d["plans"] = d["plans"][:args.max_plans]
        # 写回临时
        tmp_path = plan_file + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        plan_file = tmp_path
        out_file = tmp_path

    print(f"=== PDF 摘要反向抽 keyword ({args.project}) ===")
    print(f"输入: {plan_file}")
    stats = boost_plans_with_pdf_keywords(plan_file, out_file)
    print(f"  Plans: {stats['n_plans']}")
    print(f"  Boosted: {stats['n_boosted']}")
    print(f"  No PDF: {stats['n_no_pdf']}")
    print(f"  No keywords extracted: {stats['n_no_kw']}")
    print(f"输出: {out_file}")


if __name__ == "__main__":
    main()
