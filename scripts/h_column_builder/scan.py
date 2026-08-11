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


# ════════════════════════════════════════════════════════════════════
# 解析 CSV D 列 (作者/标题/期刊/年份/卷期页)
# ════════════════════════════════════════════════════════════════════


def scan_pn_x_dir(pn_x: str, lit_base: str = "/Users/david/Desktop/雷管方案_文献整理/_literature_citation_index", src_base: str = "/Users/david/Desktop/雷管方案_文献整理") -> Dict:
    """
    扫描 Pn-x 目录 + manifest.fallback_pdfs, 返回 main / fb / supp 三类文件 + manifest

    v8.2 升级: 同时扫描主目录 (src_base), 如果 lit_base 缺 _fallback_/_supp_ 文件, 自动同步.
    主目录是真理源, _literature_citation_index/ 是工作副本.
    
    Args:
        pn_x: Pn-x 标识 (如 "P5-2")
        lit_base: 文献标注根目录
    
    Returns:
        {
            "pn_x": "P5-2",
            "main": ["P5-2_main_xxx.pdf"],
            "fb": ["P5-2_fb_xxx.pdf"],
            "supp": ["P5-2_supp_xxx.pdf"],
            "fb_cross_refs": [...],  # 跨 Pn-x 引用 (manifest.fallback_pdfs 提取)
            "fb_info": {filename: {应证内容, score, exists}},
            "sizes": {filename: int (bytes)},
            "manifest": {...},
            "highlight_summary": {...},
            "fallback_triggered": bool,
            "fallback_reason": str,
        }
    """
    import os as _os
    import re as _re
    p = f"{lit_base}/{pn_x}"
    if not _os.path.isdir(p):
        return {"pn_x": pn_x, "main": [], "fb": [], "supp": [], "fb_cross_refs": [], "fb_info": {}, "sizes": {}, "manifest": {}, "highlight_summary": {}, "fallback_triggered": False, "fallback_reason": ""}
    
    # v8.2: 自动同步主目录到 lit_base (缺失 fb / supp 自动复制)
    src_p = f"{src_base}/{pn_x}"
    if _os.path.isdir(src_p) and _os.path.isdir(p):
        # 扫描主目录
        src_pdfs = sorted([f for f in _os.listdir(src_p) if f.endswith('.pdf')])
        for f in src_pdfs:
            dst_path = f"{p}/{f}"
            src_path = f"{src_p}/{f}"
            # 只复制 fb / supp (main 不复制, 避免覆盖主目录的变更)
            if not _os.path.isfile(dst_path) and ('_fallback_' in f or '_fb_' in f or '_supp_' in f):
                try:
                    import shutil as _shutil
                    _shutil.copy2(src_path, dst_path)
                except Exception:
                    pass
        # 同步 manifest 的 fallback_pdfs
        if _os.path.isfile(f"{src_p}/_manifest.json"):
            try:
                import json as _json2
                with open(f"{src_p}/_manifest.json") as _smf:
                    src_m = _json2.load(_smf)
                src_fb = src_m.get("fallback_pdfs", [])
                if src_fb:
                    mp_local = f"{p}/_manifest.json"
                    local_m = {}
                    if _os.path.isfile(mp_local):
                        with open(mp_local) as _lmf:
                            local_m = _json2.load(_lmf)
                    # 合并 fallback_pdfs (去重)
                    existing = local_m.get("fallback_pdfs", [])
                    for entry in src_fb:
                        if entry not in existing:
                            existing.append(entry)
                    local_m["fallback_pdfs"] = existing
                    if _os.path.isfile(mp_local):
                        with open(mp_local, 'w') as _lmf:
                            _json2.dump(local_m, _lmf, ensure_ascii=False, indent=2)
            except Exception:
                pass

    pdfs = sorted([f for f in _os.listdir(p) if f.endswith('.pdf')])
    main = [f for f in pdfs if '_main_' in f]
    fb = [f for f in pdfs if '_fallback_' in f or '_fb_' in f]
    supp = [f for f in pdfs if '_supp_' in f]
    sizes = {f: _os.path.getsize(f"{p}/{f}") for f in pdfs}
    
    manifest = {}
    manifest_path = f"{p}/_manifest.json"
    if _os.path.isfile(manifest_path):
        import json as _json
        with open(manifest_path) as _f:
            manifest = _json.load(_f)
    
    hl_summary = manifest.get("highlight_summary", {})
    if isinstance(hl_summary, list) and hl_summary:
        # 多张高亮图时, 取最大 hits/terms
        best = max(hl_summary, key=lambda x: x.get("hits", 0))
        hl_summary = best
    
    # 解析 manifest.fallback_pdfs (可能含跨 Pn-x 引用)
    # 格式: ['P4-3/P4-3_main_Gao_Gastro_2017.pdf (应证 PPT 异质性概念)', ...]
    fb_cross_refs = []
    fb_info = {}  # 本目录 fb 文件的元信息 (从 manifest 提取)
    fb_pdfs_raw = manifest.get("fallback_pdfs", [])
    
    for entry in fb_pdfs_raw:
        # 提取路径和应证内容
        m = _re.match(r'\s*(\S+?\.pdf)\s*(?:\(([^)]+)\))?', entry)
        if not m:
            continue
        pdf_rel = m.group(1)
        应证_text = m.group(2) or ""
        
        # 路径可能是 Pn-x/file.pdf (跨标号) 或 file.pdf (本目录)
        if "/" in pdf_rel:
            # 跨标号引用
            target_pn_x = pdf_rel.split("/")[0]
            target_file = pdf_rel.split("/")[-1]
            target_path = f"{lit_base}/{target_pn_x}/{target_file}"
            
            # 检查是否在跨标号目录下也存在于 _literature_citation_index
            exists_in_lit = _os.path.isfile(target_path)
            # 也可能在 src_base
            src_target = f"/Users/david/Desktop/雷管方案_文献整理/{pdf_rel}"
            exists_in_src = _os.path.isfile(src_target)
            
            # 从目标 Pn-x 的 manifest 取 step2_score
            target_score = 0.0
            target_mp = f"{lit_base}/{target_pn_x}/_manifest.json"
            if _os.path.isfile(target_mp):
                with open(target_mp) as tf:
                    target_manifest = _json.load(tf)
                target_score = target_manifest.get("step2_score", 0.0)
            
            # 计算目标文件名 (去路径)
            target_basename = pdf_rel.split("/")[-1] if "/" in pdf_rel else pdf_rel
            # 应证内容: fallback_trigger_reason 里有更多信息
            fb_info_text = 应证_text or manifest.get("fallback_trigger_reason", "")[:100]
            
            if target_pn_x != pn_x:
                # 跨标号引用
                fb_cross_refs.append({
                    "path": pdf_rel,
                    "应证": fb_info_text,
                    "target_pn_x": target_pn_x,
                    "target_file": target_basename,
                    "exists_in_lit": exists_in_lit,
                    "exists_in_src": exists_in_src,
                    "score": target_score,
                })
            else:
                # 同标号, 检查是否在本目录 fb_local (扫到的文件名)
                if target_basename in fb:
                    fb_info[target_basename] = {
                        "应证": fb_info_text,
                        "score": manifest.get("step2_score", 0.0),
                        "path": target_basename,
                    }
        else:
            # 本目录 fb 文件
            local_path = f"{p}/{pdf_rel}"
            if _os.path.isfile(local_path):
                fb_info[pdf_rel] = {
                    "应证": 应证_text,
                    "score": manifest.get("step2_score", 0.0),
                    "path": pdf_rel,
                }
    
    # 合并: fb + fb_cross_refs 都视为 fallback
    # 但 fb (本目录) 优先, fb_cross_refs 补充
    all_fb = list(fb)
    seen = set(fb)
    for cross in fb_cross_refs:
        if cross["target_file"] not in seen:
            all_fb.append(cross["target_file"])
            seen.add(cross["target_file"])
    
    # 计算 main_pdf / main_score (统一接口)
    main_pdf = main[0] if main else None
    main_score = manifest.get("step2_score")

    return {
        "pn_x": pn_x,
        "main": main,
        "main_pdf": main_pdf,
        "main_pdf_path": f"{p}/{main_pdf}" if main_pdf else None,
        "main_pdf_size_kb": (sizes.get(main_pdf, 0) // 1024) if main_pdf else 0,
        "main_score": main_score,
        "fb": all_fb,  # 本目录 + 跨标号引用合并
        "fb_local": fb,  # 仅本目录
        "fb_cross_refs": fb_cross_refs,  # 跨标号引用详情
        "fb_info": fb_info,  # 本目录 fb 元信息
        "supp": supp,
        "sizes": sizes,
        "manifest": manifest,
        "highlight_summary": hl_summary,
        "fallback_triggered": manifest.get("fallback_triggered", False),
        "fallback_reason": manifest.get("fallback_trigger_reason", ""),
    }





def calculate_main_score(scan: Dict) -> Optional[float]:
    """
    计算 main PDF 应证 PPT 内容的评分 (None / 0.00-1.00)
    
    Returns:
        score ∈ [0.00, 1.00], 或 None (表示未运行 docling, 用 CSV 元数据默认 1.00)
    """
    if not scan["main"]:
        return 0.0

    # 1) 优先用 P5 Step 2 的真实评分 (docling 搜 PPT 数据点)
    if scan.get("manifest", {}).get("step2_score") is not None:
        return float(scan["manifest"]["step2_score"])

    # 2) 其次用 highlight_summary hits/terms (cap 1.0)
    hl = scan.get("highlight_summary", {})
    if hl and hl.get("terms"):
        raw = hl.get("hits", 0) / max(hl.get("terms", 1), 1)
        return round(min(raw, 1.0), 2)

    # 3) fallback_triggered 时 main 不足
    if scan["fallback_triggered"]:
        return 0.4

    # 4) 默认 None (slide 6+: 未运行 docling, 用 D 列元数据默认 1.00)
    return None





def calculate_fallback_score(scan: Dict, fb_filename: str) -> float:
    """
    计算 fallback PDF 应证 PPT 内容的评分
    
    优先级:
    1. 跨标号引用的 target_score (从目标 Pn-x manifest 提取, 比较准)
    2. 基于 fb_filename 推断 (Bray → 0.85, NEJM → 0.70, Appendix → 0.50 等)
    3. fallback_triggered 时 0.60
    
    Returns:
        score ∈ [0.00, 1.00]
    """
    # 优先级 1: 跨标号引用
    for cross in scan.get("fb_cross_refs", []):
        if cross.get("target_file") == fb_filename:
            s = cross.get("score", 0)
            if s > 0:
                return s
    
    fb_lower = fb_filename.lower()
    
    # ICMJE 披露: 通常是补充材料, 不应证主论点
    if 'icmje' in fb_lower or 'disclosure' in fb_lower:
        return 0.30
    
    # 综述/标准评论 (standard review / review)
    if 'review' in fb_lower or 'standard' in fb_lower:
        return 0.65
    
    # Appendix 补充材料
    if 'appendix' in fb_lower:
        return 0.50
    
    # 政府文件 / 卫健委令汇编 / 法规 (永久)
    if any(kw in fb_lower for kw in ['卫健委', '政府', '令汇编', 'nhc', 'gov', 'regulation']):
        return 0.75
    
    # Bray/2024 GLOBOCAN 论文 (Ca-Cancer J Clin) - 高分
    if 'bray' in fb_lower or 'caac' in fb_lower:
        return 0.85
    
    # GLOBOCAN 2024 China fact sheet - 中等分
    if 'globocan' in fb_lower or '2024' in fb_lower and 'china' in fb_lower:
        return 0.65
    
    # ASCO 摘要/会议摘要 (abstract)
    if 'abstract' in fb_lower or 'asco' in fb_lower or 'esmo' in fb_lower:
        return 0.55
    
    # NEJM 全文 / 同期发表
    if 'nejm' in fb_lower or 'lancet' in fb_lower:
        return 0.70
    
    # fallback_triggered 时说明 fb 应证的是 main 漏掉的内容
    if scan.get("fallback_triggered"):
        return 0.60
    
    return 0.50


# ════════════════════════════════════════════════════════════════════
# v6: 链接时效性识别
# ════════════════════════════════════════════════════════════════════



def run_light_step2(pn_x: str, lit_base: str, ppt_data_points: list) -> Dict:
    """
    v8.5: 轻量级 step2 应证 — 对 slide 6+ Pn-x (没 docling 应证数据) 跑 PyMuPDF 搜索,
    写入 manifest: ppt_data_points / found_data_points / found_data_point_locations / step2_score

    原则: 不依赖 D 列, 只从 PPT 视觉识别 (ppt_data_points) + PDF 实际搜索

    Args:
        pn_x: Pn-x 标识 (如 "P11-1")
        lit_base: 文献标注根目录
        ppt_data_points: 从 PPT 视觉提取的数据点 (如 ['301', '15.9', '2023', '12', '12%', ...])

    Returns:
        {
            "ppt_data_points": [...],
            "found_data_points": [...],
            "found_data_point_locations": {dp: [{page_no, text_snippet}, ...]},
            "step2_score": float (found/total, e.g. 0.75),
            "step2_found": int,
            "step2_total": int,
        }
    """
    import os as _os_lite
    import re as _re_lite
    result = {
        "ppt_data_points": ppt_data_points,
        "found_data_points": [],
        "found_data_point_locations": {},
        "step2_score": 0.0,
        "step2_found": 0,
        "step2_total": len(ppt_data_points),
    }

    if not ppt_data_points:
        return result

    # 找 main PDF 路径
    p = f"{lit_base}/{pn_x}"
    if not _os_lite.path.isdir(p):
        return result

    main_pdfs = [f for f in _os_lite.listdir(p) if '_main_' in f and f.endswith('.pdf')]
    if not main_pdfs:
        return result

    main_pdf_path = f"{p}/{main_pdfs[0]}"

    try:
        import fitz as _fitz_lite
        doc = _fitz_lite.open(main_pdf_path)

        # 数值等价: 14.4 == 14.40 == 14.4%
        def gen_variants(dp):
            variants = [dp]
            if dp.endswith('%'):
                variants.append(dp[:-1])  # 14.4% → 14.4
            elif dp.replace('.', '').replace('-', '').isdigit():
                variants.append(dp + '%')  # 14.4 → 14.4%
            return variants

        # 搜索每个 ppt_data_point
        for dp in ppt_data_points:
            variants = gen_variants(dp)
            hit_pages = []
            for variant in variants:
                for p_idx in range(min(8, len(doc))):  # 搜前 8 页
                    text = doc[p_idx].get_text()
                    if variant in text:
                        idx = text.find(variant)
                        ctx = text[max(0, idx-30):idx+80].replace("\n", " ")
                        hit_pages.append({"page_no": p_idx+1, "text_snippet": ctx[:120]})
                        break
                if hit_pages:
                    break
            if hit_pages:
                result["found_data_points"].append(dp)
                result["found_data_point_locations"][dp] = hit_pages

        doc.close()

        # 计算 step2_score
        result["step2_found"] = len(result["found_data_points"])
        if result["step2_total"] > 0:
            result["step2_score"] = min(1.0, result["step2_found"] / result["step2_total"])

        # 写 manifest
        mp = f"{p}/_manifest.json"
        if _os_lite.path.isfile(mp):
            import json as _json_lite
            with open(mp) as _mf:
                m = _json_lite.load(_mf)
        else:
            m = {}

        m["ppt_data_points"] = ppt_data_points
        m["found_data_points"] = result["found_data_points"]
        m["found_data_point_locations"] = result["found_data_point_locations"]
        m["step2_score"] = result["step2_score"]
        m["step2_found"] = result["step2_found"]
        m["step2_total"] = result["step2_total"]
        m["algorithm_version"] = "v8.5_light_step2"

        with open(mp, 'w') as _mf:
            _json_lite.dump(m, _mf, ensure_ascii=False, indent=2)

    except Exception as _e:
        pass

    return result




def extract_ppt_data_points_from_c(c_raw: str) -> List[str]:
    """
    v8.5: 从 C 列 (PPT 视觉识别) 提取 ppt_data_points
    不依赖 D 列. 提取数字 + 医学术语 + 关键文字
    """
    import re as _re
    pts = []
    if not c_raw:
        return pts

    # 1. 数字 (≥2 位) - 含百分比/小数
    for m in _re.finditer(r"\b(\d+(?:\.\d+)?)\s*%?", c_raw):
        v = m.group(1)
        if len(v) >= 2 and v not in pts:
            pts.append(v)

    # 2. 医学术语
    medical_kws = [
        "STRIDE", "T+A", "O+Y", "Len", "Lenvatinib", "Pembro", "NIVO", "IPI",
        "Durvalumab", "Tremelimumab", "Atezolizumab", "Bevacizumab", "Sorafenib",
        "Regorafenib", "Cabozantinib", "Ramucirumab", "Sintilimab", "Toripalimab",
        "Camrelizumab", "Tislelizumab", "Penpulimab", "Cadonilimab", "AK104",
        "Donafenib", "Envafolimab", "Anlotinib", "Apatinib", "Lenvatinib",
        "FOLFOX4", "GEMOX", "HAIC", "TACE", "RFA", "PEI",
    ]
    for kw in medical_kws:
        if kw in c_raw and kw not in pts:
            pts.append(kw)

    # 3. 研究名 (大写 + 数字)
    for m in _re.finditer(r"\b([A-Z][A-Z\-]+(?:\d+)?)\b", c_raw):
        study = m.group(1)
        if len(study) >= 3 and study not in pts:
            pts.append(study)

    return pts[:15]  # 限制 15 项



