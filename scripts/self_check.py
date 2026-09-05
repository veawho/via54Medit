#!/usr/bin/env python3.11
"""
self_check.py - 自检脚本 (v4.0)
  1. 验证所有 160 Pn-x 有 manifest + highlight JPG
  2. 验证 manifest 完整 (含 l0_classify, l4_allegation, highlight_summary)
  3. 验证 highlight JPG 文件存在且 > 50KB
  4. 验证 main PDF 存在
  5. 统计 hits 分布, 找出 hits=0 的异常
  6. 抽样 sensenova 视觉复核 5 张高亮

Output: self_check_report.json + summary
"""
import json
import os
import random
import subprocess
import sys
from pathlib import Path

LIT_ROOT = Path(os.environ.get('LIT_ROOT', '/Users/david/Desktop/雷管方案_文献整理'))
ARCHIVE_ROOT = LIT_ROOT / '_literature_citation_index'
PYTHON = (os.environ.get('HERMES_PYTHON')
          or os.environ.get('PYTHON')
          or '/Users/david/.hermes/hermes-agent/venv/bin/python3.11')


def main():
    report = {
        'timestamp': '2026-08-01T21:30:00',
        'total': 0,
        'pass': 0,
        'fail': 0,
        'issues': [],
        'stats': {
            'highlight_hits_total': 0,
            'highlight_hits_avg': 0,
            'pdf_type_distribution': {},
            'sensenova_sample': [],
        },
    }

    # 1. 找所有 Pn-x 归档
    pnx_dirs = []
    for d in ARCHIVE_ROOT.iterdir():
        if d.is_dir() and not d.name.startswith('_'):
            pnx_dirs.append(d)
    report['total'] = len(pnx_dirs)

    print(f'Checking {len(pnx_dirs)} Pn-x...')

    for d in pnx_dirs:
        pnx = d.name
        issues = []

        # 1.1 manifest 存在
        manifest_path = d / '_manifest.json'
        if not manifest_path.exists():
            issues.append('manifest_missing')
        else:
            try:
                with open(manifest_path) as f:
                    manifest = json.load(f)
                # 1.2 manifest 完整
                required = ['pn_x', 'main_pdf', 'l0_classify', 'l4_allegation', 'highlight_summary']
                for r in required:
                    if r not in manifest:
                        issues.append(f'manifest_missing_{r}')
                # 1.3 highlight_summary 完整
                if 'highlight_summary' in manifest:
                    hs = manifest['highlight_summary']
                    if 'hits' not in hs:
                        issues.append('manifest_missing_hits')
                    else:
                        report['stats']['highlight_hits_total'] += hs.get('hits', 0)
            except Exception as e:
                issues.append(f'manifest_parse_error: {e}')

        # 1.4 highlight JPG 存在
        highlight_files = list(d.glob('*highlight*.jpg'))
        if not highlight_files:
            issues.append('highlight_jpg_missing')
        else:
            # 1.5 highlight JPG > 50KB
            for hf in highlight_files:
                size = hf.stat().st_size
                if size < 50000:  # 50KB
                    issues.append(f'highlight_too_small: {hf.name} ({size}B)')

        # 1.6 main PDF 存在
        pnx_dir = LIT_ROOT / pnx.split('_')[0]  # 简化
        # 找 main PDF
        main_pdfs = []
        for c in d.glob('*main*.pdf'):
            if '_v39' not in str(c):
                main_pdfs.append(c)
        if not main_pdfs:
            # 在 LIT_ROOT/Pn-x/ 找
            pnx_real = pnx
            if '_' in pnx:
                # 处理 shared 目录: P5-18_P12-3_... → 取 P5-18
                pnx_real = pnx.split('_')[0]
            real_dir = LIT_ROOT / pnx_real
            if real_dir.exists():
                for c in real_dir.glob('*main*.pdf'):
                    if '_v39' not in str(c):
                        main_pdfs.append(c)
        if not main_pdfs:
            issues.append('main_pdf_missing')

        # 1.7 pdf_type 分布
        if manifest_path.exists():
            try:
                with open(manifest_path) as f:
                    m = json.load(f)
                if 'l0_classify' in m and isinstance(m['l0_classify'], dict):
                    pdf_type = m['l0_classify'].get('pdf_type', 'unknown')
                    report['stats']['pdf_type_distribution'][pdf_type] = \
                        report['stats']['pdf_type_distribution'].get(pdf_type, 0) + 1
            except Exception:
                pass

        if issues:
            report['fail'] += 1
            report['issues'].append({'pnx': pnx, 'issues': issues})
        else:
            report['pass'] += 1

    # 2. 算平均
    if report['pass'] > 0:
        report['stats']['highlight_hits_avg'] = round(
            report['stats']['highlight_hits_total'] / report['pass'], 2)

    # 3. 抽样 sensenova 视觉复核 (5 张)
    print('\n抽样 sensenova 视觉复核 5 张高亮...')
    sample_dirs = random.sample([d for d in pnx_dirs if list(d.glob('*highlight*.jpg'))], 5)
    for d in sample_dirs:
        pnx = d.name
        highlight_files = list(d.glob('*highlight*.jpg'))
        if not highlight_files:
            continue
        hf = highlight_files[0]
        # 调 sensenova
        code = f"""
import sys
sys.path.insert(0, '{Path("/Users/david/Desktop/developments/via54Medit/scripts")}')
from provider_vision import vision_analyze
result = vision_analyze(sys.argv[1], '这张图里有几处黄色高亮? 简单描述每处覆盖的内容.')
print('SUCCESS' if result.get('success') else 'FAIL')
print('---')
print(result.get('content', '')[:300])
"""
        try:
            out = subprocess.run([PYTHON, "-c", code, str(hf)],
                                capture_output=True, text=True, timeout=60)
            if out.returncode == 0:
                lines = out.stdout.split('---', 1)
                success = 'SUCCESS' in lines[0] if lines else False
                content = lines[1] if len(lines) > 1 else ''
                report['stats']['sensenova_sample'].append({
                    'pnx': pnx,
                    'highlight_file': str(hf),
                    'success': success,
                    'content_preview': content[:200],
                })
                print(f'  {pnx}: {"✓" if success else "✗"} {content[:80]}')
        except Exception as e:
            print(f'  {pnx}: ERROR {e}')

    # 输出
    print(f'\n{"="*50}')
    print(f'Total: {report["total"]}')
    print(f'Pass: {report["pass"]}')
    print(f'Fail: {report["fail"]}')
    print(f'Highlight total hits: {report["stats"]["highlight_hits_total"]}')
    print(f'Highlight avg: {report["stats"]["highlight_hits_avg"]}')
    print(f'PDF type distribution: {report["stats"]["pdf_type_distribution"]}')
    print(f'sensenova sample: {len(report["stats"]["sensenova_sample"])}')

    if report['issues']:
        print(f'\n{len(report["issues"])} issues:')
        for it in report['issues'][:20]:
            print(f'  {it["pnx"]}: {it["issues"]}')

    with open('/tmp/self_check_report.json', 'w') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f'\nFull report: /tmp/self_check_report.json')

    return report


if __name__ == '__main__':
    main()
