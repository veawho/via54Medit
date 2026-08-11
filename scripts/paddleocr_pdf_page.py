#!/usr/bin/env python3
"""
PaddleOCR PDF Page Parser — Phase 7 L2 (中量方案)

用途: 对 PDF 的指定页进行 PaddleOCR 识别, 输出结构化 JSON
   - 文字块: 文本 + 坐标 + 置信度
   - 表格识别 (PP-Structure): 如果检测到表格, 输出行/列/schema
   - 聚合: 文本按 y 坐标排序, 行/段合并

调用: python3 paddleocr_pdf_page.py <pdf_path> <page_num>
输出: stderr = 进度日志; stdout = JSON

依赖: PaddleOCR 3.7.0 + PaddlePaddle 3.3.1 (已在 hermes-agent venv)
"""

import json
import os
import sys
import traceback

import fitz  # PyMuPDF


def render_page_to_image(pdf_path: str, page_num: int, dpi: int = 200) -> str:
    """将 PDF 指定页渲染为 PNG 图片"""
    doc = fitz.open(pdf_path)
    page = doc[page_num - 1]  # 1-indexed → 0-indexed
    pix = page.get_pixmap(dpi=dpi)
    out_path = f"/tmp/paddleocr_p{page_num}_{os.getpid()}.png"
    pix.save(out_path)
    doc.close()
    return out_path


def group_rows_by_y(texts, scores, polys, y_gap: int = 30):
    """
    按 y 坐标分组: 同行的文本块合并 (y 坐标在 y_gap 像素内)
    返回: [{row: N, text: "xxx", y: y_mid, bbox: [x0,y0,x1,y1]}]
    """
    items = []
    for i, t in enumerate(texts):
        if scores[i] < 0.3:
            continue
        p = polys[i]
        x0 = min(pt[0] for pt in p)
        y0 = min(pt[1] for pt in p)
        x1 = max(pt[0] for pt in p)
        y1 = max(pt[1] for pt in p)
        y_mid = (y0 + y1) / 2
        items.append({
            "text": t, "score": round(float(scores[i]), 3),
            "x0": int(x0), "y0": int(y0), "x1": int(x1), "y1": int(y1),
            "y_mid": y_mid
        })

    # 按 y_mid 排序
    items.sort(key=lambda x: (x["y_mid"], x["x0"]))

    # 行分组: 如果 y_mid 差 > y_gap 则新行
    rows = []
    current_row = []
    current_y = None
    for item in items:
        if current_y is None or abs(item["y_mid"] - current_y) <= y_gap:
            current_row.append(item)
        else:
            rows.append(current_row)
            current_row = [item]
        current_y = item["y_mid"] if current_y is None else (current_y * 0.7 + item["y_mid"] * 0.3)

    if current_row:
        rows.append(current_row)

    # 合并行文本
    result = []
    for ri, row in enumerate(rows):
        texts_joined = "".join([r["text"] for r in row])
        x0 = min(r["x0"] for r in row)
        y0 = min(r["y0"] for r in row)
        x1 = max(r["x1"] for r in row)
        y1 = max(r["y1"] for r in row)
        avg_score = sum(r["score"] for r in row) / len(row)
        result.append({
            "row": ri + 1,
            "text": texts_joined,
            "score": round(avg_score, 3),
            "bbox": [x0, y0, x1, y1],
            "items": [{"text": r["text"], "bbox": [r["x0"], r["y0"], r["x1"], r["y1"]]} for r in row]
        })

    return result


def extract_table_data(rows, keywords=None):
    """
    从行分组的文本中尝试识别表格结构
    如果文本包含多个数字 + 中文名 的 pattern, 视为表格行
    """
    import re
    table_rows = []
    for row in rows:
        text = row["text"]
        # 找数字 pattern (如 14.4, 46.6, 84.3 等)
        nums = re.findall(r'\d+(?:\.\d+)?', text)
        # 找中文名 (2-4 字中文)
        names = re.findall(r'[\u4e00-\u9fff]{2,4}', text)

        # 如果一行同时有中文名和数字, 可能是表格行
        if len(nums) >= 1 and len(names) >= 1:
            table_rows.append({
                "row": row["row"],
                "text": text,
                "names": names,
                "values": [float(n) for n in nums],
                "bbox": row["bbox"],
                "score": row["score"]
            })

    return table_rows


def main():
    if len(sys.argv) < 3:
        print("Usage: paddleocr_pdf_page.py <pdf_path> <page_num>", file=sys.stderr)
        sys.exit(1)

    pdf_path = sys.argv[1]
    page_num = int(sys.argv[2])

    print(f"[L2] PaddleOCR parsing: {pdf_path} page {page_num}", file=sys.stderr)

    if not os.path.exists(pdf_path):
        print(f"[L2] ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    # 渲染 PDF 页为图片
    img_path = render_page_to_image(pdf_path, page_num)
    print(f"[L2] Rendered page {page_num} to {img_path} ({os.path.getsize(img_path)} bytes)", file=sys.stderr)

    # 用 PaddleOCR 识别
    try:
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(use_textline_orientation=True, lang='ch')
        print(f"[L2] PaddleOCR initialized, running inference...", file=sys.stderr)
        result = ocr.predict(img_path)
        r = result[0]

        texts = r['rec_texts']
        scores = r['rec_scores']
        polys = r['rec_polys']

        print(f"[L2] OCR found {len(texts)} text blocks", file=sys.stderr)

        # 行分组
        rows = group_rows_by_y(texts, scores, polys)
        print(f"[L2] Grouped into {len(rows)} rows", file=sys.stderr)

        # 表格识别
        table_rows = extract_table_data(rows)
        print(f"[L2] Detected {len(table_rows)} potential table rows", file=sys.stderr)

        # 输出 JSON
        output = {
            "page": page_num,
            "pdf": pdf_path,
            "ocr_blocks": len(texts),
            "rows": rows,
            "table_rows": table_rows,
            "has_table": len(table_rows) >= 3,
            "all_text": "\n".join(r["text"] for r in rows),
        }

        print(json.dumps(output, ensure_ascii=False, indent=2))

    except Exception as e:
        print(f"[L2] ERROR: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
    finally:
        # 清理临时图片
        if os.path.exists(img_path):
            os.remove(img_path)


if __name__ == "__main__":
    main()