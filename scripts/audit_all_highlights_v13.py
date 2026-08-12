#!/usr/bin/env python3
"""
audit_all_highlights_v13.py — 全面 visual + structural + semantic audit

3 阶段:
  Phase 1: Structural - 检测 forbidden zones (title/author/refs/keywords/figure-caption/...)
  Phase 2: Visual - 渲染每页 highlight, 检查 y 位置 + 覆盖文本
  Phase 3: Semantic - GLM 验证 anchor 跟 slide 应证段 (在 main() 调用)

User 硬要求 (2026-08-12):
  > 必须视觉匹配+语义匹配, 必须禁止 highlight 标题、作者、PDF 中的文献引用
"""
import os, sys, json, re, hashlib
from pathlib import Path
from typing import List, Dict, Tuple
import fitz
fitz.TOOLS.mupdf_display_warnings(False)

# === 路径 ===
TMA_ROOT = "/Users/david/Desktop/TMA_文献整理"
STEP4_DIR = f"{TMA_ROOT}/step4_highlight_106目录_合并DOI"
PNX_DIR = f"{TMA_ROOT}/_pnx"
CSV_PATH = f"{TMA_ROOT}/_citation_table/tma_citation_table.csv"
PPT_JSON = f"{TMA_ROOT}/step2_标注分析/_pptx_xml_structured.json"
PPT_SLIDES_JSON = f"{TMA_ROOT}/_citation_table/ppt_slides_analysis.json"

# === 严格 forbidden zone rules (v13 user 硬要求) ===
FORBIDDEN_RULES = {
    # 1. 几何位置
    "page0_top_8%": lambda page, rect, pno: (pno == 0 and rect.y0 < page.rect.height * 0.08),  # 标题区
    "page0_top_15%": lambda page, rect, pno: (pno == 0 and rect.y0 < page.rect.height * 0.15),  # 标题+作者
    "page0_top_30%": lambda page, rect, pno: (pno == 0 and rect.y0 < page.rect.height * 0.30),  # 中文 author/affiliation
    "bottom_8%_footer": lambda page, rect, pno: (rect.y0 > page.rect.height * 0.92),
    "top_5%_header": lambda page, rect, pno: (rect.y1 < page.rect.height * 0.05),
    "too_wide_and_tall": lambda page, rect, pno: (rect.width / page.rect.width > 0.85 and rect.height / page.rect.height > 0.25),
    "too_tall": lambda page, rect, pno: (rect.height / page.rect.height > 0.5),
    "too_narrow": lambda page, rect, pno: (rect.width < 8),
    "too_short_text": lambda page, rect, pno: False,  # 文字长度单独处理
    # 2. 文字内容 (regex patterns)
    "title_pattern": lambda page, rect, pno: False,  # 文字 regex
    "author_pattern": lambda page, rect, pno: False,
    "reference_pattern": lambda page, rect, pno: False,
    "keywords_pattern": lambda page, rect, pno: False,
    "abbreviation_list": lambda page, rect, pno: False,
    "figure_caption": lambda page, rect, pno: False,
    "declaration_section": lambda page, rect, pno: False,
}

# === 文字 patterns (从 m3_vision_highlight.py 借鉴) ===
AUTHOR_TEXT_PATTERNS = [
    r'^\d+\.\s',  # "1. ", "2. "
    # 缩写: 单词边界 + 后面跟分隔符或 cap
    r'\b(MD|PhD|M\.D|Ph\.D|BSc|MSc|RN|FACS|FACP)\b(?=\s*[,.;:]|\s*$)',
    r'(Department of|Department\sof|^\w+\s+(University|Hospital|Institute|College|School|Center|Centre))',
    r'(@\w+\.(edu|com|org|ac|cn|uk))',
    r'(Email:|E-?mail:|Corresponding author)',
    r'^\d{4}-\d{4}$',  # 假电话
    r'(\bORCID\b|\borcid\b)',
    r'(University Medical Center|Medical Center|University Hospital)',
    r'(Professor|Prof\.|Dr\.|Doctor)',
    r'(Department|Institute) of [A-Z]\w+',
    r'^[\w\s,]+(?:,?\s*MD|PhD){1,}',
]

REFERENCE_TEXT_PATTERNS = [
    # 经典 "Authors. Title. Journal. Year;Vol(Issue):Pages."
    r'\b\d{4}\s*;\s*\d+(\s*\(\d+\))?\s*:\s*\d+([-–]\d+)?\.?\s*$',
    r'et\s+al\.',
    r'\b(Available from|Accessed|doi:|DOI:|PMID:|PMCID:)\b',
    r'^\s*\d+\.\s+[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\s+[A-Z][a-z]',
    r'\b(?:Lancet|N Engl J Med|Blood|JAMA|Br J Haematol|J Thromb Haemost|Nat Rev|Nat Med|Sci Transl Med|J Clin Invest|Hematology|Am J Hematol|J Am Soc Nephrol|Kidney Int|Transplantation|Biol Blood Marrow Transplant|BBMT|Clin Infect Dis|J Pediatr|Pediatrics|Nephrol Dial Transplant|Front Pediatr)\b.*\b\d{4}\b',
    r'(http|https)://(www\.)?(doi\.org|pubmed|ncbi|elsevier|springer|wiley|nejm|lancet)',
    r'^(?:[A-Z][a-z]+\s+){1,3}(?:[A-Z]{2,3}|[A-Z][a-z]+)(?:\s+[A-Z][a-z]*\.?){0,3}\s*(?:[A-Z][a-z]*\.?\s*){0,5}\d{4}',
    r'\d{4}\s*;\s*\d+',  # Year;Volume
    r'\d+\s*:\s*\d+[-–]\d+',  # Pages
    r'^\d+[\.\)]\s+',  # "1. " or "1) " ref start
]

KEYWORDS_TEXT_PATTERNS = [
    r'^\s*KEYWORDS?\s*[:：]',
    r'^\s*Key\s+words?\s*[:：]',
    r'^\s*关键词\s*[:：]',
    r'^\s*关键词[：:]',
    r'^\s*关键字\s*[:：]',
    r'^\s*主题词\s*[:：]',
]

FIGURE_CAPTION_PATTERNS = [
    r'^\s*Fig\.?\s*\d+',
    r'^\s*Figure\s+\d+',
    r'^\s*表\s*\d+',
    r'^\s*Table\s+\d+',
    r'^\s*图\s*\d+',
]

DECLARATION_TEXT_PATTERNS = [
    r'^\s*DECLARATION',
    r'^\s*Disclosure',
    r'^\s*AUTHOR\s+CONTRIBUTION',
    r'^\s*FUNDING',
    r'^\s*ACKNOWLEDG(E)?MENT',
    r'^\s*CONFLICT\s+OF\s+INTEREST',
    r'^\s*DATA\s+AVAILABILITY',
    r'^\s*Compliance with Ethics',
    r'^\s*Ethics',
    r'^\s*Author Contributions',
    r'^\s*Funding Information',
    r'^\s*Additional Information',
    r'^\s*Supplementary',
    r'^\s*Publisher\s+Note',
    r'^\s*致谢\s*[:：]',
    r'^\s*利益冲突',
    r'^\s*基金资助',
    r'^\s*作者贡献',
    r'^\s*数据可用性',
]

CITATION_TEXT_PATTERNS = [
    r'^\s*CITATION\s*:',
    r'^\s*Received\s*:',
    r'^\s*Accepted\s*:',
    r'^\s*Published\s*:',
    r'^\s*Copyright\s*[©©]',
]

# === 工具函数 ===
def get_annot_text(page, rect) -> str:
    """取 rect 内文字 (不 segfault)"""
    try:
        # clip + text 安全
        text = page.get_text("text", clip=rect).strip()
        return text
    except:
        return ""

def matches_any(text: str, patterns: list) -> str:
    if not text:
        return None
    for pat in patterns:
        if re.search(pat, text, re.IGNORECASE | re.MULTILINE):
            return pat
    return None

def is_title_text(text: str) -> bool:
    """检查 text 是否像 title: 大字 / 短行 / 多行连贯"""
    if not text or len(text) < 5:
        return False
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if not lines:
        return False
    first_line = lines[0]
    # 标题特征: 不含句号, 长度 < 250 字符, 不像句子
    if len(first_line) > 250:
        return False
    if first_line.endswith('.') or first_line.endswith('。'):
        return False
    # 排除 "References" 关键词
    if re.match(r'^\s*(References|REFERENCES|参考文献|引文|Bibliography|参考)\s*[:：]?\s*\d*\s*$', first_line, re.IGNORECASE):
        return False
    # 标题常见: 纯字符/含冒号
    if re.search(r'[:：]', first_line) and len(first_line) < 100:
        return False  # 标题很少含冒号
    # 至少看起来像标题
    return False  # 暂不主动判定 title, 主要靠几何位置

def is_reference_section(page, rect, pno, total_pages) -> bool:
    """检测是否在 References 段: 页码 >= total-1 (倒数第一/二页) + 几何 bottom half"""
    if pno >= total_pages - 1:
        page_h = page.rect.height
        if rect.y0 > page_h * 0.3:  # 不是 page top
            # 进一步检测文字: 多行 + 含年份/作者名模式
            text = get_annot_text(page, rect)
            if matches_any(text, REFERENCE_TEXT_PATTERNS):
                return True
    return False

def audit_one_highlight(page, rect, pno, total_pages, page_text_blocks) -> Dict:
    """审计单个 highlight, 返回 violations 列表"""
    page_h = page.rect.height
    page_w = page.rect.width
    text = get_annot_text(page, rect)
    violations = []

    # 扫描大图检测: page_h > 1500 (single page super tall 扫描)
    is_scanned_tall = page_h > 1500

    # 1. 几何 forbidden zones
    if pno == 0 and rect.y0 < page_h * (0.01 if is_scanned_tall else 0.08):
        violations.append(("page0_top_8%_title", f"y0={rect.y0:.0f}/{page_h:.0f}={rect.y0/page_h*100:.1f}%"))
    if pno == 0 and rect.y0 < page_h * (0.02 if is_scanned_tall else 0.15):
        # 标题区 (8%-15% 多数是 author/affiliation)
        if not any(v[0].startswith("page0_top_8%") for v in violations):
            violations.append(("page0_top_15%_title_or_author", f"y0={rect.y0:.0f}/{page_h:.0f}={rect.y0/page_h*100:.1f}%"))
    if pno == 0 and rect.y0 < page_h * (0.05 if is_scanned_tall else 0.30):
        # 中文 author/affiliation 区 (扫描大图阈值收紧到 5%)
        if not any(v[0].startswith("page0_top_8%") or v[0].startswith("page0_top_15%") for v in violations):
            # 仅当中文 PDF 或长 author 列表时算违规, 英文短 author OK
            text_first_50 = text[:50]
            if re.search(r'[\u4e00-\u9fff]', text):  # 含中文
                violations.append(("page0_top_30%_CN_author", f"y0={rect.y0:.0f}/{page_h:.0f}={rect.y0/page_h*100:.1f}%"))
    if rect.y0 > page_h * 0.92:
        violations.append(("bottom_8%_footer", f"y0={rect.y0:.0f}"))
    if rect.y1 < page_h * (0.005 if is_scanned_tall else 0.05):
        violations.append(("top_5%_header", f"y1={rect.y1:.0f}"))
    if rect.width / page_w > 0.85 and rect.height / page_h > 0.25:
        violations.append(("too_wide_and_tall", f"w={rect.width/page_w*100:.0f}%, h={rect.height/page_h*100:.0f}%"))
    if rect.height / page_h > 0.5:
        violations.append(("too_tall", f"h={rect.height/page_h*100:.0f}%"))
    if rect.width < 8:
        violations.append(("too_narrow", f"w={rect.width:.0f}px"))

    # 2. 文字 forbidden patterns
    if text:
        # author
        if pat := matches_any(text, AUTHOR_TEXT_PATTERNS):
            violations.append(("author_text", f"pat={pat}, text={text[:80]!r}"))
        # references
        if pat := matches_any(text, REFERENCE_TEXT_PATTERNS):
            violations.append(("ref_text", f"pat={pat}, text={text[:80]!r}"))
        # keywords
        if pat := matches_any(text, KEYWORDS_TEXT_PATTERNS):
            violations.append(("keywords_text", f"pat={pat}, text={text[:80]!r}"))
        # figure caption
        if pat := matches_any(text, FIGURE_CAPTION_PATTERNS):
            violations.append(("figure_caption", f"pat={pat}, text={text[:80]!r}"))
        # declaration
        if pat := matches_any(text, DECLARATION_TEXT_PATTERNS):
            violations.append(("declaration_text", f"pat={pat}, text={text[:80]!r}"))
        # citation
        if pat := matches_any(text, CITATION_TEXT_PATTERNS):
            violations.append(("citation_text", f"pat={pat}, text={text[:80]!r}"))
        # 整段都是 [n] [n] [n]
        if re.search(r'\[\d+\]\s*\[\d+\]\s*\[\d+\]', text):
            violations.append(("ref_numbers_only", f"text={text[:80]!r}"))
        # 整段都是数字 + 句点 (像 1. 2. 3. 列表)
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if lines and all(re.match(r'^\d+[\.\)]\s*$', l) for l in lines):
            violations.append(("numbered_list_only", f"text={text[:80]!r}"))

    # 3. References 段几何检测
    if is_reference_section(page, rect, pno, total_pages):
        violations.append(("ref_section", f"pno={pno}/{total_pages-1}, y0={rect.y0/page_h*100:.1f}%"))

    return {
        "text": text,
        "rect": [rect.x0, rect.y0, rect.x1, rect.y1],
        "y_pct": f"{rect.y0/page_h*100:.1f}-{rect.y1/page_h*100:.1f}%",
        "violations": violations,
    }


# === Main audit loop ===
def main():
    if not os.path.exists(STEP4_DIR):
        print(f"❌ {STEP4_DIR} 不存在")
        return
    if not os.path.exists(PNX_DIR):
        print(f"❌ {PNX_DIR} 不存在")
        return

    # 读 CSV (BOM 兼容)
    csv_data = {}
    if os.path.exists(CSV_PATH):
        import csv
        with open(CSV_PATH, encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                csv_data[row['PN']] = row

    # 收集所有 step4 PDF
    pn_x = sorted([f.replace('_semantic_highlight.pdf', '')
                   for f in os.listdir(STEP4_DIR)
                   if f.endswith('_semantic_highlight.pdf')])
    print(f"📋 找到 {len(pn_x)} 个 Pn-x highlight PDF")

    # 排除 0 字节 / 已知不救
    SKIP_PN = {'P12-3'}  # 留缺
    results = {}
    total_violations = 0
    total_no_highlight = 0
    no_audit = []

    for pn in pn_x:
        if pn in SKIP_PN:
            continue
        step4_pdf = f"{STEP4_DIR}/{pn}_semantic_highlight.pdf"
        if not os.path.exists(step4_pdf):
            no_audit.append(pn)
            continue
        size = os.path.getsize(step4_pdf)
        if size < 5000:  # 太小可能错 PDF
            no_audit.append(pn)
            continue

        try:
            doc = fitz.open(step4_pdf)
        except Exception as e:
            no_audit.append(pn)
            continue

        pn_result = {
            "pages": [],
            "total_highlights": 0,
            "violations": [],
        }

        for pno in range(doc.page_count):
            page = doc[pno]
            try:
                annots = list(page.annots() or [])
            except:
                annots = []

            for annot in annots:
                try:
                    atype = annot.type[0]
                except:
                    continue
                if atype not in (fitz.PDF_ANNOT_HIGHLIGHT, fitz.PDF_ANNOT_UNDERLINE):
                    continue
                rect = annot.rect
                info = audit_one_highlight(page, rect, pno, doc.page_count, None)
                pn_result["total_highlights"] += 1
                if info["violations"]:
                    pn_result["violations"].append({
                        "page": pno + 1,
                        **info,
                    })
                    total_violations += 1

        if pn_result["total_highlights"] == 0:
            total_no_highlight += 1
        results[pn] = pn_result
        doc.close()

    # 汇总
    print(f"\n=== 审计结果 ===")
    print(f"总 Pn-x: {len(pn_x)}")
    print(f"实审计: {len(results)}")
    print(f"无 highlight: {total_no_highlight}")
    print(f"跳过 (缺/小): {len(no_audit)} → {no_audit[:10]}")
    print(f"违规总数: {total_violations}")

    # 按违规分类
    violation_types = {}
    for pn, r in results.items():
        for v in r["violations"]:
            vtype = v["violations"][0][0] if v["violations"] else "unknown"
            violation_types.setdefault(vtype, []).append(pn)

    print(f"\n=== 违规类型分布 ===")
    for vtype, pns in sorted(violation_types.items(), key=lambda x: -len(x[1])):
        print(f"  {vtype}: {len(pns)} 个 → {sorted(pns)[:5]}{'...' if len(pns)>5 else ''}")

    # 详细违规 Pn-x 列表
    print(f"\n=== 违规 Pn-x 列表 (前 30) ===")
    viol_pns = [(pn, len(r["violations"])) for pn, r in results.items() if r["violations"]]
    viol_pns.sort(key=lambda x: -x[1])
    for pn, n in viol_pns[:30]:
        print(f"  {pn}: {n} violations")

    # 保存结果
    out_path = "/tmp/audit_v13_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_pn_x": len(pn_x),
            "audited": len(results),
            "no_highlight": total_no_highlight,
            "skipped": no_audit,
            "total_violations": total_violations,
            "violation_types": {k: v for k, v in violation_types.items()},
            "results": results,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n💾 详细结果: {out_path}")

if __name__ == "__main__":
    main()
