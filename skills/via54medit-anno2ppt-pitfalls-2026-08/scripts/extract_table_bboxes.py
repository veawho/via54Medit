#!/usr/bin/env python3
"""
PDF 表格 bbox 严格配对抽取器 — P3-3 Fig.2 实战验证版

功能: 从 PDF 指定页抽取 (disease, value) bbox 对, y 坐标严格 3pt 匹配
坑: y 容差太宽 (>5pt) 会导致错位 (肝癌 14.4 vs 胰腺癌 8.5)
修法: < 3pt 严格匹配 + disease 按 y_mid 排序 + 同 disease 只配一个 value

用法:
    python3 extract_table_bboxes.py <pdf_path> <page_num> [--output /tmp/rows.json]

依赖: PyMuPDF (已装). 无须 LLM, 纯算法.
"""

import argparse
import json
import os
import re
import sys

import fitz  # PyMuPDF


# 27 种癌肿 (P3-3 Fig.2 实际顺序, 中英文映射)
DISEASE_ZH = {
    "Pancreas": "胰腺癌",
    "Liver": "肝癌",
    "Gallbladder": "胆囊癌",
    "Esophagus": "食管癌",
    "Lung": "肺癌",
    "Leukemia": "白血病",
    "Stomach": "胃癌",
    "Brain": "脑癌",
    "Bone": "骨癌",
    "Ovary": "卵巢癌",
    "Other thoracic organs": "其他胸部器官癌",
    "Lymphoma": "淋巴瘤",
    "All": "所有癌种合计",
    "Oral/Pharynx": "口腔/咽癌",
    "Melanoma of skin": "皮肤黑色素瘤",
    "All others": "其他所有癌种",
    "Larynx": "喉癌",
    "Colon-rectum": "结直肠癌",
    "Nasopharynx": "鼻咽癌",
    "Kidney": "肾癌",
    "Cervix": "宫颈癌",
    "Uterus": "子宫癌",
    "Prostate": "前列腺癌",
    "Bladder": "膀胱癌",
    "Testis": "睾丸癌",
    "Breast": "乳腺癌",
    "Thyroid": "甲状腺癌",
}


def extract_disease_and_value_blocks(page, skip_top=70, skip_bottom=730):
    """提取 disease 名 + 数值 block 列表 (跳过页眉页脚)"""
    text_dict = page.get_text("dict")
    disease_items = []
    value_items = []

    for block in text_dict["blocks"]:
        if "lines" not in block:
            continue
        for line in block["lines"]:
            bbox = line["bbox"]
            text = "".join([s["text"] for s in line["spans"]]).strip()
            if bbox[1] < skip_top or bbox[3] > skip_bottom:
                continue
            # disease 名 (英文, 已知 27 种之一)
            for en in DISEASE_ZH.keys():
                if text == en or text.replace(" ", "") == en.replace(" ", ""):
                    disease_items.append({
                        "name": en,
                        "y_mid": (bbox[1] + bbox[3]) / 2,
                        "bbox": bbox,
                    })
                    break
            else:
                # 数值 (x.x 格式)
                if re.match(r"^\d+\.\d+$", text):
                    try:
                        v = float(text)
                        value_items.append({
                            "value": v,
                            "y_mid": (bbox[1] + bbox[3]) / 2,
                            "bbox": bbox,
                        })
                    except ValueError:
                        pass

    return disease_items, value_items


def pair_disease_value_strict(disease_items, value_items, y_tolerance=3.0):
    """严格 y < 3pt 配对 (避免错位)"""
    rows = []
    used_values = set()
    for d in disease_items:
        best_v = None
        best_diff = float("inf")
        for vi, v in enumerate(value_items):
            if vi in used_values:
                continue
            diff = abs(d["y_mid"] - v["y_mid"])
            if diff < y_tolerance and diff < best_diff:
                best_v = vi
                best_diff = diff
        if best_v is not None:
            v = value_items[best_v]
            used_values.add(best_v)
            x0 = min(d["bbox"][0], v["bbox"][0])
            y0 = min(d["bbox"][1], v["bbox"][1])
            x1 = max(d["bbox"][2], v["bbox"][2])
            y1 = max(d["bbox"][3], v["bbox"][3])
            rows.append({
                "Disease": DISEASE_ZH[d["name"]],
                "Value": v["value"],
                "Unit": "%",
                "Geography": "中国",
                "BBox": {
                    "X0": round(x0, 1),
                    "Y0": round(y0, 1),
                    "X1": round(x1, 1),
                    "Y1": round(y1, 1),
                },
            })
    rows.sort(key=lambda r: -r["Value"])  # 从高到低排
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_path")
    parser.add_argument("page_num", type=int)
    parser.add_argument("--output", "-o", default="/tmp/table_rows.json")
    parser.add_argument("--y-tolerance", type=float, default=3.0)
    args = parser.parse_args()

    if not os.path.exists(args.pdf_path):
        print(f"ERROR: PDF not found: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)

    doc = fitz.open(args.pdf_path)
    if args.page_num < 1 or args.page_num > len(doc):
        print(f"ERROR: page {args.page_num} out of range (1-{len(doc)})", file=sys.stderr)
        sys.exit(1)
    page = doc[args.page_num - 1]

    disease_items, value_items = extract_disease_and_value_blocks(page)
    rows = pair_disease_value_strict(disease_items, value_items, args.y_tolerance)

    print(f"[extract_table_bboxes] {args.pdf_path} page {args.page_num}", file=sys.stderr)
    print(f"  found {len(disease_items)} disease blocks, {len(value_items)} value blocks", file=sys.stderr)
    print(f"  matched {len(rows)} (disease, value) pairs (y_tolerance={args.y_tolerance}pt)", file=sys.stderr)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"  wrote {args.output}", file=sys.stderr)

    doc.close()


if __name__ == "__main__":
    main()