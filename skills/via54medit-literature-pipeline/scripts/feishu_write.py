#!/usr/bin/env python3
"""飞书在线表写入: 把与雷管方案一致的 14 列表写回飞书
用法:
  1) 用户提供 spreadsheet_token 后填入下方 FEISHU_SPREADSHEET_TOKEN
  2) app_id/app_secret 从环境变量 FEISHU_APP_ID / FEISHU_APP_SECRET 读取
  3) python3 feishu_write.py --sheet <spreadsheet_token> [--csv tma_citation_table_feishu_ALIGNED.csv]
流程: tenant_access_token → 获取 sheet 元数据(匹配列头) → 清空旧数据 → 写入 106 行 14 列
依赖: requests"""
import sys, os, json, csv, time
import urllib.request

APP_ID = os.environ.get('FEISHU_APP_ID', '')
APP_SECRET = os.environ.get('FEISHU_APP_SECRET', '')
BASE = 'https://open.feishu.cn/open-apis'

def post(url, body, headers=None):
    h = {'Content-Type': 'application/json; charset=utf-8'}
    if headers: h.update(headers)
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=h, method='POST')
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

def get_tenant_token():
    d = post(f'{BASE}/auth/v3/tenant_access_token/internal',
             {'app_id': APP_ID, 'app_secret': APP_SECRET})
    return d.get('tenant_access_token')

def write_sheet(spreadsheet_token, csv_path):
    token = get_tenant_token()
    if not token:
        raise RuntimeError('获取 tenant_access_token 失败(检查 app_id/app_secret)')
    hdr = {'Authorization': f'Bearer {token}'}
    # 1. 获取工作表
    meta = get(f'{BASE}/sheets/v3/spreadsheets/{spreadsheet_token}/sheets/query', hdr)
    sheets = meta.get('data', {}).get('sheets', [])
    print('工作表:', [(s.get('sheet_id'), s.get('title')) for s in sheets])
    if not sheets:
        raise RuntimeError('无工作表')
    sheet_id = sheets[0]['sheet_id']
    # 2. 读取现有行(确认列头/清空范围)
    with open(csv_path, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    cols = list(rows[0].keys())
    n = len(rows)
    print(f'将写入 {n} 行 × {len(cols)} 列, 表 {sheet_id}')
    # 3. 清空旧数据(先扩大范围再清)
    post(f'{BASE}/sheets/v2/spreadsheets/{spreadsheet_token}/values_append',
         {'valueRange': {'range': f'{sheet_id}!A1:Z200', 'values': [[]]}},
         hdr)  # no-op 占位
    clear = post(f'{BASE}/sheets/v2/spreadsheets/{spreadsheet_token}/values_clear',
                 {'range': f'{sheet_id}!A1:Z200'}, hdr)
    print('清空:', clear.get('code'), clear.get('msg'))
    # 4. 写入(表头 + 数据)
    values = [cols] + [[r[c] for c in cols] for r in rows]
    res = post(f'{BASE}/sheets/v2/spreadsheets/{spreadsheet_token}/values',
               {'valueRange': {'range': f'{sheet_id}!A1',
                               'values': values}}, hdr)
    print('写入:', res.get('code'), res.get('msg'))
    if res.get('code') == 0:
        print(f'✅ 飞书在线表已更新: {n} 行 × {len(cols)} 列(与雷管方案一致)')

if __name__ == '__main__':
    if '--sheet' in sys.argv:
        tok = sys.argv[sys.argv.index('--sheet') + 1]
    else:
        tok = os.environ.get('FEISHU_SPREADSHEET_TOKEN', '')
    if not tok:
        print('需提供 spreadsheet_token: --sheet <token> 或环境变量 FEISHU_SPREADSHEET_TOKEN')
        sys.exit(1)
    csv_path = sys.argv[sys.argv.index('--csv') + 1] if '--csv' in sys.argv else \
        '/Users/david/Desktop/TMA_文献整理/_citation_table/tma_citation_table_feishu_ALIGNED.csv'
    write_sheet(tok, csv_path)
