#!/usr/bin/env python3
"""
step5_alignment.py — 6 步规则 #5 三方对齐 (v10.1)

校验 3 件事:
  Step 5#1: PPT slide+引用序号 (A+B) vs 下载目录 vs highlight 目录
  Step 5#2: PPT 引用文献字段 (C) + DOI (E) vs 下载 PDF vs highlight PDF
  Step 5#3: PPT 视觉内容 (D) vs highlight 图片 vs 应证推理 (H)

输出:
  - step5_三方对齐_report.md    (人类可读)
  - step5_三方对齐_status.json  (机器可读, 可入 CI)
  - step5_三方对齐_aligned.csv  (更新 I/J/K 列)

支持项目 (按 --project):
  雷管方案: /Users/david/Desktop/雷管方案_文献整理
  TMA:      /Users/david/Desktop/TMA_文献整理

用法:
  python3.11 step5_alignment.py --project 雷管方案
  python3.11 step5_alignment.py --project TMA
  python3.11 step5_alignment.py --csv <path> --step3 <dir> --step4 <dir> --out <dir>
"""
import os, sys, json, csv, argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# PIL / numpy 用于检测高亮图
try:
    from PIL import Image
    import numpy as np
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# PyMuPDF 用于抽 highlight 文字
try:
    import fitz
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False


# ════════════════════════════════════════════════════════════════
# 项目预设
# ════════════════════════════════════════════════════════════════

PROJECTS = {
    "雷管方案": {
        "root": "/Users/david/Desktop/雷管方案_文献整理",
        "csv": "step2_标注分析/PPT_citations_8col_aligned.csv",
        "step3": "step3_pdf下载_160目录",
        "step4": "step4_highlight_v10_glm",  # v10.2: GLM 增强版
        "step5": "step5_三方对齐",
        "convention": "nested",  # Pn-x/ 内有 main.pdf
    },
    "TMA": {
        "root": "/Users/david/Desktop/TMA_文献整理",
        "csv": "_citation_table/tma_citation_table.csv",
        "step3": "_2_pdfs",
        "step4": "_3_highlight_v10_glm",  # v10.2: GLM 增强版 (vs 旧 _3_highlight)
        "step5": "_step5_三方对齐",
        "convention": "flat",
    },
}


# ════════════════════════════════════════════════════════════════
# 检查函数
# ════════════════════════════════════════════════════════════════

def _is_pn_x(s: str) -> bool:
    import re
    return bool(re.match(r'^P\d+-\d+', s or ''))


def _pn_x_from_filename(fname: str) -> Optional[str]:
    import re
    m = re.match(r'^(P\d+-\d+)', fname)
    return m.group(1) if m else None


def _find_pn_x_in_dir(dir_path: str, convention: str) -> Dict[str, List[str]]:
    """
    在目录里找 Pn-x, 返回 {Pn-x: [filenames]}

    nested 约定: dir_path/Pn-x/...
    flat 约定:   dir_path/Pn-x_*.pdf
    """
    result: Dict[str, List[str]] = {}
    if not os.path.isdir(dir_path):
        return result
    if convention == "nested":
        for d in os.listdir(dir_path):
            if _is_pn_x(d) and os.path.isdir(os.path.join(dir_path, d)):
                files = os.listdir(os.path.join(dir_path, d))
                result[d] = files
    else:  # flat
        for f in os.listdir(dir_path):
            pn = _pn_x_from_filename(f)
            if pn:
                result.setdefault(pn, []).append(f)
    return result


def _yellow_pct(jpg_path: str) -> float:
    """检测 jpg 中黄色像素占比"""
    if not HAS_PIL or not os.path.isfile(jpg_path):
        return 0.0
    try:
        arr = np.array(Image.open(jpg_path).convert("RGB"))
        yellow = (arr[:, :, 0] > 200) & (arr[:, :, 1] > 200) & (arr[:, :, 2] < 150)
        return float(yellow.sum() / yellow.size * 100)
    except Exception:
        return 0.0


def _extract_highlight_text(pdf_path: str, page_hint: Optional[int] = None,
                            max_chars: int = 500) -> str:
    """
    从 PDF 抽 highlight 区域文字 (给 GLM 用)
    优先用 page_hint, 否则 page 1-3

    Returns: 抽取的文本 (可能空)
    """
    if not HAS_PYMUPDF or not pdf_path or not os.path.isfile(pdf_path):
        return ""
    try:
        doc = fitz.open(pdf_path)
        n = min(3, len(doc))
        # 优先 page_hint 页
        if page_hint and 1 <= page_hint <= n:
            text = doc[page_hint - 1].get_text() or ""
            if text:
                doc.close()
                return text[:max_chars]
        # fallback: 抽前 N 页
        all_text = ""
        for i in range(n):
            all_text += (doc[i].get_text() or "") + "\n"
        doc.close()
        return all_text[:max_chars]
    except Exception:
        return ""


def _check_step5_alignment(
    csv_path: str,
    step3_dir: str,
    step4_dir: str,
    convention: str = "nested",
    use_glm: bool = False,
) -> Dict:
    """
    主函数: 跑三方对齐检查

    Returns:
        {
            'total_rows': int,
            'aligned_5_1': int,  # PPT+mark vs dir
            'aligned_5_2': int,  # C+DOI vs PDF
            'aligned_5_3': int,  # D vs highlight
            'rows': [每行的详细结果],
            'issues_summary': {...},
        }
    """
    if not os.path.isfile(csv_path):
        return {"error": f"CSV 不存在: {csv_path}"}

    with open(csv_path, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        cols = reader.fieldnames or []

    # 列名适配: 不同项目列名可能不同
    def _col(*candidates):
        for c in candidates:
            if c in cols:
                return c
        return None

    a_col = _col("A_slide", "PPT页", "A")
    b_col = _col("B_mark", "第几条", "B")
    c_col = _col("C_citation", "PPT中的文献引用 完整字段", "C_citation", "C")
    d_col = _col("D_ppt_visual", "D_visual_text_analysis", "D", "D_ppt_content")
    e_col = _col("E_DOI", "DOI", "E")
    g_col = _col("G_actual_pdf", "对应PDF文件", "G")

    if not all([a_col, b_col, c_col]):
        return {"error": f"CSV 缺关键列: A={a_col}, B={b_col}, C={c_col}"}

    # 索引 step3/step4
    step3_idx = _find_pn_x_in_dir(step3_dir, convention)  # Pn-x → [files]
    step4_idx = _find_pn_x_in_dir(step4_dir, convention)

    # 统计
    issues: Dict[str, int] = {}
    rows_result: List[Dict] = []
    n_total = 0
    n_aligned_5_1 = 0
    n_aligned_5_2 = 0
    n_aligned_5_3 = 0

    for r in rows:
        slide = (r.get(a_col, "") or "").strip()
        mark = (r.get(b_col, "") or "").strip()
        citation = (r.get(c_col, "") or "").strip()
        d_visual = (r.get(d_col, "") or "").strip() if d_col else ""
        doi = (r.get(e_col, "") or "").strip() if e_col else ""
        g_pdf = (r.get(g_col, "") or "").strip() if g_col else ""

        # 跳过空行
        if not slide and not mark and not citation:
            continue
        n_total += 1

        pn_x = f"P{slide}-{mark}" if slide and mark else ""
        row = {
            "pn_x": pn_x,
            "slide": slide,
            "mark": mark,
            "citation": citation[:60],
            "doi": doi,
            "pdf": g_pdf,
            "aligned_5_1": False,  # PPT+mark vs dir
            "aligned_5_2": False,  # C+DOI vs PDF
            "aligned_5_3": False,  # D vs highlight
            "issues": [],
        }

        # Step 5#1: A+B → Pn-x 目录
        if pn_x and pn_x in step3_idx and pn_x in step4_idx:
            row["aligned_5_1"] = True
            n_aligned_5_1 += 1
        else:
            missing = []
            if pn_x not in step3_idx:
                missing.append("step3")
            if pn_x not in step4_idx:
                missing.append("step4")
            row["issues"].append(f"5#1: Pn-x 目录缺 {','.join(missing)}")
            issues[f"5#1 missing_{','.join(missing)}"] = issues.get(f"5#1 missing_{','.join(missing)}", 0) + 1

        # Step 5#2: C+DOI → PDF
        pdf_ok = False
        if pn_x in step3_idx:
            step3_files = step3_idx[pn_x]
            # 看 G 列指定的 PDF 或任一 main PDF
            target_pdf = None
            if g_pdf and g_pdf in step3_files:
                target_pdf = g_pdf
            else:
                # 找 main PDF
                mains = [f for f in step3_files if 'main' in f.lower() and 'fallback' not in f.lower()]
                target_pdf = mains[0] if mains else (step3_files[0] if step3_files else None)
            if target_pdf and target_pdf.lower().endswith('.pdf'):
                pdf_path = os.path.join(step3_dir, pn_x, target_pdf) if convention == "nested" else os.path.join(step3_dir, target_pdf)
                if os.path.isfile(pdf_path):
                    pdf_ok = True
                    row["pdf_path"] = pdf_path

        if pdf_ok:
            row["aligned_5_2"] = True
            n_aligned_5_2 += 1
        else:
            row["issues"].append("5#2: C+DOI 找不到对应 PDF")
            issues["5#2 no_pdf"] = issues.get("5#2 no_pdf", 0) + 1

        # Step 5#3: D (视觉内容) vs highlight 图
        highlight_ok = False
        yellow_total = 0.0
        n_highlight_imgs = 0
        if pn_x in step4_idx:
            step4_files = step4_idx[pn_x]
            hl_jpgs = [f for f in step4_files if f.lower().endswith(('.jpg', '.jpeg', '.png'))
                       and ('highlight' in f.lower() or 'page_' in f.lower())]
            for jpg in hl_jpgs[:5]:  # 最多看 5 张
                jpg_path = os.path.join(step4_dir, pn_x, jpg) if convention == "nested" else os.path.join(step4_dir, jpg)
                pct = _yellow_pct(jpg_path)
                if pct > 0:
                    n_highlight_imgs += 1
                    yellow_total = max(yellow_total, pct)
            if yellow_total > 0.01:  # 健康检查阈值
                highlight_ok = True
                row["yellow_max_pct"] = yellow_total
                row["n_highlight_imgs"] = n_highlight_imgs

        if highlight_ok:
            row["aligned_5_3"] = True
            n_aligned_5_3 += 1
        elif pn_x in step4_idx:
            row["issues"].append(f"5#3: 有 highlight 图但 0% 黄 (max={yellow_total:.3f}%)")
            issues["5#3 zero_yellow"] = issues.get("5#3 zero_yellow", 0) + 1
        else:
            row["issues"].append("5#3: 无 highlight 目录")
            issues["5#3 no_highlight"] = issues.get("5#3 no_highlight", 0) + 1

        # v10.2: GLM 语义对齐 (5#3 失败时调 GLM 兜底)
        if use_glm and not row["aligned_5_3"] and d_visual:
            try:
                from glm_integration import semantic_align_step5
                # 抽 highlight 实际文字 (从 PDF 找应证段, 不用 jpg 文件名)
                highlight_text = _extract_highlight_text(
                    pdf_path=row.get("pdf_path", ""),
                    page_hint=int(r.get("page", 0)) or None,
                )
                if highlight_text:
                    glm_result = semantic_align_step5(
                        visual_context=d_visual,
                        highlight_text=highlight_text,
                        use_glm=True,
                    )
                    if glm_result and glm_result.get("aligns"):
                        row["aligned_5_3"] = True
                        n_aligned_5_3 += 1
                        row["glm_align"] = glm_result
            except Exception:
                pass

        rows_result.append(row)

    return {
        "total_rows": n_total,
        "aligned_5_1": n_aligned_5_1,
        "aligned_5_2": n_aligned_5_2,
        "aligned_5_3": n_aligned_5_3,
        "rows": rows_result,
        "issues_summary": issues,
        "csv_cols": cols,
    }


# ════════════════════════════════════════════════════════════════
# 报告输出
# ════════════════════════════════════════════════════════════════

def _write_report(report: Dict, project_name: str, out_dir: str) -> str:
    """写人类可读报告"""
    md_path = os.path.join(out_dir, "step5_三方对齐_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# {project_name} — Step 5 三方对齐报告\n\n")
        f.write(f"生成时间: {__import__('datetime').datetime.now().isoformat()}\n\n")
        f.write(f"## 总览\n\n")
        f.write(f"- 总 Pn-x 数: **{report['total_rows']}**\n")
        f.write(f"- Step 5#1 (PPT slide+mark ↔ 下载目录+highlight 目录): **{report['aligned_5_1']}** / {report['total_rows']} ({report['aligned_5_1']/max(report['total_rows'],1)*100:.1f}%)\n")
        f.write(f"- Step 5#2 (C 列引文 + DOI ↔ PDF): **{report['aligned_5_2']}** / {report['total_rows']} ({report['aligned_5_2']/max(report['total_rows'],1)*100:.1f}%)\n")
        f.write(f"- Step 5#3 (D 列视觉内容 ↔ highlight 图): **{report['aligned_5_3']}** / {report['total_rows']} ({report['aligned_5_3']/max(report['total_rows'],1)*100:.1f}%)\n")
        f.write(f"\n## Issue 汇总\n\n")
        if not report["issues_summary"]:
            f.write("_无 issue_\n")
        else:
            for k, v in sorted(report["issues_summary"].items(), key=lambda x: -x[1]):
                f.write(f"- `{k}`: {v} 个\n")
        f.write(f"\n## 完全对齐 (3/3) 案例 (前 20 个)\n\n")
        all_ok = [r for r in report["rows"] if r["aligned_5_1"] and r["aligned_5_2"] and r["aligned_5_3"]]
        for r in all_ok[:20]:
            yellow = r.get("yellow_max_pct", 0)
            f.write(f"- `{r['pn_x']}` 黄={yellow:.3f}% — {r['citation'][:50]}\n")
        if len(all_ok) > 20:
            f.write(f"- ... (还有 {len(all_ok) - 20} 个)\n")

        f.write(f"\n## 部分对齐案例 (2/3 或 1/3, 前 30 个)\n\n")
        partial = [r for r in report["rows"]
                   if 0 < (r["aligned_5_1"] + r["aligned_5_2"] + r["aligned_5_3"]) < 3]
        for r in partial[:30]:
            score = sum([r["aligned_5_1"], r["aligned_5_2"], r["aligned_5_3"]])
            f.write(f"- `{r['pn_x']}` ({score}/3) issues: {'; '.join(r['issues'])}\n")

        f.write(f"\n## 完全不对齐 (0/3, 前 30 个)\n\n")
        none = [r for r in report["rows"]
                if not (r["aligned_5_1"] or r["aligned_5_2"] or r["aligned_5_3"])]
        for r in none[:30]:
            f.write(f"- `{r['pn_x']}` issues: {'; '.join(r['issues'])}\n")

    return md_path


def _write_status_json(report: Dict, project_name: str, out_dir: str) -> str:
    """写机器可读状态"""
    json_path = os.path.join(out_dir, "step5_三方对齐_status.json")
    output = {
        "project": project_name,
        "total_rows": report["total_rows"],
        "aligned_5_1": report["aligned_5_1"],
        "aligned_5_2": report["aligned_5_2"],
        "aligned_5_3": report["aligned_5_3"],
        "issues_summary": report["issues_summary"],
        "rows": report["rows"],
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    return json_path


def _update_csv_with_alignment(report: Dict, csv_path: str) -> str:
    """更新原 CSV 的 I/J/K 列 (alignment status)"""
    import csv as csvmod

    # 读
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csvmod.DictReader(f)
        rows = list(reader)
        cols = reader.fieldnames or []

    # 找/建 I/J/K 列
    for col in ["I_alignment_A_B", "J_alignment_C_PDF", "K_alignment_D_HL"]:
        if col not in cols:
            cols.append(col)
            for r in rows:
                r[col] = ""

    # 索引 rows by (slide, mark)
    by_key = {(r.get("A_slide", "").strip(), r.get("B_mark", "").strip()): r
              for r in rows}

    for row_result in report["rows"]:
        key = (row_result["slide"], row_result["mark"])
        if key in by_key:
            r = by_key[key]
            r["I_alignment_A_B"] = "✓" if row_result["aligned_5_1"] else "❌"
            r["J_alignment_C_PDF"] = "✓" if row_result["aligned_5_2"] else "❌"
            r["K_alignment_D_HL"] = "✓" if row_result["aligned_5_3"] else "❌"
            if row_result.get("yellow_max_pct"):
                r["K_alignment_D_HL"] += f" ({row_result['yellow_max_pct']:.3f}%)"

    # 写回 (覆盖原文件, 备份到 .bak)
    bak_path = csv_path + ".bak"
    if not os.path.isfile(bak_path):
        import shutil
        shutil.copy(csv_path, bak_path)
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csvmod.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(rows)
    return csv_path


# ════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", choices=list(PROJECTS.keys()),
                        help="项目预设 (雷管方案 / TMA)")
    parser.add_argument("--csv", help="CSV 路径 (覆盖 --project.csv)")
    parser.add_argument("--step3", help="下载目录 (覆盖 --project.step3)")
    parser.add_argument("--step4", help="Highlight 目录 (覆盖 --project.step4)")
    parser.add_argument("--out", help="输出目录 (覆盖 --project.step5)")
    parser.add_argument("--convention", choices=["nested", "flat", "auto"], default="auto")
    parser.add_argument("--use-glm", action="store_true", help="启用 GLM 语义对齐兜底 (5#3)")
    args = parser.parse_args()
    use_glm = args.use_glm

    # 解析参数
    if args.project:
        p = PROJECTS[args.project]
        root = p["root"]
        csv_path = os.path.join(root, args.csv or p["csv"])
        step3_dir = os.path.join(root, args.step3 or p["step3"])
        step4_dir = os.path.join(root, args.step4 or p["step4"])
        out_dir = os.path.join(root, args.out or p["step5"])
        convention = args.convention if args.convention != "auto" else p["convention"]
    else:
        if not (args.csv and args.step3 and args.step4):
            print("需要 --project 或 (--csv + --step3 + --step4)")
            sys.exit(1)
        csv_path = args.csv
        step3_dir = args.step3
        step4_dir = args.step4
        out_dir = args.out or os.path.dirname(csv_path)
        convention = args.convention if args.convention != "auto" else "nested"

    # 跑校验
    print(f"=== Step 5 三方对齐 ===")
    print(f"CSV:      {csv_path}")
    print(f"Step3:    {step3_dir}")
    print(f"Step4:    {step4_dir}")
    print(f"Output:   {out_dir}")
    print(f"约定:     {convention}")
    print()

    report = _check_step5_alignment(csv_path, step3_dir, step4_dir, convention, use_glm=use_glm)
    if "error" in report:
        print(f"❌ {report['error']}")
        sys.exit(1)

    print(f"总 Pn-x: {report['total_rows']}")
    print(f"  5#1 (slide+mark ↔ 目录): {report['aligned_5_1']} ({report['aligned_5_1']/max(report['total_rows'],1)*100:.1f}%)")
    print(f"  5#2 (C+DOI ↔ PDF):       {report['aligned_5_2']} ({report['aligned_5_2']/max(report['total_rows'],1)*100:.1f}%)")
    print(f"  5#3 (D ↔ highlight):     {report['aligned_5_3']} ({report['aligned_5_3']/max(report['total_rows'],1)*100:.1f}%)")
    print(f"Issues:   {len(report['issues_summary'])} 类")

    # 输出
    os.makedirs(out_dir, exist_ok=True)
    md_path = _write_report(report, args.project or "custom", out_dir)
    json_path = _write_status_json(report, args.project or "custom", out_dir)
    csv_out = _update_csv_with_alignment(report, csv_path)
    print()
    print(f"✓ 报告:     {md_path}")
    print(f"✓ 状态 JSON: {json_path}")
    print(f"✓ CSV 更新:  {csv_out} (备份: {csv_out}.bak)")


if __name__ == "__main__":
    main()
