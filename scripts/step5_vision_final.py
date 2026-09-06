#!/usr/bin/env python3
"""
step5_vision_final.py — Step5 真·视觉双对齐终版
对每个 {Pn-x}: 左=引用位置裁剪图(claim_visual) 右=文献含高亮候选页
mmx 视觉逐条返回支撑该引用位置论点的完整原句(附页码) -> 原文流整句定位 -> 单 Highlight 落位。
用法: python3 step5_vision_final.py <run_base_dir> <mirror_dir> <out_dir>
"""
import os, sys, re, json, glob, csv, shutil
import pymupdf
from PIL import Image, ImageDraw

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "hl_v3_final"))
import hl_lib
from provider_vision import vision_analyze

YELLOW = (1, 0.85, 0)
OPAC = 0.45


def hl_pages(pdf):
    d = pymupdf.open(pdf)
    pages = []
    for pi, p in enumerate(d, 1):
        n = sum(1 for a in (p.annots() or []) if a.type[1] in ('Highlight', 'Square'))
        if n:
            pages.append(pi)
    d.close()
    return pages


def render_page(pdf, pi, dpi=140):
    d = pymupdf.open(pdf)
    pix = d[pi - 1].get_pixmap(dpi=dpi)
    p = f"/tmp/step5_p{os.getpid()}_{pi}.png"
    pix.save(p)
    d.close()
    return p


def compose(claim_png, page_pngs):
    crop = Image.open(claim_png).convert('RGB')
    cw, ch = crop.size
    cw = min(cw, 700)
    ch = int(ch * cw / crop.size[0])
    crop = crop.resize((cw, ch))
    imgs = []
    for i, pp in enumerate(page_pngs):
        im = Image.open(pp).convert('RGB')
        pw = 1000
        ph = int(im.size[1] * pw / im.size[0])
        im = im.resize((pw, ph))
        pad = Image.new('RGB', (pw, 46), (255, 255, 255))
        dr = ImageDraw.Draw(pad)
        dr.text((10, 12), f"--- PAGE {i+1} ---", fill=(0, 0, 0))
        imgs.append(pad)
        imgs.append(im)
    total_h = ch + sum(im.size[1] for im in imgs)
    w = max(cw, max(im.size[0] for im in imgs))
    canvas = Image.new('RGB', (cw + w + 10, total_h), (230, 230, 230))
    canvas.paste(crop, (0, 0))
    y = ch
    for im in imgs:
        canvas.paste(im, (cw + 10, y))
        y += im.size[1]
    tmp = f"/tmp/step5_comp_{os.getpid()}.png"
    canvas.save(tmp)
    return tmp


def draw_sentence(page, chars, text, s):
    loc = hl_lib.locate_sentence(text, s)
    if loc is None:
        return False
    rects = hl_lib.sentence_rects(chars, *loc)
    rects = [r for r in rects if r.width >= 1 and r.height >= 1]
    if not rects:
        return False
    merged = []
    for q in sorted(rects, key=lambda r: (r.y0, r.x0)):
        if merged and abs(q.y0 - merged[-1].y0) < 2 and q.x0 - merged[-1].x1 < 12:
            merged[-1] = pymupdf.Rect(merged[-1].x0, merged[-1].y0, max(merged[-1].x1, q.x1), merged[-1].y1)
        else:
            merged.append(q)
    try:
        h = page.add_highlight_annot(quads=merged)
        h.set_colors(stroke=YELLOW)
        h.set_opacity(OPAC)
        h.update()
        return True
    except Exception:
        return False


def main():
    run_base, mirror, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(out_dir, exist_ok=True)
    dirs = sorted(glob.glob(run_base + "/P*/"))
    rows = []
    total_ok = 0
    for d in dirs:
        pn = os.path.basename(d.rstrip('/'))
        if not re.match(r'^P\d+-\d+$', pn):
            continue
        meta_p = os.path.join(d, pn + "_meta.json")
        hl_pdf = os.path.join(d, pn + "_highlight.pdf")
        visual = os.path.join(d, pn + "_claim_visual.png")
        if not (os.path.isfile(meta_p) and os.path.isfile(visual)):
            continue
        meta = json.load(open(meta_p))
        claim = meta.get('claim_text') or meta.get('reference_field') or pn
        mirror_pdf = os.path.join(mirror, pn + ".pdf")
        if not os.path.isfile(mirror_pdf):
            rows.append([pn, 'NO_MIRROR', '', '', ''])
            continue
        pages = hl_pages(hl_pdf) if os.path.isfile(hl_pdf) else []
        if not pages:
            rows.append([pn, 'NO_HL_PAGES', claim[:80], '', ''])
            continue
        sel = pages[:3]
        try:
            page_pngs = [render_page(mirror_pdf, p) for p in sel]
            comp = compose(visual, page_pngs)
            prompt = (
                "你是医学文献质检专家。左侧裁剪图=幻灯中某条引用(编号位置)对应的论点与脚注; 右侧=该文献页面(按顺序1..n, 每页上方有---PAGE k---标注)。\n"
                f"引用论点: {claim[:400]}\n"
                "任务: 找到**直接支撑该引用位置论点**的1-3个完整句子(必须是右侧文献中的原文, 逐字照抄, 从句子首词到句末标点), 每条标注所在PAGE编号。\n"
                "只输出JSON: {\"finds\":[{\"page\":1,\"sentence\":\"完整原句\",\"support\":\"direct\"}]}"
            )
            res = vision_analyze(comp, prompt, timeout=240)
            content = res.get('content', '') if isinstance(res, dict) else str(res)
            mj = re.search(r'\{.*\}', content, re.S)
            if not mj:
                rows.append([pn, 'PARSE_ERR', claim[:80], content[:150], ''])
                continue
            finds = json.loads(mj.group(0)).get('finds', [])
            doc = pymupdf.open(mirror_pdf)
            n_ok = 0
            for f in finds[:3]:
                k = int(f.get('page') or 0)
                s = (f.get('sentence') or '').strip()
                if not (1 <= k <= len(doc)) or len(s) < 15:
                    continue
                page = doc[k - 1]
                chars, text = hl_lib.page_char_stream(page)
                if draw_sentence(page, chars, text, s):
                    n_ok += 1
            out_pdf = os.path.join(out_dir, pn + ".pdf")
            doc.save(out_pdf, garbage=4, deflate=True)
            doc.close()
            shutil.copy2(meta_p, os.path.join(out_dir, pn + "_meta.json"))
            shutil.copy2(visual, os.path.join(out_dir, pn + "_claim_visual.png"))
            total_ok += n_ok
            rows.append([pn, f'OK{n_ok}', claim[:80], '', ''])
            print(f"{pn} ok={n_ok}", flush=True)
        except Exception as e:
            rows.append([pn, 'RUN_ERR', claim[:80], str(e)[:150], ''])
    tsv = os.path.join(out_dir, "..", "高亮最终视觉版清单.tsv")
    with open(tsv, 'w', encoding='utf-8') as fp:
        fp.write('pn_x\tstatus\tclaim\tdetail\tremark\n')
        for r in rows:
            fp.write('\t'.join(str(x).replace('\t', ' ').replace('\n', ' ') for x in r) + '\n')
    print('DONE total_ok=', total_ok, 'items=', len(rows), 'tsv=', tsv, flush=True)


if __name__ == '__main__':
    main()
