#!/usr/bin/env python3
"""逐个重跑所有 hl_p*.py: 先带 run 参数, 失败则直接执行; 成功后 fitz 渲染"""
import subprocess, sys, os, glob, re

BASE = "/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI"
logf = open('/tmp/rerun_all.log', 'w')
fail = []

# 脚本来源: 优先 toolkit/scripts(沉淀), 回退 /tmp(工作区)
SCRIPT_DIRS = ['/Users/david/Desktop/TMA_文献整理/_highlight_toolkit/scripts', '/tmp']
# 按 basename 去重(toolkit/scripts 优先, /tmp 回退)
by_name = {}
for sd in SCRIPT_DIRS:
    for f in glob.glob(os.path.join(sd, 'hl_p*.py')):
        by_name.setdefault(os.path.basename(f), f)
scripts = sorted(by_name.values())
# 排除非 Pn-x 脚本与 _v2/_full 变体
scripts = [s for s in scripts if re.search(r'hl_p\d+-\d+\.py$', os.path.basename(s))]
if __name__ == "__main__":
    print(f'{len(scripts)} scripts to rerun')

    for script in scripts:
        name = os.path.basename(script)
        pn = 'P' + re.match(r'hl_p(\d+-\d+)\.py', name).group(1).upper()
        outdir = os.path.join(BASE, pn)
        if not os.path.isdir(outdir):
            fail.append((pn, 'NO_OUTDIR'))
            continue
        ok = False
        for args in ([script, 'run'], [script]):
            try:
                r = subprocess.run([sys.executable] + args, capture_output=True, text=True, timeout=180, cwd='/tmp')
                logf.write(f'--- {pn} {args[-1] if len(args)>1 else "direct"}\n')
                logf.write(r.stdout[-2000:])
                logf.write(r.stderr[-2000:])
                if r.returncode == 0:
                    ok = True
                    break
            except subprocess.TimeoutExpired:
                logf.write(f'--- {pn} TIMEOUT {args}\n')
                break
            except Exception as e:
                logf.write(f'--- {pn} EXC {e}\n')
        if not ok:
            fail.append((pn, 'SCRIPT_FAIL'))
            continue
        hp = os.path.join(outdir, f'{pn}_highlight.pdf')
        if not os.path.exists(hp):
            fail.append((pn, 'NO_OUTPUT_PDF'))
            continue
        pages = os.path.join(outdir, f'{pn}_highlight_pages')
        import shutil
        if os.path.isdir(pages):
            shutil.rmtree(pages)
        os.makedirs(pages)
        try:
            r = subprocess.run([sys.executable, '/tmp/render_fitz.py', hp, pages, '100'],
                               capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                fail.append((pn, 'RENDER_FAIL'))
        except Exception as e:
            fail.append((pn, f'RENDER_EXC {e}'))
        print(f'[{pn}] OK')

    logf.close()
    print('\n=== FAILURES ===')
    for pn, msg in fail:
        print(f'  {pn}: {msg}')
    print(f'total {len(scripts)}, failed {len(fail)}')
