import os
"""tma_verify_pdfs.py — 下载后 PDF 内容与引用核对

对 _2_pdfs 中每个 Pn-Sx_y.pdf, 提取首页文本, 与 _references_FINAL.json 的引用字段核对:
  - 期刊名包含度 (citation 中的期刊关键词是否出现在首页)
  - 年份是否出现
  - 作者姓氏是否出现
输出 _pdf_verify_report.json: 每 ref 的 score + 判定 (ok / suspicious / mismatch)
"""
import json, os, re, io, sys, fitz

T = os.environ.get('TMA_PROJECT') or r'C:\\Users\\via54\\Desktop\\TMA_test'
REF_JSON = os.path.join(T, '_references_FINAL.json')
PDF_DIR = os.path.join(T, '_2_pdfs')
OUT = os.path.join(T, '_pdf_verify_report.json')

CN_PATTERN = re.compile(r'[\u4e00-\u9fff]')

def journal_keywords(citation):
    """从引用串提取期刊名关键词 (中英文期刊名 + 常见词)"""
    kw = set()
    # 英文期刊名: 形如 'Br J Haematol', 'Nat Rev Nephrol' — 取大写词组合
    for m in re.finditer(r'([A-Z][A-Za-z&]+(?:\s[A-Z][A-Za-z&]+){0,4})', citation):
        tok = m.group(1)
        if 3 <= len(tok) <= 40 and not tok.startswith(('DOI', 'PMID', 'PMC')):
            kw.add(tok.lower())
    # 中文期刊名: 连续中文段
    for m in re.finditer(r'[\u4e00-\u9fff]{4,}', citation):
        kw.add(m.group(0))
    return kw

def author_surnames(citation):
    """提取作者姓氏 (英文大写开头的词, 排除期刊词)"""
    names = set()
    for m in re.finditer(r'\b([A-Z][a-z]{2,})\b', citation):
        names.add(m.group(1).lower())
    return names

def first_page_text(path, n=2500):
    try:
        doc = fitz.open(path)
        txt = doc[0].get_text()[:n] if len(doc) else ''
        doc.close()
        return txt
    except Exception:
        return ''

def check(ref_id, citation, path):
    txt = first_page_text(path)
    t = txt.lower()
    jkw = journal_keywords(citation)
    asn = author_surnames(citation)
    years = set(re.findall(r'(19|20)\d{2}', citation))
    hits_j = []
    for k in jkw:
        if k.lower() in t:
            hits_j.append(k)
    hits_y = [y for y in years if y in txt]
    hits_a = [a for a in asn if a in t and a not in ('et','al','the','new','england','journal','medicine','hematology','international','transplantation','transplant','blood','oncology','immunology','clinical','nephrology','pediatric','advances','in','of','for','and','with')]
    score = 0
    if hits_j: score += 2
    if hits_y: score += 1
    if hits_a: score += 1
    is_cn = bool(CN_PATTERN.search(citation))
    # 中文文献: 期刊名命中是关键
    if is_cn:
        cn_hits = [k for k in jkw if CN_PATTERN.search(k) and k in txt]
        if cn_hits: score += 3
    if not txt.strip():
        verdict = 'no_text'
    elif score >= 3:
        verdict = 'ok'
    elif score >= 1:
        verdict = 'suspicious'
    else:
        verdict = 'mismatch'
    return {
        'ref': ref_id, 'verdict': verdict, 'score': score,
        'journal_hits': hits_j[:4], 'year_hits': hits_y, 'author_hits': hits_a[:4],
        'head': txt[:120].replace('\n', ' '),
    }

def main():
    refs = json.load(open(REF_JSON, encoding='utf-8'))
    only = None
    if '--only' in sys.argv:
        only = set(sys.argv[sys.argv.index('--only') + 1].split(','))
    results = []
    for ref_id, citation in sorted(refs.items()):
        if only and ref_id not in only:
            continue
        path = os.path.join(PDF_DIR, 'Pn-' + ref_id + '.pdf')
        if not os.path.exists(path) or os.path.getsize(path) < 5000:
            results.append({'ref': ref_id, 'verdict': 'no_pdf'})
            continue
        r = check(ref_id, citation, path)
        print('%-8s %-10s score=%-2d %s' % (ref_id, r['verdict'], r['score'], r['head'][:70]), flush=True)
        results.append(r)
    json.dump(results, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    from collections import Counter
    print('\n汇总:', dict(Counter(r['verdict'] for r in results)))

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    main()
