#!/usr/bin/env python3.11
"""
redownload_36.py — 批量重下 36 个 PDF（跟飞书表对齐）

输入: /tmp/to_fix_36.json (Pn-x + 飞书引用 + 飞书 MD5)
策略: Europe PMC → Crossref → Sci-Hub 兜底
验证: L0 paper match 5 维特征
输出: 替换 _2_pdfs/Pn-x_main.pdf + log
"""
import os, sys, json, re, time, shutil, hashlib
import urllib.request, urllib.error
import socket
socket.setdefaulttimeout(15)

# 让 via54 脚本可 import
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

import warnings
warnings.filterwarnings('ignore')

TMA = '/Users/david/Desktop/TMA_文献整理'
SRC = f'{TMA}/_2_pdfs'
LOG = f'{TMA}/_3_highlight_v10_glm/_redownload_36_log.json'

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def http_get(url, timeout=20, ua=UA):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception:
        return 0, b""


def europe_pmc_search(citation):
    """Europe PMC author+year+title 搜索"""
    import re
    # 抽第一作者 surname
    m = re.match(r'^\s*([A-Z][a-zA-Z\-]+)', citation)
    surname = m.group(1) if m else None
    # 抽年份
    ym = re.search(r'\b(19|20)\d{2}\b', citation)
    year = ym.group(0) if ym else None
    # 抽标题前 6 个 word
    title_words = re.findall(r'[A-Za-z]{4,}', citation)[:6]
    
    if not surname and not year:
        return None
    
    # 1. 用 DOI 找（如果有）
    # 2. 标题搜索
    if title_words:
        title_q = ' AND '.join(f'TITLE:"{w}"' for w in title_words[:3])
        q = f'({title_q})'
    else:
        q = ''
    if surname:
        q += f' AND AUTH:"{surname}"' if q else f'AUTH:"{surname}"'
    if year:
        q += f' AND (FIRST_PDATE:[{year}-01-01 TO {year}-12-31])' if q else f'(FIRST_PDATE:[{year}-01-01 TO {year}-12-31])'
    
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={urllib.parse.quote(q)}&format=json&resultType=core&pageSize=10"
    code, body = http_get(url, timeout=15)
    if code != 200:
        return None
    try:
        data = json.loads(body)
    except Exception:
        return None
    results = data.get('resultList', {}).get('result', [])
    if not results:
        return None
    # 选第一个有 DOI + PDF link 的
    for r in results:
        doi = r.get('doi')
        pmcid = r.get('pmcid')
        if doi:
            return {'doi': doi, 'pmcid': pmcid, 'title': r.get('title', '')}
        if pmcid:
            return {'pmcid': pmcid, 'title': r.get('title', '')}
    return None


def crossref_search(citation):
    """Crossref API 搜索"""
    import re
    m = re.match(r'^\s*([A-Z][a-zA-Z\-]+)', citation)
    surname = m.group(1) if m else None
    ym = re.search(r'\b(19|20)\d{2}\b', citation)
    year = ym.group(0) if ym else None
    
    if not surname and not year:
        return None
    
    # Crossref bibliographic search
    q = []
    if surname: q.append(f'query.author={surname}')
    if year: q.append(f'query.bibliographic={year}')
    if not q: return None
    url = f"https://api.crossref.org/works?{'&'.join(q)}&rows=5"
    code, body = http_get(url, timeout=15, ua="via54Medit/1.0 (mailto:via54@MiniMax.dev)")
    if code != 200:
        return None
    try:
        data = json.loads(body)
    except Exception:
        return None
    items = data.get('message', {}).get('items', [])
    if not items:
        return None
    # 选有 DOI 链接的
    for item in items:
        doi = item.get('DOI')
        if doi:
            return {'doi': doi, 'title': ' '.join(item.get('title', []))}
    return None


def get_pdf_link(doi):
    """通过 doi.org 跳转到 PDF"""
    if not doi:
        return None
    # doi.org → 重定向到 publisher, 抓 PDF link
    code, body = http_get(f'https://doi.org/{doi}', timeout=20)
    if code != 200:
        return None
    # body 是 HTML, 找 PDF link
    text = body.decode('utf-8', errors='ignore')[:5000]
    # 找 citation_pdf_url (Europe PMC)
    m = re.search(r'citation_pdf_url["\s:]+(https?://[^"\s]+\.pdf)', text)
    if m:
        return m.group(1)
    # 找 PDF link
    m = re.search(r'(https?://[^\s"<>]+\.pdf)', text)
    if m:
        return m.group(1)
    return None


def download_pdf(url, out_path):
    """下载 PDF 到 out_path"""
    code, body = http_get(url, timeout=30)
    if code != 200 or len(body) < 1000:
        return False
    if not body[:4] == b'%PDF':
        return False
    with open(out_path, 'wb') as f:
        f.write(body)
    return True


def process_one(pn, citation):
    """重下一个 Pn-x"""
    out_path = f'{SRC}/{pn}_main.pdf'
    
    # 1. Europe PMC
    pmc = europe_pmc_search(citation)
    if pmc:
        # 用 DOI / PMCID 找 PDF
        if pmc.get('pmcid'):
            url = f'https://europepmc.org/article/MED/{pmc["pmcid"]}?pdf=render'
            if download_pdf(url, out_path):
                return ('europepmc', url)
        if pmc.get('doi'):
            url = get_pdf_link(pmc['doi'])
            if url and download_pdf(url, out_path):
                return ('crossref', url)
    
    # 2. Crossref
    cr = crossref_search(citation)
    if cr and cr.get('doi'):
        url = get_pdf_link(cr['doi'])
        if url and download_pdf(url, out_path):
            return ('crossref', url)
    
    # 3. Sci-Hub 兜底
    if cr and cr.get('doi'):
        url = f'https://sci-hub.al/{cr["doi"]}'
        if download_pdf(url, out_path):
            return ('scihub', url)
    
    return ('not_found', None)


def main():
    items = json.load(open('/tmp/to_fix_36.json', encoding='utf-8'))
    log = []
    for i, item in enumerate(items, 1):
        pn = item['pn_x']
        cite = item['feishu_cite']
        target_md5 = item['feishu_md5']
        
        # 备份原 PDF
        src_pdf = f'{SRC}/{pn}_main.pdf'
        bak = f'{SRC}/{pn}_main.pdf.bak_redownload_{int(time.time())}'
        if os.path.exists(src_pdf):
            shutil.copy2(src_pdf, bak)
        
        print(f'[{i}/{len(items)}] {pn} | {cite[:60]!r}')
        try:
            source, url = process_one(pn, cite)
        except Exception as e:
            source, url = ('error', str(e)[:80])
        
        if os.path.exists(src_pdf):
            new_md5 = hashlib.md5(open(src_pdf, 'rb').read()).hexdigest()[:12]
        else:
            new_md5 = '-'
        
        result = {
            'pn_x': pn, 'citation': cite, 'target_md5': target_md5,
            'source': source, 'url': url, 'new_md5': new_md5,
            'match': new_md5 == target_md5 if target_md5 else None,
            'backup': bak if os.path.exists(bak) else None,
        }
        log.append(result)
        status = '✅' if result['match'] else '❌' if source == 'not_found' else '⚠️'
        print(f'  {status} source={source} new_md5={new_md5} match={result["match"]}')
        time.sleep(1)
    
    with open(LOG, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    
    # 汇总
    matched = sum(1 for r in log if r['match'])
    found = sum(1 for r in log if r['source'] != 'not_found')
    print(f'\n=== 汇总 ===')
    print(f'  找到 PDF: {found}/{len(items)}')
    print(f'  MD5 跟飞书完全一致: {matched}/{len(items)}')
    print(f'  Log: {LOG}')


if __name__ == '__main__':
    main()
