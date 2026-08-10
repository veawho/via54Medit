#!/usr/bin/env python3
"""
via54.py — via54Medit 统一入口 (2026-08-10)

整合所有 v10 工具, 一个 CLI 全跑.

子命令:
  rules           6 步规则校验
  step5           Step 5 三方对齐
  highlight       Highlight 重新生成 (v10.1)
  paper-match     L0 错论文校验
  keyword         L4 关键词抽取
  ppt             PPT 扩页 + 审计 + 渲染
  diff            双项目对比
  all             跑全部

用法:
  python3.11 via54.py rules <project_dir> [--verbose]
  python3.11 via54.py step5 --project 雷管方案
  python3.11 via54.py highlight --project TMA --mode line
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", choices=["雷管方案", "TMA"], required=True)
    parser.add_argument("--mode", default="line", choices=["line", "fill", "both"])
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip-existing", action="store_true")
    ns = parser.parse_args(args)
    if ns.project == "雷管方案":
        script = "rerun_leidafang_highlight_v10.py"
    else:
        script = "rerun_tma_highlight_v10.py"
    argv = ["--mode", ns.mode]
    if ns.limit: argv.extend(["--limit", str(ns.limit)])
    if ns.skip_existing: argv.append("--skip-existing")
    return _run_module(script, argv)


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


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    rest = sys.argv[2:]

    handlers = {
        "rules": cmd_rules,
        "step5": cmd_step5,
        "highlight": cmd_highlight,
        "paper-match": cmd_paper_match,
        "keyword": cmd_keyword,
        "ppt": cmd_ppt,
        "diff": cmd_diff,
        "all": cmd_all,
    }

    if cmd not in handlers:
        print(f"未知命令: {cmd}")
        print(f"可用: {list(handlers.keys())}")
        sys.exit(1)

    sys.exit(handlers[cmd](rest) or 0)


if __name__ == "__main__":
    main()
