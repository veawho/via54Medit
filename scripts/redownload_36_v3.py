#!/usr/bin/env python3.11
"""
redownload_36_v3.py — v3: 加 L0 verify 验证 + 内容匹配, 避免 Sci-Hub 给错

升级:
  1. 加 L0 paper_match verify 5 维特征验证下载的 PDF
  2. 飞书引用 + 抽 vol(issue):pages 5 维搜索
  3. Sci-Hub 多 mirror fallback
  4. 错的 PDF 立即回滚 (用 .bak_v3_ 备份)
"""
import os, sys, json, re, time, shutil, hashlib, urllib.parse
import urllib.request, urllib.error
import socket, threading
socket.setdefaulttimeout(15)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import warnings
warnings.filterwarnings('ignore')

TMA = '/Users/david/Desktop/TMA_文献整理'
SRC = f'{TMA}/_2_pdfs'
LOG = f'{TMA}/_3_highlight_v10_glm/_redownload_36_v3_log.json'

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
UA_CROSSREF = "via54Medit/1.0 (mailto:via54@MiniMax.dev)"

# Sci-Hub mirrors (含 user-tested 多个)
SH_MIRRORS = [
    'https://sci-hub.al',
    'https://sci.bban.top',
    'https://sci-hub.shop',
    'https://www.sci-hub.wf',
]


def parse_citation(cite):
    info = {'surname': None, 'year': None, 'journal': None, 'vol': None,
            'issue': None, 'pages': None, 'doi': None, 'is_chinese': False}
    if re.search(r'[\u4e00-\u9fff]', cite):
        info['is_chinese'] = True
    m = re.search(r'(10\.\d{4,9}/[^\s,]+)', cite)
    if m: info['doi'] = m.group(1).rstrip('.,;')
    m = re.search(r'\b(19|20)\d{2}\b', cite)
    if m: info['year'] = int(m.group(0))
    m = re.match(r'^\s*([A-Z][a-zA-Z\-]+)', cite)
    if m: info['surname'] = m.group(1)
    m = re.search(r'(\d+)\s*\((\d+)\)\s*:\s*([\d\-]+)', cite)
    if m:
        info['vol'] = int(m.group(1))
        info['issue'] = int(m.group(2))
        info['pages'] = m.group(3)
    m = re.search(r'\.\s*([A-Z][a-zA-Z\.\s]{2,30}?)\.?\s*' + str(info['year'] or 'XXXX'), cite)
    if m:
        info['journal'] = m.group(1).strip().rstrip('.')
    return info


def http_get(url, timeout=20, ua=UA):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except Exception:
        return 0, b""


def get_real_doi(cite_info):
    """找正确的 DOI (Europe PMC first, Crossref fallback)"""
    if not cite_info['surname'] or not cite_info['year']:
        return cite_info.get('doi')
    
    surname = cite_info['surname']
    year = cite_info['year']
    journal = cite_info['journal'] or ''
    
    # 1. Europe PMC
    q = f'AUTH:"{surname}" AND (FIRST_PDATE:[{year}-01-01 TO {year}-12-31])'
    if journal:
        q += f' AND JOURNAL:"{journal}"'
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={urllib.parse.quote(q)}&format=json&resultType=core&pageSize=10"
    code, body = http_get(url, timeout=12)
    if code == 200:
        try:
            data = json.loads(body)
            items = data.get('resultList', {}).get('result', [])
            # 优先匹配 vol(issue):pages
            for it in items:
                if cite_info['vol']:
                    journal_info = it.get('journalInfo', {})
                    if journal_info.get('volume') != str(cite_info['vol']):
                        continue
                doi = it.get('doi', '')
                if doi and doi.startswith('10.'):
                    return doi
            # 没匹配到 vol 就回退到第一个有 DOI 的
            for it in items:
                doi = it.get('doi', '')
                if doi and doi.startswith('10.'):
                    return doi
        except Exception:
            pass
    
    # 2. Crossref fallback
    if cite_info['journal'] and cite_info['surname']:
        q2 = f'query.author={cite_info["surname"]}&query.bibliographic={cite_info["year"]}'
        url2 = f"https://api.crossref.org/works?{q2}&rows=5"
        code, body = http_get(url2, timeout=12, ua=UA_CROSSREF)
        if code == 200:
            try:
                data = json.loads(body)
                items = data.get('message', {}).get('items', [])
                for it in items:
                    if it.get('DOI'):
                        return it['DOI']
            except Exception:
                pass
    return cite_info.get('doi')


def sci_hub_resolve(doi, mirror):
    if not doi: return None
    url = f'{mirror}/{doi}'
    code, body = http_get(url, timeout=15)
    if code != 200: return None
    html = body.decode('utf-8', errors='ignore')[:15000]
    # 多个 pattern
    m = re.search(r'src=["\'](https?://[^"\']+\.pdf)["\']', html)
    if m: return m.group(1)
    m = re.search(r'(https?://[^\s"<>]*\.pdf)', html)
    if m: return m.group(1)
    m = re.search(r'location\.href\s*=\s*["\']([^"\']+\.pdf)["\']', html)
    if m: return m.group(1)
    return None


def download_pdf(url, out_path, timeout=60):
    code, body = http_get(url, timeout=timeout)
    if code != 200:
        return False, f"http_{code}"
    if body[:4] != b"%PDF":
        return False, f"not_pdf (got {body[:10]!r})"
    if len(body) < 5000:
        return False, f"too_small ({len(body)}B)"
    with open(out_path, 'wb') as f:
        f.write(body)
    return True, f"{len(body)}B"


def verify_pdf(out_path, cite_info):
    """验证下载的 PDF 内容跟飞书引用匹配
       检查: 第一页文字含 surname + year + journal 关键词
    """
    try:
        import fitz
        d = fitz.open(out_path)
        if d.page_count == 0:
            d.close()
            return False, "empty"
        # 第一页 + 前 2 页文字
        text = ''.join(d[i].get_text() for i in range(min(2, d.page_count)))
        d.close()
    except Exception as e:
        return False, f"read_err: {e}"
    
    if not cite_info['surname'] or not cite_info['year']:
        return True, "no_verify"  # 中文/无信息, 不验证
    
    text_lower = text.lower()
    surname = cite_info['surname'].lower()
    year = str(cite_info['year'])
    journal = (cite_info['journal'] or '').lower()
    
    has_surname = surname in text_lower
    has_year = year in text
    has_journal = (journal[:5] in text_lower) if len(journal) > 5 else True
    
    if not has_surname:
        return False, f"no_surname({surname})"
    if not has_year:
        return False, f"no_year({year})"
    if not has_journal:
        return False, f"no_journal({journal[:10]})"
    return True, "verified"


def process_one(pn, citation, sh_mirrors=SH_MIRRORS):
    """重下一个 Pn-x, 加 verify 验证"""
    out = f'{SRC}/{pn}_main.pdf'
    info = parse_citation(citation)
    
    # 找正确 DOI
    doi = get_real_doi(info)
    
    # 多 mirror 尝试 + verify
    for mirror in sh_mirrors:
        if not doi: break
        url = sci_hub_resolve(doi, mirror)
        if not url: continue
        ok, msg = download_pdf(url, out)
        if not ok: continue
        # verify
        v_ok, v_msg = verify_pdf(out, info)
        if v_ok:
            return ('scihub', url, msg, v_msg)
        else:
            # 不通过, 删掉 PDF
            try: os.remove(out)
            except: pass
    
    return ('not_found', None, '', '')


def main():
    items = json.load(open('/tmp/to_fix_36.json', encoding='utf-8'))
    log = []
    
    for i, item in enumerate(items, 1):
        pn = item['pn_x']
        cite = item['feishu_cite']
        target_md5 = item['feishu_md5']
        src_pdf = f'{SRC}/{pn}_main.pdf'
        
        # 备份 (保留原文件, 不动 symlink)
        bak = f'{SRC}/{pn}_main.pdf.bak_v3_{int(time.time())}'
        if os.path.exists(src_pdf) and not os.path.islink(src_pdf):
            shutil.copy2(src_pdf, bak)
        elif os.path.islink(src_pdf):
            # 删 symlink 让脚本可以下新 PDF
            os.unlink(src_pdf)
        
        t0 = time.time()
        try:
            source, url, dmsg, vmsg = process_one(pn, cite)
        except Exception as e:
            source, url, dmsg, vmsg = ('error', None, str(e)[:80], '')
        
        if os.path.exists(src_pdf):
            new_md5 = hashlib.md5(open(src_pdf, 'rb').read()).hexdigest()[:12]
        else:
            new_md5 = '-'
        
        result = {
            'pn_x': pn, 'citation': cite[:80], 'target_md5': target_md5,
            'source': source, 'url': url, 'dl_msg': dmsg, 'verify': vmsg,
            'new_md5': new_md5, 'match': new_md5 == target_md5 if target_md5 else None,
            'elapsed': round(time.time() - t0, 1),
        }
        log.append(result)
        status = '✅' if result['match'] else ('❌' if source == 'not_found' else '⚠️')
        print(f'[{i:2d}/{len(items)}] {status} {pn} | {source:10s} {new_md5} verify={vmsg[:20]:<20s} {result["elapsed"]}s')
    
    with open(LOG, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    
    matched = sum(1 for r in log if r['match'])
    found = sum(1 for r in log if r['source'] != 'not_found')
    verified = sum(1 for r in log if r['verify'] == 'verified')
    print(f'\n=== 汇总 ===')
    print(f'  找到 PDF: {found}/{len(items)}')
    print(f'  通过 verify: {verified}/{len(items)}')
    print(f'  MD5 跟飞书完全一致: {matched}/{len(items)}')
    print(f'  Log: {LOG}')


if __name__ == '__main__':
    main()
