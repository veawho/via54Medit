#!/usr/bin/env python3
"""test_deploy_scan.py — 部署扫描器的平台感知 / 按需安装 不变量

这些用例守的是本功能的核心承诺:
  * **只部署与平台相关的** —— Windows 上不装 macOS 独有的东西, 反之亦然;
    与平台无关的能力必须标成"不适用", 且**探测与安装都不得被调用**。
  * **只部署缺失的** —— 已就绪的能力不会被重装; ``--check`` 一律不装。
  * **按正确通道装** —— mmx-cli 走 npm(它**不是** PyPI 包), Python 包走 pip。
  * **OCR 真的被检测** —— 缺 paddleocr 必须被报出来并按 pip 通道补齐。
"""
import io
import json
import os
import sys
import unittest
import contextlib
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import deploy_scan as ds                                        # noqa: E402


class _Recorder:
    """把矩阵里每个能力的 probe/install 换成记录器, 保留**真实的平台分类**。"""

    def __init__(self, missing=()):
        self.missing = set(missing)
        self.probes = []
        self.installs = []

    def probe(self, key):
        self.probes.append(key)
        return (key not in self.missing), ("ok" if key not in self.missing else "missing")

    def install(self, key):
        self.installs.append(key)
        return True, "装好了"

    def matrix(self, real, *a, **kw):
        caps = real(*a, **kw)
        for c in caps:
            c._probe = (lambda c=c: self.probe(c.key))
            c._install = (lambda c=c: self.install(c.key))
        return caps


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


class TestEntrypoints(unittest.TestCase):
    """两个入口脚本必须共用同一引擎, 且 mmx 安装不再走 pip。"""

    def test_install_mmx_uses_npm_and_not_pip(self):
        import install_mmx
        with mock.patch.object(install_mmx.shutil, "which",
                               side_effect=lambda n: "/usr/bin/" + n), \
                mock.patch.object(ds, "npm_install", return_value=(True, "ok")) as npm, \
                mock.patch.object(ds, "pip_install", return_value=(True, "ok")) as pip:
            ok, detail = install_mmx.install_mmx_cli()
        self.assertTrue(ok, detail)
        npm.assert_called_once_with("mmx-cli")
        pip.assert_not_called()

    def test_bootstrap_delegates_to_deploy_scan(self):
        import bootstrap_device as bs
        with open(bs.__file__, encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("deploy_scan.py", src, "bootstrap 应当委托给 deploy_scan")
        self.assertNotIn('"mmx-cli"', src, "bootstrap 不该再自己 pip 装 mmx-cli")


if __name__ == "__main__":
    unittest.main(verbosity=2)
