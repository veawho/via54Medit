#!/usr/bin/env python3
"""创建飞书在线表并写入与雷管方案一致的 8 列 × 106 行数据
依赖: app_secret 从 ~/.hermes/config.yaml (gateway.platforms.feishu.app_secret) 读取
输出: 在线表链接 + 授权用户(全编辑) + 公开可读"""
import json, urllib.request, csv, yaml, sys
from pathlib import Path

BASE = '/Users/david/Desktop/TMA_文献整理'
APP_ID = 'cli_aa93fb63c1b9dcc7'
USER_OPEN_ID = 'ou_83cf959d09334d3d1585d332fc4a15ce'

def api(method, url, body=None, token=None):
    h = {'Content-Type': 'application/json; charset=utf-8'}
    if token: h['Authorization'] = f'Bearer {token}'
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())

def main():
    cfg = yaml.safe_load(open(Path.home() / '.hermes' / 'config.yaml'))
    secret = cfg['gateway']['platforms']['feishu']['app_secret']
    tok = api('POST', 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
              {'app_id': APP_ID, 'app_secret': secret}).get('tenant_access_token')
    if not tok:
        print('token FAIL'); sys.exit(1)
    # 创建表
    d = api('POST', 'https://open.feishu.cn/open-apis/sheets/v3/spreadsheets',
            {'title': 'TMA在线表_与雷管方案一致'}, tok)
    st = d['data']['spreadsheet']['spreadsheet_token']
    url = d['data']['spreadsheet']['url']
    sid = api('GET', f'https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{st}/sheets/query', token=tok)['data']['sheets'][0]['sheet_id']
    # 写入
    with open(f'{BASE}/_citation_table/tma_citation_table.csv', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    cols = list(rows[0].keys())
    # 逐格构造; P12-3 引用含 URL, 加零宽字符防飞书链接化(其余保持原样)
    values = [cols]
    for r in rows:
        row_vals = []
        for c in cols:
            v = r[c]
            if r['PN'] == 'P12-3' and c == '引用':
                v = v.replace('https://', '\u200bhttps://')
            row_vals.append(v)
        values.append(row_vals)
    w = api('PUT', f'https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{st}/values',
            {'valueRange': {'range': f'{sid}!A1:H{len(values)}', 'values': values}}, tok)
    # 授权
    api('POST', f'https://open.feishu.cn/open-apis/drive/v1/permissions/{st}/members?type=sheet',
        {'member_type': 'openid', 'member_id': USER_OPEN_ID, 'perm': 'full_access'}, tok)
    api('PATCH', f'https://open.feishu.cn/open-apis/drive/v1/permissions/{st}/public?type=sheet',
        {'link_share_entity': 'anyone_readable', 'external_access_entity': 'open', 'security_entity': 'anyone_can_view'}, tok)
    print(f'在线表已创建: {url}')
    print(f'写入 {len(rows)} 行 × {len(cols)} 列 (write code={w.get("code")})')

if __name__ == '__main__':
    main()
