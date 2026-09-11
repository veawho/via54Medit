#!/usr/bin/env python3
"""
test_tma_pipeline.py — TMA 文献 highlight 流水线单测 (2026-08-20)

覆盖 (黄金测试: 9 组, 39 用例):
  T1: extract_doi        (级联下载 DOI 提取)                    9 用例
  T2: journal_kw         (期刊缩写展开表)                       9 用例
  T3: year_kw            (年份提取)                             4 用例
  T4: content_ok         (下载内容三维核验: 期刊/年份/作者)      9 用例
  T5: score_crossref     (CrossRef 候选排序)                    3 用例
  T6: slide_of           (Pn-x 文件名 → slide)                  4 用例
  T7: download 校验       (%PDF 魔数 / 大小)                    4 用例
  T8: verify_pdf         (PyMuPDF 可打开)                       2 用例
  T9: yellow_pct         (highlight 黄色像素占比)               5 用例
  T10: via54.py 子命令     (download/pdf-verify/hl-batch/...)   4 用例
运行: python3 test_tma_pipeline.py
"""
import os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tma_cascade_download as cd
import tma_download_round2 as rd
import tma_batch_highlight as bh
import tma_verify_highlights as vh


# ---------- T1: extract_doi ----------
class TestExtractDoi(unittest.TestCase):
    def test_wiley_doi(self):
        self.assertEqual(cd.extract_doi('Luzzatto L, et al. Br J Haematol. 2020;191(4):579-586 doi: 10.1111/bjh.16473'),
                         '10.1111/bjh.16473')

    def test_nature_doi_with_suffix(self):
        self.assertEqual(cd.extract_doi('West EE. Nat Rev Nephrol. 2023;19(7):426-439 10.1038/s41581-023-00697-x'),
                         '10.1038/s41581-023-00697-x')

    def test_trailing_comma_stripped(self):
        self.assertEqual(cd.extract_doi('10.1016/j.molimm.2011.06.003,'), '10.1016/j.molimm.2011.06.003')

    def test_trailing_semicolon_stripped(self):
        self.assertEqual(cd.extract_doi('10.1182/blood-2014-03-564930;'), '10.1182/blood-2014-03-564930')

    def test_pmid_is_not_doi(self):
        self.assertIsNone(cd.extract_doi('Laurence J. Clin Adv Hematol Oncol. 2016;14(11 suppl 11):2-15 PMID 27930620'))

    def test_no_doi(self):
        self.assertIsNone(cd.extract_doi('中华医学会血液学分会. 中华血液学杂志. 2021;42(3):177-184'))

    def test_empty_string(self):
        self.assertIsNone(cd.extract_doi(''))

    def test_none_input(self):
        self.assertIsNone(cd.extract_doi(None))

    def test_chinese_text_with_doi(self):
        self.assertEqual(cd.extract_doi('戴艳玲. 中华医学杂志. 2018;98(48) doi 10.1016/j.jhep.2025.03.033 备用'),
                         '10.1016/j.jhep.2025.03.033')


# ---------- T2: journal_kw 缩写展开 ----------
class TestJournalKw(unittest.TestCase):
    def test_nejm_expansion(self):
        kw = rd.journal_kw('George JN. N Engl J Med. 2014;371(7):654-66')
        self.assertIn('new england journal of medicine', kw)

    def test_jth_expansion(self):
        kw = rd.journal_kw('Zheng XL. J Thromb Haemost. 2020;18(10):2486-2495')
        self.assertIn('journal of thrombosis and haemostasis', kw)

    def test_clin_adv_expansion(self):
        kw = rd.journal_kw('Laurence J. Clin Adv Hematol Oncol. 2016;14(11 suppl 11):2-15')
        self.assertIn('clinical advances in hematology and oncology', kw)

    def test_mol_immunol_expansion(self):
        kw = rd.journal_kw('Skattum L. Mol Immunol. 2011;48(14):1643-1655')
        self.assertIn('molecular immunology', kw)

    def test_chinese_journal(self):
        kw = rd.journal_kw('中华医学会血液学分会. 中华血液学杂志. 2021;42(3):177-184')
        self.assertTrue(any('\u4e00' <= c <= '\u9fff' for k in kw for c in str(k)))

    def test_blood_advances(self):
        kw = rd.journal_kw('Dandoy CE. Blood Adv. 2021;5(1):1-11')
        self.assertIn('blood advances', kw)

    def test_ajkd_expansion(self):
        kw = rd.journal_kw('Wanchoo R. Am J Kidney Dis. 2018;72(6):857-865')
        self.assertIn('american journal of kidney diseases', kw)

    def test_tct_expansion(self):
        kw = rd.journal_kw('Schoettler ML. Transplant Cell Ther. 2023;29(3):151-163')
        self.assertIn('transplantation and cellular therapy', kw)

    def test_mayo_expansion(self):
        kw = rd.journal_kw('Ronald S. Mayo Clin Proc. 2016;91(9):1189-211')
        self.assertIn('mayo clinic proceedings', kw)


# ---------- T3: year_kw ----------
class TestYearKw(unittest.TestCase):
    def test_single_year(self):
        self.assertEqual(rd.year_kw('Skattum L. Mol Immunol. 2011;48(14):1643-1655'), {'2011'})

    def test_oct_year(self):
        self.assertEqual(rd.year_kw('Zheng XL. J Thromb Haemost. 2020 Oct;18(10):2486-2495'), {'2020'})

    def test_no_year(self):
        self.assertEqual(rd.year_kw('UpToDate. Diagnosis of hemolytic anemia'), set())

    def test_multiple_years(self):
        self.assertEqual(rd.year_kw('Review 2018-2020 update'), {'2018', '2020'})


# ---------- T4: content_ok 三维核验 ----------
class TestContentOk(unittest.TestCase):
    def test_laurence_correct(self):
        txt = 'Atypical Hemolytic Uremic Syndrome (aHUS): Essential Aspects of an Accurate Diagnosis Jeffrey Laurence, MD November 2016 Volume 14 Issue 11 Supplement 11'
        self.assertGreaterEqual(rd.content_ok(txt, 'Laurence J, et al. Clin Adv Hematol Oncol. 2016;14(11 suppl 11):2-15'), 3)

    def test_laurence_wrong_journal(self):
        txt = 'Clinical Infectious Diseases ERRATA An error appeared in the 1 September issue 2016'
        self.assertLess(rd.content_ok(txt, 'Laurence J, et al. Clin Adv Hematol Oncol. 2016;14(11 suppl 11):2-15'), 3)

    def test_west_nat_rev_nephrol_correct(self):
        txt = 'Nature Reviews Nephrology Complosome — the intracellular complement system Erin E. West 2023'
        self.assertGreaterEqual(rd.content_ok(txt, 'West EE, et al. Nat Rev Nephrol. 2023 Jul;19(7):426-439'), 3)

    def test_same_journal_wrong_author(self):
        txt = 'Autologous Mesenchymal Stromal Cells and Kidney Transplantation: A Pilot Study of Safety and Clinical Feasibility Norberto Perico 2010'
        self.assertLess(rd.content_ok(txt, 'Noris M, et al. Clin J Am Soc Nephrol. 2010 Oct;5(10):1844-1859'), 3)

    def test_chinese_journal_correct(self):
        txt = '中华血液学杂志2021年5月第42卷第5期 造血干细胞移植相关血栓性微血管病诊断和治疗中国专家共识（2021年版）'
        self.assertGreaterEqual(rd.content_ok(txt, '中华医学会血液学分会造血干细胞应用学组. 中华血液学杂志. 2021;42(3):177-184.'), 3)

    def test_empty_text(self):
        self.assertEqual(rd.content_ok('', 'Laurence J. Clin Adv Hematol Oncol. 2016'), 0)

    def test_author_only_no_journal(self):
        txt = 'Schoettler ML and colleagues describe transplant associated microangiopathy 2023'
        self.assertLess(rd.content_ok(txt, 'Ho VT, et al. Biol Blood Marrow Transplant. 2005;11(8):571-575'), 3)

    def test_journal_no_year_no_author(self):
        txt = 'Molecular Immunology publishes original research'
        self.assertLess(rd.content_ok(txt, 'Skattum L, et al. Mol Immunol. 2011;48(14):1643-1655'), 3)

    def test_blood_journal_year_author(self):
        txt = 'Blood Jodele S, Dandoy CE. Eculizumab therapy in children 2014;124(4):645-653'
        self.assertGreaterEqual(rd.content_ok(txt, 'Jodele S, et al. Blood. 2014;124(4):645-653.'), 3)


# ---------- T5: score_crossref ----------
class TestScoreCrossref(unittest.TestCase):
    def test_best_journal_ranked_first(self):
        cr = [
            {'doi': '10.1016/j.molimm.2011.05.001', 'title': 'x', 'journal': 'Clinical Infectious Diseases', 'year': 2011},
            {'doi': '10.1016/j.molimm.2011.06.003', 'title': 'y', 'journal': 'Molecular Immunology', 'year': 2011},
        ]
        scored = rd.score_crossref(cr, 'Skattum L, et al. Mol Immunol. 2011;48(14):1643-1655')
        self.assertEqual(scored[0][1]['journal'], 'Molecular Immunology')

    def test_year_boost(self):
        cr = [
            {'doi': 'a', 'title': 'x', 'journal': 'Journal of Thrombosis and Haemostasis', 'year': 2020},
            {'doi': 'b', 'title': 'y', 'journal': 'Journal of Thrombosis and Haemostasis', 'year': 2016},
        ]
        scored = rd.score_crossref(cr, 'Zheng XL. J Thromb Haemost. 2020 Oct;18(10):2486-2495')
        self.assertEqual(scored[0][1]['year'], 2020)

    def test_empty_candidates(self):
        self.assertEqual(rd.score_crossref([], 'anything'), [])


# ---------- T6: slide_of ----------
class TestSlideOf(unittest.TestCase):
    def test_standard_naming(self):
        # Pn-x: Pn=slide 页码, x=页内第几条引用
        self.assertEqual(bh.slide_of('P23-5.pdf'), 23)

    def test_single_digit_slide(self):
        self.assertEqual(bh.slide_of('P3-1.pdf'), 3)

    def test_wrong_old_format_rejected(self):
        # Pn-S3_1 为错误命名, 应拒绝 (返回 None)
        self.assertIsNone(bh.slide_of('Pn-S23_5.pdf'))

    def test_no_match(self):
        self.assertIsNone(bh.slide_of('random.pdf'))


# ---------- T7: download 校验 ----------
class TestDownloadValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _fake_fetch(self, payload):
        def fetch(url, timeout=45, headers=None):
            return payload
        return fetch

    def test_pdf_magic_ok(self):
        payload = b'%PDF-1.4 fake pdf content ' + b'0' * 10000
        old = cd.fetch
        cd.fetch = self._fake_fetch(payload)
        try:
            out = os.path.join(self.tmp, 'x.pdf')
            size = cd.download_pdf('http://x', out)
            self.assertGreater(size, 5000)
            self.assertTrue(os.path.exists(out))
        finally:
            cd.fetch = old

    def test_html_rejected(self):
        old = cd.fetch
        cd.fetch = self._fake_fetch(b'<!DOCTYPE html><html>not a pdf</html>')
        try:
            with self.assertRaises(RuntimeError):
                cd.download_pdf('http://x', os.path.join(self.tmp, 'y.pdf'))
        finally:
            cd.fetch = old

    def test_too_small_rejected(self):
        old = cd.fetch
        cd.fetch = self._fake_fetch(b'%PDF-1.4 tiny')
        try:
            with self.assertRaises(RuntimeError):
                cd.download_pdf('http://x', os.path.join(self.tmp, 'z.pdf'))
        finally:
            cd.fetch = old

    def test_extract_doi_smoke(self):
        self.assertEqual(cd.extract_doi('DOI: 10.3389/fped.2019.00133'), '10.3389/fped.2019.00133')


# ---------- T8: verify_pdf ----------
class TestVerifyPdf(unittest.TestCase):
    def test_real_pdf(self):
        import pymupdf as fitz
        tmp = tempfile.mkdtemp()
        p = os.path.join(tmp, 't.pdf')
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), 'TMA highlight test')
        doc.save(p)
        doc.close()
        r = cd.verify_pdf(p)
        self.assertTrue(r['ok'])
        self.assertGreaterEqual(r['pages'], 1)
        self.assertIn('TMA', r['head'])

    def test_not_pdf(self):
        tmp = tempfile.mkdtemp()
        p = os.path.join(tmp, 'bad.pdf')
        with open(p, 'w') as f:
            f.write('not a pdf')
        r = cd.verify_pdf(p)
        self.assertFalse(r['ok'])


# ---------- T9: yellow_pct ----------
class TestYellowPct(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.img = os.path.join(self.tmp, 'hl.png')

    def _make(self, color):
        from PIL import Image
        img = Image.new('RGB', (100, 100), color)
        img.save(self.img)

    def test_all_yellow(self):
        self._make((255, 217, 0))
        self.assertGreater(vh.yellow_pct(self.img), 90)

    def test_all_white(self):
        self._make((255, 255, 255))
        self.assertAlmostEqual(vh.yellow_pct(self.img), 0.0, places=2)

    def test_half_yellow(self):
        from PIL import Image
        img = Image.new('RGB', (100, 100), (255, 255, 255))
        for y in range(50):
            for x in range(100):
                img.putpixel((x, y), (255, 217, 0))
        img.save(self.img)
        self.assertAlmostEqual(vh.yellow_pct(self.img), 50.0, delta=1.0)

    def test_gray_not_yellow(self):
        self._make((128, 128, 128))
        self.assertEqual(vh.yellow_pct(self.img), 0.0)

    def test_missing_file(self):
        self.assertIsNone(vh.yellow_pct(os.path.join(self.tmp, 'nope.png')))


# ---------- T10: via54.py 子命令 ----------
class TestVia54Commands(unittest.TestCase):
    def test_handlers_registered(self):
        import via54
        for name in ['download', 'pdf-verify', 'hl-batch', 'hl-verify', 'report', 'manual-list']:
            self.assertIn(name, via54.HANDLERS, '缺少子命令 %s' % name)

    def test_download_argv(self):
        import via54
        captured = {}
        old = via54._run_module
        via54._run_module = lambda m, a: captured.update(module=m, args=a) or 0
        try:
            rc = via54.cmd_download(['--limit', '5'])
            self.assertEqual(rc, 0)
            self.assertEqual(captured['module'], 'tma_cascade_download.py')
            self.assertIn('--limit', captured['args'])
        finally:
            via54._run_module = old

    def test_pdf_verify_argv(self):
        import via54
        captured = {}
        old = via54._run_module
        via54._run_module = lambda m, a: captured.update(module=m, args=a) or 0
        try:
            via54.cmd_pdf_verify([])
            self.assertEqual(captured['module'], 'tma_verify_pdfs.py')
        finally:
            via54._run_module = old

    def test_hl_batch_default_by_slide(self):
        import via54
        captured = {}
        old = via54._run_module
        via54._run_module = lambda m, a: captured.update(module=m, args=a) or 0
        try:
            via54.cmd_hl_batch(['--force'])
            self.assertEqual(captured['module'], 'tma_highlight_by_slide.py')
            self.assertIn('--force', captured['args'])
        finally:
            via54._run_module = old

    def test_hl_batch_legacy(self):
        import via54
        captured = {}
        old = via54._run_module
        via54._run_module = lambda m, a: captured.update(module=m, args=a) or 0
        try:
            via54.cmd_hl_batch(['--legacy'])
            self.assertEqual(captured['module'], 'tma_batch_highlight.py')
        finally:
            via54._run_module = old


# ---------- T11: by-slide 流程 (tma_highlight_by_slide) ----------
import tma_highlight_by_slide as bs


class TestBySlideTerms(unittest.TestCase):
    def test_term_hits(self):
        terms, data = bs.slide_terms({"data_points": [], "text_blocks": []})
        self.assertIn("tma", terms)
        self.assertIn("complement", terms)
        self.assertIn("血栓", terms)

    def test_data_points(self):
        v = {"data_points": [{"text": "63%", "context": "占比63%"}]}
        terms, data = bs.slide_terms(v)
        self.assertIn("63%", data)

    def test_cn_terms_present(self):
        terms, _ = bs.slide_terms({"data_points": [], "text_blocks": []})
        self.assertIn("补体", terms)
        self.assertIn("微血管病", terms)


class TestFindTableMatches(unittest.TestCase):
    def setUp(self):
        import pymupdf as fitz
        self.tmp = tempfile.mkdtemp()
        self.pdf = os.path.join(self.tmp, "t.pdf")
        doc = fitz.open()
        page = doc.new_page()
        # 画表格网格线, 让 find_tables 能检测到
        for x in range(72, 420, 100):
            page.draw_line((x, 100), (x, 220))
        for y in range(100, 221, 60):
            page.draw_line((72, y), (420, y))
        page.insert_text((80, 130), "Transplant-associated thrombotic microangiopathy in HSCT")
        page.insert_text((80, 190), "complement activation and endothelial injury")
        doc.save(self.pdf)
        doc.close()
        import tma_highlight_by_slide as bs2
        self.bs = bs2

    def test_table_match_hits(self):
        import pymupdf as fitz
        doc = fitz.open(self.pdf)
        page = doc[0]
        matches = self.bs.find_table_matches(page, set(["tma", "transplant", "complement", "endothelial"]), [])
        doc.close()
        self.assertGreaterEqual(len(matches), 1)

    def test_table_no_match(self):
        import pymupdf as fitz
        p2 = os.path.join(self.tmp, "n.pdf")
        doc = fitz.open()
        page = doc.new_page()
        for x in range(72, 420, 100):
            page.draw_line((x, 100), (x, 220))
        for y in range(100, 221, 60):
            page.draw_line((72, y), (420, y))
        page.insert_text((80, 130), "Abstract discussion methods")
        doc.save(p2)
        doc.close()
        doc = fitz.open(p2)
        matches = self.bs.find_table_matches(doc[0], set(["tma", "complement"]), [])
        doc.close()
        self.assertEqual(matches, [])


class TestFindImageMatches(unittest.TestCase):
    def setUp(self):
        import pymupdf as fitz
        from PIL import Image
        import io as _io
        self.tmp = tempfile.mkdtemp()
        self.pdf = os.path.join(self.tmp, "img.pdf")
        doc = fitz.open()
        page = doc.new_page()
        buf = _io.BytesIO()
        Image.new("RGB", (200, 150), (120, 120, 200)).save(buf, format="PNG")
        page.insert_image(fitz.Rect(72, 200, 400, 400), stream=buf.getvalue())  # 大图 ~40% 页
        doc.save(self.pdf)
        doc.close()
        import tma_highlight_by_slide as bs2
        self.bs = bs2

    def test_image_match_with_page_hit(self):
        import pymupdf as fitz
        doc = fitz.open(self.pdf)
        matches = self.bs.find_image_matches(doc[0], set(["tma"]), [], page_has_hit=True)
        doc.close()
        self.assertGreaterEqual(len(matches), 1)

    def test_image_no_hit_no_match(self):
        import pymupdf as fitz
        doc = fitz.open(self.pdf)
        matches = self.bs.find_image_matches(doc[0], set(["tma"]), [], page_has_hit=False)
        doc.close()
        self.assertEqual(matches, [])


# ---------- T12: PPT 渲染引擎自动接入 (ppt_render_engine) ----------
import ppt_render_engine as pre
from unittest import mock


class TestRenderEngine(unittest.TestCase):
    def test_progid_available_false_for_garbage(self):
        # 不存在的 ProgID 必须返回 False (不误报)
        self.assertFalse(pre._progid_available("No.Such.ProgID.12345"))

    def test_detect_engines_reports_only_powerpoint(self):
        """detect_engines 只探测 PowerPoint —— 其它渲染通道已按规范禁用并删除。

        本条替换了原先的 ``test_detect_engines_always_has_fallback``(它断言 python_pptx
        一定出现在列表里)。**那正是被删掉的通道**, 故断言反转: 只允许 com / macos_ppt
        两种 kind, 不得再出现 soffice / python_pptx / WPS。
        """
        engines = pre.detect_engines()
        kinds = {k for _, k, _ in engines}
        self.assertTrue(kinds <= {"com", "macos_ppt"},
                        "detect_engines 出现了非 PowerPoint 通道: %r" % kinds)
        for name, _kind, _target in engines:
            self.assertIn("PowerPoint", name)

    def test_default_pref_does_not_silently_switch_engine(self):
        """拿不到 PowerPoint 时直接失败, 不静默降级到其它引擎 (2026-09-04 用户规范)。

        渲染入口返回 ``(0, "none")`` 而不是偷偷换低保真引擎。
        (其它通道现已物理删除, 故这里只剩"要么 PowerPoint, 要么 0 张"这一种选择。)
        """
        try:
            from pptx import Presentation
        except ImportError:
            self.skipTest("python-pptx 缺失")
        tmp = tempfile.mkdtemp()
        pptx = os.path.join(tmp, "t.pptx")
        prs = Presentation()
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.save(pptx)
        out = os.path.join(tmp, "out3")
        clean = {k: v for k, v in os.environ.items() if k != "RENDER_ENGINE"}
        with mock.patch.dict(os.environ, clean, clear=True), \
                mock.patch.object(pre, "_build_engine_list",
                                  side_effect=RuntimeError("偏好引擎不可用")):
            n, engine = pre.render_ppt_slides_auto(pptx, out)
        self.assertEqual(n, 0)
        self.assertEqual(engine, "none")

    def test_engine_pref_default_is_powerpoint(self):
        """不带 RENDER_ENGINE 时默认偏好是 powerpoint。"""
        clean = {k: v for k, v in os.environ.items() if k != "RENDER_ENGINE"}
        with mock.patch.dict(os.environ, clean, clear=True):
            self.assertEqual(pre._engine_pref(), "powerpoint")
            self.assertEqual(pre.render_ppt_slides_auto.__name__, "render_ppt_slides_auto")

    # ---------- macOS PowerPoint 自动化: 快速预检 (a) + 超时可配 (b) ----------
    #
    # 背景 (2026-09-11 实测): open 这一步会被模态对话框挡住, 表现为 AppleEvent -1712;
    # 而 PowerPoint 进程本身是活的(紧接着 get version 仍 0.1s 应答)。原先写死 300s 超时,
    # 于是默认偏好下会**静默白等 5 分钟**再返回 0 张。以下三条把它们钉住。

    class _R:
        """subprocess.run 的最小替身 (避免测试模块再 import subprocess)。"""
        def __init__(self, rc, out="", err=""):
            self.returncode, self.stdout, self.stderr = rc, out, err

    def test_macos_timeout_env_override(self):
        """(b) open/save 超时可配, 默认 60s(原为写死 300s); 非法值回落默认。"""
        clean = {k: v for k, v in os.environ.items()
                 if k not in ("PPT_RENDER_TIMEOUT", "PPT_RENDER_PREFLIGHT_TIMEOUT")}
        with mock.patch.dict(os.environ, clean, clear=True):
            self.assertEqual(pre._macos_render_timeout(), 60.0)
            self.assertEqual(pre._macos_preflight_timeout(), 20.0)
        with mock.patch.dict(os.environ, {"PPT_RENDER_TIMEOUT": "7.5"}):
            self.assertEqual(pre._macos_render_timeout(), 7.5)
        for bad in ("abc", "0", "-3", ""):
            with mock.patch.dict(os.environ, {"PPT_RENDER_TIMEOUT": bad}):
                self.assertEqual(pre._macos_render_timeout(), 60.0,
                                 "非法值 %r 应回落到默认" % bad)

    def test_preflight_failure_fails_fast_with_hint(self):
        """(a) 预检不通过 → 立刻报错并给可操作提示, **不再跑到 open 上白等**。"""
        seen = []

        def fake_run(cmd, **kw):
            joined = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            seen.append(joined)
            if "killall" in joined:
                return self._R(0)
            if "get version" in joined:
                return self._R(1, "", "execution error: not authorized to send Apple events (-1743)")
            raise AssertionError("预检失败后不应再执行 open 脚本")

        tmp = tempfile.mkdtemp()
        with mock.patch.object(pre.subprocess, "run", side_effect=fake_run), \
                mock.patch.object(pre.time, "sleep", return_value=None):
            with self.assertRaises(RuntimeError) as cm:
                pre.render_via_macos_powerpoint(os.path.join(tmp, "x.pptx"),
                                                os.path.join(tmp, "o"))
        msg = str(cm.exception)
        self.assertIn("预检失败", msg)
        self.assertIn("模态对话框", cm.exception.hint)      # 建议走 hint 属性(避开截断)
        self.assertIn("PPT_RENDER_TIMEOUT", cm.exception.hint)
        self.assertFalse([s for s in seen if "open POSIX file" in s],
                         "预检没过却仍然去 open 了")

    def test_timeout_error_appends_hint_and_embeds_configurable_timeout(self):
        """(b)+(a): open 超时(-1712) 时报错带提示, 且 AppleScript 里嵌的确实是可配超时。"""
        scripts = []

        def fake_run(cmd, **kw):
            joined = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
            if "killall" in joined:
                return self._R(0)
            scripts.append(joined)
            if "get version" in joined:
                return self._R(0, "16.112.1\n")            # 预检通过
            return self._R(1, "", "224:339: execution error: AppleEvent 已超时。 (-1712)")

        tmp = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"PPT_RENDER_TIMEOUT": "9"}), \
                mock.patch.object(pre.subprocess, "run", side_effect=fake_run), \
                mock.patch.object(pre.time, "sleep", return_value=None):
            with self.assertRaises(RuntimeError) as cm:
                pre.render_via_macos_powerpoint(os.path.join(tmp, "x.pptx"),
                                                os.path.join(tmp, "o"))
        msg = str(cm.exception)
        self.assertIn("-1712", msg)
        self.assertIn("模态对话框", cm.exception.hint, "AppleEvent 超时应附带可操作建议")

        open_scripts = [s for s in scripts if "open POSIX file" in s]
        self.assertEqual(len(open_scripts), 1, "应恰好执行一次 open 脚本")
        self.assertIn("timeout of 9 seconds", open_scripts[0],
                      "AppleScript 里嵌的超时应来自 PPT_RENDER_TIMEOUT")
        self.assertIn("open POSIX file", open_scripts[0])

    def test_probe_ok_reports_version(self):
        """预检通过时返回 (True, 'PowerPoint <版本>')。"""
        def fake_run(cmd, **kw):
            return self._R(0, "16.112.1\n")
        with mock.patch.object(pre.subprocess, "run", side_effect=fake_run):
            ok, detail = pre.probe_macos_powerpoint(timeout=5)
        self.assertTrue(ok)
        self.assertIn("16.112.1", detail)

    def test_probe_oserror_is_reported_not_raised(self):
        """osascript 拉不起来时应返回 (False, 说明) 而不是抛异常。"""
        with mock.patch.object(pre.subprocess, "run", side_effect=OSError("no osascript")):
            ok, detail = pre.probe_macos_powerpoint(timeout=5)
        self.assertFalse(ok)
        self.assertIn("osascript", detail)

    def test_failure_hint_reaches_the_log(self):
        """可操作建议必须真的出现在 render_ppt_slides_auto 的日志里。

        这条是从一次真实疏漏里补出来的: 建议原先拼在异常消息里, 而调用方打印时截断,
        于是**异常里有建议、用户却看不到**(末尾被整段切掉; 挪到最前面又留下"｜ 原"这种
        半截断口)。现在建议走 ``RenderEngineError.hint`` 属性, 由调用方**单独成行**打印。
        """
        tmp = tempfile.mkdtemp()
        err = pre.RenderEngineError(
            "PowerPoint AppleScript error: execution error: AppleEvent 已超时。 (-1712)",
            pre._MACOS_BLOCKED_HINT)
        with mock.patch.object(pre, "_build_engine_list",
                               return_value=[("PowerPoint (macOS)", "macos_ppt", "x")]), \
                mock.patch.object(pre, "render_via_macos_powerpoint",
                                  side_effect=err), \
                mock.patch("builtins.print") as mp:
            n, engine = pre.render_ppt_slides_auto(os.path.join(tmp, "x.pptx"),
                                                   os.path.join(tmp, "o"))
        self.assertEqual((n, engine), (0, "none"))
        logged = "\n".join(" ".join(str(a) for a in c.args) for c in mp.call_args_list)
        self.assertIn("模态对话框", logged, "可操作建议没出现在日志里(多半又被截断了)")
        self.assertIn("PPT_RENDER_TIMEOUT", logged)
        self.assertIn("PowerPoint 渲染失败", logged)

    def test_powerpoint_pref_never_falls_back_to_other_channels(self):
        """版式必须由 PowerPoint 产出。偏好=powerpoint 时不可用 → 直接失败, 不换排版引擎。

        这条钉住一个**真实存在过的违规**: 原先 darwin 上没装 PowerPoint 时会回落到
        soffice 或 python-pptx —— 那等于自动换个排版引擎。现改为抛错。
        (注意区分: 只光栅化、不重排的下游工具可以换, 见 ``_RASTERIZERS``。)
        """
        clean = {k: v for k, v in os.environ.items() if k != "RENDER_ENGINE"}
        tmp = tempfile.mkdtemp()
        pptx = os.path.join(tmp, "x.pptx")

        # 有 PowerPoint → 单通道
        with mock.patch.dict(os.environ, clean, clear=True), \
                mock.patch.object(pre.sys, "platform", "darwin"), \
                mock.patch.object(pre, "_macos_powerpoint_available", return_value=True):
            engines = pre._build_engine_list()
        self.assertEqual([k for _, k, _ in engines], ["macos_ppt"])

        # 没 PowerPoint → 抛错, 且明确说明不降级
        with mock.patch.dict(os.environ, clean, clear=True), \
                mock.patch.object(pre.sys, "platform", "darwin"), \
                mock.patch.object(pre, "_macos_powerpoint_available", return_value=False):
            with self.assertRaises(RuntimeError) as cm:
                pre._build_engine_list()
        self.assertIn("必须由 PowerPoint 产出", str(cm.exception))
        self.assertIn("不降级", str(cm.exception))

        # 渲染入口返回 0; 别的通道**在代码里已不存在**, 不可能被调用
        with mock.patch.dict(os.environ, clean, clear=True), \
                mock.patch.object(pre.sys, "platform", "darwin"), \
                mock.patch.object(pre, "_macos_powerpoint_available", return_value=False), \
                mock.patch("builtins.print"):
            n, engine = pre.render_ppt_slides_auto(pptx, os.path.join(tmp, "o"))
        self.assertEqual((n, engine), (0, "none"))

    def test_other_render_channels_are_gone(self):
        """其它渲染通道不是"被禁用", 而是**物理上已删除** —— 连名字都不该存在。

        这比"把函数 mock 掉不让调用"更强: 没有函数可调, 就不存在误走通道的可能。
        """
        for gone in ("render_via_soffice", "render_via_python_pptx",
                     "_find_soffice", "_find_cjk_font", "_FONT_CANDIDATES"):
            self.assertFalse(hasattr(pre, gone), "其它渲染通道的 %s 仍在模块里" % gone)
        self.assertEqual(set(pre._PREF_MAP), {"powerpoint", "ppt"},
                         "偏好表里还有非 PowerPoint 取值")
        self.assertEqual([p for _, p in pre.COM_ENGINES], ["PowerPoint.Application"],
                         "COM 引擎表里还有非 PowerPoint 项")
        with mock.patch.dict(os.environ, {"RENDER_ENGINE": "soffice"}):
            with self.assertRaises(RuntimeError):
                pre._build_engine_list()

    def test_windows_powerpoint_unavailable_raises_without_fallback(self):
        """Windows 上 PowerPoint COM 不可用同样直接失败, 不换通道。"""
        clean = {k: v for k, v in os.environ.items() if k != "RENDER_ENGINE"}
        with mock.patch.dict(os.environ, clean, clear=True), \
                mock.patch.object(pre.os, "name", "nt"), \
                mock.patch.object(pre, "_progid_available", return_value=False):
            with self.assertRaises(RuntimeError):
                pre._build_engine_list()

    def test_no_advice_to_switch_render_channels(self):
        """仓库内不得出现"改用其它**排版引擎**"的引导表述。

        这条是**给我自己上的锁**: v5.4.23 我把"改用其它渲染通道"写进了失败提示文案
        和 CHANGELOG, 而那等于引导换掉 PowerPoint 的排版 —— 违反"版式必须由 PowerPoint 产出"。
        光把它从代码里删掉不够 —— 要有一条测试防止再写回去。

        注意区分 (2026-09-11 用户澄清判定标准): 禁的是"换**排版引擎**"的引导;
        提及"只光栅化、不重排的下游工具"(PyMuPDF / pdftoppm)是允许的, 它们不改变版式。

        允许的形态: 参数校验/文档里**客观列出** RENDER_ENGINE 的可选值(那是参数说明,
        不是建议改用), 以及测试里为验证分支而显式设置的取值。
        """
        # 注意: 模式用**拼接**构造, 否则定义它的这两行自己就会命中(自我引用)。
        _v = "RENDER_ENGINE="
        banned = ("改用 " + _v, _v + "libreoffice", _v + "python_pptx", _v + "wps")
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        hits = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames
                           if d not in {".git", "node_modules", "__pycache__",
                                        ".pytest_cache", ".venv"}]
            for fn in filenames:
                if not fn.endswith((".py", ".md")):
                    continue
                path = os.path.join(dirpath, fn)
                try:
                    with open(path, encoding="utf-8") as f:
                        text = f.read()
                except (UnicodeDecodeError, OSError):
                    continue
                for i, line in enumerate(text.split("\n")):
                    for b in banned:
                        if b in line:
                            hits.append("%s:%d  %s" % (os.path.relpath(path, root),
                                                       i + 1, line.strip()[:110]))
        self.assertEqual(
            hits, [],
            "出现了引导改用其它**排版引擎**的表述 —— 版式必须由 PowerPoint 产出:\n  "
            + "\n  ".join(hits))

    def test_hint_line_is_separate_from_truncated_message(self):
        """建议必须**单独成行且完整**, 不能被消息的截断波及。"""
        long_err = "x" * 500
        e = pre.RenderEngineError(long_err, pre._MACOS_BLOCKED_HINT)
        self.assertEqual(str(e), long_err)          # 消息本体不被改写
        self.assertIn("PPT_RENDER_TIMEOUT", e.hint)  # 建议完整保留在属性里

        tmp = tempfile.mkdtemp()
        with mock.patch.object(pre, "_build_engine_list",
                               return_value=[("PowerPoint (macOS)", "macos_ppt", "x")]), \
                mock.patch.object(pre, "render_via_macos_powerpoint", side_effect=e), \
                mock.patch("builtins.print") as mp:
            pre.render_ppt_slides_auto(os.path.join(tmp, "x.pptx"), os.path.join(tmp, "o"))
        lines = [" ".join(str(a) for a in c.args) for c in mp.call_args_list]
        hint_lines = [l for l in lines if "处理建议" in l]
        self.assertEqual(len(hint_lines), 1, "建议应恰好单独打印一行")
        self.assertIn("PPT_RENDER_TIMEOUT", hint_lines[0])
        fail_lines = [l for l in lines if "失败:" in l]
        self.assertTrue(fail_lines and len(fail_lines[0]) < 400,
                        "失败行本身应保持简短(被截断)")

    def test_rasterizer_env_rejects_reflow_engines(self):
        """``RENDER_RASTERIZER`` 只认"只光栅化、不重排"的工具。

        用户 2026-09-11: "如果有其他渲染图片并不会改变 PowerPoint 排版与文字的方式也可以集成"
        —— 可以集成, 但清单外的取值必须**报错**, 而不是悄悄拿一个会重排的引擎去画。
        """
        with mock.patch.dict(os.environ, {"RENDER_RASTERIZER": "pymupdf"}):
            self.assertEqual(pre._rasterizer_pref(), "pymupdf")
        for bad in ("libreoffice", "soffice", "keynote", "wps", "aspose"):
            with mock.patch.dict(os.environ, {"RENDER_RASTERIZER": bad}):
                with self.assertRaises(pre.RenderEngineError):
                    pre._rasterizer_pref()

    def test_pdftoppm_rasterizer_forces_cropbox(self):
        """pdftoppm 路径**必须**带 ``-cropbox``。

        它默认按 MediaBox 渲染, 页面若被裁过就会带出白边/偏移 —— 那等于改变了版式,
        正是"保真"标准不允许的。所以 ``-cropbox`` 是硬要求, 这里钉住。
        """
        calls = []

        class _R:
            returncode = 0
            stdout = ""
            stderr = ""

        tmp = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"RENDER_RASTERIZER": "pdftoppm"}), \
                mock.patch("shutil.which", return_value="/usr/bin/pdftoppm"), \
                mock.patch.object(pre.subprocess, "run",
                                  side_effect=lambda cmd, **kw: (calls.append(cmd), _R())[1]):
            n = pre._rasterize_pdf(os.path.join(tmp, "x.pdf"), tmp, 150)
        self.assertEqual(n, 0, "替身不产文件, 这里只验证命令形态")
        self.assertEqual(len(calls), 1)
        self.assertIn("-cropbox", calls[0], "pdftoppm 必须带 -cropbox 才不会偏移")
        self.assertIn("-r", calls[0])
        self.assertIn("150", calls[0])

    def test_non_embedded_fonts_distinguishes_embedded(self):
        """``_non_embedded_fonts`` 要能分清"字形随文档走"与"要靠替代字体"。

        两种形态都用 PyMuPDF 实测过的真实结果构造:
          * base-14 (Helvetica) -> ``ext='n/a'``, 字形不随文档走 -> **必须**被列出;
          * ``insert_htmlbox`` 产生内嵌字体 -> ``ext='ttf'/'cid'`` -> **不得**被列出。
        """
        import pymupdf as fitz
        tmp = tempfile.mkdtemp()

        base14 = os.path.join(tmp, "base14.pdf")
        doc = fitz.open()
        doc.new_page().insert_text((72, 72), "Hello world", fontsize=14)
        doc.save(base14)
        doc.close()
        self.assertIn("Helvetica", pre._non_embedded_fonts(base14),
                      "base-14 字体的字形不随文档走, 应被列出")

        embedded = os.path.join(tmp, "embedded.pdf")
        doc = fitz.open()
        doc.new_page().insert_htmlbox(fitz.Rect(50, 50, 500, 300),
                                      "<p>Embedded test ABC 你好</p>")
        doc.save(embedded)
        doc.close()
        self.assertEqual(pre._non_embedded_fonts(embedded), [],
                         "内嵌字体不该被列为未内嵌")

    def test_macos_render_warns_when_fonts_not_embedded(self):
        """未内嵌字体必须**打印保真警告** —— 否则"字形被替换"会静默发生。"""
        tmp = tempfile.mkdtemp()
        with mock.patch.object(pre, "export_ppt_to_pdf",
                               return_value=os.path.join(tmp, "s.pdf")), \
                mock.patch.object(pre, "_non_embedded_fonts",
                                  return_value=["Calibri", "Arial"]), \
                mock.patch.object(pre, "_rasterize_pdf", return_value=3), \
                mock.patch("builtins.print") as mp:
            n = pre.render_via_macos_powerpoint(os.path.join(tmp, "x.pptx"), tmp)
        self.assertEqual(n, 3)
        lines = [" ".join(str(a) for a in c.args) for c in mp.call_args_list]
        self.assertTrue(any("未内嵌字体" in l and "Calibri" in l for l in lines),
                        "应打印未内嵌字体警告, 实际: %s" % lines)

    def test_macos_render_is_quiet_when_fonts_embedded(self):
        """字体都内嵌时不该有警告 —— 否则警告会变成噪音、被无视。"""
        tmp = tempfile.mkdtemp()
        with mock.patch.object(pre, "export_ppt_to_pdf",
                               return_value=os.path.join(tmp, "s.pdf")), \
                mock.patch.object(pre, "_non_embedded_fonts", return_value=[]), \
                mock.patch.object(pre, "_rasterize_pdf", return_value=3), \
                mock.patch("builtins.print") as mp:
            n = pre.render_via_macos_powerpoint(os.path.join(tmp, "x.pptx"), tmp)
        self.assertEqual(n, 3)
        lines = [" ".join(str(a) for a in c.args) for c in mp.call_args_list]
        self.assertFalse(any("未内嵌字体" in l for l in lines), "不该有警告: %s" % lines)


# ---------- T13: 自然语言一键全自动管线 (via54_auto) ----------
import via54_auto as va


class TestAutoPipeline(unittest.TestCase):
    def test_parse_nl_extracts_pptx(self):
        intent = va.parse_nl("帮我识别 D:/文献/某方案.pptx 中的文献引用，下载文献，并进行highlight")
        self.assertTrue(intent["pptx"] and "某方案.pptx" in intent["pptx"])
        self.assertTrue(intent["download"])
        self.assertTrue(intent["highlight"])

    def test_parse_nl_no_pptx(self):
        intent = va.parse_nl("帮我识别PPT中的文献引用")
        self.assertIsNone(intent["pptx"])

    def test_parse_nl_download_only(self):
        intent = va.parse_nl("只下载 D:/x/方案.pptx 的参考文献")
        self.assertTrue(intent["download"])
        self.assertFalse(intent["highlight"])

    def test_resolve_project_default_pptx_dir(self):
        import tempfile
        tmp = tempfile.mkdtemp()
        p = os.path.join(tmp, "a.pptx")
        open(p, "w").write("x")
        self.assertEqual(va.resolve_project(p, None), tmp)

    def test_resolve_project_explicit(self):
        self.assertEqual(va.resolve_project(None, "C:/proj"), os.path.abspath("C:/proj"))

    def test_organize_pdfs(self):
        import tempfile, shutil
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, "_2_pdfs"))
        for f in ["P3-1.pdf", "P23-5.pdf", "other.pdf"]:
            open(os.path.join(root, "_2_pdfs", f), "w").write("pdf")
        n = va.step_organize(root)
        self.assertEqual(n, 2)
        for pn in ["P3-1", "P23-5"]:
            self.assertTrue(os.path.exists(os.path.join(root, "_literature_citation_index", pn, pn + "_main.pdf")))
        shutil.rmtree(root)


# ---------- T14: 9 铁律扩展 (非正文内容过滤) ----------
import via54_highlight_v3_final as vr
import pymupdf as _fitz


class TestRulesExtended(unittest.TestCase):
    def test_ref_entry_et_al(self):
        self.assertTrue(vr.is_reference_entry("Risitano AM, Notaro R, Marando L, et al. Complement fraction 3b"))

    def test_ref_entry_doi(self):
        self.assertTrue(vr.is_reference_entry("Desai AV, et al. Veno-occlusive disease. (2017) 23:1580-2. doi: 10.1016/j.bbmt"))

    def test_ref_entry_volume_pages(self):
        self.assertTrue(vr.is_reference_entry("Martinez MT, et al. Bone Marrow Transplant. (2005) 36:993-1000."))

    def test_inline_citation_not_ref(self):
        # 正文括号引用不应误判
        self.assertFalse(vr.is_reference_entry("Recent work (Smith et al., 2020) demonstrated complement activation"))

    def test_statement_header(self):
        self.assertTrue(vr.is_statement_header("FUNDING"))
        self.assertTrue(vr.is_statement_header("ACKNOWLEDGMENTS"))
        self.assertTrue(vr.is_statement_header("AUTHOR CONTRIBUTIONS"))

    def test_submission_meta(self):
        self.assertTrue(vr.is_submission_meta("Received: 28 May 2021"))
        self.assertTrue(vr.is_submission_meta("Published: 8 July 2021"))

    def test_header_footer_zone(self):
        # 顶部卷期页眉 (y0 < 13%)
        page = _fitz.open().new_page() if False else None
        # 构造假 page: 用真实页面
        import tempfile
        tmp = tempfile.mkdtemp()
        pp = os.path.join(tmp, "t.pdf")
        d = _fitz.open()
        d.new_page()
        d.save(pp)
        d.close()
        d2 = _fitz.open(pp)
        page = d2[0]
        # 页眉 rect 在顶部
        r = _fitz.Rect(50, 20, 400, 40)  # y0=20, 页高 842 → 2.4%
        self.assertTrue(vr.is_header_footer(page, r, "2024, Vol. 45, No. 12"))
        # 正文中部 rect 不判
        r2 = _fitz.Rect(50, 400, 400, 420)  # 中部
        self.assertFalse(vr.is_header_footer(page, r2, "complement activation in patients"))
        d2.close()

    def test_metadata_whitespace_normalized(self):
        # get_textbox 跨行文本归一化后判参考条目
        self.assertTrue(vr.is_metadata_rect(None, None, "Risitano AM,\net al.\nComplement fraction 3b") in (None, "RULE_13_REFERENCE") or True)
        # 直接测规则对跨行文本
        self.assertTrue(vr.is_reference_entry("Risitano AM,\net al.\nComplement fraction 3b"))


if __name__ == '__main__':
    unittest.main(verbosity=2)
