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


