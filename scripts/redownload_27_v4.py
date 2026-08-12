#!/usr/bin/env python3.11
"""
redownload_27_v4.py — 严格 L0 verify 验证的 PDF 重下 v4

输入: 24 MISMATCH + 3 FS_NO_MD5 = 27 个 Pn-x (from /tmp/pdf_feishu_alignment_final.json)
策略:
  1. Europe PMC (author + year + journal)
  2. Crossref (精确 title 验证)
  3. Sci-Hub 多 mirror (bban.top, sci-hub.al, sci-hub.wf, sci-hub.shop)
  4. 5 维特征 verify: 第一作者 + 年份 + 期刊 + vol(issue) + pages (至少 4/5)
失败/找不到的: 列到 _redownload_27_v4_failed.json
"""
import os, sys, json, re, time, shutil, hashlib, urllib.parse
import urllib.request, urllib.error
import socket, threading
socket.setdefaulttimeout(15)

import warnings
warnings.filterwarnings('ignore')

TMA = '/Users/david/Desktop/TMA_文献整理'
SRC = f'{TMA}/_2_pdfs'
LOG = f'{TMA}/_3_highlight_v10_glm/_redownload_27_v4_log.json'
FAILED = f'{TMA}/_3_highlight_v10_glm/_redownload_27_v4_failed.json'

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
UA_CROSSREF = "via54Medit/1.0 (mailto:via54@MiniMax.dev)"

# Sci-Hub mirrors
SH_MIRRORS = [
    'https://sci.bban.top',
    'https://sci-hub.al',
    'https://sci-hub.shop',
    'https://www.sci-hub.wf',
]


def http_get(url, timeout=20, ua=UA):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except Exception:
        return 0, b""


def parse_citation_5d(cite):
    """5 维特征抽取"""
    f = {'surname': None, 'year': None, 'journal': None, 'vol': None,
         'issue': None, 'pages': None, 'doi': None, 'is_chinese': False,
         'title_words': []}
    if re.search(r'[\u4e00-\u9fff]', cite):
        f['is_chinese'] = True
    # DOI
    m = re.search(r'(10\.\d{4,9}/[^\s,]+)', cite)
    if m: f['doi'] = m.group(1).rstrip('.,;')
    # Year
    m = re.search(r'\b(19|20)\d{2}\b', cite)
    if m: f['year'] = m.group(0)
    # Surname (英文) - 第一个大写词
    m = re.match(r'^\s*([A-Z][a-zA-Z\-]+)', cite)
    if m: f['surname'] = m.group(1)
    # vol(issue):pages
    m = re.search(r'(\d+)\s*\((\d+)\)\s*:\s*([\d\-]+)', cite)
    if m:
        f['vol'] = m.group(1)
        f['issue'] = m.group(2)
        f['pages'] = m.group(3)
    # Journal
    if f['year']:
        m = re.search(r'\.\s*([A-Z][a-zA-Z\.\s]{2,30}?)\.?\s*' + f['year'], cite)
        if m:
            f['journal'] = m.group(1).strip().rstrip('.')
    # 英文 title words (>=5 字符, 不是 author, 不是 journal)
    f['title_words'] = [w for w in re.findall(r'[A-Za-z]{5,}', cite) if w.lower() not in (f['surname'] or '').lower()]
    return f


def europe_pmc_search(f):
    """Europe PMC 搜"""
    if not f['surname'] or not f['year']:
        return None
    q = f'AUTH:"{f["surname"]}" AND (FIRST_PDATE:[{f["year"]}-01-01 TO {f["year"]}-12-31])'
    if f['journal']:
        q += f' AND JOURNAL:"{f["journal"]}"'
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={urllib.parse.quote(q)}&format=json&resultType=core&pageSize=10"
    result_box = [None]
    def run():
        try:
            code, body = http_get(url, timeout=10)
            if code != 200: return
            data = json.loads(body)
            items = data.get('resultList', {}).get('result', [])
            # 选匹配 vol 的
            for it in items:
                if f['vol']:
                    ji = it.get('journalInfo', {})
                    if ji.get('volume') != f['vol']: continue
                doi = it.get('doi', '')
                if doi and doi.startswith('10.'):
                    result_box[0] = {'doi': doi, 'pmcid': it.get('pmcid'),
                                      'title': it.get('title', '')}
                    return
            # 没匹配到 vol, 用第一个有 DOI 的
            for it in items:
                doi = it.get('doi', '')
                if doi and doi.startswith('10.'):
                    result_box[0] = {'doi': doi, 'pmcid': it.get('pmcid'),
                                      'title': it.get('title', '')}
                    return
        except Exception:
            pass
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=12)
    return result_box[0]


def crossref_search(f):
    """Crossref 搜"""
    if not f['surname'] or not f['year']:
        return None
    url = f"https://api.crossref.org/works?query.author={f['surname']}&query.bibliographic={f['year']}&rows=5"
    result_box = [None]
    def run():
        try:
            code, body = http_get(url, timeout=12, ua=UA_CROSSREF)
            if code != 200: return
            data = json.loads(body)
            items = data.get('message', {}).get('items', [])
            for it in items:
                if it.get('DOI'):
                    result_box[0] = {'doi': it['DOI'], 'title': ' '.join(it.get('title', []))}
                    return
        except Exception:
            pass
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=15)
    return result_box[0]


def doi_to_pdf_url(doi):
    """DOI 跳 publisher 找 PDF"""
    if not doi: return None
    code, body = http_get(f'https://doi.org/{doi}', timeout=12)
    if code != 200: return None
    text = body.decode('utf-8', errors='ignore')[:8000]
    m = re.search(r'(https?://[^\s"<>]+\.pdf)', text)
    if m: return m.group(1)
    return None


def sci_hub_resolve(doi, mirror):
    if not doi: return None
    code, body = http_get(f'{mirror}/{doi}', timeout=15)
    if code != 200: return None
    html = body.decode('utf-8', errors='ignore')[:15000]
    m = re.search(r'src=["\'](https?://[^"\']+\.pdf)["\']', html)
    if m: return m.group(1)
    m = re.search(r'(https?://[^\s"<>]*\.pdf)', html)
    if m: return m.group(1)
    m = re.search(r'location\.href\s*=\s*["\']([^"\']+\.pdf)["\']', html)
    if m: return m.group(1)
    return None


def europe_pmc_pdf(pmcid):
    """Europe PMC PDF 直链"""
    if not pmcid: return None
    return f"https://europepmc.org/articles/{pmcid}/pdf/main.pdf"


def download_pdf(url, out_path, timeout=60):
    result_box = [(False, "init")]
    def run():
        try:
            code, body = http_get(url, timeout=timeout)
            if code != 200:
                result_box[0] = (False, f"http_{code}")
                return
            if body[:4] != b"%PDF":
                result_box[0] = (False, f"not_pdf")
                return
            if len(body) < 5000:
                result_box[0] = (False, f"too_small_{len(body)}")
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


def verify_5d(pdf_path, f):
    """5 维特征验证"""
    try:
        import fitz
        d = fitz.open(pdf_path)
        if d.page_count == 0:
            d.close()
            return False, "empty"
        # 第一页 + 前 2 页文字
        text = ''.join(d[i].get_text() for i in range(min(2, d.page_count)))
        d.close()
    except Exception as e:
        return False, f"read_err: {e}"

    text_lower = text.lower()
    score = 0
    max_score = 0
    checks = []
    
    if f['surname']:
        max_score += 1
        if f['surname'].lower() in text_lower:
            score += 1
            checks.append(f"author✓{f['surname']}")
        else:
            checks.append(f"author✗{f['surname']}")
    
    if f['year']:
        max_score += 1
        if f['year'] in text:
            score += 1
            checks.append(f"year✓{f['year']}")
        else:
            checks.append(f"year✗{f['year']}")
    
    if f['journal'] and len(f['journal']) > 4:
        max_score += 1
        if f['journal'][:8].lower() in text_lower:
            score += 1
            checks.append(f"journal✓{f['journal'][:10]}")
        else:
            checks.append(f"journal✗{f['journal'][:10]}")
    
    if f['vol']:
        max_score += 1
        if f'vol {f["vol"]}' in text_lower or f'volume {f["vol"]}' in text_lower or f' {f["vol"]}(' in text or f';{f["vol"]}' in text:
            score += 1
            checks.append(f"vol✓{f['vol']}")
        else:
            checks.append(f"vol✗{f['vol']}")
    
    if f['pages']:
        max_score += 1
        page_num = f['pages'].split('-')[0]
        if page_num in text:
            score += 1
            checks.append(f"page✓{page_num}")
        else:
            checks.append(f"page✗{page_num}")
    
    # 至少 4/5 通过 (or 3/4 for 部分特征缺失的)
    min_required = min(4, max_score) if max_score >= 4 else max_score
    passed = score >= min_required
    return passed, f"{score}/{max_score} [{','.join(checks)}]"


def process_one(pn, citation):
    """重下一个 Pn-x + 5D 验证"""
    out = f'{SRC}/{pn}_main.pdf'
    f = parse_citation_5d(citation)
    
    # 1. Europe PMC
    pmc = europe_pmc_search(f)
    if pmc:
        # 试 PMCID PDF
        if pmc.get('pmcid'):
            url = europe_pmc_pdf(pmc['pmcid'])
            if url:
                ok, msg = download_pdf(url, out)
                if ok:
                    v_ok, v_msg = verify_5d(out, f)
                    if v_ok:
                        return ('europepmc', url, msg, v_msg)
                    else:
                        try: os.remove(out)
                        except: pass
        # 试 DOI redirect
        if pmc.get('doi'):
            url = doi_to_pdf_url(pmc['doi'])
            if url:
                ok, msg = download_pdf(url, out)
                if ok:
                    v_ok, v_msg = verify_5d(out, f)
                    if v_ok:
                        return ('doi_redirect', url, msg, v_msg)
                    else:
                        try: os.remove(out)
                        except: pass
    
    # 2. Crossref
    cr = crossref_search(f)
    if cr and cr.get('doi'):
        url = doi_to_pdf_url(cr['doi'])
        if url:
            ok, msg = download_pdf(url, out)
            if ok:
                v_ok, v_msg = verify_5d(out, f)
                if v_ok:
                    return ('crossref', url, msg, v_msg)
                else:
                    try: os.remove(out)
                    except: pass
    
    # 3. Sci-Hub 多 mirror
    doi = (pmc or {}).get('doi') or (cr or {}).get('doi') or f.get('doi')
    if doi:
        for mirror in SH_MIRRORS:
            url = sci_hub_resolve(doi, mirror)
            if not url: continue
            ok, msg = download_pdf(url, out)
            if not ok: continue
            v_ok, v_msg = verify_5d(out, f)
            if v_ok:
                return ('scihub', url, msg, v_msg)
            else:
                try: os.remove(out)
                except: pass
    
    return ('not_found', None, '', '')


def main():
    items = json.load(open('/tmp/pdf_feishu_alignment_final.json', encoding='utf-8'))
    # 只处理 MISMATCH + FS_NO_MD5
    to_fix = [r for r in items if r['status'] in ('MISMATCH', 'FS_NO_MD5')]
    log = []
    failed = []
    
    print(f'处理 {len(to_fix)} 个 Pn-x (MISMATCH + FS_NO_MD5)')
    print(f'{"":<60} {"飞书 MD5":<14} {"":<4} {"新MD5":<14} {"verify":<25} {"time"}')
    print('=' * 130)
    
    for i, item in enumerate(to_fix, 1):
        pn = item['pn']
        citation = item['cite']
        target_md5 = item['feishu_md5']
        src_pdf = f'{SRC}/{pn}_main.pdf'
        
        # 备份 (实体文件才备份, symlink 不需要)
        bak = f'{SRC}/{pn}_main.pdf.bak_v4_{int(time.time())}'
        if os.path.exists(src_pdf) and not os.path.islink(src_pdf):
            shutil.copy2(src_pdf, bak)
        elif os.path.islink(src_pdf):
            os.unlink(src_pdf)  # 删 symlink 让脚本可以下
        
        t0 = time.time()
        try:
            source, url, dmsg, vmsg = process_one(pn, citation)
        except Exception as e:
            source, url, dmsg, vmsg = ('error', None, str(e)[:80], '')
        
        if os.path.exists(src_pdf):
            new_md5 = hashlib.md5(open(src_pdf, 'rb').read()).hexdigest()[:12]
        else:
            new_md5 = '-'
        
        match = new_md5 == target_md5 if target_md5 else None
        result = {
            'pn_x': pn, 'citation': citation[:80], 'target_md5': target_md5,
            'source': source, 'url': url, 'dl_msg': dmsg, 'verify': vmsg,
            'new_md5': new_md5, 'match': match,
            'elapsed': round(time.time() - t0, 1),
        }
        log.append(result)
        if source == 'not_found':
            failed.append(result)
        
        status = '✅' if match else ('❌' if source == 'not_found' else '⚠️')
        print(f'[{i:2d}/{len(to_fix)}] {status} {pn:<10} {target_md5 or "-":<14} → {new_md5:<14} verify={vmsg[:30]:<30} {result["elapsed"]}s')
    
    with open(LOG, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    with open(FAILED, 'w', encoding='utf-8') as f:
        json.dump(failed, f, ensure_ascii=False, indent=2)
    
    matched = sum(1 for r in log if r['match'])
    found = sum(1 for r in log if r['source'] != 'not_found')
    verified = sum(1 for r in log if 'verified' in r.get('verify', ''))
    
    print(f'\n=== 汇总 ===')
    print(f'  找到 PDF: {found}/{len(to_fix)}')
    print(f'  通过 5D verify: {verified}/{len(to_fix)}')
    print(f'  MD5 完全匹配飞书: {matched}/{len(to_fix)}')
    print(f'  失败 (not_found): {len(failed)}')
    print(f'  Log: {LOG}')
    print(f'  Failed: {FAILED}')


if __name__ == '__main__':
    main()
