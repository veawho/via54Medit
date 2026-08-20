import os
#!/usr/bin/env python3
"""
tma_cascade_download.py — TMA 文献多级 OA 级联下载器

对 89 个引用中缺 PDF 的引用, 按级联顺序尝试:
  1) 已知 DOI:   OpenAlex OA -> Unpaywall OA -> Europe PMC OA -> NCBI PMC OA -> doi.org(browser UA)
  2) 无 DOI:     CrossRef 文献查询定位 DOI -> 同上 OA 级联
下载后校验 (%PDF 魔数 + 大小 + PyMuPDF 可打开)。

用法:
  python tma_cascade_download.py [--limit N] [--only S23_6,S24_1] [--sleep S]
输出: _2_pdfs/Pn-{Sx_y}.pdf + _download_cascade_report.json
"""
import json, os, re, sys, time, urllib.request, urllib.parse

T = os.environ.get('TMA_PROJECT') or r'C:\\Users\\via54\\Desktop\\TMA_test'
REF_JSON = os.path.join(T, '_references_FINAL.json')
DOI_MAP = os.path.join(T, '_doi_map_full.json')
OUT = os.path.join(T, '_2_pdfs')
LOG = os.path.join(T, '_download_cascade_report.json')

UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'}


def fetch(url, timeout=45, headers=None):
    h = dict(UA)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_json(url, timeout=30):
    return json.loads(fetch(url, timeout).decode('utf-8', 'replace'))


def extract_doi(text):
    m = re.search(r'10\.\d{4,9}/[^\s,;。]+', text or '')
    return m.group(0).rstrip('.,;') if m else None


def crossref_lookup(citation):
    q = urllib.parse.quote(citation)
    try:
        d = fetch_json('https://api.crossref.org/works?query.bibliographic=' + q + '&rows=4')
        items = d.get('message', {}).get('items', [])
        out = []
        for it in items:
            out.append({
                'doi': it.get('DOI'),
                'title': (it.get('title') or [''])[0][:120],
                'year': (it.get('issued') or {}).get('date-parts', [[None]])[0][0],
                'journal': (it.get('container-title') or [''])[0][:60],
            })
        return out
    except Exception as e:
        return [{'error': str(e)}]


def openalex_oa(doi):
    try:
        d = fetch_json('https://api.openalex.org/works/doi:' + urllib.parse.quote(doi))
        oa = d.get('best_oa_location') or {}
        return oa.get('pdf_url') or oa.get('landing_page_url')
    except Exception:
        return None


def unpaywall_oa(doi):
    try:
        d = fetch_json('https://api.unpaywall.org/v2/' + urllib.parse.quote(doi) + '?email=via54.tma.downloader@gmail.com')
        loc = d.get('best_oa_location') or {}
        return loc.get('url_for_pdf') or loc.get('url')
    except Exception:
        return None


def epmc_pdf_candidates(doi):
    try:
        q = urllib.parse.quote('DOI:"' + doi + '"')
        d = fetch_json('https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=' + q + '&resultType=core&format=json&pageSize=3')
        res = d.get('resultList', {}).get('result', [])
        for r in res:
            pmcid = r.get('pmcid')
            urls = []
            for u in (r.get('fullTextUrlList') or {}).get('fullTextUrl', []) or []:
                if u.get('documentStyle') == 'pdf' and u.get('availability') in ('Open access', 'Free'):
                    urls.append(u.get('url'))
            if pmcid:
                urls.append('https://europepmc.org/articles/' + pmcid + '/pdf/main.pdf')
                urls.append('https://www.ebi.ac.uk/europepmc/webservices/rest/' + pmcid + '/fullTextPDF')
            if urls:
                return pmcid, urls
    except Exception:
        pass
    return None, []


def ncbi_pmc_candidates(doi):
    try:
        d = fetch_json('https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids=' + urllib.parse.quote(doi) + '&format=json')
        for rec in d.get('records', []):
            pmcid = rec.get('pmcid')
            if pmcid:
                return pmcid, [
                    'https://www.ncbi.nlm.nih.gov/pmc/articles/' + pmcid + '/pdf/',
                    'https://pmc.ncbi.nlm.nih.gov/articles/' + pmcid + '/pdf/',
                ]
    except Exception:
        pass
    return None, []


def download_pdf(url, out_path, timeout=90, referer=None):
    headers = {'Referer': referer} if referer else None
    data = fetch(url, timeout, headers)
    if data[:4] != b'%PDF':
        raise RuntimeError('not pdf: %r' % data[:40])
    if len(data) < 5000:
        raise RuntimeError('too small: %db' % len(data))
    with open(out_path, 'wb') as f:
        f.write(data)
    return len(data)


def verify_pdf(path):
    try:
        import fitz
        doc = fitz.open(path)
        n = len(doc)
        head = doc[0].get_text()[:150].replace('\n', ' ') if n else ''
        doc.close()
        return {'ok': n > 0, 'pages': n, 'head': head}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def try_urls(urls, out_path, ref, src_label, attempts):
    for u in urls:
        if not u:
            continue
        try:
            size = download_pdf(u, out_path)
            v = verify_pdf(out_path)
            if v['ok']:
                attempts.append((src_label, u[:90], True, size, v['pages']))
                return {'source': src_label, 'url': u, 'size': size, 'pages': v['pages'], 'head': v['head'][:100]}
            else:
                attempts.append((src_label, u[:90], False, 0, 'verify: ' + str(v)))
        except Exception as e:
            attempts.append((src_label, u[:90], False, 0, str(e)[:80]))
    return None


def process_ref(ref_id, citation, doi_map_info, out_dir, sleep_s):
    out_path = os.path.join(out_dir, ref_id + '.pdf')
    if os.path.exists(out_path) and os.path.getsize(out_path) > 5000:
        v = verify_pdf(out_path)
        if v['ok']:
            return {'ref': ref_id, 'status': 'exists', 'pages': v['pages']}
    log = {'ref': ref_id, 'citation': citation[:80]}
    attempts = []

    known_doi = (doi_map_info or {}).get('doi')
    if not known_doi:
        known_doi = extract_doi(citation)
    log['known_doi'] = known_doi

    dois_to_try = []
    if known_doi:
        dois_to_try.append(known_doi)
    cr = crossref_lookup(citation)
    for it in cr:
        if it.get('doi') and it['doi'] not in dois_to_try:
            dois_to_try.append(it['doi'])
    log['crossref_top'] = [{'doi': it.get('doi'), 'title': it.get('title'), 'year': it.get('year')} for it in cr[:2]]

    for doi in dois_to_try:
        oa_url = openalex_oa(doi)
        if oa_url:
            r = try_urls([oa_url], out_path, ref_id, 'openalex', attempts)
            if r:
                r.update({'ref': ref_id, 'status': 'ok', 'doi': doi})
                log.update(r)
                log['attempts'] = attempts
                return log
        up_url = unpaywall_oa(doi)
        if up_url:
            r = try_urls([up_url], out_path, ref_id, 'unpaywall', attempts)
            if r:
                r.update({'ref': ref_id, 'status': 'ok', 'doi': doi})
                log.update(r)
                log['attempts'] = attempts
                return log
        pmcid, ep_urls = epmc_pdf_candidates(doi)
        if ep_urls:
            r = try_urls(ep_urls, out_path, ref_id, 'epmc', attempts)
            if r:
                r.update({'ref': ref_id, 'status': 'ok', 'doi': doi, 'pmcid': pmcid})
                log.update(r)
                log['attempts'] = attempts
                return log
        pmcid2, ncbi_urls = ncbi_pmc_candidates(doi)
        if ncbi_urls:
            r = try_urls(ncbi_urls, out_path, ref_id, 'ncbi_pmc', attempts)
            if r:
                r.update({'ref': ref_id, 'status': 'ok', 'doi': doi, 'pmcid': pmcid2})
                log.update(r)
                log['attempts'] = attempts
                return log
        r = try_urls(['https://doi.org/' + doi], out_path, ref_id, 'doi_org', attempts)
        if r:
            r.update({'ref': ref_id, 'status': 'ok', 'doi': doi})
            log.update(r)
            log['attempts'] = attempts
            return log

    log['status'] = 'FAILED'
    log['attempts'] = attempts[:6]
    log['suggested'] = list(dict.fromkeys(['https://doi.org/' + d for d in dois_to_try]))[:3]
    return log


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    limit = None
    only = None
    sleep_s = 0.8
    if '--limit' in sys.argv:
        limit = int(sys.argv[sys.argv.index('--limit') + 1])
    if '--only' in sys.argv:
        only = sys.argv[sys.argv.index('--only') + 1].split(',')
    if '--sleep' in sys.argv:
        sleep_s = float(sys.argv[sys.argv.index('--sleep') + 1])

    refs = json.load(open(REF_JSON, encoding='utf-8'))
    doi_map = json.load(open(DOI_MAP, encoding='utf-8'))
    os.makedirs(OUT, exist_ok=True)

    todo = []
    for ref_id, citation in sorted(refs.items()):
        p = os.path.join(OUT, ref_id + '.pdf')
        if os.path.exists(p) and os.path.getsize(p) > 5000:
            continue
        todo.append((ref_id, citation))
    if only:
        todo = [t for t in todo if t[0] in only]
    if limit:
        todo = todo[:limit]

    print('待下载:', len(todo), flush=True)
    results = []
    for i, (ref_id, citation) in enumerate(todo):
        print('[%d/%d] %s: %s...' % (i + 1, len(todo), ref_id, citation[:40]), flush=True)
        r = process_ref(ref_id, citation, doi_map.get(ref_id, {}), OUT, sleep_s)
        st = r.get('status')
        if st == 'ok':
            print('   -> OK %s (%d pages, %s)' % (r.get('source'), r.get('pages', 0), r.get('url', '')[:80]), flush=True)
        else:
            print('   -> %s' % st, flush=True)
        results.append(r)
        time.sleep(sleep_s)

    with open(LOG, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    n_ok = sum(1 for r in results if r.get('status') == 'ok')
    print('\n成功 %d/%d -> %s' % (n_ok, len(results), OUT), flush=True)


if __name__ == '__main__':
    main()

