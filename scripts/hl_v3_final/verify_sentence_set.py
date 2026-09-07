#!/usr/bin/env python3
"""
verify_sentence_set.py — 句集定位复现验证器 (区域级, E3)

对「整句清单 TSV」中每个 (file, page, sentence) 重新定位并报告逐文件汇总。
页级文字层可用性改为区域级判定:
  - image : 整页无有效字母/CJK -> 整页 OCR 通道
  - mixed : 页含少量文字层(页眉/页码/脚注)但正文区(去边距)无文字层
            -> 正文在图像, 句子走 OCR 通道, 不再误报 NOT FOUND
  - text  : 正文区有文字层 -> hl_lib 文本层定位
可选 --ocr: 对 image/mixed 页句子用 E1(layout + locate_in_ocr) 做 OCR 复现,
            命中计入 located_ok(标注 OCR), 否则归 OCR 通道计数。

TSV 列: file  page  type  flag  text   (tab 分隔, 首行表头)
用法:
    python3 verify_sentence_set.py --pdf-dir <dir> --sentences <sentences.tsv>
    # 区域阈值: --top-margin 0.10 --bottom-margin 0.10 --side-margin 0.05
    # OCR 复现: --ocr [--ocr-lang eng] [--ocr-dpi 200] [--ocr-cache dir]
"""
import argparse, csv, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fitz  # noqa: E402
import hl_lib  # noqa: E402
import layout  # noqa: E402
import hl_ocr_band as ob  # noqa: E402


def norm(s):
    return re.sub(r'\s+', '', s)


def classify_page(page, top_m=0.10, bottom_m=0.10, side_m=0.05,
                  body_min=150, garbled_ratio=0.5):
    """区域级文字层判定 (E3). 返回 ('image'|'mixed'|'garbled'|'text', ...)

    按正文区(去上下左右边距的版心)字符统计分层:
      image   : 整页无有效字母/CJK -> 纯图像页, OCR 通道
      garbled : 正文区字符很多但有效字母率 < garbled_ratio -> 字形映射乱码
                (字符码错乱/符号填充), 文本层不可用于匹配, OCR 通道
      mixed   : 页面有少量文字层(页眉/页码/行), 正文区字符 < body_min
                -> 正文主体在图像, OCR 通道
      text    : 正文区字符 >= body_min 且字母率足够 -> 真实文本层, 走 hl_lib
    """
    chars, text = hl_lib.page_char_stream(page)
    if not chars:
        return 'image', 0, 0, 0.0, text
    W, H = page.rect.width, page.rect.height
    bx0, bx1 = W * side_m, W * (1 - side_m)
    by0, by1 = H * top_m, H * (1 - bottom_m)
    letters_total = 0
    body_chars = 0
    body_letters = 0
    for c, r in chars:
        if not c.strip():
            continue
        if re.match(r'[\u4e00-\u9fffA-Za-z]', c):
            letters_total += 1
        cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        if bx0 <= cx <= bx1 and by0 <= cy <= by1:
            body_chars += 1
            if re.match(r'[\u4e00-\u9fffA-Za-z]', c):
                body_letters += 1
    rate = body_letters / body_chars if body_chars else 0.0
    if letters_total == 0:
        return 'image', body_chars, letters_total, rate, text
    if body_chars >= body_min and rate >= garbled_ratio:
        return 'text', body_chars, letters_total, rate, text
    if body_chars >= body_min:
        # 正文区字符很多但有效字母率低 -> 字形乱码(标点/符号/错码填充)
        return 'garbled', body_chars, letters_total, rate, text
    return 'mixed', body_chars, letters_total, rate, text


def _read_words_tsv(tsv):
    """读取 tesseract TSV -> 词 dict 列表 (与 hl_ocr_band.words_tsv 相同解析)."""
    rows = list(csv.reader(open(tsv, encoding='utf-8'), delimiter='\t'))
    if not rows or 'text' not in rows[0]:
        return []
    ci = {c: i for i, c in enumerate(rows[0])}
    ws = []
    for r in rows[1:]:
        if len(r) > 11 and r[ci['level']] == '5' and r[ci['text']].strip():
            try:
                if float(r[ci['conf']]) > 20:
                    ws.append(dict(x=int(r[ci['left']]), y=int(r[ci['top']]),
                                   w=int(r[ci['width']]), h=int(r[ci['height']]),
                                   ln=r[ci['line_num']], t=r[ci['text']]))
            except Exception:
                pass
    return ws


def ocr_locate(pdf_path, page_no, sentence, lang='eng', dpi=200, cache_dir=None,
               psm='4'):
    """E1 OCR 复现: 页渲染 -> tesseract TSV -> layout zones -> locate_in_ocr.
    cache_dir 命中 {name}_p{page}.tsv 时直接复用. 返回 bool.
    """
    name = os.path.splitext(os.path.basename(pdf_path))[0]
    png = None
    if cache_dir:
        tsv = os.path.join(cache_dir, f'{name}_p{page_no}.tsv')
        if os.path.exists(tsv):
            ws = _read_words_tsv(tsv)
        else:
            ws = []
    else:
        ws = []
    if not ws:
        import tempfile
        tmpd = os.environ.get('HL_OCR_TMP') or tempfile.mkdtemp(prefix='vfy_ocr_')
        png = os.path.join(tmpd, f'{name}_p{page_no}.png')
        d = fitz.open(pdf_path)
        if page_no < 1 or page_no > len(d):
            d.close()
            return False
        d[page_no - 1].get_pixmap(dpi=dpi).save(png)
        d.close()
        ob.words_tsv(png, png[:-4], lang, psm=psm)
        ws = _read_words_tsv(png[:-4] + '.tsv')
        try:
            os.remove(png)
            os.remove(png[:-4] + '.tsv')
        except OSError:
            pass
    if not ws:
        return False
    d = fitz.open(pdf_path)
    if page_no < 1 or page_no > len(d):
        d.close()
        return False
    hpx = d[page_no - 1].rect.height * (dpi / 72.0)
    d.close()
    flows, _ = layout.reading_columns(ws, hpx, lang)
    if not flows:
        flows = [sorted(ws, key=lambda w: (w['y'] // 8, w['x']))]
    return any(ob.locate_in_ocr(f, sentence) is not None for f in flows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pdf-dir', required=True)
    ap.add_argument('--sentences', required=True)
    ap.add_argument('--top-margin', type=float, default=0.10)
    ap.add_argument('--bottom-margin', type=float, default=0.10)
    ap.add_argument('--side-margin', type=float, default=0.05)
    ap.add_argument('--body-min', type=int, default=150,
                    help='正文区字符数达到该值才可能判 text/garbled 页')
    ap.add_argument('--garbled-ratio', type=float, default=0.5,
                    help='正文区有效字母率低于该值且正文字符多 -> garbled 字形乱码')
    ap.add_argument('--ocr', action='store_true',
                    help='对 image/mixed/garbled 页句子做 E1 OCR 复现(命中计入 located_ok, 标注 OCR)')
    ap.add_argument('--ocr-lang', default='eng')
    ap.add_argument('--ocr-dpi', type=int, default=200)
    ap.add_argument('--ocr-cache', default=None,
                    help='OCR TSV 缓存目录({name}_p{page}.tsv); 命中则免重跑 tesseract')
    a = ap.parse_args()

    rows = list(csv.reader(open(a.sentences, encoding='utf-8'), delimiter='\t'))[1:]
    by_file = {}
    for r in rows:
        if len(r) < 5:
            continue
        by_file.setdefault(r[0].replace('.pdf', ''), []).append((int(r[1]), r[4]))

    summary, not_found = [], []
    ocr_ch = []      # 走 OCR 通道的 (pn, pg, sent, kind)
    ocr_ok = 0       # OCR 复现命中句数 (仅 --ocr 时)
    for pn in sorted(by_file):
        pdf = os.path.join(a.pdf_dir, pn + '.pdf')
        if not os.path.exists(pdf):
            summary.append((pn, len(by_file[pn]), 0, 'NO-PDF'))
            continue
        doc = fitz.open(pdf)
        ok = 0
        file_nf = []
        file_ocr = []
        for (pg, sent) in by_file[pn]:
            if pg < 1 or pg > len(doc):
                file_nf.append((pn, pg, sent[:40], 'BAD PAGE'))
                continue
            page = doc[pg - 1]
            kind, body_chars, letters_total, rate, text = classify_page(
                page, a.top_margin, a.bottom_margin, a.side_margin,
                a.body_min, a.garbled_ratio)
            if kind in ('image', 'mixed', 'garbled'):
                file_ocr.append((pg, sent, kind))
                continue
            # text 页: hl_lib 文本层定位
            chars, _ = hl_lib.page_char_stream(page)
            loc = hl_lib.locate_sentence(text, sent)
            if loc is None:
                locs = hl_lib.locate_sentence_all(text, sent)
                if len(locs) == 1:
                    loc = locs[0]
            if loc is None or not hl_lib.sentence_rects(chars, *loc):
                file_nf.append((pn, pg, norm(sent)[:60], 'NOT FOUND'))
                continue
            ok += 1
        # OCR 通道句: 可选 E1 复现
        file_ocr_ok = 0
        if a.ocr:
            for (pg, sent, kind) in file_ocr:
                if ocr_locate(pdf, pg, sent, a.ocr_lang, a.ocr_dpi, a.ocr_cache):
                    ok += 1
                    file_ocr_ok += 1
                else:
                    ocr_ch.append((pn, pg, norm(sent)[:60], kind))
        else:
            ocr_ch.extend((pn, pg, norm(sent)[:60], kind) for (pg, sent, kind) in file_ocr)
        doc.close()
        not_found.extend(file_nf)
        total = len(by_file[pn])
        img = sum(1 for (_, _, k) in file_ocr if k == 'image')
        mix = sum(1 for (_, _, k) in file_ocr if k == 'mixed')
        gar = sum(1 for (_, _, k) in file_ocr if k == 'garbled')
        if not file_nf and ok == total:
            tag = []
            if a.ocr and file_ocr:
                tag.append(f'OCR+{file_ocr_ok}/{len(file_ocr)}')
            summary.append((pn, total, ok, 'OK' + (f' ({",".join(tag)})' if tag else '')))
        elif not file_nf:
            parts = []
            if img:
                parts.append(f'image={img}')
            if mix:
                parts.append(f'mixed={mix}')
            if gar:
                parts.append(f'garbled={gar}')
            summary.append((pn, total, ok, 'OCR 通道' + (f' ({",".join(parts)})' if parts else '')))
        else:
            summary.append((pn, total, ok, f'PARTIAL ({len(file_nf)} NOT FOUND)'))

    print(f'{"file":<8} {"sents":>5} {"ok":>4}  status')
    for s in summary:
        print(f'{s[0]:<8} {s[1]:>5} {s[2]:>4}  {s[3]}')
    print('\n=== OCR 通道句 (image/mixed/garbled, 未复现) ===')
    for c in ocr_ch:
        print(' ', c)
    if not_found:
        print('\n=== NOT FOUND (text 页真实缺失) ===')
        for nf in not_found:
            print(' ', nf)
    total_s = sum(s[1] for s in summary)
    total_ok = sum(s[2] for s in summary)
    mode = ' + OCR 复现' if a.ocr else ''
    print(f'\nTOTAL sentences={total_s} located_ok={total_ok}{mode}'
          f'  ocr_channel={len(ocr_ch)}  not_found={len(not_found)}')


if __name__ == '__main__':
    main()
