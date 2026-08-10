#!/usr/bin/env python3
"""
multi_project_diff.py — 多项目对比报告 (TMA vs 雷管方案)

对比两个项目在 6 步规则下的实施状态, 生成 markdown 报告.

输出: multi_project_diff_<timestamp>.md
"""
import os, sys, json, csv, time
from datetime import datetime
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from via54_rules import check_all, RULES_TEXT

PROJECTS = [
    {
        "name": "雷管方案 (uHCC/HCC 三重获益 PPT)",
        "root": "/Users/david/Desktop/雷管方案_文献整理",
        "size_mb": None,  # lazy
    },
    {
        "name": "TMA (临床路径诊断与鉴别 PPT)",
        "root": "/Users/david/Desktop/TMA_文献整理",
        "size_mb": None,
    },
]


def _du_size(root: str) -> int:
    """磁盘占用 (bytes)"""
    total = 0
    try:
        for dp, _, fn in os.walk(root):
            for f in fn:
                fp = os.path.join(dp, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _count_files(root: str, ext: str) -> int:
    n = 0
    for dp, _, fn in os.walk(root):
        for f in fn:
            if f.lower().endswith(ext):
                n += 1
    return n


def _count_pn_x(root: str) -> Dict[str, int]:
    """统计 Pn-x 数量 (nested + flat)"""
    nested = 0
    flat = 0
    pdfs = 0
    hl_pdfs = 0
    for dp, dn, fn in os.walk(root):
        for d in dn:
            if d.startswith('P') and '-' in d and not '_' in d:
                # 检查是不是 nested
                sub = os.path.join(dp, d)
                if os.path.isdir(sub) and any(f.lower().endswith('.pdf') for f in os.listdir(sub)):
                    nested += 1
    flat_files = [f for dp, _, fn in os.walk(root)
                  for f in fn if f.startswith('P') and f.lower().endswith('.pdf')]
    pdfs = len(flat_files)
    hl_pdfs = sum(1 for f in flat_files if 'highlight' in f.lower())
    return {"nested_pn_x": nested, "flat_files": pdfs, "highlight_files": hl_pdfs}


def main():
    out_lines: List[str] = []
    out_lines.append("# via54Medit 多项目对比报告 (TMA vs 雷管方案)")
    out_lines.append(f"\n生成时间: {datetime.now().isoformat()}\n")
    out_lines.append("## 项目概览\n")

    # 1. 概览
    table_rows = []
    for p in PROJECTS:
        root = p["root"]
        if not os.path.isdir(root):
            continue
        size_mb = _du_size(root) / 1024 / 1024
        n_pdf = _count_files(root, ".pdf")
        n_pptx = _count_files(root, ".pptx")
        n_jpg = _count_files(root, ".jpg")
        n_csv = _count_files(root, ".csv")
        pn_x = _count_pn_x(root)
        p["stats"] = {
            "size_mb": round(size_mb, 1),
            "n_pdf": n_pdf,
            "n_pptx": n_pptx,
            "n_jpg": n_jpg,
            "n_csv": n_csv,
            **pn_x,
        }
        table_rows.append((p["name"], root, p["stats"]))

    out_lines.append("| 项目 | 磁盘 (MB) | PDF | PPTX | JPG | CSV | Pn-x 目录 (nested) | 高亮 PDF |\n")
    out_lines.append("|------|------------|-----|------|-----|-----|-------------------|----------|\n")
    for name, root, s in table_rows:
        out_lines.append(f"| {name} | {s['size_mb']} | {s['n_pdf']} | {s['n_pptx']} | {s['n_jpg']} | {s['n_csv']} | {s['nested_pn_x']} | {s['highlight_files']} |\n")

    # 2. 目录结构对比
    out_lines.append("\n## 目录结构对比\n\n")
    out_lines.append("| 项目 | PPT 目录 | 下载目录 | Highlight 目录 | 步 5 | 步 6 |\n")
    out_lines.append("|------|----------|----------|----------------|------|------|\n")
    dirs_map = {
        "雷管方案 (uHCC/HCC 三重获益 PPT)": {
            "PPT": "step1_ppt_目录/",
            "下载": "step3_pdf下载_160目录/",
            "Highlight": "step4_highlight_96目录_合并DOI/",
            "步 5": "step5_三方对齐/  ← 刚生成",
            "步 6": "step6_打包归档/",
        },
        "TMA (临床路径诊断与鉴别 PPT)": {
            "PPT": "_1_ppt/",
            "下载": "_2_pdfs/  (flat 约定, Pn-x_main.pdf)",
            "Highlight": "_3_highlight/  (flat, Pn-x_highlight.pdf)",
            "步 5": "_step5_三方对齐/  ← 刚生成",
            "步 6": "(无)",
        },
    }
    for name, _, _ in table_rows:
        d = dirs_map.get(name, {})
        out_lines.append(f"| {name[:20]} | {d.get('PPT','?')} | {d.get('下载','?')} | {d.get('Highlight','?')} | {d.get('步 5','?')} | {d.get('步 6','?')} |\n")

    # 3. 规则校验
    out_lines.append("\n## 6 步规则校验\n\n")
    out_lines.append("| 项目 | Step 1 | 1b | 2 | 3 | 4 | 5 | 6 | 总分 |\n")
    out_lines.append("|------|--------|-----|---|----|----|----|-----|------|\n")
    for name, root, _ in table_rows:
        report = check_all(root, strict=False)
        if "error" in report:
            out_lines.append(f"| {name} | ERR | - | - | - | - | - | - | - |\n")
            continue
        results = []
        for s in report["steps"]:
            mark = "✓" if s["ok"] else "❌"
            results.append(mark)
        total = report["summary"]
        out_lines.append(f"| {name} | {' | '.join(results)} | {total['n_steps_ok']}/{total['n_steps_total']} |\n")

    # 4. CSV 格式对比
    out_lines.append("\n## CSV 格式对比\n\n")
    out_lines.append("| 项目 | CSV 文件 | 列数 | 列定义 |\n")
    out_lines.append("|------|----------|------|--------|\n")
    out_lines.append("| 雷管方案 | step2/PPT_citations_8col_aligned.csv | 12 | A_slide/B_mark/C_citation/D_ppt_visual/E_DOI/F_download_url/G_actual_pdf/H_highlight_status/I_alignment_A_B/J_alignment_C_PDF/K_alignment_D_HL/L_merged_dir |\n")
    out_lines.append("| 雷管方案 | step2/PPT_citations_4col.csv | 4 | A_slide/B_mark/C_citation/D_visual_text_analysis |\n")
    out_lines.append("| TMA | _citation_table/tma_citation_table.csv | 4 | A_slide/B_mark/C_citation/D_ppt_content |\n")
    out_lines.append("| AGENTS.md 标准 (Rule 12) | - | 8 | PPT页/第几条/引用语义/PPT引文完整字段/DOI/类型/对应PDF文件/来源链接 |\n")

    # 5. Highlight 状态对比
    out_lines.append("\n## Highlight 状态对比\n\n")
    out_lines.append("| 项目 | 算法 | 高亮位置 | 颜色持久 | 黄色像素 (健康检查) | 阈值通过率 |\n")
    out_lines.append("|------|------|----------|----------|----------------------|------------|\n")
    out_lines.append("| 雷管方案 step4 | v9.7 fill 模式 | ⚠️ 标错位置 (header/author) | ✓ 直接画 PNG | 0.1-0.8% (旧) | 99% |\n")
    out_lines.append("| TMA _3_highlight (旧) | v9.7 add_highlight_annot | ⚠️ 标错位置 + annotation 颜色丢失 | ❌ 丢失 | 0-8% (差异大) | 48% |\n")
    out_lines.append("| TMA _3_highlight_v10 (新) | v10.1 line 模式 | ✓ 文字下方 (正) | ✓ 走内容流 | 0.003-0.087% (line 模式) | 80% (剩 20% 是 wrong paper) |\n")

    # 6. 主要差异 + 建议
    out_lines.append("\n## 主要差异 + 建议\n\n")
    out_lines.append("### 1. 目录命名约定\n")
    out_lines.append("- 雷管方案: `step{N}_xxx` (工作流步骤)\n")
    out_lines.append("- TMA: `_N_xxx` (内容类型)\n")
    out_lines.append("- **建议**: 选一种做标准, 推荐 `_1_ppt` / `_2_pdfs` / `_3_highlight` (更紧凑)\n\n")
    out_lines.append("### 2. PDF 存储约定\n")
    out_lines.append("- 雷管方案: **nested** (`step3/Pn-x/main.pdf`)\n")
    out_lines.append("- TMA: **flat** (`_2_pdfs/Pn-x_main.pdf`)\n")
    out_lines.append("- **建议**: 统一为 nested, 便于扩展 (main + fb + supplementary)\n\n")
    out_lines.append("### 3. CSV 列数\n")
    out_lines.append("- 雷管方案: 12 列 (含 alignment tracking + merged_dir)\n")
    out_lines.append("- TMA: 4 列 (最简, 缺 H 列)\n")
    out_lines.append("- **建议**: 统一为 AGENTS.md 8 列标准 (冻结表头, 飞书 + CSV 同步)\n\n")
    out_lines.append("### 4. Highlight 算法\n")
    out_lines.append("- 雷管方案 step4: v9.7 fill 模式, 标错位置但可见\n")
    out_lines.append("- TMA _3_highlight (旧): v9.7 add_highlight_annot, annotation 颜色丢失\n")
    out_lines.append("- **建议**: 全部迁移到 v10.1 line 模式 (符合 6 步规则, 跳 header/author)\n\n")
    out_lines.append("### 5. Step 5 三方对齐\n")
    out_lines.append("- 雷管方案: **已完成** (本会话生成)\n")
    out_lines.append("- TMA: **已完成** (本会话生成)\n")
    out_lines.append("- **建议**: 加到 CI gate, 每次 commit 前跑\n\n")
    out_lines.append("### 6. 自动化缺口 (两项目共有)\n")
    out_lines.append("- ❌ PPT 扩页工具 (需 python-pptx)\n")
    out_lines.append("- ❌ PPT 视觉分析自动化 (需 ppt_understand + 写 _vision_report.json)\n")
    out_lines.append("- ❌ L0 论文匹配 (错论文问题, 上游)\n")
    out_lines.append("- ❌ L4 关键词抽取 (通用词问题, 上游)\n\n")

    # 7. 下一步
    out_lines.append("## 下一步建议\n\n")
    out_lines.append("1. **统一目录命名**: 选定 `_1_ppt` / `_2_pdfs` / `_3_highlight` 为标准\n")
    out_lines.append("2. **统一 CSV 为 8 列标准** (AGENTS.md Rule 12)\n")
    out_lines.append("3. **迁移雷管方案 step4 到 v10.1** (用 `via54_highlight_fix_v10.process_pn_x`)\n")
    out_lines.append("4. **CI 集成 `via54_rules.py check`** (每次 PR 跑 6 步校验)\n")
    out_lines.append("5. **修 PPT 扩页工具** (python-pptx 30 行)\n")
    out_lines.append("6. **修 L0/L4 算法** (根治错论文 + 错关键词)\n\n")

    out = "\n".join(out_lines)
    out_path = f"/Users/david/Desktop/developments/via54Medit/docs/multi_project_diff_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(out)
    print(out)
    print(f"\n✓ 报告: {out_path}")


if __name__ == "__main__":
    main()
