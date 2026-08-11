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



