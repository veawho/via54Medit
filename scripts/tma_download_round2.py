"""tma_download_round2.py — 缺失 39 引用第二轮下载: CrossRef 重解析 DOI + 内容核验

对 _missing_list.json 每个引用:
  1) CrossRef 按题录查 DOI (取与引用期刊/年份最匹配者)
  2) 用正确 DOI 跑 OA 级联 (OpenAlex/Unpaywall/EPMC/PMC/doi.org)
  3) 下载后核验: 首页必须含引用期刊关键词 + 年份 (期刊不符即放弃)
输出 _download_round2_report.json; 成功的写入 _2_pdfs
"""
import json, os, re, io, sys, time, urllib.request, urllib.parse, fitz
import sys as _sys; _sys.path.insert(0, r'G:genti\projects\deepseek-harness-desktop')
from tma_scihub import scihub_pdf

T = os.environ.get('TMA_PROJECT') or r'C:\\Users\\via54\\Desktop\\TMA_test'
MISSING = os.path.join(T, '_missing_list.json')
OUT = os.path.join(T, '_2_pdfs')
REPORT = os.path.join(T, '_download_round2_report.json')
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


def crossref_best(citation):
    """CrossRef 题录查询 → [(doi, title, journal, year)]"""
    q = urllib.parse.quote(citation)
    try:
        d = fetch_json('https://api.crossref.org/works?query.bibliographic=' + q + '&rows=5')
        items = d.get('message', {}).get('items', [])
        out = []
        for it in items:
            out.append({
                'doi': it.get('DOI'),
                'title': (it.get('title') or [''])[0][:150],
                'journal': (it.get('container-title') or [''])[0][:80],
                'year': (it.get('issued') or {}).get('date-parts', [[None]])[0][0],
            })
        return out
    except Exception as e:
        return []


J_ABBR = {
    'n engl j med': 'new england journal of medicine',
    'engl j med': 'new england journal of medicine',
    'j thromb haemost': 'journal of thrombosis and haemostasis',
    'jth': 'journal of thrombosis and haemostasis',
    'clin adv hematol oncol': 'clinical advances in hematology and oncology',
    'clin microbiol rev': 'clinical microbiology reviews',
    'nat rev nephrol': 'nature reviews nephrology',
    'am j kidney dis': 'american journal of kidney diseases',
    'ajkd': 'american journal of kidney diseases',
    'kidney int': 'kidney international',
    'mayo clin proc': 'mayo clinic proceedings',
    'am j hematol': 'american journal of hematology',
    'blood adv': 'blood advances',
    'biol blood marrow transplant': 'biology of blood and marrow transplantation',
    'transplant cell ther': 'transplantation and cellular therapy',
    'bone marrow transplant': 'bone marrow transplantation',
    'j clin med': 'journal of clinical medicine',
    'front cell infect microbiol': 'frontiers in cellular and infection microbiology',
    'front immunol': 'frontiers in immunology',
    'front pediatr': 'frontiers in pediatrics',
    'semin hematol': 'seminars in hematology',
    'blood rev': 'blood reviews',
    'pediatr nephrol': 'pediatric nephrology',
    'int j lab hematol': 'international journal of laboratory hematology',
    'clin j am soc nephrol': 'clinical journal of the american society of nephrology',
    'cjasn': 'clinical journal of the american society of nephrology',
    'cureus': 'cureus',
    'plos one': 'plos one',
    'mol immunol': 'molecular immunology',
    'j innate immun': 'journal of innate immunity',
    'j multidiscip healthc': 'journal of multidisciplinary healthcare',
    'intern med j': 'internal medicine journal',
    'ann hematol': 'annals of hematology',
    'eur radiol': 'european radiology',
    'clin transplant': 'clinical transplantation',
    'lancet': 'the lancet',
    'chest': 'chest',
    'blood': 'blood',
    'j pers med': 'journal of personalized medicine',
    'front pharmacol': 'frontiers in pharmacology',
    'toxins': 'toxins',
}
def journal_kw(citation):
    kw = set()
    for m in re.finditer(r'([A-Z][A-Za-z&]*(?:\s[A-Z][A-Za-z&]*){0,4})', citation):
        tok = m.group(1)
        if 3 <= len(tok) <= 40 and not tok.startswith(('DOI', 'PMID', 'PMC')):
            t = tok.lower()
            kw.add(J_ABBR.get(t, t))
    for m in re.finditer(r'[\u4e00-\u9fff]{4,}', citation):
        kw.add(m.group(0))
    return kw


def year_kw(citation):
    return set(re.findall(r'(?:19|20)\d{2}', citation))


def score_crossref(cr, citation):
    jkw = journal_kw(citation)
    ykw = year_kw(citation)
    scored = []
    for it in cr:
        s = 0
        j = (it.get('journal') or '').lower()
        for k in jkw:
            # 期刊名首词匹配即可 (如 'nat rev nephrol' in 'Nature Reviews Nephrology')
            first = k.split()[0] if isinstance(k, str) and k.split() else k
            if first and first in j:
                s += 2
                break
            if k in j:
                s += 2
        for y in ykw:
            if str(it.get('year')) == y:
                s += 1
        scored.append((s, it))
    scored.sort(key=lambda x: -x[0])
    return scored


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


def epmc_urls(doi):
    try:
        q = urllib.parse.quote('DOI:"' + doi + '"')
        d = fetch_json('https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=' + q + '&resultType=core&format=json&pageSize=3')
        res = d.get('resultList', {}).get('result', [])
        urls = []
        for r in res:
            pmcid = r.get('pmcid')
            for u in (r.get('fullTextUrlList') or {}).get('fullTextUrl', []) or []:
                if u.get('documentStyle') == 'pdf' and u.get('availability') in ('Open access', 'Free'):
                    urls.append(u.get('url'))
            if pmcid:
                urls.append('https://europepmc.org/articles/' + pmcid + '/pdf/main.pdf')
        return urls
    except Exception:
        return []


def ncbi_urls(doi):
    try:
        d = fetch_json('https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/?ids=' + urllib.parse.quote(doi) + '&format=json')
        for rec in d.get('records', []):
            pmcid = rec.get('pmcid')
            if pmcid:
                return ['https://www.ncbi.nlm.nih.gov/pmc/articles/' + pmcid + '/pdf/',
                        'https://pmc.ncbi.nlm.nih.gov/articles/' + pmcid + '/pdf/']
    except Exception:
        pass
    return []


def download_pdf(url, out_path, timeout=90):
    data = fetch(url, timeout)
    if data[:4] != b'%PDF':
        raise RuntimeError('not pdf: %r' % data[:30])
    if len(data) < 5000:
        raise RuntimeError('too small')
    open(out_path, 'wb').write(data)
    return len(data)


def page1(path):
    try:
        doc = fitz.open(path)
        t = doc[0].get_text()[:2500]
        doc.close()
        return t
    except Exception:
        return ''


_STOP = set('et al the of and with in for on new england journal medicine clinical american society biology marrow cellular therapy blood pediatric international nature reviews'.split())


def content_ok(txt, citation):
    """核验: 期刊整词 + 年份 + 作者姓氏 三维 (需期刊+年份 或 期刊+作者)"""
    jkw = journal_kw(citation)
    ykw = year_kw(citation)
    # 作者候选: 排除期刊缩写词 (J_ABBR 键) 与月份/通用词
    jall = set()
    for k in jkw:
        jall.update(str(k).lower().split())
    for k in J_ABBR:
        jall.update(k.split())
    asn = {a.lower() for a in re.findall(r'\b([A-Z][a-z]{2,})\b', citation)} - _STOP - jall
    asn = {a for a in asn if a not in ('jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec',
                                       'et','al','the','doi','vol','suppl','issue','pages','pp')}
    t = txt.lower()
    hit_j = False
    for k in jkw:
        if not isinstance(k, str) or not k:
            continue
        if any(ord(c) > 0x4e00 for c in k):
            if k in txt:
                hit_j = True
                break
            continue
        for w in k.split():
            if len(w) >= 5 and w not in _STOP and re.search(r'\b' + re.escape(w) + r'\b', t):
                hit_j = True
                break
        if hit_j:
            break
    hit_y = any(y in txt for y in ykw)
    hit_a = any(a.lower() in t for a in asn)
    score = (2 if hit_j else 0) + (1 if hit_y else 0) + (1 if hit_a else 0)
    return score


def process_ref(ref_id, citation, doi_map_info=None, out_dir=None, sleep_s=0.5):
    """单条引用恢复下载 (供 via54_auto 编排器调用, 签名与 tma_cascade_download.process_ref 一致)

    流程: CrossRef 重解析 DOI → OA 级联 (OpenAlex/Unpaywall/EPMC/NCBI/doi.org) → Sci-Hub 兜底
    → content_ok 三维核验 (期刊/年份/作者) → 返回 {'ref','status':'ok|fail|exists',...}
    """
    out_dir = out_dir or OUT
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, ref_id + ".pdf")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 5000:
        return {"ref": ref_id, "status": "exists"}
    log = {"ref": ref_id}
    cr = crossref_best(citation)
    if not cr:
        log["status"] = "crossref_fail"
        return log
    scored = score_crossref(cr, citation)
    dois = []
    known = (doi_map_info or {}).get("doi") if isinstance(doi_map_info, dict) else None
    if known and str(known).startswith("10."):
        dois.append(str(known))
    for _s, it in scored:
        if it.get("doi") and it["doi"] not in dois:
            dois.append(it["doi"])
    attempts = []
    done = False
    for doi in dois[:4]:
        if done:
            break
        for src, urls in [
            ("openalex", [openalex_oa(doi)]),
            ("unpaywall", [unpaywall_oa(doi)]),
            ("epmc", epmc_urls(doi)),
            ("ncbi", ncbi_urls(doi)),
            ("doi_org", ["https://doi.org/" + doi]),
        ]:
            if done:
                break
            for u in urls:
                if not u:
                    continue
                try:
                    download_pdf(u, out_path)
                    txt = page1(out_path)
                    score = content_ok(txt, citation)
                    attempts.append((src, u[:70], "downloaded", score))
                    if score >= 3:
                        log.update({"status": "ok", "source": src, "doi": doi, "url": u, "score": score})
                        done = True
                        break
                    os.remove(out_path)
                    attempts[-1] = (src, u[:70], "content-mismatch", score)
                except Exception as e:
                    attempts.append((src, u[:70], str(e)[:40], 0))
        if not done and doi.startswith("10."):
            try:
                if scihub_pdf(doi, out_path):
                    txt = page1(out_path)
                    score = content_ok(txt, citation)
                    if score >= 3:
                        log.update({"status": "ok", "source": "scihub", "doi": doi, "url": "sci-hub/" + doi, "score": score})
                        done = True
                        break
                    os.remove(out_path)
                elif os.path.exists(out_path):
                    os.remove(out_path)
            except Exception:
                if os.path.exists(out_path):
                    os.remove(out_path)
        if not done and os.path.exists(out_path):
            os.remove(out_path)
    if not done:
        log["status"] = "fail"
        log["doi_tried"] = dois[:3]
        log["attempts"] = attempts[:6]
    time.sleep(sleep_s)
    return log


def main():
    only = None
    if '--only' in sys.argv:
        only = set(sys.argv[sys.argv.index('--only') + 1].split(','))
    missing = json.load(open(MISSING, encoding='utf-8'))
    results = []
    for m in missing:
        ref = m['ref']
        if only and ref not in only:
            continue
        citation = m['citation']
        print('=== %s ===' % ref, flush=True)
        print('  cit:', citation[:80], flush=True)
        cr = crossref_best(citation)
        if not cr:
            results.append({'ref': ref, 'status': 'crossref_fail'})
            print('  -> crossref_fail', flush=True)
            continue
        scored = score_crossref(cr, citation)
        # 优先已知 doi (若正确) + 高分 CrossRef 候选
        dois = []
        known = m.get('doi')
        if known and known.startswith('10.'):
            dois.append(known)
        for s, it in scored:
            if it.get('doi') and it['doi'] not in dois:
                dois.append(it['doi'])
        print('  doi candidates:', [(s, it.get('doi'), it.get('journal'), it.get('year')) for s, it in scored[:3]], flush=True)
        done = False
        for doi in dois[:4]:
            if done:
                break
            out_path = os.path.join(OUT, ref + '.pdf')
            attempts = []
            for src, urls in [
                ('openalex', [openalex_oa(doi)]),
                ('unpaywall', [unpaywall_oa(doi)]),
                ('epmc', epmc_urls(doi)),
                ('ncbi', ncbi_urls(doi)),
                ('doi_org', ['https://doi.org/' + doi]),
            ]:
                if done:
                    break
                for u in urls:
                    if not u:
                        continue
                    try:
                        download_pdf(u, out_path)
                        txt = page1(out_path)
                        score = content_ok(txt, citation)
                        attempts.append((src, u[:70], 'downloaded', score))
                        if score >= 3:
                            print('  -> OK %s score=%d %s' % (src, score, u[:70]), flush=True)
                            results.append({'ref': ref, 'status': 'ok', 'source': src, 'doi': doi,
                                            'url': u, 'score': score})
                            done = True
                            break
                        else:
                            os.remove(out_path)
                            attempts[-1] = (src, u[:70], 'content-mismatch', score)
                    except Exception as e:
                        attempts.append((src, u[:70], str(e)[:40], 0))
            if not done and doi.startswith('10.'):
                try:
                    if scihub_pdf(doi, out_path):
                        txt = page1(out_path)
                        score = content_ok(txt, citation)
                        if score >= 3:
                            print('  -> OK scihub ' + doi, flush=True)
                            results.append({'ref': ref, 'status': 'ok', 'source': 'scihub', 'doi': doi, 'url': 'sci-hub/' + doi, 'score': score})
                            done = True
                            break
                        else:
                            os.remove(out_path)
                    elif os.path.exists(out_path):
                        os.remove(out_path)
                except Exception:
                    if os.path.exists(out_path):
                        os.remove(out_path)
            if not done:
                # 清理可能残留
                if os.path.exists(out_path):
                    os.remove(out_path)
                results.append({'ref': ref, 'status': 'fail', 'doi_tried': dois[:3], 'attempts': attempts[:6]})
                print('  -> fail', flush=True)
        time.sleep(0.5)

    json.dump(results, open(REPORT, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    ok = [r for r in results if r.get('status') == 'ok']
    print('\n成功 %d/%d' % (len(ok), len(results)))
    for r in results:
        if r.get('status') != 'ok':
            print('  [%s] %s' % (r['ref'], r['status']))

if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    main()
