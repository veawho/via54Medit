#!/usr/bin/env python3
"""
hl_ocr_band.py — OCR 词级高亮器 (乱码 / 纯图像 PDF 通道)

场景: PDF 文字层乱码或为空 (扫描件), 文本定位不可用。
方法: 渲染页面 -> tesseract(eng/chi_sim) TSV -> 分栏阅读序词流
      -> start/end 短语窗口 -> 行 band -> Highlight quads (仅栏内 x, 不跨栏)。

用法:
    python3 hl_ocr_band.py <pdf> <page(1-based)> <start_phrase> [end_phrase]
                           [--lang eng] [--dpi 200] [--out out.pdf] [--dry-run]
    # --dry-run 只打印命中行文本与预估 band, 不改文件。
    # start/end 为 OCR 将出现的子串 (短语内断字请缩短关键词避开)。
"""
import argparse, csv, os, re, subprocess, sys, tempfile

import fitz

DEFAULT_TESS = '/Users/david/Library/Application Support/TRAE SOLO CN/ModularData/ai-agent/vm/tools/bin/tesseract'
YELLOW = (1.0, 0.85, 0.0)


def find_tess():
    cands = [DEFAULT_TESS, os.environ.get('TESSERACT', ''), 'tesseract']
    for c in cands:
        if c and os.path.exists(c) if not c.startswith('tess') and c else False:
            pass
    # 优先显式默认/环境, 最后回退 PATH
    for c in cands:
        if not c:
            continue
        try:
            r = subprocess.run([c, '--version'], capture_output=True, timeout=20)
            if r.returncode == 0:
                return c
        except Exception:
            continue
    raise SystemExit('tesseract not found; set TESSERACT env')


def words_tsv(png, base, lang, psm='6'):
    tess = find_tess()
    subprocess.run([tess, png, base, '-l', lang, '--psm', psm, 'tsv'],
                   capture_output=True, timeout=600)
    rows = list(csv.reader(open(base + '.tsv'), delimiter='\t'))
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


def split_cols(ws):
    if len(ws) < 30:
        return [ws]
    xs = sorted(w['x'] for w in ws)
    gaps, prev = [], xs[0]
    for x in xs[1:]:
        if x - prev > 80:
            gaps.append((prev + x) // 2)
        prev = x
    if not gaps:
        return [ws]
    # 若多个大间隙(三栏等)只取最显著者; 两栏取中位gap
    cut = gaps[len(gaps) // 2]
    left = [w for w in ws if w['x'] + w['w'] / 2 < cut]
    right = [w for w in ws if w['x'] + w['w'] / 2 >= cut]
    return [left, right] if left and right else [ws]


def band_highlight(pdf_path, page0, png, start, end, lang, dpi, dry, replace_page,
                   xoff=0.0, yoff=0.0, psm='6'):
    """xoff/yoff: crop 渲染时 OCR 坐标相对整页的偏移(pt)."""
    S = dpi / 72.0
    ws = words_tsv(png, png[:-4], lang, psm)
    doc = fitz.open(pdf_path)
    page = doc[page0]
    if replace_page:
        for a in list(page.annots() or []):
            try:
                page.delete_annot(a)
            except Exception:
                pass
    added, hits = 0, []
    for col in split_cols(ws):
        col = sorted(col, key=lambda w: (w['y'] // 8, w['x']))
        full = ' '.join(w['t'] for w in col)
        s = full.find(start)
        if s < 0:
            continue
        if end:
            e = full.find(end, s)
            if e < 0:
                # 容错: OCR 断字/括号错位导致 end 短语失配时, 回退到 end 末词,
                # 避免越界覆盖到页脚/作者区
                last_word = end.split()[-1]
                e = full.find(last_word, s)
            if e < 0:
                e = len(full)  # 末词也失配: 交由调用方检查 added bands
        else:
            e = len(full)
        pos = si = ei = 0
        for i, w in enumerate(col):
            if pos <= s < pos + len(w['t']) + 1:
                si = i
            if pos <= e < pos + len(w['t']) + 1:
                ei = i
            pos += len(w['t']) + 1
        sel = sorted(col[si:ei + 1], key=lambda w: (w['y'], w['x']))
        if not sel:
            continue
        # 按 tesseract line_num 聚合: 词级 y 聚类会把相邻行误并(descender),
        # line_num 是 OCR 层级的真实文本行
        lines = {}
        for w in sel:
            L = lines.setdefault(w['ln'], dict(y0=w['y'], y1=w['y'] + w['h'],
                                               x0=w['x'], x1=w['x'] + w['w']))
            L['y0'] = min(L['y0'], w['y']); L['y1'] = max(L['y1'], w['y'] + w['h'])
            L['x0'] = min(L['x0'], w['x']); L['x1'] = max(L['x1'], w['x'] + w['w'])
        bands = [lines[k] for k in sorted(lines)]
        hits.append(full[max(0, s - 40):e + 60])
        if dry:
            continue
        for i, b in enumerate(bands):
            x0, x1 = b['x0'] / S + xoff, b['x1'] / S + xoff
            y0, y1 = b['y0'] / S + yoff, (b['y1'] + 6) / S + yoff
            hl = page.add_highlight_annot(quads=[(x0 - 1, y0 - 1, x1 + 1, y1 + 1)])
            hl.set_colors(stroke=YELLOW)
            hl.set_opacity(0.45)
            hl.update()
            added += 1
    if not dry:
        out = os.environ.get('HL_OCR_OUT')
        out = out or args_out
        if out is None:
            out = pdf_path.rsplit('.pdf', 1)[0] + '.hl.pdf'
        if os.path.abspath(out) == os.path.abspath(pdf_path):
            doc.save(out, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        else:
            doc.save(out, garbage=4, deflate=True)
    doc.close()
    for h in hits:
        print(' hit:', h)
    print(f'added_bands={added} columns_hit={len(hits)} (page={page0 + 1}, lang={lang})')


args_out = None  # module-level for closure; set below


def main():
    global args_out
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf')
    ap.add_argument('page', type=int)
    ap.add_argument('start')
    ap.add_argument('end', nargs='?', default=None)
    ap.add_argument('--lang', default='eng')
    ap.add_argument('--psm', default='6', help='tesseract 版面模式 (整页复杂版面漏检时可试 6/4/11)')
    ap.add_argument('--dpi', type=int, default=200)
    ap.add_argument('--out', default=None)
    ap.add_argument('--inplace', action='store_true')
    ap.add_argument('--replace-page', action='store_true',
                    help='先清除该页既有 Highlight 再重绘(可复现/回归用)')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--crop-top', type=float, default=None,
                    help='页内裁剪上界(pt); 整页 psm 漏检区域时使用, OCR 结果自动映射回整页坐标')
    ap.add_argument('--crop-bottom', type=float, default=None)
    a = ap.parse_args()
    args_out = a.out
    doc = fitz.open(a.pdf)
    if a.page < 1 or a.page > len(doc):
        raise SystemExit('page out of range')
    # 临时目录: tesseract 沙箱可能读不了 /tmp, 用 cwd 或 $HL_OCR_TMP
    tmpd = os.environ.get('HL_OCR_TMP') or os.path.join(os.getcwd(), '.hlocr_tmp')
    os.makedirs(tmpd, exist_ok=True)
    png = os.path.join(tmpd, 'p.png')
    page = doc[a.page - 1]
    xoff = yoff = 0.0
    if a.crop_top is not None and a.crop_bottom is not None:
        y0p, y1p = max(0, a.crop_top), min(page.rect.height, a.crop_bottom)
        yoff = y0p
        page.get_pixmap(dpi=a.dpi, clip=fitz.Rect(0, y0p, page.rect.width, y1p)).save(png)
    else:
        page.get_pixmap(dpi=a.dpi).save(png)
    doc.close()
    try:
        band_highlight(a.pdf, a.page - 1, png, a.start, a.end, a.lang, a.dpi,
                       a.dry_run, a.replace_page, xoff, yoff, a.psm)
    finally:
        if a.out is None and not a.inplace and not a.dry_run:
            pass  # 默认输出 .hl.pdf, 保留渲染缓存以便复跑
        try:
            os.remove(png)
            for ext in ('.tsv',):
                if os.path.exists(png[:-4] + ext):
                    os.remove(png[:-4] + ext)
            try:
                os.rmdir(tmpd)
            except OSError:
                pass
        except OSError:
            pass


if __name__ == '__main__':
    main()
