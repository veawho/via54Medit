#!/usr/bin/env python3
"""
verify_sentence_set.py — 句集定位复现验证器 (通用)

对「整句清单 TSV」中每个 (file, page, sentence)，用 hl_lib 的
locate_sentence + sentence_rects 在对应 PDF 重新定位，报告 NOT FOUND / 逐文件汇总。
用途: 证明当前 hl_lib 算法能 100% 复现某批 PDF 的全部整句高亮配置。

TSV 列: file  page  type  flag  text   (tab 分隔, 首行表头)
用法:
    python3 verify_sentence_set.py --pdf-dir <dir> --sentences <sentences.tsv>
    # 文字层可读判定阈值可调: --min-cjk 50 --min-en 300
"""
import argparse, csv, glob, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fitz  # noqa: E402
import hl_lib  # noqa: E402


def norm(s):
    return re.sub(r'\s+', '', s)


def readable(pdf_path, min_cjk=50, min_en=300):
    doc = fitz.open(pdf_path)
    tot = ''.join(p.get_text('text') for p in doc)
    doc.close()
    cjk = len(re.findall(r'[\u4e00-\u9fff]', tot))
    en = len(re.findall(r'[A-Za-z]', tot))
    return cjk >= min_cjk or en >= min_en


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pdf-dir', required=True)
    ap.add_argument('--sentences', required=True)
    ap.add_argument('--min-cjk', type=int, default=50)
    ap.add_argument('--min-en', type=int, default=300)
    a = ap.parse_args()

    rows = list(csv.reader(open(a.sentences, encoding='utf-8'), delimiter='\t'))[1:]
    by_file = {}
    for r in rows:
        if len(r) < 5:
            continue
        by_file.setdefault(r[0].replace('.pdf', ''), []).append((int(r[1]), r[4]))

    summary, not_found, ocr_sents = [], [], 0
    for pn in sorted(by_file):
        pdf = os.path.join(a.pdf_dir, pn + '.pdf')
        if not os.path.exists(pdf):
            summary.append((pn, len(by_file[pn]), 0, 'NO-PDF'))
            continue
        doc = fitz.open(pdf)
        ok = 0
        page_ocr = 0
        file_nf = []
        for (pg, sent) in by_file[pn]:
            if pg < 1 or pg > len(doc):
                file_nf.append((pn, pg, sent[:40], 'BAD PAGE'))
                continue
            page = doc[pg - 1]
            ptxt = page.get_text('text')
            # 页级文字层可用性: 含有效 CJK/字母即认为可定位; 否则该页走 OCR 通道
            if not re.search(r'[\u4e00-\u9fffA-Za-z]', ptxt):
                page_ocr += 1
                ocr_sents += 1
                continue
            chars, text = hl_lib.page_char_stream(page)
            loc = hl_lib.locate_sentence(text, sent)
            if loc is None:
                # occurrence 尝试: 句可能多次出现
                locs = hl_lib.locate_sentence_all(text, sent)
                if len(locs) == 1:
                    loc = locs[0]
            if loc is None or not hl_lib.sentence_rects(chars, *loc):
                file_nf.append((pn, pg, norm(sent)[:60], 'NOT FOUND'))
                continue
            ok += 1
        doc.close()
        not_found.extend(file_nf)
        total = len(by_file[pn])
        if not file_nf and page_ocr == total:
            summary.append((pn, total, ok, 'GARBLED/IMAGE (OCR 通道)'))
        elif not file_nf and ok == total - page_ocr:
            summary.append((pn, total, ok, 'OK' + (f' (+{page_ocr} OCR 句)' if page_ocr else '')))
        else:
            summary.append((pn, total, ok, f'PARTIAL ({len(file_nf)} NOT FOUND)'))

    print(f'{"file":<8} {"sents":>5} {"ok":>4}  status')
    for s in summary:
        print(f'{s[0]:<8} {s[1]:>5} {s[2]:>4}  {s[3]}')
    print('\n=== NOT FOUND ===')
    for nf in not_found:
        print(' ', nf)
    total_s = sum(s[1] for s in summary)
    total_ok = sum(s[2] for s in summary)
    print(f'\nTOTAL sentences={total_s} located_ok={total_ok}'
          f' (text-layer files; garbled/image files excluded above)')


if __name__ == '__main__':
    main()
