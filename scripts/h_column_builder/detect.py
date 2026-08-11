#!/usr/bin/env python3
"""
h_column_builder.py — H 列 v5.0 内容生成器 (2026-08-02)

基于用户的修正指令:
1. 不需要本地路径, 只需要本地文件名
2. 主文件需要列出文献信息 (标题, 作者, 期刊, 年/卷/期/页, 出版, DOI)
3. 多引用结构 C 列已有类似内容, 不需要保留
4. 视觉关联数据扩展整合为: 视觉对齐/数据对齐/视觉语义推理

核心功能:
- parse_d_field(d): 解析 CSV D 列 → {authors, title, journal, year, vol, issue, pages, type}
- parse_c_field(c): 解析飞书 C 列 → {visual_alignment, data_alignment, semantic_reasoning}
- build_h_md(...): 生成 H 列 markdown 字符串
- markdown_to_rich_text_v3(...): markdown → 飞书 rich_text (保留换行 + 裸 URL)
"""

import re
from typing import Dict, List, Optional


# ════════════════════════════════════════════════════════════════════
# 解析 CSV D 列 (作者/标题/期刊/年份/卷期页)
# ════════════════════════════════════════════════════════════════════


def detect_main_pdf_mismatch(pn_x: str, info_d: Dict, scan: Dict, d_raw: Optional[str] = None) -> Optional[Dict]:
    """
    v9.5: 检测 main PDF 是否与 D 列文献匹配
    
    v9.7: 跳过共享目录 (跨 slide 共享引用, 目录名含 _ ) 和 manifest 标记的共享引用
    
    Returns:
        None - 匹配
        Dict {mismatch_type, expected, actual, note} - 错位
    """
    # v9.7: 跳过共享目录 (跨 slide 共享引用)
    if '_' in pn_x[2:]:  # 目录名如 P15-1_P16-1_P17-1
        return None
    # v9.7: 跳过 manifest 标记的共享引用
    manifest = scan.get("manifest", {})
    if manifest.get("is_shared_reference"):
        return None
    if not scan.get("main"):
        return None

    actual_main = scan.get("main_pdf", "")
    if not actual_main:
        return None

    actual_lower = actual_main.lower()

    # P3-1 GLOBOCAN 例外
    if pn_x == "P3-1":
        if "globocan" in actual_lower or "gco.iarc" in actual_lower:
            return None
        else:
            return {
                "mismatch_type": "GLOBOCAN 错位",
                "expected": "GLOBOCAN/IARC PDF",
                "actual": actual_main,
                "note": "D 列是 GLOBOCAN 2022 但 main PDF 不是 IARC 文档"
            }

    # 直接从原始 D 列抽取所有可能的关键词
    import re as _re_m

    text_to_match = d_raw if d_raw else ""

    # 加入 info_d 中所有可能的字段
    for field in ["authors", "journal", "title", "year", "volume", "issue", "pages", "abstract_id"]:
        v = info_d.get(field, "")
        if v:
            text_to_match += " " + str(v)

    # 抽取所有可能关键词
    candidates = set()

    # 1. 英文单词 (>=3 字符)
    words = _re_m.findall(r'[a-zA-Z]{3,}', text_to_match)
    for w in words:
        candidates.add(w.lower())

    # 2. 中文词 (>=2 字符)
    chinese_words = _re_m.findall(r'[\u4e00-\u9fff]{2,}', text_to_match)
    for w in chinese_words:
        candidates.add(w)

    # 3. 期刊缩写映射
    journal_abbrs = {
        "j hepatol": ["jhepatol", "j_hepatol"],
        "j clin oncol": ["jco", "jclinoncol"],
        "jama oncol": ["jamaoncol"],
        "front oncol": ["frontoncol"],
        "front immunol": ["frontimmunol"],
        "front pharmacol": ["frontpharmacol"],
        "br j cancer": ["bjc", "brjcancer"],
        "nat commun": ["natcommun"],
        "nat rev cancer": ["natrevcancer"],
        "nat rev immunol": ["natrevimmunol"],
        "lancet": ["lancet"],
        "lancet oncol": ["lancetoncol"],
        "liver cancer": ["livercancer"],
        "liver int": ["liverint"],
        "clin cancer res": ["clincancerres"],
        "hepatology": ["hepatology"],
        "immunity": ["immunity"],
        "n engl j med": ["nejm"],
        "j am med assoc": ["jama"],
        "nccn": ["nccn"],
        "csco": ["csco"],
        "esmo": ["esmo"],
        "asco": ["asco"],
        "apasl": ["apasl"],
        "easl": ["easl"],
        "aasld": ["aasld"],
        "j natl cancer cent": ["jncc", "jnatlcancercent"],
        "gastroenterology": ["gastro", "gastroenterology"],
        "jama": ["jama"],
        "ann oncol": ["annoncol"],
        "oncotarget": ["oncotarget"],
        "acta crystallogr": ["actacrystallogr"],
        "anticancer res": ["anticancerres"],
        "nat rev": ["natrev"],
        "med": ["med"],
    }
    text_lower = text_to_match.lower()
    for j_full, abbrs in journal_abbrs.items():
        if j_full in text_lower:
            candidates.update(abbrs)

    # 4. 会议名 + 摘要号
    if info_d.get("conference_name"):
        candidates.add(info_d["conference_name"].lower())
    if info_d.get("abstract_id"):
        candidates.add(info_d["abstract_id"].lower())

    # 5. 年份
    if info_d.get("year"):
        candidates.add(str(info_d["year"]))

    # 检查 candidates 是否有任何在 actual_lower 中
    actual_no_dash = actual_lower.replace("-", "")

    matched = []
    for c in candidates:
        if not c:
            continue
        c_lower = c.lower() if isinstance(c, str) else c
        if c_lower in actual_lower or c_lower in actual_no_dash:
            matched.append(c)

    # 阈值: 至少 1 个关键词匹配
    if not matched:
        return {
            "mismatch_type": "无任何关键词匹配",
            "expected": f"前 5 个关键词 = {list(candidates)[:5]}",
            "actual": actual_main,
            "note": f"D 列无任何关键词匹配 main PDF. D 列: {text_to_match[:80]}"
        }

    return None




def detect_main_pdf_content_mismatch(pn_x: str, info_d: Dict, scan: Dict, d_raw: Optional[str] = None) -> Optional[Dict]:
    """
    v9.5: 检测 main PDF 实际内容是否与 D 列文献匹配 (基于 page 1 文本内容)
    
    v9.7: 跳过共享目录 (跨 slide 共享引用, 目录名含 _ )
    
    Returns:
        None - 匹配
        Dict {mismatch_type, ...} - 错位
    """
    # v9.7: 跳过共享目录
    if '_' in pn_x[2:]:
        return None
    if not scan.get("main"):
        return None
    if not scan.get("main_pdf_path"):
        return None

    actual_main = scan.get("main_pdf", "")
    if not actual_main:
        return None

    # 读取 main PDF page 1
    import fitz as _fitz_c
    try:
        doc = _fitz_c.open(scan.get("main_pdf_path", ""))
        if len(doc) == 0:
            doc.close()
            return None
        page1_text = doc[0].get_text()
        doc.close()
    except:
        return None

    if not page1_text:
        return None

    page1_lower = page1_text.lower()

    # P3-1 GLOBOCAN 例外
    if pn_x == "P3-1":
        if "globocan" in page1_lower or "gco.iarc" in page1_lower or "cancer observatory" in page1_lower:
            return None
        else:
            return {
                "mismatch_type": "GLOBOCAN 内容错位",
                "expected": "GLOBOCAN/IARC PDF",
                "actual": actual_main,
                "note": f"main PDF page 1 不是 GLOBOCAN 内容"
            }

    # 内容错位检查 1: main 是 study protocol, 但 D 列是论文
    # 严格判断: page 1 含 "Protocol Number" / "Study Drug Number" 等明显 protocol 标识
    is_protocol = (
        "protocol number" in page1_lower or
        "study drug number" in page1_lower or
        "hengrui confidential" in page1_lower or
        ("clinical study of " in page1_lower and "protocol" in page1_lower and len(page1_text) > 1500) or
        # Novartis 药物 protocol
        ("novartis" in page1_lower and "protocol" in page1_lower)
    )

    if is_protocol:
        return {
            "mismatch_type": "main PDF 是 Study Protocol 不是论文",
            "expected": f"{info_d.get('journal', '')} {info_d.get('year', '')} 论文",
            "actual": actual_main,
            "note": f"main PDF 是 study protocol (含 'Protocol Number'/'Study Drug Number' 关键词), 不是 {info_d.get('journal', '')} 论文"
        }

    # 内容错位检查 2: main 是其他研究的 appendix / supplementary
    # 但这个判断太严格, 不检查

    return None



