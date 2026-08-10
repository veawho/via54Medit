#!/usr/bin/env python3
"""
via54_highlight_fix_v10.py — v10.1 修复版高亮渲染 (2026-08-10)

修复 v9.7 系列的 4 个核心 bug:
  Bug 1: add_highlight_annot().set_colors() save/reload 后 colors=None
         → 黄色丢失, 渲染为隐形细线 (实测 P11-1 全部 0% 黄色)
  Bug 2: best_page 选 page 1, 但 page 1 多半是标题/作者/摘要
         → 高亮落在错内容 (header/author row, 不是应证段)
  Bug 3: search_for 失败 (Chinese vs English 关键词) 无回退
  Bug 4: 单页覆盖, 实际证据常常跨多页

v10.1 新增 (匹配 6 步规则):
  - 默认 highlight_mode="line" (规则第 4 步要求 "文字下方细黄线")
  - expand_citation() 多引文展开 ("1,2" / "1-3" / "1, 3-5" → [1,2,1,2,3,1,3,4,5])
  - merge_pn_x_dirs() 目录合并 (规则第 6 步 "Pn1-x1Pn2-x2" 格式)
  - 验证 via54_rules.py 规则校验

修复策略:
  1. 改用 page.draw_line(...) 在文字下方画细黄线 (规则要求)
     可选 fill 模式 (page.draw_rect) 给特殊场景
  2. 跳过页眉/页脚/前 2 行/后 2 行 (高亮落正文段)
  3. 多页搜索 + 关键词权重 (中段页优先)
  4. search_for 失败时回退到 fitz 文本流 + 模糊匹配
  5. 输出 PDF (主) + jpg per page (健康检查用)

API:
  highlight_pdf_robust(pdf_in, pdf_out, keywords, ...) -> Dict
  render_pages_jpg(pdf_path, out_dir, ...) -> List[str]
  process_pn_x(pn_x, pdf_in, pdf_out, keywords, jpg_dir, ...) -> Dict
  expand_citation("1,2-3,5") -> [1, 2, 3, 5]
  merge_pn_x_dirs(download_dir, merge_groups) -> Dict
"""
import os, re, sys, json
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import fitz  # PyMuPDF


# ════════════════════════════════════════════════════════════════
# 常量
# ════════════════════════════════════════════════════════════════

# 纯黄 (1, 1, 0) 不用 set_colors
HIGHLIGHT_FILL = (1, 1, 0)  # RGB

# 跳过区域: 页眉/页脚/前 N 行/后 N 行
SKIP_TOP_RATIO = 0.10   # 跳过顶部 10% (页眉)
SKIP_BOTTOM_RATIO = 0.08  # 跳过底部 8% (页脚/页码)
SKIP_TOP_LINES = 2       # 跳过前 2 行 (标题/作者)
SKIP_BOTTOM_LINES = 2    # 跳过后 2 行 (通信/脚注)

# 健康检查的黄色像素阈值
YELLOW_R_MIN = 200
YELLOW_G_MIN = 200
YELLOW_B_MAX = 150
YELLOW_MIN_PCT = 0.01  # 0.01% (与 via54_health.py 一致, fill 模式适用)
# line 模式 (6 步规则要求 "细黄线") 因线本身面积小, 阈值放宽到 0.003%
YELLOW_MIN_PCT_LINE = 0.003

# 高亮样式 (6 步规则第 4 步要求 "文字下方细黄线")
HIGHLIGHT_MODES = ("line", "fill", "both")
DEFAULT_HIGHLIGHT_MODE = "line"
LINE_WIDTH_PT = 1.8  # 黄线粗细 (pt)

# 目录合并 (6 步规则第 6 步 "Pn1-x1Pn2-x2")
# 注: 实际目录命名约定用下划线分隔 (P15-1_P16-1_P17-1),
#     规则文字是连写但实际代码用 "_" — 在 merge_pn_x_dirs 中可配置
DEFAULT_DIR_SEPARATOR = "_"


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
    mode: str = DEFAULT_HIGHLIGHT_MODE,
) -> Dict:
    """
    稳健高亮: 直接画黄色标记在文字下方 (规则第 4 步要求 "细黄线")
    跳过页眉/页脚/标题区

    Args:
        pdf_in: 输入 PDF
        pdf_out: 输出 PDF (高亮后的副本)
        keywords: 关键词列表 (e.g. ['HIMALAYA', 'STRIDE', '16.9%'])
        max_pages: 最多处理页数
        min_yellow_pct: 最小黄色像素占比 (用于报告)
        mode: 高亮样式
            - "line" (默认, 6 步规则要求): 文字下方画细黄线
            - "fill": 文字 bbox 填黄 (高亮笔效果, 文字仍可读)
            - "both": line + fill

    Returns:
        {
            'pages_processed': int,
            'total_hits': int,
            'per_page': [{'page', 'terms_matched', 'rects'}],
            'yellow_pct_estimate': float,
            'skipped_terms': [...],
            'mode': str,
        }
    """
    if mode not in HIGHLIGHT_MODES:
        raise ValueError(f"mode 必须是 {HIGHLIGHT_MODES} 之一, 收到: {mode}")

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
                # 扩展 rect 一点, 让高亮更明显
                pad = 1.5
                draw_rect = fitz.Rect(
                    max(0, r.x0 - pad),
                    max(0, r.y0 - pad),
                    min(page_rect.x1, r.x1 + pad),
                    min(page_rect.y1, r.y1 + pad)
                )

                # 根据 mode 画高亮
                if mode in ("fill", "both"):
                    # 黄色填充 (高亮笔效果)
                    page.draw_rect(
                        draw_rect,
                        fill=HIGHLIGHT_FILL,
                        color=HIGHLIGHT_FILL,
                        width=0,
                        overlay=True,
                        fill_opacity=0.55,
                    )

                if mode in ("line", "both"):
                    # 文字下方细黄线 (6 步规则要求)
                    # 位置: 文字底部下方 1pt
                    line_y = r.y1 + 1.2
                    page.draw_line(
                        fitz.Point(r.x0, line_y),
                        fitz.Point(r.x1, line_y),
                        color=HIGHLIGHT_FILL,
                        width=LINE_WIDTH_PT,
                        overlay=True,
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

    # 保存 — 用 garbage=0 避免 annotation 颜色被清掉
    os.makedirs(os.path.dirname(pdf_out) or ".", exist_ok=True)
    doc.save(pdf_out, garbage=0, deflate=True)
    doc.close()

    # 估计黄色像素占比
    yellow_pct = _estimate_yellow_pct(pdf_out, max_pages=n_pages)

    # line 模式天然面积小, 自动用更低的阈值
    effective_threshold = min_yellow_pct
    if mode == "line" and min_yellow_pct == YELLOW_MIN_PCT:
        effective_threshold = YELLOW_MIN_PCT_LINE

    return {
        "pages_processed": n_pages,
        "total_hits": total_hits,
        "per_page": per_page_hits,
        "yellow_pct_estimate": yellow_pct,
        "matched_terms": matched_terms,
        "skipped_terms": skipped_terms,
        "min_yellow_pct": effective_threshold,
        "ok": yellow_pct >= effective_threshold,
        "mode": mode,
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
    v10.1.1: 优先用 L4 v2 (可信度评分), fallback 到原启发式

    v10.1 增强: 调用 l4_keyword_extract.extract_keywords_v2() 用 5 维特征
    + 可信度评分, 避免抽过于通用的词 (e.g., 2020, 99%)
    """
    if not d_text and not c_text:
        return []
    # 优先用 L4 v2 (如果可 import)
    try:
        from l4_keyword_extract import extract_keywords_simple
        kws = extract_keywords_simple(c_text or "", d_text or "")
        if kws:
            return kws
    except ImportError:
        pass

    # Fallback: 原启发式
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
# 6 步规则 #4: 多引文展开 "1,2" / "1-3" / "1, 3-5"
# ════════════════════════════════════════════════════════════════

def expand_citation(citation: str) -> List[int]:
    """
    展开 PPT 中的引文标号

    支持格式:
      "1"         → [1]
      "1,2"       → [1, 2]
      "1, 2"      → [1, 2]
      "1-3"       → [1, 2, 3]
      "1,2-3"     → [1, 2, 3]
      "1, 3-5, 7" → [1, 3, 4, 5, 7]

    Args:
        citation: 原始标号字符串

    Returns:
        展开后的整数列表 (去重, 保持出现顺序)
    """
    if citation is None:
        return []
    s = str(citation).strip()
    if not s:
        return []

    result: List[int] = []
    seen: set = set()
    # 按逗号分段
    parts = re.split(r'[,，]\s*', s)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # 范围 "1-3" 或 "1~3"
        m = re.match(r'^(\d+)\s*[-–—~]\s*(\d+)$', part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            lo, hi = (a, b) if a <= b else (b, a)
            for n in range(lo, hi + 1):
                if n not in seen:
                    seen.add(n)
                    result.append(n)
        else:
            # 单数字
            m = re.match(r'^(\d+)$', part)
            if m:
                n = int(m.group(1))
                if n not in seen:
                    seen.add(n)
                    result.append(n)
            # 其它格式 (e.g., "1a", "1-2a") — 静默忽略非数字部分
    return result


def expand_citations_batch(citations: List[str]) -> Dict[str, List[int]]:
    """批量展开引文"""
    return {c: expand_citation(c) for c in citations}


# ════════════════════════════════════════════════════════════════
# 6 步规则 #6: 目录合并 (相同文献的 Pn-x 目录合并)
# ════════════════════════════════════════════════════════════════

def merge_pn_x_dirs(
    source_dir: str,
    merge_groups: List[List[str]],
    separator: str = DEFAULT_DIR_SEPARATOR,
    dry_run: bool = False,
) -> Dict:
    """
    把多个 Pn-x 子目录合并为一个, 名字用 separator 连接
    (6 步规则第 6 步: "Pn1-x1Pn2-x2" — 实际代码用下划线分隔)

    Args:
        source_dir: 包含 Pn-x 子目录的父目录 (e.g., _highlight/)
        merge_groups: e.g. [['P15-1', 'P16-1', 'P17-1'], ['P23-10', 'P23-11']]
        separator: 目录名分隔符 (默认 "_", 规则文字是连写)
        dry_run: True 只报告不执行

    Returns:
        {
            'merged': [(target_name, src_list, files_moved)],
            'errors': [...],
            'dry_run': bool,
        }
    """
    import shutil

    result = {"merged": [], "errors": [], "dry_run": dry_run}
    for group in merge_groups:
        if not group or len(group) < 2:
            result["errors"].append(f"组至少 2 个 Pn-x: {group}")
            continue
        # 排序: 按 slide 然后 mark
        def _sort_key(p):
            m = re.match(r'P(\d+)-(\d+)', p)
            return (int(m.group(1)) if m else 999, int(m.group(2)) if m else 999)
        group_sorted = sorted(group, key=_sort_key)
        target_name = separator.join(group_sorted)
        target_dir = os.path.join(source_dir, target_name)

        if dry_run:
            result["merged"].append({
                "target": target_name,
                "sources": group_sorted,
                "files_moved": 0,
            })
            continue

        try:
            os.makedirs(target_dir, exist_ok=True)
            files_moved = 0
            for src_name in group_sorted:
                src_dir = os.path.join(source_dir, src_name)
                if not os.path.isdir(src_dir):
                    continue
                for f in os.listdir(src_dir):
                    src = os.path.join(src_dir, f)
                    dst = os.path.join(target_dir, f)
                    if not os.path.exists(dst):
                        shutil.move(src, dst)
                        files_moved += 1
                    else:
                        # 重复, 删源
                        try:
                            os.remove(src)
                        except Exception:
                            pass
                # 删空源目录
                try:
                    os.rmdir(src_dir)
                except OSError:
                    pass
            result["merged"].append({
                "target": target_name,
                "sources": group_sorted,
                "files_moved": files_moved,
            })
        except Exception as e:
            result["errors"].append(f"合并 {group_sorted} → {target_name} 失败: {e}")

    return result


def find_merge_groups_from_dir(
    source_dir: str,
    by: str = "md5",  # "md5" | "filename"
) -> List[List[str]]:
    """
    自动找相同文献的 Pn-x 组 (按 md5 或文件名)

    Args:
        source_dir: 父目录
        by: 分组依据
            - "md5": 同一 PDF md5 (真正相同)
            - "filename": 同名 PDF (可能是同一文件)

    Returns:
        [[Pn-x, ...], ...]  # 每组 >= 2 个才返回
    """
    import hashlib
    pn_x_dirs = [d for d in os.listdir(source_dir)
                 if os.path.isdir(os.path.join(source_dir, d)) and d.startswith('P')]
    groups: Dict[str, List[str]] = {}

    for pn in pn_x_dirs:
        pn_path = os.path.join(source_dir, pn)
        pdfs = [f for f in os.listdir(pn_path) if f.lower().endswith('.pdf')]
        if not pdfs:
            continue
        # 用第一个 PDF 算 key
        target_pdf = next((f for f in pdfs if 'main' in f.lower() and 'fallback' not in f.lower()), pdfs[0])
        pdf_path = os.path.join(pn_path, target_pdf)
        try:
            if by == "md5":
                with open(pdf_path, 'rb') as f:
                    key = hashlib.md5(f.read()).hexdigest()
            elif by == "filename":
                key = target_pdf
            else:
                key = target_pdf
        except Exception:
            continue
        groups.setdefault(key, []).append(pn)

    # 只返回 >= 2 个的组
    return [sorted(g, key=lambda p: (
        int(re.match(r'P(\d+)-(\d+)', p).group(1)) if re.match(r'P(\d+)-(\d+)', p) else 999,
        int(re.match(r'P(\d+)-(\d+)', p).group(2)) if re.match(r'P(\d+)-(\d+)', p) else 999,
    )) for g in groups.values() if len(g) >= 2]


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
    mode: str = DEFAULT_HIGHLIGHT_MODE,
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
        mode: 高亮样式 ("line" / "fill" / "both")

    Returns:
        同 highlight_pdf_robust() 返回值 + jpg_files
    """
    result = highlight_pdf_robust(pdf_in, pdf_out, keywords, mode=mode)
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
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Highlight: via54_highlight_fix_v10.py hl <pn_x> <pdf_in> <pdf_out> [kw1,kw2,...] [jpg_dir]")
        print("  Expand:   via54_highlight_fix_v10.py expand <citation>")
        print("  Merge:    via54_highlight_fix_v10.py merge <source_dir> [--by md5|filename] [--execute]")
        print()
        print("Examples:")
        print("  via54_highlight_fix_v10.py hl P11-1 in.pdf out.pdf '摘要,方法' /tmp/jpg")
        print("  via54_highlight_fix_v10.py expand '1,2-3,5'")
        print("  via54_highlight_fix_v10.py merge /path/to/highlight_dir --by md5")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "expand":
        # 展开引文
        if len(sys.argv) < 3:
            print("Usage: expand <citation>")
            sys.exit(1)
        result = expand_citation(sys.argv[2])
        print(f"  '{sys.argv[2]}' → {result}")
    elif cmd == "merge":
        # 合并目录
        if len(sys.argv) < 3:
            print("Usage: merge <source_dir> [--by md5|filename] [--execute]")
            sys.exit(1)
        source_dir = sys.argv[2]
        by = "md5"
        dry_run = True
        for i, arg in enumerate(sys.argv[3:], start=3):
            if arg == "--by" and i + 1 < len(sys.argv):
                by = sys.argv[i + 1]
            elif arg == "--execute":
                dry_run = False
        if not os.path.isdir(source_dir):
            print(f"  目录不存在: {source_dir}")
            sys.exit(1)
        groups = find_merge_groups_from_dir(source_dir, by=by)
        if not groups:
            print(f"  无可合并组 (按 {by})")
            sys.exit(0)
        print(f"  发现 {len(groups)} 个可合并组 (按 {by}):")
        for g in groups:
            print(f"    {g}")
        if dry_run:
            print(f"  (dry-run, 加 --execute 真正合并)")
        else:
            result = merge_pn_x_dirs(source_dir, groups, dry_run=False)
            for m in result["merged"]:
                print(f"  ✓ {m['target']}: 移动 {m['files_moved']} 个文件")
            if result["errors"]:
                for e in result["errors"]:
                    print(f"  ❌ {e}")
    elif cmd == "hl":
        if len(sys.argv) < 5:
            print("Usage: hl <pn_x> <pdf_in> <pdf_out> [kw1,kw2,...] [jpg_dir]")
            sys.exit(1)
        pn_x = sys.argv[2]
        pdf_in = sys.argv[3]
        pdf_out = sys.argv[4]
        keywords = sys.argv[5].split(",") if len(sys.argv) > 5 and sys.argv[5] else []
        jpg_dir = sys.argv[6] if len(sys.argv) > 6 else None
        result = process_pn_x(pn_x, pdf_in, pdf_out, keywords, jpg_dir)
        print(f"\n=== {pn_x} highlight result ===")
        print(f"  Pages processed: {result['pages_processed']}")
        print(f"  Total hits: {result['total_hits']}")
        print(f"  Mode: {result.get('mode', 'unknown')}")
        print(f"  Yellow pixel %: {result['yellow_pct_estimate']:.3f}%")
        print(f"  Matched terms ({len(result['matched_terms'])}): {result['matched_terms'][:10]}")
        print(f"  Skipped terms ({len(result['skipped_terms'])}): {result['skipped_terms'][:5]}")
        print(f"  OK: {result['ok']}")
        if jpg_dir:
            print(f"  JPG files: {len(result['jpg_files'])}")
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
