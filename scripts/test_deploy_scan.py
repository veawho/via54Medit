#!/usr/bin/env python3
"""test_deploy_scan.py — 部署扫描器的平台感知 / 按需安装 不变量

这些用例守的是本功能的核心承诺:
  * **只部署与平台相关的** —— Windows 上不装 macOS 独有的东西, 反之亦然;
    与平台无关的能力必须标成"不适用", 且**探测与安装都不得被调用**。
  * **只部署缺失的** —— 已就绪的能力不会被重装; ``--check`` 一律不装。
  * **按正确通道装** —— mmx-cli 走 npm(它**不是** PyPI 包), Python 包走 pip。
  * **OCR 真的被检测** —— 缺 paddleocr 必须被报出来并按 pip 通道补齐。

v5.4.36 起还守下面这些(都是参考 hermes-agent / openclaw 的部署方式借来的机制):

  * **只装缺的, 且装完必须复验** —— 安装器说成功不算, 复验通过才算。这条来自
    Word 通道那个真实故障: ``save as`` 返回 rc=0 却**没有任何产出**。
  * **--dry-run 绝不落地** —— 只打印计划。
  * **--only 只动被点名的能力** —— hermes ``--ensure`` 的等价物。
  * **探测超时只给"跨 GUI/授权边界"的探测** —— 给进程内 import 加上界是假阴性发生器。
  * **退出码有语义** —— 用法错误必须是 2, 不能被当成"环境有问题"。
"""
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import contextlib
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import deploy_scan as ds                                        # noqa: E402


class _Recorder:
    """把矩阵里每个能力的 probe/install 换成记录器, 保留**真实的平台分类**。

    ``install`` 默认真的把 key 从 ``missing`` 里拿掉 —— 忠实模拟"装完复验通过"。
    要模拟"安装器报成功但没产出"(Word 通道踩过的那个坑), 用 ``_LyingRecorder``。
    """

    def __init__(self, missing=(), resolves_on_install=True):
        self.missing = set(missing)
        self.resolves_on_install = resolves_on_install
        self.probes = []
        self.installs = []

    def probe(self, key):
        self.probes.append(key)
        return (key not in self.missing), ("ok" if key not in self.missing else "missing")

    def install(self, key):
        self.installs.append(key)
        # 真实的安装路径都会记下自己用了哪条通道; 记录器照做, 否则部署戳记就测不到。
        ds._note_channel("fake", "install %s" % key)
        if self.resolves_on_install:
            self.missing.discard(key)
        return True, "装好了"

    def matrix(self, real, *a, **kw):
        caps = real(*a, **kw)
        for c in caps:
            c._probe = (lambda c=c: self.probe(c.key))
            # 尊重"本项没有自动安装通道"的真相(Office / browser / lark_cli):
            # 无条件塞一个安装器会掩盖 collect() 里"无解缺口"的分支。
            if c._install is not None:
                c._install = (lambda c=c: self.install(c.key))
        return caps


class _LyingRecorder(_Recorder):
    """安装器**报成功**, 但东西并没有真的出现。

    这正是本项目在 Word 通道上踩到的坑: ``save as`` 返回 rc=0, 却没有任何产出。
    hermes-agent 的 "installer reported success but binary not found → exit 1" 与
    openclaw 的 "lifecycle-pending 标记 -> 必须判失败" 都在防这件事。
    """

    def __init__(self, missing=()):
        super().__init__(missing, resolves_on_install=False)


class _PlanAssertions:
    """与平台无关的"计划里含这条命令"断言。

    **不要**写 ``assertIn("npm install -g mmx-cli", plan)``: Windows 上 npm 的可执行文件是
    ``npm.CMD``, 于是这句在 Linux/macOS 上过、在 Windows 跑者上必然挂 —— v5.4.36 实际
    就这样红过一次。改成"这些片段**按顺序**出现", 就与具体路径与扩展名无关了。
    """

    def assert_plan_has(self, plan, parts):
        pos = 0
        for p in parts:
            idx = plan.find(p, pos)
            if idx < 0:
                self.fail("计划里缺少片段 %r (需按序出现): %r" % (p, plan))
            pos = idx + len(p)


@contextlib.contextmanager
def env_for(osname, rec, **kwargs):
    """在指定平台上跑 run(); 记录 probe/install 调用。"""
    real = ds.build_matrix
    with mock.patch.object(ds, "current_os", return_value=osname), \
            mock.patch.object(ds, "build_matrix",
                              side_effect=lambda *a, **k: rec.matrix(real, *a, **k)), \
            mock.patch.object(ds, "scan_platform_compat", return_value=([], 0)):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = ds.run(**kwargs)
        yield code, buf.getvalue()


class TestPlatformFiltering(unittest.TestCase):
    """核心承诺: 与平台无关的能力 → 不适用, 不探测、不安装。"""

    def test_windows_only_capability_is_not_touched_on_macos(self):
        rec = _Recorder()
        with env_for("macos", rec, install=True) as (code, _out):
            self.assertNotIn("pywin32", rec.probes, "macOS 上不该探测 Windows 专属的 pywin32")
            self.assertNotIn("pywin32", rec.installs, "macOS 上不该安装 pywin32")
        self.assertIn(code, (0, 1), "只要跑完即可")

    def test_windows_only_capability_is_deployed_on_windows(self):
        rec = _Recorder(missing=["pywin32"])
        with env_for("windows", rec, install=True):
            self.assertIn("pywin32", rec.probes, "Windows 上必须探测 pywin32")
            self.assertIn("pywin32", rec.installs, "Windows 上缺失的 pywin32 必须被安装")

    def test_office_is_not_applicable_on_linux(self):
        """Linux 没有桌面 Office —— 必须标不适用, 且不去装(它也无法自动安装)。"""
        rec = _Recorder()
        with env_for("linux", rec, install=True) as (_, out):
            for key in ("powerpoint", "word"):
                self.assertNotIn(key, rec.probes, "Linux 上不该探测 %s" % key)
                self.assertNotIn(key, rec.installs, "Linux 上不该安装 %s" % key)
        self.assertIn("本平台不适用", out)

    def test_office_is_probed_on_windows_and_macos(self):
        for osname in ("windows", "macos"):
            rec = _Recorder()
            with env_for(osname, rec, install=True):
                self.assertIn("word", rec.probes, "%s 上必须探测 Word" % osname)
                self.assertIn("powerpoint", rec.probes, "%s 上必须探测 PowerPoint" % osname)

    def test_na_rows_are_reported_as_not_applicable(self):
        rec = _Recorder()
        with env_for("linux", rec, install=False, as_json=True) as (_, out):
            data = json.loads(out)
        na = {r["key"] for r in data["capabilities"] if r["status"] == ds.NA}
        self.assertIn("powerpoint", na)
        self.assertIn("word", na)
        self.assertIn("pywin32", na)
        for r in data["capabilities"]:
            if r["status"] == ds.NA:
                self.assertIn("不适用", r["detail"])

    def test_every_capability_has_a_valid_platform_list(self):
        for c in ds.build_matrix():
            self.assertTrue(c.platforms, "%s 没有平台列表" % c.key)
            self.assertTrue(set(c.platforms) <= set(ds.ALL),
                            "%s 的平台列表含未知平台 %s" % (c.key, c.platforms))


class TestInstallOnlyMissing(unittest.TestCase):
    """只装缺的; --check 一律不装。"""

    def test_ready_capabilities_are_never_reinstalled(self):
        rec = _Recorder(missing=[])      # 全部就绪
        with env_for("macos", rec, install=True):
            self.assertEqual(rec.installs, [], "全部就绪时不该有任何安装动作")

    def test_check_mode_never_installs_anything(self):
        rec = _Recorder(missing=["pymupdf", "ocr", "mmx_cli", "pywin32"])
        with env_for("windows", rec, install=False):
            self.assertEqual(rec.installs, [], "--check 绝不能安装任何东西")

    def test_missing_required_capability_blocks(self):
        rec = _Recorder(missing=["pymupdf"])
        with env_for("macos", rec, install=False) as (code, out):
            self.assertEqual(code, 1, "必需能力缺失时必须非零退出")
        self.assertIn("未就绪", out)

    def test_office_missing_does_not_gate(self):
        """Office 无法由脚本自动安装 —— 缺它要强力提示, 但不该判部署失败。"""
        rec = _Recorder(missing=["powerpoint", "word"])
        with env_for("macos", rec, install=True) as (code, _):
            self.assertEqual(code, 0, "缺桌面 Office 不应让部署扫描失败")

    def test_skip_heavy_removes_ocr_from_matrix(self):
        keys = {c.key for c in ds.build_matrix(include_heavy=False)}
        self.assertNotIn("ocr", keys, "--skip-heavy 时应完全不纳入 OCR")
        keys_all = {c.key for c in ds.build_matrix(include_heavy=True)}
        self.assertIn("ocr", keys_all)


class TestInstallChannels(unittest.TestCase):
    """按正确通道安装: mmx-cli 走 npm(不是 PyPI), Python 包走 pip。"""

    def test_mmx_cli_installs_via_npm(self):
        cap = [c for c in ds.build_matrix() if c.key == "mmx_cli"][0]
        with mock.patch.object(ds, "npm_install", return_value=(True, "ok")) as npm, \
                mock.patch.object(ds, "pip_install", return_value=(True, "ok")) as pip:
            cap.install()
        npm.assert_called_once_with("mmx-cli")
        pip.assert_not_called()

    def test_ocr_installs_paddle_via_pip(self):
        cap = [c for c in ds.build_matrix() if c.key == "ocr"][0]
        with mock.patch.object(ds, "pip_install", return_value=(True, "ok")) as pip:
            cap.install()
        args = pip.call_args[0][0]
        self.assertIn("paddleocr", args)
        self.assertIn("paddlepaddle", args)

    def test_no_capability_pip_installs_mmx_cli(self):
        """回归守卫: mmx-cli 不是 PyPI 包, 任何能力都不该用 pip 装它。"""
        for cap in ds.build_matrix():
            if cap._install is None:
                continue
            with mock.patch.object(ds, "pip_install", return_value=(True, "ok")) as pip, \
                    mock.patch.object(ds, "npm_install", return_value=(True, "ok")):
                cap.install()
            for call in pip.call_args_list:
                pkgs = call[0][0]
                pkgs = [pkgs] if isinstance(pkgs, str) else list(pkgs)
                self.assertNotIn("mmx-cli", pkgs,
                                 "%s 用 pip 装 mmx-cli —— 它在 PyPI 上不存在" % cap.key)

    def test_no_code_path_pip_installs_mmx_cli(self):
        """回归守卫: mmx-cli 不是 PyPI 包, 任何能力都不该用 pip 装它。

        只查 **AST 里真实的 pip_install(...) 实参** —— 文档字符串里
        "``pip install mmx-cli`` 是错的" 这类说明是在记录更正, 不该被误判。
        (初版用纯文本匹配, 结果被 install_mmx.py 的说明段落绊倒。)
        """
        import ast
        for name in ("deploy_scan.py", "install_mmx.py", "bootstrap_device.py", "deps_auto.py"):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                fname = getattr(fn, "id", None) or getattr(fn, "attr", None)
                if fname != "pip_install":
                    continue
                lits = " ".join(str(a.value) for a in node.args
                                if isinstance(a, ast.Constant))
                self.assertNotIn("mmx-cli", lits,
                                 "%s:%d 用 pip 装 mmx-cli —— 它在 PyPI 上不存在"
                                 % (name, node.lineno))


class TestWordProbeIsNotPowerpointProbe(unittest.TestCase):
    """回归: 初版 Word 那行复用了 PowerPoint 的探测, 于是"没装 Word"被报成"已就绪"。"""

    def test_word_probe_fails_when_word_missing_even_if_ppt_present(self):
        fake_ppt = [("PowerPoint (macOS)", "macos_ppt", "com.microsoft.Powerpoint")]
        with mock.patch("ppt_render_engine.detect_engines", return_value=fake_ppt):
            ok, detail = ds._probe_office("powerpoint")()
        self.assertTrue(ok)
        self.assertIn("PowerPoint", detail)

        with mock.patch("ppt_render_engine.detect_engines", return_value=fake_ppt), \
                mock.patch.object(sys, "platform", "darwin"), \
                mock.patch.object(os, "name", "posix"), \
                mock.patch("unified_render_engine.probe_macos_word",
                           return_value=(False, "预检失败: 卡住")):
            ok2, detail2 = ds._probe_office("word")()
        self.assertFalse(ok2, "PowerPoint 在不在, 都不能让 Word 的探测变成就绪")
        self.assertIn("预检失败", detail2)

    def test_powerpoint_probe_does_not_fall_into_word_branch(self):
        """回归: 调用点曾把 app 传成 "ppt", 于是 PowerPoint 那行显示成 Word 的结果。"""
        fake = [("PowerPoint (macOS)", "macos_ppt", "com.microsoft.Powerpoint")]
        with mock.patch("ppt_render_engine.detect_engines", return_value=fake), \
                mock.patch.object(sys, "platform", "darwin"), \
                mock.patch.object(os, "name", "posix"), \
                mock.patch("unified_render_engine.probe_macos_word",
                           return_value=(True, "Microsoft Word 16.112")):
            for alias in ("powerpoint", "ppt"):
                ok, detail = ds._probe_office(alias)()
                self.assertTrue(ok)
                self.assertIn("PowerPoint", detail,
                              "别名 %r 落进了 Word 分支: %s" % (alias, detail))
                self.assertNotIn("Word", detail)

    def test_word_probe_ok_only_when_word_answers(self):
        with mock.patch.object(sys, "platform", "darwin"), \
                mock.patch.object(os, "name", "posix"), \
                mock.patch("unified_render_engine.probe_macos_word",
                           return_value=(True, "Microsoft Word 16.112")):
            ok, detail = ds._probe_office("word")()
        self.assertTrue(ok)
        self.assertIn("Word", detail)


class TestCompatScan(unittest.TestCase):
    """平台兼容性扫描本身不能自伤, 也要真的报出 POSIX 专属假设。"""

    def test_scanner_does_not_flag_itself(self):
        findings, _ = ds.scan_platform_compat()
        files = {f["file"] for f in findings}
        self.assertNotIn(os.path.join("scripts", "deploy_scan.py"), files,
                         "扫描器把自己的检测规则当成违规了")

    def test_scanner_finds_posix_tmp_and_foreign_paths(self):
        findings, scanned = ds.scan_platform_compat()
        self.assertGreater(scanned, 50, "扫描的文件数太少, 像是没扫到")
        kinds = {f["kind"] for f in findings}
        self.assertIn("posix_tmp", kinds, "应当报出硬编码 /tmp")
        self.assertIn("foreign_path", kinds, "应当报出外机绝对路径")
        for f in findings:
            self.assertTrue(f["file"] and f["line"] > 0 and f["detail"])

    def test_strict_mode_gates_on_compat_findings(self):
        """能力全就绪时, 只有兼容性问题在 --strict 下才计失败。

        注意必须把矩阵也换成记录器: 否则跑的是**真实探测**, 本机 OCR 缺失会直接
        让两条断言都变成 1, 看着像 --strict 生效, 其实是被别的阻塞项顶起来的。
        (第一版就是这么写的, 实测 strict=False 也返回 1 才暴露。)
        """
        real = ds.build_matrix
        rec = _Recorder(missing=[])          # 能力全就绪 -> 只剩兼容性问题
        compat = [{"file": "x.py", "line": 1, "kind": "posix_tmp",
                   "detail": "d", "code": "c"}]
        with mock.patch.object(ds, "current_os", return_value="macos"), \
                mock.patch.object(ds, "build_matrix",
                                  side_effect=lambda *a, **k: rec.matrix(real, *a, **k)), \
                mock.patch.object(ds, "scan_platform_compat",
                                  return_value=(compat, 10)), \
                contextlib.redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(ds.run(install=False, strict=True), 1)
            buf.truncate(0), buf.seek(0)
            self.assertEqual(ds.run(install=False, strict=False), 0)


class TestPlatformSelfCheck(unittest.TestCase):
    """``--verify-platform`` 是 CI 在真 Windows/Linux/macOS 跑者上用的自检。

    它必须**不依赖 shell 语义**(最初写在 workflow 里用了 `2>/dev/null`, Windows 跑者
    的 PowerShell 下直接崩), 而且要在分类错位时真的报出来。
    """

    def test_real_host_classification_is_consistent(self):
        result, _ = ds.collect(install=False, include_heavy=True)
        ok, problems = ds.verify_platform(result)
        self.assertTrue(ok, "本机平台分类自检未通过: %s" % problems)

    def test_detects_na_mismatch(self):
        """伪造"macOS 上 pywin32 却是 missing" -> 必须报出来。"""
        result = {
            "environment": {"os": "macos"},
            "capabilities": [
                {"key": "pywin32", "status": "missing"},
                {"key": "powerpoint", "status": "ok"},
                {"key": "word", "status": "ok"},
                {"key": "ocr", "status": "ok"},
                {"key": "mmx_cli", "status": "ok"},
                {"key": "node", "status": "ok"},
            ],
        }
        with mock.patch.object(ds, "current_os", return_value="macos"), \
                contextlib.redirect_stdout(io.StringIO()):
            ok, problems = ds.verify_platform(result)
        self.assertFalse(ok)
        self.assertTrue(any("pywin32" in p for p in problems), problems)

    def test_detects_linux_office_not_na(self):
        result = {
            "environment": {"os": "linux"},
            "capabilities": [
                {"key": "pywin32", "status": "na"},
                {"key": "powerpoint", "status": "ok"},      # 错: Linux 上应为 na
                {"key": "word", "status": "na"},
                {"key": "ocr", "status": "ok"},
                {"key": "mmx_cli", "status": "ok"},
                {"key": "node", "status": "ok"},
            ],
        }
        with mock.patch.object(ds, "current_os", return_value="linux"), \
                contextlib.redirect_stdout(io.StringIO()):
            ok, problems = ds.verify_platform(result)
        self.assertFalse(ok)
        self.assertTrue(any("powerpoint" in p for p in problems), problems)

    def test_detects_windows_pywin32_wrongly_na(self):
        result = {
            "environment": {"os": "windows"},
            "capabilities": [
                {"key": "pywin32", "status": "na"},         # 错: Windows 上不该 na
                {"key": "powerpoint", "status": "ok"},
                {"key": "word", "status": "ok"},
                {"key": "ocr", "status": "ok"},
                {"key": "mmx_cli", "status": "ok"},
                {"key": "node", "status": "ok"},
            ],
        }
        with mock.patch.object(ds, "current_os", return_value="windows"), \
                contextlib.redirect_stdout(io.StringIO()):
            ok, problems = ds.verify_platform(result)
        self.assertFalse(ok)
        self.assertTrue(any("pywin32" in p for p in problems), problems)

    def test_verify_platform_is_shell_free(self):
        """回归: 这段逻辑不能再回到"靠 shell 重定向"的写法。"""
        with mock.patch.object(ds, "collect", wraps=ds.collect) as coll, \
                contextlib.redirect_stdout(io.StringIO()):
            code = ds.main(["--verify-platform"])
        self.assertEqual(code, 0)
        # 只读: 必须是以 install=False 调用的
        self.assertFalse(coll.call_args.kwargs.get("install", True),
                         "--verify-platform 不该触发安装")


class TestPostInstallReverify(unittest.TestCase):
    """**装完必须复验** —— 安装器说成功不算数。

    两条外部经验都指向同一件事:
      * hermes-agent: "uv installer reported success but binary not found at ..." → exit 1
      * openclaw: 残留 ``.openclaw-lifecycle-pending`` 标记时**必须判失败**, 而不是把
        "跳过了生命周期脚本的包"报成安装成功
    本项目自己的版本是这个: Word 通道的 ``save as`` 返回 rc=0, 却没有任何产出。
    """

    def test_lying_installer_is_reported_as_missing(self):
        rec = _LyingRecorder(missing=["pymupdf"])
        with env_for("macos", rec, install=True, as_json=True) as (code, out):
            data = json.loads(out)
        row = [r for r in data["capabilities"] if r["key"] == "pymupdf"][0]
        self.assertEqual(row["status"], ds.MISSING,
                         "安装器报成功但复验没过 —— 不能记成就绪")
        self.assertIs(row["verified"], False)
        self.assertIn("复验", row["detail"])
        self.assertEqual(rec.installs, ["pymupdf"], "该试还是要试")
        self.assertEqual(code, ds.EXIT_GAP, "必需能力复验不过 = 部署未就绪")

    def test_verify_failed_is_counted_in_summary(self):
        rec = _LyingRecorder(missing=["pymupdf", "ocr"])
        with env_for("macos", rec, install=True, as_json=True) as (_, out):
            data = json.loads(out)
        self.assertEqual(data["summary"]["verify_failed"], 2)
        self.assertEqual(data["summary"]["fixed"], 0, "复验没过就不该算'已补齐'")

    def test_successful_install_is_fixed_and_verified(self):
        rec = _Recorder(missing=["pymupdf"])
        with env_for("macos", rec, install=True, as_json=True) as (code, out):
            data = json.loads(out)
        row = [r for r in data["capabilities"] if r["key"] == "pymupdf"][0]
        self.assertEqual(row["status"], ds.FIXED)
        self.assertIs(row["verified"], True)
        self.assertEqual(code, ds.EXIT_OK)
        self.assertEqual(data["summary"]["fixed"], 1)


class TestDryRun(_PlanAssertions, unittest.TestCase):
    """``--dry-run`` (openclaw): 只打印将要执行的动作, 绝不落地任何修改。"""

    def test_dry_run_never_installs(self):
        rec = _Recorder(missing=["pymupdf", "ocr", "mmx_cli"])
        with env_for("macos", rec, install=False, dry_run=True, as_json=True) as (code, out):
            data = json.loads(out)
        self.assertEqual(rec.installs, [], "--dry-run 绝不能真的安装")
        planned = {r["key"] for r in data["capabilities"] if r["status"] == ds.PLAN}
        self.assertEqual(planned, {"pymupdf", "ocr", "mmx_cli"}, "缺失项应变成'计划'")
        self.assertTrue(data["dry_run"])
        self.assertEqual(code, ds.EXIT_OK, "计划生成成功就该退 0")

    def test_dry_run_plan_shows_the_real_command(self):
        """计划里必须是**真会执行的那条命令**, 不是一句"将安装 pymupdf"。

        断言必须走 ``self.assert_plan_has`` 这种**按词元**的写法 —— 直接
        ``assertIn("npm install -g mmx-cli", plan)`` 在 Linux/macOS 上会过、
        在 Windows 跑者上必挂(那里的可执行文件是 ``npm.CMD``)。v5.4.36 实际挂过一次。
        """
        rec = _Recorder(missing=["pymupdf", "mmx_cli"])
        with env_for("macos", rec, install=False, dry_run=True, as_json=True) as (_, out):
            data = json.loads(out)
        plans = {r["key"]: r["detail"] for r in data["capabilities"]}
        self.assert_plan_has(plans["pymupdf"], ["-m", "pip", "install", "pymupdf"])
        self.assert_plan_has(plans["mmx_cli"], ["npm", "install", "-g", "mmx-cli"])

    def test_plan_assertion_helper_is_platform_agnostic(self):
        """自守卫: 上面的辅助断言本身要能同时吃下 POSIX 与 Windows 形态的命令行。

        价值在于 —— 即便在 macOS 上跑, 它也会拿 Windows 形态的字符串去验断言逻辑,
        于是"断言写得依赖平台"这件事**在本机就会被发现**, 不必等 CI 变红。
        """
        cases = [
            ("/usr/local/bin/npm install -g mmx-cli", ["npm", "install", "-g", "mmx-cli"]),
            (r"C:\Program Files\nodejs\npm.CMD install -g mmx-cli",
             ["npm", "install", "-g", "mmx-cli"]),
            ("/opt/python/bin/python3 -m pip install pymupdf",
             ["-m", "pip", "install", "pymupdf"]),
            (r"C:\hostedtoolcache\windows\Python\3.11.9\x64\python.exe -m pip install pymupdf",
             ["-m", "pip", "install", "pymupdf"]),
        ]
        for plan, tokens in cases:
            self.assert_plan_has(plan, tokens)

    def test_dry_run_does_not_write_stamp(self):
        rec = _Recorder(missing=["pymupdf"])
        # 注意顺序: env_for 在 __enter__ 里就把 run() 跑完了, patch 必须写在它**前面**,
        # 否则断言的是"没人调用过", 而不是"没被调用" —— 空断言。
        with mock.patch.object(ds, "write_stamp") as ws, \
                env_for("macos", rec, install=False, dry_run=True):
            pass
        ws.assert_not_called()

    def test_dry_run_flags_required_gap_without_any_channel(self):
        """必需、且**没有任何自动通道**的缺口 —— dry-run 也要非零退出, 因为再跑一百次
        也补不上(逼人去装)。"""
        rec = _Recorder(missing=["python"])          # python 能力没有自动安装通道
        with env_for("macos", rec, install=False, dry_run=True, as_json=True) as (code, out):
            data = json.loads(out)
        self.assertEqual(data["summary"]["unresolvable"], 1)
        self.assertEqual(code, ds.EXIT_GAP)


class TestOnly(unittest.TestCase):
    """hermes 的 ``--ensure node,browser`` 等价物: 按需只补点名的能力。"""

    def test_only_limits_work_to_selected_capabilities(self):
        rec = _Recorder(missing=["pymupdf", "mmx_cli", "ocr", "git"])
        with env_for("macos", rec, install=True, only=["mmx_cli"], as_json=True) as (_, out):
            data = json.loads(out)
        self.assertEqual(rec.installs, ["mmx_cli"], "只该动被点名的能力")
        self.assertEqual([r["key"] for r in data["capabilities"]], ["mmx_cli"])

    def test_unknown_only_is_a_usage_error_listing_valid_keys(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = ds.main(["--only", "nope"])
        self.assertEqual(code, ds.EXIT_USAGE)
        out = buf.getvalue()
        self.assertIn("未知能力", out)
        self.assertIn("pymupdf", out, "应把合法能力键列出来, 否则用户无从下手")


class TestExitCodes(unittest.TestCase):
    """退出码有语义(openclaw: 非法取值退 2)—— 用法错误不能被当成"环境有问题"。"""

    def _main(self, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            return ds.main(argv), buf.getvalue()

    def test_usage_errors_are_two(self):
        for argv in (["--only", "nope"], ["--stage", "nope"]):
            code, out = self._main(argv)
            self.assertEqual(code, ds.EXIT_USAGE, "%s 应退 2, 实际 %s" % (argv, code))
            self.assertIn("未知", out)

    def test_help_and_list_exit_zero(self):
        for argv in (["--help"], ["--list"]):
            code, _ = self._main(argv)
            self.assertEqual(code, ds.EXIT_OK)

    def test_hard_gap_is_one(self):
        rec = _Recorder(missing=["pymupdf"])
        with env_for("macos", rec, install=False) as (code, _):
            self.assertEqual(code, ds.EXIT_GAP)

    def test_unknown_stage_does_not_raise(self):
        """回归: 第一版把 ``stage_flags`` 返回的 None 直接解包, 抛 TypeError 退 1 ——
        看着像"环境有问题", 其实是纯用法错误。"""
        code, _ = self._main(["--stage", "nope"])
        self.assertEqual(code, ds.EXIT_USAGE)


class TestStageProtocol(unittest.TestCase):
    """hermes 的 ``--stage``: 每个阶段只做一件能被单独复跑的事, 并给出 JSON 进度帧。"""

    def test_stage_env_reports_only_the_environment(self):
        result, _ = ds.collect(install=False, include_caps=False, include_compat=False)
        self.assertEqual(result["capabilities"], [])
        self.assertFalse(result["compat_included"])
        self.assertIn("via54_home", result["environment"])

    def test_stage_deps_skips_compat_scan(self):
        result, _ = ds.collect(install=False, include_compat=False)
        self.assertFalse(result["compat_included"])
        self.assertEqual(result["compat"]["scanned_files"], 0)
        self.assertTrue(result["capabilities"], "deps 阶段必须有能力矩阵")

    def test_stage_compat_skips_capabilities(self):
        result, _ = ds.collect(install=False, include_caps=False)
        self.assertTrue(result["compat_included"])
        self.assertEqual(result["capabilities"], [])

    def test_unknown_stage_has_no_flags(self):
        self.assertIsNone(ds.stage_flags("nope"))
        self.assertEqual(ds.stage_flags("all"), (True, True))
        self.assertEqual(ds.stage_flags("env"), (False, False))

    def test_emit_frame_is_one_machine_readable_line(self):
        """外层部署器只读这一行就知道成败 —— 不该让它去解析整份人类可读报告。"""
        buf = io.StringIO()
        rec = _Recorder()
        real = ds.build_matrix          # 必须在 patch 之前抓住真身, 否则 lambda 里再取
        with mock.patch.object(ds, "current_os", return_value="macos"), \
                mock.patch.object(ds, "build_matrix",
                                  side_effect=lambda *a, **k: rec.matrix(real, *a, **k)), \
                mock.patch.object(ds, "scan_platform_compat", return_value=([], 0)), \
                contextlib.redirect_stdout(buf):
            code = ds.run(install=False, stage="deps", emit_frame=True)
        lines = [l for l in buf.getvalue().splitlines() if l.startswith("{")]
        self.assertEqual(len(lines), 1, "应恰好一行 JSON 帧")
        frame = json.loads(lines[0])
        self.assertEqual(frame["stage"], "deps")
        self.assertIs(frame["ok"], code == ds.EXIT_OK)


class TestProbeTimeoutPolicy(unittest.TestCase):
    """探测超时**只**给"跨 GUI/授权边界"的探测。

    给进程内 import 加上界是假阴性发生器 —— 重的包(如 paddle)首次导入会编译/初始化,
    超过小上界就被误报"没装"。本机实测到过同一条命令两次结论不同(一次 missing 一次 ok)。
    """

    def test_only_gui_boundary_caps_declare_a_timeout(self):
        timed = {c.key for c in ds.build_matrix() if c.probe_timeout}
        self.assertEqual(timed, {"powerpoint", "word"},
                         "只有走 AppleEvent 的 Office 通道该有线程上界, 实际: %s" % timed)

    def test_no_import_capability_has_a_timeout(self):
        for c in ds.build_matrix():
            if c.kind in ("python", "env"):
                self.assertIsNone(c.probe_timeout,
                                  "%s 是进程内探测, 不该设上界" % c.key)

    def test_hanging_probe_is_reported_as_a_timeout(self):
        def hang():
            time.sleep(5)
            return True, "永远回不来"

        t0 = time.time()
        ok, detail = ds._probe_with_timeout(hang, 0.2, "office")
        self.assertFalse(ok)
        self.assertIn("探测超时", detail)
        self.assertLess(time.time() - t0, 3, "必须在 0.2s 上界附近返回, 而不是等它跑完")

    def test_no_timeout_runs_inline(self):
        box = []

        def fn():
            box.append(1)
            return True, "inline"

        ok, detail = ds._probe_with_timeout(fn, None, "x")
        self.assertTrue(ok)
        self.assertEqual(detail, "inline")
        self.assertEqual(box, [1], "不设上界时应在本线程直接跑完, 不另起线程")

    def test_timed_out_probe_does_not_poison_later_probes(self):
        """核心回归: 被 join 超时掐断的 daemon 线程会继续在后台把导入跑完, 于是同进程里
        **后续**探测得到不同结果。这里放一个卡住的 Office 探测 + 一个真实 OCR 探测,
        验证后者的结论与直接调用完全一致。"""
        expect_ok, expect_detail = ds._probe_ocr()

        caps = ds.build_matrix(include_heavy=True)
        for c in caps:
            if c.key == "powerpoint":
                c._probe = lambda: (time.sleep(5), (True, "卡住"))[1]
                c.probe_timeout = 0.2
        with mock.patch.object(ds, "build_matrix", return_value=caps), \
                mock.patch.object(ds, "current_os", return_value="macos"), \
                mock.patch.object(ds, "scan_platform_compat", return_value=([], 0)):
            result, _ = ds.collect(install=False)

        by_key = {r["key"]: r for r in result["capabilities"]}
        self.assertEqual(by_key["powerpoint"]["status"], ds.MISSING)
        self.assertIn("探测超时", by_key["powerpoint"]["detail"])
        self.assertEqual(by_key["ocr"]["status"], ds.OK if expect_ok else ds.MISSING,
                         "被掐断的探测影响了后续探测 —— 同进程内结论不一致")
        self.assertEqual(by_key["ocr"]["detail"], expect_detail)


class TestNpmChannelFallback(unittest.TestCase):
    """``npm install -g`` 撞权限时退回私有前缀 —— openclaw ``install-cli.sh`` 的 rootless 思路,
    hermes 则把 node 装进 ``$HERMES_HOME/node``。都不 sudo、不污染系统 node_modules。"""

    def test_falls_back_to_private_prefix(self):
        calls = []

        def fake_run(cmd, timeout=900, env=None):
            calls.append(list(cmd))
            if "--prefix" in cmd:
                return True, "added 1 package"
            return False, "EACCES: permission denied, mkdir '/usr/lib/node_modules'"

        def fake_which(name):
            if name == "npm":
                return "/usr/bin/npm"
            if name == "mmx-cli" and any("--prefix" in c for c in calls):
                return os.path.join(ds.NODE_PREFIX, "bin", "mmx-cli")
            return None

        with mock.patch.object(ds, "_run", side_effect=fake_run), \
                mock.patch.object(ds, "_which", side_effect=fake_which), \
                mock.patch.object(ds, "_remembered_npm_prefix", return_value=None):
            ok, detail = ds.npm_install("mmx-cli")
        self.assertTrue(ok, detail)
        self.assertTrue(any("--prefix" in c for c in calls), "应该试过私有前缀")
        self.assertEqual(calls[0][1:3], ["install", "-g"], "第一步仍是标准全局安装")

    def test_success_without_artifact_is_not_success(self):
        """命令返回 0, 但可执行文件并不在 —— 不能算装成功(openclaw 的
        "lifecycle 被跳过的包不算成功" 同源)。"""
        with mock.patch.object(ds, "_run", return_value=(True, "added 1 package")), \
                mock.patch.object(ds, "_which",
                                  side_effect=lambda n: "/usr/bin/npm" if n == "npm" else None), \
                mock.patch.object(ds, "_remembered_npm_prefix", return_value=None):
            ok, detail = ds.npm_install("mmx-cli")
        self.assertFalse(ok, "命令成功却没有可执行文件 —— 不能报成功")
        self.assertIn("不在 PATH", detail)

    def test_global_install_that_lands_on_path_is_not_downgraded(self):
        with mock.patch.object(ds, "_run", return_value=(True, "added 1 package")) as r, \
                mock.patch.object(ds, "_which",
                                  side_effect=lambda n: "/usr/bin/" + n), \
                mock.patch.object(ds, "_remembered_npm_prefix", return_value=None):
            ok, detail = ds.npm_install("mmx-cli")
        self.assertTrue(ok, detail)
        self.assertEqual(r.call_count, 1, "全局就成, 不该再去试私有前缀")

    def test_remembered_prefix_is_tried_first(self):
        """上次用私有前缀装成功了, 这次就该沿用 —— 别再去撞一遍权限。"""
        seen = []

        def fake_run(cmd, timeout=900, env=None):
            seen.append(list(cmd))
            return True, "added 1 package"

        with mock.patch.object(ds, "_run", side_effect=fake_run), \
                mock.patch.object(ds, "_which", side_effect=lambda n: "/usr/bin/" + n), \
                mock.patch.object(ds, "_remembered_npm_prefix", return_value="/custom/prefix"):
            ok, _detail = ds.npm_install("mmx-cli")
        self.assertTrue(ok)
        self.assertEqual(seen[0][seen[0].index("--prefix") + 1], "/custom/prefix")

    def test_missing_npm_gives_actionable_message(self):
        with mock.patch.object(ds, "_which", return_value=None):
            ok, detail = ds.npm_install("mmx-cli")
        self.assertFalse(ok)
        self.assertIn("npm install -g mmx-cli", detail)


class TestPipBoundary(unittest.TestCase):
    """撞上 PEP 668 时**默认不越过**解释器管理方划的边界(本项目 v5.4.3 的既定决定)。"""

    PEP668 = "error: externally-managed-environment"

    def test_does_not_add_break_system_packages_by_default(self):
        with mock.patch.dict(os.environ, {"VIA54_ALLOW_BREAK_SYSTEM": ""}), \
                mock.patch.object(ds, "_run", return_value=(False, self.PEP668)) as r:
            ok, detail = ds.pip_install("pymupdf")
        self.assertFalse(ok)
        for call in r.call_args_list:
            self.assertNotIn("--break-system-packages", call[0][0],
                             "默认不得替用户决定突破解释器管理的边界")
        self.assertIn("不越过", detail)
        self.assertIn("venv", detail, "必须给出可执行的替代做法, 而不是只报错")

    def test_explicit_optin_does_allow_it(self):
        with mock.patch.dict(os.environ, {"VIA54_ALLOW_BREAK_SYSTEM": "1"}), \
                mock.patch.object(ds, "_run", return_value=(False, self.PEP668)) as r:
            ok, _detail = ds.pip_install("pymupdf")
        self.assertFalse(ok, "第二次仍失败, 就该如实报失败")
        self.assertTrue(any("--break-system-packages" in c[0][0] for c in r.call_args_list),
                        "显式授权后应当尝试越界")

    def test_plain_failure_is_passed_through(self):
        with mock.patch.object(ds, "_run", return_value=(False, "no matching distribution")):
            ok, detail = ds.pip_install("nonexistent-pkg")
        self.assertFalse(ok)
        self.assertIn("no matching distribution", detail)


class TestDeployStamp(unittest.TestCase):
    """hermes 的 ``.install_method``: 记下"每个能力实际用了哪条通道", 下次沿用。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        for attr, val in (("VIA54_HOME", self.tmp),
                          ("STAMP_PATH", os.path.join(self.tmp, ".deploy_stamp.json"))):
            p = mock.patch.object(ds, attr, val)
            p.start()
            self.addCleanup(p.stop)

    def test_roundtrip(self):
        path = ds.write_stamp({"mmx_cli": {"channel": "npm", "package": "mmx-cli",
                                           "prefix": "/x"}})
        self.assertTrue(path and os.path.isfile(path))
        self.assertEqual(ds.read_stamp()["capabilities"]["mmx_cli"]["prefix"], "/x")
        self.assertEqual(ds.read_stamp()["os"], ds.current_os())

    def test_remembered_prefix_lookup(self):
        ds.write_stamp({"mmx_cli": {"channel": "npm", "package": "mmx-cli", "prefix": "/x"}})
        self.assertEqual(ds._remembered_npm_prefix("mmx-cli"), "/x")
        self.assertIsNone(ds._remembered_npm_prefix("other-pkg"))

    def test_corrupt_stamp_is_ignored(self):
        with open(ds.STAMP_PATH, "w", encoding="utf-8") as fh:
            fh.write("{ not json")
        self.assertEqual(ds.read_stamp(), {})

    def test_unwritable_home_is_not_fatal(self):
        with mock.patch.object(ds.os, "makedirs", side_effect=OSError("read-only fs")):
            self.assertIsNone(ds.write_stamp({"a": {}}),
                              "记不了账不该让部署失败")

    def test_stamp_is_written_only_for_actually_fixed_capabilities(self):
        rec = _Recorder(missing=["mmx_cli"])
        with mock.patch.object(ds, "write_stamp") as ws, \
                env_for("macos", rec, install=True):
            pass
        ws.assert_called_once()
        self.assertIn("mmx_cli", ws.call_args[0][0])

    def test_lying_install_is_not_recorded_in_the_stamp(self):
        """复验没过的通道不能记进戳记 —— 否则下次会去沿用一条**已知失败**的通道。"""
        rec = _LyingRecorder(missing=["mmx_cli"])
        with mock.patch.object(ds, "write_stamp") as ws, \
                env_for("macos", rec, install=True):
            pass
        ws.assert_not_called()


class TestEnvMirror(unittest.TestCase):
    """openclaw 把所有开关都镜像成环境变量 —— CI / 无人值守部署要用。"""

    def test_env_vars_provide_defaults(self):
        env = {"VIA54_DRY_RUN": "1", "VIA54_ONLY": "ocr", "VIA54_STRICT": "1",
               "VIA54_SKIP_HEAVY": "1", "VIA54_STAGE": "deps"}
        with mock.patch.dict(os.environ, env, clear=False), \
                mock.patch.object(ds, "run", return_value=0) as r, \
                contextlib.redirect_stdout(io.StringIO()):
            ds.main(["--check"])
        kw = r.call_args.kwargs
        self.assertTrue(kw["dry_run"])
        self.assertTrue(kw["strict"])
        self.assertEqual(kw["only"], ["ocr"])
        self.assertEqual(kw["stage"], "deps")
        self.assertFalse(kw["include_heavy"])

    def test_cli_flag_overrides_env(self):
        with mock.patch.dict(os.environ, {"VIA54_ONLY": "ocr"}, clear=False), \
                mock.patch.object(ds, "run", return_value=0) as r, \
                contextlib.redirect_stdout(io.StringIO()):
            ds.main(["--only", "git"])
        self.assertEqual(r.call_args.kwargs["only"], ["git"])

    def test_dry_run_env_never_installs(self):
        with mock.patch.dict(os.environ, {"VIA54_DRY_RUN": "1"}, clear=False), \
                mock.patch.object(ds, "run", return_value=0) as r, \
                contextlib.redirect_stdout(io.StringIO()):
            ds.main([])
        self.assertFalse(r.call_args.kwargs["install"], "VIA54_DRY_RUN 必须压掉安装")


class TestToolProbeRunsTheBinary(unittest.TestCase):
    """探测"真的能跑"而不是"文件在"(openclaw: probe the exact executable it will use)。

    实测教训: ``pdftoppm --version`` 会被当成文件名, 报 I/O Error —— 只有 ``-v`` 可用。
    """

    def test_existing_but_failing_binary_is_not_ready(self):
        with mock.patch.object(ds, "_which", return_value="/usr/bin/git"), \
                mock.patch.object(ds, "_run", return_value=(False, "fatal: not a git repo")):
            ok, detail = ds._probe_tool("git", "--version")
        self.assertFalse(ok, "exit 非零的二进制不算就绪")
        self.assertIn("执行失败", detail)

    def test_missing_binary_reports_not_installed(self):
        with mock.patch.object(ds, "_which", return_value=None):
            ok, detail = ds._probe_tool("git", "--version")
        self.assertFalse(ok)
        self.assertIn("未安装", detail)

    def test_poppler_uses_dash_v_not_double_dash(self):
        """回归: poppler 的版本开关是 ``-v``; 写成 ``--version`` 会误报"执行失败"。"""
        cap = [c for c in ds.build_matrix() if c.key == "poppler"][0]
        seen = {}

        def fake_probe_tool(names, version_flag="--version", timeout=20):
            seen["names"] = names
            seen["flag"] = version_flag
            return True, "ok"

        with mock.patch.object(ds, "_probe_tool", side_effect=fake_probe_tool):
            cap.probe()
        self.assertEqual(seen["flag"], "-v", "poppler 只认 -v")
        self.assertEqual(list(seen["names"]), ["pdftoppm", "pdftotext"])

    def test_git_is_a_required_capability(self):
        """``git pull`` 是"更新版本后自动补齐"自身的运行前提。"""
        caps = {c.key: c for c in ds.build_matrix()}
        self.assertIn("git", caps)
        self.assertTrue(caps["git"].required, "缺 git 会让自动更新静默失效")
        self.assertTrue(caps["git"].installable(), "git 应当有自动安装通道")


class TestPrivatePrefixIsProbed(unittest.TestCase):
    """私有前缀装的东西必须能被自己的探测认出来, 否则每次部署都重装一遍
    (hermes 的 ``_has_hermes_agent_browser`` 就专门查过 ``$HERMES_HOME/node/bin``)。"""

    def test_which_falls_back_to_private_prefix(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        bindir = os.path.join(tmp, "bin")
        os.makedirs(bindir)
        exe = os.path.join(bindir, "mmx-cli")
        with open(exe, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\n")
        os.chmod(exe, 0o755)

        with mock.patch.object(ds, "NODE_PREFIX", tmp), \
                mock.patch.object(ds, "_private_bin_dirs",
                                  return_value=[bindir]), \
                mock.patch.object(ds.shutil, "which", return_value=None):
            self.assertEqual(ds._which("mmx-cli"), exe)


class TestEntrypoints(unittest.TestCase):
    """两个入口脚本必须共用同一引擎, 且 mmx 安装不再走 pip。"""

    def test_install_mmx_uses_npm_and_not_pip(self):
        import install_mmx
        # install_mmx 现在通过 ds._which 探测(node/npm 可能装在私有前缀里),
        # 所以 patch 的是引擎的 _which, 而不是某个模块自己的 shutil。
        with mock.patch.object(ds, "_which", side_effect=lambda n: "/usr/bin/" + n), \
                mock.patch.object(ds, "npm_install", return_value=(True, "ok")) as npm, \
                mock.patch.object(ds, "pip_install", return_value=(True, "ok")) as pip:
            ok, detail = install_mmx.install_mmx_cli()
        self.assertTrue(ok, detail)
        npm.assert_called_once_with("mmx-cli")
        pip.assert_not_called()

    def test_install_mmx_recognises_private_prefix_installs(self):
        """回归: 若这里用 shutil.which 而不是引擎的 _which, 从私有前缀装好的 mmx
        会被判成"没装", 每次部署都重装一遍。"""
        import install_mmx
        with mock.patch.object(ds, "_which",
                               side_effect=lambda n: "/x/tools/node/bin/mmx" if n == "mmx" else None):
            self.assertTrue(install_mmx.check_mmx_installed())

    def test_bootstrap_delegates_to_deploy_scan(self):
        import bootstrap_device as bs
        with open(bs.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("deploy_scan.py", src, "bootstrap 应当委托给 deploy_scan")
        self.assertNotIn('"mmx-cli"', src, "bootstrap 不该再自己 pip 装 mmx-cli")

    def test_deps_auto_ensure_env_runs(self):
        """回归: ``ensure_env`` 把 ``collect()`` 的结果直接交给 ``_render``, 而
        ``_render`` 要读 ``ok`` 键 —— v5.4.34~v5.4.35 期间 ``collect()`` 没给这个键,
        于是 **管线第 [0] 步(via54_auto.py 的环境自检)一进去就 KeyError**。
        这条路径当时没有任何测试覆盖, 所以一直没被发现。"""
        import deps_auto
        with contextlib.redirect_stdout(io.StringIO()):
            ok, problems = deps_auto.ensure_env(install=False)
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(problems, list)

    def test_deps_auto_dry_run_never_installs(self):
        import deps_auto
        with mock.patch.object(ds, "collect", wraps=ds.collect) as coll, \
                contextlib.redirect_stdout(io.StringIO()):
            deps_auto.ensure_env(install=False, dry_run=True, only=["ocr"])
        self.assertFalse(coll.call_args.kwargs["install"])
        self.assertTrue(coll.call_args.kwargs["dry_run"])
        self.assertEqual(coll.call_args.kwargs["only"], ["ocr"])

    def test_deps_auto_main_parses_dry_run_flag(self):
        import deps_auto
        argv = ["--check", "--dry-run", "--skip-heavy", "--only", "ocr"]
        kw = deps_auto._parse(argv)
        self.assertFalse(kw["install"])
        self.assertTrue(kw["dry_run"])
        self.assertFalse(kw["include_heavy"])
        self.assertEqual(kw["only"], ["ocr"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
