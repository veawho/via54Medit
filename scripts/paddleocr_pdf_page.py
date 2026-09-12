#!/usr/bin/env python3
"""
PaddleOCR PDF Page Parser — Phase 7 L2 (中量方案)

用途: 对 PDF 的指定页进行 PaddleOCR 识别, 输出结构化 JSON
   - 文字块: 文本 + 坐标 + 置信度
   - 行/段合并: 按 y 坐标把文字块聚成行
   - 疑似表格行: 从行文本里按"同时出现中文名与数字"的启发式挑出来

调用: python3 paddleocr_pdf_page.py <pdf_path> <page_num>
      python3 paddleocr_pdf_page.py --smoke          # 真识别自检(部署/复检用)
输出: stderr = 进度日志; stdout = JSON

依赖: PaddleOCR 3.x + PaddlePaddle 3.x + PyMuPDF。

**注意 (2026-09-12)**: 这个脚本**必须**用装了 paddleocr 的那个解释器运行。
本机实测过一个真实故障: `python3.11` 有 pymupdf 却没有 paddleocr, 而 `python3` 两个都有 ——
`ResolvePython` 先按名字挑到 python3.11, 于是 `medit anno2ppt ocr` 直接 ModuleNotFoundError,
而部署报告因为用的是**另一个**解释器探测, 仍然写着"PaddleOCR 已就绪"。
现在调用方按"能不能 import"挑解释器(见 foundation.ResolvePythonFor 与
deploy_scan.ocr_python), 本脚本的 ``--smoke`` 也用于把这个选择结果验一遍。

关于"表格识别": 早期文档写作 PP-Structure, 但实现里并没有引入它 —— 只有上面那条
行/数字启发式。这里如实描述, 不再声称用了 PP-Structure。
"""

import json
import os
import sys
import tempfile
import traceback

import pymupdf as fitz  # PyMuPDF


def _temp_png_path(tag: str) -> str:
    """临时 PNG 路径。

    **不用** 硬编码 ``/tmp`` —— 那是 POSIX 假设, Windows 上 ``C:\\tmp`` 通常不存在,
    渲染会在第一步就失败(部署扫描器的平台兼容段一直在报这条)。
    """
    fd, path = tempfile.mkstemp(prefix="paddleocr_%s_" % tag, suffix=".png")
    os.close(fd)
    return path


def render_page_to_image(pdf_path: str, page_num: int, dpi: int = 200) -> str:
    """将 PDF 指定页渲染为 PNG 图片"""
    doc = fitz.open(pdf_path)
    try:
        page = doc[page_num - 1]  # 1-indexed → 0-indexed
        pix = page.get_pixmap(dpi=dpi)
        out_path = _temp_png_path("p%d" % page_num)
        pix.save(out_path)
    finally:
        doc.close()
    return out_path


def run_ocr_on_image(img_path: str):
    """跑一次 PaddleOCR 推理, 返回第一条结果对象。

    单独抽出来是为了让**真实业务路径**与 ``--smoke`` 自检走同一段代码:
    自检若与业务不同源, 它验过的就不是真正会跑的那条路。
    """
    from paddleocr import PaddleOCR

    ocr = PaddleOCR(use_textline_orientation=True, lang="ch")
    result = ocr.predict(img_path)
    return (result or [None])[0]


def smoke_test() -> int:
    """真识别自检 —— 部署/复检用。返回进程退出码。

    为什么需要它: "能 import" 不等于 "能识别"。权重没下、ABI 不匹配、解释器选错,
    这三种情况在 import 阶段都可能看不出来, 只有真跑一次才会暴露。
    这里自造一张带文字的图(Pillow 直接画, 不依赖任何外部素材), 跑完断言拿到非空文字。

    断言只要求"识别到非空文本", **不比对具体字符串** —— OCR 把 O 认成 D 是正常的
    (实测 "OCR 12345" → "DCR 12345", 置信度 0.996), 拿精确比对当门槛是自找假红。
    """
    text = os.environ.get("VIA54_OCR_SMOKE_TEXT", "OCR 12345")
    img_path = None
    try:
        from PIL import Image, ImageDraw, ImageFont

        font = None
        for p in ("/System/Library/Fonts/Supplemental/Arial.ttf",
                  "/System/Library/Fonts/Helvetica.ttc",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                  r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\arial.ttf"):
            if os.path.exists(p):
                try:
                    font = ImageFont.truetype(p, 64)
                    break
                except Exception:                           # noqa: BLE001
                    continue
        if font is None:
            try:
                font = ImageFont.load_default(size=64)      # Pillow >= 10.1
            except Exception:                               # noqa: BLE001
                font = ImageFont.load_default()

        img_path = _temp_png_path("smoke")
        image = Image.new("RGB", (520, 150), "white")
        # 只用数字与拉丁字母: Pillow 默认字体没有 CJK 字形, 画中文会变成方框 -> 假失败
        ImageDraw.Draw(image).text((20, 40), text, fill="black", font=font)
        image.save(img_path)

        r = run_ocr_on_image(img_path)
        if r is None:
            print("[L2][smoke] ERROR: 推理返回空结果", file=sys.stderr)
            return 1
        try:
            texts = list(r["rec_texts"])
        except Exception:                                   # noqa: BLE001
            texts = list(getattr(r, "rec_texts", None) or [])
        if not texts:
            print("[L2][smoke] ERROR: 模型加载成功但没识别出任何文字"
                  "(权重损坏或 ABI 不匹配)", file=sys.stderr)
            return 1
        print("[L2][smoke] OK: 识别到 %d 段文字 (%s)"
              % (len(texts), "".join(str(t) for t in texts)[:40]), file=sys.stderr)
        return 0
    except Exception as e:                                  # noqa: BLE001
        print("[L2][smoke] ERROR: %s: %s" % (type(e).__name__, str(e)[:200]), file=sys.stderr)
        return 1
    finally:
        if img_path and os.path.exists(img_path):
            os.remove(img_path)


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
    # --smoke: 真识别自检(部署/复检入口)。放在参数校验之前 —— 它不需要 PDF 参数。
    if "--smoke" in sys.argv[1:]:
        sys.exit(smoke_test())

    if len(sys.argv) < 3:
        print("Usage: paddleocr_pdf_page.py <pdf_path> <page_num>", file=sys.stderr)
        print("       paddleocr_pdf_page.py --smoke", file=sys.stderr)
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

    # 用 PaddleOCR 识别 (与 --smoke 自检同一段代码)
    try:
        print(f"[L2] PaddleOCR initialized, running inference...", file=sys.stderr)
        r = run_ocr_on_image(img_path)
        if r is None:
            raise RuntimeError("推理返回空结果")

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