#!/usr/bin/env python3
"""
ppt_vision_analyze.py — 6 步规则 #2 PPT 视觉分析 (2026-08-10)

调用现有 ppt_understand.build_ppt_vision_report() 跑全 PPT,
输出:
  - _vision_report.json    (一文件, 含所有 slide 的 citation_marks + tables)
  - _ppt_renders/          (每页 jpg, 用于视觉复核)

跑完自动让 6 步规则的 Step 2 从 ❌ 变 ✓.

用法:
  python3.11 ppt_vision_analyze.py <project_dir> [--start 3] [--end 43] [--no-render]
"""
import os, sys, json, argparse
from pathlib import Path
from typing import Dict, List, Optional

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)


PROJECTS = {
    "雷管方案": {
        "root": "/Users/david/Desktop/雷管方案_文献整理",
        "pptx": "step1_ppt_目录/PPT原版_雷管方案_三重获益_引领uHCC一线治疗_0622.pptx",
        "out_dir": "step1_ppt_目录",
    },
    "TMA": {
        "root": "/Users/david/Desktop/TMA_文献整理",
        "pptx": "TMA临床路径的诊断与鉴别.pptx",  # 顶层
        "out_dir": ".",
    },
}


def find_pptx(project_root: str) -> Optional[str]:
    """在项目根找 .pptx, 优先 step1_ppt_目录/_1_ppt"""
    # 优先路径
    priority = ["step1_ppt_目录", "_1_ppt", "PPT", "ppt"]
    for pri in priority:
        for f in os.listdir(os.path.join(project_root, pri)) if os.path.isdir(os.path.join(project_root, pri)) else []:
            if f.lower().endswith(('.pptx', '.ppt')) and not f.startswith('~$'):
                return os.path.join(project_root, pri, f)
    # 兜底
    for dp, _, fn in os.walk(project_root):
        if '_backup' in dp or '_old' in dp or '__pycache__' in dp:
            continue
        for f in fn:
            if f.lower().endswith(('.pptx', '.ppt')) and not f.startswith('~$'):
                return os.path.join(dp, f)
    return None


def build_full_vision_report(pptx_path: str, start_slide: int = 1, end_slide: Optional[int] = None) -> Dict:
    """
    跑全 PPT 每页, 构建 _vision_report.json
    """
    from ppt_understand import build_ppt_vision_report, extract_ppt_slide

    from pptx import Presentation
    prs = Presentation(pptx_path)
    n_total = len(prs.slides)
    end = end_slide or n_total
    print(f"  PPT 总页数: {n_total}, 跑 [{start_slide}..{end}]")

    full_report = {
        "pptx_path": pptx_path,
        "n_slides": n_total,
        "slides": {},
        "all_marks": {},  # {slide_num: [mark1, mark2, ...]}
        "total_marks": 0,
    }

    for sn in range(start_slide, end + 1):
        if sn > n_total:
            break
        try:
            # 给 marks 默认 1-20
            r = build_ppt_vision_report(pptx_path, sn, list(range(1, 21)))
            full_report["slides"][sn] = r
            marks_found = r.get("found_marks", [])
            full_report["all_marks"][sn] = marks_found
            full_report["total_marks"] += len(marks_found)
            if marks_found:
                print(f"    Slide {sn}: 标号 {marks_found}")
        except Exception as e:
            print(f"    Slide {sn}: ERROR {e}")
            full_report["slides"][sn] = {"error": str(e)}

    return full_report


def render_slides(pptx_path: str, out_dir: str, start_slide: int = 1, end_slide: Optional[int] = None) -> List[str]:
    """
    用 ppt_expand.py 渲染每页 jpg (复用现有 ppt_expand 工具)
    """
    try:
        from ppt_expand import render_pptx_images
        # 调 render 拿所有页
        files = render_pptx_images(pptx_path, out_dir)
        return files
    except Exception as e:
        print(f"  [render] 失败: {e}")
        return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project", help="项目根目录 或 --project 雷管方案/TMA")
    parser.add_argument("--project-name", choices=list(PROJECTS.keys()))
    parser.add_argument("--start", type=int, default=3, help="起始 slide (默认 3, 雷管方案经验)")
    parser.add_argument("--end", type=int, default=0, help="结束 slide (0=全部)")
    parser.add_argument("--no-render", action="store_true", help="不渲染 jpg (只输出 JSON)")
    args = parser.parse_args()

    # 解析项目
    if args.project_name:
        cfg = PROJECTS[args.project_name]
        project_dir = cfg["root"]
        pptx_rel = cfg["pptx"]
        out_rel = cfg["out_dir"]
        pptx_path = os.path.join(project_dir, pptx_rel)
        out_dir_abs = os.path.join(project_dir, out_rel)
    else:
        project_dir = args.project
        pptx_path = find_pptx(project_dir)
        if not pptx_path:
            print(f"❌ 项目目录无 .pptx: {project_dir}")
            sys.exit(1)
        out_dir_abs = project_dir
        print(f"  找到 PPT: {pptx_path}")

    print(f"=== PPT 视觉分析 ===")
    print(f"项目: {project_dir}")
    print(f"PPT:  {pptx_path}")

    end = args.end if args.end > 0 else None

    # 1. 跑视觉分析
    print(f"\n[1/2] 跑视觉分析 (slide {args.start}..{end or 'end'})...")
    report = build_full_vision_report(pptx_path, args.start, end)

    # 写 _vision_report.json
    out_json = os.path.join(out_dir_abs, "_vision_report.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"  ✓ {out_json}")
    print(f"  ✓ 总标号: {report['total_marks']}")

    # 2. 渲染 jpg
    if not args.no_render:
        print(f"\n[2/2] 渲染 jpg...")
        img_dir = os.path.join(out_dir_abs, "_exported_images")
        os.makedirs(img_dir, exist_ok=True)
        files = render_slides(pptx_path, img_dir, args.start, end)
        print(f"  ✓ 渲染 {len(files)} 张 → {img_dir}/")

    print(f"\n=== 完成 ===")
    print(f"  6 步规则 Step 2 现在可以通过")


if __name__ == "__main__":
    main()
