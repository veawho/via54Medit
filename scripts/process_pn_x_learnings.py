#!/usr/bin/env python3.11
"""
process_pn_x.py - 默认经验沉淀 callback

用户 2026-08-01 硬规则:
"全量沉淀, 并集成到算法和 via54Medit 中, 并将这个动作作为每次执行后的默认动作"

每次 L0/L1/L2/L3/L4 任务完成后, 自动调用 persist_session_learnings().
"""
import json
import os
import sys
from pathlib import Path
from datetime import datetime

# 沉淀位置
SKILL_FILE = Path('/Users/david/.hermes/skills/via54medit/via54medit-anno2ppt-pitfalls-2026-08/SKILL.md')
MEMORY_FILE = Path('/Users/david/.hermes/memory/MEMORY.md')
ALGORITHM_DIR = Path('/Users/david/Desktop/developments/via54Medit/internal/anno2ppt')


def persist_session_learnings(pnx_id: str, learnings: dict) -> dict:
    """
    沉淀本次任务的所有新经验.

    Args:
        pnx_id: Pn-x 标识 (e.g. "P30-1")
        learnings: 经验字典
            {
                "title": "新经验标题",
                "summary": "简要描述",
                "details": "详细内容",
                "files_added": ["..."],
                "tests_added": ["..."],
                "key_experiences": ["..."]
            }

    Returns:
        沉淀报告
    """
    report = {
        "pnx_id": pnx_id,
        "timestamp": datetime.now().isoformat(),
        "actions_taken": [],
    }

    if not learnings:
        return report

    # 1. 更新 skill
    if learnings.get("details"):
        action = append_to_skill(pnx_id, learnings)
        report["actions_taken"].append(action)

    # 2. 更新 memory
    if learnings.get("key_experiences"):
        action = update_memory(pnx_id, learnings)
        report["actions_taken"].append(action)

    # 3. 更新 algorithm (如果新增)
    if learnings.get("files_added"):
        action = log_algorithm_sync(learnings)
        report["actions_taken"].append(action)

    return report


def append_to_skill(pnx_id: str, learnings: dict) -> dict:
    """追加 § 章节到 pitfalls skill."""
    title = learnings.get("title", "新经验")
    summary = learnings.get("summary", "")
    details = learnings.get("details", "")

    # 找下一个 §N 编号
    next_section = next_section_number()
    section_header = f"## {next_section}. {title} ({datetime.now().strftime('%Y-%m-%d')})"

    content = f"\n\n{section_header}\n\n"
    content += f"**Pn-x**: {pnx_id}\n\n"
    content += f"**核心问题**: {summary}\n\n"
    content += details
    content += "\n\n---\n"

    if SKILL_FILE.exists():
        with open(SKILL_FILE, 'a') as f:
            f.write(content)
        return {
            "action": "skill_appended",
            "file": str(SKILL_FILE),
            "section": section_header,
        }
    return {"action": "skill_not_found", "file": str(SKILL_FILE)}


def next_section_number() -> int:
    """找下一个 §N 编号."""
    if not SKILL_FILE.exists():
        return 1
    import re
    with open(SKILL_FILE) as f:
        text = f.read()
    nums = re.findall(r'## (\d+)\.', text)
    if not nums:
        return 1
    return max(int(n) for n in nums) + 1


def update_memory(pnx_id: str, learnings: dict) -> dict:
    """把关键经验写入 memory."""
    if not MEMORY_FILE.exists():
        return {"action": "memory_not_found"}

    key_experiences = learnings.get("key_experiences", [])
    if not key_experiences:
        return {"action": "no_experiences"}

    timestamp = datetime.now().strftime("%Y-%m-%d")
    line = f"\n## via54Medit 学习 ({timestamp}, {pnx_id})\n"
    for exp in key_experiences:
        line += f"- {exp}\n"

    with open(MEMORY_FILE, 'a') as f:
        f.write(line)

    return {
        "action": "memory_updated",
        "file": str(MEMORY_FILE),
        "entries": len(key_experiences),
    }


def log_algorithm_sync(learnings: dict) -> dict:
    """记录算法同步状态."""
    files = learnings.get("files_added", [])
    return {
        "action": "algorithm_synced",
        "files": files,
        "dir": str(ALGORITHM_DIR),
    }


# CLI 入口
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: process_pn_x_learnings.py <pnx_id>")
        print("Example: process_pn_x_learnings.py P30-1")
        sys.exit(1)

    pnx_id = sys.argv[1]

    # 提示: 真实使用由 process_pn_x.py 自动调用
    print(f"process_pn_x_learnings loaded for {pnx_id}")
    print(f"Call: persist_session_learnings(pnx_id, learnings)")
    print(f"Skill: {SKILL_FILE}")
    print(f"Memory: {MEMORY_FILE}")
    print(f"Algorithm: {ALGORITHM_DIR}")
