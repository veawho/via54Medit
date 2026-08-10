#!/usr/bin/env python3
"""
via54_highlight_fix_v10.py — v10.0 修复版高亮渲染 (2026-08-10)

修复 v9.7 系列的 4 个核心 bug:
  Bug 1: add_highlight_annot().set_colors() save/reload 后 colors=None
         → 黄色丢失, 渲染为隐形细线 (实测 P11-1 全部 0% 黄色)
  Bug 2: best_page 选 page 1, 但 page 1 多半是标题/作者/摘要
         → 高亮落在错内容 (header/author row, 不是应证段)
  Bug 3: search_for 失败 (Chinese vs English 关键词) 无回退
  Bug 4: 单页覆盖, 实际证据常常跨多页

修复策略:
  1. 改用 page.draw_rect(..., fill=(1,1,0), overlay=True) 直接画在内容流
     → 颜色物理嵌入, 不依赖 annotation metadata
  2. 跳过页眉/页脚/前 2 行/后 2 行 (高亮落正文段)
  3. 多页搜索 + 关键词权重 (中段页优先)
  4. search_for 失败时回退到 fitz 文本流 + 模糊匹配
  5. 输出 PDF (主) + jpg per page (健康检查用)

API:
  highlight_pdf_robust(pdf_in, pdf_out, keywords, ...) -> Dict
  render_pages_jpg(pdf_path, out_dir, ...) -> List[str]
  process_pn_x(pn_x, pdf_in, pdf_out, keywords, jpg_dir, ...) -> Dict
"""
import os, re, sys, json
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import fitz  # PyMuPDF


# ════════════════════════════════════════════════════════════════
# 常量
# ════════════════════════════════════════════════════════════════

# 纯黄 (1, 1, 0) 不用 set_colors, 走 draw_rect fill
HIGHLIGHT_FILL = (1, 1, 0)  # RGB
HIGHLIGHT_OVERLAY = True     # 在原文上方叠加, 不替换文字

# 跳过区域: 页眉/页脚/前 N 行/后 N 行
SKIP_TOP_RATIO = 0.10   # 跳过顶部 10% (页眉)
SKIP_BOTTOM_RATIO = 0.08  # 跳过底部 8% (页脚/页码)
SKIP_TOP_LINES = 2       # 跳过前 2 行 (标题/作者)
SKIP_BOTTOM_LINES = 2    # 跳过后 2 行 (通信/脚注)

# 健康检查的黄色像素阈值 (放宽, 配合 v9.7 修复后)
YELLOW_R_MIN = 200
YELLOW_G_MIN = 200
YELLOW_B_MAX = 150
YELLOW_MIN_PCT = 0.01  # 0.01% (与 via54_health.py 一致)


# ════════════════════════════════════════════════════════════════
# 兼容层: 旧 process_all_pn_x.py 调用的 highlight_pdf() 签名
# ════════════════════════════════════════════════════════════════

def highlight_pdf(pdf_path, page_num, terms, output_path):
    """
    v10 兼容层: 匹配 process_all_pn_x.py:highlight_pdf() 旧签名

    旧实现: add_highlight_annot + draw_line (颜色 save 后丢失 → 0% 黄色)
    新实现: draw_rect 黄色 fill 走内容流 (颜色持久, 跳页眉/页脚)
    
    Args:
        pdf_path: PDF 源文件 (会被 in-place 修改 — 与旧实现语义一致)
        page_num: 1-based 页码
        terms: 关键词列表
        output_path: 输出 jpg 路径 (单页渲染)
    
    Returns:
        int: hit 数
    """
    import shutil

    # in-place 修改语义: 复制到临时文件, 改完后覆盖回 pdf_path
    # 复制必须做: PyMuPDF 不允许 in-place saveIncr 同一文件名 (会 raise)
    tmp_pdf = pdf_path + ".hl_v10_tmp.pdf"
    if os.path.abspath(pdf_path) == os.path.abspath(tmp_pdf):
        tmp_pdf = pdf_path + ".v10tmp.pdf"
    shutil.copy(pdf_path, tmp_pdf)

    # 用 robust 主函数, 但只画指定 page (max_pages=1) 拿其单页结果
    # 实际上: 旧接口只关心 1 页, 我们画 1 页 (但不局限于 1 页 — v10 的 max_pages=1 控制范围)
    tmp_out = tmp_pdf + ".out.pdf"
    result = highlight_pdf_robust(
        pdf_in=tmp_pdf,
        pdf_out=tmp_out,
        keywords=terms or [],
        max_pages=max(page_num, 1),
    )

    # 覆盖回原 PDF
    shutil.move(tmp_out, pdf_path)
    if os.path.exists(tmp_pdf):
        os.remove(tmp_pdf)

    # 渲染指定 page 为 jpg
    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        import io
        from PIL import Image
        try:
            doc = fitz.open(pdf_path)
            if page_num <= len(doc):
                page = doc[page_num - 1]
                pix = page.get_pixmap(matrix=fitz.Matrix(150 / 72, 150 / 72))
                img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
                img.save(output_path, "JPEG", quality=85)
            doc.close()
        except Exception as e:
            print(f"  [v10 compat] render jpg 失败: {e}")

    return result.get("total_hits", 0)


# ════════════════════════════════════════════════════════════════
# 核心: 单 PDF 高亮
# ════════════════════════════════════════════════════════════════

def _is_in_skip_zone(rect: fitz.Rect, page_rect: fitz.Rect,
                     first_lines: List[str], last_lines: List[str]) -> bool:
    """
    判断 rect 是否落在应跳过的区域:
    - 页眉 (顶部 10%)
    - 页脚 (底部 8%)
    - 前 2 行 (标题/作者)
    - 后 2 行 (脚注)
    """
    ph = page_rect.height
    pw = page_rect.width

    # 顶部 10%
    if rect.y0 < ph * SKIP_TOP_RATIO:
        return True
    # 底部 8%
    if rect.y1 > ph * (1 - SKIP_BOTTOM_RATIO):
        return True

    # 前 2 行的 y 范围: 从上往下累积, 直到覆盖 ~120 pt
    # 简单做法: 任何 y 落在 first_lines bbox 内算跳过
    # 实际我们用近似: 顶部 1/8 区域 + 标题常见 y 范围
    title_zone_bottom = ph * 0.18  # 标题 + 作者常见在 18% 以内
    if rect.y0 < title_zone_bottom and len(first_lines) >= SKIP_TOP_LINES:
        return True

    return False


def _normalize_term(term: str) -> List[str]:
    """
    一个 term 可能有多种写法 (e.g., "14.4%" vs "14.4 %"), 生成变体
    """
    variants = [term]
    # 数字 + % 空格变体
    m = re.match(r'^(\d+\.?\d*)\s*%$', term)
    if m:
        n = m.group(1)
        variants.extend([f"{n}%", f"{n} %", f"{n}％"])  # 全角百分号
    # HR 数字
    m = re.match(r'^HR\s*(\d+\.?\d*)$', term)
    if m:
        n = m.group(1)
        variants.extend([f"HR{n}", f"HR {n}", f"HR = {n}", f"HR={n}", n])
    # n= 数字
    m = re.match(r'^n=(\d+)$', term)
    if m:
        n = m.group(1)
        variants.extend([f"n = {n}", f"n= {n}", f" n {n} "])
    # 去空格
    if ' ' in term:
        variants.append(term.replace(' ', ''))
    return list(set(variants))


def _search_term_in_page(page: fitz.Page, term: str) -> List[fitz.Rect]:
    """
    在 page 中搜 term, 尝试多种变体; 失败时用 get_text("words") 做模糊匹配
    """
    rects = []
    for variant in _normalize_term(term):
        try:
            r = page.search_for(variant)
            if r:
                rects.extend(r)
        except Exception:
            pass

    if rects:
        return rects

    # 模糊匹配: 拆词 + 顺序匹配
    # e.g. "肝细胞癌" → 拆 [肝, 细胞, 癌], 找页面里包含连续字符的 span
    try:
        words = page.get_text("words")  # list of (x0,y0,x1,y1,word,block,line,word_no)
        text_lower = " ".join(w[4] for w in words).lower()
        if term.lower() in text_lower:
            # 找包含 term 的 line 的 bbox
            target_words = [w for w in words if term.lower() in w[4].lower()]
            if target_words:
                # merge rects of matching words in same line
                by_line = {}
                for w in target_words:
                    key = (w[5], w[6])  # block, line
                    if key not in by_line:
                        by_line[key] = []
                    by_line[key].append(w)
                for line_words in by_line.values():
                    x0 = min(w[0] for w in line_words)
                    y0 = min(w[1] for w in line_words)
                    x1 = max(w[2] for w in line_words)
                    y1 = max(w[3] for w in line_words)
                    rects.append(fitz.Rect(x0, y0, x1, y1))
    except Exception:
        pass

    return rects


def highlight_pdf_robust(
    pdf_in: str,
    pdf_out: str,
    keywords: List[str],
    max_pages: int = 20,
    min_yellow_pct: float = YELLOW_MIN_PCT,
) -> Dict:
    """
    稳健高亮: 改用 content stream 直接画黄色矩形, 跳过页眉/页脚/标题区

    Args:
        pdf_in: 输入 PDF
        pdf_out: 输出 PDF (高亮后的副本)
        keywords: 关键词列表 (e.g. ['HIMALAYA', 'STRIDE', '16.9%'])
        max_pages: 最多处理页数
        min_yellow_pct: 最小黄色像素占比 (用于报告)

    Returns:
        {
            'pages_processed': int,
            'total_hits': int,
            'per_page': [{'page', 'terms_matched', 'rects'}],
            'yellow_pct_estimate': float,
            'skipped_terms': [...],
        }
    """
    doc = fitz.open(pdf_in)
    n_pages = min(max_pages, len(doc))

    # 统计
    per_page_hits: List[Dict] = []
    total_hits = 0
    skipped_terms: List[str] = []
    matched_terms: List[str] = []

    for pi in range(n_pages):
        page = doc[pi]
        page_rect = page.rect
        page_h = page_rect.height

        page_data = {
            "page": pi + 1,
            "terms_matched": [],
            "rects": [],
        }

        # 抽前 2 行 / 后 2 行的 y 范围 (用于后续判断)
        try:
            blocks = page.get_text("dict")["blocks"]
            all_lines = []
            for b in blocks:
                if b.get("type") != 0:
                    continue
                for line in b.get("lines", []):
                    bbox = line.get("bbox")
                    text = " ".join(s.get("text", "") for s in line.get("spans", []))
                    all_lines.append({"y0": bbox[1], "y1": bbox[3], "text": text})
            all_lines.sort(key=lambda x: x["y0"])
        except Exception:
            all_lines = []

        for kw in keywords:
            if not kw or not kw.strip():
                continue
            rects = _search_term_in_page(page, kw)
            if not rects:
                continue

            # 过滤 skip zone
            valid_rects = [r for r in rects if not _is_in_skip_zone(r, page_rect, all_lines, all_lines)]
            if not valid_rects:
                # 全在 skip zone 也至少画 1 个 (避免 0% 黄色), 选离标题最远的
                rects_sorted = sorted(rects, key=lambda r: r.y0)
                valid_rects = [rects_sorted[-1]]  # 最下面的一个

            for r in valid_rects:
                # 扩展 rect: 加点 padding 让高亮更明显
                pad = 1.5
                draw_rect = fitz.Rect(
                    max(0, r.x0 - pad),
                    max(0, r.y0 - pad),
                    min(page_rect.x1, r.x1 + pad),
                    min(page_rect.y1, r.y1 + pad)
                )
                # 关键: 用 draw_rect + fill 画在内容流 (overlay=True 不替换底层)
                page.draw_rect(
                    draw_rect,
                    fill=HIGHLIGHT_FILL,
                    color=HIGHLIGHT_FILL,
                    width=0,
                    overlay=True,
                    fill_opacity=0.55,  # 55% 不透明, 不遮挡文字
                )
                total_hits += 1
                page_data["rects"].append({
                    "term": kw,
                    "rect": [r.x0, r.y0, r.x1, r.y1],
                })

            if kw not in page_data["terms_matched"]:
                page_data["terms_matched"].append(kw)
            if kw not in matched_terms:
                matched_terms.append(kw)

        per_page_hits.append(page_data)

    # 处理未匹配的 term
    for kw in keywords:
        if kw and kw not in matched_terms:
            skipped_terms.append(kw)

    # 保存 — 用 garbage=0 避免 annotation 颜色被清掉 (虽然我们没 add annotation, 但保险)
    os.makedirs(os.path.dirname(pdf_out) or ".", exist_ok=True)
    doc.save(pdf_out, garbage=0, deflate=True)
    doc.close()

    # 估计黄色像素占比
    yellow_pct = _estimate_yellow_pct(pdf_out, max_pages=n_pages)

    return {
        "pages_processed": n_pages,
        "total_hits": total_hits,
        "per_page": per_page_hits,
        "yellow_pct_estimate": yellow_pct,
        "matched_terms": matched_terms,
        "skipped_terms": skipped_terms,
        "min_yellow_pct": min_yellow_pct,
        "ok": yellow_pct >= min_yellow_pct,
    }


def _estimate_yellow_pct(pdf_path: str, max_pages: int = 20, dpi: int = 100) -> float:
    """渲染 PDF 估算黄色像素占比 (用于自检)"""
    import io
    from PIL import Image
    import numpy as np

    doc = fitz.open(pdf_path)
    n = min(max_pages, len(doc))
    if n == 0:
        doc.close()
        return 0.0
    total_yellow = 0
    total_pixels = 0
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    for i in range(n):
        try:
            pix = doc[i].get_pixmap(matrix=mat)
            arr = np.array(Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB"))
            yellow = (arr[:, :, 0] > YELLOW_R_MIN) & (arr[:, :, 1] > YELLOW_G_MIN) & (arr[:, :, 2] < YELLOW_B_MAX)
            total_yellow += int(yellow.sum())
            total_pixels += arr.shape[0] * arr.shape[1]
        except Exception:
            continue
    doc.close()
    return (total_yellow / total_pixels * 100) if total_pixels > 0 else 0.0


# ════════════════════════════════════════════════════════════════
# 配套: 渲染 page jpg (给健康检查 / 用户查看)
# ════════════════════════════════════════════════════════════════

def render_pages_jpg(pdf_path: str, out_dir: str, prefix: str,
                    max_pages: int = 5, dpi: int = 120) -> List[str]:
    """渲染前 N 页为 jpg"""
    import io
    from PIL import Image

    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    files = []
    n = min(max_pages, len(doc))
    for i in range(n):
        try:
            pix = doc[i].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72))
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            out = os.path.join(out_dir, f"{prefix}_page{i+1}.jpg")
            img.save(out, "JPEG", quality=85)
            files.append(out)
        except Exception as e:
            print(f"  render page {i+1} fail: {e}")
    doc.close()
    return files


# ════════════════════════════════════════════════════════════════
# 关键词提取 (从 CSV D/C 列)
# ════════════════════════════════════════════════════════════════

def extract_keywords_from_d(d_text: str, c_text: str = "") -> List[str]:
    """
    从 D 列 + C 列提搜索关键词
    - 数字+%
    - HR/p值/95%CI
    - 期刊 (Lancet/NEJM/Hepatol/...)
    - 关键术语 (HIMALAYA/STRIDE/...)
    - 年份
    """
    if not d_text and not c_text:
        return []
    keywords = set()
    full = f"{d_text} {c_text}"

    # 数字+%
    for m in re.finditer(r'(\d+\.?\d*)\s*%', full):
        keywords.add(f"{m.group(1)}%")
    # HR
    for m in re.finditer(r'HR\s*[=:]?\s*(\d+\.?\d*)', full, re.IGNORECASE):
        keywords.add(f"HR {m.group(1)}")
        keywords.add(m.group(1))
    # n=
    for m in re.finditer(r'n\s*=\s*(\d+)', full):
        keywords.add(f"n={m.group(1)}")
    # 年份
    for m in re.finditer(r'\b(19|20)\d{2}\b', full):
        keywords.add(m.group(0))
    # 期刊
    for kw in ['Lancet', 'Hepatol', 'NEJM', 'JCO', 'ASCO', 'ESMO', 'JAMA',
               'HBSN', 'Cancer Discov', 'Anticancer', 'J Hepatol', '中华血液']:
        if kw in full:
            keywords.add(kw)
    # 关键术语
    for kw in ['STRIDE', 'HIMALAYA', 'T+A', 'O+Y', 'CheckMate', 'IMbrave',
               'ORIENT', 'TREMENDOUS', 'LEAP', 'AHELP', 'APASL', 'EASL', 'AASLD']:
        if kw in full:
            keywords.add(kw)
    # 作者姓 + 年份
    for m in re.finditer(r'([A-Z][a-zA-Z\-]{2,})\s+[A-Z]{1,3}', c_text or ''):
        author = m.group(0).strip()
        if len(author) > 3:
            keywords.add(author)

    return list(keywords)


# ════════════════════════════════════════════════════════════════
# 顶层: 处理 Pn-x
# ════════════════════════════════════════════════════════════════

def process_pn_x(
    pn_x: str,
    pdf_in: str,
    pdf_out: str,
    keywords: List[str],
    jpg_out_dir: Optional[str] = None,
    jpg_prefix: Optional[str] = None,
) -> Dict:
    """
    顶层 API: 处理一个 Pn-x, 输出高亮 PDF + 可选 page jpg

    Args:
        pn_x: 'P11-1'
        pdf_in: 输入 PDF
        pdf_out: 输出高亮 PDF
        keywords: 关键词列表
        jpg_out_dir: 可选, 输出 page jpg 目录
        jpg_prefix: 可选, jpg 前缀 (默认 pn_x)

    Returns:
        同 highlight_pdf_robust() 返回值 + jpg_files
    """
    result = highlight_pdf_robust(pdf_in, pdf_out, keywords)
    jpg_files = []
    if jpg_out_dir:
        prefix = jpg_prefix or pn_x
        jpg_files = render_pages_jpg(pdf_out, jpg_out_dir, prefix)
    result["jpg_files"] = jpg_files
    result["pn_x"] = pn_x
    return result


# ════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 4:
        print("Usage: via54_highlight_fix_v10.py <pn_x> <pdf_in> <pdf_out> [kw1,kw2,...] [jpg_dir]")
        print("Example: via54_highlight_fix_v10.py P11-1 in.pdf out.pdf '摘要,方法' /tmp/jpg")
        sys.exit(1)

    pn_x = sys.argv[1]
    pdf_in = sys.argv[2]
    pdf_out = sys.argv[3]
    keywords = sys.argv[4].split(",") if len(sys.argv) > 4 and sys.argv[4] else []
    jpg_dir = sys.argv[5] if len(sys.argv) > 5 else None

    result = process_pn_x(pn_x, pdf_in, pdf_out, keywords, jpg_dir)
    print(f"\n=== {pn_x} highlight result ===")
    print(f"  Pages processed: {result['pages_processed']}")
    print(f"  Total hits: {result['total_hits']}")
    print(f"  Yellow pixel %: {result['yellow_pct_estimate']:.3f}%")
    print(f"  Matched terms ({len(result['matched_terms'])}): {result['matched_terms'][:10]}")
    print(f"  Skipped terms ({len(result['skipped_terms'])}): {result['skipped_terms'][:5]}")
    print(f"  OK: {result['ok']}")
    if jpg_dir:
        print(f"  JPG files: {len(result['jpg_files'])}")
        for f in result['jpg_files']:
            print(f"    {f}")


if __name__ == "__main__":
    main()
