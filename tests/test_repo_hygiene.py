"""仓库卫生防护 —— 钉住两类会静默退化的不变量。

1) 工具链镜像一致
   ``scripts/hl_v3_final/`` 与 ``skills/via54medit-literature-pipeline/scripts/`` 是同一套
   高亮工具链的两份副本, 且**两侧各有引用方**:

   - ``scripts/hl_v3_final/``: CI 的 ``working-directory``、``scripts/auto_sync.py`` 的
     定时自测路径、7 个 ``scripts/*.py`` 的 ``sys.path.insert``、``.trae/rules/project_rules.md``、
     ``.cursorrules``、``.github/copilot-instructions.md``、``AGENTS.md`` 与多份 ``docs/``。
   - 技能目录那份: 两个 SKILL.md 通过 ``~/.hermes/skills/...`` 镜像路径引用
     (``via54medit-ppt-citation-analysis``、``via54-tma-literature-workflow``)。

   两份都不能删 —— 技能必须自包含才能被镜像分发, 而 ``scripts/`` 那份是仓库内的运行路径。
   所以这里不主张删除, 而是断言「两侧逐字节一致」: 一旦有人只改一侧, 测试立刻失败,
   而不是让分叉静默存在。这正是 ``list_citations`` v1/v2 那类问题的成因。

2) 命令注册无重复
   ``cmd/medit`` 里同一个 cobra 命令变量不应被 ``rootCmd.AddCommand`` 注册多次, 否则
   ``medit --help`` 会把同名命令列两遍 (2026-09-11 修过一次: anno2ppt / pico / systematic /
   grade 各挂了两遍)。这里加静态防护。
"""
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIRROR_A = os.path.join(REPO, "scripts", "hl_v3_final")
MIRROR_B = os.path.join(REPO, "skills", "via54medit-literature-pipeline", "scripts")

# 缓存目录不参与比对 —— 两侧各自跑测试会生成不同的 .pyc
IGNORE_DIRS = {"__pycache__", ".pytest_cache"}


class TestToolchainMirror(unittest.TestCase):
    """技能分发包不得携带过期的高亮工具链。

    A (权威, 开发位置) = ``scripts/hl_v3_final/``
    B (分发副本)       = ``skills/via54medit-literature-pipeline/scripts/``

    不变量: **A 的每个文件都必须在 B 中按映射存在且内容一致** —— 即"分发包不含旧副本、
    也不缺文件"。反向不成立: B 独有辅助脚本不算漂移（技能自带的东西）。

    历史教训: 这个同步原本是手工做的 (提交 01a9452 只同步了 2 个文件), 于是 4 天内 B 就
    少了 A 在 2026-09-07 新增的 5 个 OCR/版面脚本、vision_check.py 也停在旧版。
    漂移的修法是 ``python3 scripts/sync_skill_bundle.py``, 本测试负责让它不会静默发生。
    """

    # A 侧目录名 -> B 侧目录名: 两侧目录名各自的引用方都还在用, 故不重命名, 只做映射
    DIR_RENAME = {"examples": "hl_pnx_examples"}

    @classmethod
    def _snapshot(cls, root):
        files = {}
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
            for name in filenames:
                if name.endswith(".pyc"):
                    continue
                full = os.path.join(dirpath, name)
                with open(full, "rb") as fp:
                    files[os.path.relpath(full, root)] = fp.read()
        return files

    @classmethod
    def _map(cls, rel):
        parts = rel.split(os.sep)
        if parts and parts[0] in cls.DIR_RENAME:
            parts[0] = cls.DIR_RENAME[parts[0]]
        return os.path.join(*parts)

    def test_authoritative_tree_is_fully_mirrored(self):
        self.assertTrue(os.path.isdir(MIRROR_A), f"缺少权威目录 {MIRROR_A}")
        self.assertTrue(os.path.isdir(MIRROR_B), f"缺少分发包 {MIRROR_B}")

        src = self._snapshot(MIRROR_A)
        dst = self._snapshot(MIRROR_B)
        self.assertGreater(len(src), 50, "权威侧快照文件数异常偏少, 检查路径")

        missing = sorted(rel for rel in src if self._map(rel) not in dst)
        self.assertEqual(
            missing, [],
            f"分发包缺少这些文件 (跑 scripts/sync_skill_bundle.py): {missing[:8]}",
        )

        stale = sorted(
            rel for rel in src
            if src[rel] != dst[self._map(rel)]
        )
        self.assertEqual(
            stale, [],
            f"分发包里的这些文件已过期 (跑 scripts/sync_skill_bundle.py): {stale[:8]}",
        )


class TestCommandRegistration(unittest.TestCase):
    """同一命令变量不得被 rootCmd 重复挂载。"""

    def test_no_duplicate_root_registration(self):
        cmds_dir = os.path.join(REPO, "cmd", "medit", "commands")
        self.assertTrue(os.path.isdir(cmds_dir), f"缺少 {cmds_dir}")

        counts = {}
        for name in sorted(os.listdir(cmds_dir)):
            if not name.endswith(".go") or name.endswith("_test.go"):
                continue
            with open(os.path.join(cmds_dir, name), encoding="utf-8") as fp:
                for line in fp:
                    stripped = line.lstrip()
                    if stripped.startswith("//"):
                        continue
                    hit = re.search(r"rootCmd\.AddCommand\((\w+)\)", line)
                    if hit:
                        counts.setdefault(hit.group(1), []).append(name)

        self.assertGreater(len(counts), 10, "解析到的注册项过少, 检查正则是否失效")
        duplicated = {k: v for k, v in counts.items() if len(v) > 1}
        self.assertEqual(duplicated, {}, f"这些命令被重复注册: {duplicated}")


if __name__ == "__main__":
    unittest.main()
