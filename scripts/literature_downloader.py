#!/usr/bin/env python3
"""
literature_downloader.py — Step 3 & 4: 文献检索下载、访问链接整理与标准目录结构化

流程:
  Step 3: 提取引用字段 (DOI / PMID / 引文字符串) → 级联检索并下载 PDF，或整理下载/访问链接
  Step 4: 组织标准结构目录:
          {Pn-x}/
            ├── {Pn-x}_main.pdf
            ├── {Pn-x}_claim_visual.png
            └── {Pn-x}_meta.json
"""
import os
import sys
import re
import json
import time
import shutil
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import fitz

_UA = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
}


def _http_get_json(url: str, timeout: int = 30) -> Optional[Dict]:
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8', 'replace'))
    except Exception:
        return None


def _download_pdf_stream(url: str, out_path: str, timeout: int = 60) -> bool:
    try:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            if data.startswith(b'%PDF'):
                os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
                with open(out_path, 'wb') as f:
                    f.write(data)
                return True
    except Exception:
        pass
    return False


def verify_pdf_validity(pdf_path: str) -> bool:
    """验证 PDF 是否合法可读"""
    if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) < 1024:
        return False
    try:
        doc = fitz.open(pdf_path)
        valid = len(doc) > 0
        doc.close()
        return valid
    except Exception:
        return False


def resolve_doi_from_citation(citation: str) -> Optional[str]:
    """通过 Crossref 查询将引文条目解析为 DOI"""
    if not citation or len(citation) < 10:
        return None
    # 直接正则查找
    m = re.search(r'10\.\d{4,9}/[^\s,;。\'"]+', citation)
    if m:
        return m.group(0).rstrip('.,;')
        
    q = urllib.parse.quote(citation[:200])
    url = f"https://api.crossref.org/works?query.bibliographic={q}&rows=1"
    data = _http_get_json(url, timeout=20)
    if data and "message" in data:
        items = data["message"].get("items", [])
        if items and "DOI" in items[0]:
            return items[0]["DOI"]
    return None


def fetch_open_access_pdf_url(doi: str) -> Optional[str]:
    """通过 OpenAlex / Unpaywall 获取开放获取 PDF 直链"""
    if not doi:
        return None
        
    # 1. OpenAlex
    oa_url = f"https://api.openalex.org/works/doi:{urllib.parse.quote(doi)}"
    data = _http_get_json(oa_url, timeout=20)
    if data:
        loc = data.get("best_oa_location") or {}
        pdf_url = loc.get("pdf_url")
        if pdf_url:
            return pdf_url

    # 2. Europe PMC via DOI
    epmc_url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{urllib.parse.quote(doi)}&format=json&pageSize=1"
    epmc_data = _http_get_json(epmc_url, timeout=20)
    if epmc_data:
        results = epmc_data.get("resultList", {}).get("result", [])
        if results:
            for ft in results[0].get("fullTextUrlList", {}).get("fullTextUrl", []):
                if ft.get("documentStyle") == "pdf":
                    return ft.get("url")
                    
    return None


def find_local_pdf_candidate(pn_x: str, search_dirs: List[str]) -> Optional[str]:
    """在本地目录中检索已有的文献 PDF 文件"""
    for s_dir in search_dirs:
        if not os.path.exists(s_dir):
            continue
            
        # 1. 精确匹配 P2-1.pdf, P12-1.pdf, Pn-S2_1.pdf 或 P2-1_main.pdf
        for cand_name in [f"{pn_x}.pdf", f"{pn_x}_main.pdf", f"Pn-S{pn_x.replace('P', '')}.pdf"]:
            cand = os.path.join(s_dir, cand_name)
            if verify_pdf_validity(cand):
                return cand
            cand_sub = os.path.join(s_dir, pn_x, cand_name)
            if verify_pdf_validity(cand_sub):
                return cand_sub
            
        # 2. 遍历模糊匹配
        for p in Path(s_dir).rglob("*.pdf"):
            if "highlight" in p.name or "tmp" in p.name:
                continue
            if pn_x in p.name:
                if verify_pdf_validity(str(p)):
                    return str(p)
                    
        # 3. 兜底: 若 search_dir 为单文件或只包含单个文献 PDF
        if os.path.isfile(s_dir) and s_dir.endswith(".pdf") and verify_pdf_validity(s_dir):
            return s_dir
        pdfs = [p for p in Path(s_dir).glob("*.pdf") if "highlight" not in p.name]
        if len(pdfs) == 1 and verify_pdf_validity(str(pdfs[0])):
            return str(pdfs[0])
            
    return None



def process_literature_for_claim(
    claim_item: Dict[str, Any],
    out_base_dir: str,
    local_search_dirs: Optional[List[str]] = None,
    allow_download: bool = True
) -> Dict[str, Any]:
    """
    Step 3 & 4 核心逻辑:
    针对单个 Claim，准备并组织 {Pn-x} 目录结构，保证 main_pdf 与 claim_visual 齐全。
    """
    pn_x = claim_item.get("pn_x", "P1-1")
    citation_text = claim_item.get("reference_field") or claim_item.get("claim_text") or ""
    doi = claim_item.get("doi")
    
    # 建立目标嵌套目录: out_base_dir/{Pn-x}/
    pn_x_dir = os.path.join(out_base_dir, pn_x)
    os.makedirs(pn_x_dir, exist_ok=True)
    
    main_pdf_path = os.path.join(pn_x_dir, f"{pn_x}_main.pdf")
    links_info = {
        "pn_x": pn_x,
        "doi": doi,
        "doi_url": f"https://doi.org/{doi}" if doi else None,
        "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/?term={urllib.parse.quote(citation_text[:80])}" if citation_text else None,
        "scholar_url": f"https://scholar.google.com/scholar?q={urllib.parse.quote(citation_text[:80])}" if citation_text else None,
        "download_url": None,
        "download_status": "pending",
        "main_pdf": None
    }

    # 1. 优先在本地寻找已有 PDF
    all_search_dirs = list(local_search_dirs or []) + [out_base_dir, "."]
    local_found = find_local_pdf_candidate(pn_x, all_search_dirs)
    if local_found:
        if os.path.abspath(local_found) != os.path.abspath(main_pdf_path):
            shutil.copy2(local_found, main_pdf_path)
        links_info["download_status"] = "found_local"
        links_info["main_pdf"] = main_pdf_path

    # 2. 本地不存在且允许下载时，尝试在线获取
    if not links_info["main_pdf"] and allow_download:
        if not doi:
            doi = resolve_doi_from_citation(citation_text)
            links_info["doi"] = doi
            if doi:
                links_info["doi_url"] = f"https://doi.org/{doi}"
                
        if doi:
            oa_pdf_url = fetch_open_access_pdf_url(doi)
            if oa_pdf_url:
                links_info["download_url"] = oa_pdf_url
                if _download_pdf_stream(oa_pdf_url, main_pdf_path) and verify_pdf_validity(main_pdf_path):
                    links_info["download_status"] = "downloaded_oa"
                    links_info["main_pdf"] = main_pdf_path

    # 3. 复制局部视觉裁切图到 {Pn-x} 目录
    src_crop = claim_item.get("visual_crop_path")
    dest_crop = os.path.join(pn_x_dir, f"{pn_x}_claim_visual.png")
    if src_crop and os.path.exists(src_crop):
        if os.path.abspath(src_crop) != os.path.abspath(dest_crop):
            shutil.copy2(src_crop, dest_crop)
        claim_item["visual_crop_path"] = dest_crop

    # 4. 保存元数据 JSON
    meta_json_path = os.path.join(pn_x_dir, f"{pn_x}_meta.json")
    meta_data = {
        **claim_item,
        **links_info,
        "organized_dir": pn_x_dir
    }
    with open(meta_json_path, "w", encoding="utf-8") as f:
        json.dump(meta_data, f, ensure_ascii=False, indent=2)

    return meta_data


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 literature_downloader.py <claim_json> <out_base_dir>")
        sys.exit(1)
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        c_item = json.load(f)
    res = process_literature_for_claim(c_item, sys.argv[2])
    print(json.dumps(res, ensure_ascii=False, indent=2))
