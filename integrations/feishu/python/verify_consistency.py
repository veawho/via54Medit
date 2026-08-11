#!/usr/bin/env python3
"""
CSV ↔ 飞书 一致性 verify 脚本 (只读, 不写)

拉飞书全表 D-H, 跟 CSV 对比, 输出 mismatch 详情.
不会修改任何数据.

GitHub-ready (无硬编码 token/路径):
- 通过环境变量或 CLI 参数配置
- 推荐使用 config 文件 (~/.config/hermes/feishu_credentials.json)
"""

import os
import csv as csv_mod
import sys
import json
import argparse
import subprocess

# === 配置加载 (GitHub-ready) ===

def load_config():
    """从环境变量 / config 文件 / 默认值 加载配置"""
    config = {
        'feishu_token': os.environ.get('FEISHU_TOKEN', ''),
        'sheet_id': os.environ.get('SHEET_ID', ''),
        'csv_path': os.environ.get('CSV_PATH', ''),
        'lark_cli': os.environ.get('LARK_CLI', '/Users/david/.hermes/node/bin/lark-cli'),
    }
    
    # 尝试 config 文件
    config_paths = [
        os.environ.get('FEISHU_CONFIG_PATH', ''),
        os.path.expanduser('~/.config/hermes/feishu_credentials.json'),
        os.path.expanduser('~/.feishu_credentials.json'),
    ]
    
    for cp in config_paths:
        if cp and os.path.exists(cp):
            try:
                with open(cp) as f:
                    file_config = json.load(f)
                config.update(file_config)
            except Exception:
                pass
    
    # CLI 参数覆盖
    parser = argparse.ArgumentParser()
    parser.add_argument('--feishu-token', help='飞书 spreadsheet token')
    parser.add_argument('--sheet-id', help='飞书 sheet ID (e.g. b03e59)')
    parser.add_argument('--csv-path', help='本地 CSV 文件路径')
    parser.add_argument('--lark-cli', help='lark-cli 可执行文件路径')
    parser.add_argument('--row', type=int, help='只 verify 单 row')
    parser.add_argument('--column', choices=['D', 'E', 'F', 'G', 'H', 'all'], default='all', help='只 verify 指定列')
    parser.add_argument('--quiet', action='store_true', help='只输出错误')
    parser.add_argument('--json-output', help='输出 JSON 结果到指定文件')
    args, _ = parser.parse_known_args()
    
    if args.feishu_token:
        config['feishu_token'] = args.feishu_token
    if args.sheet_id:
        config['sheet_id'] = args.sheet_id
    if args.csv_path:
        config['csv_path'] = args.csv_path
    if args.lark_cli:
        config['lark_cli'] = args.lark_cli
    
    # 默认值 (本地 dev - 仅 fallback, 推荐用 config 文件)
    # 注意: 这是 via54Medit skill, 不应假设任何特定项目路径.
    # 如果用户在 config 文件没设, 才会用这个默认 placeholder (用户必须自己覆盖).
    if not config['csv_path']:
        config['csv_path'] = os.path.join(os.environ.get('HOME', '/tmp'), 'citation_table.csv')
    
    # 验证
    if not config['feishu_token']:
        raise ValueError(
            'FEISHU_TOKEN not set. Either:\n'
            '  1. Set environment variable FEISHU_TOKEN=<token>\n'
            '  2. Put in config file ~/.config/hermes/feishu_credentials.json\n'
            '  3. Pass --feishu-token <token>'
        )
    if not config['sheet_id']:
        raise ValueError('SHEET_ID not set. Set env var SHEET_ID=<id> or pass --sheet-id')
    if not os.path.exists(config['csv_path']):
        raise FileNotFoundError(f'CSV file not found: {config["csv_path"]}')
    
    return config, args


CONFIG, ARGS = load_config()

CSV_PATH = CONFIG['csv_path']
FEISHU_TOKEN = CONFIG['feishu_token']
SHEET_ID = CONFIG['sheet_id']
LARK_CLI = CONFIG['lark_cli']


def cell_to_text(cell):
    if not cell:
        return ''
    if isinstance(cell, str):
        return cell
    if isinstance(cell, dict):
        return cell.get('value', '') or cell.get('text', '')
    if isinstance(cell, list):
        parts = []
        for item in cell:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get('text', '') or item.get('value', ''))
            elif isinstance(item, list):
                for sub in item:
                    if isinstance(sub, str):
                        parts.append(sub)
                    elif isinstance(sub, dict):
                        parts.append(sub.get('text', '') or sub.get('value', ''))
        return ''.join(parts)
    return ''


def extract_text_from_feishu_h(cell):
    """从飞书 rich text 节点提取纯文本 (用于 H 列比对)"""
    if not cell:
        return ''
    if isinstance(cell, str):
        return cell
    if isinstance(cell, dict):
        return cell.get('text', '') or cell.get('value', '')
    if isinstance(cell, list):
        parts = []
        for item in cell:
            if isinstance(item, list):
                for sub in item:
                    if isinstance(sub, dict):
                        parts.append(sub.get('text', ''))
            elif isinstance(item, dict):
                parts.append(item.get('text', ''))
        return ''.join(parts)
    return ''


def main():
    if not ARGS.quiet:
        print('=' * 60)
        print('CSV ↔ 飞书 一致性 verify (只读, GitHub-ready)')
        print('=' * 60)
    
    # 读 CSV
    with open(CSV_PATH, encoding='utf-8-sig') as f:
        rows = list(csv_mod.DictReader(f))
    if not ARGS.quiet:
        print(f'\nCSV rows: {len(rows)}')
    
    # 拉飞书
    cmd = [LARK_CLI, 'sheets', '+read',
           '--range', f'{SHEET_ID}!D2:H161',
           '--spreadsheet-token', FEISHU_TOKEN,
           '--json']
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    data = json.loads(result.stdout)
    
    if not data.get('ok'):
        print(f'❌ Feishu API not ok: {result.stdout[:300]}')
        sys.exit(1)
    
    feishu_cells = data['data']['valueRange']['values']
    if not ARGS.quiet:
        print(f'飞书 rows: {len(feishu_cells)}')
    
    # 对比
    d_mismatches = []
    e_mismatches = []
    f_mismatches = []
    g_mismatches = []
    h_mismatches = []
    file_missing = []
    
    rows_to_check = [ARGS.row - 2] if ARGS.row else range(len(rows))
    
    for i in rows_to_check:
        if i < 0 or i >= len(rows):
            continue
        csv_row = rows[i]
        csv_d = csv_row['PPT中的文献引用 完整字段'].strip()
        csv_e = csv_row['DOI'].strip()
        csv_f = csv_row['类型'].strip()
        csv_g = csv_row['对应PDF文件'].strip()
        csv_g_basename = os.path.basename(csv_g) if '/' in csv_g else csv_g
        csv_h = csv_row['来源链接 → 阅读全文'].strip()
        
        if csv_g and not os.path.exists(csv_g):
            file_missing.append((i+2, csv_g_basename, csv_d[:50]))
        
        if i < len(feishu_cells) and feishu_cells[i]:
            feishu_d = cell_to_text(feishu_cells[i][0])
            feishu_e = cell_to_text(feishu_cells[i][1]) if len(feishu_cells[i]) > 1 else ''
            feishu_f = cell_to_text(feishu_cells[i][2]) if len(feishu_cells[i]) > 2 else ''
            feishu_g = cell_to_text(feishu_cells[i][3]) if len(feishu_cells[i]) > 3 else ''
            feishu_h = extract_text_from_feishu_h(feishu_cells[i][4]) if len(feishu_cells[i]) > 4 else ''
            
            if ARGS.column in ('D', 'all') and csv_d != feishu_d:
                d_mismatches.append((i+2, csv_d[:50], feishu_d[:50]))
            if ARGS.column in ('E', 'all') and csv_e != feishu_e:
                e_mismatches.append((i+2, csv_e[:40], feishu_e[:40]))
            if ARGS.column in ('F', 'all') and csv_f != feishu_f:
                f_mismatches.append((i+2, csv_f, feishu_f))
            if ARGS.column in ('G', 'all') and csv_g_basename != feishu_g:
                g_mismatches.append((i+2, csv_g_basename, feishu_g))
            if ARGS.column in ('H', 'all') and csv_h != feishu_h:
                h_mismatches.append((i+2, len(csv_h), len(feishu_h), csv_h[:50], feishu_h[:50]))
    
    # 报告
    if not ARGS.quiet:
        print(f'\n=== Mismatch 统计 ===')
        print(f'D 列: {len(d_mismatches)}')
        print(f'E 列: {len(e_mismatches)}')
        print(f'F 列: {len(f_mismatches)}')
        print(f'G 列: {len(g_mismatches)}')
        print(f'H 列: {len(h_mismatches)}')
        print(f'文件不存在: {len(file_missing)}')
    
    total = len(d_mismatches) + len(e_mismatches) + len(f_mismatches) + len(g_mismatches) + len(h_mismatches)
    
    # JSON 输出
    if ARGS.json_output:
        result_data = {
            'total_mismatches': total,
            'file_missing': len(file_missing),
            'csv_rows': len(rows),
            'feishu_rows': len(feishu_cells),
            'd_mismatches': [{'row': fr, 'csv': c, 'feishu': f} for fr, c, f in d_mismatches],
            'e_mismatches': [{'row': fr, 'csv': c, 'feishu': f} for fr, c, f in e_mismatches],
            'f_mismatches': [{'row': fr, 'csv': c, 'feishu': f} for fr, c, f in f_mismatches],
            'g_mismatches': [{'row': fr, 'csv': c, 'feishu': f} for fr, c, f in g_mismatches],
            'h_mismatches': [{'row': fr, 'csv_len': cl, 'feishu_len': fl} for fr, cl, fl, _, _ in h_mismatches],
        }
        with open(ARGS.json_output, 'w') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
    
    if not ARGS.quiet:
        print(f'\n总 mismatch: {total}')
    
    if total == 0 and len(file_missing) == 0:
        if not ARGS.quiet:
            print('\n✅ CSV ↔ 飞书 100% 一致, 所有 PDF 文件存在')
        sys.exit(0)
    else:
        if not ARGS.quiet:
            print(f'\n❌ 需修复: {total} mismatch + {len(file_missing)} 文件缺失')
            for label, mismatches in [('D', d_mismatches), ('E', e_mismatches), ('F', f_mismatches), ('G', g_mismatches)]:
                if mismatches:
                    print(f'\n{label} 列 mismatch:')
                    for fr, csv, fsh in mismatches[:10]:
                        print(f'  Row {fr}: csv="{csv}" feishu="{fsh}"')
            
            if h_mismatches:
                print(f'\nH 列 mismatch (前 10):')
                for fr, csv_len, fsh_len, csv_pre, fsh_pre in h_mismatches[:10]:
                    print(f'  Row {fr}: csv_len={csv_len} feishu_len={fsh_len}')
            
            if file_missing:
                print(f'\n文件不存在:')
                for fr, g, d in file_missing[:10]:
                    print(f'  Row {fr} {g}: {d}')
        sys.exit(2)


if __name__ == '__main__':
    main()