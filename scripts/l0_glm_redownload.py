#!/usr/bin/env python3
"""
l0_glm_redownload.py — L0 GLM 兜底补搜正确论文

对 v10.1 highlight fail 的 Pn-x, 用 l0 paper match + GLM 知识库
找出正确论文, 输出补搜建议.

不做: 自动重下载 (那需要 PDF 链接, GLM 只能给方向)

输入: rerun summary CSV
输出: redownload_suggestions.json
"""
import os, sys, csv, json, re
from pathlib import Path
from typing import Dict, List, Optional

# 让 l0_paper_match 可 import
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)

# 现有 GLM 集成
from glm_integration import _get_client, _call_glm, DEFAULT_MODEL

# 16 个 fail 案例 (从 rerun summary 抽)
TMA_FAIL_PN_X = [
    "P12-1", "P13-1", "P14-3", "P23-22", "P23-26", "P23-3",
    "P23-6", "P24-1", "P25-5", "P25-7", "P28-2", "P28-3",
    "P30-3", "P5-1", "P8-2",
]
LEIDA_FAIL_PN_X = ["P40-10"]


def _get_fail_rows(csv_path: str) -> List[Dict]:
    """从 rerun summary CSV 抽 fail 案例 (ok=False 或 hits=0)"""
    if not os.path.isfile(csv_path):
        return []
    with open(csv_path) as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if r.get('ok') == 'False' or int(r.get('hits', 0) or 0) == 0]


def _get_csv_rows(csv_path: str) -> Dict[str, Dict]:
    """读 TMA 4 列 CSV, 返回 {Pn-x: row}"""
    if not os.path.isfile(csv_path):
        return {}
    with open(csv_path, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    idx = {}
    for r in rows:
        a = r.get('A_slide', '').strip()
        b = r.get('B_mark', '').strip()
        if a and b:
            idx[f"P{a}-{b}"] = r
    return idx


# ════════════════════════════════════════════════════════════════
# GLM 找正确论文
# ════════════════════════════════════════════════════════════════

REDOWNLOAD_PROMPT = """# 任务
你是医学文献检索专家。给定 D 列引文 + 视觉分析 (PPT 想引用的内容),
找出最可能的正确论文, 包括:
  1. 完整作者列表
  2. 完整期刊
  3. 准确年份 + 卷期页
  4. DOI (如有)
  5. 已知全文 PDF URL (e.g., PMC, Frontiers, MDPI, Europe PMC)

# D 列引文 (期望论文)
{citation}

# D 列视觉分析 (应证段上下文)
{visual}

# 当前下载的 PDF (可能错)
当前 PDF 第一作者: {actual_surname}
当前 PDF 期刊: {actual_journal}
当前 PDF 年份: {actual_year}

# 输出 (严格 JSON)
{{
  "correct_citation": {{
    "authors": "完整作者 (Last FM 格式)",
    "journal": "期刊全称",
    "year": 4-digit year,
    "volume": "卷",
    "issue": "期",
    "pages": "起-止",
    "doi": "DOI or null",
    "pmid": "PMID or null"
  }},
  "search_queries": [
    "PubMed 搜索词 1 (含作者+期刊+年)",
    "PubMed 搜索词 2 (含 DOI)",
    "Google Scholar 搜索词"
  ],
  "pdf_urls": [
    "可能 PDF URL 1 (PMC/Frontiers/MDPI 等 OA)",
    "可能 PDF URL 2"
  ],
  "title_keywords": ["标题关键词 1-3 (用于二次确认)"],
  "reason_zh": "为什么当前 PDF 错 + 正确论文应该是 (中文 1-2 句)",
  "confidence": 0.0-1.0
}}"""


def redownload_suggest(
    citation: str,
    visual: str,
    actual_surname: str = "",
    actual_journal: str = "",
    actual_year: str = "",
    use_glm: bool = True,
) -> Optional[Dict]:
    """
    GLM 找正确论文, 返回补搜建议
    """
    if not use_glm:
        return None
    try:
        client = _get_client()
    except Exception:
        return None

    prompt = REDOWNLOAD_PROMPT.format(
        citation=citation[:500],
        visual=visual[:500] or "(无)",
        actual_surname=actual_surname or "(未知)",
        actual_journal=actual_journal or "(未知)",
        actual_year=actual_year or "(未知)",
    )
    response = _call_glm(client, DEFAULT_MODEL, prompt, max_retries=2)
    if not response:
        return None

    try:
        m = re.search(r'\{[\s\S]*\}', response)
        if not m:
            return None
        data = json.loads(m.group(0))
        return data
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════════════════════════

PROJECTS = {
    "TMA": {
        "rerun_csv": "/Users/david/Desktop/TMA_文献整理/_3_highlight_v10_glm/_rerun_summary.csv",
        "source_csv": "/Users/david/Desktop/TMA_文献整理/_citation_table/tma_citation_table.csv",
        "pdf_dir": "/Users/david/Desktop/TMA_文献整理/_2_pdfs",
        "highlight_dir": "/Users/david/Desktop/TMA_文献整理/_3_highlight_v10_glm",
    },
    "雷管方案": {
        "rerun_csv": "/Users/david/Desktop/雷管方案_文献整理/step4_highlight_v10_glm/_rerun_summary.csv",
        "source_csv": "/Users/david/Desktop/雷管方案_文献整理/step2_标注分析/PPT_citations_8col_aligned.csv",
        "pdf_dir": "/Users/david/Desktop/雷管方案_文献整理/step3_pdf下载_160目录",
        "highlight_dir": "/Users/david/Desktop/雷管方案_文献整理/step4_highlight_v10_glm",
    },
}


def process_project(name: str, cfg: dict, use_glm: bool = True) -> Dict:
    """处理一个项目的 fail 案例, 输出补搜建议"""
    print(f"\n=== {name} ===")
    rerun_csv = cfg["rerun_csv"]
    source_csv = cfg["source_csv"]

    fail_rows = _get_fail_rows(rerun_csv)
    print(f"  Fail 案例: {len(fail_rows)}")

    if not fail_rows:
        print(f"  无 fail, 跳过")
        return {"project": name, "n_fail": 0, "suggestions": []}

    csv_idx = _get_csv_rows(source_csv)

    suggestions = []
    for r in fail_rows:
        pn = r["pn_x"]
        hits = int(r.get("hits", 0) or 0)
        print(f"  [{len(suggestions)+1}/{len(fail_rows)}] {pn}: hits={hits} ...", end="", flush=True)

        # 从 source CSV 找 citation
        csv_row = csv_idx.get(pn, {})
        c_cit = csv_row.get("C_citation", "") or csv_row.get("c_citation", "")
        d_vis = (csv_row.get("D_ppt_content", "") or
                 csv_row.get("D_visual_text_analysis", "") or
                 csv_row.get("D_ppt_visual", ""))

        # 从 actual PDF 抽 (拿首页作者/期刊/年)
        actual_surname = ""
        actual_journal = ""
        actual_year = ""
        # 找 PDF 路径
        pdf_dir = cfg["pdf_dir"]
        for cand in [
            os.path.join(pdf_dir, pn, f"{pn}_main.pdf"),
            os.path.join(pdf_dir, f"{pn}_main.pdf"),
            os.path.join(pdf_dir, pn, "main.pdf"),
        ]:
            if os.path.isfile(cand):
                try:
                    import fitz
                    doc = fitz.open(cand)
                    if len(doc) > 0:
                        t = doc[0].get_text()
                        m = re.search(r'([A-Z][a-zA-Z\-]+)\s+[A-Z][a-z]+', t)
                        if m:
                            actual_surname = m.group(1)
                        m = re.search(r'\b(20\d{2})\b', t)
                        if m:
                            actual_year = m.group(0)
                    doc.close()
                except Exception:
                    pass
                break

        suggest = redownload_suggest(
            citation=c_cit,
            visual=d_vis,
            actual_surname=actual_surname,
            actual_journal=actual_journal,
            actual_year=actual_year,
            use_glm=use_glm,
        )
        if suggest:
            suggestions.append({
                "pn_x": pn,
                "expected_citation": c_cit[:200],
                "expected_visual": d_vis[:200],
                "actual_surname": actual_surname,
                "actual_year": actual_year,
                "suggestion": suggest,
            })
            corr = suggest.get("correct_citation", {})
            doi = corr.get("doi", "no_doi")
            urls = suggest.get("pdf_urls", [])
            conf = suggest.get("confidence", 0)
            print(f" GLM conf={conf:.2f}  doi={doi or '?'}  urls={len(urls)}")
        else:
            print(" GLM 失败")
            suggestions.append({
                "pn_x": pn,
                "expected_citation": c_cit[:200],
                "suggestion": None,
            })

    # 输出
    out_path = os.path.join(cfg["highlight_dir"], "_redownload_suggestions.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "project": name,
            "n_fail": len(fail_rows),
            "n_suggestions": len([s for s in suggestions if s.get("suggestion")]),
            "suggestions": suggestions,
        }, f, ensure_ascii=False, indent=2)
    print(f"  ✓ 报告: {out_path}")

    return {
        "project": name,
        "n_fail": len(fail_rows),
        "n_suggestions": len([s for s in suggestions if s.get("suggestion")]),
        "out_path": out_path,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", choices=list(PROJECTS.keys()) + ["all"], default="all")
    parser.add_argument("--no-glm", action="store_true")
    args = parser.parse_args()

    targets = list(PROJECTS.keys()) if args.project == "all" else [args.project]
    results = []
    for name in targets:
        r = process_project(name, PROJECTS[name], use_glm=not args.no_glm)
        results.append(r)

    # 总览
    print(f"\n=== 汇总 ===")
    for r in results:
        print(f"  {r.get('project', '?')}: {r.get('n_suggestions', 0)}/{r.get('n_fail', 0)} fail 有 GLM 建议")

    if args.no_glm:
        sys.exit(0)
    sys.exit(0 if all(r.get("n_suggestions", 0) == r.get("n_fail", 0) for r in results) else 1)


if __name__ == "__main__":
    main()
