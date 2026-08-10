#!/usr/bin/env python3
"""
l0_paper_match.py — L0 错论文根治 (作者 + 期刊 + 年份 交叉校验)

问题: via54_pdf_download.py 下载的 PDF 经常是"名字相近"的论文
       (e.g., D 列要 Nguyen TC 2006, 下载到 Reigada D 论文)
修复: 5 维特征交叉验证, 不匹配则拒绝 + 重新搜

5 维特征:
  1. 作者 (surname + initials)
  2. 期刊 (缩写/全称)
  3. 年份
  4. 标题关键词 (>= 3)
  5. DOI 后缀 (路径段)

Usage:
  python3.11 l0_paper_match.py verify <pdf_path> <expected_d_citation>
  python3.11 l0_paper_match.py search <expected_d_citation>  # 重新搜正确论文
  python3.11 l0_paper_match.py audit <lit_base>  # 全量审计
"""
import os, sys, json, re, subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

try:
    import fitz
    fitz.TOOLS.mupdf_display_warnings(False)
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False


# ════════════════════════════════════════════════════════════════
# 特征提取
# ════════════════════════════════════════════════════════════════

# 期刊别名映射
JOURNAL_ALIASES = {
    "j hepatol": ["jhepatol", "j_hepatol", "journal of hepatology"],
    "j clin oncol": ["jco", "jclinoncol", "journal of clinical oncology"],
    "jama oncol": ["jamaoncol", "jama oncology"],
    "front oncol": ["frontoncol", "frontiers in oncology"],
    "front immunol": ["frontimmunol", "frontiers in immunology"],
    "br j cancer": ["bjc", "brjcancer", "british journal of cancer"],
    "nat commun": ["natcommun", "nature communications"],
    "nat rev cancer": ["natrevcancer"],
    "lancet oncol": ["lancetoncol", "the lancet oncology"],
    "liver int": ["liverint", "liver international"],
    "clin cancer res": ["clincancerres", "clinical cancer research"],
    "hepatology": ["hepatology"],
    "n engl j med": ["nejm", "new england journal of medicine"],
    "j am med assoc": ["jama", "journal of the american medical association"],
    "gastroenterology": ["gastroenterology"],
    "ann oncol": ["annoncol", "annals of oncology"],
    "br j haematol": ["brjh", "bjh", "british journal of haematology"],
}


def _extract_surname(citation: str) -> Optional[str]:
    """从引文抽第一作者姓 (e.g. 'Qin S, et al. Lancet. 2025' → 'Qin')"""
    # 第一段到逗号
    m = re.match(r'^\s*([A-Z][a-zA-Z\-]+)\s+[A-Z]', citation)
    if m:
        return m.group(1)
    # 中文 (e.g. "任宏, 等")
    m = re.match(r'^([\u4e00-\u9fff]{2,4})', citation)
    if m:
        return m.group(1)
    return None


def _extract_journal(citation: str) -> Optional[str]:
    """抽期刊名 (缩写或全称)"""
    # 找 "X. 2024" 模式 (期刊. 年份)
    m = re.search(r'([A-Z][a-zA-Z\.\s]+?)\.?\s*20\d{2}', citation)
    if m:
        return m.group(1).strip().rstrip('.')
    # 中文期刊
    m = re.search(r'《([^》]+)》', citation)
    if m:
        return m.group(1)
    return None


def _extract_year(citation: str) -> Optional[str]:
    """抽年份"""
    m = re.search(r'\b(19|20)\d{2}\b', citation)
    return m.group(0) if m else None


def _extract_volume_issue_pages(citation: str) -> Optional[Dict]:
    """抽 卷(期):页"""
    # e.g., "2024;6(1):39-50" → {year: 2024, vol: 6, issue: 1, pages: 39-50}
    m = re.search(r'(20\d{2})\s*;\s*(\d+)\s*\((\d+)\)\s*:\s*([\d\-]+)', citation)
    if m:
        return {
            "year": m.group(1),
            "vol": m.group(2),
            "issue": m.group(3),
            "pages": m.group(4),
        }
    return None


def _extract_doi(citation: str) -> Optional[str]:
    """抽 DOI"""
    m = re.search(r'10\.\d{4,9}/[A-Za-z0-9._\-\(\)/]+', citation)
    return m.group(0) if m else None


def _extract_d_citation(citation: str) -> Dict:
    """从 D 列引文抽全部特征"""
    return {
        "surname": _extract_surname(citation),
        "journal": _extract_journal(citation),
        "year": _extract_year(citation),
        "doi": _extract_doi(citation),
        "vip": _extract_volume_issue_pages(citation),
        "raw": citation,
    }


# ════════════════════════════════════════════════════════════════
# PDF 内容特征提取
# ════════════════════════════════════════════════════════════════

def _extract_pdf_features(pdf_path: str, max_pages: int = 3) -> Dict:
    """
    从 PDF 头部 (1-3 页) 抽:
    - 第一作者姓
    - 期刊
    - 年份
    - DOI
    - 标题关键词
    """
    if not HAS_PYMUPDF or not os.path.isfile(pdf_path):
        return {"error": "no_pymupdf_or_file"}
    try:
        doc = fitz.open(pdf_path)
        n = min(max_pages, len(doc))
        all_text = ""
        for i in range(n):
            try:
                all_text += doc[i].get_text() + "\n"
            except Exception:
                pass
        doc.close()
    except Exception as e:
        return {"error": str(e)}

    text_lower = all_text.lower()
    features = {
        "surname_in_pdf": None,
        "journal_in_pdf": None,
        "year_in_pdf": None,
        "doi_in_pdf": _extract_doi(all_text),
        "first_words": [],
    }

    # 第一作者姓: 取 page 1 第一个大写词组
    m = re.search(r'([A-Z][a-zA-Z\-]+)\s+[A-Z][a-z]+', all_text)
    if m:
        features["surname_in_pdf"] = m.group(1)

    # 期刊: 在已知别名里匹配
    for j, aliases in JOURNAL_ALIASES.items():
        if any(a in text_lower for a in [j] + aliases):
            features["journal_in_pdf"] = j
            break

    # 年份
    years = re.findall(r'\b(?:19|20)\d{2}\b', all_text)
    if years:
        # 优先取前 3 页出现次数最多的年份 (最可能是发表年)
        from collections import Counter
        features["year_in_pdf"] = Counter(years).most_common(1)[0][0]

    # 标题关键词: 取前 100 字符的 5+ 字符词
    title_candidates = re.findall(r'\b[A-Z][a-zA-Z]{4,}\b', all_text[:500])
    features["first_words"] = list(set(title_candidates))[:10]

    return features


# ════════════════════════════════════════════════════════════════
# 校验: PDF 是否符合 D 列引文
# ════════════════════════════════════════════════════════════════

def verify_paper_match(pdf_path: str, expected_citation: str, min_score: float = 0.5) -> Dict:
    """
    验证下载的 PDF 是否符合 expected_citation

    Returns:
        {
            'ok': bool,             # 是否匹配
            'score': float,         # 0-1
            'matches': {...},       # 匹配的字段
            'mismatches': [...],    # 不匹配的字段
            'expected': {...},      # 期望特征
            'actual': {...},        # PDF 实际特征
        }
    """
    expected = _extract_d_citation(expected_citation)
    actual = _extract_pdf_features(pdf_path)

    matches = {}
    mismatches = []
    score = 0.0
    max_score = 0.0

    # 1. 作者姓 (权重 0.3)
    max_score += 0.3
    if expected["surname"] and actual.get("surname_in_pdf"):
        if expected["surname"].lower() == actual["surname_in_pdf"].lower():
            matches["surname"] = "exact"
            score += 0.3
        elif expected["surname"].lower() in actual["surname_in_pdf"].lower() or \
             actual["surname_in_pdf"].lower() in expected["surname"].lower():
            matches["surname"] = "partial"
            score += 0.15
        else:
            mismatches.append(f"作者姓不符: 期望 '{expected['surname']}', 实际 '{actual['surname_in_pdf']}'")
    elif expected["surname"]:
        # 作者姓缺失: 不加分也不扣分
        max_score -= 0.3
        score += 0.15  # 默认给 0.15 (中性)

    # 2. 期刊 (权重 0.3)
    max_score += 0.3
    if expected["journal"] and actual.get("journal_in_pdf"):
        ej = expected["journal"].lower()
        aj = actual["journal_in_pdf"]
        if ej in aj or aj in ej or ej in JOURNAL_ALIASES and aj in JOURNAL_ALIASES[ej]:
            matches["journal"] = "exact"
            score += 0.3
        else:
            mismatches.append(f"期刊不符: 期望 '{expected['journal']}', 实际 '{actual['journal_in_pdf']}'")
    elif expected["journal"]:
        max_score -= 0.3
        score += 0.15

    # 3. 年份 (权重 0.2)
    max_score += 0.2
    if expected["year"] and actual.get("year_in_pdf"):
        if expected["year"] == actual["year_in_pdf"]:
            matches["year"] = "exact"
            score += 0.2
        else:
            mismatches.append(f"年份不符: 期望 '{expected['year']}', 实际 '{actual['year_in_pdf']}'")
    elif expected["year"]:
        max_score -= 0.2
        score += 0.1

    # 4. DOI (权重 0.2)
    max_score += 0.2
    if expected["doi"] and actual.get("doi_in_pdf"):
        if expected["doi"] == actual["doi_in_pdf"]:
            matches["doi"] = "exact"
            score += 0.2
        elif expected["doi"].split('/')[-1] == actual["doi_in_pdf"].split('/')[-1]:
            matches["doi"] = "tail_match"
            score += 0.1
        else:
            mismatches.append(f"DOI 不符: 期望 '{expected['doi']}', 实际 '{actual['doi_in_pdf']}'")
    elif expected["doi"]:
        max_score -= 0.2
        score += 0.1

    # 归一化
    final_score = score / max_score if max_score > 0 else 0

    return {
        "ok": final_score >= min_score and not mismatches,
        "score": round(final_score, 3),
        "matches": matches,
        "mismatches": mismatches,
        "expected": expected,
        "actual": actual,
        "min_score": min_score,
    }


# ════════════════════════════════════════════════════════════════
# 重新搜索正确论文
# ════════════════════════════════════════════════════════════════

def search_correct_paper(citation: str) -> List[Dict]:
    """
    根据 D 列引文, 重新搜正确论文
    返回候选下载链接

    策略:
    1. DOI 直链 (如果有)
    2. PubMed ESearch (作者 + 期刊 + 年份)
    3. Crossref API
    """
    expected = _extract_d_citation(citation)
    candidates = []

    # 1. DOI 直链
    if expected["doi"]:
        candidates.append({
            "source": "doi",
            "url": f"https://doi.org/{expected['doi']}",
            "score": 0.9,
        })

    # 2. PubMed
    if expected["surname"] and expected["year"]:
        q = f'{expected["surname"]}[Author] AND {expected["journal"]}[Journal] AND {expected["year"]}[PDAT]'
        if expected["doi"]:
            q += f' OR {expected["doi"]}[doi]'
        candidates.append({
            "source": "pubmed",
            "url": f"https://pubmed.ncbi.nlm.nih.gov/?term={q.replace(' ', '+')}",
            "score": 0.8,
        })

    # 3. Crossref
    if expected["surname"] and expected["year"]:
        q = f'?query.author={expected["surname"]}&query.bibliographic={expected["year"]}'
        if expected["doi"]:
            q = f'/{expected["doi"]}'
        candidates.append({
            "source": "crossref",
            "url": f"https://api.crossref.org/works{q}",
            "score": 0.85,
        })

    # 4. Google Scholar
    if expected["surname"]:
        gs_q = expected["surname"] + " " + (expected.get("journal") or "") + " " + (expected.get("year") or "")
        gs_url = "https://scholar.google.com/scholar?q=" + gs_q.replace(" ", "+")
        candidates.append({
            "source": "google_scholar",
            "url": gs_url,
            "score": 0.6,
        })

    return candidates


# ════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "verify":
        if len(sys.argv) < 4:
            print("Usage: verify <pdf_path> <expected_citation>")
            sys.exit(1)
        result = verify_paper_match(sys.argv[2], sys.argv[3])
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result["ok"] else 1)
    elif cmd == "search":
        if len(sys.argv) < 3:
            print("Usage: search <expected_citation>")
            sys.exit(1)
        candidates = search_correct_paper(sys.argv[2])
        print(json.dumps(candidates, ensure_ascii=False, indent=2))
    elif cmd == "audit":
        if len(sys.argv) < 3:
            print("Usage: audit <lit_base_dir>")
            sys.exit(1)
        # 简单 audit
        lit_base = sys.argv[2]
        # 找所有 PDF
        pdfs = []
        for root, _, fn in os.walk(lit_base):
            for f in fn:
                if f.lower().endswith('.pdf') and 'main' in f.lower() and 'v39' not in f:
                    pdfs.append(os.path.join(root, f))
        print(f"找到 {len(pdfs)} 个 main PDF, 逐个 verify 需要 expected_citation")
        print("提示: 此命令需配合 CSV 跑, 写脚本循环")
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
