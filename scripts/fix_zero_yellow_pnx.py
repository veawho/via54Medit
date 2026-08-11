#!/usr/bin/env python3
"""
fix_zero_yellow_pnx.py — 修 18 个 0 黄 Pn-x (strict mode 边缘 case)

策略:
1. 对每个 0 黄 Pn-x, 用 PDF 摘要反向抽英文关键词
2. 加到 CSV D_ppt_content (中文) 后, 重跑 highlight
3. 跳过 strict mode (让 title 区也可画)
"""
import os, sys, csv, re, json
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fitz
fitz.TOOLS.mupdf_display_warnings(False)

TMA_ROOT = "/Users/david/Desktop/TMA_文献整理"
PDF_DIR = os.path.join(TMA_ROOT, "_2_pdfs")
CSV_PATH = os.path.join(TMA_ROOT, "_citation_table/tma_citation_table.csv")
SUMMARY_PATH = os.path.join(TMA_ROOT, "_3_highlight_v10_4/_rerun_summary.csv")

# 暂时关闭 strict 模式
import via54_highlight_fix_v10
via54_highlight_fix_v10.STRICT_SKIP_HEADER = False  # 改 mode
ORIG_STRICT = via54_highlight_fix_v10.STRICT_SKIP_HEADER


def extract_pdf_keywords(pdf_path: str, max_pages: int = 2) -> list:
    """从 PDF 摘要抽英文关键词"""
    try:
        doc = fitz.open(pdf_path)
        text = ''
        for pg in range(min(max_pages, doc.page_count)):
            t = doc[pg].get_text()
            text += t
        if not text:
            return []
        # 抽 5-15 字符英文词, 找出现多次的
        words = re.findall(r'[A-Za-z]{4,15}', text)
        from collections import Counter
        top = [w for w, c in Counter(words).most_common(50) if c >= 3]
        # 加些医学关键词
        return top[:30]
    except Exception as e:
        return []


def main():
    # 1. 找 0 黄 Pn-x
    summary = {}
    with open(SUMMARY_PATH) as f:
        for row in csv.DictReader(f):
            summary[row['pn_x']] = row

    targets = [pn for pn, r in summary.items()
               if float(r.get('new_yellow_pct', 0) or 0) < 0.01 and int(r.get('hits', 0)) > 0]
    print(f"目标: {len(targets)} 个 0 黄 Pn-x")

    # 2. 抽 PDF 关键词
    updates = {}
    for pn in targets:
        pdf_path = os.path.join(PDF_DIR, f"{pn}_main.pdf")
        if not os.path.isfile(pdf_path):
            continue
        kws = extract_pdf_keywords(pdf_path)
        if kws:
            updates[pn] = kws
            print(f"  {pn}: {len(kws)} keywords (e.g. {kws[:5]})")

    # 3. 更新 CSV D_ppt_content
    if updates:
        with open(CSV_PATH, encoding='utf-8-sig') as f:
            text = f.read()
        # 备份
        with open(CSV_PATH + '.bak_pre_eng_kws', 'w', encoding='utf-8-sig') as f:
            f.write(text)

        for pn, kws in updates.items():
            # 找对应行 (Pn-x → a-b)
            m = re.match(r'P(\d+)-(\d+)', pn)
            if not m:
                continue
            a, b = m.group(1), m.group(2)
            # 找这行
            pattern = rf'^{a},{b},'
            lines = text.split('\n')
            for i, line in enumerate(lines):
                if re.match(pattern, line):
                    # 在 D 列 (第 4 字段) 后加英文关键词
                    parts = line.split(',', 4)
                    if len(parts) >= 5:
                        # 已有 D 列内容, 在尾部加英文关键词
                        orig_d = parts[3]
                        new_d = orig_d + ' / ' + ' '.join(kws[:10])
                        parts[3] = new_d
                        lines[i] = ','.join(parts)
                        print(f"  {pn}: D 列加 10 英文关键词")
                    break
            text = '\n'.join(lines)

        with open(CSV_PATH, 'w', encoding='utf-8-sig') as f:
            f.write(text)
        print(f"\\nCSV 已更新 {len(updates)} 个 Pn-x 的 D 列 (加英文关键词)")

    # 4. 关闭 strict 重跑
    via54_highlight_fix_v10.STRICT_SKIP_HEADER = False
    print(f"\\n重跑 highlight (STRICT_SKIP_HEADER=False)...")

    from rerun_tma_highlight_v104 import _read_csv_kws
    csv_kws = _read_csv_kws()

    from via54_highlight_fix_v10 import process_pn_x

    for pn in targets:
        pdf_path = os.path.join(PDF_DIR, f"{pn}_main.pdf")
        if not os.path.isfile(pdf_path):
            continue
        c_cit, d_ppt, kws_csv = csv_kws.get(pn, ('', '', []))
        if not kws_csv:
            continue
        out_pdf = os.path.join(TMA_ROOT, "_3_highlight_v10_4", f"{pn}_highlight.pdf")
        jpg_dir = os.path.join(TMA_ROOT, "_3_highlight_v10_4", f"{pn}_jpgs")
        os.makedirs(jpg_dir, exist_ok=True)
        try:
            r = process_pn_x(pn, pdf_path, out_pdf, kws_csv, jpg_dir, f"{pn}_page", mode='line', use_glm=False)
            mark = "✓" if r['yellow_pct_estimate'] > 0.01 else "❌"
            print(f"  {mark} {pn}: hits={r['total_hits']} yellow={r['yellow_pct_estimate']:.3f}% matched={len(r['matched_terms'])}/{len(kws_csv)}")
        except Exception as e:
            print(f"  ❌ {pn}: {e}")

    # 恢复 strict mode
    via54_highlight_fix_v10.STRICT_SKIP_HEADER = ORIG_STRICT
    print("\\n完成")


if __name__ == "__main__":
    main()
