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

    def test_no_unexpected_bundle_only_files(self):
        """反向: 分发包**独有**的文件必须全部在 ``sync_skill_bundle.py`` 的白名单里。

        为什么需要这条: 分发包独有文件本身是允许的 (技能自带的辅助脚本), 但原先"允许"
        只是报告里一句"目标独有, 不处理" —— 于是「有意保留的辅助脚本」与「谁手滑放进来的
        文件」在报告里长得一模一样。有了白名单, 意外多出的文件会被直接判失败。

        白名单以 ``sync_skill_bundle.py`` 的 ``BUNDLE_ONLY_OK`` 为**唯一事实来源**,
        避免两处各维护一份而再次分叉。
        """
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "sync_skill_bundle_probe",
            os.path.join(REPO, "scripts", "sync_skill_bundle.py"))
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)

        dst = self._snapshot(MIRROR_B)
        reverse = {v: k for k, v in self.DIR_RENAME.items()}

        unexpected = []
        for rel in dst:
            parts = rel.split(os.sep)
            if parts[0] in reverse:
                parts[0] = reverse[parts[0]]
            if not os.path.exists(os.path.join(MIRROR_A, *parts)):
                if rel not in tool.BUNDLE_ONLY_OK:
                    unexpected.append(rel)

        self.assertEqual(
            unexpected, [],
            "分发包里出现了白名单之外的独有文件 —— 要么删掉它, 要么确认它属于分发包后"
            f"加进 sync_skill_bundle.py 的 BUNDLE_ONLY_OK: {unexpected}")

    def test_bundle_only_allowlist_entries_still_exist(self):
        """白名单不该留"僵尸条目" —— 文件已被删掉时也要把条目一起清掉。"""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "sync_skill_bundle_probe2",
            os.path.join(REPO, "scripts", "sync_skill_bundle.py"))
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)

        stale = [rel for rel in tool.BUNDLE_ONLY_OK
                 if not os.path.exists(os.path.join(MIRROR_B, rel))]
        self.assertEqual(
            stale, [],
            f"BUNDLE_ONLY_OK 里这些条目已不存在于分发包, 应删除: {stale}")


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


class TestFitzImportForm(unittest.TestCase):
    """高亮工具链不得再出现裸 ``import fitz``。

    为什么值得设成不变量: PyMuPDF 1.24 起 ``fitz`` 只是别名, 用它会在 stderr 打一行
    弃用警告, 且官方已声明将来会**移除**该别名 —— 到那天全部脚本一起坏。所以统一写成
    ``import pymupdf as fitz`` + 旧版回退。

    实测: 2026-09-11 前 ``scripts/hl_v3_final/`` 下有 **195 处**裸 ``import fitz``
    (117 个文件; 其中 182 处在 105 个 ``examples/hl_p*.py`` 里, 以函数内局部导入的形式)。
    v5.4.20 全部改掉: 核心文件写完整 try/except, 示例脚本改为 ``from hl_lib import fitz``
    (它们本来就依赖 hl_lib, 由那一处统一决定导入名)。

    本测试把允许的形态钉死:
      * ``from hl_lib import fitz, ...``            —— 允许 (示例脚本走这条)
      * ``import pymupdf as fitz``                  —— 允许
      * ``import fitz`` 紧跟 ``except ImportError:`` —— 允许 (旧版回退)
      * 其它任何 ``import fitz`` / ``import fitz, x`` —— 不允许
    """

    def test_no_bare_fitz_import(self):
        offenders = []
        for root, dirs, files in os.walk(MIRROR_A):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                path = os.path.join(root, fn)
                with open(path, encoding="utf-8") as f:
                    lines = f.read().split("\n")
                for i, line in enumerate(lines):
                    m = re.match(r"^(\s*)import\s+fitz\s*(,.*)?$", line)
                    if not m:
                        continue
                    if m.group(2):                      # import fitz, x —— 复合形式
                        offenders.append((path, i + 1, line.strip()))
                        continue
                    prev = lines[i - 1].strip() if i else ""
                    if not prev.startswith("except ImportError"):
                        offenders.append((path, i + 1, line.strip()))

        rel = [f"{os.path.relpath(p, REPO)}:{n}  {t}" for p, n, t in offenders]
        self.assertEqual(
            rel, [],
            "这些位置用了裸 import fitz (应为 `import pymupdf as fitz` + except ImportError 回退, "
            "或示例脚本的 `from hl_lib import fitz`):\n  " + "\n  ".join(rel))

    def test_fitz_alias_resolves_to_pymupdf(self):
        """``hl_lib.fitz`` 必须是 pymupdf 模块本身 —— 示例脚本都靠它取导入名。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "hl_lib_probe", os.path.join(MIRROR_A, "hl_lib.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(getattr(mod.fitz, "__name__", ""), "pymupdf")


if __name__ == "__main__":
    unittest.main()
