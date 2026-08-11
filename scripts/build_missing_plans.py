#!/usr/bin/env python3
"""
build_missing_plans.py — 给无 vision plan 的 Pn-x 自动建 plan (2026-08-11)

读 citation_table (A_slide/B_mark/C_citation/D_ppt_content), 对每个 Pn-x:
1. 抽 slide / mark / citation / ppt_content
2. 用 L4 抽 keyword (基于 ppt_content)
3. 用 PDF 摘要反向抽英文 keyword (基于 PDF first 2 pages)
4. 合并 keyword (cap 30)
5. 写 plan entry 到 _highlight_plans.json (合并到现有 plans)

用法:
    python3 build_missing_plans.py --project TMA
"""
import os, sys, json, csv, argparse
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


TMA_ROOT = "/Users/david/Desktop/TMA_文献整理"
LEIDA_ROOT = "/Users/david/Desktop/雷管方案_文献整理"


def find_ppt_render(project_root: str, slide_num: int) -> Optional[str]:
    """找 PPT slide 渲染图 (多个候选)"""
    candidates = [
        os.path.join(project_root, "_1_ppt/_3_images", f"slide_pp_{slide_num:03d}.jpg"),
        os.path.join(project_root, "_1_ppt/_3_images", f"slide_{slide_num:03d}.jpg"),
        os.path.join(project_root, "step1_ppt_目录/_ppt_renders_expanded", f"slide_{slide_num:03d}.jpg"),
        os.path.join(project_root, "step1_ppt_目录/_ppt_renders", f"slide_{slide_num:03d}.jpg"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def find_pdf(project_root: str, pn_x: str) -> Optional[str]:
    """找 Pn-x 的 main PDF (flat + nested)"""
    for d in [os.path.join(project_root, "_2_pdfs"),
              os.path.join(project_root, "step3_pdf下载_160目录")]:
        flat = os.path.join(d, f"{pn_x}_main.pdf")
        if os.path.isfile(flat):
            return flat
        nested = os.path.join(d, pn_x, f"{pn_x}_main.pdf")
        if os.path.isfile(nested):
            return nested
    return None


def read_pdf_abstract(pdf_path: str, max_pages: int = 2, max_chars: int = 3000) -> str:
    """读 PDF 前 N 页作为摘要"""
    import fitz
    fitz.TOOLS.mupdf_display_warnings(False)
    doc = fitz.open(pdf_path)
    text = ""
    for p in range(min(max_pages, doc.page_count)):
        text += doc[p].get_text() + "\n"
        if len(text) > max_chars:
            break
    doc.close()
    return text[:max_chars]


def extract_keywords_from_text(text: str, max_keywords: int = 15) -> List[str]:
    """从文本抽 medical keywords (简单版, 不调 GLM)"""
    import re
    if not text:
        return []

    # 1. 抽 2-4 字大写开头的英文术语 (TMA, aHUS, eculizumab 等)
    # 2. 抽中文 2-6 字关键词
    en_terms = set()
    # 大写缩写 (2-6 chars)
    for m in re.finditer(r'\b[A-Z][A-Z0-9]{1,5}\b', text):
        t = m.group(0)
        if t not in {'THE', 'AND', 'FOR', 'WITH', 'THIS', 'THAT', 'FROM', 'WERE', 'WAS', 'ARE', 'HAD'}:
            en_terms.add(t)
    # 标题式词 (大小写混合 4+ chars)
    for m in re.finditer(r'\b[A-Z][a-z]{3,}\b', text):
        t = m.group(0)
        if t.lower() not in {'this', 'that', 'with', 'from', 'were', 'have', 'been', 'they', 'these', 'those', 'which', 'their', 'where', 'there', 'would', 'could', 'should', 'about', 'into', 'than', 'after', 'before', 'because', 'while', 'during', 'through', 'where', 'such', 'some', 'each', 'using'}:
            en_terms.add(t)

    # 中文 2-6 字
    zh_terms = set()
    for m in re.finditer(r'[\u4e00-\u9fff]{2,6}', text):
        t = m.group(0)
        if t not in {'这些', '那些', '这个', '那个', '我们', '你们', '他们', '以及', '可以', '通过', '由于', '因此', '因为', '如果', '或者', '并且', '但是', '然而', '虽然', '不过', '其他', '其中', '有关', '一些', '一种', '这个', '那个', '进行', '使用', '研究', '患者', '治疗', '临床', '分析', '显示', '结果', '方法', '讨论', '结论', '目的', '意义', '情况', '条件', '情况', '主要', '重要', '明显', '严重', '正常', '存在', '发生', '发现', '应用', '包括', '以及', '具有', '作用', '影响', '不同', '相同', '部分', '全部', '主要', '目前', '已经', '可以', '可能', '应该', '需要', '使用', '进行', '采用', '具有', '包括', '存在', '情况', '研究', '分析', '显示', '结果', '方法'}:
            zh_terms.add(t)

    # 合并, 英文优先 (cap max_keywords)
    keywords = list(en_terms)[:max_keywords]
    if len(keywords) < max_keywords:
        keywords.extend(list(zh_terms)[:max_keywords - len(keywords)])

    return keywords[:max_keywords]


def build_plan_from_citation(project_root: str, row: Dict) -> Optional[Dict]:
    """从 citation_table 一行建 plan"""
    pn_x = row.get('B_pn_x', '').strip()
    if not pn_x:
        return None

    try:
        slide = int(row.get('A_slide', 0) or 0)
    except (ValueError, TypeError):
        slide = 0
    try:
        mark = int(row.get('B_mark', 1) or 1)
    except (ValueError, TypeError):
        mark = 1
    citation = row.get('C_citation', '').strip()
    ppt_content = row.get('D_ppt_content', '').strip()

    pdf = find_pdf(project_root, pn_x)
    if not pdf:
        return None
    ppt_render = find_ppt_render(project_root, slide) if slide > 0 else None

    # 抽 keyword: 中文从 ppt_content + 英文从 PDF 摘要
    zh_keywords = extract_keywords_from_text(ppt_content, max_keywords=15)
    en_text = read_pdf_abstract(pdf, max_pages=2, max_chars=3000) if pdf else ""
    en_keywords = extract_keywords_from_text(en_text, max_keywords=15)

    # 合并去重, cap 30
    all_kw = list(dict.fromkeys(zh_keywords + en_keywords))[:30]

    return {
        'pn_x': pn_x,
        'slide': slide,
        'mark': mark,
        'citation': citation,
        'ppt_content': ppt_content,
        'pdf_path': pdf,
        'ppt_render': ppt_render,
        'target_text': ppt_content[:200] if ppt_content else citation[:200],
        'data_points': [],
        'keywords': all_kw,
        'auto_built': True,  # 标记自动建
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', choices=['TMA', '雷管方案'], default='TMA')
    parser.add_argument('--citation-table', default='')
    parser.add_argument('--plans-out', default='')
    parser.add_argument('--no-merge', action='store_true', help='不合并到现有 plans.json')
    args = parser.parse_args()

    project_root = TMA_ROOT if args.project == 'TMA' else LEIDA_ROOT
    citation_csv = args.citation_table or os.path.join(project_root, '_citation_table', f'{args.project.lower().replace("方案","")}_citation_table.csv')
    if not os.path.isfile(citation_csv):
        # fallback
        for cand in [os.path.join(project_root, '_citation_table', 'tma_citation_table.csv'),
                     os.path.join(project_root, '_citation_table', 'leida_citation_table.csv')]:
            if os.path.isfile(cand):
                citation_csv = cand; break

    plans_path = args.plans_out or os.path.join(project_root, '_3_highlight_vision', '_highlight_plans.json')

    # 读现有 plans
    existing = {}
    if not args.no_merge and os.path.isfile(plans_path):
        d = json.load(open(plans_path))
        existing = {p['pn_x']: p for p in d['plans']}
        print(f'Existing plans: {len(existing)}')

    # 读 citation table
    new_count = 0
    with open(citation_csv, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            pn_x = row.get('B_pn_x', '').strip()
            if not pn_x or pn_x in existing:
                continue
            plan = build_plan_from_citation(project_root, row)
            if plan:
                existing[pn_x] = plan
                new_count += 1
                print(f'  + {pn_x} slide={plan["slide"]} kw={len(plan["keywords"])}')

    # 写回
    out = {'plans': list(existing.values())}
    if not args.no_merge:
        os.makedirs(os.path.dirname(plans_path), exist_ok=True)
        json.dump(out, open(plans_path, 'w'), ensure_ascii=False, indent=2)
        print(f'\n→ Written {len(existing)} plans to {plans_path} (+{new_count} new)')
    else:
        # 写到 tmp 供检查
        out_path = f'/tmp/_built_plans_{args.project}.json'
        json.dump(out, open(out_path, 'w'), ensure_ascii=False, indent=2)
        print(f'\n→ {new_count} new plans written to {out_path}')


if __name__ == '__main__':
    main()
