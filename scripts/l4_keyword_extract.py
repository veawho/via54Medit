#!/usr/bin/env python3
"""
l4_keyword_extract.py — L4 关键词抽取改进 (避免过于通用)

问题: 原 extract_keywords_from_d() 抽 "2020", "99%" 这种过于通用的词
      搜不到 PDF 里的具体内容
修复: 5 维特征, 每个都加可信度评分, 低分词丢弃

5 维:
  1. 数字 + % (高可信, 直接抽)
  2. 药物/方案名 (高可信, 白名单)
  3. 期刊缩写 (中可信)
  4. 数字 (低可信, 容易是页码/年份/编号, 需组合)
  5. 作者姓 (低可信, 同名干扰)

可信度评分:
  - 高 (>0.7): 必保留
  - 中 (0.3-0.7): 看上下文
  - 低 (<0.3): 默认丢弃
"""
import os, sys, json, re
from typing import Dict, List, Optional, Tuple
from collections import Counter


# ════════════════════════════════════════════════════════════════
# 5 维特征 + 可信度
# ════════════════════════════════════════════════════════════════

# 高可信: 药物/方案名 (HCC/TMA 等领域术语)
HIGH_CONFIDENCE_TERMS = {
    # uHCC 药物
    "atezolizumab", "bevacizumab", "sorafenib", "lenvatinib", "regorafenib",
    "cabozantinib", "ramucirumab", "tremelimumab", "durvalumab",
    "nivolumab", "pembrolizumab", "ipilimumab", "camrelizumab",
    "tislelizumab", "sintilimab", "toripalimab", "penpulimab",
    "apatinib", "donafenib", "anlotinib",
    # 方案名
    "STRIDE", "HIMALAYA", "IMbrave150", "IMbrave", "LEAP-002", "LEAP",
    "AHELP", "ORIENT", "CheckMate", "RATIONALE", "T+A", "O+Y",
    "TREMENDOUS", "CARES-310", "APASL", "EASL", "AASLD", "NCCN",
    "T+A方案", "O+Y方案", "STRIDE方案", "双免疫", "联合治疗", "单药",
    "一线治疗", "二线治疗", "转化治疗", "新辅助", "辅助治疗",
    "RESORCE", "REFLECT", "IMbrave050", "CheckMate 9DW", "HCC",
    "uHCC", "BCLC", "Child-Pugh", "ECOG", "ORR", "DCR", "PFS", "OS",
    "mOS", "mPFS", "DOR", "TTR", "HRQoL",
    # TMA/HUS/TTP 术语
    "aHUS", "TTP", "TMA", "HUS", "STEC-HUS", "MAHA", "ADAMTS13",
    "complement", "C3", "C5", "C5a", "C1q", "CFH", "CFI", "CD55", "CD59",
    "eculizumab", "ravulizumab", "caplacizumab", "PNH",
    # 通用检验/指标
    "Hb", "LDH", "PLT", "Cr", "AST", "ALT", "TBil", "PT", "APTT",
    "D-dimer", "FDP", "INR", "网织红", "裂红细胞", "球形红细胞",
}

# 中可信: 期刊
MEDIUM_CONFIDENCE_TERMS = {
    "Lancet", "Hepatol", "NEJM", "JCO", "ASCO", "ESMO", "JAMA",
    "HBSN", "Cancer", "Anticancer", "中华血液", "BJC", "J Hepatol",
    "Clin Gastroenterol", "Gut", "Hepatology",
    "Front Oncol", "Front Immunol", "Nat Med", "Nat Commun",
}

# 低可信: 数字/通用术语
LOW_CONFIDENCE_TERMS = {
    "patient", "patients", "study", "results", "method", "background",
    "目的", "方法", "结果", "结论", "讨论", "摘要", "引言",
    "2020", "2021", "2022", "2023", "2024", "2025",  # 纯年份
}


# ════════════════════════════════════════════════════════════════
# 核心
# ════════════════════════════════════════════════════════════════

def extract_keywords_v2(citation: str, visual_context: str = "",
                       min_confidence: float = 0.3,
                       max_keywords: int = 12) -> List[Dict]:
    """
    抽取关键词 + 可信度评分

    Args:
        citation: D 列引文
        visual_context: D 列视觉内容 (可选, 用于补充)
        min_confidence: 最低可信度阈值 (低于丢弃)
        max_keywords: 最多返回几个

    Returns:
        [{'term': str, 'confidence': float, 'category': str, 'source': str}, ...]
    """
    candidates: Dict[str, Dict] = {}  # term -> best candidate
    full_text = f"{citation} {visual_context}"

    # 1. 数字 + % (高可信)
    for m in re.finditer(r'(\d+\.?\d*)\s*%', full_text):
        term = m.group(1) + "%"
        candidates[term] = {
            "term": term,
            "confidence": 0.9,
            "category": "percentage",
            "source": "regex",
        }

    # 2. HR 数字
    for m in re.finditer(r'HR\s*[=:]?\s*(\d+\.?\d*)', full_text, re.IGNORECASE):
        n = m.group(1)
        for term in [f"HR {n}", f"HR={n}", n]:
            candidates[term] = {
                "term": term,
                "confidence": 0.85,
                "category": "hr",
                "source": "regex",
            }

    # 3. 高可信术语 (药物/方案)
    for term in HIGH_CONFIDENCE_TERMS:
        if term in full_text:
            candidates[term] = {
                "term": term,
                "confidence": 0.85,
                "category": "drug_or_trial",
                "source": "whitelist",
            }

    # 4. 中可信术语 (期刊)
    for term in MEDIUM_CONFIDENCE_TERMS:
        if term in full_text:
            candidates[term] = {
                "term": term,
                "confidence": 0.5,
                "category": "journal",
                "source": "whitelist",
            }

    # 5. 中文 2-4 字词 (中可信, 从 visual_context 抽)
    if visual_context:
        cn_words = re.findall(r'[\u4e00-\u9fff]{2,4}', visual_context)
        cn_count = Counter(cn_words)
        for word, count in cn_count.most_common(10):
            if word in LOW_CONFIDENCE_TERMS:
                continue
            if len(word) < 2:
                continue
            # 出现 2+ 次加分
            conf = 0.6 if count >= 2 else 0.4
            if word not in candidates or candidates[word]["confidence"] < conf:
                candidates[word] = {
                    "term": word,
                    "confidence": conf,
                    "category": "cn_term",
                    "source": "ngram",
                    "count": count,
                }

    # 6. 作者姓 (低可信)
    m = re.match(r'^\s*([A-Z][a-zA-Z\-]+)', citation)
    if m:
        surname = m.group(1)
        candidates[surname] = {
            "term": surname,
            "confidence": 0.3,
            "category": "author_surname",
            "source": "regex",
        }

    # 7. 纯年份 (低可信, 默认丢弃)
    for m in re.finditer(r'\b(?:19|20)\d{2}\b', full_text):
        term = m.group(0)
        if term not in candidates:
            # 年份只在 [位置: ...] 上下文有意义
            if visual_context and ('发表' in visual_context or '年份' in visual_context):
                candidates[term] = {
                    "term": term,
                    "confidence": 0.4,
                    "category": "year",
                    "source": "regex",
                }
            # 否则丢弃

    # 过滤 + 排序
    result = [c for c in candidates.values() if c["confidence"] >= min_confidence]
    result.sort(key=lambda c: -c["confidence"])

    return result[:max_keywords]


# ════════════════════════════════════════════════════════════════
# 与 v10.1 兼容的简化版本 (返回 list[str])
# ════════════════════════════════════════════════════════════════

def extract_keywords_simple(citation: str, visual_context: str = "") -> List[str]:
    """v10.1 兼容 API: 返回 [term, ...]"""
    return [c["term"] for c in extract_keywords_v2(citation, visual_context)]


# ════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "extract":
        if len(sys.argv) < 3:
            print("Usage: extract <citation> [visual_context]")
            sys.exit(1)
        citation = sys.argv[2]
        visual = sys.argv[3] if len(sys.argv) > 3 else ""
        result = extract_keywords_v2(citation, visual)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif sys.argv[1] == "demo":
        # 演示
        samples = [
            ("Rimassa L, et al. J Hepatol. 2025", "[数据点: 16.9% 5年OS, HR 0.78, STRIDE 方案]"),
            ("Llovet JM, et al. NEJM 2008", "[Sorafenib vs placebo, mOS 10.7月 vs 7.9月, SHARP trial]"),
            ("Qin S, et al. Lancet 2023", "[IMbrave150, atezolizumab+bevacizumab, 24.0月 vs 13.4月]"),
            ("任宏, 等. 中国小儿急救医学, 2020, 27 (08): 577-581.", "[TTP诊断, ADAMTS13 90% 灵敏度, 99% 特异]"),
        ]
        for cit, ctx in samples:
            print(f"\n=== {cit[:60]} ===")
            print(f"  Context: {ctx[:60]}")
            kws = extract_keywords_v2(cit, ctx)
            for k in kws:
                print(f"    {k['confidence']:.2f} [{k['category']:18s}] {k['term']}")
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
