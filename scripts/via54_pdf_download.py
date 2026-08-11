#!/usr/bin/env python3
"""
via54_pdf_download.py — 多策略 PDF 下载引擎 (v9.7)

5 级下载策略:
1. ❄️ 直接下载 (已知 OA 出版商: Frontiers/MDPI/PMC/BMC/PLOS)
2. 📖 PubMed → PMID → PMCID → PMC OA PDF 下载
3. 🏛️ Europe PMC → 找 PDF 全文
4. 🔍 Google Scholar → 搜索 PDF
5. 🚀 Sci-Hub (备用, 仅当用户明确允许)

用法:
    python3.11 via54_pdf_download.py <doi> <output_path> [--allow-scihub]
    python3.11 via54_pdf_download.py 10.3389/fonc.2022.906778 /tmp/test.pdf
    python3.11 via54_pdf_download.py 10.1056/NEJMoa1915745 /tmp/imb.pdf --allow-scihub
"""
import sys, os, json, subprocess, re, tempfile, time, urllib.parse
from pathlib import Path
from typing import Optional, Dict, List, Tuple


# 已知 OA 出版商 (可直接下载 PDF)
OA_PUBLISHERS = {
    "frontiersin.org": {"url_template": "https://www.frontiersin.org/journals/{journal}/articles/10.3389/{doi}/pdf", "label": "Frontiers"},
    "mdpi.com": {"url_template": "https://www.mdpi.com/{journal}/{doi}/pdf", "label": "MDPI"},
    "biomedcentral.com": {"url_template": "https://{journal}.biomedcentral.com/counter/pdf/10.1186/{doi}", "label": "BMC"},
    "plos.org": {"url_template": "https://journals.plos.org/{journal}/article/file?id=10.1371/journal.{doi}.pdf", "label": "PLOS"},
    "ncbi.nlm.nih.gov": {"url_template": "https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/main.pdf", "label": "PubMed Central"},
    "elifesciences.org": {"url_template": "https://elifesciences.org/articles/{doi}.pdf", "label": "eLife"},
    "cell.com": {"url_template": "https://www.cell.com/{journal}/pdf/S{s}{p},pdf", "label": "Cell Press"},
}


def _fetch_pubmed_meta(doi: str) -> Dict:
    """PubMed E-utilities: DOI → PMID → metadata (含 PMCID, OA 状态)"""
    # Step 1: ESearch (DOI → PMID)
    time.sleep(0.35)  # NCBI rate limit: 3 req/s
    r = subprocess.run([
        'curl', '-s', '-L', '--max-time', '15',
        f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={doi}&retmode=json'
    ], capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        return {"error": f"curl error: {r.stderr[:200]}"}
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"error": "JSON parse error"}
    
    ids = data.get('esearchresult', {}).get('idlist', [])
    if not ids:
        return {"error": "PMID not found"}
    
    pmid = ids[0]
    
    # Step 2: ESummary (PMID → PMCID + OA 状态)
    time.sleep(0.35)
    r2 = subprocess.run([
        'curl', '-s', '-L', '--max-time', '15',
        f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={pmid}&retmode=json'
    ], capture_output=True, text=True, timeout=20)
    if r2.returncode != 0:
        return {"pmid": pmid, "error": f"esummary error: {r2.stderr[:200]}"}
    try:
        data2 = json.loads(r2.stdout)
    except json.JSONDecodeError:
        return {"pmid": pmid, "error": "esummary JSON parse error"}
    
    result = data2.get('result', {}).get(pmid, {})
    pmcid = result.get('pmcid', '') or result.get('elocationid', '')
    if 'PMC' in pmcid:
        pmcid = pmcid.replace('PMC', '')
    else:
        pmcid = ''
    
    return {
        "pmid": pmid,
        "pmcid": pmcid,
        "is_oa": result.get('openaccess', 'N/A') == 'Y',
        "title": result.get('title', '')[:100],
        "source": result.get('source', ''),
        "pubdate": result.get('pubdate', ''),
        "doi": result.get('doi', ''),
    }


def _download_direct(url: str, output_path: str, timeout: int = 60, min_size: int = 10000) -> bool:
    """直接下载 PDF, 验证 PDF 头 (%PDF-)"""
    r = subprocess.run(['curl', '-s', '-L', '-o', output_path, '--max-time', str(timeout), url],
        capture_output=True, text=True, timeout=timeout + 10)
    if r.returncode == 0 and os.path.isfile(output_path):
        size = os.path.getsize(output_path)
        if size < min_size:
            return False
        # 验证 PDF 头
        with open(output_path, 'rb') as f:
            header = f.read(5)
        if header == b'%PDF-':
            return True
        # 不是 PDF, 删除
        os.remove(output_path)
    return False


def _download_via_pmc(pmcid: str, output_path: str) -> bool:
    """通过 PMC OA 服务下载 PDF"""
    for url in [
        f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid}/pdf/main.pdf",
        f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid}/pdf/",
        f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid}/pdf/nihms-{pmcid}.pdf",
    ]:
        if _download_direct(url, output_path):
            return True
    return False


def _download_via_europe_pmc(pmcid: str, output_path: str) -> bool:
    """通过 Europe PMC 下载 PDF"""
    for url in [
        f"https://europepmc.org/backend/ptpmcrender.fcgi?accid=PMC{pmcid}&blobtype=pdf",
        f"https://europepmc.org/articles/PMC{pmcid}/pdf",
    ]:
        if _download_direct(url, output_path):
            return True
    return False


def _download_via_scihub(doi: str, output_path: str) -> bool:
    """通过 Sci-Hub 下载 PDF (备用, 可能违法 + 不稳定)"""
    scihub_urls = [
        "https://sci-hub.ru",
        "https://sci-hub.st",
    ]
    user_agents = [
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]
    for base_url in scihub_urls:
        for ua in user_agents:
            try:
                # 先获取页面, 找 PDF 重定向
                url = f"{base_url}/{doi}"
                r = subprocess.run(['curl', '-s', '-L', '-o', output_path, '--max-time', '90',
                    '-H', f'User-Agent: {ua}',
                    '-H', 'Accept: application/pdf,*/*',
                    url],
                    capture_output=True, text=True, timeout=100)
                if r.returncode == 0 and os.path.isfile(output_path):
                    size = os.path.getsize(output_path)
                    if size > 30000:  # 至少 30KB
                        with open(output_path, 'rb') as f:
                            header = f.read(5)
                        if header == b'%PDF-':
                            return True
                        # 如果 HTML 但包含 PDF 链接, 尝试提取
                        if header == b'<!DOC' or header == b'<html':
                            content = open(output_path, 'rb').read().decode('utf-8', errors='ignore')
                            # 找 iframe src 或 redirect
                            pdf_links = re.findall(r'(?:iframe|redirect|href|src)\s*=\s*["\']([^"\']+\.pdf)["\']', content, re.I)
                            if pdf_links:
                                for pdf_url in pdf_links:
                                    if pdf_url.startswith('/'):
                                        pdf_url = base_url + pdf_url
                                    if _download_direct(pdf_url, output_path, 60, 30000):
                                        return True
            except:
                continue
    return False


def download_pdf(doi: str, output_path: str, allow_scihub: bool = False, journal: str = "") -> Dict:
    """
    多策略 PDF 下载

    Args:
        doi: DOI (e.g., "10.3389/fonc.2022.906778")
        output_path: 输出路径
        allow_scihub: 是否允许 Sci-Hub (默认 False)
        journal: 期刊名 (可选, 用于直接下载)

    Returns:
        {"success": bool, "method": str, "size": int, "errors": [str]}
    """
    errors = []
    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 策略 1: 直接下载 (OA 出版商)
    # Frontiers 已知 OA
    if 'front' in journal.lower() or 'frontiers' in journal.lower() or 'fonc' in doi.lower():
        # 直接构造 Frontiers URL
        url = f"https://www.frontiersin.org/journals/oncology/articles/{doi}/pdf"
        if _download_direct(url, output_path):
            size = os.path.getsize(output_path)
            return {"success": True, "method": "frontiers_direct", "size": size, "errors": errors}
    
    # MDPI 已知 OA
    if 'mdpi' in journal.lower() or 'ijms' in doi.lower() or 'ijms' in journal.lower():
        url = f"https://www.mdpi.com/{doi}/pdf"
        if _download_direct(url, output_path):
            size = os.path.getsize(output_path)
            return {"success": True, "method": "mdpi_direct", "size": size, "errors": errors}

    # 策略 2: PubMed → PMCID → PMC OA
    meta = _fetch_pubmed_meta(doi)
    if "error" not in meta:
        pmcid = meta.get("pmcid", "")
        is_oa = meta.get("is_oa", False)
        
        if pmcid and is_oa:
            if _download_via_pmc(pmcid, output_path):
                size = os.path.getsize(output_path) if os.path.isfile(output_path) else 0
                return {"success": True, "method": "pmc_oa", "size": size, "errors": errors, "meta": meta}
            
            if _download_via_europe_pmc(pmcid, output_path):
                size = os.path.getsize(output_path) if os.path.isfile(output_path) else 0
                return {"success": True, "method": "europe_pmc", "size": size, "errors": errors, "meta": meta}
        
        errors.append(f"PMCID={pmcid} OA={is_oa} 下载失败")
    else:
        errors.append(f"PubMed: {meta['error']}")

    # 策略 3: 尝试 DOI 重定向 → 检查是否可访问
    url = f"https://doi.org/{doi}"
    r = subprocess.run(['curl', '-sI', '-o', '/dev/null', '-w', '%{http_code}', '-L', '--max-time', '15', url],
        capture_output=True, text=True, timeout=20)
    if r.stdout.strip() in ['200', '301', '302']:
        # 跟踪重定向拿到最终 URL
        r2 = subprocess.run(['curl', '-s', '-L', '-o', '/dev/null', '-w', '%{url_effective}', '--max-time', '15', url],
            capture_output=True, text=True, timeout=20)
        final_url = r2.stdout.strip()
        errors.append(f"DOI 200 OK 但可能是付费墙: {final_url[:80]}")
    else:
        errors.append(f"DOI 返回 {r.stdout.strip()}")

    # 策略 4: 直接猜出版商 PDF URL
    if '10.1016' in doi:
        # Elsevier
        pii = doi.replace('10.1016/', '')
        url = f"https://www.sciencedirect.com/science/article/pii/{pii}/pdf"
        if _download_direct(url, output_path):
            return {"success": True, "method": "elsevier_guess", "size": os.path.getsize(output_path), "errors": errors}
        # 备选: linkinghub
        url = f"https://linkinghub.elsevier.com/retrieve/pii/{pii}"
        if _download_direct(url, output_path):
            return {"success": True, "method": "elsevier_linkinghub", "size": os.path.getsize(output_path), "errors": errors}

    if '10.1056' in doi:
        # NEJM
        url = f"https://www.nejm.org/doi/pdf/{doi}"
        if _download_direct(url, output_path):
            return {"success": True, "method": "nejm_direct", "size": os.path.getsize(output_path), "errors": errors}

    if '10.1001' in doi:
        # JAMA
        url = f"https://jamanetwork.com/journals/jama/articlepdf/{doi.replace('10.1001/', '')}"
        if _download_direct(url, output_path):
            return {"success": True, "method": "jama_direct", "size": os.path.getsize(output_path), "errors": errors}

    # 策略 5: 尝试 Google Scholar
    try:
        gs_url = f"https://scholar.google.com/scholar?q={doi}"
        r = subprocess.run(['curl', '-s', '-L', '--max-time', '15', '-o', '/dev/null', '-w', '%{url_effective}', 
            '-H', 'User-Agent: Mozilla/5.0', gs_url],
            capture_output=True, text=True, timeout=20)
        # Google Scholar 可能有 PDF 链接
    except:
        pass

    # 策略 6: Sci-Hub (主要 fallback, 当付费墙时)
    if allow_scihub:
        if _download_via_scihub(doi, output_path):
            size = os.path.getsize(output_path) if os.path.isfile(output_path) else 0
            return {"success": True, "method": "scihub", "size": size, "errors": errors}
        errors.append("Sci-Hub 下载失败")

    return {"success": False, "method": "all_failed", "size": 0, "errors": errors, "meta": meta if "error" not in meta else None}


def download_pn_x_pdf(pn_x: str, doi: str, output_dir: str, allow_scihub: bool = False, journal: str = "") -> Dict:
    """
    为 Pn-x 下载 main PDF
    
    输出: {output_dir}/{pn_x}_main_{journal}_{doi_short}.pdf
    """
    # 生成文件名
    doi_short = doi.replace('/', '_').replace('.', '_')
    if journal:
        journal_short = journal.replace(' ', '_')[:20]
        filename = f"{pn_x}_main_{journal_short}_{doi_short}.pdf"
    else:
        filename = f"{pn_x}_main_{doi_short}.pdf"
    
    output_path = f"{output_dir}/{filename}"
    
    result = download_pdf(doi, output_path, allow_scihub, journal)
    result["filename"] = filename
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('doi', help='DOI (e.g., 10.3389/fonc.2022.906778)')
    parser.add_argument('output', help='输出路径')
    parser.add_argument('--allow-scihub', action='store_true', help='允许 Sci-Hub')
    parser.add_argument('--journal', default='', help='期刊名 (可选)')
    args = parser.parse_args()

    result = download_pdf(args.doi, args.output, args.allow_scihub, args.journal)

    print(f"=== PDF 下载结果 ===")
    print(f"  DOI: {args.doi}")
    print(f"  输出: {args.output}")
    print(f"  成功: {'✅' if result['success'] else '❌'}")
    print(f"  方法: {result['method']}")
    if result.get('size'):
        print(f"  大小: {result['size']//1024} KB")
    if result.get('errors'):
        print(f"  错误: {len(result['errors'])} 个")
        for e in result['errors'][:5]:
            print(f"    - {e[:100]}")
    if result.get('meta'):
        m = result['meta']
        print(f"  元数据: PMID={m.get('pmid')}, PMCID={m.get('pmcid')}, OA={m.get('is_oa')}")


if __name__ == "__main__":
    main()