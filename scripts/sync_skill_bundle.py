#!/usr/bin/env python3
"""把权威高亮工具链同步到技能分发包。

背景
----
同一套高亮工具链存在两份:

  A (权威, 开发位置)  ``scripts/hl_v3_final/``
  B (分发副本)        ``skills/via54medit-literature-pipeline/scripts/``

两侧各有引用方, 都不能删:

  - A: CI 的 ``working-directory``、``scripts/auto_sync.py`` 的定时自测路径、
       7 个 ``scripts/*.py`` 的 ``sys.path.insert``、``.trae/rules/project_rules.md``、
       ``.cursorrules``、``.github/copilot-instructions.md``、``AGENTS.md`` 与多份 ``docs/``。
  - B: 技能必须**自包含**才能被镜像/分发到 ``~/.hermes/skills/``; 有两个 SKILL.md 按
       ``~/.hermes/skills/...`` 路径引用它。

历史上这个同步是手工做的 (见提交 ``01a9452``, 当时只同步了 2 个文件), 所以在 4 天内又
漂了 —— B 缺少 A 在 2026-09-07 新增的 5 个 OCR/版面脚本, ``vision_check.py`` 也停在旧版。
本脚本把手动动作变成可重复的一步。

用法
----
    python3 scripts/sync_skill_bundle.py --check   # 只报告差异, 不写
    python3 scripts/sync_skill_bundle.py           # 执行同步 (A -> B)

约定
----
- 方向恒为 A -> B。A 是权威, 不要反向覆盖。
- 目录名映射: A 的 ``examples/`` 对应 B 的 ``hl_pnx_examples/``。两侧目录名各自的引用方
  都还在用 (``docs/6_step_sop.md`` 指 A 的 ``examples/``; 两份 SKILL.md 指 B 的
  ``hl_pnx_examples/``), 故不做重命名, 只在此处声明映射。
- B 中 A 没有的文件**不动** (属分发包自带的辅助脚本), 仅列出提示。
"""
from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "scripts", "hl_v3_final")
DST = os.path.join(REPO, "skills", "via54medit-literature-pipeline", "scripts")

# A 侧目录名 -> B 侧目录名
DIR_RENAME = {"examples": "hl_pnx_examples"}

IGNORE_DIRS = {"__pycache__", ".pytest_cache"}


def iter_files(root):
    """产出 (相对路径, 绝对路径)。跳过缓存目录与 .pyc。"""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for name in filenames:
            if name.endswith(".pyc"):
                continue
            full = os.path.join(dirpath, name)
            yield os.path.relpath(full, root), full


def map_rel(rel):
    """把 A 侧相对路径映射为 B 侧的对应相对路径。"""
    parts = rel.split(os.sep)
    if parts and parts[0] in DIR_RENAME:
        parts[0] = DIR_RENAME[parts[0]]
    return os.path.join(*parts)


def main():
    ap = argparse.ArgumentParser(description="同步 hl_v3_final -> 技能分发包")
    ap.add_argument("--check", action="store_true", help="只报告差异, 不写文件")
    args = ap.parse_args()

    if not os.path.isdir(SRC) or not os.path.isdir(DST):
        print(f"路径缺失: SRC={SRC} DST={DST}", file=sys.stderr)
        return 2

    missing, differing = [], []
    for rel, full in iter_files(SRC):
        target = os.path.join(DST, map_rel(rel))
        if not os.path.exists(target):
            missing.append((rel, target))
        elif not filecmp.cmp(full, target, shallow=False):
            differing.append((rel, target))

    dst_only = []
    reversed_rename = {v: k for k, v in DIR_RENAME.items()}
    for rel, _ in iter_files(DST):
        parts = rel.split(os.sep)
        if parts and parts[0] in reversed_rename:
            parts[0] = reversed_rename[parts[0]]
        if not os.path.exists(os.path.join(SRC, *parts)):
            dst_only.append(rel)

    print(f"源 (权威): {SRC}")
    print(f"目标 (分发): {DST}")
    print(f"  需新增 {len(missing)} 个, 需更新 {len(differing)} 个, "
          f"目标独有 {len(dst_only)} 个")

    for rel, _ in missing:
        print(f"    + {rel}")
    for rel, _ in differing:
        print(f"    ~ {rel}")
    for rel in dst_only:
        print(f"    ? {rel}  (目标独有, 不处理)")

    if args.check:
        return 1 if (missing or differing) else 0
    if not (missing or differing):
        print("已一致, 无需同步。")
        return 0

    for rel, target in missing + differing:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(os.path.join(SRC, rel), target)
    print(f"已同步 {len(missing) + len(differing)} 个文件 (A -> B)。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
