#!/usr/bin/env python3.11
"""
redownload_36_v2.py — 简化版批量重下 36 个 PDF

输入: /tmp/to_fix_36.json (Pn-x + 飞书引用)
策略:
  1. Europe PMC 搜 first author + year + journal
  2. Crossref 兜底 (精确 title)
  3. Sci-Hub 兜底 (DOI)
输出: 替换 _2_pdfs/Pn-x_main.pdf
"""
import os, sys, json, re, time, shutil, hashlib, urllib.parse
import urllib.request, urllib.error
import socket, threading
socket.setdefaulttimeout(15)

TMA = '/Users/david/Desktop/TMA_文献整理'
SRC = f'{TMA}/_2_pdfs'
LOG = f'{TMA}/_3_highlight_v10_glm/_redownload_36_v2_log.json'

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
UA_CROSSREF = "via54Medit/1.0 (mailto:via54@MiniMax.dev)"


def http_get(url, timeout=20, ua=UA):
    """通用 GET"""
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception:
        return 0, b""


def parse_citation(cite):
    """从飞书引用抽取 first author + year + journal + DOI"""
    info = {'surname': None, 'year': None, 'journal': None, 'vol': None,
            'issue': None, 'pages': None, 'doi': None, 'is_chinese': False}
    # 中文检测
    if re.search(r'[\u4e00-\u9fff]', cite):
        info['is_chinese'] = True
    # DOI
    m = re.search(r'(10\.\d{4,9}/[^\s,]+)', cite)
    if m: info['doi'] = m.group(1).rstrip('.,;')
    # Year
    m = re.search(r'\b(19|20)\d{2}\b', cite)
    if m: info['year'] = int(m.group(0))
    # Surname (英文: "Smith" 或 "Smith J")
    m = re.match(r'^\s*([A-Z][a-zA-Z\-]+)', cite)
    if m: info['surname'] = m.group(1)
    # Vol(Issue):pages
    m = re.search(r'(\d+)\s*\((\d+)\)\s*:\s*([\d\-]+)', cite)
    if m:
        info['vol'] = int(m.group(1))
        info['issue'] = int(m.group(2))
        info['pages'] = m.group(3)
    # Journal (英文缩写, 在 "X. YYYY" 模式里)
    m = re.search(r'\.\s*([A-Z][a-zA-Z\.\s]{2,30}?)\.?\s*' + str(info['year'] or 'XXXX'), cite)
    if m:
        info['journal'] = m.group(1).strip().rstrip('.')
    return info


def europe_pmc_search(cite_info):
    """Europe PMC 搜 (first author + year + journal)"""
    if not cite_info['surname'] or not cite_info['year']:
        return None
    surname = cite_info['surname']
    year = cite_info['year']
    journal = cite_info['journal'] or ''
    
    # 1. author + year
    q = f'AUTH:"{surname}" AND (FIRST_PDATE:[{year}-01-01 TO {year}-12-31])'
    if journal:
        q += f' AND JOURNAL:"{journal}"'
    
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={urllib.parse.quote(q)}&format=json&resultType=core&pageSize=10"
    
    result_box = [None]
    def run():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            items = data.get('resultList', {}).get('result', [])
            # 选有 DOI 的
            for it in items:
                doi = it.get('doi')
                pmcid = it.get('pmcid')
                title = it.get('title', '')
                if doi and doi.startswith('10.'):
                    result_box[0] = {'doi': doi, 'pmcid': pmcid, 'title': title,
                                      'pdf_url': it.get('fullTextUrlList', {}).get('fullTextUrl', [])}
                    return
        except Exception:
            pass
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=12)
    return result_box[0]


def get_pdf_url_from_europe_pmc(pmcid):
    """Europe PMC PDF 直链"""
    if not pmcid: return None
    return f"https://europepmc.org/articles/{pmcid}/pdf/main.pdf"


def doi_redirect_pdf(doi):
    """DOI 跳 publisher 找 PDF 链接"""
    if not doi: return None
    result_box = [None]
    def run():
        try:
            url = f'https://doi.org/{doi}'
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
            with urllib.request.urlopen(req, timeout=12) as r:
                final = r.geturl()
                body = r.read().decode('utf-8', errors='ignore')[:8000]
            # 找 PDF link
            m = re.search(r'(https?://[^\s"<>]+\.pdf)', body)
            if m: result_box[0] = m.group(1); return
            # 找 PubMed 风格的 PDF
            if 'ncbi.nlm.nih.gov' in final:
                result_box[0] = f'https://www.ncbi.nlm.nih.gov/pmc/articles/{final.split("/")[-2]}/pdf/'
                return
        except Exception:
            pass
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=15)
    return result_box[0]


def sci_hub_resolve(doi, mirror='https://sci-hub.al'):
    """Sci-Hub 找 PDF 链接"""
    if not doi: return None
    result_box = [None]
    def run():
        try:
            url = f'{mirror}/{doi}'
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
            with urllib.request.urlopen(req, timeout=12) as r:
                html = r.read().decode('utf-8', errors='ignore')[:10000]
            m = re.search(r'src="(https?://[^"]+\.pdf)"', html)
            if m: result_box[0] = m.group(1); return
            m = re.search(r"location\.href\s*=\s*['\"]([^'\"]+)['\"]", html)
            if m and m.group(1).endswith('.pdf'): result_box[0] = m.group(1); return
            m = re.search(r'(https?://[^\s"<>]+\.pdf)', html)
            if m: result_box[0] = m.group(1); return
        except Exception:
            pass
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=15)
    return result_box[0]


def download_pdf(url, out_path, timeout=60):
    """下载 PDF, 验证 magic bytes"""
    result_box = [(False, "init")]
    def run():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
            if body[:4] != b"%PDF":
                result_box[0] = (False, f"not_pdf (got {body[:10]!r})")
                return
            if len(body) < 5000:
                result_box[0] = (False, f"too_small ({len(body)}B)")
                return
            with open(out_path, 'wb') as f:
                f.write(body)
            result_box[0] = (True, f"{len(body)}B")
        except Exception as e:
            result_box[0] = (False, str(e)[:60])
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=timeout+5)
    return result_box[0]


def process_one(pn, citation):
    """重下一个 Pn-x"""
    out = f'{SRC}/{pn}_main.pdf'
    info = parse_citation(citation)
    
    # 1. Europe PMC
    pmc = europe_pmc_search(info)
    if pmc and pmc.get('pmcid'):
        url = get_pdf_url_from_europe_pmc(pmc['pmcid'])
        if url:
            ok, msg = download_pdf(url, out)
            if ok: return ('europepmc', url, msg)
    if pmc and pmc.get('doi'):
        # 2. DOI redirect
        url = doi_redirect_pdf(pmc['doi'])
        if url:
            ok, msg = download_pdf(url, out)
            if ok: return ('doi_redirect', url, msg)
        # 3. Sci-Hub
        url = sci_hub_resolve(pmc['doi'])
        if url:
            ok, msg = download_pdf(url, out)
            if ok: return ('scihub', url, msg)
    
    # 如果飞书引用有 DOI 直接用
    if info['doi']:
        url = doi_redirect_pdf(info['doi'])
        if url:
            ok, msg = download_pdf(url, out)
            if ok: return ('doi_direct', url, msg)
        url = sci_hub_resolve(info['doi'])
        if url:
            ok, msg = download_pdf(url, out)
            if ok: return ('scihub_doi', url, msg)
    
    return ('not_found', None, '')


def main():
    items = json.load(open('/tmp/to_fix_36.json', encoding='utf-8'))
    log = []
    
    for i, item in enumerate(items, 1):
        pn = item['pn_x']
        cite = item['feishu_cite']
        target_md5 = item['feishu_md5']
        src_pdf = f'{SRC}/{pn}_main.pdf'
        
        # 备份
        bak = f'{SRC}/{pn}_main.pdf.bak_v2_{int(time.time())}'
        if os.path.exists(src_pdf):
            shutil.copy2(src_pdf, bak)
        
        t0 = time.time()
        try:
            source, url, msg = process_one(pn, cite)
        except Exception as e:
            source, url, msg = ('error', None, str(e)[:80])
        
        if os.path.exists(src_pdf):
            new_md5 = hashlib.md5(open(src_pdf, 'rb').read()).hexdigest()[:12]
        else:
            new_md5 = '-'
        
        result = {
            'pn_x': pn, 'citation': cite[:80], 'target_md5': target_md5,
            'source': source, 'url': url, 'msg': msg,
            'new_md5': new_md5, 'match': new_md5 == target_md5 if target_md5 else None,
            'elapsed': round(time.time() - t0, 1),
        }
        log.append(result)
        status = '✅' if result['match'] else '❌' if source == 'not_found' else '⚠️'
        print(f'[{i:2d}/{len(items)}] {status} {pn} | {source:12s} {new_md5} (target={target_md5 or "-"}) {result["elapsed"]}s')
    
    with open(LOG, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    
    matched = sum(1 for r in log if r['match'])
    found = sum(1 for r in log if r['source'] != 'not_found')
    print(f'\n=== 汇总 ===')
    print(f'  找到 PDF: {found}/{len(items)}')
    print(f'  MD5 跟飞书完全一致: {matched}/{len(items)}')
    print(f'  Log: {LOG}')


if __name__ == '__main__':
    main()
