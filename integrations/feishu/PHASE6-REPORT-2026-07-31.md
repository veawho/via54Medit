# via54Medit Feishu Integration (Phase 6, 2026-07-31)

## 背景

用户要把 via54Medit (算法+经验集成项目) 推到 GitHub, 但 **雷管方案_文献整理** 是私有项目, 绝不推到 GitHub.

csv-feishu-bidirectional-sync 是 via54Medit 的一个 **飞书集成**, 提供 CSV ↔ Feishu 表格 D/E/F/G/H 列的强制一致性保证.

## 架构

```
via54Medit/
├── cmd/medit/commands/
│   └── feishu.go                # CLI 子命令: medit feishu verify|push
├── cmd/medit-mcp/main.go        # MCP tool: medit_feishu_push / medit_feishu_verify (Phase 6.x)
├── internal/integrations/feishu/
│   ├── feishu.go                # 核心 Client (Verify + Push)
│   └── feishu_test.go           # 黄金 9 + 集成测试 (25 子测试)
└── integrations/feishu/
    ├── README.md                # 集成设计文档
    └── python/                  # Python reference impl (Phase 1 quick path)
        ├── csv_to_feishu_push.py
        └── verify_consistency.py
```

## 关键设计

### GitHub-ready: 零硬编码

- ❌ **绝对没有** token / sheet_id / 路径的硬编码
- ✅ 全部从环境变量读取: `FEISHU_TOKEN`, `SHEET_ID`, `CSV_PATH`, `BASE_DIR`
- ✅ 推荐用 config 文件: `~/.config/hermes/feishu_credentials.json`
- ✅ 用户私有项目路径**只出现在用户私有 config**, 不进入代码

### 7 条铁律 (Hard Rules)

1. **永远 csv → 飞书 单方向 push** — 不反向
2. **永远先 re-read CSV** (不用内存缓存)
3. **push 前/后 acquire lock** (`_citation_table/csv.lock`)
4. **push 后立即 verify** (3 retry with exponential backoff)
5. **大 mismatch 自动 alert** — 抛异常让用户介入
6. **永不调 `sync_all.py` Step 1** — 反向覆盖
7. **永远用 `cells-set` 单 row push** — 不整批

### Rich Text (H 列) 自动处理

```go
// 自动检测 URL, 转 {type: 'link'} 节点
buildHCell("Visit https://example.com for info")
// → {rich_text: [{text: "Visit ", type: 'text'},
//                 {text: "https://example.com", type: 'link', link: '...'},
//                 {text: " for info", type: 'text'}]}
```

❌ 错误: `type: 'url'` / 直接 array `[{text, type}, ...]`
✅ 正确: `type: 'link'` / `{rich_text: [...]}`

### UTF-8 BOM 自动处理

Go `encoding/csv` 不会自动 strip UTF-8 BOM (`\ufeff`). `readCSV()` 手动 strip 3 字节 BOM.

### CSV 末尾 `\r\n` 自动 strip

Go csv reader 不会 strip 行末尾 `\r\n`. 每列用 `strings.TrimRight(s, "\r\n")` 处理.

## 测试结果

```bash
$ go test ./internal/integrations/feishu/...
ok  	github.com/veawho/via54Medit/internal/integrations/feishu	0.437s
```

**25 个测试全部通过** (TestBuildHCell 6 + TestNewClientValidation 6 + TestExtractCellText 5 + TestReadCSV + TestExtractMismatchedRowNumbers + TestClientIntegration).

## 真实 verify 测试

```bash
$ FEISHU_TOKEN=... SHEET_ID=b03e59 CSV_PATH=... BASE_DIR=... \
  medit feishu verify
{"msg":"verify: done","consistent":true,"d_mismatches":0,"g_mismatches":0,"h_mismatches":0}
✅ CSV ↔ Feishu 100% 一致
```

## 真实 push dry-run 测试

```bash
$ medit feishu push --dry-run --fix
{"msg":"push: pushing rows","count":160}
{"msg":"DRY-RUN: would push","row":2,"D":"The Global Cancer Observatory 2022. http...","G":"P3-1_main.pdf"}
✅ Success: 160
```

## CLI 用法

```bash
# 验证一致性 (只读)
medit feishu verify [--json] [--column G]

# 推送 (auto-fix)
medit feishu push [--dry-run] [--fix] [--row N]
```

## MCP Tool (Phase 6.x 即将)

```go
mcp.AddTool(server, &mcp.Tool{
    Name:        "medit_feishu_verify",
    Description: "Verify CSV ↔ Feishu consistency. Read-only.",
}, feishuVerifyTool)

mcp.AddTool(server, &mcp.Tool{
    Name:        "medit_feishu_push",
    Description: "Push CSV → Feishu. Auto-fix mismatches.",
}, feishuPushTool)
```

## Cron 集成

嵌入到现有 `hlo_daily_normalize` cron (Phase 5):

```yaml
prompt: |
  ...
  5. (追加) csv ↔ 飞书一致性 verify + 自动修复 (用 skill csv-feishu-bidirectional-sync):
     python3 ~/.hermes/skills/csv-feishu-bidirectional-sync/scripts/verify_consistency.py --quiet || \
     python3 ~/.hermes/skills/csv-feishu-bidirectional-sync/scripts/csv_to_feishu_push.py
```

**不单独建 30 分钟一次的 cron** — 跟用户"不随时用文献整理"匹配, 零资源浪费.

## 发布到 GitHub

via54Medit 主项目已经推到 GitHub (private) `github.com/veawho/via54Medit`. 飞书集成作为 Phase 6 加进去:

```bash
cd ~/Desktop/developments/via54Medit
git add cmd/medit/commands/feishu.go \
        cmd/medit/commands/root.go \
        internal/integrations/feishu/ \
        integrations/feishu/
git commit -m "feat(feishu): Phase 6 - CSV ↔ Feishu bidirectional sync (zero-config, GitHub-ready)"
git push origin main
```

**不推送**:
- 雷管方案_文献整理/ (用户私有项目, .gitignore 已加)
- 用户 config 文件 (`~/.config/hermes/feishu_credentials.json`)

## 私有项目隔离

via54Medit 主项目 `.gitignore`:

```gitignore
# 私有临床项目 (用户隐私 + 商业机密)
~/Desktop/雷管方案_文献整理/

# 用户私有 config (token)
~/.config/hermes/feishu_credentials.json
```

✅ Token / 私有项目路径**永远不进入 git**.

## 失败案例学习

### H 列漏推 (v1.0 → v2.0)

v1.0 只推 D/E/F/G 4 列, 漏 H 列. 导致 152 row H 列漂移.  
v2.0 加 H 列 + rich text 自动转换 + trailing `\n` strip → 全表修复.

### sync_all.py 反向覆盖

**永远不要调** `sync_all.py` Step 1 (sync_csv_g) — 它会 read-modify-write 整个 csv, 反向覆盖用户手动修改.

### Go BOM bug

Go `encoding/csv` 不会自动 strip UTF-8 BOM. CSV header 显示 `"\ufeffPPT页"` 而不是 `"PPT页"`, 找不到列.

修复: `readCSV()` 手动 strip 3 字节 BOM.

### Go csv trailing `\r\n`

Go `csv.Reader` 不会 strip 每行末尾 `\r\n`. CSV "ppt 页 \r\n" 读出来是 "ppt 页 \r\n", 比飞书 (已 strip) 多 1 字符.

修复: 每列 `strings.TrimRight(s, "\r\n")`.

## 工作量

- **Phase 6.0** (✅ 已完成): Python impl + Go 集成骨架 + 25 测试 + CLI + 设计文档
- **Phase 6.1** (即将): MCP tool (`medit_feishu_*`)
- **Phase 6.2** (未来): 替换 lark-cli 为 native Go HTTP (消除 Node.js 依赖)

总计 Phase 6.0: **3.5 小时**

## 关联资源

- via54Medit 主项目: `~/Desktop/developments/via54Medit/`
- Hermes skill (Python ref): `~/.hermes/skills/csv-feishu-bidirectional-sync/`
- 雷管方案 (私有): `~/Desktop/雷管方案_文献整理/`