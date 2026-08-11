#!/usr/bin/env python3
"""
build_missing_plans.py v2 — 给无 vision plan 的 Pn-x 自动建 plan (2026-08-11)

从 _2_pdfs/ 读 PDF filename 抽 Pn-x, 对每个无 plan 的 Pn-x:
1. 找 PDF
2. 找对应 PPT slide render (从 citation_table 抽 slide, 或用 Pn-x 数字 fallback)
3. 用 L4 抽 keyword (基于 PDF 摘要反向)
4. target_text 用 PPT 内容 (从 citation_table 抽) 或 generic ("找讲 [PDF 主题] 的段落")
5. 写 plan entry

用法:
    python3 build_missing_plans.py --project TMA [--auto-slide]
"""
import os, sys, json, csv, argparse, re
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


TMA_ROOT = "/Users/david/Desktop/TMA_文献整理"
LEIDA_ROOT = "/Users/david/Desktop/雷管方案_文献整理"


def find_pdf(project_root: str, pn_x: str) -> Optional[str]:
    for d in [os.path.join(project_root, "_2_pdfs"),
              os.path.join(project_root, "step3_pdf下载_160目录")]:
        flat = os.path.join(d, f"{pn_x}_main.pdf")
        if os.path.isfile(flat):
            return flat
        nested = os.path.join(d, pn_x, f"{pn_x}_main.pdf")
        if os.path.isfile(nested):
            return nested
    return None


def find_ppt_render(project_root: str, slide_num: int) -> Optional[str]:
    if slide_num <= 0:
        return None
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


def read_pdf_abstract(pdf_path: str, max_pages: int = 2, max_chars: int = 3000) -> str:
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


def extract_keywords_l4(pdf_path: str) -> List[str]:
    """用 L4 从 PDF 摘要抽英文 keyword (TMA 4 轮验证)"""
    try:
        from vision_stage3_keyword_boost import _extract_keywords_from_pdf
        return _extract_keywords_from_pdf(pdf_path)
    except Exception as e:
        print(f"  ⚠ L4 err: {e}")
        return []


def build_plan_from_pdf(pdf_path: str, citation_match: Optional[Dict] = None) -> Dict:
    """从 PDF + 可选 citation 抽 plan"""
    pn_x = os.path.basename(pdf_path).replace('_main.pdf', '')

    # 从 citation_match 抽 (slide / mark / target_text)
    slide = 0
    mark = 1
    target_text = ""
    if citation_match:
        slide = citation_match.get('slide', 0)
        mark = citation_match.get('mark', 1)
        target_text = citation_match.get('target_text', '') or ""

    # fallback: 从 Pn-x 数字抽 slide (P11-1 → 11, P23-6 → 23, P5-1 → 5)
    if slide == 0:
        m = re.match(r'P(\d+)-', pn_x)
        if m:
            slide = int(m.group(1))

    # 抽 PDF 摘要反向 keyword
    pdf_kw = extract_keywords_l4(pdf_path)

    # 抽 abstract 用作 fallback target_text
    abstract = read_pdf_abstract(pdf_path, max_pages=2, max_chars=2000)

    # 如果没 target_text, 用 PDF 摘要前 200 字
    if not target_text:
        target_text = abstract[:200].replace('\n', ' ').strip()

    return {
        'pn_x': pn_x,
        'slide': slide,
        'mark': mark,
        'citation': citation_match.get('citation', '') if citation_match else '',
        'ppt_content': target_text,
        'pdf_path': pdf_path,
        'ppt_render': find_ppt_render_from(pdf_path, slide),
        'target_text': target_text,
        'data_points': [],
        'keywords': pdf_kw[:30],
        'auto_built': True,
    }


def find_ppt_render_from(pdf_path: str, slide: int) -> Optional[str]:
    """从 PDF 路径推 project_root, 再找 PPT render"""
    if slide <= 0:
        return None
    # 找项目根
    cur = os.path.dirname(pdf_path)
    while cur and cur != '/':
        if os.path.basename(cur) == 'TMA_文献整理' or os.path.basename(cur) == '雷管方案_文献整理':
            return find_ppt_render(cur, slide)
        cur = os.path.dirname(cur)
    return None


def load_citation_table(project_root: str) -> Dict[str, Dict]:
    """读 citation_table.csv → {pn_x: {slide, mark, citation, target_text}}"""
    csv_path = os.path.join(project_root, '_citation_table', 'tma_citation_table.csv')
    if not os.path.isfile(csv_path):
        return {}
    result = {}
    try:
        with open(csv_path, encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            # 找 Pn-x 列
            for row in reader:
                # 当前格式: A_slide, B_mark, C_citation, D_ppt_content
                # 但 Pn-x 在 PDF filename, citation 匹配靠作者
                slide = int(row.get('A_slide', 0) or 0)
                mark = int(row.get('B_mark', 1) or 1)
                citation = row.get('C_citation', '').strip()
                content = row.get('D_ppt_content', '').strip()
                # citation 里有作者+年, 用作 key
                if citation:
                    result[citation[:60]] = {
                        'slide': slide,
                        'mark': mark,
                        'citation': citation,
                        'target_text': content,
                    }
    except Exception as e:
        print(f"  ⚠ citation table err: {e}")
    return result


def match_citation_to_pdf(pdf_path: str, citation_dict: Dict[str, Dict]) -> Optional[Dict]:
    """从 PDF 摘要抽第一作者+年, 匹配 citation_table"""
    abstract = read_pdf_abstract(pdf_path, max_pages=1, max_chars=500)
    if not abstract:
        return None
    # 抽第一作者姓 (大写 letter 开头 4+ chars)
    m = re.search(r'\b([A-Z][a-z]{2,})\s+[A-Z]{1,3}', abstract)
    if not m:
        return None
    author = m.group(1)
    # 在 citation_dict 找含 author
    for cite, info in citation_dict.items():
        if author in cite:
            return info
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', choices=['TMA', '雷管方案'], default='TMA')
    parser.add_argument('--plans-out', default='')
    args = parser.parse_args()

    project_root = TMA_ROOT if args.project == 'TMA' else LEIDA_ROOT
    plans_path = args.plans_out or os.path.join(project_root, '_3_highlight_vision', '_highlight_plans.json')

    # 读现有 plans
    existing = {}
    if os.path.isfile(plans_path):
        d = json.load(open(plans_path))
        existing = {p['pn_x']: p for p in d['plans']}
        print(f'Existing plans: {len(existing)}')

    # 读 citation_table
    citation_dict = load_citation_table(project_root)
    print(f'Citation table entries: {len(citation_dict)}')

    # 列所有 PDF
    pdf_dir = os.path.join(project_root, '_2_pdfs')
    if not os.path.isdir(pdf_dir):
        pdf_dir = os.path.join(project_root, 'step3_pdf下载_160目录')
    pdfs = sorted([f for f in os.listdir(pdf_dir) if f.endswith('.main.pdf') or f.endswith('_main.pdf')])
    print(f'Total PDFs: {len(pdfs)}')

    # 找无 plan 的
    all_pn_x = [f.replace('_main.pdf', '').replace('.main.pdf', '') for f in pdfs]
    no_plan = [pn for pn in all_pn_x if pn not in existing]
    print(f'No plan: {len(no_plan)}')

    # 给每个无 plan 建
    new_count = 0
    for pn_x in no_plan:
        pdf = os.path.join(pdf_dir, f'{pn_x}_main.pdf')
        if not os.path.isfile(pdf):
            # try alternate
            for f in pdfs:
                if f.startswith(pn_x):
                    pdf = os.path.join(pdf_dir, f)
                    break
        if not os.path.isfile(pdf):
            print(f'  - {pn_x}: no pdf')
            continue

        # 尝试匹配 citation
        citation_match = match_citation_to_pdf(pdf, citation_dict)
        plan = build_plan_from_pdf(pdf, citation_match)
        plan['pn_x'] = pn_x
        existing[pn_x] = plan
        new_count += 1
        if new_count <= 5:
            print(f'  + {pn_x}: slide={plan["slide"]} kw={len(plan["keywords"])} target={plan["target_text"][:60]!r}')

    print(f'Built {new_count} new plans')

    # 写回
    out = {'plans': list(existing.values())}
    os.makedirs(os.path.dirname(plans_path), exist_ok=True)
    json.dump(out, open(plans_path, 'w'), ensure_ascii=False, indent=2)
    print(f'\n→ Written {len(existing)} plans to {plans_path}')


if __name__ == '__main__':
    main()
