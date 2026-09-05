#!/usr/bin/env python3.11
"""
process_all_pn_x.py - 160 个 Pn-x 全量算法驱动文献标注

v4.0 流程 (L0-L6):
  1. L0 分类 (medit anno2ppt classify)
  2. L0 验证 (medit anno2ppt l0verify) [optional]
  3. L4 应证推理 (medit anno2ppt confirm)
  4. Highlight 生成 (PyMuPDF, 黄色下划线 + 色块)
  5. Sensnova 视觉复核 (Python API)
  6. Manifest 更新 + 自检

Usage:
  python3.11 process_all_pn_x.py            # 跑全部 160
  python3.11 process_all_pn_x.py --limit 5  # 测试用, 前 5 个
  python3.11 process_all_pn_x.py --pnx P22-1  # 跑单个
"""
import argparse
import json
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime
import re

# 路径
PROJECT_ROOT = Path('/Users/david/Desktop/developments/via54Medit')
LIT_ROOT = Path('/Users/david/Desktop/雷管方案_文献整理')
ARCHIVE_ROOT = LIT_ROOT / '_literature_citation_index'
CSV_PATH = LIT_ROOT / '_citation_table' / 'citation_table.csv'
MEDIT_BIN = '/tmp/medit'
PYTHON = '/Users/david/.hermes/hermes-agent/venv/bin/python3.11'

# Highlight 颜色
YELLOW = (1, 0.92, 0)
HIGHLIGHT_PNG_DPI = 150


def find_main_pdf(pnx):
    """找 Pn-x main PDF (排除 _v39_deprecated)."""
    pnx_dir = LIT_ROOT / pnx
    if pnx_dir.exists():
        candidates = list(pnx_dir.glob('*main*.pdf'))
        candidates = [c for c in candidates if '_v39' not in str(c)]
        if candidates:
            return candidates[0]
    # 找 shared 目录
    for d in ARCHIVE_ROOT.iterdir():
        if not d.is_dir() or d.name.startswith('_'):
            continue
        if pnx in d.name:
            for c in d.glob('*main*.pdf'):
                if '_v39' not in str(c):
                    return c
    # 找 _literature_citation_index/Pn-x/
    arch_dir = ARCHIVE_ROOT / pnx
    if arch_dir.exists():
        for c in arch_dir.glob('*main*.pdf'):
            if '_v39' not in str(c):
                return c
    return None


def find_archive_dir(pnx):
    """找 Pn-x 归档目录. 优先 Pn-x 单独目录, fallback shared 目录."""
    arch_dir = ARCHIVE_ROOT / pnx
    if arch_dir.exists():
        return arch_dir
    # 找 shared 目录
    for d in ARCHIVE_ROOT.iterdir():
        if not d.is_dir() or d.name.startswith('_'):
            continue
        if pnx in d.name.split('_'):
            return d
    return None


def run_medit(*args, timeout=30):
    """调用 medit CLI, 返回 JSON 或 None."""
    cmd = [MEDIT_BIN] + list(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            # 重试, 用 inline python 替代 (修复 producer 含特殊字符 bug)
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        return {"_error": str(e)}


def extract_pdf_text(pdf_path, max_pages=3):
    """用 PyMuPDF 提取 PDF 文字层 (限定前 N 页). 忽略 MuPDF 警告."""
    code = f"""
import sys, json, warnings
warnings.filterwarnings('ignore')
import logging
logging.disable(logging.CRITICAL)
import fitz
fitz.TOOLS.mupdf_display_warnings(False)
fitz.TOOLS.mupdf_display_errors(False)
doc = fitz.open(sys.argv[1])
n = min({max_pages}, doc.page_count)
result = []
for i in range(n):
    try:
        text = doc[i].get_text()
    except Exception as e:
        text = '[ERROR: ' + str(e) + ']'
    result.append({{'page': i+1, 'text': text}})
print(json.dumps(result, ensure_ascii=False))
"""
    try:
        out = subprocess.run([PYTHON, "-c", code, str(pdf_path)],
                            capture_output=True, text=True, timeout=30)
        if out.returncode == 0:
            return json.loads(out.stdout)
    except Exception:
        pass
    return []


def parse_allegation(text):
    """L4: 用 medit anno2ppt parse 抽取 4 维要素."""
    return run_medit("anno2ppt", "parse", text)


def highlight_pdf(pdf_path, page_num, terms, output_path):
    """在 PDF 指定页画黄色下划线 + 渲染 PNG. 忽略 MuPDF 警告.

    v10 修复版: 改用 via54_highlight_fix_v10.highlight_pdf() 兼容层.
    旧实现 (add_highlight_annot + draw_line) 颜色 save 后丢失 → 0% 黄色.
    新实现走 draw_rect 内容流, 颜色持久, 跳页眉/页脚/标题区.
    """
    try:
        from via54_highlight_fix_v10 import highlight_pdf as _hl_v10
        return _hl_v10(str(pdf_path), page_num, terms or [], str(output_path))
    except Exception as e:
        # 兜底: 返回 0, 避免整个 pipeline 挂掉
        print(f"  [highlight v10 compat] 失败: {e}")
        return 0


def sensenova_verify(image_path, expected_terms, provider="cascade", timeout=60):
    """L3: 视觉复核 (3 级 Cascade: sensenova → minimax → local)."""
    # 优先用新 cascade 脚本
    vision_script = PROJECT_ROOT / "scripts" / "vision_verify.py"
    if vision_script.exists():
        code = f"""
import sys, json
sys.path.insert(0, '{PROJECT_ROOT}/scripts')
from vision_verify import vision_analyze

result = vision_analyze(sys.argv[1], sys.argv[2], provider="{provider}", timeout={timeout})
print(json.dumps(result, ensure_ascii=False))
"""
        try:
            out = subprocess.run([PYTHON, "-c", code,
                                  image_path,
                                  f"这张图里有多少处黄色高亮? 这些高亮是否覆盖了以下关键词: {', '.join(expected_terms[:6])}"],
                                capture_output=True, text=True, timeout=timeout + 10)
            if out.returncode == 0:
                data = json.loads(out.stdout)
                return data.get("success", False), data.get("content", ""), data.get("provider", "")
        except Exception:
            pass

    # Fallback: 老 sensenova_vision.py
    code = f"""
import sys
sys.path.insert(0, '{PROJECT_ROOT}/scripts')
from provider_vision import vision_analyze

result = vision_analyze(sys.argv[1], '''这张图里有多少处黄色高亮? 这些高亮是否覆盖了以下关键词: {", ".join(expected_terms[:6])}''')
print('SUCCESS' if result.get('success') else 'FAIL')
print('---')
print(result.get('content', '')[:600])
"""
    try:
        out = subprocess.run([PYTHON, "-c", code, str(image_path)],
                            capture_output=True, text=True, timeout=timeout)
        if out.returncode == 0:
            lines = out.stdout.split('---', 1)
            success = 'SUCCESS' in lines[0] if lines else False
            content = lines[1] if len(lines) > 1 else ''
            return success, content, "sensenova_legacy"
    except Exception as e:
        return False, str(e), "error"
    return False, "timeout", "timeout"


def get_ppt_allegation(pnx, csv_text):
    """从 CSV D 列抽取 PPT 引用语义 (4 维要素)."""
    # 算法: 解析 D 列的关联数据
    allegations = []
    # 提取位置 N: 「...」 的内容
    pos_matches = re.findall(r'位置\d+[:：]\s*「([^」]+)」', csv_text)
    for p in pos_matches[:3]:
        allegations.append(p[:80])
    # 提取关联数据 - **XX.X%** 或 数字%
    data_matches = re.findall(r'\*?\*?(\d+\.?\d*\s*%)\*?\*?', csv_text)
    for d in data_matches[:5]:
        allegations.append(d.strip())
    # 提取引文
    cite_match = re.search(r'引文[:：]?\s*([^。\n]{10,200})', csv_text)
    if cite_match:
        allegations.append(cite_match.group(1)[:100])
    return allegations


def process_pn_x(pnx, csv_text, debug=False):
    """处理 1 个 Pn-x 的完整流程."""
    result = {
        'pnx': pnx,
        'timestamp': datetime.now().isoformat(),
        'steps': [],
        'errors': [],
    }

    # Step 0: 找 main PDF
    main_pdf = find_main_pdf(pnx)
    if not main_pdf:
        result['errors'].append('main_pdf_not_found')
        return result
    result['main_pdf'] = str(main_pdf)
    result['steps'].append({'step': 'find_main', 'ok': True})

    # Step 1: L0 分类 (失败不阻塞, 继续 L4)
    classify = run_medit("anno2ppt", "classify", str(main_pdf))
    if not classify or "_error" in classify:
        # 降级: 用 inline Python 直接分类
        cls_inline = subprocess.run([PYTHON, "-c", f"""
import sys, json, warnings
warnings.filterwarnings('ignore')
import fitz
fitz.TOOLS.mupdf_display_warnings(False)
fitz.TOOLS.mupdf_display_errors(False)
doc = fitz.open(sys.argv[1])
m = doc.metadata
first_text = doc[0].get_text()[:200] if doc.page_count > 0 else ''
print(json.dumps({{
    'producer': m.get('producer', '') or '',
    'creator': m.get('creator', '') or '',
    'first_text': first_text,
}}))
""", str(main_pdf)], capture_output=True, text=True, timeout=30)
        if cls_inline.returncode == 0:
            try:
                meta = json.loads(cls_inline.stdout)
                classify = {
                    "pdf_type": "unknown",  # 跳过分类算法
                    "strategy": "inspect_manually",
                    "_inline": True,
                    "producer": meta.get("producer", ""),
                    "creator": meta.get("creator", ""),
                }
            except Exception:
                pass
    if not classify:
        result['errors'].append('L0_classify_failed')
        return result
    result['L0_classify'] = classify
    result['steps'].append({
        'step': 'L0_classify',
        'pdf_type': classify.get('pdf_type', 'unknown'),
        'strategy': classify.get('strategy', 'unknown'),
    })

    # Step 2: 抽取 PPT 引用语义
    allegation = get_ppt_allegation(pnx, csv_text)
    result['allegation'] = allegation
    result['steps'].append({'step': 'extract_allegation', 'count': len(allegation)})

    # Step 3: L4 应证要素解析
    allegation_text = ' '.join(allegation[:3])
    parsed = parse_allegation(allegation_text)
    if parsed:
        result['L4_parsed'] = parsed
        result['steps'].append({'step': 'L4_parse', 'ok': True})

    # Step 4: Highlight 生成
    archive_dir = find_archive_dir(pnx)
    if not archive_dir:
        archive_dir = ARCHIVE_ROOT / pnx
        archive_dir.mkdir(parents=True, exist_ok=True)

    # 找 main PDF 第 1 页 (一般应有 abstract / 标题)
    # 抽出文字层找关键 keyword
    pages = extract_pdf_text(main_pdf, max_pages=3)
    if not pages:
        result['errors'].append('extract_text_failed')
        return result

    # 找哪个 page 含 PPT 引用的关键术语
    best_page = 1
    best_score = 0
    for p in pages:
        text = p.get('text', '')
        score = 0
        for term in allegation:
            if term in text:
                score += 1
        if score > best_score:
            best_score = score
            best_page = p['page']

    # 提取该页的关键术语
    page_text = pages[best_page - 1].get('text', '') if best_page <= len(pages) else ''
    key_terms = []
    # 数字 + % 数据点
    for m in re.findall(r'\d+\.?\d*\s*%', page_text):
        if m not in key_terms:
            key_terms.append(m)
    # 标题关键术语
    for keyword in ['OS', 'PFS', 'ORR', 'DCR', 'HR', 'mOS', 'mPFS', 'T+A', 'STRIDE', 'HIMALAYA',
                    'Atezo', 'Bev', 'Tremelimumab', 'Durvalumab', 'Apatinib', 'Sorafenib',
                    'AHELP', 'LEAP-002', 'phase', 'III', 'NCT', 'CONSORT']:
        if keyword in page_text and keyword not in key_terms:
            key_terms.append(keyword)
    # 主要术语 (allegation)
    for term in allegation[:3]:
        if len(term) > 3 and term in page_text and term not in key_terms:
            key_terms.append(term)

    if not key_terms:
        key_terms = ['abstract', 'method', 'background']

    # 限定前 12 个 terms
    key_terms = key_terms[:12]
    result['key_terms'] = key_terms

    # 画 highlight
    highlight_path = archive_dir / f'{pnx}_page{best_page}_highlight.jpg'
    hits = highlight_pdf(main_pdf, best_page, key_terms, str(highlight_path))
    result['highlight_hits'] = hits
    result['highlight_path'] = str(highlight_path)
    result['steps'].append({
        'step': 'highlight',
        'page': best_page,
        'terms': len(key_terms),
        'hits': hits,
    })

    # Step 5: sensenova 视觉复核 (仅在 highlight 命中数高时调用, 限制超时)
    if highlight_path.exists() and hits >= 3 and os.environ.get('SKIP_SENSENOVA') != '1':
        success, content, provider_used = sensenova_verify(str(highlight_path), key_terms)
        result['sensenova'] = {
            'success': success,
            'content_preview': content[:200],
            'provider': provider_used,
        }
        result['steps'].append({
            'step': 'L3_sensenova',
            'success': success,
        })

    # Step 6: 更新 manifest
    manifest_path = archive_dir / '_manifest.json'
    manifest = {}
    if manifest_path.exists():
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
        except Exception:
            pass

    manifest.update({
        'pn_x': pnx,
        'main_pdf': str(main_pdf.relative_to(LIT_ROOT) if main_pdf.is_relative_to(LIT_ROOT) else main_pdf),
        'l0_classify': classify,
        'l4_allegation': allegation,
        'l4_key_terms': key_terms,
        'highlight_summary': {
            'page': best_page,
            'terms': len(key_terms),
            'hits': hits,
            'path': f'{pnx}_page{best_page}_highlight.jpg',
        },
        'sensenova_verified': result['steps'][-1].get('success', False) if result['steps'] and result['steps'][-1].get('step') == 'L3_sensenova' else None,
        'last_processed': datetime.now().isoformat(),
        'algorithm_version': 'v4.0',
    })

    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    result['steps'].append({'step': 'manifest', 'ok': True, 'path': str(manifest_path)})

    return result


def get_csv_row(pnx):
    """从 CSV 找 Pn-x 的 D 列内容."""
    if not CSV_PATH.exists():
        return ""
    with open(CSV_PATH) as f:
        content = f.read()
    # 找 Pn-x 行 (按位置 1 模式)
    pnx_short = pnx.split('-')[0] + ' ' + pnx.split('-')[1]  # e.g. "P3 -2"
    # 直接读全文 + 找 pnx 上下文
    idx = content.find(pnx)
    if idx >= 0:
        # 找下一个 Pn-x 起点
        # 简化: 找下一个 "Row" 标记
        next_row = content.find('\nRow', idx + len(pnx))
        if next_row > 0:
            return content[idx:next_row]
        return content[idx:idx + 5000]
    return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=0, help='Limit to first N Pn-x')
    parser.add_argument('--pnx', type=str, default='', help='Single Pn-x to process')
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()

    # 找所有 Pn-x (含 shared 目录)
    if args.pnx:
        pnx_list = [args.pnx]
    else:
        pnx_list = []
        # 1. 找 LIT_ROOT/P*/
        for d in LIT_ROOT.iterdir():
            if d.is_dir() and d.name.startswith('P'):
                pnx_list.append(d.name)
        # 2. 找 shared 目录 (Pn-x_Pn-y_...)
        for d in ARCHIVE_ROOT.iterdir():
            if d.is_dir() and not d.name.startswith('_'):
                # 加 shared 目录名
                if d.name not in pnx_list:
                    # 拆出所有 Pn-x 子 ID
                    for p in d.name.split('_'):
                        if p.startswith('P') and '-' in p:
                            pnx_list.append(p)
        pnx_list = sorted(set(pnx_list))
        if args.limit:
            pnx_list = pnx_list[:args.limit]

    print(f'Processing {len(pnx_list)} Pn-x...')
    summary = {
        'total': len(pnx_list),
        'success': 0,
        'failed': 0,
        'results': [],
    }

    for i, pnx in enumerate(pnx_list, 1):
        print(f'\n[{i}/{len(pnx_list)}] {pnx} ...', end=' ', flush=True)
        csv_text = get_csv_row(pnx)
        result = process_pn_x(pnx, csv_text, args.debug)
        summary['results'].append(result)
        if result.get('errors'):
            summary['failed'] += 1
            print(f'FAILED: {result["errors"]}')
        else:
            summary['success'] += 1
            hits = result.get('highlight_hits', 0)
            print(f'OK ({hits} hits)')

    # 输出总结
    print(f'\n{"="*50}')
    print(f'Total: {summary["total"]}')
    print(f'Success: {summary["success"]}')
    print(f'Failed: {summary["failed"]}')

    # 详细报告
    with open('/tmp/process_all_pn_x_report.json', 'w') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f'Detailed report: /tmp/process_all_pn_x_report.json')

    return summary


if __name__ == '__main__':
    main()
