#!/usr/bin/env python3
"""
via54_rules.py — 6 步规则校验 (v10.1)

校验一个文献整理 pipeline run 是否符合 6 步规则:
  Step 1: 文献整理目录结构 (3 个子目录)
  Step 2: PPT 视觉理解 (扩页 + 引文分析)
  Step 3: 文献下载 (DOI + 完整字段交叉验证)
  Step 4: Highlight (细黄线 + 多引文展开)
  Step 5: 三方对齐 (PPT/表格/PDF)
  Step 6: 目录合并 (Pn1-x1Pn2-x2 格式)

可作为 CI gate, 也可人工跑:
  python3.11 via54_rules.py check <project_dir> [--strict]
  python3.11 via54_rules.py print-rules        # 打印 6 步规则文本
  python3.11 via54_rules.py quick-check <dir>  # 快速看合规度
"""
import os, re, sys, json
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ════════════════════════════════════════════════════════════════
# 规则文本 (从用户需求提取, 6 步)
# ════════════════════════════════════════════════════════════════

RULES_TEXT = """
═══════════════════════════════════════════════════════════════
via54Medit 6 步规则 (2026-08-10 用户版 + AGENTS.md 校准)
═══════════════════════════════════════════════════════════════

[表格列定义 — 8 列标准表头, 与 AGENTS.md Rule 12 一致]
  A = PPT页              (slide number)
  B = 第几条             (citation mark, 1-N)
  C = 引用语义           (semantic context, e.g. "标准与讨论" 段)
  D = PPT引文完整字段     (full citation field, e.g. "Qin S, et al. Lancet Oncol. 2025")
  E = DOI                (with hyperlink)
  F = 类型               (LITERATURE / DATABASE / GOVERNMENT / CONFERENCE / OTHER)
  G = 对应PDF文件         (filename, not full path)
  H = 来源链接            (来源链接 + 视觉/文字分析 + 应证推理 + Highlight 链接)

  [注意] 用户原话 "D 列 = 视觉+文字分析结果" 实际映射到 H 列的"应证推理"段
         D 列在真实表里是 PPT引文完整字段 (用户可能用 D 泛指"分析结果")
         H 列才是真正的分析 + Highlight 综合位置

【步骤一】拿到 PPT 后, 先建立文献整理目录
  1. PPT 目录 (3 个内容):
     - 原版 PPT (file: *.pptx)
     - 重新扩充页面尺寸的 PPT (保证关键内容都能看到)
     - 扩充页面尺寸后导出的 PPT 图片 (用于视觉分析)
  2. 文献 PDF 下载目录
  3. 文献 PDF highlight 目录

【步骤二】分析 PPT 中的文献标注
  1. 文献标注分两部分: 引用序号 + slide 底部对应引用文献
  2. 视觉分析所有元素可见性. 引用文献超出页面 → 重新扩 PPT 页.
     扩页时分析引用文献文字颜色, 扩后底色必须保证引用文献可识别.
  3. 视觉 + 文字理解, 分析引用序号指向的 PPT 内容, 记到 H 列"应证推理"段
     A=slide, B=mark, C=引用语义, D=完整引文, F=类型
     A/B/C 对齐 PPT 后固定不变
     D 列因缺 PDF 校准为暂定, 后续可调
  4. 必须视觉分析. 如需先导出图片, 建立 PPT 导出图片目录

【步骤三】搜索并下载文献
  1. 引用文献完整字段 (D 列) 的 DOI 值 (带超链接) 填入 E 列
  2. D + E 交叉校验, 找出下载链接. PPT 引文 (D 列) = 唯一真值
  3. 下载所有文献, 按 Pn-x 归档 (不去重), 一 Pn-x = 一 PDF.
     没有全文就下载摘要 PDF
  4. 所有 PDF + DOI 对齐每个 slide 每个引文序号的引用文献完整字段 (D 列)

【步骤四】对文献 PDF 做 highlight (按 slide 顺序)
  1. 把确认的下载子目录全部复制到 highlight 目录
  2. 看一 slide, 视觉分析每个引用序号要表达的内容, 对照序号 PDF,
     找 PDF 中能说明引文语义的段/数据/图标/表格, 提取匹配页图片
  3. PPT 分析结果 + 准备 highlight 的 PDF 图片, 视觉对照 + 语义匹配,
     确认后做 highlight (文字下方细黄线, 图标/表格数据也是文字下方细黄线)
  4. "1,2" / "1-3" 这类多引文 (展开为 1,2,3) 需综合对比多个 Pn-x
  5. 再次对照 PPT 视觉与 highlight 后图片是否完全对应
  6. 确认后, 对 PDF 同样做 highlight
  7. 最终检查: highlight 子目录 = PPT 引用序号条数个 Pn-x 目录,
     每目录 1 个已 highlight PDF + 多张 highlight 图片

【步骤五】三方对齐 (PPT 视觉 / 表格 / PDF highlight)
  1. PPT slide+引用序号 (A+B)  &  下载目录  &  highlight 目录
  2. PPT 引用文献字段 (D)  &  表格 D+E  &  下载 PDF  &  highlight PDF
  3. PPT 视觉内容  &  highlight 图片  &  表格 H (应证推理段)

【步骤六】Highlight 目录整理 + 打包
  1. 合并相同文献目录, 命名 Pn1-x1Pn2-x2 格式 (代码默认用 "_" 分隔)
  2. 验证每目录 = 1 篇文献, 1 文献 = 1 目录, 无冲突
  3. 最终检查: 原始 PPT / 扩尺寸 PPT / 扩尺寸 PPT 图片 / 下载目录 /
     highlight 目录 / PPT-文献逐页引用表 — 全部正确且为真实情况

[via54_rules.py 校验用法]
  python3.11 via54_rules.py check <project_dir> [--verbose]
  python3.11 via54_rules.py quick-check <project_dir>    # exit 0/1
  python3.11 via54_rules.py print-rules                    # 打印本规则文本

  兼容 nested (Pn-x/main.pdf) + flat (Pn-x_main.pdf) 两种目录约定
  TMA 项目用 flat, 雷管方案用 nested, check 自动适配
"""


# ════════════════════════════════════════════════════════════════
# 规则校验 (按 6 步)
# ════════════════════════════════════════════════════════════════

def _check_step1_dirs(project_dir: str) -> Dict:
    """
    步骤一: 检查 3 个目录是否存在
      - _ppt/ 或 ppt/ (PPT 目录)
      - _download/ 或 download/ 或 _pdfs/ (PDF 下载)
      - _highlight/ 或 highlight/ (highlight)
    """
    issues: List[str] = []
    found: Dict[str, Optional[str]] = {}

    candidates = {
        "ppt": ["_ppt", "ppt", "_1_ppt", "PPT", "step1_ppt_目录", "step1_ppt"],
        "download": ["_download", "download", "_pdfs", "_2_pdfs", "pdfs",
                     "step3_pdf下载_160目录", "step3_pdf", "step3_pdfs"],
        # v10_glm 是最新最完整的 (含合并 Pn1-x1Pn2-x2), 优先选
        "highlight": ["_3_highlight_v10_glm", "step4_highlight_v10_glm",
                      "_highlight", "highlight", "_3_highlight", "hl",
                      "step4_highlight_96目录_合并DOI", "step4_highlight"],
    }
    for kind, names in candidates.items():
        for n in names:
            p = os.path.join(project_dir, n)
            if os.path.isdir(p):
                found[kind] = p
                break
        else:
            issues.append(f"缺 {kind} 目录 (候选: {names})")
            found[kind] = None

    return {
        "ok": len(issues) == 0,
        "found": found,
        "issues": issues,
    }


def _check_step1_ppt_expansion(project_dir: str, ppt_dir: Optional[str]) -> Dict:
    """
    步骤一#1: PPT 目录应有原版 + 扩页后 + 扩页后导出的图

    支持 TMA 风格 nested 结构: _1_ppt/_1_original/TMA临床路径的诊断与鉴别.pptx
    直接子文件 + 1 层子目录 都算.
    """
    issues: List[str] = []
    if not ppt_dir or not os.path.isdir(ppt_dir):
        return {"ok": False, "issues": ["PPT 目录不存在"], "counts": {}}

    # 找 .pptx / .pdf (导出图)/ _expanded 标记
    # 递归找: 直接子文件 + 1 层子目录
    files = os.listdir(ppt_dir)
    sub_files = []
    for sub in files:
        sub_path = os.path.join(ppt_dir, sub)
        if os.path.isdir(sub_path):
            try:
                sub_files.extend(os.listdir(sub_path))
            except OSError:
                pass
    all_files = files + sub_files
    # has_original: 直接子文件 或 1 层子目录里都算 (TMA 风格 _1_original/...)
    has_original = any(f.lower().endswith(('.pptx', '.ppt')) for f in all_files)
    has_expanded = any('expand' in f.lower() or 'enlarged' in f.lower() for f in all_files)
    has_images = any(f.lower().endswith(('.jpg', '.png', '.jpeg')) for f in all_files)

    if not has_original:
        issues.append("PPT 目录无 .pptx/.ppt 原版文件")
    if not has_expanded:
        issues.append("PPT 目录无扩尺寸后的 PPT (建议: 原名_expanded.pptx)")
    if not has_images:
        issues.append("PPT 目录无导出图片 (.jpg/.png)")

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "counts": {
            "original": sum(1 for f in files if f.lower().endswith(('.pptx', '.ppt'))),
            "expanded": sum(1 for f in files if 'expand' in f.lower() or 'enlarged' in f.lower()),
            "images": sum(1 for f in files if f.lower().endswith(('.jpg', '.png', '.jpeg'))),
        },
    }


def _check_step2_ppt_analysis(ppt_dir: Optional[str]) -> Dict:
    """
    步骤二: PPT 视觉理解 — 找有没有
      - 标号位置提取 (citation_marks)
      - 视觉+文字分析 (D 列内容)
    """
    issues: List[str] = []
    checks: Dict[str, bool] = {}
    if not ppt_dir:
        return {"ok": False, "issues": ["PPT 目录不存在"], "checks": {}}

    # 检查是否有 _vision_report.json 或 _analysis.md
    # 支持: 直接子文件 + 1 层子目录 (TMA 风格 _1_ppt/_1_original/...)
    analysis_files = ['_vision_report.json', '_analysis.md', '_ppt_analysis.json']
    analysis_paths = []
    for f in analysis_files:
        # 直接
        if os.path.isfile(os.path.join(ppt_dir, f)):
            analysis_paths.append(os.path.join(ppt_dir, f))
        # 1 层子目录
        for sub in os.listdir(ppt_dir):
            sp = os.path.join(ppt_dir, sub)
            if os.path.isdir(sp) and os.path.isfile(os.path.join(sp, f)):
                analysis_paths.append(os.path.join(sp, f))
    checks["analysis_file"] = len(analysis_paths) > 0
    # 检查 _exported_images 或 _ppt_renders 目录 (直接 + 1 层)
    img_dirs = ['_exported_images', '_ppt_renders', '_ppt_images', 'images', '_3_images', '_2_expanded']
    checks["exported_images"] = any(os.path.isdir(os.path.join(ppt_dir, d)) for d in img_dirs) \
        or any(os.path.isdir(os.path.join(ppt_dir, sub, d))
               for sub in os.listdir(ppt_dir) if os.path.isdir(os.path.join(ppt_dir, sub))
               for d in img_dirs)

    if not checks["analysis_file"]:
        issues.append("无 PPT 视觉分析结果 (建议: _vision_report.json)")
    if not checks["exported_images"]:
        issues.append("无 PPT 导出图片目录 (建议: _exported_images/)")

    return {"ok": len(issues) == 0, "issues": issues, "checks": checks}


def _check_step3_download(download_dir: Optional[str]) -> Dict:
    """
    步骤三: 文献下载
      - 有 Pn-x 子目录 (嵌套) 或 Pn-x_*.pdf 文件 (flat)
      - 每个有 PDF
      - 没有去重 (即使同 PDF 也可独立)

    支持两种约定:
      1. 嵌套: download_dir/Pn-x/main.pdf (规则推荐)
      2. flat: download_dir/Pn-x_xxx.pdf (TMA 项目用)
    """
    issues: List[str] = []
    warnings: List[str] = []
    counts: Dict[str, int] = {"pn_x_dirs": 0, "with_pdf": 0, "total_pdfs": 0,
                              "flat_files": 0, "convention": ""}
    if not download_dir:
        return {"ok": False, "issues": ["下载目录不存在"], "counts": counts}

    # 优先按嵌套 (Pn-x 子目录) 扫
    pn_x_dirs = [d for d in os.listdir(download_dir)
                 if os.path.isdir(os.path.join(download_dir, d)) and d.startswith('P')]

    if pn_x_dirs:
        counts["convention"] = "nested"
        counts["pn_x_dirs"] = len(pn_x_dirs)
        for d in pn_x_dirs:
            full = os.path.join(download_dir, d)
            pdfs = [f for f in os.listdir(full) if f.lower().endswith('.pdf')]
            if pdfs:
                counts["with_pdf"] += 1
                counts["total_pdfs"] += len(pdfs)

        if counts["with_pdf"] < counts["pn_x_dirs"]:
            missing = counts["pn_x_dirs"] - counts["with_pdf"]
            issues.append(f"{missing} 个 Pn-x 目录无 PDF")
    else:
        # 退到 flat 约定: Pn-x_*.pdf
        pn_x_files = [f for f in os.listdir(download_dir)
                      if f.lower().endswith('.pdf') and f.startswith('P')]
        if pn_x_files:
            counts["convention"] = "flat"
            counts["flat_files"] = len(pn_x_files)
            counts["total_pdfs"] = len(pn_x_files)
            counts["pn_x_dirs"] = len(set(re.match(r'(P\d+-\d+)', f).group(1)
                                          for f in pn_x_files if re.match(r'(P\d+-\d+)', f)))
            counts["with_pdf"] = counts["pn_x_dirs"]
            warnings.append(
                "使用 flat 约定 (Pn-x_*.pdf 在 download_dir 直接子文件), "
                "规则推荐嵌套 (Pn-x/main.pdf). 后续步骤会自动兼容."
            )
        else:
            issues.append("下载目录无 Pn-x 子目录或 Pn-x_*.pdf 文件")

    return {"ok": len(issues) == 0, "issues": issues, "warnings": warnings, "counts": counts}


def _check_step4_highlight(highlight_dir: Optional[str], download_dir: Optional[str]) -> Dict:
    """
    步骤四: Highlight
      - 有 Pn-x 子目录 (嵌套) 或 Pn-x_*.pdf (flat)
      - 每目录/file 有 highlight PDF
      - 有 highlight 图片
      - 数量 = PPT 引用序号条数 (≈ 下载目录 Pn-x 数)

    支持 flat (Pn-x_highlight.pdf) 和 nested (Pn-x/main.pdf + page jpg) 两种约定
    """
    issues: List[str] = []
    warnings: List[str] = []
    counts: Dict[str, int] = {
        "pn_x_dirs": 0,
        "with_pdf": 0,
        "with_jpg": 0,
        "with_highlight_jpg": 0,
        "flat_pdfs": 0,
        "convention": "",
    }
    if not highlight_dir:
        return {"ok": False, "issues": ["Highlight 目录不存在"], "counts": counts}

    # 区分 nested 真正的 Pn-x (有 main.pdf / v10.pdf) vs flat 的 Pn-x_jpgs/ 辅助目录
    # 规则: 只把包含 PDF 的目录当 nested Pn-x, 其他是辅助
    all_p_dirs = [d for d in os.listdir(highlight_dir)
                  if os.path.isdir(os.path.join(highlight_dir, d)) and d.startswith('P')]
    pn_x_dirs = []
    pn_x_jpgs = []  # 辅助 jpg 目录 (Pn-x_jpgs/)
    for d in all_p_dirs:
        full = os.path.join(highlight_dir, d)
        if d.endswith('_jpgs') or d.endswith('_images'):
            pn_x_jpgs.append(d)
            continue
        files = os.listdir(full)
        if any(f.lower().endswith('.pdf') for f in files):
            pn_x_dirs.append(d)
        else:
            # 纯 jpg 目录 (无 PDF) 也算辅助
            pn_x_jpgs.append(d)

    if pn_x_dirs:
        counts["convention"] = "nested"
        counts["pn_x_dirs"] = len(pn_x_dirs)
        for d in pn_x_dirs:
            full = os.path.join(highlight_dir, d)
            files = os.listdir(full)
            pdfs = [f for f in files if f.lower().endswith('.pdf')]
            jpgs = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
            hl_jpgs = [f for f in files if 'highlight' in f.lower() and f.lower().endswith(('.jpg', '.jpeg', '.png'))]
            if pdfs:
                counts["with_pdf"] += 1
            if jpgs:
                counts["with_jpg"] += 1
            if hl_jpgs:
                counts["with_highlight_jpg"] += 1
    else:
        # flat 约定: Pn-x_highlight.pdf
        hl_pdfs = [f for f in os.listdir(highlight_dir)
                   if f.lower().endswith('.pdf') and 'highlight' in f.lower() and f.startswith('P')]
        if hl_pdfs:
            counts["convention"] = "flat"
            counts["flat_pdfs"] = len(hl_pdfs)
            counts["with_pdf"] = len(hl_pdfs)
            counts["pn_x_dirs"] = len(set(re.match(r'(P\d+-\d+)', f).group(1)
                                          for f in hl_pdfs if re.match(r'(P\d+-\d+)', f)))
            warnings.append(
                "使用 flat 约定 (Pn-x_highlight.pdf 在 highlight_dir 直接子文件), "
                "规则推荐嵌套 (Pn-x/main.pdf + page jpg)."
            )
        else:
            issues.append("Highlight 目录无 Pn-x 子目录或 Pn-x_highlight.pdf")

    if counts["convention"] == "flat":
        # flat 约定下没有 highlight jpg (只有 PDF), 是符合预期的
        if counts["with_highlight_jpg"] == 0:
            warnings.append("flat 约定下无 highlight jpg (需要渲染 PDF 提取)")
    else:
        if counts["with_pdf"] == 0:
            issues.append("Highlight 目录无 PDF")
        # v10 line 模式: jpg 命名是 page_001.jpg / page_page1.jpg, 不一定含 highlight
        # 兼容: 含 highlight 的 jpg 优先, 否则任意 jpg 都算
        if counts["with_highlight_jpg"] == 0 and counts["with_jpg"] == 0:
            issues.append("Highlight 目录无图片 (jpg/png)")

    # 对齐检查: highlight 数 ≈ download 数 (无论哪种约定)
    if download_dir and os.path.isdir(download_dir):
        dl_pn_x = _count_pn_x(download_dir)
        if abs(dl_pn_x - counts["pn_x_dirs"]) > max(2, dl_pn_x * 0.05):
            issues.append(
                f"Highlight 目录 ({counts['pn_x_dirs']} Pn-x) 与下载目录 "
                f"({dl_pn_x} Pn-x) 数量不一致 (差异 >5%)"
            )

    return {"ok": len(issues) == 0, "issues": issues, "warnings": warnings, "counts": counts}


def _count_pn_x(dir_path: str) -> int:
    """统计一个目录下 Pn-x 的数量 (兼容 nested + flat + 辅助 _jpgs/_images)"""
    # 排除辅助目录 (Pn-x_jpgs/, Pn-x_images/)
    real_dirs = [d for d in os.listdir(dir_path)
                 if os.path.isdir(os.path.join(dir_path, d))
                 and d.startswith('P')
                 and not (d.endswith('_jpgs') or d.endswith('_images'))]
    if real_dirs:
        return len(real_dirs)
    # flat: 统计顶层 Pn-x_*.pdf 文件
    files = [f for f in os.listdir(dir_path)
             if f.startswith('P')
             and not os.path.isdir(os.path.join(dir_path, f))
             and (f.lower().endswith('.pdf') or '_' in f)]
    pns = set()
    for f in files:
        m = re.match(r'(P\d+-\d+)', f)
        if m:
            pns.add(m.group(1))
    return len(pns)


def _check_step5_alignment(
    ppt_dir: Optional[str],
    download_dir: Optional[str],
    highlight_dir: Optional[str],
    project_dir: str,
) -> Dict:
    """
    步骤五: 三方对齐
      - A+B (slide+mark) vs Pn-x 目录名
      - C+E (citation+DOI) vs PDF 文件
      - D+F+H (visual) vs highlight 图片
    """
    issues: List[str] = []
    info: Dict = {}

    if not download_dir or not highlight_dir:
        return {"ok": False, "issues": ["下载或 highlight 目录缺失"], "info": {}}

    # 排除辅助目录 (Pn-x_jpgs/, Pn-x_images/)
    def _real_pn_x(d: str) -> bool:
        return (d.startswith('P')
                and not d.endswith('_jpgs')
                and not d.endswith('_images'))

    def _extract_pn_x_set(dir_path: str) -> set:
        """兼容 nested (Pn-x 目录) + flat (Pn-x_*.pdf)"""
        items = set()
        for name in os.listdir(dir_path):
            full = os.path.join(dir_path, name)
            if os.path.isdir(full):
                if _real_pn_x(name):
                    items.add(name)
            elif name.startswith('P') and (name.lower().endswith('.pdf') or '_' in name):
                m = re.match(r'(P\d+-\d+)', name)
                if m:
                    items.add(m.group(1))
        return items

    dl_pn_x = _extract_pn_x_set(download_dir)
    hl_pn_x = _extract_pn_x_set(highlight_dir)

    # A+B 对齐: highlight 应当包含 download 的所有 Pn-x
    missing_in_hl = dl_pn_x - hl_pn_x
    extra_in_hl = hl_pn_x - dl_pn_x
    if missing_in_hl:
        issues.append(f"Step 5#1: highlight 缺 {len(missing_in_hl)} 个 Pn-x (例: {list(missing_in_hl)[:3]})")
    if extra_in_hl:
        issues.append(f"Step 5#1: highlight 多 {len(extra_in_hl)} 个 Pn-x (例: {list(extra_in_hl)[:3]})")

    info["dl_count"] = len(dl_pn_x)
    info["hl_count"] = len(hl_pn_x)
    info["missing_in_hl"] = list(missing_in_hl)[:5]
    info["extra_in_hl"] = list(extra_in_hl)[:5]

    return {"ok": len(issues) == 0, "issues": issues, "info": info}


def _check_step6_merge(highlight_dir: Optional[str]) -> Dict:
    """
    步骤六: 目录合并
      - 合并目录名含 '_' (P15-1_P16-1)
      - 散乱单 Pn-x 不应独立存在 (应已合并)
    """
    issues: List[str] = []
    info: Dict = {"merged_dirs": [], "single_dirs": []}

    if not highlight_dir:
        return {"ok": False, "issues": ["Highlight 目录不存在"], "info": {}}

    for d in os.listdir(highlight_dir):
        full = os.path.join(highlight_dir, d)
        if not os.path.isdir(full) or not d.startswith('P'):
            continue
        if '_' in d:
            # 检查是否符合 Pn-n_Pn-n 格式
            parts = d.split('_')
            if all(re.match(r'^P\d+-\d+$', p) for p in parts):
                info["merged_dirs"].append(d)
        else:
            info["single_dirs"].append(d)

    # 冲突检查: 两个合并目录不应该有相同 PDF
    seen_pdfs: Dict[str, str] = {}
    conflicts: List[str] = []
    for d in info["merged_dirs"] + info["single_dirs"]:
        full = os.path.join(highlight_dir, d)
        for f in os.listdir(full):
            if f.lower().endswith('.pdf'):
                if f in seen_pdfs and seen_pdfs[f] != d:
                    conflicts.append(f"{f} 在 {seen_pdfs[f]} 和 {d} 都存在")
                else:
                    seen_pdfs[f] = d
    if conflicts:
        issues.append(f"Step 6#2: 目录冲突 ({len(conflicts)} 个, 例: {conflicts[:3]})")

    return {"ok": len(issues) == 0, "issues": issues, "info": info}


# ════════════════════════════════════════════════════════════════
# 顶层: 完整校验
# ════════════════════════════════════════════════════════════════

def check_all(project_dir: str, strict: bool = False) -> Dict:
    """
    跑全部 6 步校验

    Args:
        project_dir: 项目根目录 (含 3 个子目录)
        strict: 严格模式 (warning 也算 fail)

    Returns:
        {
            'project': str,
            'overall_ok': bool,
            'steps': [{'step': 1, 'name': ..., 'ok': ..., 'issues': [...], 'details': {...}}],
            'summary': {...},
        }
    """
    if not os.path.isdir(project_dir):
        return {"project": project_dir, "overall_ok": False,
                "error": f"项目目录不存在: {project_dir}"}

    # Step 1
    s1 = _check_step1_dirs(project_dir)
    ppt_dir = s1["found"]["ppt"]
    download_dir = s1["found"]["download"]
    highlight_dir = s1["found"]["highlight"]

    s1_ppt = _check_step1_ppt_expansion(project_dir, ppt_dir)

    # Step 2
    s2 = _check_step2_ppt_analysis(ppt_dir)

    # Step 3
    s3 = _check_step3_download(download_dir)

    # Step 4
    s4 = _check_step4_highlight(highlight_dir, download_dir)

    # Step 5
    s5 = _check_step5_alignment(ppt_dir, download_dir, highlight_dir, project_dir)

    # Step 6
    s6 = _check_step6_merge(highlight_dir)

    all_issues = []
    all_warnings = []
    steps = [
        {"step": 1, "name": "目录结构 (3 个子目录)", "ok": s1["ok"],
         "issues": s1["issues"], "warnings": [], "details": s1["found"]},
        {"step": "1b", "name": "PPT 扩页 + 图片导出", "ok": s1_ppt["ok"],
         "issues": s1_ppt["issues"], "warnings": [], "details": s1_ppt["counts"]},
        {"step": 2, "name": "PPT 视觉分析 (引文标号 + 视觉+文字)", "ok": s2["ok"],
         "issues": s2["issues"], "warnings": [], "details": s2["checks"]},
        {"step": 3, "name": "文献下载 (Pn-x 归档, DOI 交叉校验)", "ok": s3["ok"],
         "issues": s3["issues"], "warnings": s3.get("warnings", []), "details": s3["counts"]},
        {"step": 4, "name": "Highlight (细黄线 + 多页 + 多引文)", "ok": s4["ok"],
         "issues": s4["issues"], "warnings": s4.get("warnings", []), "details": s4["counts"]},
        {"step": 5, "name": "三方对齐 (PPT/表格/PDF)", "ok": s5["ok"],
         "issues": s5["issues"], "warnings": [], "details": s5["info"]},
        {"step": 6, "name": "目录合并 (Pn1-x1Pn2-x2)", "ok": s6["ok"],
         "issues": s6["issues"], "warnings": [], "details": s6["info"]},
    ]
    for s in steps:
        all_issues.extend(s["issues"])
        all_warnings.extend(s["warnings"])

    overall = all(s["ok"] for s in steps)

    return {
        "project": project_dir,
        "overall_ok": overall,
        "steps": steps,
        "summary": {
            "n_steps_ok": sum(1 for s in steps if s["ok"]),
            "n_steps_total": len(steps),
            "n_issues": sum(len(s["issues"]) for s in steps),
            "n_warnings": sum(len(s["warnings"]) for s in steps),
        },
    }


def print_report(report: Dict, verbose: bool = True) -> None:
    """打印规则校验报告"""
    print("═" * 70)
    print(f"via54 Rules Check: {report['project']}")
    print("═" * 70)

    if "error" in report:
        print(f"❌ {report['error']}")
        return

    summary = report["summary"]
    overall = report["overall_ok"]
    mark = "✅" if overall else "❌"
    print(f"\n{mark} 总体: {summary['n_steps_ok']}/{summary['n_steps_total']} 步通过, {summary['n_issues']} 个 issue\n")

    for s in report["steps"]:
        sm = "✓" if s["ok"] else "❌"
        print(f"  {sm} Step {s['step']}: {s['name']}")
        if s["issues"] and (verbose or not s["ok"]):
            for issue in s["issues"]:
                print(f"      ⚠ {issue}")
        if s["warnings"] and verbose:
            for w in s["warnings"]:
                print(f"      ℹ️ {w}")
        if verbose and s["details"]:
            for k, v in s["details"].items():
                if isinstance(v, list):
                    v_str = f"{len(v)} 个" if not v else str(v[:3])
                elif isinstance(v, dict):
                    v_str = json.dumps(v, ensure_ascii=False)[:100]
                else:
                    v_str = str(v)
                print(f"      · {k}: {v_str}")
        print()


def quick_check(project_dir: str) -> int:
    """快速校验, 返回 exit code (0=ok, 1=fail)"""
    report = check_all(project_dir, strict=False)
    print_report(report, verbose=False)
    return 0 if report["overall_ok"] else 1


# ════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "print-rules":
        print(RULES_TEXT)
    elif cmd == "check":
        if len(sys.argv) < 3:
            print("Usage: check <project_dir> [--strict] [--verbose]")
            sys.exit(1)
        project_dir = sys.argv[2]
        strict = "--strict" in sys.argv
        verbose = "--verbose" in sys.argv or "-v" in sys.argv
        report = check_all(project_dir, strict=strict)
        print_report(report, verbose=verbose)
        sys.exit(0 if report["overall_ok"] else 1)
    elif cmd == "quick-check":
        if len(sys.argv) < 3:
            print("Usage: quick-check <project_dir>")
            sys.exit(1)
        sys.exit(quick_check(sys.argv[2]))
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
