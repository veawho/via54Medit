#!/usr/bin/env python3
"""
skills_bootstrap.py — 仓库 vendored skills ↔ 本机 skills 目录一键同步

背景 (2026-08-21): 与 via54Medit 代码/算法强绑定的核心 skills 已 vendored 到
仓库 skills/ (SKILL.md + references + scripts)。本脚本把它们同步到本机
skills 目录 (默认 ~/.hermes/skills), 新设备部署后一条命令接入全部核心经验。

用法:
  python skills_bootstrap.py [--dest DIR] [--dry-run] [--force] [--list]

  --list      列出仓库将安装的 skills (不执行)
  --dry-run   只显示将复制的文件
  --force     覆盖已存在且内容不同的 skills (默认: 差异时提示并跳过)
  --dest DIR  目标根 (默认: ~/.hermes/skills)

幂等: 内容一致的文件跳过; 目录不存在自动创建。
"""
import argparse
import filecmp
import os
import shutil
import sys

REPO_SKILLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills")


def list_vendored():
    """返回仓库 skills/ 下的一级目录名 (即 skill 名)"""
    if not os.path.isdir(REPO_SKILLS):
        return []
    return sorted(d for d in os.listdir(REPO_SKILLS)
                  if os.path.isdir(os.path.join(REPO_SKILLS, d)))


def sync_skill(name, dest_root, dry_run, force):
    """同步单个 skill; 返回 (copied, skipped, updated)"""
    src = os.path.join(REPO_SKILLS, name)
    dst = os.path.join(dest_root, name)
    copied = skipped = updated = 0
    for root, _dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        for f in files:
            sfile = os.path.join(root, f)
            dfile = os.path.join(dst, rel, f) if rel != "." else os.path.join(dst, f)
            if os.path.exists(dfile) and filecmp.cmp(sfile, dfile, shallow=False):
                skipped += 1
                continue
            if os.path.exists(dfile) and not force:
                print("  ~ %s 已存在且内容不同 (--force 覆盖)" % os.path.relpath(dfile, dest_root), flush=True)
                skipped += 1
                continue
            if not dry_run:
                os.makedirs(os.path.dirname(dfile), exist_ok=True)
                shutil.copy2(sfile, dfile)
            print("  %s %s" % ("[dry-run]" if dry_run else "[copy]", os.path.relpath(dfile, dest_root)), flush=True)
            if os.path.exists(dfile) and not dry_run:
                updated += 1
            else:
                copied += 1
    return copied, skipped, updated


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", default=os.path.join(os.path.expanduser("~"), ".hermes", "skills"),
                    help="目标 skills 根目录 (默认 ~/.hermes/skills)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    names = list_vendored()
    if not names:
        print("仓库 skills/ 为空或不存在: %s" % REPO_SKILLS)
        return 1
    if args.list:
        print("仓库 vendored skills (%d 项):" % len(names))
        for n in names:
            size = sum(os.path.getsize(os.path.join(REPO_SKILLS, n, f))
                       for f in os.listdir(os.path.join(REPO_SKILLS, n))
                       if os.path.isfile(os.path.join(REPO_SKILLS, n, f)))
            print("  - %s (%.1f KB 顶层文件)" % (n, size / 1024))
        return 0

    print("== skills bootstrap: %s → %s ==" % (REPO_SKILLS, args.dest))
    total = {"copied": 0, "skipped": 0, "updated": 0}
    for n in names:
        print("[%s]" % n, flush=True)
        c, s, u = sync_skill(n, args.dest, args.dry_run, args.force)
        total["copied"] += c
        total["skipped"] += s
        total["updated"] += u
    print("== 完成: 复制 %d / 更新 %d / 跳过 %d %s ==" % (
        total["copied"], total["updated"], total["skipped"],
        "(dry-run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
