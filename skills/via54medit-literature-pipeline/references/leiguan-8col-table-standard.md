# 雷管方案 8 列表标准 + H 列卡片格式(2026-08-14 定稿)

> 用户硬要求: **本地表与在线表在逻辑、列、规则上与雷管方案完全一致**。
> 权威生成脚本: `scripts/align_tables.py`(本地表) + `scripts/leiguan_table.py`(在线表)。
> 数据源唯一性: step4 雷管方案目录 `{Pn-x}/` + verify.json + 引用表, 禁止手工改表。

## 一、两张表

| 表 | 文件/位置 | 列(8 列 A-H) |
|---|---|---|
| 本地表 | `_citation_table/tma_citation_table.csv` | PN \| 幻灯片 \| 引用序号 \| 引用 \| PDF大小 \| 已Highlight \| MD5 \| 页数 |
| 在线表(飞书) | 飞书 spreadsheet(sheet 4805fc 等) | PPT页 \| 第几条 \| 引用语义(上下文) \| PPT中的文献引用 完整字段 \| DOI \| 类型 \| 对应PDF文件 \| 来源链接 → 阅读全文 |

**两表同构**: 106 行(每个 Pn-x 一行), 数据全部从雷管方案目录实测派生(MD5/页数/PDF大小/高亮图片数), 不手工填。

### 本地表 8 列(A-H)
A=PN | B=幻灯片 | C=引用序号 | D=引用 | E=PDF大小 | F=已Highlight | G=MD5 | H=页数
- D 引用: 来自引用表(slide/num → 文本), 与 PPT 提取(step2)一致
- E/F/G/H: main.pdf 实测; F = annots>0 即 ✅
- P31-8/P31-9 不存在; slide31 重复编号(Laurence/Jiang)以 106 Pn-x 体系为准

### 在线表 8 列(A-H, 雷管方案模板)
A=PPT页 | B=第几条 | C=引用语义(上下文) | D=PPT中的文献引用 完整字段 | E=DOI | F=类型 | G=对应PDF文件 | H=来源链接 → 阅读全文
- C 引用语义: verify.json slide_topic(优先 _highlight_plan.md 应证上下文 → 在线表 D 列 → 人工)
- E DOI: CrossRef 查询; 中文期刊/UpToDate/未解析 → `备注: 无 DOI (中文期刊 / UpToDate / 未解析)`
- F 类型: 指南 / 病例报告 / RCT 试验 / 数据 / 文献(关键词判定)
- G 对应PDF文件: `{Pn-x}/{Pn-x}_main.pdf`(存在才写, 否则 `(缺 PDF)`)

## 二、H 列卡片格式(用户逐条核对过)

```
🎯 Row {N} ({Pn-x}) — {文献标题}

【📄 主文件 (按 PPT 引用内容部署)】
  - 本地路径: `{Pn-x}/{Pn-x}_main.pdf`        ← 反引号纯文本(file:// 中文路径飞书会截断!)
  - 大小: {size} KB, {pages} 页
  - MD5: `{md5前8}` (完整 `{md5}`)
  - 📥 在线访问: {DOI 解析 / PMC / UpToDate / 暂无 (中文期刊, 见本地 PDF)}

【🔗 DOI 状态】
  - {[doi](https://doi.org/{doi}) 超链接 | 备注: 无 DOI ...}

【📍 PPT 真实内容位置】
  - 标号: {第几条}
  - 位置{i}: 「{slide 引用上下文原文}」

【🔎 Highlight 情况】
  - {N} 处高亮, {N} 张图, 句子: 「{首句...}」

【📌 文献类型】 {类型}

【🗂 完整入口】
  - 本地: `{Pn-x}/`
  - 在线访问: {可达链接 1}
  - DOI: {doi 链接}
  - PPT: {slide 页码} 第 {num} 条
  - Highlight 图: {在线图链接}
```

要点:
- **4-tier 链接** = DOI / 在线访问 / PPT 位置 / Highlight 图 四层可点击
- 含 URL 的单元格飞书自动转 url 段; **file:// 中文路径会被截断 → 本地路径用反引号纯文本**
- 不希望被链接化的 URL 用零宽字符 `\u200b` 前缀(如 P12-3 引用字段)
- 读回验证需拼接 text 段(富文本拆段)

## 三、生成与写入(自动化)

```bash
# 本地表 + 在线表同构 CSV
python3 scripts/align_tables.py
#   → _citation_table/tma_citation_table.csv(本地权威)
#   → _citation_table/tma_citation_table_feishu_ALIGNED.csv(在线同构)

# 在线表(雷管方案格式)生成 + 写入飞书
python3 scripts/leiguan_table.py --write
#   → /tmp/tma_leiguan_final.json + 写飞书 sheet

# 仅生成本地表(引用列更新 + 保留实测列)
python3 scripts/sync_table.py <refs.json> _citation_table/tma_citation_table.csv --feishu-out feishu_sync.csv
```

## 四、飞书写入要点

1. token: `POST /open-apis/auth/v3/tenant_access_token/internal` (app_id + app_secret 从 `~/.hermes/config.yaml` 的 `gateway.platforms.feishu.app_secret` 读取)
2. 写入: `PUT /open-apis/sheets/v2/spreadsheets/{token}/values`, range `{sheet_id}!A1:H{n}`(单格 range 必须 D31:D31 格式)
3. 清空: `values_clear`(范围先扩大 A1:Z200)
4. 授权: `POST /open-apis/drive/v1/permissions/{token}/members?type=sheet`(member_type=openid, perm=full_access)
5. 公开: `PATCH /open-apis/drive/v1/permissions/{token}/public?type=sheet`(link_share_entity=anyone_readable)
6. 读回验证: `GET sheets/v2/spreadsheets/{token}/values/{sheet_id}!A1:H{last}` 逐格比对

## 五、超链接可达性验证

- 用 DOI 列直接验证(正则提取 URL 会被 DOI 内括号截断)
- TMA 106 行实测: 142 URL, 94 可达 + 48 受限(403/Cloudflare, 非失效) + 0 失效
- 受限链接(订阅期刊)标注为"受限"而非"失效", 不删除

## 六、目录交付基线(雷管方案)

```
step4_highlight_106目录_合并DOI/{Pn-x}/
├── {Pn-x}_highlight.pdf       # 高亮 PDF(先清旧 annots 再生成)
├── {Pn-x}_highlight_pNNN.png  # 根目录: 仅"有高亮"的页面图
├── {Pn-x}_highlight_pages/    # 全部页面图(存档, 含无高亮页)
├── {Pn-x}_main.pdf            # 源文献(与 slide 引用匹配, md5 记录)
└── {Pn-x}_verify.json         # md5/pages/highlights 句子/annot_count/download_status
```
