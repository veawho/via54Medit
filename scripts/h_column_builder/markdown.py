#!/usr/bin/env python3
"""
h_column_builder.py — H 列 v5.0 内容生成器 (2026-08-02)

基于用户的修正指令:
1. 不需要本地路径, 只需要本地文件名
2. 主文件需要列出文献信息 (标题, 作者, 期刊, 年/卷/期/页, 出版, DOI)
3. 多引用结构 C 列已有类似内容, 不需要保留
4. 视觉关联数据扩展整合为: 视觉对齐/数据对齐/视觉语义推理

核心功能:
- parse_d_field(d): 解析 CSV D 列 → {authors, title, journal, year, vol, issue, pages, type}
- parse_c_field(c): 解析飞书 C 列 → {visual_alignment, data_alignment, semantic_reasoning}
- build_h_md(...): 生成 H 列 markdown 字符串
- markdown_to_rich_text_v3(...): markdown → 飞书 rich_text (保留换行 + 裸 URL)
"""

import re
from typing import Dict, List, Optional
from .scan import scan_pn_x_dir, calculate_main_score, calculate_fallback_score, run_light_step2
from .detect import detect_main_pdf_mismatch, detect_main_pdf_content_mismatch
from .links import (
    identify_publisher, get_publisher_pdf_urls,
    _infer_publisher_label, _infer_fallback_search_link,
    _infer_main_pdf_link, identify_link_eternality
)
from .parse import parse_d_field, parse_c_field


# ════════════════════════════════════════════════════════════════════
# 解析 CSV D 列 (作者/标题/期刊/年份/卷期页)
# ════════════════════════════════════════════════════════════════════


def markdown_to_rich_text(md: str) -> List[Dict]:
    """
    把 markdown 文本转换成飞书 rich_text 数组 (v3)
    
    特性:
    - 同时检测 [text](url) 和裸 https://... URL
    - 保留换行符 \n (飞书渲染时自动换行)
    - 相邻 text 段自动合并
    
    根因: 之前 H 列写入多段文本 (每行一段), 飞书内联渲染无换行。
    """
    rt: List[Dict] = []
    if not md:
        return rt
    
    # 找所有链接
    all_links = []
    # 找 [text](url) 链接, 用手写 parser 处理嵌套括号 (URL 含 (25) 等)
    i = 0
    while i < len(md):
        if md[i] == '[':
            j = i + 1
            depth = 0
            while j < len(md):
                if md[j] == '[':
                    depth += 1
                elif md[j] == ']':
                    if depth == 0:
                        break
                    depth -= 1
                j += 1
            if j >= len(md):
                i += 1
                continue
            text_part = md[i+1:j]
            k = j + 1
            if k < len(md) and md[k] == '(':
                m_end = k + 1
                depth = 1
                while m_end < len(md):
                    if md[m_end] == '(':
                        depth += 1
                    elif md[m_end] == ')':
                        depth -= 1
                        if depth == 0:
                            break
                    m_end += 1
                if m_end < len(md):
                    url_part = md[k+1:m_end]
                    all_links.append((i, m_end+1, text_part, url_part))
                    i = m_end + 1
                    continue
        i += 1
    for m in re.finditer(r"https?://[^\s`\n\)>]+", md):
        already = False
        for s, e, _, _ in all_links:
            if s <= m.start() and m.end() <= e:
                already = True
                break
        if not already:
            all_links.append((m.start(), m.end(), m.group(), m.group()))
    all_links.sort(key=lambda x: x[0])
    
    parts = []
    last = 0
    for s, e, text, url in all_links:
        if s > last:
            parts.append(("text", md[last:s]))
        parts.append(("link", text, url))
        last = e
    if last < len(md):
        parts.append(("text", md[last:]))
    
    if not parts:
        rt.append({"type": "text", "text": md})
        return rt
    
    # 合并相邻 text
    merged = []
    for p in parts:
        if p[0] == "text":
            if merged and merged[-1][0] == "text":
                merged[-1] = ("text", merged[-1][1] + p[1])
            else:
                merged.append(p)
        else:
            merged.append(p)
    
    for p in merged:
        if p[0] == "text":
            rt.append({"type": "text", "text": p[1]})
        else:
            rt.append({"type": "link", "text": p[1], "link": p[2]})
    
    return rt


# ════════════════════════════════════════════════════════════════════
# 一站式: 从 CSV D 列 + 飞书 C 列生成 H 列 rich_text
# ════════════════════════════════════════════════════════════════════



def build_h_md(
    pn: str,
    info_d: Dict[str, str],
    info_c: Dict[str, List[str]],
    g_path: str,
    doi: str,
    c_raw: Optional[str] = None,
    row_n: Optional[int] = None,
) -> str:
    """
    生成 H 列 markdown 内容 (v5.0)
    
    Args:
        pn: Pn-x 标号 (如 "2")
        row_n: 飞书 Row 编号 (1 是表头, Row N = P(N-1))
              None 时自动按 Pn 计算 (Row = 11 + (pn-1))
              但这仅适用于 slide 5. slide 3/4 需要外部传入
    """
    import os
    if row_n is None:
        # 默认: slide 5, Row 11 = P5-1
        pn_int = int(pn)
        row_n = pn_int + 10
    
    # 文件名 (从 g_path 提取)
    fname = os.path.basename(g_path) if g_path else f"P5-{pn}_main_*.pdf"
    
    # 类型 emoji
    if info_d["type"] == "conference_abstract":
        type_emoji = "📄 CONFERENCE ABSTRACT"
    elif pn == "1":
        type_emoji = "📋 GUIDELINE"
    else:
        type_emoji = "📄 LITERATURE"
    
    publisher = identify_publisher(info_d["journal"])
    
    # 标题
    title = info_d.get("title", "")
    if not title and info_c.get("visual_alignment"):
        for va in info_c["visual_alignment"]:
            if "引文:" in va:
                title = va.replace("引文:", "").strip()
                break
    
    md_parts = []
    md_parts.append(f"🎯 Row {row_n} (P5-{pn}) — {info_d['journal']} {info_d['year']} 文献应证\n")
    
    # 【📄 主文件】
    md_parts.append("【📄 主文件】 (D 列核心, 主文件 + 文献信息)")
    md_parts.append(f"  - 文件名: `{fname}`")

    if title and title != info_d["journal"]:
        md_parts.append(f"  - 标题: {title[:80]}")
    md_parts.append(f"  - 作者: {info_d['authors']}")
    md_parts.append(f"  - 期刊: {info_d['journal']}")
    vol_issue = f"v{info_d['volume']}" + (f"({info_d['issue']})" if info_d['issue'] else "")
    pages = info_d['pages']
    if vol_issue and pages:
        md_parts.append(f"  - 年/卷/期/页: {info_d['year']}, {vol_issue}: {pages}")
    elif vol_issue:
        md_parts.append(f"  - 年/卷: {info_d['year']}, {vol_issue}")
    else:
        md_parts.append(f"  - 年: {info_d['year']}")
    if publisher:
        md_parts.append(f"  - 出版: {publisher}")
    
    if doi and not doi.startswith("备注"):
        md_parts.append(f"  - DOI: [{doi}](https://doi.org/{doi})")
    elif info_d.get("abstract_id"):
        md_parts.append(f"  - 摘要号: {info_d['abstract_id']}")
    
    md_parts.append("")
    
    # 【⚠️ 应证评分警告】 (main < 0.7 且无 fb)
    if main_score is not None and main_score < 0.7 and not scan.get("fb") and not scan.get("fb_cross_refs"):
        manifest = scan.get("manifest", {})
        missing = manifest.get("missing_data_points", [])
        found = manifest.get("found_data_points", [])
        md_parts.append(f"【⚠️ 应证评分低】 (main={main_score:.2f}, step2 hits {manifest.get('step2_found', 0)}/{manifest.get('step2_total', 0)})")
        md_parts.append(f"  原因: PPT 数据点在 PDF 中匹配率低")
        if missing:
            md_parts.append(f"  未找到数据点: {', '.join(missing[:8])}{'...' if len(missing) > 8 else ''}")
        if found:
            md_parts.append(f"  已找到: {', '.join(found[:8])}{'...' if len(found) > 8 else ''}")
        md_parts.append(f"  说明: PPT 引用数据点在 PDF 中以变体形式出现 (如 '14.4' vs '14.4%'), docling 文本匹配未必完整. 但 main PDF 仍是应证真理. 参考 main PDF 内容核对 PPT 数据点.")

        # v9.6: Vision OCR fallback - 当 PDF 文字找不到数据点时, 用 sensenova_vision API 提取 highlight 图
        vision_data_points = manifest.get("vision_ocr_data_points", [])
        if vision_data_points:
            md_parts.append("")
            md_parts.append(f"  📸 Vision OCR 已提取 ({len(vision_data_points)} 个数据点, 来自 highlight 图):")
            for dp in vision_data_points[:5]:
                md_parts.append(f"    - {dp.get('value', 'N/A')} ({dp.get('description', '')[:40]})")
            if len(vision_data_points) > 5:
                md_parts.append(f"    - ... 等共 {len(vision_data_points)} 个")
            md_parts.append("")
        md_parts.append("")

    # 【🧠 语义等同性推理】 (数值精度等价 + 单位等价)
    manifest = scan.get("manifest", {})
    equiv_matches = manifest.get("equivalent_found_data_points", [])
    if equiv_matches:
        md_parts.append("【🧠 语义等同性推理】 (数值/单位等价)")
        md_parts.append("  算法: 14.4 ≈ 14.40 ≈ 14.400 (浮点等) ; 14.4 ≈ 14.4% (单位等价, 当 PDF 上下文说明数据是百分比)")
        # 显示前 10 个等价匹配
        for eq in equiv_matches[:10]:
            md_parts.append(f"  - '{eq['dp']}' 在 PDF 中以变体 '{eq['variant']}' 出现 → 应证等价")
        if len(equiv_matches) > 10:
            md_parts.append(f"  - ... 等共 {len(equiv_matches)} 个等价命中")
        md_parts.append("")

    # 【✅ main 完整应证】 (当 main_score >= 0.95)
    # 注意: main_score 可能来自 highlight_summary (slide 6+) 而非 step2 (slide 3-5)
    if main_score is not None and main_score >= 0.95:
        manifest = scan.get("manifest", {})
        found_pts = manifest.get("found_data_points", [])
        equiv_pts = manifest.get("equivalent_found_data_points", [])
        found_locs = manifest.get("found_data_point_locations", {})
        total = manifest.get("step2_total", len(found_pts))
        step2_score = manifest.get("step2_score")
        hl_summary = scan.get("highlight_summary", {})

        # 是否满分
        perfect = main_score >= 1.0
        md_parts.append("【✅ main 完整应证 PPT 内容】" + (" ⭐满分" if perfect else ""))

        # 区分 score 来源
        if step2_score is not None:
            # slide 3-5: 真实 step2 docling 应证
            md_parts.append(f"  PPT 标号指向的内容已在 main PDF 中找到 ({len(found_pts)}/{total} 数据点命中, 评分 {main_score:.2f})")
        elif hl_summary and hl_summary.get("terms"):
            # slide 6+: 简化 highlight 应证
            hits = hl_summary.get("hits", 0)
            terms = hl_summary.get("terms", 0)
            page = hl_summary.get("page", "?")
            md_parts.append(f"  PPT 标号指向的内容已在 main PDF highlight 区域找到 ({hits} hits / {terms} terms, page {page})")
            md_parts.append(f"  ⚠️ 此评分基于 highlight 图视觉匹配, 未做 docling 语义级 step2 应证 (待升级)")
        else:
            md_parts.append(f"  PPT 标号指向的内容已在 main PDF 中找到 (评分 {main_score:.2f})")

        # 推理链: PPT 标号 → 语义理解 → PDF 应证位置
        if info_c.get("positions"):
            pos = info_c["positions"][0]
            ppt_text = pos.get("text", "")
            if ppt_text:
                md_parts.append(f"  PPT 引文 (推理源): {ppt_text[:100]}")
            if pos.get("data"):
                md_parts.append(f"  PPT 语义 (推理目标): {pos['data'][:100]}")

        # PDF 应证位置 (核心数据点的具体位置)
        if found_locs:
            # 优先找核心数据点 (带 % 或 > 10 数字)
            core_dps = [dp for dp in found_locs if "%" in dp or dp.replace(".", "").isdigit() and float(dp.replace("%", "")) >= 10]
            core_dps = core_dps[:3] if core_dps else list(found_locs.keys())[:3]
            md_parts.append(f"  📍 main PDF 应证位置 (核心数据):")
            import re as _re_ctx1
            for dp in core_dps:
                locs = found_locs[dp]
                if locs:
                    loc = locs[0]
                    # v8.6: 移除 context 中的完整 URL (避免 markdown_to_rich_text 误识别)
                    ctx = _re_ctx1.sub(r'https?://\S+', '', loc["text_snippet"])[:60].strip()
                    if not ctx:
                        ctx = "(context 截断)"
                    md_parts.append(f"    ✓ '{dp}' → page {loc['page_no']}: {ctx}...")

        # 显示 PDF 命中数据点汇总
        if found_pts:
            md_parts.append(f"  PDF 命中数据点 (前 8 个):")
            for dp in found_pts[:8]:
                md_parts.append(f"    ✓ {dp}")
        if equiv_pts:
            md_parts.append(f"  PDF 等价命中 (前 5 个):")
            for eq in equiv_pts[:5]:
                md_parts.append(f"    ≈ {eq['dp']} (PDF 中以 {eq['variant']} 形式)")
        md_parts.append("")

    # 【🎯 应证推理】 — 完整 5 步推理链 (2026-08-02 用户硬规则 v7.3)
    md_parts.append("【🎯 应证推理】 (完整 5 步推理链: PPT视觉 → 信息要素 → PDF应证)")

    # ① PPT 标号指向位置 (视觉) — v8.5 严格从 C 列视觉描述提取, 不靠 D 列
    md_parts.append("  ① PPT 标号指向位置 (视觉):")
    
    # 整页引文 / 位置描述 / 引文位置 — 三种来源
    if info_c.get("positions"):
        for i, pos in enumerate(info_c["positions"][:3]):
            loc = pos.get("location", "PPT 右半区域")
            text = pos.get("text", "")[:60]
            md_parts.append(f"    - {loc}: {text}")
    elif info_c.get("visual_alignment"):
        for va in info_c["visual_alignment"][:2]:
            md_parts.append(f"    - {va[:80]}")
    elif info_c.get("引文位置"):
        # 整页引文 / 脚注引文
        md_parts.append(f"    - {info_c['引文位置'][:80]}")
    elif info_c.get("data_alignment"):
        # 整页引文 / 无独立位置标号
        for da in info_c["data_alignment"][:1]:
            md_parts.append(f"    - {da[:80]}")
    else:
        md_parts.append("    - (PPT slide 标号位置未识别)")

    # ② PPT 视觉内容 (完整信息要素) — v8.5 严格从 PPT slide 视觉识别 (不依赖 D 列)
    md_parts.append("  ② PPT 视觉内容 (完整信息要素, PPT slide 视觉识别):")
    
    # 优先从 manifest.ppt_data_points (这是 PPT 视觉识别后的真实数据点)
    manifest = scan.get("manifest", {})
    ppt_pts = manifest.get("ppt_data_points", [])
    
    if ppt_pts:
        for dp in ppt_pts[:8]:
            md_parts.append(f"    - 视觉识别数据点: '{dp}'")
    elif info_c.get("data_alignment"):
        for da in info_c["data_alignment"][:3]:
            md_parts.append(f"    - {da[:100]}")
    else:
        md_parts.append("    - (PPT slide 视觉识别未提取到数据点, 待 docling 视觉识别)")

    # ③ 推理: 在 main PDF 中找 PPT 视觉识别的数据点 (v8.5 严格对齐 PPT视觉 vs PDF高亮)
    md_parts.append("  ③ 推理 (信息要素匹配): 需在 main PDF 中找到:")
    
    manifest = scan.get("manifest", {})
    ppt_pts = manifest.get("ppt_data_points", [])
    found_pts = manifest.get("found_data_points", [])
    
    # 列出所有 ppt_pts 作为推理目标
    if ppt_pts:
        for dp in ppt_pts[:8]:
            md_parts.append(f"    - 数据: '{dp}'")
    else:
        # 没 manifest.ppt_data_points 时, 从 C 列 data_alignment 提取
        import re as _re5b
        if info_c.get("data_alignment"):
            for da in info_c["data_alignment"][:5]:
                for num_m in _re5b.finditer(r"\b(\d+(?:\.\d+)?)\s*%?", da):
                    v = num_m.group(1)
                    if "%" in da or len(v) >= 2:
                        if v not in ppt_pts:
                            md_parts.append(f"    - 数据: '{v}'")
                            ppt_pts.append(v)
    
    if info_c.get("引文"):
        md_parts.append(f"    - 文字: {info_c['引文'][:80]}")

    # ④ main PDF 应证位置 — v8.5 严格从 manifest.found_data_point_locations 读取真实应证位置
    md_parts.append("  ④ main PDF 应证位置 (语义推理匹配, PPT视觉 vs PDF高亮双向对齐):")
    
    manifest = scan.get("manifest", {})
    found_locs = manifest.get("found_data_point_locations", {})
    
    if found_locs and isinstance(found_locs, dict):
        # 已 docling/PyMuPDF 真实应证: 显示每个数据点的 page_no + context
        def sort_key(item):
            dp = item[0]
            locs = item[1]
            ctx = locs[0]["text_snippet"] if locs else ""
            if any(kw in ctx.lower() for kw in ["months", "month", "pfs", "os ", "hazard", "survival"]):
                return 0
            if "%" in dp:
                return 1
            try:
                v = float(dp.replace("%", ""))
                if v >= 10:
                    return 2
                else:
                    return 3
            except ValueError:
                return 4
        
        sorted_locs = sorted(found_locs.items(), key=sort_key)
        for dp, locs in sorted_locs[:5]:
            if locs:
                loc = locs[0]
                # v8.6: 移除 context 中的完整 URL (避免 markdown_to_rich_text 误识别, 飞书显示 https://d...)
                import re as _re_ctx
                ctx = _re_ctx.sub(r'https?://\S+', '', loc["text_snippet"])[:60]
                ctx = ctx.strip()
                if not ctx:
                    ctx = "(context 截断)"
                md_parts.append(f"    ✓ '{dp}' → page {loc['page_no']}: {ctx}...")
        if len(found_locs) > 5:
            md_parts.append(f"    ... 等共 {len(found_locs)} 个数据点已应证")
        
        # 标记 docling/PyMuPDF 来源
        if manifest.get("algorithm_version") == "v8.5_light_step2":
            md_parts.append("    (v8.5 PyMuPDF 轻量级搜索, 未做 docling 表格结构识别)")
        elif manifest.get("algorithm_version") == "v4.0":
            md_parts.append("    (docling 表格 + 文本 深度应证)")
    elif scan.get("main_pdf"):
        # 没 found_locs (没 docling/PyMuPDF): 跑临时 PyMuPDF 搜索 (light step2)
        main_pdf_path = f"{lit_base}/{pn_x}/{scan['main_pdf']}"
        if not _os.path.isfile(main_pdf_path):
            main_pdf_path = f"{scan.get('src_base', '/Users/david/Desktop/雷管方案_文献整理')}/{pn_x}/{scan['main_pdf']}"
        
        light_hits = []
        if _os.path.isfile(main_pdf_path):
            try:
                import fitz as _fitz
                doc = _fitz.open(main_pdf_path)
                search_terms = manifest.get("ppt_data_points", [])
                if not search_terms and info_c.get("data_alignment"):
                    import re as _re_lite
                    for da in info_c["data_alignment"][:5]:
                        for num_m in _re_lite.finditer(r"\b(\d+(?:\.\d+)?)\s*%?", da):
                            v = num_m.group(1)
                            if len(v) >= 2 and v not in search_terms:
                                search_terms.append(v)
                
                for term in search_terms[:5]:
                    for p_idx, page in enumerate(doc):
                        if p_idx >= 5:
                            break
                        text = page.get_text()[:3000]
                        if term in text:
                            idx = text.find(term)
                            ctx = text[max(0, idx-30):idx+60].replace("\n", " ")
                            light_hits.append((term, p_idx+1, ctx))
                            break
                doc.close()
            except Exception:
                pass
        
        if light_hits:
            for dp, page, ctx in light_hits[:4]:
                md_parts.append(f"    ✓ '{dp}' → page {page}: {ctx}...")
            md_parts.append("    (轻量级 PyMuPDF 搜索, 未做 docling 语义级应证, 待升级)")
        else:
            md_parts.append("    (未做 PPT视觉 vs PDF高亮 应证, 待 docling 解析)")

    # ⑤ 推理结果 — v8.5 严格基于 PPT视觉 vs PDF高亮双向对齐的 step2_score
    md_parts.append("  ⑤ 推理结果:")
    
    if main_score is None:
        md_parts.append("    ⚠️ 未做 PPT视觉 vs PDF高亮 双向对齐, 待运行 docling / 轻量级搜索应证")
        if scan.get("main_pdf"):
            md_parts.append(f"    📁 main PDF 文件: {scan['main_pdf']} ({scan.get('main_pdf_size_kb', 0)}KB)")
            md_parts.append(f"    💡 文件存在, 待 PPT视觉识别 + PDF docling/PyMuPDF 应证")
    elif main_score >= 1.0:
        md_parts.append("    ✅ main 完整应证 PPT 视觉识别的全部信息要素 (⭐满分, 双向对齐)")
    elif main_score >= 0.85:
        md_parts.append("    ✅ main 高度应证 PPT 视觉识别的多数信息要素")
    elif main_score >= 0.7:
        md_parts.append("    ⚠️ main 部分应证 PPT 视觉识别的信息要素")
    elif main_score >= 0.4:
        md_parts.append("    ⚠️ main 应证不足, 需 fallback 补强")
    else:
        md_parts.append("    ❌ main 应证失败, fallback 是必需")

    # 保留 visual_alignment / semantic_reasoning 作为补充
    if info_c.get("semantic_reasoning"):
        md_parts.append("")
        md_parts.append("  [补充参考] 视觉/语义推理原始记录:")
        for sr in info_c["semantic_reasoning"][:2]:
            md_parts.append(f"    - {sr[:100]}")

    md_parts.append("")
    
    # 【📎 下载链接】
    if doi and not doi.startswith("备注"):
        md_parts.append("【📎 下载链接】 (互联网, 可点击)")
        md_parts.append(f"  - PubMed 搜索: [{doi}](https://pubmed.ncbi.nlm.nih.gov/?term={doi})")
        md_parts.append(f"  - Europe PMC 搜索: [{doi}](https://europepmc.org/search?query={doi})")
        md_parts.append("")
    elif doi.startswith("备注") or pn == "1":  # 政府文件/无 DOI
        md_parts.append("【📎 原始链接】 (政府文件, 官方存档)")
        md_parts.append(f"  - NHC 官网: [国家卫生健康委员会](http://www.nhc.gov.cn)")
        md_parts.append(f"  - 中国实用外科杂志: [zsjwkzz.cn](https://www.zgsjwkzz.cn)")
        md_parts.append("")
    
    md_parts.append(f"【🏷️ 类型】 {type_emoji}")
    
    return "\n".join(md_parts)




def build_h_md_v6(
    pn_x: str,
    info_d: Dict,
    info_c: Dict,
    doi: str,
    scan: Optional[Dict] = None,
    c_raw: Optional[str] = None,
    row_n: Optional[int] = None,
    lit_base: str = "/Users/david/Desktop/雷管方案_文献整理/_literature_citation_index",
    d: Optional[str] = None,
) -> str:
    """
    v6.0: 与 Pn-x 目录一致的文件清单 + 应证评分 + 时效性标注

    新增:
    - 文件清单 (main + fallback + supp) 严格对应 _literature_citation_index/Pn-x/
    - 每个 PDF 都评分 (main 应证 PPT 内容的命中率)
    - 时效性标注 (DOI/IARC/NHC/会议)
    - 失效后备 (Wayback / 备用 URL)
    """
    import os as _os
    if scan is None:
        scan = scan_pn_x_dir(pn_x)
    
    if row_n is None:
        row_n = int(pn_x.split("-")[1]) + 10
    
    publisher = identify_publisher(info_d["journal"])
    
    title = info_d.get("title", "")
    if not title and info_c.get("visual_alignment"):
        for va in info_c["visual_alignment"]:
            if "引文:" in va:
                title = va.replace("引文:", "").strip()
                break
    
    # 类型 emoji
    if info_d["type"] == "conference_abstract":
        type_emoji = "📄 CONFERENCE ABSTRACT"
    elif pn_x == "P3-1":
        type_emoji = "📊 DATABASE (GLOBOCAN)"
    elif pn_x == "P3-2" or pn_x == "P5-1":
        type_emoji = "📋 GUIDELINE (政府文件)"
    else:
        type_emoji = "📄 LITERATURE"
    
    md_parts = []
    md_parts.append(f"🎯 Row {row_n} ({pn_x}) — {info_d['journal']} {info_d['year']} 文献应证\n")
    
    # 【📄 主文件】
    md_parts.append("【📄 主文件】 (D 列核心 + 文献信息)")

    main_score = calculate_main_score(scan)

    # v9.5: 检测 main PDF 错位
    # 用 D 列作为关键词源 (d 列是文献元数据, c 列是 PPT 上下文, 应该用 d 匹配文献)
    mismatch = detect_main_pdf_mismatch(pn_x, info_d, scan, d_raw=d)
    if not mismatch:
        # v9.5: 检测 main PDF 内容错位 (基于 page 1 文本)
        mismatch = detect_main_pdf_content_mismatch(pn_x, info_d, scan, d_raw=d)
    if mismatch:
        md_parts.append(f"  ⚠️ **main PDF 错位**: {mismatch['note']}")
        md_parts.append(f"    - D 列期望: {mismatch['expected']}")
        md_parts.append(f"    - 当前 main: `{mismatch['actual']}`")
        md_parts.append(f"    - 建议: 重新匹配 main PDF (当前 PDF 与 D 列文献不匹配)")

    if scan["main"]:
        for i, m in enumerate(scan["main"]):
            size_kb = scan["sizes"][m] // 1024
            md_parts.append(f"  - 文件名: `{m}` ({size_kb}KB)")
            if i == 0:  # 第一个 main, 显示文献信息
                if title and title != info_d["journal"]:
                    md_parts.append(f"    标题: {title[:80]}")
                md_parts.append(f"    作者: {info_d['authors']}")
                md_parts.append(f"    期刊: {info_d['journal']}")
                vol_issue = f"v{info_d['volume']}" + (f"({info_d['issue']})" if info_d['issue'] else "")
                pages = info_d['pages']
                if vol_issue and pages:
                    md_parts.append(f"    年/卷/期/页: {info_d['year']}, {vol_issue}: {pages}")
                elif vol_issue:
                    md_parts.append(f"    年/卷: {info_d['year']}, {vol_issue}")
                else:
                    md_parts.append(f"    年: {info_d['year']}")
                if publisher:
                    md_parts.append(f"    出版: {publisher}")
                if doi and not doi.startswith("备注"):
                    # DOI 行不显示链接 (避免与下方"下载链接"重复)
                    md_parts.append(f"    DOI: {doi}")
                elif info_d.get("abstract_id"):
                    md_parts.append(f"    摘要号: {info_d['abstract_id']}")
                # 应证评分 (从 manifest 的 step2_score 拿 found/total, 含等价推理)
                manifest = scan.get("manifest", {})
                found = manifest.get("step2_found", 0)
                total = manifest.get("step2_total", 0)
                equiv_count = manifest.get("equivalent_matches_count", 0)
                hl_summary = scan.get("highlight_summary", {})
                if total > 0:
                    # slide 3-5: 真实 step2 docling 应证
                    equiv_str = f", 含 {equiv_count} 个等价推理" if equiv_count > 0 else ""
                    perfect_mark = " ⭐满分" if main_score >= 1.0 else ""
                    md_parts.append(f"    应证评分: {main_score:.2f}{perfect_mark} (step2 hits {found}/{total}{equiv_str})")
                elif hl_summary and hl_summary.get("terms"):
                    # slide 6+: highlight 应证 (简化)
                    hits = hl_summary.get("hits", 0)
                    terms = hl_summary.get("terms", 0)
                    perfect_mark = " ⭐满分" if main_score >= 1.0 else ""
                    md_parts.append(f"    应证评分: {main_score:.2f}{perfect_mark} (highlight 应证: hits {hits} / terms {terms}, 未做 docling 语义级 step2)")
                elif main_score is None:
                    # slide 6+: 既没 highlight 也没 step2, main PDF 存在但未做 PPT视觉 vs PDF高亮 双向对齐
                    md_parts.append(f"    应证评分: ⏳ 待 PPT视觉 vs PDF高亮 双向对齐 (未运行 docling 表格结构识别 + 视觉匹配)")
                else:
                    md_parts.append(f"    应证评分: {main_score:.2f} (highlight hits {hl_summary.get('hits', 0)} / terms {hl_summary.get('terms', 1)})")
            elif i == 1:
                # 第二个 main (P5-13)
                md_parts.append(f"    注: 同一作者另一发表")
    else:
        md_parts.append("  - (无 main PDF)")
    
    md_parts.append("")
    
    # 【🔄 Fallback 补充材料】 (3 触发条件)
    #   1. main_score < 0.7 (低分, 即使 fb_cross_refs 不空也算)
    #   2. 有跨标号引用 (P4-3 fb 引 P4-1/P4-2 main, 即使 main 够也展示引用关系)
    #   3. main_score >= 1.0 满分 OR main_score=None (未做 docling) → 不显示 fb (v8.2)
    # 注: 旧条件 scan["fallback_triggered"] 是基于高亮图数量, 不准. 用 main_score 为准.
    # 满分或未验证 = 都不显示 fb (用户期望: 已验证满分 → 无需 fb; 未验证 → 不要拿未验证 fb 误导)
    hide_fb = (main_score is None) or (main_score >= 1.0)

    needs_fallback = (
        (not hide_fb and main_score < 0.7 and scan.get("fb")) or
        (not hide_fb and bool(scan.get("fb_cross_refs")))
    )

    show_supplementary = (
        not hide_fb and scan.get("fb") and not needs_fallback
    )

    if needs_fallback:
        # 区分三种 fallback 触发
        if main_score < 0.7:
            md_parts.append(f"【⚠️ Fallback 补充材料】 (main 应证评分 {main_score:.2f} < 0.7, 启用 fallback 补强)")
            md_parts.append(f"  原因: {scan['fallback_reason'][:120] if scan['fallback_reason'] else 'main 内容与 PPT 数据点不匹配'}")
        elif scan.get("fb_cross_refs"):
            md_parts.append("【🔄 Fallback 补充材料】 (跨标号引用, main 已足够应证)")
        else:
            md_parts.append("【🔄 Fallback 补充材料】")

        # v9.6: 跨 slide 共享引用段
        manifest = scan.get("manifest", {})
        if manifest.get("is_shared_reference") and manifest.get("shared_from"):
            shared_from = manifest["shared_from"]
            md_parts.append(f"【🔗 跨 slide 共享引用】 (PPT 标号在主目录无独立 PDF, 引用来自 {shared_from})")
            md_parts.append(f"  原因: PPT 标号内容已存在于 {shared_from} main PDF, 本目录共享引用")
            md_parts.append(f"  示例: P12-5 (Slide 12 标号 5) = P12-3 main PDF (Chan J Hepatol 2025 HIMALAYA Asian Subgroup - HBV 76.8%)")
            md_parts.append("")

        # v9.6: Vision OCR 段 (在 fallback 之前显示, 因为 vision 提取了 PDF 文字层没有的数据)
        vision_data_points = manifest.get("vision_ocr_data_points", [])
        if vision_data_points:
            md_parts.append(f"【📸 Vision OCR】 (sensenova-6.7-flash-lite 提取 highlight 图, {len(vision_data_points)} 个数据点)")
            for dp in vision_data_points[:8]:
                src_img = dp.get('source_image', '')
                md_parts.append(f"  - {dp.get('value', 'N/A')} ({dp.get('description', '')[:50]}) [{src_img}]")
            if len(vision_data_points) > 8:
                md_parts.append(f"  - ... 等共 {len(vision_data_points)} 个 (来源: {len(set(dp.get('source_image', '') for dp in vision_data_points))} 张 highlight 图)")
            md_parts.append("")

        # 本目录 fb (v8.7: 显示本地路径 + 文件名推断的期刊搜索链接)
        for fb in scan.get("fb_local", []):
            size_kb = scan["sizes"][fb] // 1024
            fb_score = calculate_fallback_score(scan, fb)
            fb_info_meta = scan.get("fb_info", {}).get(fb, {})
            应证_text = fb_info_meta.get("应证", "补充材料")
            fb_path = f"{lit_base}/{pn_x}/{fb}"
            md_parts.append(f"  - 文件名: `{fb}` ({size_kb}KB)")
            md_parts.append(f"    本地路径: {fb_path}")
            md_parts.append(f"    应证内容: {应证_text}")
            md_parts.append(f"    应证评分: {fb_score:.2f}")
            # v8.7: 从文件名推断期刊/会议, 显示搜索链接
            fb_search = _infer_fallback_search_link(fb)
            if fb_search:
                md_parts.append(f"    来源搜索: [{fb_search[1]}]({fb_search[0]})")

        # 跨标号引用
        for cross in scan.get("fb_cross_refs", []):
            if cross["target_file"] in scan.get("fb_local", []):
                continue  # 已在本目录显示过
            exists_mark = "✅" if cross.get("exists_in_lit") or cross.get("exists_in_src") else "❌"
            target_path = f"{lit_base}/{cross['target_pn_x']}/{cross['target_file']}"
            md_parts.append(f"  - 文件名: `{cross['target_file']}` (来自 {cross['target_pn_x']}, {exists_mark})")
            md_parts.append(f"    本地路径: {target_path}")
            md_parts.append(f"    应证内容: {cross['应证']}")
            md_parts.append(f"    应证评分: {cross['score']:.2f} (借用目标 Pn-x 的 step2_score)")
            # v8.7: 显示被引用 Pn-x 的链接
            target_pn_csv = cross['target_pn_x']
            target_doi = cross.get('target_doi', '')
            if target_doi:
                md_parts.append(f"    引用链接: [DOI 主链接](https://doi.org/{target_doi})")

        md_parts.append("")
    elif show_supplementary:
        # main 足够 (但非满分) 且有 fb (P5-8, P5-18)
        md_parts.append("【🔄 附加材料】 (main 已足够, 以下为补充)")
        for fb in scan["fb"]:
            size_kb = scan["sizes"][fb] // 1024
            fb_score = calculate_fallback_score(scan, fb)
            fb_path = f"{lit_base}/{pn_x}/{fb}"
            md_parts.append(f"  - 文件名: `{fb}` ({size_kb}KB)")
            md_parts.append(f"    本地路径: {fb_path}")
            md_parts.append(f"    用途: {'补充披露' if 'icmje' in fb.lower() else '同期发表' if 'nejm' in fb.lower() else '附录' if 'appendix' in fb.lower() else '补充材料'}")
            md_parts.append(f"    应证评分: {fb_score:.2f}")
            fb_search = _infer_fallback_search_link(fb)
            if fb_search:
                md_parts.append(f"    来源搜索: [{fb_search[1]}]({fb_search[0]})")
        md_parts.append("")
    
    # 【📚 补充材料 (supp)】
    if scan["supp"]:
        md_parts.append("【📚 补充材料】 (s1/s2 supplementary)")
        for s in scan["supp"]:
            size_kb = scan["sizes"][s] // 1024
            md_parts.append(f"  - `{s}` ({size_kb}KB)")
        md_parts.append("")
    
    # 【⚠️ 应证评分警告】 (main < 0.7 且无 fb)
    if main_score is not None and main_score < 0.7 and not scan.get("fb") and not scan.get("fb_cross_refs"):
        manifest = scan.get("manifest", {})
        missing = manifest.get("missing_data_points", [])
        found = manifest.get("found_data_points", [])
        md_parts.append(f"【⚠️ 应证评分低】 (main={main_score:.2f}, step2 hits {manifest.get('step2_found', 0)}/{manifest.get('step2_total', 0)})")
        md_parts.append(f"  原因: PPT 数据点在 PDF 中匹配率低")
        if missing:
            md_parts.append(f"  未找到数据点: {', '.join(missing[:8])}{'...' if len(missing) > 8 else ''}")
        if found:
            md_parts.append(f"  已找到: {', '.join(found[:8])}{'...' if len(found) > 8 else ''}")
        md_parts.append(f"  说明: PPT 引用数据点在 PDF 中以变体形式出现 (如 '14.4' vs '14.4%'), docling 文本匹配未必完整. 但 main PDF 仍是应证真理. 参考 main PDF 内容核对 PPT 数据点.")

        # v9.6: Vision OCR fallback - 当 PDF 文字找不到数据点时, 用 sensenova_vision API 提取 highlight 图
        vision_data_points = manifest.get("vision_ocr_data_points", [])
        if vision_data_points:
            md_parts.append("")
            md_parts.append(f"  📸 Vision OCR 已提取 ({len(vision_data_points)} 个数据点, 来自 highlight 图):")
            for dp in vision_data_points[:5]:
                md_parts.append(f"    - {dp.get('value', 'N/A')} ({dp.get('description', '')[:40]})")
            if len(vision_data_points) > 5:
                md_parts.append(f"    - ... 等共 {len(vision_data_points)} 个")
            md_parts.append("")
        md_parts.append("")

    # 【🧠 语义等同性推理】 (数值精度等价 + 单位等价)
    manifest = scan.get("manifest", {})
    equiv_matches = manifest.get("equivalent_found_data_points", [])
    if equiv_matches:
        md_parts.append("【🧠 语义等同性推理】 (数值/单位等价)")
        md_parts.append("  算法: 14.4 ≈ 14.40 ≈ 14.400 (浮点等) ; 14.4 ≈ 14.4% (单位等价, 当 PDF 上下文说明数据是百分比)")
        # 显示前 10 个等价匹配
        for eq in equiv_matches[:10]:
            md_parts.append(f"  - '{eq['dp']}' 在 PDF 中以变体 '{eq['variant']}' 出现 → 应证等价")
        if len(equiv_matches) > 10:
            md_parts.append(f"  - ... 等共 {len(equiv_matches)} 个等价命中")
        md_parts.append("")

    # 【✅ main 完整应证】 (当 main_score >= 0.95)
    # 注意: main_score 可能来自 highlight_summary (slide 6+) 而非 step2 (slide 3-5)
    if main_score is not None and main_score >= 0.95:
        manifest = scan.get("manifest", {})
        found_pts = manifest.get("found_data_points", [])
        equiv_pts = manifest.get("equivalent_found_data_points", [])
        found_locs = manifest.get("found_data_point_locations", {})
        total = manifest.get("step2_total", len(found_pts))
        step2_score = manifest.get("step2_score")
        hl_summary = scan.get("highlight_summary", {})

        # 是否满分
        perfect = main_score >= 1.0
        md_parts.append("【✅ main 完整应证 PPT 内容】" + (" ⭐满分" if perfect else ""))

        # 区分 score 来源
        if step2_score is not None:
            # slide 3-5: 真实 step2 docling 应证
            md_parts.append(f"  PPT 标号指向的内容已在 main PDF 中找到 ({len(found_pts)}/{total} 数据点命中, 评分 {main_score:.2f})")
        elif hl_summary and hl_summary.get("terms"):
            # slide 6+: 简化 highlight 应证
            hits = hl_summary.get("hits", 0)
            terms = hl_summary.get("terms", 0)
            page = hl_summary.get("page", "?")
            md_parts.append(f"  PPT 标号指向的内容已在 main PDF highlight 区域找到 ({hits} hits / {terms} terms, page {page})")
            md_parts.append(f"  ⚠️ 此评分基于 highlight 图视觉匹配, 未做 docling 语义级 step2 应证 (待升级)")
        else:
            md_parts.append(f"  PPT 标号指向的内容已在 main PDF 中找到 (评分 {main_score:.2f})")

        # 推理链: PPT 标号 → 语义理解 → PDF 应证位置
        if info_c.get("positions"):
            pos = info_c["positions"][0]
            ppt_text = pos.get("text", "")
            if ppt_text:
                md_parts.append(f"  PPT 引文 (推理源): {ppt_text[:100]}")
            if pos.get("data"):
                md_parts.append(f"  PPT 语义 (推理目标): {pos['data'][:100]}")

        # PDF 应证位置 (核心数据点的具体位置)
        if found_locs:
            # 优先找核心数据点 (带 % 或 > 10 数字)
            core_dps = [dp for dp in found_locs if "%" in dp or dp.replace(".", "").isdigit() and float(dp.replace("%", "")) >= 10]
            core_dps = core_dps[:3] if core_dps else list(found_locs.keys())[:3]
            md_parts.append(f"  📍 main PDF 应证位置 (核心数据):")
            import re as _re_ctx1
            for dp in core_dps:
                locs = found_locs[dp]
                if locs:
                    loc = locs[0]
                    # v8.6: 移除 context 中的完整 URL (避免 markdown_to_rich_text 误识别)
                    ctx = _re_ctx1.sub(r'https?://\S+', '', loc["text_snippet"])[:60].strip()
                    if not ctx:
                        ctx = "(context 截断)"
                    md_parts.append(f"    ✓ '{dp}' → page {loc['page_no']}: {ctx}...")

        # 显示 PDF 命中数据点汇总
        if found_pts:
            md_parts.append(f"  PDF 命中数据点 (前 8 个):")
            for dp in found_pts[:8]:
                md_parts.append(f"    ✓ {dp}")
        if equiv_pts:
            md_parts.append(f"  PDF 等价命中 (前 5 个):")
            for eq in equiv_pts[:5]:
                md_parts.append(f"    ≈ {eq['dp']} (PDF 中以 {eq['variant']} 形式)")
        md_parts.append("")

    # 【🎯 应证推理】 — 完整 5 步推理链 (2026-08-02 用户硬规则 v7.3)
    md_parts.append("【🎯 应证推理】 (完整 5 步推理链: PPT视觉 → 信息要素 → PDF应证)")

    # ① PPT 标号指向位置 (视觉) — v8.5 严格从 C 列视觉描述提取, 不靠 D 列
    md_parts.append("  ① PPT 标号指向位置 (视觉):")
    
    # 整页引文 / 位置描述 / 引文位置 — 三种来源
    if info_c.get("positions"):
        for i, pos in enumerate(info_c["positions"][:3]):
            loc = pos.get("location", "PPT 右半区域")
            text = pos.get("text", "")[:60]
            md_parts.append(f"    - {loc}: {text}")
    elif info_c.get("visual_alignment"):
        for va in info_c["visual_alignment"][:2]:
            md_parts.append(f"    - {va[:80]}")
    elif info_c.get("引文位置"):
        # 整页引文 / 脚注引文
        md_parts.append(f"    - {info_c['引文位置'][:80]}")
    elif info_c.get("data_alignment"):
        # 整页引文 / 无独立位置标号
        for da in info_c["data_alignment"][:1]:
            md_parts.append(f"    - {da[:80]}")
    else:
        md_parts.append("    - (PPT slide 标号位置未识别)")

    # ② PPT 视觉内容 (完整信息要素) — v8.5 严格从 PPT slide 视觉识别 (不依赖 D 列)
    md_parts.append("  ② PPT 视觉内容 (完整信息要素, PPT slide 视觉识别):")
    
    # 优先从 manifest.ppt_data_points (这是 PPT 视觉识别后的真实数据点)
    manifest = scan.get("manifest", {})
    ppt_pts = manifest.get("ppt_data_points", [])
    
    if ppt_pts:
        for dp in ppt_pts[:8]:
            md_parts.append(f"    - 视觉识别数据点: '{dp}'")
    elif info_c.get("data_alignment"):
        for da in info_c["data_alignment"][:3]:
            md_parts.append(f"    - {da[:100]}")
    else:
        md_parts.append("    - (PPT slide 视觉识别未提取到数据点, 待 docling 视觉识别)")

    # ③ 推理: 需要在 main PDF 中找到 视觉/数据/语义一致的内容
    md_parts.append("  ③ 推理 (信息要素匹配): 需在 main PDF 中找到:")
    manifest = scan.get("manifest", {})
    found_pts = manifest.get("found_data_points", [])
    found_locs = manifest.get("found_data_point_locations", {})
    
    # v8.4: 即使没 docling, 也从 C 列提取数据点 + 从 D 列提取关键术语作为推理目标
    import re as _re
    
    inference_targets = []  # [(category, value), ...]
    
    # 从 C 列 data_alignment 提取数字 + 术语
    if info_c.get("data_alignment"):
        for da in info_c["data_alignment"][:5]:
            for num_m in _re.finditer(r"\b(\d+(?:\.\d+)?)\s*%?", da):
                v = num_m.group(1)
                if "%" in da or len(v) >= 2:  # 跳过单数字
                    inference_targets.append(("数据", v))
            for kw in ["STRIDE", "T+A", "O+Y", "Len", "Pembro", "NIVO", "IPI", "Durvalumab", "Tremelimumab", "Atezolizumab", "Bevacizumab", "Sorafenib"]:
                if kw in da:
                    inference_targets.append(("术语", kw))
    
    # 从 D 列提取关键信息
    if info_d.get("title"):
        inference_targets.append(("文字", info_d["title"][:60]))
    if info_d.get("authors"):
        inference_targets.append(("作者", info_d["authors"][:60]))
    
    # 去重 + 限制显示
    seen = set()
    unique_targets = []
    for cat, v in inference_targets:
        if v not in seen:
            seen.add(v)
            unique_targets.append((cat, v))
    
    # 显示 found_pts (来自 manifest)
    if found_pts:
        core_pts = [dp for dp in found_pts if "%" in dp or (dp.replace(".", "").replace("-", "").isdigit() and float(dp.replace("%", "")) > 1)][:3]
        if not core_pts:
            core_pts = found_pts[:3]
        for dp in core_pts:
            md_parts.append(f"    - 数据: '{dp}'")
    else:
        # 没 docling: 显示 C/D 列推理目标
        for cat, v in unique_targets[:6]:
            md_parts.append(f"    - {cat}: '{v}'")
    
    if info_c.get("引文"):
        md_parts.append(f"    - 文字: {info_c['引文'][:80]}")

    # ④ main PDF 应证位置 (语义推理匹配, 按 PPT 语义相关性排序)
    md_parts.append("  ④ main PDF 应证位置 (语义推理匹配):")
    
    if found_locs:
        # 已 docling: 显示真实应证位置
        def sort_key(item):
            dp = item[0]
            ctx = item[1][0]["text_snippet"] if item[1] else ""
            if any(kw in ctx.lower() for kw in ["months", "month", "pfs", "os ", "hazard", "survival"]):
                return 0
            if "%" in dp:
                return 1
            try:
                v = float(dp.replace("%", ""))
                if v >= 10:
                    return 2
                else:
                    return 3
            except ValueError:
                return 4

        sorted_locs = sorted(found_locs.items(), key=sort_key)
        for dp, locs in sorted_locs[:5]:
            if locs:
                loc = locs[0]
                # v8.6: 移除 context 中的完整 URL (避免 markdown_to_rich_text 误识别, 飞书显示 https://d...)
                import re as _re_ctx
                ctx = _re_ctx.sub(r'https?://\S+', '', loc["text_snippet"])[:60]
                ctx = ctx.strip()
                if not ctx:
                    ctx = "(context 截断)"
                md_parts.append(f"    ✓ '{dp}' → page {loc['page_no']}: {ctx}...")
        if len(found_locs) > 5:
            md_parts.append(f"    ... 等共 {len(found_locs)} 个数据点已应证")
    elif scan.get("main_pdf"):
        # v8.4: 没 docling 时, 跑轻量级 PyMuPDF text 搜索关键数据点
        # scan.main_pdf 是文件名 (无 Pn-x/ 前缀), 路径需要 lit_base + pn_x + filename
        main_pdf_path = f"{lit_base}/{pn_x}/{scan['main_pdf']}"
        if not _os.path.isfile(main_pdf_path):
            main_pdf_path = f"{scan.get('src_base', '/Users/david/Desktop/雷管方案_文献整理')}/{pn_x}/{scan['main_pdf']}"
        if not _os.path.isfile(main_pdf_path):
            # 最后尝试: scan.main_pdf 可能含 Pn-x/ 前缀 (来自 manifest)
            main_pdf_path = f"{lit_base}/{scan['main_pdf']}"
        
        light_hits = []  # [(dp, page, ctx), ...]
        if _os.path.isfile(main_pdf_path):
            try:
                import fitz as _fitz
                doc = _fitz.open(main_pdf_path)
                # 从 C 列 + D 列提取搜索目标
                search_terms = []
                if info_c.get("data_alignment"):
                    import re as _re_lite
                    for da in info_c["data_alignment"][:5]:
                        for num_m in _re_lite.finditer(r"\b(\d+(?:\.\d+)?)\s*%?", da):
                            v = num_m.group(1)
                            if len(v) >= 2 and v not in search_terms:
                                search_terms.append(v)
                # 加上 D 列作者
                if info_d.get("authors"):
                    first_author = info_d["authors"].split(",")[0].split(" et")[0].strip()
                    if first_author and first_author not in search_terms:
                        search_terms.append(first_author)
                
                # 在 PDF 中搜索
                for term in search_terms[:5]:
                    for p_idx, page in enumerate(doc):
                        if p_idx >= 5:  # 只搜前 5 页
                            break
                        text = page.get_text()[:3000]
                        if term in text:
                            # 找上下文
                            idx = text.find(term)
                            ctx = text[max(0, idx-30):idx+60].replace("\n", " ")
                            light_hits.append((term, p_idx+1, ctx))
                            break
                doc.close()
            except Exception as _e:
                pass
        
        if light_hits:
            for dp, page, ctx in light_hits[:4]:
                md_parts.append(f"    ✓ '{dp}' → page {page}: {ctx}...")
            md_parts.append("    (轻量级 PyMuPDF 搜索, 未做 docling 语义级应证, 待升级)")
        else:
            md_parts.append("    (未做 docling 应证, 轻量级搜索未命中关键数据点)")

    # ⑤ 推理结果 — v8.5 严格基于 PPT视觉 vs PDF高亮双向对齐的 step2_score
    md_parts.append("  ⑤ 推理结果:")
    
    if main_score is None:
        md_parts.append("    ⚠️ 未做 PPT视觉 vs PDF高亮 双向对齐, 待运行 docling / 轻量级搜索应证")
        if scan.get("main_pdf"):
            md_parts.append(f"    📁 main PDF 文件: {scan['main_pdf']} ({scan.get('main_pdf_size_kb', 0)}KB)")
            md_parts.append(f"    💡 文件存在, 待 PPT视觉识别 + PDF docling/PyMuPDF 应证")
    elif main_score >= 1.0:
        md_parts.append("    ✅ main 完整应证 PPT 视觉识别的全部信息要素 (⭐满分, 双向对齐)")
    elif main_score >= 0.85:
        md_parts.append("    ✅ main 高度应证 PPT 视觉识别的多数信息要素")
    elif main_score >= 0.7:
        md_parts.append("    ⚠️ main 部分应证 PPT 视觉识别的信息要素")
    elif main_score >= 0.4:
        md_parts.append("    ⚠️ main 应证不足, 需 fallback 补强")
    else:
        md_parts.append("    ❌ main 应证失败, fallback 是必需")

    # 保留 visual_alignment / semantic_reasoning 作为补充
    if info_c.get("semantic_reasoning"):
        md_parts.append("")
        md_parts.append("  [补充参考] 视觉/语义推理原始记录:")
        for sr in info_c["semantic_reasoning"][:2]:
            md_parts.append(f"    - {sr[:100]}")

    md_parts.append("")
    
    # 【📎 下载链接 + 时效】
    link_et = identify_link_eternality(doi, info_d["journal"], info_d)

    # v8.7: 会议摘要 (ESMO/ASCO/APASL/CSCO/EASL/AASLD) 即使有 DOI, 也不走出版商直链
    # 因为 PDF 是会议摘要, 不是 ScienceDirect/PubMed 上的论文
    # v9.1: 所有有 DOI 的 Pn-x 都用 DOI 重定向 URL (指向具体文章/摘要页)
    if doi and not doi.startswith("备注"):
        md_parts.append("【📎 下载链接 + 时效性】")
        md_parts.append(f"  {link_et['label']}")

        # v7.6: 多层级下载链接 (出版商直链 + 数据库 + DOI 通用 + OpenAccess)
        # v9.0: 传递 verified URL (从 DOI 重定向链跟踪得到, 真实可访问)
        manifest = scan.get("manifest", {})
        verified_url = manifest.get("verified_doi_url")
        pdf_urls = get_publisher_pdf_urls(doi, info_d.get("journal", ""), verified_url)

        # v9.0: 优先用 verified URL (从 DOI 重定向链跟踪得到, 真实可访问)
        # 例如: 
        #   - P13-2: https://linkinghub.elsevier.com/retrieve/pii/S0168827825002260 (正确)
        #   - 旧: https://www.sciencedirect.com/science/article/doi/10.1016/j.jhep.2025.03.033 (404)
        # 特殊: Weblink 也用 verified URL (GLOBOCAN 等)
        md_parts.append("  🔗 链接:")
        for label, url in pdf_urls:
            if "全文" in label:
                # 第一行: 出版商全文 (verified URL, 真实可访问)
                md_parts.append(f"    - {label}: [{label.split()[0]}]({url})")
            elif label == "DOI 主链接":
                md_parts.append(f"    - DOI 主链接: [{doi}](https://doi.org/{doi})")
            elif label == "PubMed 搜索":
                md_parts.append(f"    - PubMed 搜索: [{doi}]({url})")
            elif label == "Europe PMC 搜索":
                md_parts.append(f"    - Europe PMC 搜索: [{doi}]({url})")

        if link_et.get("expiry_note"):
            md_parts.append(f"  - 时效说明: {link_et['expiry_note']}")
        if link_et.get("backup_url"):
            md_parts.append(f"  - 失效后备: [{link_et['backup_url']}]({link_et['backup_url']})")
        md_parts.append("")
    elif pn_x == "P3-1":
        # GLOBOCAN 特殊
        md_parts.append("【📎 下载链接 + 时效性】")
        md_parts.append(f"  {link_et['label']}")
        md_parts.append(f"  - IARC 官方 (2024 在线版): [gco.iarc.who.int](https://gco.iarc.who.int)")
        md_parts.append(f"  - GLOBOCAN 2022 Liver PDF: [IARC 存档](https://gco.iarc.fr/today/data/factsheets/cancers/11-Liver-fact-sheet.pdf)")
        md_parts.append(f"  - 时效说明: {link_et['expiry_note']}")
        md_parts.append(f"  - 失效后备: [Wayback Machine]({link_et['backup_url']})")
        md_parts.append("")
    # v9.1: 无 DOI 的 Pn-x (政府文件/中文期刊/会议摘要无DOI)
    # 构造搜索链接指向具体页面
    else:
        # 无 DOI: 用 D 列期刊名+标题构造 PubMed 搜索
        journal = info_d.get("journal", "").strip()
        title = info_d.get("title", "").strip()
        authors = info_d.get("authors", "").strip()
        year = info_d.get("year", "")

        # 构造搜索词 (与 if branch 共享)
        search_terms = []
        if authors:
            first_author = authors.split(",")[0].split(" et")[0].strip()
            if first_author:
                search_terms.append(first_author)
        if journal:
            search_terms.append(journal)
        if year:
            search_terms.append(str(year))
        if title:
            title_kw = title.replace(" ", "+")[:30]
            search_terms.append(title_kw)

        md_parts.append("【📎 下载链接 + 时效性】")

        # v9.3: 检查 verified_doi_url (从 gov.cn 搜索得到, 真实可访问页面)
        manifest = scan.get("manifest", {})
        verified_url = manifest.get("verified_doi_url")
        if verified_url:
            source_label = "gov.cn" if "gov.cn" in verified_url else "源网站"
            md_parts.append(f"  ✅ {source_label} 全文")
            md_parts.append(f"  🔗 链接:")
            md_parts.append(f"    - {source_label} 全文: [{source_label}]({verified_url})")
            md_parts.append("")
            md_parts.append("  🔍 备选搜索:")
        else:
            md_parts.append("  ⏳ 无 DOI 永久链接")

        # 构造搜索词 (优先用 DOI 备注, 如果无 DOI)
        # 无 DOI 的 Pn-x: 政府文件/中文期刊, 用 DOI 备注列的关键词
        if doi and doi.startswith("备注"):
            # 无 DOI: 用 D 列原文作为搜索关键词
            # D 列是文档标题 (如 "《健康中国行动——癌症防治行动实施方案（2023-2030年）》")
            # 这是最精确的搜索词, 指向具体文档页
            # D 列原文在 info_d 中没有, 从 c_raw 或 doi 提取
            # 用 c_raw 中的标题作为搜索词
            search_term = ""
            # 从 c_raw 提取标题 (去掉 PPT 标号前缀)
            if c_raw and "「" in c_raw and "」" in c_raw:
                import re as _re_c
                m = _re_c.search(r'「(.+?)」', c_raw)
                if m:
                    search_term = m.group(1).replace(" ", "+")[:60]
            if not search_term:
                # 用 DOI 备注
                search_term = doi.replace("备注:", "").replace("无 DOI", "").strip().replace(" ", "+")[:40]
            if not search_term:
                search_term = "health"
            if search_term and search_term != "+":
                search_url = f"https://www.google.com/search?q={search_term}"
                md_parts.append(f"  - Google 搜索: [{search_term[:40]}]({search_url})")
        elif search_terms:
            search_term = "+".join(search_terms)
            search_url = f"https://www.google.com/search?q={search_term}"
            md_parts.append(f"  - Google 搜索: [{search_term[:40]}]({search_url})")
        
        # 会议摘要搜索 (按会议名+摘要号)
        if info_d.get("abstract_id"):
            abstract_id = info_d["abstract_id"]
            conf_name = info_d.get("conference_name", "")
            search_term = f"{conf_name}+{abstract_id}" if conf_name else abstract_id
            search_url = f"https://pubmed.ncbi.nlm.nih.gov/?term={search_term}"
            md_parts.append(f"  - PubMed 搜索 (会议+摘要号): [{search_term}]({search_url})")
        
        # 政府文件: 用 NHC 搜索
        if "政府" in journal or "健康" in journal or "中国" in journal:
            # v9.2: 用 C 列标题作为 NHC 搜索词
            nhc_term = search_term if search_term else "health"
            md_parts.append(f"  - NHC 搜索: [{nhc_term[:40]}](https://www.nhc.gov.cn/search?q={nhc_term})")
        
        md_parts.append("")
    
    md_parts.append(f"【🏷️ 类型】 {type_emoji}")
    
    return "\n".join(md_parts)




def build_h_rich_text(pn: str, d_field: str, c_field: str, g_path: str, doi: str) -> List[Dict]:
    """
    从 D + C + G 列数据, 生成完整 H 列 rich_text
    
    Args:
        pn: Pn-x 标号 (如 "2")
        d_field: CSV D 列原文
        c_field: 飞书 C 列原文
        g_path: CSV G 列路径 (如 "P5-2/P5-2_main_xxx.pdf")
        doi: CSV E 列 DOI
    
    Returns:
        飞书 rich_text 数组 (List[Dict])
    """
    info_d = parse_d_field(d_field)
    info_c = parse_c_field(c_field)
    h_md = build_h_md(pn, info_d, info_c, g_path, doi)
    return markdown_to_rich_text(h_md)


if __name__ == "__main__":
    import sys
    import csv
    
    csv_path = "/Users/david/Desktop/雷管方案_文献整理/_citation_table/citation_table.csv"
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # 测试: 从 CSV 读 P5 第 2 行, 生成 rich_text
        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            cols = reader.fieldnames
            for r in reader:
                if r[cols[0]] == "5" and r[cols[1]] == "2":
                    d = r[cols[3]]
                    g = r[cols[6]]
                    doi = r[cols[4]]
                    rt = build_h_rich_text("2", d, "PPT 标号2: 化疗方案 FOLFOX", g, doi)
                    print(f"\n=== P5-2 rich_text ({len(rt)} segments) ===")
                    for i, item in enumerate(rt):
                        t = item.get("type")
                        text = str(item.get("text", ""))[:60].replace(chr(10), "\\n")
                        link = item.get("link", "")
                        print(f"  [{i}] {t}: {text} {('-> ' + link[:40]) if link else ''}")
                    break



# ════════════════════════════════════════════════════════════════════
# v6: 扫描 Pn-x 目录, 真实文件清单 (与 highlight 目录一致)
# ════════════════════════════════════════════════════════════════════



def build_h_rich_text_v6(pn_x, info_d, info_c, doi, scan=None, c_raw=None, row_n=None, lit_base="/Users/david/Desktop/雷管方案_文献整理/_literature_citation_index", d=None):
    """v6 入口"""
    if scan is None:
        scan = scan_pn_x_dir(pn_x, lit_base)
    if row_n is None:
        row_n = int(pn_x.split("-")[1]) + 10
    h_md = build_h_md_v6(pn_x, info_d, info_c, doi, scan, c_raw, row_n, lit_base, d=d)
    return markdown_to_rich_text(h_md)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("=== 测试 v6 ===")
        d = scan_pn_x_dir("P5-2")
        print(f"P5-2: main={d['main']}, fb={d['fb']}, score={calculate_main_score(d)}")
        
        d = scan_pn_x_dir("P5-8")
        print(f"P5-8: main={d['main']}, fb={d['fb']}, score={calculate_main_score(d)}")
        
        d = scan_pn_x_dir("P5-13")
        print(f"P5-13: main={d['main']}, supp={d['supp']}, score={calculate_main_score(d)}")


