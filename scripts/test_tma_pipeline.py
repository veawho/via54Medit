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
import os, sys, io, tempfile, unittest
from pathlib import Path

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
    def test_new_naming(self):
        self.assertEqual(bh.slide_of('Pn-S23_5.pdf'), 23)

    def test_single_digit_slide(self):
        self.assertEqual(bh.slide_of('Pn-S3_1.pdf'), 3)

    def test_old_naming(self):
        self.assertIsNone(bh.slide_of('P23-5.pdf'))

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
        import fitz
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
        from PIL import Image
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

    def test_hl_batch_force_flag(self):
        import via54
        captured = {}
        old = via54._run_module
        via54._run_module = lambda m, a: captured.update(module=m, args=a) or 0
        try:
            via54.cmd_hl_batch(['--force'])
            self.assertEqual(captured['module'], 'tma_batch_highlight.py')
            self.assertIn('--force', captured['args'])
        finally:
            via54._run_module = old


if __name__ == '__main__':
    unittest.main(verbosity=2)
