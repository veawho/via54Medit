#!/usr/bin/env python3
"""
spot_check_semantic_highlights.py — 实际检查每个高亮 PDF

按 user 严肃要求 (2026-08-11):
> 不要猜测, 一切都需要实际对照、实际检查、实际验证

对每个 Pn-x_semantic_highlight.pdf:
- 渲染 highlight 后 PDF 的所有有黄线/黄框的页
- 列出每个 highlight 的 bbox + 覆盖的文本
- 人工 spot check 工具
"""
import os, sys, json, argparse
from pathlib import Path
import fitz
fitz.TOOLS.mupdf_display_warnings(False)

TMA_ROOT = "/Users/david/Desktop/TMA_文献整理"
LEIDA_ROOT = "/Users/david/Desktop/雷管方案_文献整理"


def list_highlights_in_pdf(pdf_path: str) -> dict:
    """列出 PDF 中所有 highlight annotation 的位置 + 文本"""
    doc = fitz.open(pdf_path)
    result = {
        "pages": [],
        "total_highlights": 0,
        "total_figures": 0,  # 边框 (rect draw)
    }

    for pno in range(doc.page_count):
        page = doc[pno]
        page_h = page.rect.height

        # Highlight annotations (PDF native)
        highlights = []
        for annot in page.annots() or []:
            if annot.type[0] == fitz.PDF_ANNOT_HIGHLIGHT:  # 8
                rect = annot.rect
                # 取 rect 内文字
                text = page.get_text("text", clip=rect).strip()
                highlights.append({
                    "type": "highlight_annot",
                    "bbox": [rect.x0, rect.y0, rect.x1, rect.y1],
                    "y_position": f"top {rect.y0/page_h*100:.1f}% - bottom {rect.y1/page_h*100:.1f}%",
                    "text": text[:200],
                    "color": annot.colors,
                })
        result["total_highlights"] += len(highlights)

        # Yellow draw_rect (no fill) → figure border
        figures = []
        for d in page.get_drawings():
            if d.get("type") == "s":  # stroke
                color = d.get("color")
                if color and len(color) >= 3 and color[0] > 0.9 and color[1] > 0.9 and color[2] < 0.3:
                    r = d["rect"]
                    if r.width > 5 and r.height > 5:  # 忽略细线
                        figures.append({
                            "type": "yellow_border",
                            "bbox": [r.x0, r.y0, r.x1, r.y1],
                            "y_position": f"top {r.y0/page_h*100:.1f}% - bottom {r.y1/page_h*100:.1f}%",
                        })
        result["total_figures"] += len(figures)

        if highlights or figures:
            result["pages"].append({
                "page_num": pno + 1,
                "highlights": highlights,
                "figures": figures,
            })

    doc.close()
    return result


def check_alignment(plan: dict, highlight_pdf: str, original_pdf: str) -> dict:
    """对比 plan.target_text 与 highlight 区域的 text 实际匹配度"""
    target = plan.get("target_text", "")
    if not target:
        return {"aligned": False, "reason": "no target_text"}

    # 取 highlight 信息
    info = list_highlights_in_pdf(highlight_pdf)

    # 找 body highlight 的文本
    highlight_texts = []
    for p in info["pages"]:
        for h in p["highlights"]:
            if h["text"]:
                highlight_texts.append(h["text"])

    if not highlight_texts:
        return {"aligned": False, "reason": "no_highlight_text", "info": info}

    # 简单相似度: target keywords 是否在 highlight text 中
    import re
    target_words = set(w.lower() for w in re.findall(r'\w+', target) if len(w) > 3)
    highlight_combined = " ".join(highlight_texts).lower()
    found = [w for w in target_words if w in highlight_combined]
    coverage = len(found) / max(len(target_words), 1)

    return {
        "aligned": coverage >= 0.3,
        "coverage": round(coverage, 3),
        "target_keywords_found": found[:10],
        "highlight_texts": highlight_texts,
        "highlight_count": info["total_highlights"],
        "figure_count": info["total_figures"],
    }


def render_spot_check(pdf_path: str, out_dir: str, max_pages: int = 5):
    """渲染有 highlight 的页为 jpg, 供人工 spot check"""
    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    rendered = 0
    for pno in range(min(max_pages, doc.page_count)):
        page = doc[pno]
        # 是否有 highlight
        has_hl = False
        for annot in page.annots() or []:
            if annot.type[0] == fitz.PDF_ANNOT_HIGHLIGHT:
                has_hl = True
                break
        if not has_hl:
            for d in page.get_drawings():
                if d.get("type") == "s" and d.get("color") and d["color"][0] > 0.9 and d["color"][1] > 0.9 and d["color"][2] < 0.3:
                    has_hl = True
                    break
        if has_hl:
            mat = fitz.Matrix(1.5, 1.5)
            pix = page.get_pixmap(matrix=mat)
            out = os.path.join(out_dir, f"page_{pno+1:02d}.jpg")
            pix.save(out)
            rendered += 1
    doc.close()
    return rendered


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", choices=["TMA", "雷管方案"], default="TMA")
    parser.add_argument("--pn-x", default="", help="只检查某个 Pn-x, 空=全部")
    parser.add_argument("--verify", action="store_true", help="检查 alignment")
    parser.add_argument("--render", action="store_true", help="渲染 spot check jpg")
    parser.add_argument("--out-dir", default="")
    args = parser.parse_args()

    if args.project == "TMA":
        root = TMA_ROOT
        sem_dir = os.path.join(TMA_ROOT, "_3_highlight_semantic")
        plans_path = os.path.join(TMA_ROOT, "_3_highlight_vision/_highlight_plans.json")
    else:
        root = LEIDA_ROOT
        sem_dir = os.path.join(LEIDA_ROOT, "_3_highlight_semantic")
        plans_path = os.path.join(LEIDA_ROOT, "_3_highlight_vision/_highlight_plans.json")

    with open(plans_path) as f:
        plans = {p["pn_x"]: p for p in json.load(f)["plans"]}

    # 找所有 semantic highlight PDFs
    if args.pn_x:
        pdfs = [f"{args.pn_x}_semantic_highlight.pdf"]
    else:
        pdfs = sorted([f for f in os.listdir(sem_dir) if f.endswith("_semantic_highlight.pdf")])

    summary_log = os.path.join(sem_dir, "_spot_check_log.json")
    log = []

    for fname in pdfs:
        pn_x = fname.replace("_semantic_highlight.pdf", "")
        fpath = os.path.join(sem_dir, fname)
        if not os.path.isfile(fpath):
            continue
        plan = plans.get(pn_x, {})
        target_text = plan.get("target_text", "")[:60]

        info = list_highlights_in_pdf(fpath)

        # 找原始 PDF 路径
        orig_pdf = plan.get("pdf_path", "")

        entry = {
            "pn_x": pn_x,
            "highlight_pdf": fpath,
            "orig_pdf": orig_pdf,
            "target_text": target_text,
            "highlight_count": info["total_highlights"],
            "figure_count": info["total_figures"],
            "pages_with_highlights": len(info["pages"]),
            "page_details": [],
        }

        for p in info["pages"]:
            page_detail = {
                "page": p["page_num"],
                "highlights": p["highlights"][:5],
                "figures": p["figures"][:3],
            }
            entry["page_details"].append(page_detail)

        if args.verify and plan and orig_pdf and os.path.isfile(orig_pdf):
            chk = check_alignment(plan, fpath, orig_pdf)
            entry["alignment_check"] = chk

        if args.render:
            out_r = args.out_dir or os.path.join(sem_dir, "_spot_check_imgs", pn_x)
            rendered = render_spot_check(fpath, out_r)
            entry["rendered_pages"] = rendered

        log.append(entry)

        # 打印简表
        if entry["highlight_count"] > 0 or entry["figure_count"] > 0:
            print(f"✓ {pn_x}: highlights={entry['highlight_count']}, figures={entry['figure_count']}, "
                  f"pages={entry['pages_with_highlights']}, target={target_text[:30]!r}")
        else:
            print(f"✗ {pn_x}: NO HIGHLIGHTS, target={target_text[:30]!r}")

    with open(summary_log, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(f"\n→ Log: {summary_log}")


if __name__ == "__main__":
    main()
