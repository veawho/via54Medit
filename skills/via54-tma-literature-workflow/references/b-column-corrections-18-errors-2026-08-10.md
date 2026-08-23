# B列修正记录 (2026-08-10)

## 根因
用户暴怒："P3-1 B列3，P4-1 B列3，你确定这是对的？"

**真相**: B列 = PPT页码 = A列PN的n值
- P3-1 → B应为3（正确）
- P4-1 → B应为4（错写成3）
- P23-1 → B应为23（错写成26）

**我之前的错误理解**: 以为B列是"第几条引用"（那是C列），导致B列多年都是错的。

## 18处修正清单

| Row | PN | 错误B | 正确B | 根因 |
|-----|-----|-------|-------|------|
| 5 | P4-1 | 3 | 4 | 中文期刊同P3-1，PN不同B应不同 |
| 6 | P4-2 | 3 | 4 | 同上 |
| 7 | P4-3 | 3 | 4 | 同上 |
| 12 | P5-2 | 4 | 5 | PN=P5系列 |
| 13 | P5-3 | 4 | 5 | 同上 |
| 19 | P9-2 | 7 | 9 | PN=P9系列 |
| 30 | P12-1 | 11 | 12 | PN=P12系列 |
| 45 | P18-1 | 17 | 18 | PN=P18系列 |
| 52 | P23-1 | 26 | 23 | PN=P23系列 |
| 53 | P23-2 | 24 | 23 | 同上 |
| 60 | P23-9 | 26 | 23 | 同上 |
| 61 | P23-10 | 25 | 23 | 同上 |
| 62 | P23-11 | 25 | 23 | 同上 |
| 63 | P23-12 | 26 | 23 | 同上 |
| 64 | P23-13 | 26 | 23 | 同上 |
| 66 | P23-15 | 24 | 23 | 同上 |
| 67 | P23-16 | 24 | 23 | 同上 |
| 91 | P30-1 | 14 | 30 | PN=P30系列 |

## 验证脚本

```python
# 飞书B列正确性自动检查
import subprocess, json

lark_cli = '/Users/david/.hermes/node/bin/lark-cli'
TOKEN = 'YOUR_SPREADSHEET_TOKEN'

result = subprocess.run([lark_cli, 'sheets', '+cells-get',
    '--spreadsheet-token', TOKEN, '--sheet-name', 'Sheet1',
    '--range', 'A2:H110', '--as', 'bot', '--format', 'json'],
    capture_output=True, text=True)
d = json.loads(result.stdout)
cells = d['data']['ranges'][0]['cells']

errors = []
for i, row in enumerate(cells):
    pn = row[0].get('value','') if len(row)>0 else ''
    b_val = str(row[1].get('value','')) if len(row)>1 else ''
    if not pn or not pn.startswith('P'): continue
    try:
        expected = int(pn.split('-')[0][1:])
    except: continue
    try:
        actual = int(b_val)
    except: continue
    if actual != expected:
        errors.append(f"Row{i+2}: {pn} B={actual}应={expected}")

print(f"共{len(errors)}处错误")
for e in errors: print(e)
```
