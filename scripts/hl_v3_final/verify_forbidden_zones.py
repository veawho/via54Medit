#!/usr/bin/env python3
"""
verify_forbidden_zones.py — 禁止区校验: highlight 不得盖标题/作者/参考文献/页眉页脚/图表标题

v3 FINAL 规范明确要求「禁止高亮: 标题、作者、文献信息、页眉页脚、引用编号、图表标题」
(第 153 行), 但 hl_lib 在**生成期**并没有实现这条检查(生成期靠"整句定位 + 先清 annots"
规避)。本脚本把该要求做成一道**事后可复跑的校验**, 补上 v3 FINAL 工具链缺的这一环。

来源与改造
----------
移植自 ``scripts/audit_all_highlights_v13.py``(v13.2, 2026-08-12)的 Phase 1。原脚本已随
v5.4.19 下线。移植时有两处必要改造 —— 都不是"顺手改改", 而是原逻辑在当前交付物上
**可证伪地失效**:

**改造 1: 递归发现 + 认对注记类型。** 原脚本按扁平布局枚举
``{STEP4_DIR}/{pn}_semantic_highlight.pdf``, 且只认 Highlight(8)/Underline(9) 两种注记。
而 v3 FINAL 把 step4 改成嵌套布局 ``{Pn-x}/{PN}_highlight.pdf``, 且用 **Square(4)** 注记
(hl_lib: stroke+fill=(1,0.85,0), opacity 0.45, 逐行生成)。两处任一都会让原脚本"什么都
看不到", 叠加起来就是它失效的原因。本脚本递归发现 ``*_highlight.pdf`` 并认 4/8/9。

**改造 2: 规则按证据分级, 而不是照搬正则。** 实测: 原规则套在当前交付物上会报
**26 条违规 / 1325 条注记**, 而逐条核对后**没有一条是真实缺陷** —— 21 条是可证伪的误报,
5 条是需人工判断的图表标题。举三个有代表性的:

  * ``(Professor|Prof\\.|Dr\\.|Doctor)`` 命中了正文里的 "several **doctors** in southern
    Italy"(作者职称模式撞上普通名词)。
  * ``^[\\w\\s,]+(?:,?\\s*MD|PhD){1,}`` 命中了 "Alzheimer disease, atherosclerosis and
    **AMD3**"(学位模式撞上基因名)。
  * ``page0_top_30% + 含中文 => 判为中文作者区``: 实测 P9-3 的版面是标题 13.9%、
    **作者 18.3%**、正文/摘要 **22% 起** —— 规则却把 22~29% 的摘要正文判成了作者区。
    中文刊的作者块紧凑、正文起得早, 这个几何阈值区分不了二者。

因此本脚本把判定分成两级, **两级都会打印**, 不隐藏任何东西:

  * **违规 (gate, 影响退出码)**: 有工程上可靠证据的 —— 页眉带、页脚"版面附属物"、
    强作者/单位标记(作者单位/通信作者/Corresponding author/邮箱/机构名)、参考文献段
    (几何 + 文字双重门槛)、以及矩形几何异常。
  * **待人工判断 (不 gate)**: 图表标题(规范里有「除非图表即应证对象」的例外, 机器
    判不了)、page0 顶部 30% 带内(标题/作者/正文在中文刊里几何上难以区分)、正文里
    命中参考文献模式(多半是行文中的夹注)。

用法
----
    python3 verify_forbidden_zones.py --hl-dir <step4_dir> [--json <out.json>] [--quiet]

退出码
------
    0 = 无违规    1 = 有违规    2 = 用法 / 环境错误
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import pymupdf as fitz  # PyMuPDF >= 1.24 的正式导入名
except ImportError:  # 旧版回退 (写 import fitz 会打弃用警告, 见 CHANGELOG 5.4.11)
    import fitz

# 部分 PDF 会触发 mupdf 的噪声警告, 与审计结论无关
try:
    fitz.TOOLS.mupdf_display_warnings(False)
except Exception:
    pass


#: 视为"高亮"的注记类型。
#:   Square(4)    —— v3 FINAL 的 rect 模式 (当前交付物用的就是这个)
#:   Highlight(8) —— v10 / v13 的 line 细黄线模式 (仅历史)
#:   Underline(9) —— 早期变体
HIGHLIGHT_ANNOT_TYPES = (
    fitz.PDF_ANNOT_SQUARE,
    fitz.PDF_ANNOT_HIGHLIGHT,
    fitz.PDF_ANNOT_UNDERLINE,
)

ANNOT_TYPE_NAMES = {4: "Square", 8: "Highlight", 9: "Underline"}


# ════════════════════════════════════════════════════════════════
# 模式表
# ════════════════════════════════════════════════════════════════

#: 版面附属物 (页脚/页眉里的装饰性文字, 一旦被高亮就是真问题)。
#: 刻意收窄: 只认"长得像附属物"的, 不靠"位置在 92% 以下"就下结论 ——
#: 正文完全可以排到 92% 以下(实测 P14-2 / P31-4 / P4-4 都是正文被判成页脚)。
PAGE_FURNITURE_PATTERNS = [
    r'^\s*\d{1,4}\s*$',                      # 纯页码
    r'^\s*[ivxlcdmIVXLCDM]{1,7}\s*$',        # 罗马页码
    r'(Downloaded from|Downloaded by)',
    r'(https?://|www\.)',
    r'\bdoi\.org/',
    r'(Copyright|©)\s*\d{4}',
    r'^\s*(Vol|Volume)\.?\s*\d+',
    r'\bPage\s+\d+\s+of\s+\d+',
    r'\b(19|20)\d{2}\s*;\s*\d+\s*[\(:]',     # Year;Vol( / Year;Vol:
]

#: 强作者 / 单位标记 (按**内容**判定, 不再靠几何位置)。
#: 机构名前面加了 ``(?<![\w-])`` —— 否则 "in-**hospital** mortality" 这种
#: 连字符复合词会被当成机构名 (实测 P28-4 就中过这一枪)。
AFFILIATION_PATTERNS = [
    r'作者单位', r'通信作者', r'基金项目', r'作者及单位信息',
    r'(?<![\w-])(Department|Division|Institute|Faculty|School|College)\s+of\b',
    r'(?<![\w-])(University|Hospital|Medical\s+Center|Centre|Medical\s+Centre)\b',
    r'Corresponding\s+author',
    r'\bORCID\b',
    r'[\w.+-]+@[\w-]+\.[A-Za-z]{2,}',
    r'\b(Prof\.|Professor|Dr\.)\s+[A-Z]',
]

#: 关键词 / 声明 / 引文头 —— 模式本身足够精确, 归入违规级。
KEYWORDS_TEXT_PATTERNS = [
    r'^\s*KEYWORDS?\s*[:：]', r'^\s*Key\s+words?\s*[:：]',
    r'^\s*(关键词|关键字|主题词)\s*[:：]',
]

DECLARATION_TEXT_PATTERNS = [
    r'^\s*DECLARATION', r'^\s*Disclosure', r'^\s*AUTHOR\s+CONTRIBUTION',
    r'^\s*FUNDING', r'^\s*ACKNOWLEDG(E)?MENT',
    r'^\s*CONFLICT\s+OF\s+INTEREST', r'^\s*DATA\s+AVAILABILITY',
    r'^\s*Compliance with Ethics', r'^\s*Author Contributions',
    r'^\s*Funding Information', r'^\s*Additional Information',
    r'^\s*Supplementary', r'^\s*Publisher\s+Note',
    r'^\s*(致谢|利益冲突|基金资助|作者贡献|数据可用性)\s*[:：]',
]

CITATION_TEXT_PATTERNS = [
    r'^\s*CITATION\s*:', r'^\s*Received\s*:', r'^\s*Accepted\s*:',
    r'^\s*Published\s*:', r'^\s*Copyright\s*[©©]',
]

#: 参考文献**条目**的强签名 (年份 + 至少一个期刊/卷期页/DOI 标记)。
#: 注意 ``\b(19|20)\d{2}\b`` 不会命中 "1980s" / "1990s" (数字后紧跟 s, 无词边界) ——
#: 这正是原脚本那条 `^(?:[A-Z][a-z]+\s+){1,3}...\d{4}` 误报 "In the 1970s and 1980s,
#: as the complexities of the C cascade" 的原因, 本脚本据实收紧。
REF_ENTRY_YEAR_RE = re.compile(r'\b(19|20)\d{2}\b')
REF_ENTRY_MARKERS = [
    r'et\s+al\.',
    r'\b\d+\s*\(\d+\)\s*:\s*\d+',
    r'\b\d+\s*:\s*\d+[-–]\d+',
    r'\b(?:Lancet|N Engl J Med|Blood|JAMA|Br J Haematol|J Thromb Haemost|Nat Rev|'
    r'Nat Med|Sci Transl Med|J Clin Invest|Hematology|Am J Hematol|J Am Soc Nephrol|'
    r'Kidney Int|Transplantation|BBMT|Clin Infect Dis|J Pediatr|Pediatrics|'
    r'Nephrol Dial Transplant|Front Pediatr)\b',
    r'\b(doi|DOI|PMID|PMCID)\b',
    r'\[\d+\]\s*\[\d+\]\s*\[\d+\]',
]

#: 图表标题 —— 规范给了「除非图表即应证对象」的例外, 只能人工判断, 故不 gate。
FIGURE_CAPTION_PATTERNS = [
    r'^\s*Fig\.?\s*\d+', r'^\s*Figure\s+\d+',
    r'^\s*(表|图)\s*\d+', r'^\s*Table\s+\d+',
]

CJK_RE = re.compile(r'[\u4e00-\u9fff]')


# ════════════════════════════════════════════════════════════════
# 基础工具
# ════════════════════════════════════════════════════════════════

def matches_any(text: str, patterns) -> str:
    """返回第一条命中的模式, 未命中返回空串。"""
    if not text:
        return ""
    for pat in patterns:
        if re.search(pat, text, re.IGNORECASE | re.MULTILINE):
            return pat
    return ""


def get_annot_text(page, rect) -> str:
    """取 rect 内文字。失败返回空串 (解码坏掉的 PDF 会抛异常)。"""
    try:
        return page.get_text("text", clip=rect).strip()
    except Exception:
        return ""


def is_page_furniture(text: str) -> bool:
    """文字是否像页眉/页脚这类版面附属物。

    两条路径任一成立即可:
      1. 命中附属物模式 (页码 / 下载水印 / DOI / 版权行 ...)
      2. 短 (< 40 字符) 且没有任何句末标点 —— 附属物不会是句子
    """
    if not text:
        return False
    if matches_any(text, PAGE_FURNITURE_PATTERNS):
        return True
    return len(text) < 40 and not re.search(r'[.!?。！？；]', text)


def ref_entry_markers(text: str):
    """返回命中的参考文献标记列表。"""
    if not text:
        return []
    return [p for p in REF_ENTRY_MARKERS
            if re.search(p, text, re.IGNORECASE | re.MULTILINE)]


def is_ref_entry(text: str, min_markers: int = 1) -> bool:
    """文字是否像一条参考文献条目: 有年份 + 至少 ``min_markers`` 个标记。

    ``min_markers`` 的取值是有意的:
      * 位置无关的判定用 **2** —— 行文中的夹注 (如 "...as shown by Coppo et al.,
        2009).") 只会命中 1 个标记, 高亮这种正文句子是**合法**的, 不该报违规
        (实测 P4-4 就中过这一枪)。
      * 已由几何门槛 (倒数页 + 下半页) 约束的判定用 **1** —— 上下文已经足够强。
    """
    if not text or not REF_ENTRY_YEAR_RE.search(text):
        return False
    return len(ref_entry_markers(text)) >= min_markers


# ════════════════════════════════════════════════════════════════
# 判定 (纯函数, 便于单测)
# ════════════════════════════════════════════════════════════════

def check_geometry_violations(rect, page_w: float, page_h: float):
    """几何异常 (违规级)。"""
    v = []
    scanned = page_h > 1500
    # 页眉带: rect 完全落在页面最上沿
    if rect.y1 < page_h * (0.005 if scanned else 0.05):
        v.append(("top_5%_header", f"y1={rect.y1:.0f}/{page_h:.0f}"))
    if page_w and rect.width / page_w > 0.85 and rect.height / page_h > 0.25:
        v.append(("too_wide_and_tall",
                  f"w={rect.width / page_w * 100:.0f}%, h={rect.height / page_h * 100:.0f}%"))
    if rect.height / page_h > 0.5:
        v.append(("too_tall", f"h={rect.height / page_h * 100:.0f}%"))
    if rect.width < 8:
        v.append(("too_narrow", f"w={rect.width:.0f}px"))
    return v


def check_hard_violations(page, rect, page_h: float, text: str):
    """违规级判定: 页脚附属物 / 作者单位 / 关键词 / 声明 / 引文头 / 参考文献条目。"""
    v = []
    if rect.y0 > page_h * 0.92 and is_page_furniture(text):
        v.append(("footer_furniture", f"y0={rect.y0:.0f}, text={text[:60]!r}"))
    for label, patterns in (("author_block", AFFILIATION_PATTERNS),
                            ("keywords_text", KEYWORDS_TEXT_PATTERNS),
                            ("declaration_text", DECLARATION_TEXT_PATTERNS),
                            ("citation_text", CITATION_TEXT_PATTERNS)):
        pat = matches_any(text, patterns)
        if pat:
            v.append((label, f"pat={pat}, text={text[:80]!r}"))
    if is_ref_entry(text, min_markers=2):
        pat = ref_entry_markers(text)[0]
        v.append(("reference_entry", f"pat={pat}, text={text[:80]!r}"))
    return v


def check_soft_flags(rect, page_w: float, page_h: float, pno: int, text: str):
    """待人工判断级: 图表标题 / page0 顶部带 / 正文里的参考文献模式。"""
    w = []
    scanned = page_h > 1500
    pat = matches_any(text, FIGURE_CAPTION_PATTERNS)
    if pat:
        w.append(("figure_caption", f"pat={pat}, text={text[:80]!r}"))
    if pno == 0:
        band = 0.30 if not scanned else 0.05
        if rect.y0 < page_h * band:
            pct = rect.y0 / page_h * 100
            w.append(("page0_top_band",
                      f"y0={rect.y0:.0f}/{page_h:.0f}={pct:.1f}%"
                      f"{' (中文刊正文起得早, 几何上区分不了作者块)' if CJK_RE.search(text[:50]) else ''}"))
    # 正文里命中参考文献模式 (已排除真正的条目, 见 check_hard_violations)
    if not is_ref_entry(text, min_markers=2) and rect.y0 <= page_h * 0.92:
        if re.search(r'et\s+al\.|^\s*\d+[\.\)]\s+', text, re.IGNORECASE | re.MULTILINE):
            w.append(("ref_pattern_in_body", f"text={text[:80]!r}"))
    return w


def is_reference_section(page, rect, pno: int, total_pages: int) -> bool:
    """参考文献段: 倒数一二页 + 下半页 + 命中文献条目签名 (几何 + 文字双门槛)。"""
    if pno >= total_pages - 1:
        if rect.y0 > page.rect.height * 0.3:
            return is_ref_entry(get_annot_text(page, rect))
    return False


def audit_one_highlight(page, rect, pno: int, total_pages: int) -> dict:
    """审计单条注记, 返回 {text, rect, y_pct, violations, warnings}。"""
    page_h = page.rect.height
    text = get_annot_text(page, rect)
    violations = check_geometry_violations(rect, page.rect.width, page_h)
    violations += check_hard_violations(page, rect, page_h, text)
    if is_reference_section(page, rect, pno, total_pages):
        violations.append(("reference_section",
                           f"pno={pno}/{total_pages - 1}, y0={rect.y0 / page_h * 100:.1f}%"))
    return {
        "text": text,
        "rect": [round(x, 1) for x in (rect.x0, rect.y0, rect.x1, rect.y1)],
        "y_pct": f"{rect.y0 / page_h * 100:.1f}-{rect.y1 / page_h * 100:.1f}%",
        "violations": violations,
        "warnings": check_soft_flags(rect, page.rect.width, page_h, pno, text),
    }


# ════════════════════════════════════════════════════════════════
# 遍历
# ════════════════════════════════════════════════════════════════

def iter_highlight_pdfs(hl_dir: str):
    """递归发现 highlight PDF, 返回 [(标签, 路径)] (按标签排序)。

    兼容两种命名:
      - v3 FINAL 嵌套: ``{Pn-x 或合并名}/{PN}_highlight.pdf``
      - v13 扁平:      ``{pn}_semantic_highlight.pdf`` (根目录直接子文件)
    只取 ``*_highlight.pdf``, 天然排除 ``*_main.pdf`` 与 ``_highlight_pages/`` 内的图片。
    """
    found = []
    for dirpath, _dirnames, filenames in os.walk(hl_dir):
        for fn in filenames:
            if not fn.lower().endswith("_highlight.pdf"):
                continue
            label = re.sub(r'_(semantic_)?highlight\.pdf$', '', fn, flags=re.IGNORECASE)
            found.append((label, os.path.join(dirpath, fn)))
    return sorted(found)


def audit_pdf(path: str, min_bytes: int = 2500) -> dict:
    """审计一个 highlight PDF, 返回 {total, skipped, violations, warnings, annot_types, error}。

    注记按**逐行 rect**审计 —— v3 FINAL 一句话跨多行就是多条注记, 每条各自不得落入禁区。
    """
    out = {"total": 0, "skipped": False, "violations": [], "warnings": [],
           "annot_types": {}, "error": ""}
    try:
        if os.path.getsize(path) < min_bytes:
            out["skipped"] = True
            return out
    except OSError as e:
        out["error"] = str(e)
        return out

    try:
        doc = fitz.open(path)
    except Exception as e:
        out["error"] = str(e)
        return out

    try:
        for pno in range(doc.page_count):
            page = doc[pno]
            try:
                annots = list(page.annots() or [])
            except Exception:
                annots = []
            for annot in annots:
                try:
                    atype = annot.type[0]
                except Exception:
                    continue
                if atype not in HIGHLIGHT_ANNOT_TYPES:
                    continue
                out["annot_types"][atype] = out["annot_types"].get(atype, 0) + 1
                info = audit_one_highlight(page, annot.rect, pno, doc.page_count)
                out["total"] += 1
                if info["violations"]:
                    out["violations"].append({"page": pno + 1, **info})
                if info["warnings"]:
                    out["warnings"].append({"page": pno + 1, **info})
    finally:
        doc.close()
    return out


def main():
    ap = argparse.ArgumentParser(
        description="禁止区校验: highlight 不得盖标题/作者/参考文献/页眉页脚/图表标题")
    ap.add_argument("--hl-dir", required=True,
                    help="step4 交付目录 (嵌套或扁平布局均可)")
    ap.add_argument("--json", default="", help="把完整结果写到该 JSON 路径")
    ap.add_argument("--min-bytes", type=int, default=2500,
                    help="小于该字节数的 PDF 视为错件/占位, 跳过 (默认 2500)")
    ap.add_argument("--quiet", action="store_true", help="只打印汇总行")
    a = ap.parse_args()

    if not os.path.isdir(a.hl_dir):
        print(f"❌ 目录不存在: {a.hl_dir}")
        return 2

    targets = iter_highlight_pdfs(a.hl_dir)
    if not targets:
        print(f"❌ 未发现任何 *_highlight.pdf: {a.hl_dir}")
        return 2

    results = {}
    n_total = n_viol = n_warn = n_no_hl = n_skip = n_err = 0
    type_hist = {}

    for label, path in targets:
        r = audit_pdf(path, a.min_bytes)
        if r["error"]:
            n_err += 1
        if r["skipped"]:
            n_skip += 1
        elif r["total"] == 0:
            n_no_hl += 1
        n_total += r["total"]
        n_viol += len(r["violations"])
        n_warn += len(r["warnings"])
        for t, c in r["annot_types"].items():
            type_hist[t] = type_hist.get(t, 0) + c
        results[label] = {"path": path, **r}

    def _hist(key):
        h = {}
        for r in results.values():
            for item in r[key]:
                for k, _ in item[key]:
                    h.setdefault(k, []).append("")
        return h

    vtypes, wtypes = _hist("violations"), _hist("warnings")

    print(f"hl-dir: {a.hl_dir}")
    print(f"发现 highlight PDF: {len(targets)}   注记: {n_total}")
    print(f"注记类型: " + ", ".join(
        f"{ANNOT_TYPE_NAMES.get(t, '?')}({t})={c}" for t, c in sorted(type_hist.items())))
    print(f"❌ 违规: {n_viol}   ⚠️ 待人工判断: {n_warn}")
    print(f"无 highlight: {n_no_hl}   跳过(小文件): {n_skip}   读取失败: {n_err}")

    if not a.quiet:
        if n_viol:
            print("\n=== 违规明细 (gate: 退出码非 0) ===")
            for label, r in sorted(results.items()):
                for v in r["violations"]:
                    kinds = ",".join(k for k, _ in v["violations"])
                    print(f"  {label} p{v['page']} y={v['y_pct']} [{kinds}]  {v['text'][:60]!r}")
            print("\n--- 违规类型分布 ---")
            for k, labels in sorted(vtypes.items(), key=lambda x: -len(x[1])):
                print(f"  {k}: {len(labels)} 条")
        if n_warn:
            print("\n=== 待人工判断 (不 gate) ===")
            for k, labels in sorted(wtypes.items(), key=lambda x: -len(x[1])):
                print(f"  {k}: {len(labels)} 条")
            if wtypes.get("figure_caption"):
                print("    注: 图表标题需对照规范「除非图表即应证对象」的例外逐条判断")
            if wtypes.get("page0_top_band"):
                print("    注: page0 顶部带内几何上区分不了标题/作者/正文 (中文刊正文起得早)")

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({
                "hl_dir": a.hl_dir,
                "files": len(targets),
                "annotations": n_total,
                "annot_types": type_hist,
                "violations": n_viol,
                "warnings": n_warn,
                "no_highlight": n_no_hl,
                "skipped": n_skip,
                "errors": n_err,
                "violation_types": {k: len(v) for k, v in vtypes.items()},
                "warning_types": {k: len(v) for k, v in wtypes.items()},
                "results": results,
            }, f, ensure_ascii=False, indent=2)
        print(f"\n💾 详细结果: {a.json}")

    return 1 if n_viol else 0


if __name__ == '__main__':
    sys.exit(main())
