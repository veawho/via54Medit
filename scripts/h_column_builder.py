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

def parse_d_field(d: str) -> Dict[str, str]:
    """
    解析 D 列 (BibTeX 风格) → 文献信息字典
    
    Returns:
        {
            "authors": "Qin S, et al",
            "title": "...",
            "journal": "J Clin Oncol",
            "year": "2013",
            "volume": "31",
            "issue": "28",
            "pages": "3501-3508",
            "abstract_id": "1494P",
            "type": "literature" | "conference_abstract"
        }
    
    支持格式:
        - 中文期刊 [J]: 作者. 标题[J]. 期刊, 年, 卷(期):页
        - 英文标准; 作者. 期刊. 年;卷(期):页
        - 英文 alt, 作者. 期刊, 年, 卷(期):页
        - Nature 系: 作者. 期刊 卷, 页 (年)
        - 期刊带 vol: 作者. 期刊 vol. X,Y (year): 页
        - e页: 作者, et al. 期刊, 年, 卷: e页
        - 会议摘要: 作者. ESMO. Abstract 1494P / LBA479
        - 简: 作者. 期刊. 年
    """
    info = {
        "authors": "", "title": "", "journal": "", "year": "",
        "volume": "", "issue": "", "pages": "",
        "abstract_id": "", "type": "literature"
    }
    
    # 年份
    year_m = re.search(r"\b(\d{4})\b", d)
    if year_m:
        info["year"] = year_m.group(1)

    # 会议摘要 v9: 优先识别会议名 + 摘要号
    # 1. APASL/ASCO/EASL/AASLD (X 年 + 会议名 + 摘要号)
    conf_m = re.search(r"(\d{4})\s+(APASL|ASCO(?:-GI|-Gl)?|EASL|AASLD)\s+(?:Abstract\s+)?(\w+)", d, re.I)
    if conf_m:
        info["conference_year"] = conf_m.group(1)
        info["conference_name"] = conf_m.group(2).upper()
        info["abstract_id"] = conf_m.group(3)
        info["type"] = "conference_abstract"
        am = re.match(r"^([^\.]+?)\.", d)
        if am:
            info["authors"] = am.group(1).strip().rstrip(",")
        return info

    # 2. ESMO (X 年 ESMO + 摘要号) / ESMO ASIA 2022 Poster 79P
    esmo_m = re.search(r"(\d{4})\s+ESMO(?:\s+(?:ASIA|ASCO))?\.?\s+(?:Abstract\s+)?(?:Poster\s+)?(\w+)", d, re.I)
    if esmo_m:
        info["conference_year"] = esmo_m.group(1)
        info["conference_name"] = "ESMO"
        info["abstract_id"] = esmo_m.group(2)
        info["type"] = "conference_abstract"
        am = re.match(r"^([^\.]+?)\.", d)
        if am:
            info["authors"] = am.group(1).strip().rstrip(",")
        return info

    # 3. CSCO (presented at X CSCO)
    csco_m = re.search(r"(?:presented\s+at\s+)?(\d{4})\s*CSCO", d, re.I)
    if csco_m:
        info["conference_year"] = csco_m.group(1)
        info["conference_name"] = "CSCO"
        info["abstract_id"] = ""
        info["type"] = "conference_abstract"
        am = re.match(r"^([^\.]+?)\.", d)
        if am:
            info["authors"] = am.group(1).strip().rstrip(",")
        return info

    # 4. 通用 ESMO/ASCO/Abstract 关键词检测 (兜底)
    if re.search(r"(ESMO|ASCO|Annual Meeting|Abstract)\s*", d, re.I):
        info["type"] = "conference_abstract"
        abs_m = re.search(r"(?:Abstract|LBA|TiP)\s*(\d+\w*)", d, re.I)
        if abs_m:
            info["abstract_id"] = abs_m.group(1)
    
    # 会议摘要特殊处理
    if info["type"] == "conference_abstract":
        am = re.match(r"^([^\.]+?)\.", d)
        if am:
            info["authors"] = am.group(1).strip().rstrip(",")
        return info
    
    # CN 期刊: 作者. 标题[J]. 期刊, 年, 卷(期):页
    cn_m = re.match(r"^([^\.]+?)\.\s+(.+?)\[J\]\.\s*(.+?)[,，]\s*(\d{4})[,，]\s*(\d+)\((\d+)\)\s*:\s*(\d+(?:[\-–]\d+)?)", d)
    if cn_m:
        info["authors"] = cn_m.group(1).strip().rstrip(",")
        info["title"] = cn_m.group(2).strip()
        info["journal"] = cn_m.group(3).strip()
        info["year"] = cn_m.group(4)
        info["volume"] = cn_m.group(5)
        info["issue"] = cn_m.group(6)
        info["pages"] = cn_m.group(7)
        return info
    
    # 期刊带 vol: 作者. 期刊 vol. X,Y (year): 页
    envel_m = re.search(r"^(.+?)\.\s+(.+?)\s+vol\.\s*(\d+)\s*,\s*(\d+)\s*\((\d{4})\)\s*:\s*(\d+(?:[\-–]\d+)?)", d)
    if envel_m:
        info["authors"] = envel_m.group(1).strip().rstrip(",")
        info["journal"] = envel_m.group(2).strip()
        info["volume"] = envel_m.group(3)
        info["issue"] = envel_m.group(4)
        info["year"] = envel_m.group(5)
        info["pages"] = envel_m.group(6)
        return info
    
    # Nature 系: 期刊 卷, 页 (年)
    nature2_m = re.search(r"^(.+?)\.\s+([A-Z][A-Za-z\s]+?)\s+(\d+)\s*,\s*(\d+(?:[\-–]\d+)?)\s*\((\d{4})\)", d)
    if nature2_m:
        info["authors"] = nature2_m.group(1).strip().rstrip(",")
        info["journal"] = nature2_m.group(2).strip()
        info["volume"] = nature2_m.group(3)
        info["pages"] = nature2_m.group(4)
        info["year"] = nature2_m.group(5)
        return info
    
    # EN 标准 ;: 作者. 期刊. 年[月] ;卷(期):页
    en2_m = re.match(r"^([^\.]+?)\.\s+(.+?)\.\s*(\d{4})(?:\s+\w+)?\s*[;\.]\s*(\d+)\((\d+)\)\s*:\s*(\d+(?:[\-–]\d+)?)", d)
    if en2_m:
        info["authors"] = en2_m.group(1).strip().rstrip(",")
        info["journal"] = en2_m.group(2).strip()
        info["year"] = en2_m.group(3)
        info["volume"] = en2_m.group(4)
        info["issue"] = en2_m.group(5)
        info["pages"] = en2_m.group(6)
        return info
    
    # EN alt: 作者. 期刊, 年, 卷(期):页 (含 _suppl 期)
    en1_m = re.match(r"^([^\.]+?)\.\s+(.+?),\s*(\d{4})[,\s]+(\d+)\(([\w_]+)\)\s*:\s*(\d+(?:[\-–]\d+)?)", d)
    if en1_m:
        info["authors"] = en1_m.group(1).strip().rstrip(",")
        info["journal"] = en1_m.group(2).strip()
        info["year"] = en1_m.group(3)
        info["volume"] = en1_m.group(4)
        info["issue"] = en1_m.group(5)
        info["pages"] = en1_m.group(6)
        return info
    
    # Lancet 简化: 作者. 期刊. 年;卷, 页-页
    lancet_m = re.match(r"^([^\.]+?)\.\s+(.+?),\s*(\d{4})[;\s]+(\d+)[,\s]+(\d+(?:[\-–]\d+)?)", d)
    if lancet_m:
        info["authors"] = lancet_m.group(1).strip().rstrip(",")
        info["journal"] = lancet_m.group(2).strip()
        info["year"] = lancet_m.group(3)
        info["volume"] = lancet_m.group(4)
        info["pages"] = lancet_m.group(5)
        return info
    
    # e页: 作者. 期刊, 年, 卷: e页
    epages_m = re.match(r"^([^\.]+?)\.\s+(.+?),\s*(\d{4})[,\s]+(\d+)\s*:\s*(e\d+)", d)
    if epages_m:
        info["authors"] = epages_m.group(1).strip().rstrip(",")
        info["journal"] = epages_m.group(2).strip()
        info["year"] = epages_m.group(3)
        info["volume"] = epages_m.group(4)
        info["pages"] = epages_m.group(5)
        return info
    
    # 简: 作者. 期刊. 年 (无卷期页)
    simple_m = re.match(r"^([^\.]+?)\.\s+(.+?)\.\s+(\d{4})", d)
    if simple_m:
        info["authors"] = simple_m.group(1).strip().rstrip(",")
        info["journal"] = simple_m.group(2).strip()
        info["year"] = simple_m.group(3)
        return info
    
    return info


# ════════════════════════════════════════════════════════════════════
# 解析飞书 C 列 (PPT 视觉/数据/语义对齐)
# ════════════════════════════════════════════════════════════════════

def parse_c_field(c: str) -> Dict[str, List[str]]:
    """
    解析 C 列 → 三类对齐
    
    Returns:
        {
            "visual_alignment": ["位置1: 标号位置 (Row X/列名)"],
            "data_alignment": ["疗效: X", "关键研究: Y"],
            "semantic_reasoning": ["注: ...", "引文: ..."]
        }
    """
    info = {"visual_alignment": [], "data_alignment": [], "semantic_reasoning": []}
    
    # 视觉对齐: 位置 X: 「...」(位置)
    pos_m = re.findall(r"位置\d+:\s*「(.+?)」\s*\((.+?)\)", c)
    for m in pos_m:
        info["visual_alignment"].append(f"{m[0]} ({m[1]})")
    
    # 视觉关联数据 (Row 数据)
    visual_data_m = re.search(r"视觉关联数据\s*\(P5 表格 Row \d+\)\s*:\s*(.*?)(?=引文|注|跨|$)", c, re.DOTALL)
    if visual_data_m:
        info["visual_alignment"].append("Row 数据:\n" + visual_data_m.group(1).strip())
    
    # v8.5: 引文位置 (整页引文 / 脚注引文)
    quote_loc_m = re.search(r"引文位置\s*:\s*(.+?)(?=\n|$)", c)
    if quote_loc_m:
        info["引文位置"] = quote_loc_m.group(1).strip()
    
    # v8.5: 主标题 / 介绍 / 入组 / 三组治疗 等描述 (整页引文)
    for kw_label in ["主标题:", "banner 介绍:", "主要纳入人群", "三组治疗", "次要终点", "主要终点", "整页引文"]:
        for line in c.split("\n"):
            if kw_label in line and line.strip():
                stripped = line.strip().lstrip("- ").strip()
                if stripped and stripped not in info["visual_alignment"]:
                    info["visual_alignment"].append(f"{stripped[:80]}")
                    break
    
    # 数据对齐: 医学数据点 (中位OS / OS HR / STRIDE / 索拉非尼 / 5年 / mOS / TRAE / etc.)
    # 提取所有可能含医学数据点的行 (不限关键词, 只要含数字 + 医学术语)
    medical_keywords = ["疗效:", "5年", "5-y", "5-y", "OS率", "mOS", "OS HR", "OS",
                       "TRAE", "随访", "mTTFS", "关键研究", "TRAEs", "Grade 3/4",
                       "STRIDE", "索拉非尼", "Len", "T+A", "O+Y", "T+A", "n=", "vs",
                       "ORR", "DCR", "PFS", "OS", "HR", "中位", "率:", "月:", "%",
                       "桥头堡", "队列", "中国#"]
    for line in c.split("\n"):
        stripped = line.strip().lstrip("- ").strip()
        if not stripped:
            continue
        # 含数字且含医学关键词
        if any(kw in line for kw in medical_keywords) and any(c.isdigit() for c in line):
            if stripped not in info["data_alignment"]:
                info["data_alignment"].append(stripped)
    
    # 语义推理: 注/引文/跨文献/支持/主张/语义/main finding
    for line in c.split("\n"):
        if any(kw in line for kw in ["注:", "引文:", "跨文献", "4 与 3", "支持", "主张", "语义", "main finding", "长尾", "100%", "应证于", "应证"]):
            stripped = line.strip().lstrip("- ").strip()
            if stripped and stripped not in info["semantic_reasoning"]:
                info["semantic_reasoning"].append(stripped)
    
    return info


# ════════════════════════════════════════════════════════════════════
# 出版商识别
# ════════════════════════════════════════════════════════════════════

PUBLISHER_MAP = [
    (["Nature", "Sig Transduct"], "Springer Nature"),
    (["Lancet"], "Elsevier"),
    (["NEJM", "N Engl J Med"], "Massachusetts Medical Society"),
    (["J Clin Oncol"], "ASCO / Wolters Kluwer"),
    (["JAMA"], "AMA (American Medical Association)"),
    (["J Hepatol"], "Elsevier (EASL)"),
    (["Med Sci Monit"], "International Scientific Information"),
    (["Cancer"], "Wiley"),
    (["Ann Oncol"], "Elsevier"),
    (["J Natl Cancer Cent"], "Chinese Journal of Cancer (Elsevier)"),
    (["Front Oncol"], "Frontiers Media"),
    (["Gastroenterology"], "AGA (Elsevier)"),
    (["Liver Int"], "Wiley"),
    (["Medicine"], "Wolters Kluwer"),
    (["Frontiers"], "Frontiers Media"),
    (["Clin Cancer Res"], "AACR"),
    (["Int J Mol Sci"], "MDPI"),
    (["GLOBOCAN", "Global Cancer Observatory"], "IARC / WHO (Global Cancer Observatory)"),
    (["中国实用外科"], "国家卫生健康委员会医政司 (中国实用外科杂志)"),
]


def identify_publisher(journal: str) -> str:
    for keywords, publisher in PUBLISHER_MAP:
        if any(kw in journal for kw in keywords):
            return publisher
    return ""


# ════════════════════════════════════════════════════════════════════
# 构建 H 列 markdown
# ════════════════════════════════════════════════════════════════════

def build_h_md(
    pn: str,
    info_d: Dict[str, str],
    info_c: Dict[str, List[str]],
    g_path: str,
    doi: str,
    c_raw: Optional[str] = None,
    row_n: Optional[int] = None,
) -> str:
    """
    生成 H 列 markdown 内容 (v5.0)
    
    Args:
        pn: Pn-x 标号 (如 "2")
        row_n: 飞书 Row 编号 (1 是表头, Row N = P(N-1))
              None 时自动按 Pn 计算 (Row = 11 + (pn-1))
              但这仅适用于 slide 5. slide 3/4 需要外部传入
    """
    import os
    if row_n is None:
        # 默认: slide 5, Row 11 = P5-1
        pn_int = int(pn)
        row_n = pn_int + 10
    
    # 文件名 (从 g_path 提取)
    fname = os.path.basename(g_path) if g_path else f"P5-{pn}_main_*.pdf"
    
    # 类型 emoji
    if info_d["type"] == "conference_abstract":
        type_emoji = "📄 CONFERENCE ABSTRACT"
    elif pn == "1":
        type_emoji = "📋 GUIDELINE"
    else:
        type_emoji = "📄 LITERATURE"
    
    publisher = identify_publisher(info_d["journal"])
    
    # 标题
    title = info_d.get("title", "")
    if not title and info_c.get("visual_alignment"):
        for va in info_c["visual_alignment"]:
            if "引文:" in va:
                title = va.replace("引文:", "").strip()
                break
    
    md_parts = []
    md_parts.append(f"🎯 Row {row_n} (P5-{pn}) — {info_d['journal']} {info_d['year']} 文献应证\n")
    
    # 【📄 主文件】
    md_parts.append("【📄 主文件】 (D 列核心, 主文件 + 文献信息)")
    md_parts.append(f"  - 文件名: `{fname}`")

    if title and title != info_d["journal"]:
        md_parts.append(f"  - 标题: {title[:80]}")
    md_parts.append(f"  - 作者: {info_d['authors']}")
    md_parts.append(f"  - 期刊: {info_d['journal']}")
    vol_issue = f"v{info_d['volume']}" + (f"({info_d['issue']})" if info_d['issue'] else "")
    pages = info_d['pages']
    if vol_issue and pages:
        md_parts.append(f"  - 年/卷/期/页: {info_d['year']}, {vol_issue}: {pages}")
    elif vol_issue:
        md_parts.append(f"  - 年/卷: {info_d['year']}, {vol_issue}")
    else:
        md_parts.append(f"  - 年: {info_d['year']}")
    if publisher:
        md_parts.append(f"  - 出版: {publisher}")
    
    if doi and not doi.startswith("备注"):
        md_parts.append(f"  - DOI: [{doi}](https://doi.org/{doi})")
    elif info_d.get("abstract_id"):
        md_parts.append(f"  - 摘要号: {info_d['abstract_id']}")
    
    md_parts.append("")
    
    # 【⚠️ 应证评分警告】 (main < 0.7 且无 fb)
    if main_score is not None and main_score < 0.7 and not scan.get("fb") and not scan.get("fb_cross_refs"):
        manifest = scan.get("manifest", {})
        missing = manifest.get("missing_data_points", [])
        found = manifest.get("found_data_points", [])
        md_parts.append(f"【⚠️ 应证评分低】 (main={main_score:.2f}, step2 hits {manifest.get('step2_found', 0)}/{manifest.get('step2_total', 0)})")
        md_parts.append(f"  原因: PPT 数据点在 PDF 中匹配率低")
        if missing:
            md_parts.append(f"  未找到数据点: {', '.join(missing[:8])}{'...' if len(missing) > 8 else ''}")
        if found:
            md_parts.append(f"  已找到: {', '.join(found[:8])}{'...' if len(found) > 8 else ''}")
        md_parts.append(f"  说明: PPT 引用数据点在 PDF 中以变体形式出现 (如 '14.4' vs '14.4%'), docling 文本匹配未必完整. 但 main PDF 仍是应证真理. 参考 main PDF 内容核对 PPT 数据点.")

        # v9.6: Vision OCR fallback - 当 PDF 文字找不到数据点时, 用 sensenova_vision API 提取 highlight 图
        vision_data_points = manifest.get("vision_ocr_data_points", [])
        if vision_data_points:
            md_parts.append("")
            md_parts.append(f"  📸 Vision OCR 已提取 ({len(vision_data_points)} 个数据点, 来自 highlight 图):")
            for dp in vision_data_points[:5]:
                md_parts.append(f"    - {dp.get('value', 'N/A')} ({dp.get('description', '')[:40]})")
            if len(vision_data_points) > 5:
                md_parts.append(f"    - ... 等共 {len(vision_data_points)} 个")
            md_parts.append("")
        md_parts.append("")

    # 【🧠 语义等同性推理】 (数值精度等价 + 单位等价)
    manifest = scan.get("manifest", {})
    equiv_matches = manifest.get("equivalent_found_data_points", [])
    if equiv_matches:
        md_parts.append("【🧠 语义等同性推理】 (数值/单位等价)")
        md_parts.append("  算法: 14.4 ≈ 14.40 ≈ 14.400 (浮点等) ; 14.4 ≈ 14.4% (单位等价, 当 PDF 上下文说明数据是百分比)")
        # 显示前 10 个等价匹配
        for eq in equiv_matches[:10]:
            md_parts.append(f"  - '{eq['dp']}' 在 PDF 中以变体 '{eq['variant']}' 出现 → 应证等价")
        if len(equiv_matches) > 10:
            md_parts.append(f"  - ... 等共 {len(equiv_matches)} 个等价命中")
        md_parts.append("")

    # 【✅ main 完整应证】 (当 main_score >= 0.95)
    # 注意: main_score 可能来自 highlight_summary (slide 6+) 而非 step2 (slide 3-5)
    if main_score is not None and main_score >= 0.95:
        manifest = scan.get("manifest", {})
        found_pts = manifest.get("found_data_points", [])
        equiv_pts = manifest.get("equivalent_found_data_points", [])
        found_locs = manifest.get("found_data_point_locations", {})
        total = manifest.get("step2_total", len(found_pts))
        step2_score = manifest.get("step2_score")
        hl_summary = scan.get("highlight_summary", {})

        # 是否满分
        perfect = main_score >= 1.0
        md_parts.append("【✅ main 完整应证 PPT 内容】" + (" ⭐满分" if perfect else ""))

        # 区分 score 来源
        if step2_score is not None:
            # slide 3-5: 真实 step2 docling 应证
            md_parts.append(f"  PPT 标号指向的内容已在 main PDF 中找到 ({len(found_pts)}/{total} 数据点命中, 评分 {main_score:.2f})")
        elif hl_summary and hl_summary.get("terms"):
            # slide 6+: 简化 highlight 应证
            hits = hl_summary.get("hits", 0)
            terms = hl_summary.get("terms", 0)
            page = hl_summary.get("page", "?")
            md_parts.append(f"  PPT 标号指向的内容已在 main PDF highlight 区域找到 ({hits} hits / {terms} terms, page {page})")
            md_parts.append(f"  ⚠️ 此评分基于 highlight 图视觉匹配, 未做 docling 语义级 step2 应证 (待升级)")
        else:
            md_parts.append(f"  PPT 标号指向的内容已在 main PDF 中找到 (评分 {main_score:.2f})")

        # 推理链: PPT 标号 → 语义理解 → PDF 应证位置
        if info_c.get("positions"):
            pos = info_c["positions"][0]
            ppt_text = pos.get("text", "")
            if ppt_text:
                md_parts.append(f"  PPT 引文 (推理源): {ppt_text[:100]}")
            if pos.get("data"):
                md_parts.append(f"  PPT 语义 (推理目标): {pos['data'][:100]}")

        # PDF 应证位置 (核心数据点的具体位置)
        if found_locs:
            # 优先找核心数据点 (带 % 或 > 10 数字)
            core_dps = [dp for dp in found_locs if "%" in dp or dp.replace(".", "").isdigit() and float(dp.replace("%", "")) >= 10]
            core_dps = core_dps[:3] if core_dps else list(found_locs.keys())[:3]
            md_parts.append(f"  📍 main PDF 应证位置 (核心数据):")
            import re as _re_ctx1
            for dp in core_dps:
                locs = found_locs[dp]
                if locs:
                    loc = locs[0]
                    # v8.6: 移除 context 中的完整 URL (避免 markdown_to_rich_text 误识别)
                    ctx = _re_ctx1.sub(r'https?://\S+', '', loc["text_snippet"])[:60].strip()
                    if not ctx:
                        ctx = "(context 截断)"
                    md_parts.append(f"    ✓ '{dp}' → page {loc['page_no']}: {ctx}...")

        # 显示 PDF 命中数据点汇总
        if found_pts:
            md_parts.append(f"  PDF 命中数据点 (前 8 个):")
            for dp in found_pts[:8]:
                md_parts.append(f"    ✓ {dp}")
        if equiv_pts:
            md_parts.append(f"  PDF 等价命中 (前 5 个):")
            for eq in equiv_pts[:5]:
                md_parts.append(f"    ≈ {eq['dp']} (PDF 中以 {eq['variant']} 形式)")
        md_parts.append("")

    # 【🎯 应证推理】 — 完整 5 步推理链 (2026-08-02 用户硬规则 v7.3)
    md_parts.append("【🎯 应证推理】 (完整 5 步推理链: PPT视觉 → 信息要素 → PDF应证)")

    # ① PPT 标号指向位置 (视觉) — v8.5 严格从 C 列视觉描述提取, 不靠 D 列
    md_parts.append("  ① PPT 标号指向位置 (视觉):")
    
    # 整页引文 / 位置描述 / 引文位置 — 三种来源
    if info_c.get("positions"):
        for i, pos in enumerate(info_c["positions"][:3]):
            loc = pos.get("location", "PPT 右半区域")
            text = pos.get("text", "")[:60]
            md_parts.append(f"    - {loc}: {text}")
    elif info_c.get("visual_alignment"):
        for va in info_c["visual_alignment"][:2]:
            md_parts.append(f"    - {va[:80]}")
    elif info_c.get("引文位置"):
        # 整页引文 / 脚注引文
        md_parts.append(f"    - {info_c['引文位置'][:80]}")
    elif info_c.get("data_alignment"):
        # 整页引文 / 无独立位置标号
        for da in info_c["data_alignment"][:1]:
            md_parts.append(f"    - {da[:80]}")
    else:
        md_parts.append("    - (PPT slide 标号位置未识别)")

    # ② PPT 视觉内容 (完整信息要素) — v8.5 严格从 PPT slide 视觉识别 (不依赖 D 列)
    md_parts.append("  ② PPT 视觉内容 (完整信息要素, PPT slide 视觉识别):")
    
    # 优先从 manifest.ppt_data_points (这是 PPT 视觉识别后的真实数据点)
    manifest = scan.get("manifest", {})
    ppt_pts = manifest.get("ppt_data_points", [])
    
    if ppt_pts:
        for dp in ppt_pts[:8]:
            md_parts.append(f"    - 视觉识别数据点: '{dp}'")
    elif info_c.get("data_alignment"):
        for da in info_c["data_alignment"][:3]:
            md_parts.append(f"    - {da[:100]}")
    else:
        md_parts.append("    - (PPT slide 视觉识别未提取到数据点, 待 docling 视觉识别)")

    # ③ 推理: 在 main PDF 中找 PPT 视觉识别的数据点 (v8.5 严格对齐 PPT视觉 vs PDF高亮)
    md_parts.append("  ③ 推理 (信息要素匹配): 需在 main PDF 中找到:")
    
    manifest = scan.get("manifest", {})
    ppt_pts = manifest.get("ppt_data_points", [])
    found_pts = manifest.get("found_data_points", [])
    
    # 列出所有 ppt_pts 作为推理目标
    if ppt_pts:
        for dp in ppt_pts[:8]:
            md_parts.append(f"    - 数据: '{dp}'")
    else:
        # 没 manifest.ppt_data_points 时, 从 C 列 data_alignment 提取
        import re as _re5b
        if info_c.get("data_alignment"):
            for da in info_c["data_alignment"][:5]:
                for num_m in _re5b.finditer(r"\b(\d+(?:\.\d+)?)\s*%?", da):
                    v = num_m.group(1)
                    if "%" in da or len(v) >= 2:
                        if v not in ppt_pts:
                            md_parts.append(f"    - 数据: '{v}'")
                            ppt_pts.append(v)
    
    if info_c.get("引文"):
        md_parts.append(f"    - 文字: {info_c['引文'][:80]}")

    # ④ main PDF 应证位置 — v8.5 严格从 manifest.found_data_point_locations 读取真实应证位置
    md_parts.append("  ④ main PDF 应证位置 (语义推理匹配, PPT视觉 vs PDF高亮双向对齐):")
    
    manifest = scan.get("manifest", {})
    found_locs = manifest.get("found_data_point_locations", {})
    
    if found_locs and isinstance(found_locs, dict):
        # 已 docling/PyMuPDF 真实应证: 显示每个数据点的 page_no + context
        def sort_key(item):
            dp = item[0]
            locs = item[1]
            ctx = locs[0]["text_snippet"] if locs else ""
            if any(kw in ctx.lower() for kw in ["months", "month", "pfs", "os ", "hazard", "survival"]):
                return 0
            if "%" in dp:
                return 1
            try:
                v = float(dp.replace("%", ""))
                if v >= 10:
                    return 2
                else:
                    return 3
            except ValueError:
                return 4
        
        sorted_locs = sorted(found_locs.items(), key=sort_key)
        for dp, locs in sorted_locs[:5]:
            if locs:
                loc = locs[0]
                # v8.6: 移除 context 中的完整 URL (避免 markdown_to_rich_text 误识别, 飞书显示 https://d...)
                import re as _re_ctx
                ctx = _re_ctx.sub(r'https?://\S+', '', loc["text_snippet"])[:60]
                ctx = ctx.strip()
                if not ctx:
                    ctx = "(context 截断)"
                md_parts.append(f"    ✓ '{dp}' → page {loc['page_no']}: {ctx}...")
        if len(found_locs) > 5:
            md_parts.append(f"    ... 等共 {len(found_locs)} 个数据点已应证")
        
        # 标记 docling/PyMuPDF 来源
        if manifest.get("algorithm_version") == "v8.5_light_step2":
            md_parts.append("    (v8.5 PyMuPDF 轻量级搜索, 未做 docling 表格结构识别)")
        elif manifest.get("algorithm_version") == "v4.0":
            md_parts.append("    (docling 表格 + 文本 深度应证)")
    elif scan.get("main_pdf"):
        # 没 found_locs (没 docling/PyMuPDF): 跑临时 PyMuPDF 搜索 (light step2)
        main_pdf_path = f"{lit_base}/{pn_x}/{scan['main_pdf']}"
        if not _os.path.isfile(main_pdf_path):
            main_pdf_path = f"{scan.get('src_base', '/Users/david/Desktop/雷管方案_文献整理')}/{pn_x}/{scan['main_pdf']}"
        
        light_hits = []
        if _os.path.isfile(main_pdf_path):
            try:
                import fitz as _fitz
                doc = _fitz.open(main_pdf_path)
                search_terms = manifest.get("ppt_data_points", [])
                if not search_terms and info_c.get("data_alignment"):
                    import re as _re_lite
                    for da in info_c["data_alignment"][:5]:
                        for num_m in _re_lite.finditer(r"\b(\d+(?:\.\d+)?)\s*%?", da):
                            v = num_m.group(1)
                            if len(v) >= 2 and v not in search_terms:
                                search_terms.append(v)
                
                for term in search_terms[:5]:
                    for p_idx, page in enumerate(doc):
                        if p_idx >= 5:
                            break
                        text = page.get_text()[:3000]
                        if term in text:
                            idx = text.find(term)
                            ctx = text[max(0, idx-30):idx+60].replace("\n", " ")
                            light_hits.append((term, p_idx+1, ctx))
                            break
                doc.close()
            except Exception:
                pass
        
        if light_hits:
            for dp, page, ctx in light_hits[:4]:
                md_parts.append(f"    ✓ '{dp}' → page {page}: {ctx}...")
            md_parts.append("    (轻量级 PyMuPDF 搜索, 未做 docling 语义级应证, 待升级)")
        else:
            md_parts.append("    (未做 PPT视觉 vs PDF高亮 应证, 待 docling 解析)")

    # ⑤ 推理结果 — v8.5 严格基于 PPT视觉 vs PDF高亮双向对齐的 step2_score
    md_parts.append("  ⑤ 推理结果:")
    
    if main_score is None:
        md_parts.append("    ⚠️ 未做 PPT视觉 vs PDF高亮 双向对齐, 待运行 docling / 轻量级搜索应证")
        if scan.get("main_pdf"):
            md_parts.append(f"    📁 main PDF 文件: {scan['main_pdf']} ({scan.get('main_pdf_size_kb', 0)}KB)")
            md_parts.append(f"    💡 文件存在, 待 PPT视觉识别 + PDF docling/PyMuPDF 应证")
    elif main_score >= 1.0:
        md_parts.append("    ✅ main 完整应证 PPT 视觉识别的全部信息要素 (⭐满分, 双向对齐)")
    elif main_score >= 0.85:
        md_parts.append("    ✅ main 高度应证 PPT 视觉识别的多数信息要素")
    elif main_score >= 0.7:
        md_parts.append("    ⚠️ main 部分应证 PPT 视觉识别的信息要素")
    elif main_score >= 0.4:
        md_parts.append("    ⚠️ main 应证不足, 需 fallback 补强")
    else:
        md_parts.append("    ❌ main 应证失败, fallback 是必需")

    # 保留 visual_alignment / semantic_reasoning 作为补充
    if info_c.get("semantic_reasoning"):
        md_parts.append("")
        md_parts.append("  [补充参考] 视觉/语义推理原始记录:")
        for sr in info_c["semantic_reasoning"][:2]:
            md_parts.append(f"    - {sr[:100]}")

    md_parts.append("")
    
    # 【📎 下载链接】
    if doi and not doi.startswith("备注"):
        md_parts.append("【📎 下载链接】 (互联网, 可点击)")
        md_parts.append(f"  - PubMed 搜索: [{doi}](https://pubmed.ncbi.nlm.nih.gov/?term={doi})")
        md_parts.append(f"  - Europe PMC 搜索: [{doi}](https://europepmc.org/search?query={doi})")
        md_parts.append("")
    elif doi.startswith("备注") or pn == "1":  # 政府文件/无 DOI
        md_parts.append("【📎 原始链接】 (政府文件, 官方存档)")
        md_parts.append(f"  - NHC 官网: [国家卫生健康委员会](http://www.nhc.gov.cn)")
        md_parts.append(f"  - 中国实用外科杂志: [zsjwkzz.cn](https://www.zgsjwkzz.cn)")
        md_parts.append("")
    
    md_parts.append(f"【🏷️ 类型】 {type_emoji}")
    
    return "\n".join(md_parts)


def get_publisher_pdf_urls(doi: str, journal: str = "", verified_url: str = None, verified_code: str = None) -> list:
    """
    v9.0: 优先使用 verified REAL URL (从 DOI 重定向链跟踪得到), 保底用 DOI 主链接
    
    验证方法:
    - 跟踪 https://doi.org/{doi} 的重定向链, 拿到最终 URL
    - 例如: 10.1016/j.jhep.2025.03.033 → https://linkinghub.elsevier.com/retrieve/pii/S0168827825002260
    - 这个 URL 是真实可访问的 (scienceDirect 真实 PII 路径)
    - 不再猜测 URL 格式 (ScienceDirect /article/doi/ 可能 404)
    
    Returns:
        [(label, url), ...]
    """
    urls = []
    if not doi or doi.startswith("备注"):
        return urls
    
    # 第一优先: 验证过的真实出版商 URL (从 DOI 重定向跟踪得到)
    # 这是每个 PDF 文件对应的真实在线地址
    if verified_url:
        # 从 URL 推断出版商标签
        publisher_label = _infer_publisher_label(verified_url)
        urls.append((f"{publisher_label} 全文", verified_url))
    
    # 第二优先: DOI 主链接 (通用解析器, 永远有效)
    urls.append(("DOI 主链接", f"https://doi.org/{doi}"))
    
    # 通用数据库搜索
    urls.append(("PubMed 搜索", f"https://pubmed.ncbi.nlm.nih.gov/?term={doi}"))
    urls.append(("Europe PMC 搜索", f"https://europepmc.org/search?query={doi}"))
    
    return urls


def _infer_publisher_label(url: str) -> str:
    """
    从 URL 推断出版商名称
    """
    url_l = url.lower()
    if 'linkinghub.elsevier.com' in url_l or 'sciencedirect.com' in url_l:
        return "ScienceDirect"
    elif 'nejm.org' in url_l or 'evidence.nejm.org' in url_l:
        return "NEJM"
    elif 'thelancet.com' in url_l or 'lancet.com' in url_l:
        return "The Lancet"
    elif 'jamanetwork.com' in url_l:
        return "JAMA Network"
    elif 'ascopubs.org' in url_l or 'asco.org' in url_l:
        return "ASCO"
    elif 'aacrjournals.org' in url_l:
        return "AACR"
    elif 'nature.com' in url_l:
        return "Nature"
    elif 'wiley.com' in url_l or 'onlinelibrary.wiley.com' in url_l:
        return "Wiley"
    elif 'springer.com' in url_l or 'biomedcentral.com' in url_l or 'bmc' in url_l:
        return "BMC/Springer"
    elif 'plos.org' in url_l:
        return "PLOS"
    elif 'oup.com' in url_l or 'academic.oup.com' in url_l:
        return "Oxford"
    elif 'frontiersin.org' in url_l:
        return "Frontiers"
    elif 'sagepub.com' in url_l:
        return "SAGE"
    elif 'oncotarget.com' in url_l:
        return "Oncotarget"
    elif 'lww.com' in url_l or 'wolterskluwer' in url_l:
        return "LWW"
    elif 'mdpi.com' in url_l:
        return "MDPI"
    elif 'bmj.com' in url_l:
        return "BMJ"
    elif 'karger.com' in url_l or 'karger' in url_l:
        return "Karger"
    elif 'tandfonline.com' in url_l:
        return "Taylor & Francis"
    elif 'acs.org' in url_l or 'pubs.acs.org' in url_l:
        return "ACS"
    elif 'annualreviews.org' in url_l:
        return "Annual Reviews"
    elif 'pubmed.ncbi.nlm.nih.gov' in url_l:
        return "PubMed"
    elif 'europepmc.org' in url_l:
        return "Europe PMC"
    else:
        return "出版商"


# ════════════════════════════════════════════════════════════════════
# markdown → 飞书 rich_text
# ════════════════════════════════════════════════════════════════════

def markdown_to_rich_text(md: str) -> List[Dict]:
    """
    把 markdown 文本转换成飞书 rich_text 数组 (v3)
    
    特性:
    - 同时检测 [text](url) 和裸 https://... URL
    - 保留换行符 \n (飞书渲染时自动换行)
    - 相邻 text 段自动合并
    
    根因: 之前 H 列写入多段文本 (每行一段), 飞书内联渲染无换行。
    """
    rt: List[Dict] = []
    if not md:
        return rt
    
    # 找所有链接
    all_links = []
    # 找 [text](url) 链接, 用手写 parser 处理嵌套括号 (URL 含 (25) 等)
    i = 0
    while i < len(md):
        if md[i] == '[':
            j = i + 1
            depth = 0
            while j < len(md):
                if md[j] == '[':
                    depth += 1
                elif md[j] == ']':
                    if depth == 0:
                        break
                    depth -= 1
                j += 1
            if j >= len(md):
                i += 1
                continue
            text_part = md[i+1:j]
            k = j + 1
            if k < len(md) and md[k] == '(':
                m_end = k + 1
                depth = 1
                while m_end < len(md):
                    if md[m_end] == '(':
                        depth += 1
                    elif md[m_end] == ')':
                        depth -= 1
                        if depth == 0:
                            break
                    m_end += 1
                if m_end < len(md):
                    url_part = md[k+1:m_end]
                    all_links.append((i, m_end+1, text_part, url_part))
                    i = m_end + 1
                    continue
        i += 1
    for m in re.finditer(r"https?://[^\s`\n\)>]+", md):
        already = False
        for s, e, _, _ in all_links:
            if s <= m.start() and m.end() <= e:
                already = True
                break
        if not already:
            all_links.append((m.start(), m.end(), m.group(), m.group()))
    all_links.sort(key=lambda x: x[0])
    
    parts = []
    last = 0
    for s, e, text, url in all_links:
        if s > last:
            parts.append(("text", md[last:s]))
        parts.append(("link", text, url))
        last = e
    if last < len(md):
        parts.append(("text", md[last:]))
    
    if not parts:
        rt.append({"type": "text", "text": md})
        return rt
    
    # 合并相邻 text
    merged = []
    for p in parts:
        if p[0] == "text":
            if merged and merged[-1][0] == "text":
                merged[-1] = ("text", merged[-1][1] + p[1])
            else:
                merged.append(p)
        else:
            merged.append(p)
    
    for p in merged:
        if p[0] == "text":
            rt.append({"type": "text", "text": p[1]})
        else:
            rt.append({"type": "link", "text": p[1], "link": p[2]})
    
    return rt


# ════════════════════════════════════════════════════════════════════
# 一站式: 从 CSV D 列 + 飞书 C 列生成 H 列 rich_text
# ════════════════════════════════════════════════════════════════════

def build_h_rich_text(pn: str, d_field: str, c_field: str, g_path: str, doi: str) -> List[Dict]:
    """
    从 D + C + G 列数据, 生成完整 H 列 rich_text
    
    Args:
        pn: Pn-x 标号 (如 "2")
        d_field: CSV D 列原文
        c_field: 飞书 C 列原文
        g_path: CSV G 列路径 (如 "P5-2/P5-2_main_xxx.pdf")
        doi: CSV E 列 DOI
    
    Returns:
        飞书 rich_text 数组 (List[Dict])
    """
    info_d = parse_d_field(d_field)
    info_c = parse_c_field(c_field)
    h_md = build_h_md(pn, info_d, info_c, g_path, doi)
    return markdown_to_rich_text(h_md)


if __name__ == "__main__":
    import sys
    import csv
    
    csv_path = "/Users/david/Desktop/雷管方案_文献整理/_citation_table/citation_table.csv"
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # 测试: 从 CSV 读 P5 第 2 行, 生成 rich_text
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            cols = reader.fieldnames
            for r in reader:
                if r[cols[0]] == "5" and r[cols[1]] == "2":
                    d = r[cols[3]]
                    g = r[cols[6]]
                    doi = r[cols[4]]
                    rt = build_h_rich_text("2", d, "PPT 标号2: 化疗方案 FOLFOX", g, doi)
                    print(f"\n=== P5-2 rich_text ({len(rt)} segments) ===")
                    for i, item in enumerate(rt):
                        t = item.get("type")
                        text = str(item.get("text", ""))[:60].replace(chr(10), "\\n")
                        link = item.get("link", "")
                        print(f"  [{i}] {t}: {text} {('-> ' + link[:40]) if link else ''}")
                    break



# ════════════════════════════════════════════════════════════════════
# v6: 扫描 Pn-x 目录, 真实文件清单 (与 highlight 目录一致)
# ════════════════════════════════════════════════════════════════════

def scan_pn_x_dir(pn_x: str, lit_base: str = "/Users/david/Desktop/雷管方案_文献整理/_literature_citation_index", src_base: str = "/Users/david/Desktop/雷管方案_文献整理") -> Dict:
    """
    扫描 Pn-x 目录 + manifest.fallback_pdfs, 返回 main / fb / supp 三类文件 + manifest

    v8.2 升级: 同时扫描主目录 (src_base), 如果 lit_base 缺 _fallback_/_supp_ 文件, 自动同步.
    主目录是真理源, _literature_citation_index/ 是工作副本.
    
    Args:
        pn_x: Pn-x 标识 (如 "P5-2")
        lit_base: 文献标注根目录
    
    Returns:
        {
            "pn_x": "P5-2",
            "main": ["P5-2_main_xxx.pdf"],
            "fb": ["P5-2_fb_xxx.pdf"],
            "supp": ["P5-2_supp_xxx.pdf"],
            "fb_cross_refs": [...],  # 跨 Pn-x 引用 (manifest.fallback_pdfs 提取)
            "fb_info": {filename: {应证内容, score, exists}},
            "sizes": {filename: int (bytes)},
            "manifest": {...},
            "highlight_summary": {...},
            "fallback_triggered": bool,
            "fallback_reason": str,
        }
    """
    import os as _os
    import re as _re
    p = f"{lit_base}/{pn_x}"
    if not _os.path.isdir(p):
        return {"pn_x": pn_x, "main": [], "fb": [], "supp": [], "fb_cross_refs": [], "fb_info": {}, "sizes": {}, "manifest": {}, "highlight_summary": {}, "fallback_triggered": False, "fallback_reason": ""}
    
    # v8.2: 自动同步主目录到 lit_base (缺失 fb / supp 自动复制)
    src_p = f"{src_base}/{pn_x}"
    if _os.path.isdir(src_p) and _os.path.isdir(p):
        # 扫描主目录
        src_pdfs = sorted([f for f in _os.listdir(src_p) if f.endswith('.pdf')])
        for f in src_pdfs:
            dst_path = f"{p}/{f}"
            src_path = f"{src_p}/{f}"
            # 只复制 fb / supp (main 不复制, 避免覆盖主目录的变更)
            if not _os.path.isfile(dst_path) and ('_fallback_' in f or '_fb_' in f or '_supp_' in f):
                try:
                    import shutil as _shutil
                    _shutil.copy2(src_path, dst_path)
                except Exception:
                    pass
        # 同步 manifest 的 fallback_pdfs
        if _os.path.isfile(f"{src_p}/_manifest.json"):
            try:
                import json as _json2
                with open(f"{src_p}/_manifest.json") as _smf:
                    src_m = _json2.load(_smf)
                src_fb = src_m.get("fallback_pdfs", [])
                if src_fb:
                    mp_local = f"{p}/_manifest.json"
                    local_m = {}
                    if _os.path.isfile(mp_local):
                        with open(mp_local) as _lmf:
                            local_m = _json2.load(_lmf)
                    # 合并 fallback_pdfs (去重)
                    existing = local_m.get("fallback_pdfs", [])
                    for entry in src_fb:
                        if entry not in existing:
                            existing.append(entry)
                    local_m["fallback_pdfs"] = existing
                    if _os.path.isfile(mp_local):
                        with open(mp_local, 'w') as _lmf:
                            _json2.dump(local_m, _lmf, ensure_ascii=False, indent=2)
            except Exception:
                pass

    pdfs = sorted([f for f in _os.listdir(p) if f.endswith('.pdf')])
    main = [f for f in pdfs if '_main_' in f]
    fb = [f for f in pdfs if '_fallback_' in f or '_fb_' in f]
    supp = [f for f in pdfs if '_supp_' in f]
    sizes = {f: _os.path.getsize(f"{p}/{f}") for f in pdfs}
    
    manifest = {}
    manifest_path = f"{p}/_manifest.json"
    if _os.path.isfile(manifest_path):
        import json as _json
        with open(manifest_path) as _f:
            manifest = _json.load(_f)
    
    hl_summary = manifest.get("highlight_summary", {})
    if isinstance(hl_summary, list) and hl_summary:
        # 多张高亮图时, 取最大 hits/terms
        best = max(hl_summary, key=lambda x: x.get("hits", 0))
        hl_summary = best
    
    # 解析 manifest.fallback_pdfs (可能含跨 Pn-x 引用)
    # 格式: ['P4-3/P4-3_main_Gao_Gastro_2017.pdf (应证 PPT 异质性概念)', ...]
    fb_cross_refs = []
    fb_info = {}  # 本目录 fb 文件的元信息 (从 manifest 提取)
    fb_pdfs_raw = manifest.get("fallback_pdfs", [])
    
    for entry in fb_pdfs_raw:
        # 提取路径和应证内容
        m = _re.match(r'\s*(\S+?\.pdf)\s*(?:\(([^)]+)\))?', entry)
        if not m:
            continue
        pdf_rel = m.group(1)
        应证_text = m.group(2) or ""
        
        # 路径可能是 Pn-x/file.pdf (跨标号) 或 file.pdf (本目录)
        if "/" in pdf_rel:
            # 跨标号引用
            target_pn_x = pdf_rel.split("/")[0]
            target_file = pdf_rel.split("/")[-1]
            target_path = f"{lit_base}/{target_pn_x}/{target_file}"
            
            # 检查是否在跨标号目录下也存在于 _literature_citation_index
            exists_in_lit = _os.path.isfile(target_path)
            # 也可能在 src_base
            src_target = f"/Users/david/Desktop/雷管方案_文献整理/{pdf_rel}"
            exists_in_src = _os.path.isfile(src_target)
            
            # 从目标 Pn-x 的 manifest 取 step2_score
            target_score = 0.0
            target_mp = f"{lit_base}/{target_pn_x}/_manifest.json"
            if _os.path.isfile(target_mp):
                with open(target_mp) as tf:
                    target_manifest = _json.load(tf)
                target_score = target_manifest.get("step2_score", 0.0)
            
            # 计算目标文件名 (去路径)
            target_basename = pdf_rel.split("/")[-1] if "/" in pdf_rel else pdf_rel
            # 应证内容: fallback_trigger_reason 里有更多信息
            fb_info_text = 应证_text or manifest.get("fallback_trigger_reason", "")[:100]
            
            if target_pn_x != pn_x:
                # 跨标号引用
                fb_cross_refs.append({
                    "path": pdf_rel,
                    "应证": fb_info_text,
                    "target_pn_x": target_pn_x,
                    "target_file": target_basename,
                    "exists_in_lit": exists_in_lit,
                    "exists_in_src": exists_in_src,
                    "score": target_score,
                })
            else:
                # 同标号, 检查是否在本目录 fb_local (扫到的文件名)
                if target_basename in fb:
                    fb_info[target_basename] = {
                        "应证": fb_info_text,
                        "score": manifest.get("step2_score", 0.0),
                        "path": target_basename,
                    }
        else:
            # 本目录 fb 文件
            local_path = f"{p}/{pdf_rel}"
            if _os.path.isfile(local_path):
                fb_info[pdf_rel] = {
                    "应证": 应证_text,
                    "score": manifest.get("step2_score", 0.0),
                    "path": pdf_rel,
                }
    
    # 合并: fb + fb_cross_refs 都视为 fallback
    # 但 fb (本目录) 优先, fb_cross_refs 补充
    all_fb = list(fb)
    seen = set(fb)
    for cross in fb_cross_refs:
        if cross["target_file"] not in seen:
            all_fb.append(cross["target_file"])
            seen.add(cross["target_file"])
    
    # 计算 main_pdf / main_score (统一接口)
    main_pdf = main[0] if main else None
    main_score = manifest.get("step2_score")

    return {
        "pn_x": pn_x,
        "main": main,
        "main_pdf": main_pdf,
        "main_pdf_path": f"{p}/{main_pdf}" if main_pdf else None,
        "main_pdf_size_kb": (sizes.get(main_pdf, 0) // 1024) if main_pdf else 0,
        "main_score": main_score,
        "fb": all_fb,  # 本目录 + 跨标号引用合并
        "fb_local": fb,  # 仅本目录
        "fb_cross_refs": fb_cross_refs,  # 跨标号引用详情
        "fb_info": fb_info,  # 本目录 fb 元信息
        "supp": supp,
        "sizes": sizes,
        "manifest": manifest,
        "highlight_summary": hl_summary,
        "fallback_triggered": manifest.get("fallback_triggered", False),
        "fallback_reason": manifest.get("fallback_trigger_reason", ""),
    }



def run_light_step2(pn_x: str, lit_base: str, ppt_data_points: list) -> Dict:
    """
    v8.5: 轻量级 step2 应证 — 对 slide 6+ Pn-x (没 docling 应证数据) 跑 PyMuPDF 搜索,
    写入 manifest: ppt_data_points / found_data_points / found_data_point_locations / step2_score

    原则: 不依赖 D 列, 只从 PPT 视觉识别 (ppt_data_points) + PDF 实际搜索

    Args:
        pn_x: Pn-x 标识 (如 "P11-1")
        lit_base: 文献标注根目录
        ppt_data_points: 从 PPT 视觉提取的数据点 (如 ['301', '15.9', '2023', '12', '12%', ...])

    Returns:
        {
            "ppt_data_points": [...],
            "found_data_points": [...],
            "found_data_point_locations": {dp: [{page_no, text_snippet}, ...]},
            "step2_score": float (found/total, e.g. 0.75),
            "step2_found": int,
            "step2_total": int,
        }
    """
    import os as _os_lite
    import re as _re_lite
    result = {
        "ppt_data_points": ppt_data_points,
        "found_data_points": [],
        "found_data_point_locations": {},
        "step2_score": 0.0,
        "step2_found": 0,
        "step2_total": len(ppt_data_points),
    }

    if not ppt_data_points:
        return result

    # 找 main PDF 路径
    p = f"{lit_base}/{pn_x}"
    if not _os_lite.path.isdir(p):
        return result

    main_pdfs = [f for f in _os_lite.listdir(p) if '_main_' in f and f.endswith('.pdf')]
    if not main_pdfs:
        return result

    main_pdf_path = f"{p}/{main_pdfs[0]}"

    try:
        import fitz as _fitz_lite
        doc = _fitz_lite.open(main_pdf_path)

        # 数值等价: 14.4 == 14.40 == 14.4%
        def gen_variants(dp):
            variants = [dp]
            if dp.endswith('%'):
                variants.append(dp[:-1])  # 14.4% → 14.4
            elif dp.replace('.', '').replace('-', '').isdigit():
                variants.append(dp + '%')  # 14.4 → 14.4%
            return variants

        # 搜索每个 ppt_data_point
        for dp in ppt_data_points:
            variants = gen_variants(dp)
            hit_pages = []
            for variant in variants:
                for p_idx in range(min(8, len(doc))):  # 搜前 8 页
                    text = doc[p_idx].get_text()
                    if variant in text:
                        idx = text.find(variant)
                        ctx = text[max(0, idx-30):idx+80].replace("\n", " ")
                        hit_pages.append({"page_no": p_idx+1, "text_snippet": ctx[:120]})
                        break
                if hit_pages:
                    break
            if hit_pages:
                result["found_data_points"].append(dp)
                result["found_data_point_locations"][dp] = hit_pages

        doc.close()

        # 计算 step2_score
        result["step2_found"] = len(result["found_data_points"])
        if result["step2_total"] > 0:
            result["step2_score"] = min(1.0, result["step2_found"] / result["step2_total"])

        # 写 manifest
        mp = f"{p}/_manifest.json"
        if _os_lite.path.isfile(mp):
            import json as _json_lite
            with open(mp) as _mf:
                m = _json_lite.load(_mf)
        else:
            m = {}

        m["ppt_data_points"] = ppt_data_points
        m["found_data_points"] = result["found_data_points"]
        m["found_data_point_locations"] = result["found_data_point_locations"]
        m["step2_score"] = result["step2_score"]
        m["step2_found"] = result["step2_found"]
        m["step2_total"] = result["step2_total"]
        m["algorithm_version"] = "v8.5_light_step2"

        with open(mp, 'w') as _mf:
            _json_lite.dump(m, _mf, ensure_ascii=False, indent=2)

    except Exception as _e:
        pass

    return result


def extract_ppt_data_points_from_c(c_raw: str) -> List[str]:
    """
    v8.5: 从 C 列 (PPT 视觉识别) 提取 ppt_data_points
    不依赖 D 列. 提取数字 + 医学术语 + 关键文字
    """
    import re as _re
    pts = []
    if not c_raw:
        return pts

    # 1. 数字 (≥2 位) - 含百分比/小数
    for m in _re.finditer(r"\b(\d+(?:\.\d+)?)\s*%?", c_raw):
        v = m.group(1)
        if len(v) >= 2 and v not in pts:
            pts.append(v)

    # 2. 医学术语
    medical_kws = [
        "STRIDE", "T+A", "O+Y", "Len", "Lenvatinib", "Pembro", "NIVO", "IPI",
        "Durvalumab", "Tremelimumab", "Atezolizumab", "Bevacizumab", "Sorafenib",
        "Regorafenib", "Cabozantinib", "Ramucirumab", "Sintilimab", "Toripalimab",
        "Camrelizumab", "Tislelizumab", "Penpulimab", "Cadonilimab", "AK104",
        "Donafenib", "Envafolimab", "Anlotinib", "Apatinib", "Lenvatinib",
        "FOLFOX4", "GEMOX", "HAIC", "TACE", "RFA", "PEI",
    ]
    for kw in medical_kws:
        if kw in c_raw and kw not in pts:
            pts.append(kw)

    # 3. 研究名 (大写 + 数字)
    for m in _re.finditer(r"\b([A-Z][A-Z\-]+(?:\d+)?)\b", c_raw):
        study = m.group(1)
        if len(study) >= 3 and study not in pts:
            pts.append(study)

    return pts[:15]  # 限制 15 项


def detect_main_pdf_content_mismatch(pn_x: str, info_d: Dict, scan: Dict, d_raw: Optional[str] = None) -> Optional[Dict]:
    """
    v9.5: 检测 main PDF 实际内容是否与 D 列文献匹配 (基于 page 1 文本内容)

    比 detect_main_pdf_mismatch 更严格: 不仅检查文件名, 还检查 PDF 内容.

    v9.5 简化: 只检测"明显错位" (如 main 是 study protocol 但 D 列是论文)
    """
    if not scan.get("main"):
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


def detect_main_pdf_mismatch(pn_x: str, info_d: Dict, scan: Dict, d_raw: Optional[str] = None) -> Optional[Dict]:
    """
    v9.5: 检测 main PDF 是否与 D 列文献匹配

    d_raw: CSV 原始 D 列字符串 (用于直接提取关键词, 当 parse_d_field 失败时)

    Returns:
        None - 匹配
        Dict {mismatch_type, expected, actual, note} - 错位
    """
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


def calculate_main_score(scan: Dict) -> Optional[float]:
    """
    计算 main PDF 应证 PPT 内容的评分 (None / 0.00-1.00)
    
    Returns:
        score ∈ [0.00, 1.00], 或 None (表示未运行 docling, 用 CSV 元数据默认 1.00)
    """
    if not scan["main"]:
        return 0.0

    # 1) 优先用 P5 Step 2 的真实评分 (docling 搜 PPT 数据点)
    if scan.get("manifest", {}).get("step2_score") is not None:
        return float(scan["manifest"]["step2_score"])

    # 2) 其次用 highlight_summary hits/terms (cap 1.0)
    hl = scan.get("highlight_summary", {})
    if hl and hl.get("terms"):
        raw = hl.get("hits", 0) / max(hl.get("terms", 1), 1)
        return round(min(raw, 1.0), 2)

    # 3) fallback_triggered 时 main 不足
    if scan["fallback_triggered"]:
        return 0.4

    # 4) 默认 None (slide 6+: 未运行 docling, 用 D 列元数据默认 1.00)
    return None



def _infer_fallback_search_link(fb_filename: str):
    """
    v8.7: 从 fallback 文件名推断期刊/会议, 返回搜索链接
    
    文件名格式:
    - Pn-x_fallback_{Author}_{Journal}_{Year}_{title}.pdf
    - 例如: P15-1_fallback_Yau_Lancet_2025_CheckMate9DW_PLS.pdf
    
    Returns:
        None 或 (url, label)
    """
    # 期刊关键词映射 (期刊名 → 搜索 URL)
    journal_search = {
        "Lancet": ("https://pubmed.ncbi.nlm.nih.gov/?term=CheckMate-9DW+NIVO+IPI+hepatocellular+2025", "[PubMed 搜索 CheckMate-9DW]"),
        "NEJM": ("https://pubmed.ncbi.nlm.nih.gov/?term=IMbrave150+durvalumab+tremelimumab", "[PubMed 搜索 IMbrave150]"),
        "JCO": ("https://pubmed.ncbi.nlm.nih.gov/?term=CheckMate-9DW+IPI+NIVO", "[PubMed 搜索 CheckMate-9DW]"),
        "JClinOncol": ("https://pubmed.ncbi.nlm.nih.gov/?term=CheckMate-9DW+IPI+NIVO", "[PubMed 搜索 CheckMate-9DW]"),
        "AnnOncol": ("https://pubmed.ncbi.nlm.nih.gov/?term=HIMALAYA+atezolizumab+bevacizumab", "[PubMed 搜索 HIMALAYA]"),
        "FrontOncol": ("https://pubmed.ncbi.nlm.nih.gov/?term=sintilimab+camrelizumab+hepatocellular", "[PubMed 搜索 FrontOncol]"),
        "JAMAOncol": ("https://pubmed.ncbi.nlm.nih.gov/?term=RATIONALE-301+sintilimab", "[PubMed 搜索 RATIONALE-301]"),
        "LiverInt": ("https://pubmed.ncbi.nlm.nih.gov/?term=BRIDGE+lenvatinib+hepatocellular", "[PubMed 搜索 BRIDGE]"),
        "Gastroenterology": ("https://pubmed.ncbi.nlm.nih.gov/?term=molecular+class+hepatocellular", "[PubMed 搜索]"),
        "JHepatol": ("https://pubmed.ncbi.nlm.nih.gov/?term=HIMALAYA+5+year+survival+hepatocellular", "[PubMed 搜索 HIMALAYA 5yr]"),
    }
    
    # 会议关键词
    conf_search = {
        "ASCO": ("https://www.asco.org", "[ASCO 官网]"),
        "ASCOGI": ("https://www.asco.org", "[ASCO-GI 官网]"),
        "ASCO-GI": ("https://www.asco.org", "[ASCO-GI 官网]"),
        "ESMO": ("https://www.esmo.org/meetings", "[ESMO 会议]"),
        "APASL": ("https://www.apasl.org", "[APASL 会议]"),
        "CSCO": ("https://www.csco.ac.cn", "[CSCO 会议]"),
        "EASL": ("https://www.easl.eu", "[EASL 会议]"),
        "AASLD": ("https://www.aasld.org", "[AASLD 会议]"),
    }
    
    # 匹配期刊
    for keyword, (url, label) in journal_search.items():
        if keyword.lower() in fb_filename.lower():
            return (url, label)
    
    # 匹配会议
    for keyword, (url, label) in conf_search.items():
        if keyword.lower() in fb_filename.lower():
            return (url, label)
    
    return None




def _infer_main_pdf_link(main_pdf: str, info_d: Dict):
    """
    v8.8: 从 main PDF 文件名推断后续正式发表的 DOI + 期刊
    
    当用户标的是会议摘要 (DOI 是 ASCO LBA4008), 但 main PDF 是后续正式发表
    (Lancet 2025 / JCO 2025 等), 这个函数推断 main PDF 的 DOI.
    
    Returns:
        None 或 (doi, journal_name)
    """
    # 已知映射 (基于 lit_base 实际文件命名模式)
    # 后续正式发表 DOI 是已知的, 直接映射
    known_map = {
        # Galle CheckMate-9DW 后续正式发表
        "Galle_CheckMate9DW_Lancet_2025": ("10.1016/S0140-6736(25)00001-1", "Lancet"),
        "Yau_Lancet_2025": ("10.1016/S0140-6736(25)00403-9", "Lancet"),
        # Finn IMbrave150 后续正式发表
        "Finn_NEJM2020_IMbrave150": ("10.1056/NEJMoa1915745", "NEJM"),
        "Finn_Journal_2020": ("10.1056/NEJMoa1915745", "NEJM"),
        # Sangro STRIDE 后续正式发表 (ESMO 摘要 → NEJM Evid)
        "Abou-Alfa_NEJM_2022": ("10.1056/EVIDoa2100070", "NEJM Evidence"),
        # Rimassa HIMALAYA 后续正式发表
        "Rimassa_JHepatol_2025_HIMALAYA": ("10.1016/j.jhep.2025.05.001", "J Hepatol"),
        # Lau HIMALAYA Asian subgroup
        "Lau_JHepatol_2025": ("10.1016/j.jhep.2024.07.017", "J Hepatol"),
        # Qin RATIONALE-301 后续正式发表
        "Qin_JAMAOncol_2023": ("10.1001/jamaoncol.2023.4003", "JAMA Oncol"),
        # Cheng IMbrave150
        "Cheng_JHepatol_2022": ("10.1016/j.jhep.2021.11.030", "J Hepatol"),
    }
    
    for key, (doi, journal) in known_map.items():
        if key in main_pdf:
            return (doi, journal)
    
    # 默认: 从 main_pdf 文件名猜 DOI
    # 期刊关键词 → DOI 前缀
    doi_prefixes = {
        "Lancet": "10.1016/S0140-6736",
        "NEJM": "10.1056/NEJMoa",
        "JAMA": "10.1001/jama",
        "JCO": "10.1200/JCO",
        "JHepatol": "10.1016/j.jhep",
        "AnnOncol": "10.1016/j.annonc",
        "FrontOncol": "10.3389/fonc",
        "Gastro": "10.1053/j.gastro",
        "NatCommun": "10.1038/s41467",
        "NatRev": "10.1038/n",
        "BJC": "10.1038/s41416",
    }
    
    for journal, prefix in doi_prefixes.items():
        if journal.lower() in main_pdf.lower():
            # 没法推断具体后缀, 返回 None
            return (None, journal)
    
    return None


def calculate_fallback_score(scan: Dict, fb_filename: str) -> float:
    """
    计算 fallback PDF 应证 PPT 内容的评分
    
    优先级:
    1. 跨标号引用的 target_score (从目标 Pn-x manifest 提取, 比较准)
    2. 基于 fb_filename 推断 (Bray → 0.85, NEJM → 0.70, Appendix → 0.50 等)
    3. fallback_triggered 时 0.60
    
    Returns:
        score ∈ [0.00, 1.00]
    """
    # 优先级 1: 跨标号引用
    for cross in scan.get("fb_cross_refs", []):
        if cross.get("target_file") == fb_filename:
            s = cross.get("score", 0)
            if s > 0:
                return s
    
    fb_lower = fb_filename.lower()
    
    # ICMJE 披露: 通常是补充材料, 不应证主论点
    if 'icmje' in fb_lower or 'disclosure' in fb_lower:
        return 0.30
    
    # 综述/标准评论 (standard review / review)
    if 'review' in fb_lower or 'standard' in fb_lower:
        return 0.65
    
    # Appendix 补充材料
    if 'appendix' in fb_lower:
        return 0.50
    
    # 政府文件 / 卫健委令汇编 / 法规 (永久)
    if any(kw in fb_lower for kw in ['卫健委', '政府', '令汇编', 'nhc', 'gov', 'regulation']):
        return 0.75
    
    # Bray/2024 GLOBOCAN 论文 (Ca-Cancer J Clin) - 高分
    if 'bray' in fb_lower or 'caac' in fb_lower:
        return 0.85
    
    # GLOBOCAN 2024 China fact sheet - 中等分
    if 'globocan' in fb_lower or '2024' in fb_lower and 'china' in fb_lower:
        return 0.65
    
    # ASCO 摘要/会议摘要 (abstract)
    if 'abstract' in fb_lower or 'asco' in fb_lower or 'esmo' in fb_lower:
        return 0.55
    
    # NEJM 全文 / 同期发表
    if 'nejm' in fb_lower or 'lancet' in fb_lower:
        return 0.70
    
    # fallback_triggered 时说明 fb 应证的是 main 漏掉的内容
    if scan.get("fallback_triggered"):
        return 0.60
    
    return 0.50


# ════════════════════════════════════════════════════════════════════
# v6: 链接时效性识别
# ════════════════════════════════════════════════════════════════════

def identify_link_eternality(doi: str, journal: str, info_d: Dict) -> Dict:
    """
    识别下载链接的时效性
    
    Returns:
        {
            "eternity": "permanent" | "timed" | "temporary",
            "label": "永久有效" / "GLOBOCAN 2022→2024 时效差异" / "会议摘要 (1-2 年)",
            "expiry_note": "失效后...",
            "backup_url": "[备用 URL]"
        }
    """
    journal_l = journal.lower()
    info_d_type = info_d.get("type", "")
    
    # 1. IARC GLOBOCAN: 时效差异 (2022 数据已下线, 只显示 2024)
    if 'globocan' in journal_l or 'global cancer observatory' in journal_l or (doi and 'caac' in doi.lower()):
        return {
            "eternity": "timed",
            "label": "⚠️ 时效差异: GLOBOCAN 2022 → 2024",
            "expiry_note": "PPT 引 2022 数据 (36.8万 / 42.5%), 但 IARC gco.iarc.who.int 只显示 2024 在线版 (35.4万 / 42.7%)",
            "backup_url": "https://web.archive.org/web/2024*/https://gco.iarc.fr/today/data/factsheets/cancers/11-Liver-fact-sheet.pdf",
        }
    
    # 2. 会议摘要 (ESMO/ASCO/APASL/CSCO/EASL/AASLD): 临时 (v8.7 会议名动态选择备份 URL)
    if info_d_type == "conference_abstract" or 'asco' in journal_l or 'esmo' in journal_l or 'annonc' in journal_l and '1494P' in (doi or ''):
        conference_name = info_d.get("conference_name", "")
        conf_year = info_d.get("conference_year", "2024")
        conf_backup_urls = {
            "APASL": f"https://www.apasl.org",
            "ASCO": "https://www.asco.org/abstracts",
            "ASCO-GI": "https://www.giconsortium.org",
            "ASCO-Gl": "https://www.giconsortium.org",
            "ESMO": f"https://www.esmo.org/meetings/esmo-{conf_year}",
            "CSCO": f"https://www.csco.ac.cn",
            "EASL": "https://www.easl.eu",
            "AASLD": "https://www.aasld.org",
        }
        backup_url = conf_backup_urls.get(conference_name, f"https://www.esmo.org/meetings/esmo-{conf_year}")
        return {
            "eternity": "temporary",
            "label": "⏰ 会议摘要 (1-2 年有效期)",
            "expiry_note": f"会议摘要通常仅 1-2 年有效, 之后转为正式发表. 失效后可查 PubMed 同作者后续发表.",
            "backup_url": backup_url,
        }
    
    # 3. 政府文件 (NHC): 永久
    if '中国' in journal or '卫生' in journal or '健康中国' in journal:
        return {
            "eternity": "permanent",
            "label": "🏛️ 政府文件 (永久)",
            "expiry_note": "",
            "backup_url": "http://www.nhc.gov.cn",
        }
    
    # 4. DOI 一般期刊: 永久 (DOI 永不失效)
    if doi:
        return {
            "eternity": "permanent",
            "label": "✅ DOI 永久",
            "expiry_note": "",
            "backup_url": "",
        }
    
    # 默认
    return {
        "eternity": "permanent",
        "label": "✅ 永久",
        "expiry_note": "",
        "backup_url": "",
    }


# ════════════════════════════════════════════════════════════════════
# v6: 完整 H 列 markdown 构建
# ════════════════════════════════════════════════════════════════════

def build_h_md_v6(
    pn_x: str,
    info_d: Dict,
    info_c: Dict,
    doi: str,
    scan: Optional[Dict] = None,
    c_raw: Optional[str] = None,
    row_n: Optional[int] = None,
    lit_base: str = "/Users/david/Desktop/雷管方案_文献整理/_literature_citation_index",
    d: Optional[str] = None,
) -> str:
    """
    v6.0: 与 Pn-x 目录一致的文件清单 + 应证评分 + 时效性标注

    新增:
    - 文件清单 (main + fallback + supp) 严格对应 _literature_citation_index/Pn-x/
    - 每个 PDF 都评分 (main 应证 PPT 内容的命中率)
    - 时效性标注 (DOI/IARC/NHC/会议)
    - 失效后备 (Wayback / 备用 URL)
    """
    import os as _os
    if scan is None:
        scan = scan_pn_x_dir(pn_x)
    
    if row_n is None:
        row_n = int(pn_x.split("-")[1]) + 10
    
    publisher = identify_publisher(info_d["journal"])
    
    title = info_d.get("title", "")
    if not title and info_c.get("visual_alignment"):
        for va in info_c["visual_alignment"]:
            if "引文:" in va:
                title = va.replace("引文:", "").strip()
                break
    
    # 类型 emoji
    if info_d["type"] == "conference_abstract":
        type_emoji = "📄 CONFERENCE ABSTRACT"
    elif pn_x == "P3-1":
        type_emoji = "📊 DATABASE (GLOBOCAN)"
    elif pn_x == "P3-2" or pn_x == "P5-1":
        type_emoji = "📋 GUIDELINE (政府文件)"
    else:
        type_emoji = "📄 LITERATURE"
    
    md_parts = []
    md_parts.append(f"🎯 Row {row_n} ({pn_x}) — {info_d['journal']} {info_d['year']} 文献应证\n")
    
    # 【📄 主文件】
    md_parts.append("【📄 主文件】 (D 列核心 + 文献信息)")

    main_score = calculate_main_score(scan)

    # v9.5: 检测 main PDF 错位
    # 用 D 列作为关键词源 (d 列是文献元数据, c 列是 PPT 上下文, 应该用 d 匹配文献)
    mismatch = detect_main_pdf_mismatch(pn_x, info_d, scan, d_raw=d)
    if not mismatch:
        # v9.5: 检测 main PDF 内容错位 (基于 page 1 文本)
        mismatch = detect_main_pdf_content_mismatch(pn_x, info_d, scan, d_raw=d)
    if mismatch:
        md_parts.append(f"  ⚠️ **main PDF 错位**: {mismatch['note']}")
        md_parts.append(f"    - D 列期望: {mismatch['expected']}")
        md_parts.append(f"    - 当前 main: `{mismatch['actual']}`")
        md_parts.append(f"    - 建议: 重新匹配 main PDF (当前 PDF 与 D 列文献不匹配)")

    if scan["main"]:
        for i, m in enumerate(scan["main"]):
            size_kb = scan["sizes"][m] // 1024
            md_parts.append(f"  - 文件名: `{m}` ({size_kb}KB)")
            if i == 0:  # 第一个 main, 显示文献信息
                if title and title != info_d["journal"]:
                    md_parts.append(f"    标题: {title[:80]}")
                md_parts.append(f"    作者: {info_d['authors']}")
                md_parts.append(f"    期刊: {info_d['journal']}")
                vol_issue = f"v{info_d['volume']}" + (f"({info_d['issue']})" if info_d['issue'] else "")
                pages = info_d['pages']
                if vol_issue and pages:
                    md_parts.append(f"    年/卷/期/页: {info_d['year']}, {vol_issue}: {pages}")
                elif vol_issue:
                    md_parts.append(f"    年/卷: {info_d['year']}, {vol_issue}")
                else:
                    md_parts.append(f"    年: {info_d['year']}")
                if publisher:
                    md_parts.append(f"    出版: {publisher}")
                if doi and not doi.startswith("备注"):
                    # DOI 行不显示链接 (避免与下方"下载链接"重复)
                    md_parts.append(f"    DOI: {doi}")
                elif info_d.get("abstract_id"):
                    md_parts.append(f"    摘要号: {info_d['abstract_id']}")
                # 应证评分 (从 manifest 的 step2_score 拿 found/total, 含等价推理)
                manifest = scan.get("manifest", {})
                found = manifest.get("step2_found", 0)
                total = manifest.get("step2_total", 0)
                equiv_count = manifest.get("equivalent_matches_count", 0)
                hl_summary = scan.get("highlight_summary", {})
                if total > 0:
                    # slide 3-5: 真实 step2 docling 应证
                    equiv_str = f", 含 {equiv_count} 个等价推理" if equiv_count > 0 else ""
                    perfect_mark = " ⭐满分" if main_score >= 1.0 else ""
                    md_parts.append(f"    应证评分: {main_score:.2f}{perfect_mark} (step2 hits {found}/{total}{equiv_str})")
                elif hl_summary and hl_summary.get("terms"):
                    # slide 6+: highlight 应证 (简化)
                    hits = hl_summary.get("hits", 0)
                    terms = hl_summary.get("terms", 0)
                    perfect_mark = " ⭐满分" if main_score >= 1.0 else ""
                    md_parts.append(f"    应证评分: {main_score:.2f}{perfect_mark} (highlight 应证: hits {hits} / terms {terms}, 未做 docling 语义级 step2)")
                elif main_score is None:
                    # slide 6+: 既没 highlight 也没 step2, main PDF 存在但未做 PPT视觉 vs PDF高亮 双向对齐
                    md_parts.append(f"    应证评分: ⏳ 待 PPT视觉 vs PDF高亮 双向对齐 (未运行 docling 表格结构识别 + 视觉匹配)")
                else:
                    md_parts.append(f"    应证评分: {main_score:.2f} (highlight hits {hl_summary.get('hits', 0)} / terms {hl_summary.get('terms', 1)})")
            elif i == 1:
                # 第二个 main (P5-13)
                md_parts.append(f"    注: 同一作者另一发表")
    else:
        md_parts.append("  - (无 main PDF)")
    
    md_parts.append("")
    
    # 【🔄 Fallback 补充材料】 (3 触发条件)
    #   1. main_score < 0.7 (低分, 即使 fb_cross_refs 不空也算)
    #   2. 有跨标号引用 (P4-3 fb 引 P4-1/P4-2 main, 即使 main 够也展示引用关系)
    #   3. main_score >= 1.0 满分 OR main_score=None (未做 docling) → 不显示 fb (v8.2)
    # 注: 旧条件 scan["fallback_triggered"] 是基于高亮图数量, 不准. 用 main_score 为准.
    # 满分或未验证 = 都不显示 fb (用户期望: 已验证满分 → 无需 fb; 未验证 → 不要拿未验证 fb 误导)
    hide_fb = (main_score is None) or (main_score >= 1.0)

    needs_fallback = (
        (not hide_fb and main_score < 0.7 and scan.get("fb")) or
        (not hide_fb and bool(scan.get("fb_cross_refs")))
    )

    show_supplementary = (
        not hide_fb and scan.get("fb") and not needs_fallback
    )

    if needs_fallback:
        # 区分三种 fallback 触发
        if main_score < 0.7:
            md_parts.append(f"【⚠️ Fallback 补充材料】 (main 应证评分 {main_score:.2f} < 0.7, 启用 fallback 补强)")
            md_parts.append(f"  原因: {scan['fallback_reason'][:120] if scan['fallback_reason'] else 'main 内容与 PPT 数据点不匹配'}")
        elif scan.get("fb_cross_refs"):
            md_parts.append("【🔄 Fallback 补充材料】 (跨标号引用, main 已足够应证)")
        else:
            md_parts.append("【🔄 Fallback 补充材料】")

        # v9.6: 跨 slide 共享引用段
        manifest = scan.get("manifest", {})
        if manifest.get("is_shared_reference") and manifest.get("shared_from"):
            shared_from = manifest["shared_from"]
            md_parts.append(f"【🔗 跨 slide 共享引用】 (PPT 标号在主目录无独立 PDF, 引用来自 {shared_from})")
            md_parts.append(f"  原因: PPT 标号内容已存在于 {shared_from} main PDF, 本目录共享引用")
            md_parts.append(f"  示例: P12-5 (Slide 12 标号 5) = P12-3 main PDF (Chan J Hepatol 2025 HIMALAYA Asian Subgroup - HBV 76.8%)")
            md_parts.append("")

        # v9.6: Vision OCR 段 (在 fallback 之前显示, 因为 vision 提取了 PDF 文字层没有的数据)
        vision_data_points = manifest.get("vision_ocr_data_points", [])
        if vision_data_points:
            md_parts.append(f"【📸 Vision OCR】 (sensenova-6.7-flash-lite 提取 highlight 图, {len(vision_data_points)} 个数据点)")
            for dp in vision_data_points[:8]:
                src_img = dp.get('source_image', '')
                md_parts.append(f"  - {dp.get('value', 'N/A')} ({dp.get('description', '')[:50]}) [{src_img}]")
            if len(vision_data_points) > 8:
                md_parts.append(f"  - ... 等共 {len(vision_data_points)} 个 (来源: {len(set(dp.get('source_image', '') for dp in vision_data_points))} 张 highlight 图)")
            md_parts.append("")

        # 本目录 fb (v8.7: 显示本地路径 + 文件名推断的期刊搜索链接)
        for fb in scan.get("fb_local", []):
            size_kb = scan["sizes"][fb] // 1024
            fb_score = calculate_fallback_score(scan, fb)
            fb_info_meta = scan.get("fb_info", {}).get(fb, {})
            应证_text = fb_info_meta.get("应证", "补充材料")
            fb_path = f"{lit_base}/{pn_x}/{fb}"
            md_parts.append(f"  - 文件名: `{fb}` ({size_kb}KB)")
            md_parts.append(f"    本地路径: {fb_path}")
            md_parts.append(f"    应证内容: {应证_text}")
            md_parts.append(f"    应证评分: {fb_score:.2f}")
            # v8.7: 从文件名推断期刊/会议, 显示搜索链接
            fb_search = _infer_fallback_search_link(fb)
            if fb_search:
                md_parts.append(f"    来源搜索: [{fb_search[1]}]({fb_search[0]})")

        # 跨标号引用
        for cross in scan.get("fb_cross_refs", []):
            if cross["target_file"] in scan.get("fb_local", []):
                continue  # 已在本目录显示过
            exists_mark = "✅" if cross.get("exists_in_lit") or cross.get("exists_in_src") else "❌"
            target_path = f"{lit_base}/{cross['target_pn_x']}/{cross['target_file']}"
            md_parts.append(f"  - 文件名: `{cross['target_file']}` (来自 {cross['target_pn_x']}, {exists_mark})")
            md_parts.append(f"    本地路径: {target_path}")
            md_parts.append(f"    应证内容: {cross['应证']}")
            md_parts.append(f"    应证评分: {cross['score']:.2f} (借用目标 Pn-x 的 step2_score)")
            # v8.7: 显示被引用 Pn-x 的链接
            target_pn_csv = cross['target_pn_x']
            target_doi = cross.get('target_doi', '')
            if target_doi:
                md_parts.append(f"    引用链接: [DOI 主链接](https://doi.org/{target_doi})")

        md_parts.append("")
    elif show_supplementary:
        # main 足够 (但非满分) 且有 fb (P5-8, P5-18)
        md_parts.append("【🔄 附加材料】 (main 已足够, 以下为补充)")
        for fb in scan["fb"]:
            size_kb = scan["sizes"][fb] // 1024
            fb_score = calculate_fallback_score(scan, fb)
            fb_path = f"{lit_base}/{pn_x}/{fb}"
            md_parts.append(f"  - 文件名: `{fb}` ({size_kb}KB)")
            md_parts.append(f"    本地路径: {fb_path}")
            md_parts.append(f"    用途: {'补充披露' if 'icmje' in fb.lower() else '同期发表' if 'nejm' in fb.lower() else '附录' if 'appendix' in fb.lower() else '补充材料'}")
            md_parts.append(f"    应证评分: {fb_score:.2f}")
            fb_search = _infer_fallback_search_link(fb)
            if fb_search:
                md_parts.append(f"    来源搜索: [{fb_search[1]}]({fb_search[0]})")
        md_parts.append("")
    
    # 【📚 补充材料 (supp)】
    if scan["supp"]:
        md_parts.append("【📚 补充材料】 (s1/s2 supplementary)")
        for s in scan["supp"]:
            size_kb = scan["sizes"][s] // 1024
            md_parts.append(f"  - `{s}` ({size_kb}KB)")
        md_parts.append("")
    
    # 【⚠️ 应证评分警告】 (main < 0.7 且无 fb)
    if main_score is not None and main_score < 0.7 and not scan.get("fb") and not scan.get("fb_cross_refs"):
        manifest = scan.get("manifest", {})
        missing = manifest.get("missing_data_points", [])
        found = manifest.get("found_data_points", [])
        md_parts.append(f"【⚠️ 应证评分低】 (main={main_score:.2f}, step2 hits {manifest.get('step2_found', 0)}/{manifest.get('step2_total', 0)})")
        md_parts.append(f"  原因: PPT 数据点在 PDF 中匹配率低")
        if missing:
            md_parts.append(f"  未找到数据点: {', '.join(missing[:8])}{'...' if len(missing) > 8 else ''}")
        if found:
            md_parts.append(f"  已找到: {', '.join(found[:8])}{'...' if len(found) > 8 else ''}")
        md_parts.append(f"  说明: PPT 引用数据点在 PDF 中以变体形式出现 (如 '14.4' vs '14.4%'), docling 文本匹配未必完整. 但 main PDF 仍是应证真理. 参考 main PDF 内容核对 PPT 数据点.")

        # v9.6: Vision OCR fallback - 当 PDF 文字找不到数据点时, 用 sensenova_vision API 提取 highlight 图
        vision_data_points = manifest.get("vision_ocr_data_points", [])
        if vision_data_points:
            md_parts.append("")
            md_parts.append(f"  📸 Vision OCR 已提取 ({len(vision_data_points)} 个数据点, 来自 highlight 图):")
            for dp in vision_data_points[:5]:
                md_parts.append(f"    - {dp.get('value', 'N/A')} ({dp.get('description', '')[:40]})")
            if len(vision_data_points) > 5:
                md_parts.append(f"    - ... 等共 {len(vision_data_points)} 个")
            md_parts.append("")
        md_parts.append("")

    # 【🧠 语义等同性推理】 (数值精度等价 + 单位等价)
    manifest = scan.get("manifest", {})
    equiv_matches = manifest.get("equivalent_found_data_points", [])
    if equiv_matches:
        md_parts.append("【🧠 语义等同性推理】 (数值/单位等价)")
        md_parts.append("  算法: 14.4 ≈ 14.40 ≈ 14.400 (浮点等) ; 14.4 ≈ 14.4% (单位等价, 当 PDF 上下文说明数据是百分比)")
        # 显示前 10 个等价匹配
        for eq in equiv_matches[:10]:
            md_parts.append(f"  - '{eq['dp']}' 在 PDF 中以变体 '{eq['variant']}' 出现 → 应证等价")
        if len(equiv_matches) > 10:
            md_parts.append(f"  - ... 等共 {len(equiv_matches)} 个等价命中")
        md_parts.append("")

    # 【✅ main 完整应证】 (当 main_score >= 0.95)
    # 注意: main_score 可能来自 highlight_summary (slide 6+) 而非 step2 (slide 3-5)
    if main_score is not None and main_score >= 0.95:
        manifest = scan.get("manifest", {})
        found_pts = manifest.get("found_data_points", [])
        equiv_pts = manifest.get("equivalent_found_data_points", [])
        found_locs = manifest.get("found_data_point_locations", {})
        total = manifest.get("step2_total", len(found_pts))
        step2_score = manifest.get("step2_score")
        hl_summary = scan.get("highlight_summary", {})

        # 是否满分
        perfect = main_score >= 1.0
        md_parts.append("【✅ main 完整应证 PPT 内容】" + (" ⭐满分" if perfect else ""))

        # 区分 score 来源
        if step2_score is not None:
            # slide 3-5: 真实 step2 docling 应证
            md_parts.append(f"  PPT 标号指向的内容已在 main PDF 中找到 ({len(found_pts)}/{total} 数据点命中, 评分 {main_score:.2f})")
        elif hl_summary and hl_summary.get("terms"):
            # slide 6+: 简化 highlight 应证
            hits = hl_summary.get("hits", 0)
            terms = hl_summary.get("terms", 0)
            page = hl_summary.get("page", "?")
            md_parts.append(f"  PPT 标号指向的内容已在 main PDF highlight 区域找到 ({hits} hits / {terms} terms, page {page})")
            md_parts.append(f"  ⚠️ 此评分基于 highlight 图视觉匹配, 未做 docling 语义级 step2 应证 (待升级)")
        else:
            md_parts.append(f"  PPT 标号指向的内容已在 main PDF 中找到 (评分 {main_score:.2f})")

        # 推理链: PPT 标号 → 语义理解 → PDF 应证位置
        if info_c.get("positions"):
            pos = info_c["positions"][0]
            ppt_text = pos.get("text", "")
            if ppt_text:
                md_parts.append(f"  PPT 引文 (推理源): {ppt_text[:100]}")
            if pos.get("data"):
                md_parts.append(f"  PPT 语义 (推理目标): {pos['data'][:100]}")

        # PDF 应证位置 (核心数据点的具体位置)
        if found_locs:
            # 优先找核心数据点 (带 % 或 > 10 数字)
            core_dps = [dp for dp in found_locs if "%" in dp or dp.replace(".", "").isdigit() and float(dp.replace("%", "")) >= 10]
            core_dps = core_dps[:3] if core_dps else list(found_locs.keys())[:3]
            md_parts.append(f"  📍 main PDF 应证位置 (核心数据):")
            import re as _re_ctx1
            for dp in core_dps:
                locs = found_locs[dp]
                if locs:
                    loc = locs[0]
                    # v8.6: 移除 context 中的完整 URL (避免 markdown_to_rich_text 误识别)
                    ctx = _re_ctx1.sub(r'https?://\S+', '', loc["text_snippet"])[:60].strip()
                    if not ctx:
                        ctx = "(context 截断)"
                    md_parts.append(f"    ✓ '{dp}' → page {loc['page_no']}: {ctx}...")

        # 显示 PDF 命中数据点汇总
        if found_pts:
            md_parts.append(f"  PDF 命中数据点 (前 8 个):")
            for dp in found_pts[:8]:
                md_parts.append(f"    ✓ {dp}")
        if equiv_pts:
            md_parts.append(f"  PDF 等价命中 (前 5 个):")
            for eq in equiv_pts[:5]:
                md_parts.append(f"    ≈ {eq['dp']} (PDF 中以 {eq['variant']} 形式)")
        md_parts.append("")

    # 【🎯 应证推理】 — 完整 5 步推理链 (2026-08-02 用户硬规则 v7.3)
    md_parts.append("【🎯 应证推理】 (完整 5 步推理链: PPT视觉 → 信息要素 → PDF应证)")

    # ① PPT 标号指向位置 (视觉) — v8.5 严格从 C 列视觉描述提取, 不靠 D 列
    md_parts.append("  ① PPT 标号指向位置 (视觉):")
    
    # 整页引文 / 位置描述 / 引文位置 — 三种来源
    if info_c.get("positions"):
        for i, pos in enumerate(info_c["positions"][:3]):
            loc = pos.get("location", "PPT 右半区域")
            text = pos.get("text", "")[:60]
            md_parts.append(f"    - {loc}: {text}")
    elif info_c.get("visual_alignment"):
        for va in info_c["visual_alignment"][:2]:
            md_parts.append(f"    - {va[:80]}")
    elif info_c.get("引文位置"):
        # 整页引文 / 脚注引文
        md_parts.append(f"    - {info_c['引文位置'][:80]}")
    elif info_c.get("data_alignment"):
        # 整页引文 / 无独立位置标号
        for da in info_c["data_alignment"][:1]:
            md_parts.append(f"    - {da[:80]}")
    else:
        md_parts.append("    - (PPT slide 标号位置未识别)")

    # ② PPT 视觉内容 (完整信息要素) — v8.5 严格从 PPT slide 视觉识别 (不依赖 D 列)
    md_parts.append("  ② PPT 视觉内容 (完整信息要素, PPT slide 视觉识别):")
    
    # 优先从 manifest.ppt_data_points (这是 PPT 视觉识别后的真实数据点)
    manifest = scan.get("manifest", {})
    ppt_pts = manifest.get("ppt_data_points", [])
    
    if ppt_pts:
        for dp in ppt_pts[:8]:
            md_parts.append(f"    - 视觉识别数据点: '{dp}'")
    elif info_c.get("data_alignment"):
        for da in info_c["data_alignment"][:3]:
            md_parts.append(f"    - {da[:100]}")
    else:
        md_parts.append("    - (PPT slide 视觉识别未提取到数据点, 待 docling 视觉识别)")

    # ③ 推理: 需要在 main PDF 中找到 视觉/数据/语义一致的内容
    md_parts.append("  ③ 推理 (信息要素匹配): 需在 main PDF 中找到:")
    manifest = scan.get("manifest", {})
    found_pts = manifest.get("found_data_points", [])
    found_locs = manifest.get("found_data_point_locations", {})
    
    # v8.4: 即使没 docling, 也从 C 列提取数据点 + 从 D 列提取关键术语作为推理目标
    import re as _re
    
    inference_targets = []  # [(category, value), ...]
    
    # 从 C 列 data_alignment 提取数字 + 术语
    if info_c.get("data_alignment"):
        for da in info_c["data_alignment"][:5]:
            for num_m in _re.finditer(r"\b(\d+(?:\.\d+)?)\s*%?", da):
                v = num_m.group(1)
                if "%" in da or len(v) >= 2:  # 跳过单数字
                    inference_targets.append(("数据", v))
            for kw in ["STRIDE", "T+A", "O+Y", "Len", "Pembro", "NIVO", "IPI", "Durvalumab", "Tremelimumab", "Atezolizumab", "Bevacizumab", "Sorafenib"]:
                if kw in da:
                    inference_targets.append(("术语", kw))
    
    # 从 D 列提取关键信息
    if info_d.get("title"):
        inference_targets.append(("文字", info_d["title"][:60]))
    if info_d.get("authors"):
        inference_targets.append(("作者", info_d["authors"][:60]))
    
    # 去重 + 限制显示
    seen = set()
    unique_targets = []
    for cat, v in inference_targets:
        if v not in seen:
            seen.add(v)
            unique_targets.append((cat, v))
    
    # 显示 found_pts (来自 manifest)
    if found_pts:
        core_pts = [dp for dp in found_pts if "%" in dp or (dp.replace(".", "").replace("-", "").isdigit() and float(dp.replace("%", "")) > 1)][:3]
        if not core_pts:
            core_pts = found_pts[:3]
        for dp in core_pts:
            md_parts.append(f"    - 数据: '{dp}'")
    else:
        # 没 docling: 显示 C/D 列推理目标
        for cat, v in unique_targets[:6]:
            md_parts.append(f"    - {cat}: '{v}'")
    
    if info_c.get("引文"):
        md_parts.append(f"    - 文字: {info_c['引文'][:80]}")

    # ④ main PDF 应证位置 (语义推理匹配, 按 PPT 语义相关性排序)
    md_parts.append("  ④ main PDF 应证位置 (语义推理匹配):")
    
    if found_locs:
        # 已 docling: 显示真实应证位置
        def sort_key(item):
            dp = item[0]
            ctx = item[1][0]["text_snippet"] if item[1] else ""
            if any(kw in ctx.lower() for kw in ["months", "month", "pfs", "os ", "hazard", "survival"]):
                return 0
            if "%" in dp:
                return 1
            try:
                v = float(dp.replace("%", ""))
                if v >= 10:
                    return 2
                else:
                    return 3
            except ValueError:
                return 4

        sorted_locs = sorted(found_locs.items(), key=sort_key)
        for dp, locs in sorted_locs[:5]:
            if locs:
                loc = locs[0]
                # v8.6: 移除 context 中的完整 URL (避免 markdown_to_rich_text 误识别, 飞书显示 https://d...)
                import re as _re_ctx
                ctx = _re_ctx.sub(r'https?://\S+', '', loc["text_snippet"])[:60]
                ctx = ctx.strip()
                if not ctx:
                    ctx = "(context 截断)"
                md_parts.append(f"    ✓ '{dp}' → page {loc['page_no']}: {ctx}...")
        if len(found_locs) > 5:
            md_parts.append(f"    ... 等共 {len(found_locs)} 个数据点已应证")
    elif scan.get("main_pdf"):
        # v8.4: 没 docling 时, 跑轻量级 PyMuPDF text 搜索关键数据点
        # scan.main_pdf 是文件名 (无 Pn-x/ 前缀), 路径需要 lit_base + pn_x + filename
        main_pdf_path = f"{lit_base}/{pn_x}/{scan['main_pdf']}"
        if not _os.path.isfile(main_pdf_path):
            main_pdf_path = f"{scan.get('src_base', '/Users/david/Desktop/雷管方案_文献整理')}/{pn_x}/{scan['main_pdf']}"
        if not _os.path.isfile(main_pdf_path):
            # 最后尝试: scan.main_pdf 可能含 Pn-x/ 前缀 (来自 manifest)
            main_pdf_path = f"{lit_base}/{scan['main_pdf']}"
        
        light_hits = []  # [(dp, page, ctx), ...]
        if _os.path.isfile(main_pdf_path):
            try:
                import fitz as _fitz
                doc = _fitz.open(main_pdf_path)
                # 从 C 列 + D 列提取搜索目标
                search_terms = []
                if info_c.get("data_alignment"):
                    import re as _re_lite
                    for da in info_c["data_alignment"][:5]:
                        for num_m in _re_lite.finditer(r"\b(\d+(?:\.\d+)?)\s*%?", da):
                            v = num_m.group(1)
                            if len(v) >= 2 and v not in search_terms:
                                search_terms.append(v)
                # 加上 D 列作者
                if info_d.get("authors"):
                    first_author = info_d["authors"].split(",")[0].split(" et")[0].strip()
                    if first_author and first_author not in search_terms:
                        search_terms.append(first_author)
                
                # 在 PDF 中搜索
                for term in search_terms[:5]:
                    for p_idx, page in enumerate(doc):
                        if p_idx >= 5:  # 只搜前 5 页
                            break
                        text = page.get_text()[:3000]
                        if term in text:
                            # 找上下文
                            idx = text.find(term)
                            ctx = text[max(0, idx-30):idx+60].replace("\n", " ")
                            light_hits.append((term, p_idx+1, ctx))
                            break
                doc.close()
            except Exception as _e:
                pass
        
        if light_hits:
            for dp, page, ctx in light_hits[:4]:
                md_parts.append(f"    ✓ '{dp}' → page {page}: {ctx}...")
            md_parts.append("    (轻量级 PyMuPDF 搜索, 未做 docling 语义级应证, 待升级)")
        else:
            md_parts.append("    (未做 docling 应证, 轻量级搜索未命中关键数据点)")

    # ⑤ 推理结果 — v8.5 严格基于 PPT视觉 vs PDF高亮双向对齐的 step2_score
    md_parts.append("  ⑤ 推理结果:")
    
    if main_score is None:
        md_parts.append("    ⚠️ 未做 PPT视觉 vs PDF高亮 双向对齐, 待运行 docling / 轻量级搜索应证")
        if scan.get("main_pdf"):
            md_parts.append(f"    📁 main PDF 文件: {scan['main_pdf']} ({scan.get('main_pdf_size_kb', 0)}KB)")
            md_parts.append(f"    💡 文件存在, 待 PPT视觉识别 + PDF docling/PyMuPDF 应证")
    elif main_score >= 1.0:
        md_parts.append("    ✅ main 完整应证 PPT 视觉识别的全部信息要素 (⭐满分, 双向对齐)")
    elif main_score >= 0.85:
        md_parts.append("    ✅ main 高度应证 PPT 视觉识别的多数信息要素")
    elif main_score >= 0.7:
        md_parts.append("    ⚠️ main 部分应证 PPT 视觉识别的信息要素")
    elif main_score >= 0.4:
        md_parts.append("    ⚠️ main 应证不足, 需 fallback 补强")
    else:
        md_parts.append("    ❌ main 应证失败, fallback 是必需")

    # 保留 visual_alignment / semantic_reasoning 作为补充
    if info_c.get("semantic_reasoning"):
        md_parts.append("")
        md_parts.append("  [补充参考] 视觉/语义推理原始记录:")
        for sr in info_c["semantic_reasoning"][:2]:
            md_parts.append(f"    - {sr[:100]}")

    md_parts.append("")
    
    # 【📎 下载链接 + 时效】
    link_et = identify_link_eternality(doi, info_d["journal"], info_d)

    # v8.7: 会议摘要 (ESMO/ASCO/APASL/CSCO/EASL/AASLD) 即使有 DOI, 也不走出版商直链
    # 因为 PDF 是会议摘要, 不是 ScienceDirect/PubMed 上的论文
    # v9.1: 所有有 DOI 的 Pn-x 都用 DOI 重定向 URL (指向具体文章/摘要页)
    if doi and not doi.startswith("备注"):
        md_parts.append("【📎 下载链接 + 时效性】")
        md_parts.append(f"  {link_et['label']}")

        # v7.6: 多层级下载链接 (出版商直链 + 数据库 + DOI 通用 + OpenAccess)
        # v9.0: 传递 verified URL (从 DOI 重定向链跟踪得到, 真实可访问)
        manifest = scan.get("manifest", {})
        verified_url = manifest.get("verified_doi_url")
        pdf_urls = get_publisher_pdf_urls(doi, info_d.get("journal", ""), verified_url)

        # v9.0: 优先用 verified URL (从 DOI 重定向链跟踪得到, 真实可访问)
        # 例如: 
        #   - P13-2: https://linkinghub.elsevier.com/retrieve/pii/S0168827825002260 (正确)
        #   - 旧: https://www.sciencedirect.com/science/article/doi/10.1016/j.jhep.2025.03.033 (404)
        # 特殊: Weblink 也用 verified URL (GLOBOCAN 等)
        md_parts.append("  🔗 链接:")
        for label, url in pdf_urls:
            if "全文" in label:
                # 第一行: 出版商全文 (verified URL, 真实可访问)
                md_parts.append(f"    - {label}: [{label.split()[0]}]({url})")
            elif label == "DOI 主链接":
                md_parts.append(f"    - DOI 主链接: [{doi}](https://doi.org/{doi})")
            elif label == "PubMed 搜索":
                md_parts.append(f"    - PubMed 搜索: [{doi}]({url})")
            elif label == "Europe PMC 搜索":
                md_parts.append(f"    - Europe PMC 搜索: [{doi}]({url})")

        if link_et.get("expiry_note"):
            md_parts.append(f"  - 时效说明: {link_et['expiry_note']}")
        if link_et.get("backup_url"):
            md_parts.append(f"  - 失效后备: [{link_et['backup_url']}]({link_et['backup_url']})")
        md_parts.append("")
    elif pn_x == "P3-1":
        # GLOBOCAN 特殊
        md_parts.append("【📎 下载链接 + 时效性】")
        md_parts.append(f"  {link_et['label']}")
        md_parts.append(f"  - IARC 官方 (2024 在线版): [gco.iarc.who.int](https://gco.iarc.who.int)")
        md_parts.append(f"  - GLOBOCAN 2022 Liver PDF: [IARC 存档](https://gco.iarc.fr/today/data/factsheets/cancers/11-Liver-fact-sheet.pdf)")
        md_parts.append(f"  - 时效说明: {link_et['expiry_note']}")
        md_parts.append(f"  - 失效后备: [Wayback Machine]({link_et['backup_url']})")
        md_parts.append("")
    # v9.1: 无 DOI 的 Pn-x (政府文件/中文期刊/会议摘要无DOI)
    # 构造搜索链接指向具体页面
    else:
        # 无 DOI: 用 D 列期刊名+标题构造 PubMed 搜索
        journal = info_d.get("journal", "").strip()
        title = info_d.get("title", "").strip()
        authors = info_d.get("authors", "").strip()
        year = info_d.get("year", "")

        # 构造搜索词 (与 if branch 共享)
        search_terms = []
        if authors:
            first_author = authors.split(",")[0].split(" et")[0].strip()
            if first_author:
                search_terms.append(first_author)
        if journal:
            search_terms.append(journal)
        if year:
            search_terms.append(str(year))
        if title:
            title_kw = title.replace(" ", "+")[:30]
            search_terms.append(title_kw)

        md_parts.append("【📎 下载链接 + 时效性】")

        # v9.3: 检查 verified_doi_url (从 gov.cn 搜索得到, 真实可访问页面)
        manifest = scan.get("manifest", {})
        verified_url = manifest.get("verified_doi_url")
        if verified_url:
            source_label = "gov.cn" if "gov.cn" in verified_url else "源网站"
            md_parts.append(f"  ✅ {source_label} 全文")
            md_parts.append(f"  🔗 链接:")
            md_parts.append(f"    - {source_label} 全文: [{source_label}]({verified_url})")
            md_parts.append("")
            md_parts.append("  🔍 备选搜索:")
        else:
            md_parts.append("  ⏳ 无 DOI 永久链接")

        # 构造搜索词 (优先用 DOI 备注, 如果无 DOI)
        # 无 DOI 的 Pn-x: 政府文件/中文期刊, 用 DOI 备注列的关键词
        if doi and doi.startswith("备注"):
            # 无 DOI: 用 D 列原文作为搜索关键词
            # D 列是文档标题 (如 "《健康中国行动——癌症防治行动实施方案（2023-2030年）》")
            # 这是最精确的搜索词, 指向具体文档页
            # D 列原文在 info_d 中没有, 从 c_raw 或 doi 提取
            # 用 c_raw 中的标题作为搜索词
            search_term = ""
            # 从 c_raw 提取标题 (去掉 PPT 标号前缀)
            if c_raw and "「" in c_raw and "」" in c_raw:
                import re as _re_c
                m = _re_c.search(r'「(.+?)」', c_raw)
                if m:
                    search_term = m.group(1).replace(" ", "+")[:60]
            if not search_term:
                # 用 DOI 备注
                search_term = doi.replace("备注:", "").replace("无 DOI", "").strip().replace(" ", "+")[:40]
            if not search_term:
                search_term = "health"
            if search_term and search_term != "+":
                search_url = f"https://www.google.com/search?q={search_term}"
                md_parts.append(f"  - Google 搜索: [{search_term[:40]}]({search_url})")
        elif search_terms:
            search_term = "+".join(search_terms)
            search_url = f"https://www.google.com/search?q={search_term}"
            md_parts.append(f"  - Google 搜索: [{search_term[:40]}]({search_url})")
        
        # 会议摘要搜索 (按会议名+摘要号)
        if info_d.get("abstract_id"):
            abstract_id = info_d["abstract_id"]
            conf_name = info_d.get("conference_name", "")
            search_term = f"{conf_name}+{abstract_id}" if conf_name else abstract_id
            search_url = f"https://pubmed.ncbi.nlm.nih.gov/?term={search_term}"
            md_parts.append(f"  - PubMed 搜索 (会议+摘要号): [{search_term}]({search_url})")
        
        # 政府文件: 用 NHC 搜索
        if "政府" in journal or "健康" in journal or "中国" in journal:
            # v9.2: 用 C 列标题作为 NHC 搜索词
            nhc_term = search_term if search_term else "health"
            md_parts.append(f"  - NHC 搜索: [{nhc_term[:40]}](https://www.nhc.gov.cn/search?q={nhc_term})")
        
        md_parts.append("")
    
    md_parts.append(f"【🏷️ 类型】 {type_emoji}")
    
    return "\n".join(md_parts)


def build_h_rich_text_v6(pn_x, info_d, info_c, doi, scan=None, c_raw=None, row_n=None, lit_base="/Users/david/Desktop/雷管方案_文献整理/_literature_citation_index", d=None):
    """v6 入口"""
    if scan is None:
        scan = scan_pn_x_dir(pn_x, lit_base)
    if row_n is None:
        row_n = int(pn_x.split("-")[1]) + 10
    h_md = build_h_md_v6(pn_x, info_d, info_c, doi, scan, c_raw, row_n, lit_base, d=d)
    return markdown_to_rich_text(h_md)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("=== 测试 v6 ===")
        d = scan_pn_x_dir("P5-2")
        print(f"P5-2: main={d['main']}, fb={d['fb']}, score={calculate_main_score(d)}")
        
        d = scan_pn_x_dir("P5-8")
        print(f"P5-8: main={d['main']}, fb={d['fb']}, score={calculate_main_score(d)}")
        
        d = scan_pn_x_dir("P5-13")
        print(f"P5-13: main={d['main']}, supp={d['supp']}, score={calculate_main_score(d)}")
