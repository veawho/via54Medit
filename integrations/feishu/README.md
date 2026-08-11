# Feishu (飞书) Integration Plan

> **优先级**: P1 (集成层)  
> **API**: Feishu Open Platform (sheets v2 API)  
> **鉴权**: tenant_access_token (per-deployment secret)  
> **依赖**: 仅 `lark-cli` (Node.js) 或 Go HTTP client + 飞书 SDK

## 1. 能力

| 能力 | 备注 |
|---|---|
| CSV → 飞书推送 | 单向同步, 强制 100% 一致 |
| 飞书 → CSV verify | 只读比对, 检测漂移 |
| 自动修复 | 检测到漂移 → 自动 push (单 row + 锁 + retry) |
| Rich text (H 列) | 自动检测 URL → `{type: 'link'}` 节点 |
| File lock | `_citation_table/csv.lock` 防并发 |
| MCP tool | `medit_feishu_push` / `medit_feishu_verify` |
| CLI 子命令 | `medit feishu push` / `medit feishu verify` |

## 2. 设计原则

- ✅ **GitHub-ready**: 零硬编码 token / sheet_id / 路径 (100% 通过 env / config)
- ✅ **项目无关**: 不假设任何具体项目 (雷管方案, HLO, ...), 仅通用 CSV ↔ 飞书
- ✅ **铁律**: 不调 sync_all.py (会反向覆盖); 单向 push (csv → 飞书); 永远 re-read CSV
- ✅ **Failure-safe**: 3-retry with exponential backoff; 大 mismatch 抛异常

## 3. 集成步骤

### Phase 1 (本目录): 集成文档 + Python reference impl

- [x] `integrations/feishu/README.md` (本文档)
- [ ] `integrations/feishu/python/csv_to_feishu_push.py` (复制自 hermes skill)
- [ ] `integrations/feishu/python/verify_consistency.py` (同上)
- [ ] `integrations/feishu/schemas/citation_table.json` (列结构 schema)
- [ ] `integrations/feishu/tests/test_golden_9.py` (9 黄金案例)

### Phase 2: Go 集成 (跟 medit-mcp 同一进程)

- [ ] `cmd/medit/commands/feishu.go` (CLI 子命令)
  - `medit feishu push [--dry-run] [--fix]`
  - `medit feishu verify [--json] [--column G]`
  - `medit feishu lock/unlock`
- [ ] `cmd/medit-mcp/main.go` 新增 2 工具
  - `medit_feishu_push`
  - `medit_feishu_verify`
- [ ] `internal/integrations/feishu/client.go` (飞书 SDK 封装)
- [ ] `internal/integrations/feishu/lock.go` (file lock)
- [ ] `internal/integrations/feishu/cells.go` (rich text builder)

### Phase 3: CI/CD 集成

- [ ] `.github/workflows/feishu-verify.yml`
- [ ] `tests/integration/feishu_e2e_test.go`
- [ ] `docs/operations/feishu_setup.md`

## 4. 配置文件

### `~/.config/hermes/feishu_credentials.json` (推荐)

```json
{
  "feishu_token": "<tenant_access_token>",
  "sheet_id": "<sheet_id>",
  "csv_path": "/path/to/citation_table.csv",
  "base_dir": "/path/to/project"
}
```

### 环境变量 (CI/CD)

```bash
export FEISHU_TOKEN="<token>"
export SHEET_ID="<id>"
export CSV_PATH="/path/to/citation_table.csv"
export MEDIT_FEISHU_LOCK_DIR="/path/to/_citation_table"
```

### Go SDK 调用

```go
import "github.com/veawho/via54Medit/internal/integrations/feishu"

client := feishu.NewClient(&feishu.Config{
    Token:     os.Getenv("FEISHU_TOKEN"),
    SheetID:   os.Getenv("SHEET_ID"),
    CSVPath:   os.Getenv("CSV_PATH"),
    BaseDir:   os.Getenv("BASE_DIR"),
})
err := client.Push(context.Background())
```

## 5. 失败案例学习 (历史)

### H 列漏推 (v1.0 → v2.0)

v1.0 只推 D/E/F/G 4 列, 漏 H 列. 导致 152 row H 列漂移.  
v2.0 加 H 列 + rich text 自动转换 + trailing `\n` strip → 全表修复.

### sync_all.py 反向覆盖

**永远不要调** `sync_all.py` Step 1 (sync_csv_g) — 它会 read-modify-write 整个 csv, 反向覆盖用户手动修改.

### rich text 格式错误

❌ 错误: 直接 array `[{text, type}, ...]`
✅ 正确: 包成 `{rich_text: [...]}`

❌ 错误: type='url'
✅ 正确: type='link'

## 6. 测试

### 黄金 9 (Phase 1)

1. Empty CSV → empty push (exit 0)
2. Single row → push + verify (match)
3. Mismatch (模拟) → auto-fix
4. H 列 rich text (URL detection) → link 节点
5. H 列纯文本 → text 节点
6. File lock 并发 (模拟) → second push 等待
7. Push 失败 → 3 retry with backoff
8. Token 不存在 → 显式 error
9. 100 row push → 100% 一致

### 集成测试 (Phase 2)

- 跑 `medit feishu push` 在真实飞书表
- 跑 `medit_feishu_verify` MCP tool
- 跑 CSV 漂移 → 自动修复

## 7. 工作量

- **Phase 1**: 0.5 天 (复制 + 重构 + 测试)
- **Phase 2**: 2 天 (Go 集成 + MCP tool)
- **Phase 3**: 1 天 (CI/CD + e2e)

总计: **3.5 天**

## 8. 依赖

- **必选**: `lark-cli` (Node.js, 已存在)
- **可选 Go SDK**: `github.com/larksuite/oapi-sdk-go/v3`
- **测试**: `tests/e2e/screenshots/` (git-ignored)

## 9. 关联资源

- via54Medit 主项目: `~/Desktop/developments/via54Medit/`
- Hermes skill (Python ref): `~/.hermes/skills/csv-feishu-bidirectional-sync/`
- 历史经验 (雷管方案): `~/Desktop/雷管方案_文献整理/` (私有, 不入 git)