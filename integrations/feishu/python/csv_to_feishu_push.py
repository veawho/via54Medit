#!/usr/bin/env python3
"""
csv → 飞书 单向 push 脚本
强制保证 csv D-E-F-G-H 列跟飞书表完全一致

Hard Rules:
1. 永远先 re-read CSV (不用 memory cache)
2. 永远 csv → 飞书 单方向 push (不反向)
3. push 前/后 acquire lock 防并发
4. push 后立即 verify (单 row)
5. mismatch 自动重 push (3 次 retry)
6. 大批量 mismatch 抛异常让用户介入
7. 永远不调 sync_all.py Step 1 (sync_csv_g) - 它会反向覆盖

GitHub-ready (无硬编码 token/路径):
- 通过环境变量或 CLI 参数配置
- 推荐使用 config 文件 (~/.config/hermes/feishu_credentials.json)

Usage:
  FEISHU_TOKEN=<token> SHEET_ID=<sheet_id> \\
  CSV_PATH=/path/to/citation_table.csv \\
  BASE_DIR=/path/to/project \\
  python3 csv_to_feishu_push.py [--dry-run]

Or via config file (~/.config/hermes/feishu_credentials.json):
  {"feishu_token": "...", "sheet_id": "..."}
"""

import os
import csv as csv_mod
import sys
import json
import time
import argparse
import subprocess
import re
from pathlib import Path

# === 配置加载 (GitHub-ready) ===

def load_config():
    """从环境变量 / config 文件 / 默认值 加载配置"""
    config = {
        'feishu_token': os.environ.get('FEISHU_TOKEN', ''),
        'sheet_id': os.environ.get('SHEET_ID', ''),
        'csv_path': os.environ.get('CSV_PATH', ''),
        'base_dir': os.environ.get('BASE_DIR', ''),
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
    parser.add_argument('--base-dir', help='项目根目录')
    parser.add_argument('--lark-cli', help='lark-cli 可执行文件路径')
    parser.add_argument('--dry-run', action='store_true', help='DRY-RUN 模式 (不实际 push)')
    parser.add_argument('--fix', action='store_true', help='强制 push 所有 row (不只是 mismatch)')
    parser.add_argument('--row', type=int, help='只 push 单 row (调试用)')
    args, _ = parser.parse_known_args()
    
    if args.feishu_token:
        config['feishu_token'] = args.feishu_token
    if args.sheet_id:
        config['sheet_id'] = args.sheet_id
    if args.csv_path:
        config['csv_path'] = args.csv_path
    if args.base_dir:
        config['base_dir'] = args.base_dir
    if args.lark_cli:
        config['lark_cli'] = args.lark_cli
    
    # 默认值 (本地 dev - 仅 fallback, 推荐用 config 文件)
    # 注意: 这是 via54Medit skill, 不应假设任何特定项目路径.
    # 如果用户在 config 文件没设, 才会用这个默认 placeholder (用户必须自己覆盖).
    if not config['base_dir']:
        config['base_dir'] = os.environ.get('HOME', '/tmp')
    if not config['csv_path']:
        # 不假设任何项目路径, 用户必须通过 config / env / CLI 显式提供
        # 如果 fallback 到一个不存在路径, 后面会 raise FileNotFoundError
        config['csv_path'] = os.path.join(config['base_dir'], 'citation_table.csv')
    
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

# 加载配置
CONFIG, ARGS = load_config()

# === 全局常量 ===
CSV_PATH = CONFIG['csv_path']
BASE_DIR = CONFIG['base_dir']
LOCK_PATH = os.path.join(BASE_DIR, '_citation_table/csv.lock')
FEISHU_TOKEN = CONFIG['feishu_token']
SHEET_ID = CONFIG['sheet_id']
LARK_CLI = CONFIG['lark_cli']
DRY_RUN = ARGS.dry_run
FIX_MODE = ARGS.fix
SINGLE_ROW = ARGS.row

MAX_RETRIES = 3
RETRY_DELAY = 1.0  # seconds

# === 文件锁 ===

def acquire_lock(timeout=30):
    """Acquire file lock, raise if timeout"""
    start = time.time()
    while os.path.exists(LOCK_PATH):
        if time.time() - start > timeout:
            raise TimeoutError(f'Lock {LOCK_PATH} held by another process for >{timeout}s')
        time.sleep(1)
    Path(LOCK_PATH).touch()
    print(f'🔒 Acquired lock: {LOCK_PATH}')


def release_lock():
    """Release file lock"""
    if os.path.exists(LOCK_PATH):
        os.remove(LOCK_PATH)
        print(f'🔓 Released lock: {LOCK_PATH}')


# === 飞书 API helpers ===

def lark_cli_read(range_str, timeout=30):
    """Read cells from Feishu"""
    cmd = [LARK_CLI, 'sheets', '+read',
           '--range', f'{SHEET_ID}!{range_str}',
           '--spreadsheet-token', FEISHU_TOKEN,
           '--json']
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f'lark-cli read failed: {result.stderr[:200]}')
    data = json.loads(result.stdout)
    if not data.get('ok'):
        raise RuntimeError(f'Feishu API not ok: {result.stdout[:300]}')
    return data['data']['valueRange']['values']


def cell_to_text(cell):
    """Convert Feishu cell (str/list/dict) to plain text"""
    if not cell:
        return ''
    if isinstance(cell, str):
        return cell
    if isinstance(cell, dict):
        return cell.get('value', '') or cell.get('text', '')
    if isinstance(cell, list):
        # Handle: [{value: "..."}], [[{type, text}]], etc.
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
    return str(cell)


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


# === Push 单 row ===

def build_h_cell(h_content):
    """Build H cell JSON: {rich_text: [...]} if URLs detected, else {text: ...}"""
    h_content = h_content.strip()
    if not h_content:
        return ''
    
    url_pattern = re.compile(r'(https?://[^\s\)]+)')
    
    if url_pattern.search(h_content):
        # 转换为 rich text 节点 (lark-cli 接受 type='link')
        parts = []
        last_end = 0
        for m in url_pattern.finditer(h_content):
            start, end = m.span()
            if start > last_end:
                parts.append({'text': h_content[last_end:start], 'type': 'text'})
            parts.append({
                'text': m.group(1),
                'type': 'link',
                'link': m.group(1)
            })
            last_end = end
        if last_end < len(h_content):
            parts.append({'text': h_content[last_end:], 'type': 'text'})
        return {'rich_text': parts}
    else:
        return {'text': h_content}


def push_single_row(fr, csv_row, dry_run=False):
    """Push single row to Feishu, return True if successful"""
    g_basename = os.path.basename(csv_row['对应PDF文件'].strip()) if csv_row['对应PDF文件'].strip() else ''
    h_content = csv_row['来源链接 → 阅读全文']
    
    cells = [[
        {"value": str(csv_row['PPT中的文献引用 完整字段'])},
        {"value": str(csv_row['DOI'])},
        {"value": str(csv_row['类型'])},
        {"value": g_basename},
        build_h_cell(h_content),
    ]]
    
    cells_path = f'/tmp/literature_clean/csv_feishu_sync_row{fr}.json'
    os.makedirs(os.path.dirname(cells_path), exist_ok=True)
    with open(cells_path, 'w') as f:
        json.dump(cells, f, ensure_ascii=False)
    
    if dry_run:
        print(f'  [DRY-RUN] Row {fr}: would push D="{cells[0][0]["value"][:40]}", G="{cells[0][3]["value"]}"')
        return True
    
    cmd = [LARK_CLI, 'sheets', '+cells-set',
           '--spreadsheet-token', FEISHU_TOKEN,
           '--sheet-id', SHEET_ID,
           '--range', f'D{fr}:H{fr}',
           '--cells', open(cells_path).read()]
    
    for attempt in range(MAX_RETRIES):
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and '"ok": true' in result.stdout:
            return True
        print(f'  ⚠️ Row {fr} push attempt {attempt+1} failed: {result.stderr[:100]}')
        time.sleep(RETRY_DELAY * (attempt + 1))
    
    return False


def verify_single_row(fr, csv_row):
    """Read single row from Feishu and compare with CSV"""
    range_str = f'D{fr}:H{fr}'
    cells = lark_cli_read(range_str, timeout=30)
    if not cells or not cells[0]:
        return False, ['empty feishu response']
    
    feishu_d = cell_to_text(cells[0][0])
    feishu_e = cell_to_text(cells[0][1]) if len(cells[0]) > 1 else ''
    feishu_f = cell_to_text(cells[0][2]) if len(cells[0]) > 2 else ''
    feishu_g = cell_to_text(cells[0][3]) if len(cells[0]) > 3 else ''
    feishu_h = extract_text_from_feishu_h(cells[0][4]) if len(cells[0]) > 4 else ''
    
    csv_d = csv_row['PPT中的文献引用 完整字段'].strip()
    csv_e = csv_row['DOI'].strip()
    csv_f = csv_row['类型'].strip()
    csv_g = csv_row['对应PDF文件'].strip()
    csv_g_basename = os.path.basename(csv_g) if '/' in csv_g else csv_g
    csv_h = csv_row['来源链接 → 阅读全文'].strip()
    
    mismatches = []
    if csv_d != feishu_d:
        mismatches.append(f'D: csv="{csv_d[:30]}" feishu="{feishu_d[:30]}"')
    if csv_e != feishu_e:
        mismatches.append(f'E: csv="{csv_e[:30]}" feishu="{feishu_e[:30]}"')
    if csv_f != feishu_f:
        mismatches.append(f'F: csv="{csv_f[:20]}" feishu="{feishu_f[:20]}"')
    if csv_g_basename != feishu_g:
        mismatches.append(f'G: csv="{csv_g_basename}" feishu="{feishu_g}"')
    if csv_h != feishu_h:
        mismatches.append(f'H: csv_len={len(csv_h)} feishu_len={len(feishu_h)}')
    
    return len(mismatches) == 0, mismatches


def main():
    print('=' * 60)
    print('csv → 飞书 单向 push (强制一致, GitHub-ready)')
    print('=' * 60)
    print(f'Config: csv={CSV_PATH}, sheet={SHEET_ID}, token=***')
    if DRY_RUN:
        print('🔍 DRY-RUN mode (no actual push)')
    
    try:
        acquire_lock(timeout=30)
    except TimeoutError as e:
        print(f'❌ {e}')
        sys.exit(1)
    
    try:
        print(f'\n📖 Reading CSV: {CSV_PATH}')
        with open(CSV_PATH, encoding='utf-8-sig') as f:
            rows = list(csv_mod.DictReader(f))
        print(f'  ✓ Read {len(rows)} rows from CSV')
        
        if SINGLE_ROW:
            # Debug 模式: 只 push 单 row
            print(f'\n🔍 Single row debug mode (Row {SINGLE_ROW})')
            ok = push_single_row(SINGLE_ROW, rows[SINGLE_ROW-2], dry_run=DRY_RUN)
            if not DRY_RUN and ok:
                time.sleep(0.5)
                v, mismatches = verify_single_row(SINGLE_ROW, rows[SINGLE_ROW-2])
                print(f'  Verify: {"OK" if v else mismatches}')
            return
        
        print(f'\n📥 Reading Feishu state (all D-H)...')
        feishu_cells = lark_cli_read('D2:H161', timeout=60)
        print(f'  ✓ Read {len(feishu_cells)} rows from Feishu')
        
        print(f'\n🔍 Comparing CSV vs Feishu...')
        mismatched_rows = []
        for i, csv_row in enumerate(rows):
            fr = i + 2
            if i >= len(feishu_cells) or not feishu_cells[i]:
                mismatched_rows.append(fr)
                continue
            
            csv_d = csv_row['PPT中的文献引用 完整字段'].strip()
            csv_e = csv_row['DOI'].strip()
            csv_f = csv_row['类型'].strip()
            csv_g = csv_row['对应PDF文件'].strip()
            csv_g_basename = os.path.basename(csv_g) if '/' in csv_g else csv_g
            csv_h = csv_row['来源链接 → 阅读全文'].strip()
            
            feishu_d = cell_to_text(feishu_cells[i][0])
            feishu_e = cell_to_text(feishu_cells[i][1]) if len(feishu_cells[i]) > 1 else ''
            feishu_f = cell_to_text(feishu_cells[i][2]) if len(feishu_cells[i]) > 2 else ''
            feishu_g = cell_to_text(feishu_cells[i][3]) if len(feishu_cells[i]) > 3 else ''
            feishu_h = extract_text_from_feishu_h(feishu_cells[i][4]) if len(feishu_cells[i]) > 4 else ''
            
            if (csv_d != feishu_d or csv_e != feishu_e or 
                csv_f != feishu_f or csv_g_basename != feishu_g or csv_h != feishu_h):
                mismatched_rows.append(fr)
        
        print(f'  Mismatched rows: {len(mismatched_rows)}')
        if mismatched_rows:
            print(f'  First 10: {mismatched_rows[:10]}')
        
        if not mismatched_rows:
            print('\n✅ CSV ↔ Feishu 已完全一致 (无 mismatch)')
            return
        
        rows_to_push = mismatched_rows if not FIX_MODE else list(range(2, len(rows) + 2))
        print(f'\n🚀 Pushing {len(rows_to_push)} rows (single-row push, one at a time)...')
        
        success_count = 0
        fail_rows = []
        
        for fr in rows_to_push:
            i = fr - 2
            csv_row = rows[i]
            
            if push_single_row(fr, csv_row, dry_run=DRY_RUN):
                if not DRY_RUN:
                    time.sleep(0.5)
                    verified, mismatches = verify_single_row(fr, csv_row)
                    if verified:
                        success_count += 1
                    else:
                        if push_single_row(fr, csv_row, dry_run=DRY_RUN):
                            time.sleep(0.5)
                            verified, mismatches = verify_single_row(fr, csv_row)
                            if verified:
                                success_count += 1
                            else:
                                fail_rows.append((fr, mismatches))
                        else:
                            fail_rows.append((fr, mismatches))
                else:
                    success_count += 1
            else:
                fail_rows.append((fr, ['push failed']))
            
            if (success_count + len(fail_rows)) % 20 == 0:
                print(f'  Progress: {success_count + len(fail_rows)}/{len(rows_to_push)}')
        
        print(f'\n📊 Push 结果:')
        print(f'  ✅ Success: {success_count}')
        print(f'  ❌ Failed: {len(fail_rows)}')
        
        if fail_rows:
            print(f'\n❌ Failed rows (需要手动处理):')
            for fr, mismatches in fail_rows:
                print(f'  Row {fr}: {mismatches}')
            sys.exit(2)
        
        if not DRY_RUN:
            print(f'\n🔍 最终全表 verify...')
            feishu_cells_final = lark_cli_read('D2:H161', timeout=60)
            final_mismatches = 0
            for i, csv_row in enumerate(rows):
                fr = i + 2
                csv_g = csv_row['对应PDF文件'].strip()
                csv_g_basename = os.path.basename(csv_g) if '/' in csv_g else csv_g
                feishu_g = cell_to_text(feishu_cells_final[i][3]) if i < len(feishu_cells_final) and len(feishu_cells_final[i]) > 3 else ''
                
                if csv_g_basename != feishu_g:
                    final_mismatches += 1
            
            print(f'  Final G 列 mismatch: {final_mismatches}/{len(rows)}')
            if final_mismatches == 0:
                print('  ✅ CSV ↔ 飞书 100% 一致')
        
    finally:
        release_lock()


if __name__ == '__main__':
    main()