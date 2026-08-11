#!/usr/bin/env python3
"""
via54_highlight_render.py — v9.7 升级: bbox 精确 highlight 算法

替代现有 PyMuPDF 全页黄色覆盖:
- 用 docling 解析 PDF, 提取 texts/tables/pictures 的精确 bbox
- 根据 PPT 数据点 + 医学术语找匹配的 cell/text region
- 用 PIL 在 bbox 上画精确黄色覆盖
- 多页支持 (渲染所有有 bbox 的页面)

输入:
- pdf_path: PDF 文件路径
- data_points: PPT 数据点 (e.g., ["14.4", "8.5", "76.8%"])
- medical_terms: 医学术语 (e.g., ["Liver", "HBV", "BCLC"])
- output_prefix: 输出文件前缀 (e.g., "P3-3_page")

输出:
- {output_prefix}_N.jpg: 每页一张精确 highlight 图
- manifest 更新: highlight_summary.bbox_data_points
"""
import sys, os, json, fitz
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from PIL import Image, ImageDraw
import io

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from pdf_understand import parse_pdf_with_docling, find_data_point_in_doc
    HAS_DOCLING = True
except ImportError:
    HAS_DOCLING = False


def find_matches_in_docling(doc: Dict, data_points: List[str], medical_terms: List[str] = None) -> List[Dict]:
    """
    在 docling 解析结果中搜索数据点 + 医学术语, 返回所有匹配的 bbox
    
    Returns:
        [{page_no, bbox, text, type: "data_point" | "medical_term"}, ...]
    """
    matches = []
    
    # 1. 搜 texts
    for t in doc.get("texts", []):
        text = t.get("text", "")
        if not text:
            continue
        provs = t.get("prov", [])
        if not provs:
            continue
        
        # 数据点匹配
        for dp in (data_points or []):
            if dp in text or dp.replace('%', '') in text:
                for p in provs:
                    matches.append({
                        "page_no": p["page_no"],
                        "bbox": p["bbox"],
                        "text": text[:60],
                        "type": "data_point",
                        "data_point": dp,
                    })
                break  # 一个 text 多次匹配没意义
        
        # 医学术语匹配 (可选)
        if medical_terms:
            for term in medical_terms:
                if term in text:
                    for p in provs:
                        matches.append({
                            "page_no": p["page_no"],
                            "bbox": p["bbox"],
                            "text": text[:60],
                            "type": "medical_term",
                            "term": term,
                        })
                    break
    
    # 2. 搜 tables (cell 级别)
    for tbl in doc.get("tables", []):
        provs = tbl.get("prov", [])
        if not provs:
            continue
        # 整个 table 作为 fallback (高亮整张表)
        for p in provs:
            matches.append({
                "page_no": p["page_no"],
                "bbox": p["bbox"],
                "text": "[Table]",
                "type": "table",
            })
    
    return matches


def render_bbox_highlights(
    pdf_path: str,
    matches: List[Dict],
    output_dir: str,
    prefix: str,
    scale: float = 1.5,
    alpha: int = 80,
    max_pages: int = 5,
) -> List[str]:
    """
    在 PDF 页面上画精确 bbox 高亮, 保存为 jpg
    
    Returns:
        输出文件路径列表
    """
    doc = fitz.open(pdf_path)
    os.makedirs(output_dir, exist_ok=True)
    
    # 按页分组
    by_page = {}
    for m in matches:
        pn = m["page_no"]
        if pn not in by_page:
            by_page[pn] = []
        by_page[pn].append(m)
    
    # 限制最多渲染 max_pages 页
    pages_to_render = sorted(by_page.keys(), key=lambda x: int(x) if str(x).isdigit() else 999)[:max_pages]
    
    output_files = []
    for pn in pages_to_render:
        page = doc[int(pn) - 1]
        mat = fitz.Matrix(75/72, 75/72)  # scale倍 DPI
        pix = page.get_pixmap(matrix=mat)
        pil_img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA")
        
        # 创建透明 overlay
        overlay = Image.new("RGBA", pil_img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # 画 bbox
        page_h_pts = page.rect.height
        for m in by_page[pn]:
            bbox = m["bbox"]
            if not bbox:
                continue
            l = float(bbox.get("l", 0)) * 75 / 72
            t = float(bbox.get("t", 0)) * 75 / 72
            r = float(bbox.get("r", 0)) * 75 / 72
            b = float(bbox.get("b", 0)) * 75 / 72
            
            # BOTTOMLEFT → TOPLEFT 转换
            coord_origin = bbox.get("coord_origin", "TOPLEFT")
            if coord_origin == "BOTTOMLEFT":
                new_t = page_h_pts - float(bbox.get("t", 0))
                new_b = page_h_pts - float(bbox.get("b", 0))
                t = new_b * 75 / 72
                b = new_t * 75 / 72
            
            # 用 min/max 确保 t <= b
            t_final = min(t, b)
            b_final = max(t, b)
            l_final = min(l, r)
            r_final = max(l, r)
            
            # 最小尺寸: bbox 太小, 扩展到至少 25 px 高度 (便于观察)
            min_h = 25
            if b_final - t_final < min_h:
                center = (t_final + b_final) / 2
                t_final = center - min_h / 2
                b_final = center + min_h / 2
            
            # 最小宽度: 20 px
            min_w = 20
            if r_final - l_final < min_w:
                center = (l_final + r_final) / 2
                l_final = center - min_w / 2
                r_final = center + min_w / 2
            
            draw.rectangle([l_final, t_final, r_final, b_final], fill=(255, 255, 0, alpha))
        
        # 合成
        result = Image.alpha_composite(pil_img, overlay).convert("RGB")
        
        output_path = f"{output_dir}/{prefix}_{pn}.jpg"
        result.save(output_path, "JPEG", quality=85)
        output_files.append(output_path)
    
    doc.close()
    return output_files


def render_highlight_for_pn_x(
    pn_x: str,
    pdf_path: str,
    data_points: List[str],
    medical_terms: List[str] = None,
    output_dir: str = None,
) -> Dict:
    """
    为单个 Pn-x 生成 bbox 精确 highlight
    
    Returns:
        {"output_files": [...], "matches": [...], "manifest_update": {...}}
    """
    if output_dir is None:
        output_dir = os.path.dirname(pdf_path)
    
    if not HAS_DOCLING:
        return {"output_files": [], "matches": [], "error": "docling not available"}
    
    # 1. docling 解析
    doc = parse_pdf_with_docling(pdf_path)
    
    # 2. 找匹配
    matches = find_matches_in_docling(doc, data_points, medical_terms)
    
    # 3. 渲染
    prefix = f"{pn_x}_bbox"
    output_files = render_bbox_highlights(pdf_path, matches, output_dir, prefix)
    
    return {
        "output_files": output_files,
        "matches": matches,
        "manifest_update": {
            "bbox_data_points": data_points,
            "bbox_medical_terms": medical_terms or [],
            "bbox_match_count": len(matches),
            "bbox_rendered_pages": len(output_files),
        }
    }


def main():
    if len(sys.argv) < 3:
        print("Usage: via54_highlight_render.py <pn_x> <pdf_path> [data_points] [medical_terms]")
        print("Example: via54_highlight_render.py P3-3 main.pdf 14.4,8.5 Liver,Pancreas")
        sys.exit(1)
    
    pn_x = sys.argv[1]
    pdf_path = sys.argv[2]
    
    data_points = sys.argv[3].split(",") if len(sys.argv) > 3 and sys.argv[3] else []
    medical_terms = sys.argv[4].split(",") if len(sys.argv) > 4 and sys.argv[4] else []
    
    result = render_highlight_for_pn_x(pn_x, pdf_path, data_points, medical_terms)
    
    print(f"=== {pn_x} bbox highlight ===")
    print(f"  Matches: {len(result['matches'])}")
    print(f"  Output files: {len(result['output_files'])}")
    for f in result['output_files']:
        print(f"    {f}")


if __name__ == "__main__":
    main()
