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
    """仓库内不得再出现裸 ``import fitz``。

    为什么值得设成不变量: PyMuPDF 1.24 起 ``fitz`` 只是别名, 用它会在 stderr 打一行
    弃用警告, 且官方已声明将来会**移除**该别名 —— 到那天全部脚本一起坏。
    ``requirements.txt`` 已声明 ``pymupdf>=1.24``, 所以 ``import pymupdf as fitz``
    就是正确形态, 不需要旧版回退。

    历史 (2026-09-11 的两轮):
      * ``hl_v3_final/`` **195 处 / 117 文件**(182 处在 105 个 examples 脚本里, 函数内局部导入)
        -> 核心文件写 try/except, 示例脚本改为 ``from hl_lib import fitz``。
      * ``scripts/`` + ``skills/`` **83 处 / 63 文件** -> 统一 ``import pymupdf as fitz``。

    **这条测试的第一版有盲区**: 它只匹配「行首 ``import fitz``」, 于是
    ``import json, os, re, io, sys, fitz``(fitz 在逗号列表末尾) 这类被漏掉 ——
    第一轮改完后 CI 的 import 探针**仍在报弃用警告**, 才把剩下的 12 处抓出来。
    现在覆盖全部形态: 逗号列表任意位置 / ``as`` 别名 / ``from fitz import``。

    允许的形态:
      * ``import pymupdf as fitz``               —— 唯一推荐写法
      * ``from hl_lib import fitz, ...``         —— 示例脚本走这条(由 hl_lib 单点决定)
      * ``import fitz`` 紧跟 ``except ImportError:`` —— 仅限 hl_v3_final 的旧版回退
      * ``BARE_FITZ_ALLOWED`` 里逐条注明理由的例外
    """

    #: 允许出现裸 ``import fitz`` 的文件 -> 理由。每条都必须写明, 不许无理由放行。
    BARE_FITZ_ALLOWED = {
        "telemetry/watcher.py": "v5.4.11 的旧版回退 (except ImportError: import fitz)",
        "telemetry/pdf_utils.py": "同上",
        "tests/test_telemetry.py":
            "故意 import fitz —— 它是 'telemetry 导入路径不带弃用警告' 这条断言的对照面",
    }

    #: hl_v3_final 及其分发副本保留旧版回退 (技能工具链要分发出去, 版本不可控)
    FALLBACK_DIRS = ("scripts/hl_v3_final/",
                     "skills/via54medit-literature-pipeline/scripts/")

    _IMPORT_LINE = re.compile(r"^(\s*)import\s+([^#]+?)\s*(#.*)?$")
    _FROM_FITZ = re.compile(r"^(\s*)from\s+fitz\b")

    def _scan(self):
        offenders = []
        for root, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs
                       if d not in IGNORE_DIRS and d not in {".git", "node_modules"}]
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                path = os.path.join(root, fn)
                rel = os.path.relpath(path, REPO)
                try:
                    with open(path, encoding="utf-8") as f:
                        lines = f.read().split("\n")
                except (UnicodeDecodeError, OSError):
                    continue
                for i, line in enumerate(lines):
                    if "pymupdf" in line:
                        continue
                    m = self._IMPORT_LINE.match(line)
                    hit = False
                    if m and "fitz" in [x.strip() for x in m.group(2).split(",")]:
                        hit = True
                    if self._FROM_FITZ.match(line):
                        hit = True
                    if not hit:
                        continue
                    if rel in self.BARE_FITZ_ALLOWED:
                        continue
                    prev = lines[i - 1].strip() if i else ""
                    if (rel.replace(os.sep, "/").startswith(self.FALLBACK_DIRS)
                            and prev.startswith("except ImportError")):
                        continue
                    offenders.append(f"{rel}:{i + 1}  {line.strip()}")
        return offenders

    def test_no_bare_fitz_import(self):
        offenders = self._scan()
        self.assertEqual(
            offenders, [],
            "这些位置用了裸 import fitz。应为 `import pymupdf as fitz`"
            "(或示例脚本的 `from hl_lib import fitz`); 若确属例外, 加进 "
            "BARE_FITZ_ALLOWED 并写明理由:\n  " + "\n  ".join(offenders))

    def test_allowlist_has_no_zombie_entries(self):
        """例外清单不该留僵尸条目 —— 文件改名/删除后条目要跟着清。"""
        stale = [rel for rel in self.BARE_FITZ_ALLOWED
                 if not os.path.exists(os.path.join(REPO, rel))]
        self.assertEqual(stale, [], f"BARE_FITZ_ALLOWED 里这些文件已不存在: {stale}")

    def test_fitz_alias_resolves_to_pymupdf(self):
        """``hl_lib.fitz`` 必须是 pymupdf 模块本身 —— 示例脚本都靠它取导入名。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "hl_lib_probe", os.path.join(MIRROR_A, "hl_lib.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(getattr(mod.fitz, "__name__", ""), "pymupdf")


class TestPowerPointOnlyRender(unittest.TestCase):
    """PPT 渲染只允许 PowerPoint 一条通道。

    规则出处 (2026-08-05 用户硬规则, 2026-09-11 用户重申):
      "powerpoint 渲染作为默认, 原因是 keynote 和 libreoffice 打开后视觉和 PowerPoint
       不一致, 以 PowerPoint 为准, 并默认必须用 PowerPoint 渲染"
    权威说明: ``skills/via54medit-algorithm-driven-upgrade-v2/references/
    v2.12.0-powerpoint-render-mandatory.md``。

    为什么值得设成不变量: v5.4.24/v5.4.25 只把 ``scripts/ppt_render_engine.py`` 收口了,
    但**同一个仓库里还有别的 PPT 渲染入口**没跟着改 (``ppt_expand.render_pptx_images``、
    技能包里的 ``render_ppt_slides.py``、``step1_export_slides.py``), 于是"禁用其它通道"
    实际上没禁干净 —— 用户为此重申过一次。这条测试就是为了让那种漏改**当场红**,
    而不是等下一个人去逐个文件读。

    扫描范围: ``scripts/`` 与 ``skills/`` 下的**非测试** Python 文件
    (测试文件会为"验证某通道已消失"而故意写出通道名, 属正常引用)。
    """

    SCAN_DIRS = ("scripts", "skills")

    #: 扫描时跳过的文件名前缀 —— 它们故意写出通道名做反向断言。
    SKIP_PREFIX = ("test_", "conftest")

    #: 允许出现的文件 -> 理由。每条都必须写明, 不许无理由放行。
    ALLOWED = {
        os.path.join("scripts", "unified_render_engine.py"):
            "命中的是 **Word** (DOC/DOCX) → PDF 那条路径, 不是 PPT —— PowerPoint 无法渲染 "
            "Word 文档, 故 PPT 规则不适用, LibreOffice 在这里是 Word 渲染的实现之一。"
            "若要求 Word 也一并收口, 删掉 render_docx_to_images() 的 LibreOffice 分支 "
            "并同步删掉本条目。",
    }

    #: 以可执行名调用其它渲染器 —— 这是"换通道"最直接的形态。
    _OTHER_RENDERER = re.compile(r"""["'](?:soffice|libreoffice)["']""")
    #: LibreOffice 的转换开关 (出现即意味着走它转文档)。
    _CONVERT_FLAG = re.compile(r"--convert-to")
    #: 已删除的通道函数名 —— 连名字都不该再出现。
    _GONE_NAMES = ("render_via_soffice", "render_via_python_pptx",
                   "_find_soffice", "render_ppt_libreoffice")
    #: RENDER_ENGINE 只允许这两个取值。
    _ENGINE_ENV = re.compile(r"""RENDER_ENGINE["']\s*[:=]\s*["']([^"']+)["']""")
    _ALLOWED_ENGINE_VALUES = {"powerpoint", "ppt"}

    def _iter_py(self):
        for top in self.SCAN_DIRS:
            for root, dirs, files in os.walk(os.path.join(REPO, top)):
                dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
                for fn in files:
                    if not fn.endswith(".py") or fn.startswith(self.SKIP_PREFIX):
                        continue
                    path = os.path.join(root, fn)
                    yield os.path.relpath(path, REPO), path

    def _scan(self):
        offenders = []
        for rel, path in self._iter_py():
            if rel.replace(os.sep, "/") in {k.replace(os.sep, "/") for k in self.ALLOWED}:
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    lines = f.read().split("\n")
            except (UnicodeDecodeError, OSError):
                continue
            for i, line in enumerate(lines, 1):
                hit = None
                if self._OTHER_RENDERER.search(line):
                    hit = "调用了其它渲染器可执行文件"
                elif self._CONVERT_FLAG.search(line):
                    hit = "用了 LibreOffice 的转换开关"
                else:
                    for name in self._GONE_NAMES:
                        if name in line:
                            hit = f"出现已删除的通道函数 {name}"
                            break
                if hit:
                    offenders.append(f"{rel}:{i}  [{hit}]  {line.strip()}")
        return offenders

    def test_no_other_render_channel_in_code(self):
        offenders = self._scan()
        self.assertEqual(
            offenders, [],
            "这些位置仍在走非 PowerPoint 的渲染通道。按 2026-08-05 用户硬规则, "
            "PPT 只能由 PowerPoint 渲染 (其它渲染器字体/布局与原版不一致)。"
            "改法: 委托给 ppt_render_engine.render_ppt_slides_auto() / "
            "hl_v3_final/ppt_to_pdf.py; 若确属例外, 加进 ALLOWED 并写明理由:\n  "
            + "\n  ".join(offenders))

    def test_render_engine_env_has_no_other_channel_value(self):
        """代码里不得再设置指向其它通道的 RENDER_ENGINE 取值。"""
        bad = []
        for rel, path in self._iter_py():
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
            except (UnicodeDecodeError, OSError):
                continue
            for i, line in enumerate(text.split("\n"), 1):
                m = self._ENGINE_ENV.search(line)
                if m and m.group(1).lower() not in self._ALLOWED_ENGINE_VALUES:
                    bad.append(f"{rel}:{i}  {line.strip()}")
        self.assertEqual(bad, [], "RENDER_ENGINE 只允许 powerpoint: \n  " + "\n  ".join(bad))

    def test_allowlist_has_no_zombie_entries(self):
        """例外清单不该留僵尸条目 —— 文件改名/删除后条目要跟着清。"""
        stale = [rel for rel in self.ALLOWED
                 if not os.path.exists(os.path.join(REPO, rel))]
        self.assertEqual(stale, [], f"ALLOWED 里这些文件已不存在: {stale}")


if __name__ == "__main__":
    unittest.main()
