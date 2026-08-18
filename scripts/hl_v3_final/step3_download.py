#!/usr/bin/env python3
"""Step 3: 文献引用字段 → 查找正确 PDF 链接并下载
流程: 引用文本 → (直接DOI | CrossRef查询 | Europe PMC查询) → 下载 PDF → 校验
用法: python3 step3_download.py <refs.json> <out_dir> [--pn P23-8] [--limit 3]
依赖: requests (pip install requests); 校验: PyMuPDF"""
import sys, os, re, json, time, hashlib, urllib.request, urllib.parse

_UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'}

def fetch(url, timeout=60, referer=None):
    h = dict(_UA)
    if referer:
        h['Referer'] = referer
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()

def fetch_json(url, timeout=30):
    return json.loads(fetch(url, timeout).decode('utf-8', 'replace'))

def extract_doi(text):
    m = re.search(r'10\.\d{4,9}/[^\s,;。]+', text)
    return m.group(0).rstrip('.,;') if m else None

def crossref_lookup(citation, timeout=30):
    """CrossRef bibliographic 查询 → doi"""
    q = urllib.parse.quote(citation)
    url = f'https://api.crossref.org/works?query.bibliographic={q}&rows=3'
    try:
        d = fetch_json(url, timeout)
        items = d.get('message', {}).get('items', [])
        out = []
        for it in items:
            title = (it.get('title') or [''])[0]
            year = None
            for k in ('published-print', 'published-online', 'issued'):
                if it.get(k) and it[k].get('date-parts'):
                    year = it[k]['date-parts'][0][0]
                    break
            out.append({'doi': it.get('DOI'), 'title': title[:120], 'year': year, 'journal': (it.get('container-title') or [''])[0][:60]})
        return out
    except Exception as e:
        return [{'error': str(e)}]

def europepmc_lookup(citation, timeout=30):
    """Europe PMC 查询 → 记录(含全文 PDF 链接)"""
    q = urllib.parse.quote(citation)
    url = f'https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={q}&format=json&pageSize=3'
    try:
        d = fetch_json(url, timeout)
        res = d.get('resultList', {}).get('result', [])
        out = []
        for r in res:
            pdf = None
            ft = r.get('fullTextUrlList', {}).get('fullTextUrl', [])
            for u in ft:
                if u.get('documentStyle') == 'pdf' and u.get('availability') in ('Open access', 'Free'):
                    pdf = u.get('url'); break
            out.append({'pmcid': r.get('pmcid'), 'pmid': r.get('pmid'),
                        'title': (r.get('title') or '')[:120], 'year': r.get('pubYear'),
                        'journal': (r.get('journalInfo', {}).get('journal', {}) or {}).get('title', '')[:60],
                        'pdf': pdf})
        return out
    except Exception as e:
        return [{'error': str(e)}]

def openalex_oa(doi, timeout=30):
    """OpenAlex best_oa_location → pdf_url"""
    try:
        d = fetch_json(f'https://api.openalex.org/works/doi:{urllib.parse.quote(doi)}', timeout)
        oa = d.get('best_oa_location') or {}
        return oa.get('pdf_url') or oa.get('landing_page_url') or None
    except Exception:
        return None

def unpaywall_oa(doi, email='tma.ref.downloader@example.org', timeout=30):
    try:
        d = fetch_json(f'https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={email}', timeout)
        loc = d.get('best_oa_location') or {}
        return loc.get('url_for_pdf') or None
    except Exception:
        return None

def download_pdf(url, out_path, timeout=90, referer=None):
    data = fetch(url, timeout, referer)
    if data[:4] != b'%PDF':
        raise RuntimeError(f'not a pdf ({data[:40]!r})')
    with open(out_path, 'wb') as f:
        f.write(data)
    return out_path

def verify_pdf(path):
    """校验: 可打开 + 页数>0 + 首页文本"""
    try:
        import fitz
        doc = fitz.open(path)
        n = len(doc)
        head = doc[0].get_text()[:200].replace('\n', ' ') if n else ''
        doc.close()
        return {'ok': n > 0, 'pages': n, 'head': head}
    except Exception as e:
        return {'ok': False, 'error': str(e)}

def process_ref(ref, out_dir):
    """单个引用: 查找并下载"""
    pn = f"P{ref['slide']}-{ref['num']}"
    cit = ref['text']
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f'{pn}.pdf')
    # 1. 直接 DOI(带浏览器 UA)
    doi = extract_doi(cit)
    log = {'pn': pn, 'citation': cit[:80], 'direct_doi': doi}
    if doi:
        try:
            download_pdf(f'https://doi.org/{doi}', out_path)
            v = verify_pdf(out_path)
            if v['ok']:
                log.update({'source': 'doi_redirect', 'doi': doi, 'pages': v['pages'], 'head': v['head'][:80]})
                return log
            os.remove(out_path)
        except Exception as e:
            log['doi_err'] = str(e)[:60]
    # 2. CrossRef 定位 DOI → OpenAlex/Unpaywall OA PDF
    cr = crossref_lookup(cit)
    log['crossref'] = cr
    for it in cr:
        d = it.get('doi')
        if not d:
            continue
        for src_name, oa_url in (('openalex', openalex_oa(d)), ('unpaywall', unpaywall_oa(d))):
            if not oa_url:
                continue
            try:
                download_pdf(oa_url, out_path)
                v = verify_pdf(out_path)
                if v['ok']:
                    log.update({'source': f'oa_{src_name}', 'doi': d, 'title': it.get('title', '')[:60],
                                'oa_url': oa_url[:90], 'pages': v['pages'], 'head': v['head'][:80]})
                    return log
                os.remove(out_path)
            except Exception as e:
                log[f'{src_name}_err'] = str(e)[:60]
        # 3. CrossRef DOI 直下(带 UA)
        try:
            download_pdf(f'https://doi.org/{d}', out_path)
            v = verify_pdf(out_path)
            if v['ok']:
                log.update({'source': 'crossref_doi', 'doi': d, 'title': it.get('title', '')[:60],
                            'pages': v['pages'], 'head': v['head'][:80]})
                return log
            os.remove(out_path)
        except Exception as e:
            log['crossref_dl_err'] = str(e)[:60]
    # 4. Europe PMC OA
    ep = europepmc_lookup(cit)
    log['europepmc'] = ep
    for r in ep:
        if r.get('pdf'):
            try:
                download_pdf(r['pdf'], out_path)
                v = verify_pdf(out_path)
                if v['ok']:
                    log.update({'source': 'europepmc_oa', 'pmcid': r['pmcid'], 'title': r['title'][:60],
                                'pages': v['pages'], 'head': v['head'][:80]})
                    return log
                os.remove(out_path)
            except Exception:
                continue
    log['status'] = 'FAILED'
    log['manual_download_candidates'] = []
    for it in cr:
        d = it.get('doi')
        if d:
            log['manual_download_candidates'].append(f'https://doi.org/{d}')
            for fn, u in (('openalex', openalex_oa(d)), ('unpaywall', unpaywall_oa(d))):
                if u:
                    log['manual_download_candidates'].append(f'[{fn}] {u}')
    log['manual_download_candidates'] = list(dict.fromkeys(log['manual_download_candidates']))[:5]
    return log

def main():
    if len(sys.argv) < 3:
        print('usage: step3_download.py <refs.json> <out_dir> [--pn Pn-x] [--limit N]')
        sys.exit(1)
    refs = json.load(open(sys.argv[1], encoding='utf-8'))
    out_dir = sys.argv[2]
    only_pn = None
    limit = None
    if '--pn' in sys.argv:
        only_pn = sys.argv[sys.argv.index('--pn') + 1]
    if '--limit' in sys.argv:
        limit = int(sys.argv[sys.argv.index('--limit') + 1])
    if only_pn:
        refs = [r for r in refs if f"P{r['slide']}-{r['num']}" == only_pn]
    if limit:
        refs = refs[:limit]
    results = []
    for i, r in enumerate(refs):
        print(f'[{i+1}/{len(refs)}] P{r["slide"]}-{r["num"]}: {r["text"][:50]}...')
        res = process_ref(r, out_dir)
        print('   ->', res.get('source', res.get('status', '?')), res.get('pages', ''))
        results.append(res)
        time.sleep(1)
    json.dump(results, open(os.path.join(out_dir, '_download_report.json'), 'w'), ensure_ascii=False, indent=2)
    n_ok = sum(1 for r in results if r.get('source'))
    print(f'\n成功 {n_ok}/{len(results)} → {out_dir}')

if __name__ == '__main__':
    main()
