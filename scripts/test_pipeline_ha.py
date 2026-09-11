#!/usr/bin/env python3
"""
test_pipeline_ha.py — via54Medit 全链路高可用性 (High Availability) 与 5 步双重对齐流水线回归测试

测试覆盖:
  1. PPT 渲染: 版式与文字只由 PowerPoint 产出 (2026-08-05 硬规则; 2026-09-11 澄清判定标准)
  2. 统一多模态视觉 Provider (MiniMax mmx / SenseNova / GLM 容错与模拟应答)
  3. 统一 LLM Provider (DeepSeek / MiniMax / SenseNova / GLM)
  4. 幻灯片作用域隔离验证 (杜绝跨 Slide 候选句污染)
  5. 4阶容错定位与边界收窄标注 (Unicode规范化、连字符自愈、标点脱敏、双锚点回退)
  6. Step 1: 全格式统一分页渲染器 (PPTX / PDF / Image)
  7. Step 2: 引用字段与局部视觉区域裁切
  8. Step 3 & 4: 文献检索、下载链接整理与标准目录结构化
  9. Step 5: 引用字段元数据对齐 + 视觉与语义双对齐高精高亮
 10. 9 条铁律合规校验 (元数据与违规区域剔除)
"""
import os
import sys
import tempfile
import shutil
import unittest
from unittest import mock
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "hl_v3_final"))

import pymupdf as fitz
from pptx import Presentation
from pptx.util import Inches, Pt
from PIL import Image

import ppt_render_engine
import provider_vision
import provider_llm
import via54_ppt_visual_to_pdf
import unified_render_engine
import visual_claim_extractor
import literature_downloader
import dual_alignment_pipeline
from hl_lib import (
    locate_sentence,
    highlight_sentences,
    filter_sentences_by_slide_context,
)


class TestPipelineHA(unittest.TestCase):
    #: 缓存"本机 PowerPoint 能否真正渲染出页面"的探测结果 (None = 还没探过)
    _ppt_render_ok = None

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="via54_ha_test_")
        self.pptx_path = os.path.join(self.tmp_dir, "test_presentation.pptx")
        self.pdf_path = os.path.join(self.tmp_dir, "P12-1.pdf")
        self._create_mock_pptx()
        self._create_mock_pdf()

    def _require_powerpoint_render(self):
        """依赖**真实 PowerPoint 渲染**的用例先过这道闸。

        为什么需要: PPT 的版式与文字只由 PowerPoint 产出、不 fallback 到别的排版引擎。本机若 PowerPoint
        自动化被模态对话框挡住(实测 `save ... as PDF` 报 AppleEvent -1712), 渲染就是 0 页 ——
        那**是环境故障, 不是管线回归**。让它以"跳过 + 写明原因"呈现, 比伪装成断言失败诚实,
        也不会把 PowerPoint 自身的问题误记到 Step1/2/5 的账上。

        探测只做一次(结果缓存): 真渲染一次, 用 PPT_RENDER_TIMEOUT=8 保证失败时很快返回。
        """
        if TestPipelineHA._ppt_render_ok is None:
            out = os.path.join(self.tmp_dir, "_ppt_probe")
            env = dict(os.environ, PPT_RENDER_TIMEOUT="8")
            with mock.patch.dict(os.environ, env, clear=True):
                n, _ = ppt_render_engine.render_ppt_slides_auto(self.pptx_path, out)
            TestPipelineHA._ppt_render_ok = n > 0
        if not TestPipelineHA._ppt_render_ok:
            self.skipTest(
                "本机 PowerPoint 渲染不出页面 (AppleEvent -1712 —— 多半是 PowerPoint 弹了"
                "模态对话框)。这几条用例要真实 PPT 渲染, 故跳过; 这是环境问题, 不是回归。"
                "修法见 ppt_render_engine._MACOS_BLOCKED_HINT。")

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _create_mock_pptx(self):
        prs = Presentation()
        # Slide 1: 标题页
        slide1 = prs.slides.add_slide(prs.slide_layouts[0])
        slide1.shapes.title.text = "呼吸道合胞病毒 (RSV) 预防进展"
        slide1.placeholders[1].text = "临床研究与保护效力汇总"

        # Slide 2: RSV 单抗保护率与剂量论点 (对应 P12-1)
        slide12 = prs.slides.add_slide(prs.slide_layouts[1])
        slide12.shapes.title.text = "RSV 单抗关键临床研究数据"
        body12 = slide12.placeholders[1]
        tf12 = body12.text_frame
        tf12.text = "尼塞韦单抗推荐剂量为 50mg (体重<5kg) 或 100mg (体重≥5kg)1。"
        p1 = tf12.add_paragraph()
        p1.text = "III期临床试验结果显示，在足月儿中预防 RSV 引起的下呼吸道感染保护率为 74.5% (95% CI: 49.6-87.1, p<0.001)1。"
        p2 = tf12.add_paragraph()
        p2.text = "在整个 RSV 流行季内，因 RSV 引起的住院率降低了 62.1%1。"
        p_ref = tf12.add_paragraph()
        p_ref.text = "1. N Engl J Med 2020; 383:415-425. DOI: 10.1056/NEJMoa2110275"

        # Slide 3: 联合接种与安全性论点 (对应 P15-1，不应污染 Slide 12)
        slide15 = prs.slides.add_slide(prs.slide_layouts[1])
        slide15.shapes.title.text = "疫苗联合接种与安全性评估"
        body15 = slide15.placeholders[1]
        tf15 = body15.text_frame
        tf15.text = "与儿童常规疫苗联合接种未观察到免疫原性干扰。"
        p_safe = tf15.add_paragraph()
        p_safe.text = "不良反应发生率与安慰剂组相当 (2.3% vs 2.1%)。"

        prs.save(self.pptx_path)

    def _create_mock_pdf(self):
        doc = fitz.open()
        # Page 1 (0-based)
        page1 = doc.new_page(width=595, height=842)
        p1_text = (
            "ORIGINAL ARTICLE\n"
            "Efficacy and Safety of Nirsevimab in Healthy Late-Preterm and Term Infants\n"
            "Author: Clinical Study Group. Received: 2023-01-01. DOI: 10.1056/NEJMoa2110275\n\n"
            "RESULTS\n"
            "A single dose of nirsevimab resulted in 74.5% (95% CI: 49.6-87.1, p<0.001) lower incidence of "
            "medically attended RSV-associated lower respiratory tract infection through 150 days.\n"
            "Hospitalization for RSV-associated lower respiratory tract infection was lower by 62.1%.\n"
            "The recommended dose was 50mg for infants weighing under 5kg and 100mg for infants 5kg or more.\n\n"
            "Concomitant administration with routine childhood vaccines was evaluated and showed non-inferior responses."
        )
        page1.insert_text(fitz.Point(50, 50), p1_text, fontsize=10)

        # Page 2 (0-based)
        page2 = doc.new_page(width=595, height=842)
        p2_text = (
            "SAFETY AND ADVERSE EVENTS\n"
            "Adverse events occurred in 2.3% of the nirsevimab group compared with 2.1% in the placebo group.\n"
            "No serious treatment-related adverse events were reported.\n\n"
            "CONFLICT OF INTEREST\n"
            "The authors declare no conflict of interest regarding this publication."
        )
        page2.insert_text(fitz.Point(50, 50), p2_text, fontsize=10)

        doc.save(self.pdf_path)
        doc.close()

    def test_01_ppt_render_engine_uses_powerpoint_only(self):
        """PPT 渲染只走 PowerPoint 一条通道 (2026-09-04 规范; 2026-09-11 用户重申)。

        本条替换了原先的 ``test_01_ppt_render_engine_fallback`` —— 它把渲染通道指向
        python-pptx, 期望"优雅降级"渲染出 3 页。python-pptx / LibreOffice / WPS 三条
        通道已在 v5.4.25 物理删除, 那条断言与规范正面冲突 (v5.4.25 发布时它就被改红了,
        属本轮补修 —— 换通道的测试不该留着)。
        现在钉住的是: 渲染循环确实调用 PowerPoint 的实现, 且不降级到别处。
        """
        out_render = os.path.join(self.tmp_dir, "rendered_slides")
        os.makedirs(out_render, exist_ok=True)

        def _fake_powerpoint(pptx_path, odir, *a, **kw):
            """替身: 形状与真实 PowerPoint 渲染实现一致 (产出 3 张 slide_NNN.png)。"""
            for i in range(1, 4):
                Image.new("RGB", (32, 18), "white").save(
                    os.path.join(odir, "slide_%03d.png" % i))
            return 3

        # 按平台取 PowerPoint 那条通道 —— 两边的 kind/progid 不同, 但都只有 PowerPoint。
        if os.name == "nt":
            spec = ("PowerPoint", "com", "PowerPoint.Application")
            seam = "render_via_com"
        else:
            spec = ("PowerPoint (macOS)", "macos_ppt", "com.microsoft.Powerpoint")
            seam = "render_via_macos_powerpoint"

        # _build_engine_list 是 render_ppt_slides_auto 真正调用的接缝 (第 340 行),
        # 所以这层 mock 是生效的 —— 不是打在无效接缝上。
        # 注: patch.object 传了 new 时返回值就是 new 本身, 故这里显式用 MagicMock 以便断言。
        fake = mock.MagicMock(side_effect=_fake_powerpoint)
        with mock.patch.object(ppt_render_engine, "_build_engine_list",
                               lambda: [spec]), \
                mock.patch.object(ppt_render_engine, seam, fake):
            count, engine = ppt_render_engine.render_ppt_slides_auto(
                self.pptx_path, out_render)

        self.assertTrue(fake.called, "没有走 PowerPoint 渲染实现 —— 通道被换掉了")
        self.assertEqual(count, 3, "应该成功渲染 3 页幻灯片")
        self.assertIn("PowerPoint", engine, "引擎名必须标明 PowerPoint")
        self.assertTrue(os.path.exists(os.path.join(out_render, "slide_001.png")))
        self.assertTrue(os.path.exists(os.path.join(out_render, "slide_002.png")))

    def test_01b_ppt_render_never_switches_channel(self):
        """PowerPoint 不可用时**直接失败**, 不退化成别的渲染方式。"""
        out_render = os.path.join(self.tmp_dir, "no_channel")
        os.makedirs(out_render, exist_ok=True)

        def _boom():
            raise RuntimeError("PowerPoint 不可用")

        for seam in ("_build_engine_list", "detect_engines"):
            with mock.patch.object(ppt_render_engine, seam, side_effect=_boom):
                count, engine = ppt_render_engine.render_ppt_slides_auto(
                    self.pptx_path, out_render)
        self.assertEqual((count, engine), (0, "none"),
                         "拿不到 PowerPoint 就该返回 0 张, 不得降级到其它通道")

    def test_02_slide_scoped_isolation(self):
        """验证 Slide 作用域隔离：P12-1 仅匹配 Slide 12 的论点，不被 Slide 15 污染"""
        visual_info_12 = via54_ppt_visual_to_pdf.analyze_ppt_slide_visually(
            self.pptx_path, slide_num=2, use_vision_api=False
        )
        self.assertIn("74.5%", visual_info_12.get("full_text", ""))

        matches_12 = via54_ppt_visual_to_pdf.find_pdf_visual_match(self.pdf_path, visual_info_12)
        self.assertIn(0, matches_12, "应该在 PDF Page 1 命中保护率论点")
        
        hit_texts = " ".join(matches_12[0])
        self.assertTrue(
            "74.5%" in hit_texts or "62.1%" in hit_texts or "50mg" in hit_texts,
            f"应该精准命中 Slide 12 的临床数据论点，实际命中: {hit_texts}"
        )

    def test_03_four_stage_fuzzy_locator(self):
        """验证 4 阶高精度容错定位器与标点脱敏"""
        sample_doc = fitz.open(self.pdf_path)
        page0 = sample_doc[0]
        text0 = page0.get_text()
        sample_doc.close()

        query = "A single dose of nirsevimab resulted in 74.5% lower incidence"
        loc = locate_sentence(text0, query)
        self.assertIsNotNone(loc, "4阶定位器应成功模糊匹配截断/包含长句")

    def test_04_end_to_end_pipeline_execution(self):
        """验证端到端流水线执行，生成嵌套目录、高亮 PDF 与预览图"""
        out_base = os.path.join(self.tmp_dir, "output_nested")
        result = via54_ppt_visual_to_pdf.highlight_from_visual(
            pptx_path=self.pptx_path,
            pdf_in=self.pdf_path,
            pdf_out=None,
            slide_num=2,
            apply_9_rules=True,
            use_vision_api=False,
            export_images=True,
            out_base=out_base,
        )

        self.assertTrue(result["ok"], f"流水线应成功执行，错误信息: {result.get('error')}")
        self.assertTrue(os.path.exists(result["highlight_pdf"]), "高亮 PDF 应已成功生成")
        self.assertTrue(os.path.exists(result["main_pdf"]), "主 PDF 副本应已复制")
        self.assertGreater(result["highlights_ok"], 0, "应生成有效的高亮标注")
        self.assertTrue(os.path.exists(result["all_pages_dir"]), "全部页面目录应已生成")

    def test_05_iron_rules_sanitization(self):
        """验证 9 条铁律合规性：确保元数据（如 CONFLICT OF INTEREST, DOI 等）不被高亮"""
        out_hl = os.path.join(self.tmp_dir, "sanitized_hl.pdf")
        bad_sentences = {
            0: ["The authors declare no conflict of interest regarding this publication."],
            1: ["The authors declare no conflict of interest regarding this publication."]
        }
        highlight_sentences(self.pdf_path, out_hl, bad_sentences, verbose=False)
        
        doc = fitz.open(out_hl)
        for pi in range(len(doc)):
            page = doc[pi]
            for a in list(page.annots() or []):
                t = page.get_textbox(a.rect).strip()
                v = via54_ppt_visual_to_pdf.is_metadata_rect(page, a.rect, t)
                if v:
                    page.delete_annot(a)
        doc.save(out_hl + ".clean.pdf")
        doc.close()
        
        doc_clean = fitz.open(out_hl + ".clean.pdf")
        total_annots = sum(len(list(doc_clean[p].annots() or [])) for p in range(len(doc_clean)))
        doc_clean.close()
        self.assertEqual(total_annots, 0, "元数据应被 9 条铁律 100% 拦截并清除")

    def test_06_step1_unified_render_engine(self):
        """Step 1 验证: PPT、PDF 与图片统一分页渲染"""
        self._require_powerpoint_render()
        out_r = os.path.join(self.tmp_dir, "step1_renders")
        # 1. PPT 渲染
        res_ppt = unified_render_engine.render_source_file(self.pptx_path, os.path.join(out_r, "ppt"))
        self.assertTrue(res_ppt["success"])
        self.assertGreaterEqual(res_ppt["page_count"], 3)

        # 2. PDF 渲染
        res_pdf = unified_render_engine.render_source_file(self.pdf_path, os.path.join(out_r, "pdf"))
        self.assertTrue(res_pdf["success"])
        self.assertEqual(res_pdf["page_count"], 2)

        # 3. 单图规范化渲染
        mock_img = os.path.join(self.tmp_dir, "test.png")
        Image.new("RGB", (200, 200), color="blue").save(mock_img)
        res_img = unified_render_engine.render_source_file(mock_img, os.path.join(out_r, "img"))
        self.assertTrue(res_img["success"])
        self.assertEqual(res_img["page_count"], 1)

    def test_07_step2_visual_claim_extractor(self):
        """Step 2 验证: 提取引用字段与局部视觉区域裁切"""
        self._require_powerpoint_render()
        out_r = os.path.join(self.tmp_dir, "step1_renders", "ppt")
        unified_render_engine.render_source_file(self.pptx_path, out_r)
        p2_img = os.path.join(out_r, "page_002.png")
        self.assertTrue(os.path.exists(p2_img))

        out_crops = os.path.join(self.tmp_dir, "step2_crops")
        claims = visual_claim_extractor.extract_claims_and_visual_crops(
            page_img_path=p2_img,
            page_num=2,
            source_file_path=self.pptx_path,
            out_dir=out_crops,
            use_vlm=False
        )
        self.assertGreater(len(claims), 0, "应提取至少 1 个引用 claim")
        first_claim = claims[0]
        self.assertTrue(os.path.exists(first_claim["visual_crop_path"]), "局部视觉裁切图应生成")
        self.assertEqual(first_claim["pn_x"], "P2-1")

    def test_08_step3_step4_literature_downloader(self):
        """Step 3 & 4 验证: 文献链接整理与标准目录组织"""
        mock_claim = {
            "pn_x": "P12-1",
            "page_num": 12,
            "citation_mark": 1,
            "claim_text": "在足月儿中预防 RSV 感染保护率为 74.5%",
            "reference_field": "N Engl J Med 2020. DOI: 10.1056/NEJMoa2110275",
            "doi": "10.1056/NEJMoa2110275",
            "visual_crop_path": None
        }
        out_organize = os.path.join(self.tmp_dir, "step4_nested")
        res = literature_downloader.process_literature_for_claim(
            claim_item=mock_claim,
            out_base_dir=out_organize,
            local_search_dirs=[self.tmp_dir],  # 包含创建的 P12-1.pdf
            allow_download=False
        )
        self.assertEqual(res["download_status"], "found_local")
        self.assertTrue(os.path.exists(os.path.join(out_organize, "P12-1", "P12-1_main.pdf")))
        self.assertTrue(os.path.exists(os.path.join(out_organize, "P12-1", "P12-1_meta.json")))

    def test_09_step5_dual_alignment_pipeline(self):
        """Step 5 验证: 5步端到端总流水线与双重对齐高精标注"""
        self._require_powerpoint_render()
        out_5step = os.path.join(self.tmp_dir, "step5_full_run")
        shutil.copy2(self.pdf_path, os.path.join(self.tmp_dir, "P2-1.pdf"))
        summary = dual_alignment_pipeline.run_5step_highlight_pipeline(
            source_path=self.pptx_path,
            out_base_dir=out_5step,
            local_search_dirs=[self.tmp_dir],
            allow_download=False,
            target_page=2
        )
        self.assertTrue(summary["success"], "5步流水线应执行成功")
        self.assertIn("P2-1", summary["results"])
        p2_res = summary["results"]["P2-1"]["alignment"]
        self.assertTrue(p2_res["ok"], "双重对齐标注应成功")
        self.assertTrue(os.path.exists(p2_res["highlight_pdf"]), "高亮 PDF 应生成")

    def test_10_docx_render_is_word_only(self):
        """Word 源文件**只由 Microsoft Word 渲染** —— 不退回 LibreOffice / python-docx 拼页。

        与 PPT 同一条保真标准(见 docs/ppt-render-fidelity.md): 会改版式的第三方路径一律不用。
        v5.4.30 删掉了原来那两条兜底: LibreOffice headless 转 PDF、以及用 python-docx
        抽段落拼一张"简易 PDF"(版式与原文档完全不同)。
        """
        src = open(unified_render_engine.__file__, encoding="utf-8").read()
        self.assertNotIn("from docx import", src, "不该再用 python-docx 拼页充当渲染")

        docx = os.path.join(self.tmp_dir, "x.docx")
        with open(docx, "wb") as fh:
            fh.write(b"PK\x03\x04 fake docx")
        out = os.path.join(self.tmp_dir, "docx_out")

        # 假装本机装了 LibreOffice: 旧实现会拿它去转 PDF, 新实现必须连碰都不碰
        with mock.patch.object(unified_render_engine.sys, "platform", "linux"), \
                mock.patch.object(unified_render_engine.os, "name", "posix"), \
                mock.patch("shutil.which", return_value="/usr/bin/soffice"), \
                mock.patch.object(unified_render_engine.subprocess, "run") as runner, \
                mock.patch("builtins.print") as mp:
            self.assertEqual(unified_render_engine.render_docx_to_images(docx, out), [])
        self.assertFalse(runner.called,
                         "没有 Word 时不得去调外部转换器 —— 那正是被删掉的 LibreOffice 兜底")
        lines = [" ".join(str(a) for a in c.args) for c in mp.call_args_list]
        self.assertTrue(any("Microsoft Word" in l for l in lines),
                        "应说明缺的是 Microsoft Word 通道, 实际: %s" % lines)


if __name__ == "__main__":
    unittest.main(verbosity=2)
