"""tma_verify_highlights.py — highlight 质量验证

对 _highlight_nested 每个 Pn-x:
  1) highlight.pdf annot 数 > 0
  2) 根目录 highlight_pN.png 非 0 字节 + 黄色像素占比 (RGB 255,217,0 系)
  3) highlight_pages/ 完整 (与 PDF 页数一致)
输出 _highlight_verify_report.json + 问题清单
"""
import json, os, re, io, sys, fitz

T = os.environ.get('TMA_PROJECT') or r'C:\\Users\\via54\\Desktop\\TMA_test'
HL_BASE = os.path.join(T, '_highlight_nested')
OUT = os.path.join(T, '_highlight_verify_report.json')

def yellow_pct(path):
    """返回黄色像素占比 (%) 或 None (文件不可读)。纯 PIL, 不依赖 numpy。"""
    try:
        from PIL import Image
        img = Image.open(path).convert('RGB')
        w, h = img.size
        if w == 0 or h == 0:
            return 0.0
        total = w * h
        yellow = 0
        px = img.load()
        for y in range(0, h, 100):
            for yy in range(y, min(y + 100, h)):
                for xx in range(w):
                    r, g, b = px[xx, yy]
                    if r > 200 and g > 200 and b < 150:
                        yellow += 1
        return float(yellow) / total * 100.0
    except Exception:
        return None

def main():
    only = None
    if '--only' in sys.argv:
        only = set(sys.argv[sys.argv.index('--only') + 1].split(','))
    results = []
    issues = []
    if not os.path.isdir(HL_BASE):
        print('no highlight base'); return
    for pn_dir in sorted(os.listdir(HL_BASE)):
        full = os.path.join(HL_BASE, pn_dir)
        if not os.path.isdir(full):
            continue
        if only and pn_dir not in only:
            continue
        hl_pdf = os.path.join(full, pn_dir + '_highlight.pdf')
        rec = {'pn': pn_dir}
        if not os.path.exists(hl_pdf):
            rec['status'] = 'no_highlight_pdf'
            results.append(rec); issues.append((pn_dir, 'no_highlight_pdf')); continue
        try:
            doc = fitz.open(hl_pdf)
            n_pages = len(doc)
            annot_pages = {}
            for i in range(n_pages):
                a = list(doc[i].annots() or [])
                if a:
                    annot_pages[i + 1] = len(a)
            doc.close()
            rec['pages'] = n_pages
            rec['annot_pages'] = annot_pages
            rec['annot_total'] = sum(annot_pages.values())
        except Exception as e:
            rec['status'] = 'pdf_error: %s' % e
            results.append(rec); issues.append((pn_dir, rec['status'])); continue
        # 根目录图片
        pngs = sorted(f for f in os.listdir(full) if re.match(pn_dir + r'_highlight_p\d+\.png$', f))
        rec['imgs'] = []
        for png in pngs:
            p = os.path.join(full, png)
            sz = os.path.getsize(p)
            yp = yellow_pct(p)
            rec['imgs'].append({'file': png, 'size': sz, 'yellow_pct': yp})
            if sz == 0:
                issues.append((pn_dir, 'zero_byte_img ' + png))
            elif yp is not None and yp < 0.01:
                issues.append((pn_dir, 'low_yellow ' + png + ' %.4f%%' % yp))
        # 缺页检查: annot 页 vs 根目录图
        exp = set(annot_pages.keys())
        got = set(int(re.match(r'.*_p(\d+)\.png$', f).group(1)) for f in pngs if os.path.getsize(os.path.join(full, f)) > 0)
        missing_imgs = sorted(exp - got)
        if missing_imgs:
            issues.append((pn_dir, 'missing_img_pages ' + str(missing_imgs)))
        rec['missing_img_pages'] = missing_imgs
        # pages 子目录
        pages_dir = os.path.join(full, pn_dir + '_highlight_pages')
        if os.path.isdir(pages_dir):
            n_jpg = len([f for f in os.listdir(pages_dir) if f.endswith('.jpg')])
            rec['pages_subdir'] = n_jpg
            if n_jpg != n_pages:
                issues.append((pn_dir, 'pages_subdir %d != %d' % (n_jpg, n_pages)))
        else:
            rec['pages_subdir'] = 0
            issues.append((pn_dir, 'no_pages_subdir'))
        rec['status'] = 'ok' if rec['annot_total'] > 0 else 'no_annots'
        if rec['status'] == 'no_annots':
            issues.append((pn_dir, 'no_annots'))
        results.append(rec)

    json.dump({'results': results, 'issues': issues}, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('Pn-x dirs:', len(results))
    print('statuses:', {s: sum(1 for r in results if r.get('status') == s) for s in set(r.get('status', '?') for r in results)})
    print('issues:', len(issues))
    for pn, it in issues:
        print('  [%s] %s' % (pn, it))

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    main()
