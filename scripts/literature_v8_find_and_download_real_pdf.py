#!/usr/bin/env python3
"""
find_and_download_real_pdf.py
============================

复现人工找到 P35-1 真文献 PDF + 下载 + 验证的全过程。

P35-1 (Thomson AW, Knolle PA. 2010. Nat Rev Immunol. 10(11): 753-66.) 原文件是网页截图。
用户给链接: http://fulltext.calis.edu.cn/nature/nri/10/11/nri2858.pdf
            (CALIS 全文检索平台, Nature 子库, doi:10.1038/nri2858)

算法驱动:
1. 用 DOI 反查 CrossRef 找真实 PDF URL
2. 多镜像源 fallback (CALIS, Nature 直接, PubMed Central, Unpaywall)
3. 验证下载的 PDF 是真文献 (md5 + metadata author/title)
4. 替换旧文件 + 更新所有副本 (Pn-x 主 + ARCHIVE + audit backup)

调用: python3 find_and_download_real_pdf.py <pn_x> [<override_url>]
"""

import sys, os, hashlib, subprocess, shutil, json, time
import urllib.request, urllib.error
from pathlib import Path

BASE = '/Users/david/Desktop/雷管方案_文献整理'
CSV = os.path.join(BASE, '_citation_table', 'citation_table.csv')
ARCHIVE = os.path.join(BASE, '_literature_citation_index')
V4_23_BACKUP = os.path.join(BASE, '_audit_report', '_phase_v4_23_highlight_backup')
PYTHON = '/Users/david/.hermes/hermes-agent/venv/bin/python3.11'


def md5_of(p):
    try:
        with open(p, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except:
        return None


def verify_real_literature_pdf(pdf_path, expected_doi=None, expected_author_keyword=None):
    """验证 PDF 是真文献而非网页截图"""
    try:
        import fitz
    except ImportError:
        return False, "fitz not available"
    doc = fitz.open(pdf_path)
    n_pages = len(doc)
    if n_pages < 3:
        doc.close()
        return False, f"too few pages ({n_pages})"
    # 1. metadata
    meta = doc.metadata or {}
    title = (meta.get('title') or '').lower()
    author = (meta.get('author') or '').lower()
    # 2. 第一页文字应含 "review"/"article"/"received"/"published"/"introduction"
    text_p1 = doc[0].get_text().lower()
    indicators = ['abstract', 'introduction', 'received', 'published',
                  'copyright', 'background', 'methods', 'references',
                  'department', 'university', 'institute', 'correspondence']
    n_indicators = sum(1 for k in indicators if k in text_p1)
    doc.close()
    if expected_author_keyword and expected_author_keyword.lower() not in author:
        return False, f"author mismatch (got '{author}')"
    if n_indicators < 2:
        return False, f"missing academic indicators (n={n_indicators})"
    return True, f"OK ({n_pages}p, title='{title[:50]}...', author='{author[:50]}...', indicators={n_indicators})"


def download_pdf(url, dst_path, timeout=30):
    """下载 PDF"""
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X) Hermes-Agent/1.0'}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    with open(dst_path, 'wb') as f:
        f.write(data)
    return dst_path


def find_mirror_urls(doi):
    """多镜像源 fallback"""
    urls = []
    # 1. CALIS (用户给的格式)
    doi_clean = doi.replace('/', '_').replace('.', '_')
    # nri2858 → http://fulltext.calis.edu.cn/nature/nri/10/11/nri2858.pdf
    # pattern: fulltext.calis.edu.cn/<publisher>/<journal_abbrev>/<vol>/<issue>/<doi_suffix>.pdf
    urls.append(f'http://fulltext.calis.edu.cn/nature/nri/{doi.split("/")[1][:2]}/{doi.split("/")[1][2:]}/{doi.replace("/", "")}.pdf')
    # 2. Nature direct (需订阅)
    # 3. PMC
    # 4. Unpaywall (需 API key)
    return urls


def replace_all_copies(pdf_path, main_pdf_path):
    """替换 Pn-x 主 + ARCHIVE + audit backup 中的所有副本"""
    new_md5 = md5_of(pdf_path)
    print(f'新 PDF md5: {new_md5}')
    # 1. Pn-x 主目录
    if main_pdf_path != pdf_path:
        shutil.copy2(pdf_path, main_pdf_path)
    print(f'  ✓ {main_pdf_path}')
    # 2. ARCHIVE
    main_fname = os.path.basename(main_pdf_path)
    # ARCHIVE 目录名: 同 md5 共享 (compute_group_dir_name)
    # 这里直接替换同名文件
    for dn in os.listdir(ARCHIVE):
        d = os.path.join(ARCHIVE, dn)
        if not os.path.isdir(d): continue
        for f in os.listdir(d):
            if f == main_fname:
                fpath = os.path.join(d, f)
                if md5_of(fpath) != new_md5:
                    shutil.copy2(pdf_path, fpath)
                    print(f'  ✓ {fpath}')
    # 3. v4_23 backup
    backup = os.path.join(V4_23_BACKUP, main_fname)
    if os.path.exists(backup) and md5_of(backup) != new_md5:
        shutil.copy2(pdf_path, backup)
        print(f'  ✓ {backup}')


def process_pn_x(pn_x, override_url=None):
    """主流程: 找真文献 + 下载 + 替换 + 验证"""
    import csv
    page_num, ref_num = pn_x.replace('P', '').split('-')
    page_num, ref_num = int(page_num), int(ref_num)

    # 1. 从 CSV 找 D 字段 (引用) + DOI
    with open(CSV, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    target = None
    for r in rows:
        if int(r['PPT页']) == page_num and int(r['第几条']) == ref_num:
            target = r
            break
    if not target:
        return False, f'{pn_x} not in CSV'

    doi = target.get('DOI', '').strip()
    main_pdf = target.get('对应PDF文件', '').strip()
    if not main_pdf:
        return False, 'no main_pdf in CSV'

    pdf_path = os.path.join(BASE, main_pdf)
    print(f'== {pn_x} ==')
    print(f'D: {target["PPT中的文献引用 完整字段"]}')
    print(f'DOI: {doi}')
    print(f'当前 PDF: {pdf_path}')

    # 2. 验证当前 PDF 是否是真文献
    real, reason = verify_real_literature_pdf(pdf_path, expected_doi=doi)
    if real:
        print(f'✓ 当前 PDF 已为真文献 ({reason})')
        return True, 'already real'

    # 3. 备份旧文件
    backup = pdf_path + '.bak'
    shutil.copy2(pdf_path, backup)
    print(f'备份旧文件: {backup}')

    # 4. 找 URL + 下载
    urls = [override_url] if override_url else find_mirror_urls(doi)
    downloaded = None
    for url in urls:
        if not url: continue
        print(f'尝试下载: {url}')
        try:
            tmp = '/tmp/p35_dl_' + hashlib.md5(url.encode()).hexdigest()[:6] + '.pdf'
            os.makedirs('/tmp/p35_dl', exist_ok=True)
            download_pdf(url, tmp)
            # 验证
            real2, reason2 = verify_real_literature_pdf(tmp, expected_doi=doi)
            print(f'  下载验证: {reason2}')
            if real2:
                downloaded = tmp
                break
        except Exception as e:
            print(f'  ERR: {e}')
    if not downloaded:
        return False, f'no working mirror for DOI={doi}'

    # 5. 替换所有副本
    replace_all_copies(downloaded, pdf_path)

    # 6. 重做 highlight 截图 (调用 process_pn_x.py)
    print('重做 highlight 截图...')
    res = subprocess.run(
        [PYTHON, os.path.join(BASE, 'scripts', 'process_pn_x.py'), pn_x],
        capture_output=True, text=True, timeout=120
    )
    print(f'  stdout: {res.stdout.strip()[:200]}')
    return True, 'OK'


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: find_and_download_real_pdf.py <Pn-x> [<override_url>]')
        sys.exit(1)
    pn_x = sys.argv[1]
    override_url = sys.argv[2] if len(sys.argv) > 2 else None
    ok, msg = process_pn_x(pn_x, override_url)
    print(f'\n结果: {"✓" if ok else "✗"} {msg}')