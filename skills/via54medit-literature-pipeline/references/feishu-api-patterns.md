# 飞书 API 调用模式(2026-08-14 实测沉淀)

> 用途: 在线表创建/写入/授权/公开、docx 文档发布。
> 凭据: app_id=`cli_aa93fb63c1b9dcc7`, app_secret 从 `~/.hermes/config.yaml` 的 `gateway.platforms.feishu.app_secret` 读取(安全: 不回显)。
> 用户 open_id: `ou_83cf959d09334d3d1585d332fc4a15ce`(授权对象)。

## 1. tenant_access_token

```python
POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal
body: {"app_id": ..., "app_secret": ...}
→ data.tenant_access_token  (2h 有效)
```

## 2. 电子表格(sheets)

| 动作 | 方法/路径 | 要点 |
|---|---|---|
| 创建表 | POST `/open-apis/sheets/v3/spreadsheets` `{"title": ...}` | → data.spreadsheet.spreadsheet_token + url |
| 查工作表 | GET `/open-apis/sheets/v3/spreadsheets/{st}/sheets/query` | → data.sheets[].sheet_id |
| 写入 | PUT `/open-apis/sheets/v2/spreadsheets/{st}/values` | body `{"valueRange": {"range": "{sid}!A1:H{n}", "values": [[...]]}}` |
| 清空 | POST `/open-apis/sheets/v2/spreadsheets/{st}/values_clear` | range 先扩大(A1:Z200)再清 |
| 授权用户 | POST `/open-apis/drive/v1/permissions/{st}/members?type=sheet` | `{"member_type":"openid","member_id":...,"perm":"full_access"}` |
| 公开可读 | PATCH `/open-apis/drive/v1/permissions/{st}/public?type=sheet` | `{"link_share_entity":"anyone_readable","external_access_entity":"open","security_entity":"anyone_can_view"}` |
| 读回验证 | GET `/open-apis/sheets/v2/spreadsheets/{st}/values/{sid}!A1:H{last}` | 逐格比对 |

**坑(实测)**:
- 单格 range 必须 `{sid}!D31:D31` 格式(写成 `D31` 会失败)
- 含 URL 的单元格飞书自动转 url 段; **file:// 中文路径截断 → 本地路径用反引号纯文本**
- 不想被链接化的 URL 加零宽字符前缀 `\u200b`
- 读回时富文本单元格拆成多个 text 段, 需拼接后再比对

## 3. 文档(docx, 发布总结报告)

| 动作 | 方法/路径 | 要点 |
|---|---|---|
| 创建文档 | POST `/open-apis/docx/v1/documents` `{"title": ...}` | → data.document.document_id |
| 写块 | POST `/open-apis/docx/v1/documents/{doc_id}/blocks/{block_id}/children` | **block_id 用 document_id**(不是 "1")! |
| 删块 | DELETE `/open-apis/docx/v1/documents/{doc_id}/blocks/{block_id}/children/batch_delete` | body 传根块 children index |
| 授权/公开 | 同 sheets 的 drive permissions 接口, type=docx | — |

块类型: heading1/heading2/paragraph/bullet/ordered(表格用文本行渲染, 飞书原生表格块可选)。
分批写入(每次 ≤ 50 blocks), 写完读回验证首末行。

## 4. 链接可达性验证(交付前)

- 用 DOI 列直接验证(正则提取 URL 会被 DOI 内括号截断)
- 判定: 200 可达 / 403-Cloudflare 受限(标注"受限", 不删) / 连接失败才算失效
