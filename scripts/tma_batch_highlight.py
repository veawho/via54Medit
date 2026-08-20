"""tma_batch_highlight.py — 全量嵌套 highlight (v3 FINAL rect 模式, 每 Pn-x 用其所在 slide 视觉定位)

修复 _batch_nested.py 的两个问题:
  1) 之前未传 --slide, 把全部 33 页 PPT 内容都拿去匹配每个 PDF (过宽)
  2) 之前中断, Pn-S27_1 无输出, Pn-S23_5 图片导出残缺
本脚本: 每 Pn-x 提取 slide → --slide N --no-vision → 嵌套目录输出 → 记录汇总
"""
import os, re, sys, io, json, subprocess, shutil, time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import os as _os
PYTHON = _os.environ.get('TMA_PYTHON') or sys.executable
SCRIPT = _os.environ.get('TMA_SCRIPT') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'via54_ppt_visual_to_pdf.py')
PPTX = _os.environ.get('TMA_PPTX') or r"C:\Users\via54\Desktop\TMA_test\TMA临床路径的诊断与鉴别.pptx"
PDF_DIR = _os.environ.get('TMA_PDF_DIR') or (os.environ.get('TMA_PROJECT') or r"C:\Users\via54\Desktop\TMA_test") + r"\_2_pdfs"
OUT_BASE = _os.environ.get('TMA_OUT_BASE') or (os.environ.get('TMA_PROJECT') or r"C:\Users\via54\Desktop\TMA_test") + r"\_highlight_nested"

only = None
if '--only' in sys.argv:
    only = sys.argv[sys.argv.index('--only') + 1].split(',')
force = '--force' in sys.argv

pdfs = sorted([f for f in os.listdir(PDF_DIR) if f.endswith('.pdf') and f.startswith('Pn-')])
print('待处理 PDF:', len(pdfs), flush=True)

def slide_of(pdf_name):
    m = re.match(r'Pn-S(\d+)_(\d+)\.pdf', pdf_name)
    return int(m.group(1)) if m else None

results = []
for pdf_file in pdfs:
    if only and pdf_file.replace('.pdf','') not in only:
        continue
    slide = slide_of(pdf_file)
    pn = pdf_file.replace('.pdf', '')
    out_dir = os.path.join(OUT_BASE, pn)
    hl_pdf = os.path.join(out_dir, pn + '_highlight.pdf')
    # 已存在且有效则跳过 (除非 --force)
    if not force and os.path.exists(hl_pdf) and os.path.getsize(hl_pdf) > 10000:
        print(f'[skip] {pdf_file} (已有输出)', flush=True)
        continue

    print(f'\n=== {pdf_file} (slide {slide}) ===', flush=True)
    pdf_in = os.path.join(PDF_DIR, pdf_file)
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'
    cmd = [PYTHON, SCRIPT, pdf_in, '--slide', str(slide), '--no-vision']
    try:
        r = subprocess.run(cmd, capture_output=True, env=env, timeout=600, text=False)
        out = r.stdout.decode('utf-8', errors='replace') if r.stdout else ''
        err = r.stderr.decode('utf-8', errors='replace') if r.stderr else ''
        if r.returncode == 0:
            rec = {'pdf': pdf_file, 'slide': slide, 'ok': True}
            for line in out.split('\n'):
                line = line.strip()
                if '匹配句' in line: rec['matched'] = line
                if 'Highlights OK' in line: rec['highlights_ok'] = line
                if 'Removed' in line: rec['removed'] = line
                if '高亮页' in line: rec['hl_pages'] = line
            print('  OK', json.dumps(rec, ensure_ascii=False), flush=True)
            results.append(rec)
        else:
            print(f'  FAIL: {err[:200]}', flush=True)
            results.append({'pdf': pdf_file, 'slide': slide, 'ok': False, 'err': err[:200]})
    except Exception as e:
        print(f'  ERROR: {e}', flush=True)
        results.append({'pdf': pdf_file, 'slide': slide, 'ok': False, 'err': str(e)})
    time.sleep(0.5)

print(f'\n=== 总结: {sum(1 for r in results if r.get("ok"))}/{len(results)} 成功 ===', flush=True)
with open(os.path.join(OUT_BASE, '_batch_summary.json'), 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print('\n=== 输出结构 ===', flush=True)
for pn_dir in sorted(os.listdir(OUT_BASE)):
    full = os.path.join(OUT_BASE, pn_dir)
    if os.path.isdir(full):
        n_files = sum(1 for _ in os.scandir(full))
        pages_dir = os.path.join(full, pn_dir + '_highlight_pages')
        n_pages = len([f for f in os.listdir(pages_dir) if f.endswith('.jpg')]) if os.path.isdir(pages_dir) else 0
        print(f'  {pn_dir}/: {n_files} files, {n_pages} page images', flush=True)
