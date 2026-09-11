#!/usr/bin/env python3
"""
hl_ocr_band.py — OCR 词级高亮器 (乱码 / 纯图像 PDF 通道)

场景: PDF 文字层乱码或为空 (扫描件), 文本定位不可用。
方法: 渲染页面 -> tesseract(eng/chi_sim) TSV -> 版面区域(layout.page_zones)
      -> 整句定位(locate_in_ocr, 与 hl_lib.locate_sentence 对齐的多级回退)
      -> 行 band -> Highlight quads (仅栏内 x, 不跨栏)。
     整句定位失败时回退到 start/end 短语窗口模式 (兼容旧用法)。

用法:
    python3 hl_ocr_band.py <pdf> <page(1-based)> --sentence "整句原文"
                           [--start start_phrase --end end_phrase  # 整句失败时的短语回退]
                           [--lang eng] [--dpi 200] [--out out.pdf] [--dry-run]
    python3 hl_ocr_band.py <pdf> <page(1-based)> <start_phrase> [end_phrase]  # 旧短语用法
    # --dry-run 只打印命中行文本与预估 band, 不改文件。
    # start/end 为 OCR 将出现的子串 (短语内断字请缩短关键词避开)。
"""
import argparse, csv, os, re, subprocess, sys, tempfile

try:
    import pymupdf as fitz  # PyMuPDF >= 1.24 的正式导入名
except ImportError:  # 旧版只有 fitz (写 import fitz 会打弃用警告)
    import fitz

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hl_lib  # noqa: E402  (复用 canon/canon_keys 规范化)
import layout  # noqa: E402  (版面区域: 页眉页脚/双栏阅读序)

DEFAULT_TESS = '/Users/david/Library/Application Support/TRAE SOLO CN/ModularData/ai-agent/vm/tools/bin/tesseract'
YELLOW = (1.0, 0.85, 0.0)
_PUNCT_RE = re.compile(r'[^\w\u4e00-\u9fff]')


def find_tess():
    cands = [DEFAULT_TESS, os.environ.get('TESSERACT', ''), 'tesseract']
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


def flow_norm(flow_words, lower=True):
    """把按阅读序排列的词流转成规范化连续串, 供整句匹配.

    复用 hl_lib.canon_keys 的字符规范化 (去空白/全角半角/连字/变音符),
    词间不再插空格 (与文本层 locate_sentence 的 whitespace-agnostic 语义一致).
    Returns (ns, wmap): ns=规范化串, wmap[i]=ns[i] 所属词的索引.
    """
    parts, wmap = [], []
    for wi, w in enumerate(flow_words):
        sk, _ = hl_lib.canon_keys(w['t'])
        if lower:
            sk = sk.lower()
        if not sk:
            continue
        parts.append(sk)
        wmap.extend([wi] * len(sk))
    return ''.join(parts), wmap


def sent_norm(sentence, lower=True):
    sk, _ = hl_lib.canon_keys(sentence)
    return sk.lower() if lower else sk


def _char_to_word_span(wmap, i0, i1):
    """规范化串区间 [i0, i1] -> 词索引区间 (含边界)"""
    if i0 < 0 or i0 >= len(wmap) or i1 < i0 or i1 >= len(wmap):
        return None
    return wmap[i0], wmap[i1]


def locate_in_ocr(flow_words, sentence):
    """整句定位: 在 OCR 词流里找整句, 返回词索引区间 (start, end) 或 None.

    回退链与 hl_lib.locate_sentence 对齐并针对 OCR 放宽:
      1) 精确规范化匹配 (去空白/全半角/连字/大小写)
      2) 连字符自愈 (跨行断字, 如 trans-missibility)
      3) 标点脱敏匹配 (OCR 标点噪声)
      4) 首尾双锚点自愈 (句子中部 OCR 错字/插入置信区间时, 仍能定出整句窗口)
    返回的区间直接映射到 flow_words 索引, 供 band 聚合使用。
    """
    ns, wmap = flow_norm(flow_words)
    sk = sent_norm(sentence)
    n = len(sk)
    if n == 0 or n > len(ns):
        return None
    # 1. 精确匹配
    i = ns.find(sk)
    if i >= 0:
        return _char_to_word_span(wmap, i, i + n - 1)
    # 2. 连字符自愈: 移除两侧 '-' 后重匹配 (需重建无连字符串的字符->词映射)
    if '-' in sk or '-' in ns:
        keep = [j for j, ch in enumerate(ns) if ch != '-']
        ns2 = ''.join(ns[j] for j in keep)
        sk2 = sk.replace('-', '')
        if sk2 and len(sk2) <= len(ns2):
            j = ns2.find(sk2)
            if j >= 0:
                i0 = keep[j]
                i1 = keep[j + len(sk2) - 1]
                return _char_to_word_span(wmap, i0, i1)
    # 3. 标点脱敏: 双方去掉标点后匹配 (纯化串同时供第 4 步复用)
    _P = re.compile(r'[^\w\u4e00-\u9fff]')
    sk_pure = _P.sub('', sk)
    keep = [j for j, ch in enumerate(ns) if not _P.match(ch)]
    ns_pure = ''.join(ns[j] for j in keep)
    if len(sk_pure) >= 6:
        if len(ns_pure) >= len(sk_pure):
            j = ns_pure.find(sk_pure)
            if j >= 0:
                i0 = keep[j]
                i1 = keep[j + len(sk_pure) - 1]
                return _char_to_word_span(wmap, i0, i1)
    # 4. 首尾双锚点 (中部 OCR 噪声容错): 长度 >= 20 的句子才启用
    if len(sk_pure) >= 20 and len(ns_pure) >= len(sk_pure):
        head = sk_pure[:12]
        tail = sk_pure[-12:]
        h = ns_pure.find(head)
        if h >= 0:
            t = ns_pure.find(tail, h + len(head))
            if t >= 0 and (t + len(tail) - h) <= int(len(sk_pure) * 2.2) + 20:
                i0 = keep[h]
                i1 = keep[t + len(tail) - 1]
                return _char_to_word_span(wmap, i0, i1)
    return None


def _add_bands(page, ws_words, dpi, xoff=0.0, yoff=0.0, dry=False):
    """按 tesseract line_num 聚合选词 -> 行 band quads. 返回 (added, lines_hit)."""
    S = dpi / 72.0
    lines = {}
    for w in ws_words:
        L = lines.setdefault(w['ln'], dict(y0=w['y'], y1=w['y'] + w['h'],
                                           x0=w['x'], x1=w['x'] + w['w']))
        L['y0'] = min(L['y0'], w['y']); L['y1'] = max(L['y1'], w['y'] + w['h'])
        L['x0'] = min(L['x0'], w['x']); L['x1'] = max(L['x1'], w['x'] + w['w'])
    bands = [lines[k] for k in sorted(lines)]
    added = 0
    for b in bands:
        x0, x1 = b['x0'] / S + xoff, b['x1'] / S + xoff
        y0, y1 = b['y0'] / S + yoff, (b['y1'] + 6) / S + yoff
        if dry:
            added += 1
            continue
        hl = page.add_highlight_annot(quads=[(x0 - 1, y0 - 1, x1 + 1, y1 + 1)])
        hl.set_colors(stroke=YELLOW)
        hl.set_opacity(0.45)
        hl.update()
        added += 1
    return added, bands


def _save_out(doc, pdf_path, dry):
    """统一落盘规则: HL_OCR_OUT > args_out > 默认 .hl.pdf; dry 不写."""
    if dry:
        return
    out = os.environ.get('HL_OCR_OUT')
    out = out or args_out
    if out is None:
        out = pdf_path.rsplit('.pdf', 1)[0] + '.hl.pdf'
    if os.path.abspath(out) == os.path.abspath(pdf_path):
        doc.save(out, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
    else:
        doc.save(out, garbage=4, deflate=True)


def sentence_band_highlight(pdf_path, page0, png, sentence, lang, dpi, dry, replace_page,
                            xoff=0.0, yoff=0.0, psm='6'):
    """整句定位 -> 行 band 高亮 (E1). 在版面 zones 上逐流尝试, 优先正文区。
    sentence 未命中时返回 (0, None), 由调用方决定是否回退到短语窗口 band_highlight。
    """
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
    page_h_px = page.rect.height * S
    flows, info = layout.reading_columns(ws, page_h_px, lang)
    # 兜底: 无 zone 词流时退化整页阅读序
    if not flows:
        allw = sorted(ws, key=lambda w: (w['y'] // 8, w['x']))
        if allw:
            flows = [allw]
    hit = None
    for flow in flows:
        rng = locate_in_ocr(flow, sentence)
        if rng is not None:
            si, ei = rng
            if ei < si:
                continue
            hit = (flow[si:ei + 1], len(flow))
            break
    added = 0
    ncols = len(flows)
    if hit:
        sel = hit[0]
        added, _ = _add_bands(page, sel, dpi, xoff, yoff, dry)
        joined = ' '.join(w['t'] for w in sel)
        print(f' hit[{len(sel)}/{hit[1]} words]: {joined[:120]}')
    _save_out(doc, pdf_path, dry)
    doc.close()
    return added, hit, ncols


def band_highlight(pdf_path, page0, png, start, end, lang, dpi, dry, replace_page,
                   xoff=0.0, yoff=0.0, psm='6'):
    """xoff/yoff: crop 渲染时 OCR 坐标相对整页的偏移(pt)."""
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
    _save_out(doc, pdf_path, dry)
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
    ap.add_argument('start', nargs='?', default=None,
                    help='start 短语 (旧用法, 或 --sentence 失败时的短语回退)')
    ap.add_argument('end', nargs='?', default=None, help='end 短语 (可选)')
    ap.add_argument('--sentence', default=None,
                    help='整句原文: 优先走整句定位(locate_in_ocr), 失败且提供 start 时回退短语窗口')
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
    if a.sentence is None and a.start is None:
        ap.error('需要 --sentence "整句" 或位置参数 start 短语')
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
        if a.sentence is not None:
            # E1: 整句定位优先; 未命中且给 start 短语时回退旧窗口
            added, hit, ncols = sentence_band_highlight(
                a.pdf, a.page - 1, png, a.sentence, a.lang, a.dpi,
                a.dry_run, a.replace_page, xoff, yoff, a.psm)
            if hit is None and a.start is not None:
                print('sentence not found, fallback to phrase window')
                band_highlight(a.pdf, a.page - 1, png, a.start, a.end, a.lang,
                               a.dpi, a.dry_run, a.replace_page, xoff, yoff, a.psm)
        else:
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
