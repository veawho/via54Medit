#!/usr/bin/env python3
"""
via54.py — via54Medit 统一入口 (2026-08-10, 2026-08-20 update)

整合所有 v10 工具, 一个 CLI 全跑.

子命令:
  rules           6 步规则校验
  step5           Step 5 三方对齐
  highlight       Highlight 重新生成 (默认 visual-v3: PPT 视觉 API + v3 FINAL + 9 铁律)
  paper-match     L0 错论文校验
  keyword         L4 关键词抽取
  ppt             PPT 扩页 + 审计 + 渲染
  diff            双项目对比
  all             跑全部
  download        TMA 文献级联下载 (round1 OA 级联 / round2 CrossRef+核验+SciHub)
  pdf-verify      下载 PDF 内容核验 (期刊/年份/作者)
  hl-batch        批量 highlight (嵌套目录, 每 Pn-x 按所在 slide)
  hl-verify       highlight 质量验证 (annot/黄色像素/图片完整性)
  report          生成 8 列 CSV + 交付报告
  manual-list     生成人工下载清单 (付费墙/中文期刊 + 访问链接)

用法:
  python3.11 via54.py rules <project_dir> [--verbose]
  python3.11 via54.py step5 --project 雷管方案
  python3.11 via54.py highlight --project TMA                    # 默认 visual-v3 (推荐)
  python3.11 via54.py highlight --project TMA --mode plan-v3      # 用预存 vision plan 快速跑
  python3.11 via54.py highlight --project TMA --mode legacy-v10  # 旧 v10.1 line 模式 (历史)
  python3.11 via54.py highlight --project TMA --no-vision        # 不用 vision API
  python3.11 via54.py paper-match <pdf> <citation>
  python3.11 via54.py keyword "<citation>" "[context]"
  python3.11 via54.py ppt audit <input.pptx>
  python3.11 via54.py diff
  python3.11 via54.py all <project_dir>  # 跑全部
"""
import os, sys, json, argparse, subprocess
from pathlib import Path

# 让子工具可以被 import
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)


def _run_module(mod_name: str, args: list) -> int:
    """以子进程跑另一个脚本"""
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, mod_name)] + args
    return subprocess.call(cmd)


def cmd_rules(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir", help="项目根目录")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--quick", action="store_true", help="只看 OK/Fail")
    ns = parser.parse_args(args)
    argv = [ns.project_dir]
    if ns.verbose: argv.append("--verbose")
    if ns.quick: argv = ["quick-check", ns.project_dir]
    return _run_module("via54_rules.py", argv)


def cmd_step5(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", choices=["雷管方案", "TMA"])
    parser.add_argument("--csv", help="CSV 路径")
    parser.add_argument("--step3", help="下载目录")
    parser.add_argument("--step4", help="Highlight 目录")
    parser.add_argument("--out", help="输出目录")
    parser.add_argument("--convention", choices=["nested", "flat", "auto"], default="auto")
    ns = parser.parse_args(args)
    argv = []
    if ns.project: argv.extend(["--project", ns.project])
    if ns.csv: argv.extend(["--csv", ns.csv])
    if ns.step3: argv.extend(["--step3", ns.step3])
    if ns.step4: argv.extend(["--step4", ns.step4])
    if ns.out: argv.extend(["--out", ns.out])
    if ns.convention != "auto": argv.extend(["--convention", ns.convention])
    return _run_module("step5_alignment.py", argv)


def cmd_highlight(args):
    """
    Highlight 重新生成 (v3 FINAL + 9 铁律 + 视觉驱动)

    默认流程 (新):
      via54_ppt_visual_to_pdf.py - PPT 视觉 API 实时识别 + PDF 应证 + v3 FINAL 高亮
    快速流程 (有预存 vision plan 时):
      rerun_tma_highlight_v3_final.py - 用预存 vision plan 快速跑
    兼容模式 (历史参考):
      --mode legacy-v10 旧 v10.1 line 模式

    用法:
      python3 via54.py highlight --project TMA      # 默认 visual-v3, 跑所有 PDF
      python3 via54.py highlight --project TMA --mode plan-v3 --limit 5  # 快速流程
      python3 via54.py highlight --project TMA --mode legacy-v10  # 旧 v10.1
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", choices=["雷管方案", "TMA"], required=True)
    parser.add_argument("--mode", default="visual-v3",
                        choices=["visual-v3", "plan-v3", "line", "fill", "both", "legacy-v10"],
                        help="""默认 visual-v3 (PPT 视觉 API 实时识别 + 9 铁律)
                        plan-v3 = 用预存 vision plan 快速跑
                        legacy-v10 = 旧 v10.1 line 模式 (历史参考)""")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--no-vision", action="store_true",
                        help="不用 vision API (用 python-pptx fallback)")
    parser.add_argument("--no-rules", action="store_true",
                        help="不应用 9 条铁律")
    parser.add_argument("--slide", type=int, default=None,
                        help="只处理指定 slide (默认所有)")
    parser.add_argument("--pptx", default=None,
                        help="PPT 文件路径 (默认自动查找)")
    parser.add_argument("--pdf-dir", default=None,
                        help="PDF 目录 (默认 _2_pdfs)")
    parser.add_argument("--out-dir", default=None,
                        help="输出目录 (默认 _3_highlight_v10)")
    ns = parser.parse_args(args)

    # 选脚本
    if ns.mode == "legacy-v10":
        # 旧 v10.1 line 模式 (仅历史参考)
        if ns.project == "雷管方案":
            script = "rerun_leidafang_highlight_v10.py"
        else:
            script = "rerun_tma_highlight_v10.py"
        argv = ["--mode", "line"]
        if ns.limit: argv.extend(["--limit", str(ns.limit)])
        if ns.skip_existing: argv.append("--skip-existing")
        return _run_module(script, argv)

    # visual-v3 / plan-v3 都基于项目目录跑所有 PDF
    # 默认项目目录
    if ns.project == "雷管方案":
        proj_dir = os.environ.get("VIA54_LEIGUAN_DIR", "/Users/david/Desktop/雷管方案_文献整理")
    else:
        proj_dir = os.environ.get("VIA54_TMA_DIR", "/Users/david/Desktop/TMA_文献整理")

    # 找 PPT 文件
    pptx_path = ns.pptx or os.path.join(proj_dir, "PPT原版_雷管方案_三重获益_引领uHCC一线治疗_0622.pptx")
    if not os.path.exists(pptx_path):
        # TMA: 找顶层 .pptx
        for f in os.listdir(proj_dir):
            if f.endswith(".pptx"):
                pptx_path = os.path.join(proj_dir, f)
                break

    pdf_dir = ns.pdf_dir or os.path.join(proj_dir, "_2_pdfs")
    out_dir = ns.out_dir or os.path.join(proj_dir, "_3_highlight_v10")

    if not os.path.isdir(pdf_dir):
        print(f"错误: PDF 目录不存在 {pdf_dir}")
        return 1

    # 列出所有 PDF
    pdfs = sorted([f for f in os.listdir(pdf_dir) if f.endswith(".pdf") and f.startswith("P")])
    if ns.limit:
        pdfs = pdfs[:ns.limit]
    print(f"待处理 PDF: {len(pdfs)} (mode={ns.mode})")

    # 选脚本
    if ns.mode == "plan-v3":
        # 快速流程: 一次跑所有 Pn-x
        argv = []
        if ns.limit: argv.extend(["--limit", str(ns.limit)])
        return _run_module("rerun_tma_highlight_v3_final.py", argv)
    else:
        # 默认 visual-v3: 每 PDF 单独跑 (精确但慢)
        # 输出按 8 列标准嵌套: {Pn-x}/{Pn-x}_main.pdf, _highlight.pdf, _pages/
        script = "via54_ppt_visual_to_pdf.py"
        n_ok = 0
        for pdf_file in pdfs:
            pdf_in = os.path.join(pdf_dir, pdf_file)

            # 从文件名提取 slide (Pn-x: Pn=slide 页码, x=该页第几条引用; Pn-S23_5 → 23; P23-5 → 23)
            slide_num = None
            m = re.match(r"Pn-S(\d+)_(\d+)\.pdf", pdf_file) or re.match(r"P(\d+)-(\d+)\.pdf", pdf_file)
            if m:
                slide_num = int(m.group(1))

            argv = [pdf_in]
            if pptx_path and os.path.exists(pptx_path):
                argv.extend(["--pptx", pptx_path])
            if ns.no_vision: argv.append("--no-vision")
            if ns.no_rules: argv.append("--no-rules")
            if slide_num: argv.extend(["--slide", str(slide_num)])

            print(f"\n=== {pdf_file} (slide {slide_num}) ===", flush=True)
            rc = _run_module(script, argv)
            if rc == 0:
                n_ok += 1
        print(f"\n=== 总结: {n_ok}/{len(pdfs)} 成功 ===")
        return 0




def _tma_project_dir(ns):
    """解析项目根: --project-dir > TMA_PROJECT env > VIA54_TMA_DIR env"""
    if getattr(ns, "project_dir", None):
        return ns.project_dir
    return os.environ.get("TMA_PROJECT") or os.environ.get("VIA54_TMA_DIR") or "/Users/david/Desktop/TMA_文献整理"


def _run_tma(script, argv, project_dir):
    os.environ["TMA_PROJECT"] = project_dir
    print(f"[tma] project={project_dir} script={script} args={argv}", flush=True)
    return _run_module(script, argv)


def cmd_download(args):
    """TMA 文献级联下载: round1 = OA 级联 (OpenAlex/Unpaywall/EPMC/PMC/doi.org), round2 = CrossRef 重解析 + 内容核验 + Sci-Hub"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", default=None, help="项目根 (默认 TMA_PROJECT env)")
    parser.add_argument("--round2", action="store_true", help="用 round2 (CrossRef 重解析 DOI + 三维核验 + Sci-Hub 兜底)")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only", default=None, help="只处理指定引用, 逗号分隔")
    parser.add_argument("--sleep", type=float, default=0.5)
    ns = parser.parse_args(args)
    proj = _tma_project_dir(ns)
    script = "tma_download_round2.py" if ns.round2 else "tma_cascade_download.py"
    argv = []
    if ns.limit: argv.extend(["--limit", str(ns.limit)])
    if ns.only: argv.extend(["--only", ns.only])
    if ns.sleep != 0.5: argv.extend(["--sleep", str(ns.sleep)])
    return _run_tma(script, argv, proj)


def cmd_pdf_verify(args):
    """下载后 PDF 内容核验 (期刊/年份/作者匹配)"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", default=None)
    parser.add_argument("--only", default=None)
    ns = parser.parse_args(args)
    argv = []
    if ns.only: argv.extend(["--only", ns.only])
    return _run_tma("tma_verify_pdfs.py", argv, _tma_project_dir(ns))


def cmd_hl_batch(args):
    """批量 highlight: 嵌套目录 + 每 Pn-x 用其所在 slide (v3 FINAL rect + 9 铁律)"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", default=None)
    parser.add_argument("--force", action="store_true", help="已存在输出也重跑")
    parser.add_argument("--only", default=None)
    ns = parser.parse_args(args)
    argv = []
    if ns.force: argv.append("--force")
    if ns.only: argv.extend(["--only", ns.only])
    return _run_tma("tma_batch_highlight.py", argv, _tma_project_dir(ns))


def cmd_hl_verify(args):
    """highlight 质量验证 (annot/黄色像素/图片完整性/pages 子目录)"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", default=None)
    parser.add_argument("--only", default=None)
    ns = parser.parse_args(args)
    argv = []
    if ns.only: argv.extend(["--only", ns.only])
    return _run_tma("tma_verify_highlights.py", argv, _tma_project_dir(ns))


def cmd_report(args):
    """生成 89 行 8 列 CSV + 交付报告 md"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", default=None)
    ns = parser.parse_args(args)
    return _run_tma("tma_final_report.py", [], _tma_project_dir(ns))


def cmd_manual_list(args):
    """生成人工下载清单 (付费墙/中文期刊 + DOI/PubMed/万方/知网链接)"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", default=None)
    ns = parser.parse_args(args)
    return _run_tma("tma_manual_list.py", [], _tma_project_dir(ns))


def cmd_paper_match(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["verify", "search"])
    parser.add_argument("arg1")
    parser.add_argument("arg2", nargs="?")
    ns = parser.parse_args(args)
    if ns.mode == "verify":
        if not ns.arg2:
            print("Usage: paper-match verify <pdf> <citation>")
            return 1
        return _run_module("l0_paper_match.py", ["verify", ns.arg1, ns.arg2])
    else:
        return _run_module("l0_paper_match.py", ["search", ns.arg1])


def cmd_keyword(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("citation")
    parser.add_argument("context", nargs="?", default="")
    parser.add_argument("--demo", action="store_true")
    ns = parser.parse_args(args)
    if ns.demo:
        return _run_module("l4_keyword_extract.py", ["demo"])
    argv = ["extract", ns.citation]
    if ns.context: argv.append(ns.context)
    return _run_module("l4_keyword_extract.py", argv)


def cmd_ppt(args):
    parser = argparse.ArgumentParser()
    parser.add_argument("subcmd", choices=["audit", "expand", "render", "all"])
    parser.add_argument("input_pptx")
    parser.add_argument("out", nargs="?")
    parser.add_argument("--margin-pt", type=float, default=20)
    parser.add_argument("--dpi", type=int, default=150)
    ns = parser.parse_args(args)
    argv = [ns.subcmd, ns.input_pptx]
    if ns.out: argv.append(ns.out)
    if ns.margin_pt != 20: argv.extend(["--margin-pt", str(ns.margin_pt)])
    if ns.dpi != 150: argv.extend(["--dpi", str(ns.dpi)])
    return _run_module("ppt_expand.py", argv)


def cmd_diff(args):
    return _run_module("multi_project_diff.py", [])


def cmd_all(args):
    """跑全部: rules + step5 + diff"""
    if not args:
        # 默认跑两个项目
        for proj in ["/Users/david/Desktop/雷管方案_文献整理",
                     "/Users/david/Desktop/TMA_文献整理"]:
            if os.path.isdir(proj):
                print(f"\n=== Rules check: {proj} ===")
                _run_module("via54_rules.py", [proj])
                print(f"\n=== Step 5: {proj} ===")
                # 自动检测 project 名
                if "雷管方案" in proj:
                    _run_module("step5_alignment.py", ["--project", "雷管方案"])
                elif "TMA" in proj:
                    _run_module("step5_alignment.py", ["--project", "TMA"])
        print(f"\n=== Multi-project diff ===")
        _run_module("multi_project_diff.py", [])
    else:
        for proj in args:
            _run_module("via54_rules.py", [proj])
    return 0


def cmd_glm(args):
    """GLM 集成层直接调用"""
    return _run_module("glm_integration.py", args)


HANDLERS = {
    "rules": cmd_rules,
    "step5": cmd_step5,
    "highlight": cmd_highlight,
    "paper-match": cmd_paper_match,
    "keyword": cmd_keyword,
    "ppt": cmd_ppt,
    "download": cmd_download,
    "pdf-verify": cmd_pdf_verify,
    "hl-batch": cmd_hl_batch,
    "hl-verify": cmd_hl_verify,
    "report": cmd_report,
    "manual-list": cmd_manual_list,
    "diff": cmd_diff,
    "glm": cmd_glm,
    "all": cmd_all,
}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    rest = sys.argv[2:]
    handlers = HANDLERS

    if cmd not in handlers:
        print(f"未知命令: {cmd}")
        print(f"可用: {list(handlers.keys())}")
        sys.exit(1)

    sys.exit(handlers[cmd](rest) or 0)


if __name__ == "__main__":
    main()
