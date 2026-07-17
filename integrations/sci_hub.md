# Sci-Hub 集成 — via54Medit 全文获取层

> **集成日期**: 2026-06-20 (Phase 2)
> **源 ID**: `sci-hub`
> **定位**: 全文 PDF 获取器（enricher + standalone CLI），非检索源
> **配置**: `sources.sci_hub` — 默认 disabled

---

## 1. 设计定位

Sci-Hub 不是文献检索引擎——它接受 DOI 或 PMID，返回 PDF URL。这与 PubMed/OpenAlex/S2/Antfu 本质不同。因此：

- **不是 `source.SourceAdapter` 的 fan-out 成员**：`ask`/`search` 的 4 源并发不包含 Sci-Hub
- **是 enrich 层的一员**：在 citation 已有 DOI/PMID 但无 `OAPDFURL` 时，Sci-Hub enricher 尝试解析
- **有独立的 CLI 命令**：`medit sci-hub <doi|pmid>` 供用户手动触发

## 2. 文件清单

| 文件 | 作用 |
|---|---|
| `internal/source/sci_hub.go` | Sci-Hub SourceAdapter + Resolve 方法 |
| `internal/source/sci_hub_test.go` | 单元测试（20 测试用例） |
| `internal/enrich/enrich.go` | `SciHubEnricher` 类型（+50 行） |
| `cmd/medit/commands/sci_hub.go` | CLI 子命令 |
| `cmd/medit/commands/root.go` | 注册 `sciHubCmd` |
| `internal/foundation/config.go` | 默认配置 `sources.sci_hub` |
| `pkg/types/types.go` | `Citation.SciHubURL` 字段 |

## 3. API 速览

### 3.1 Resolve 方法（核心）

```go
func NewSciHubSource(cfg map[string]any) (*SciHubSource, error)
func (s *SciHubSource) Resolve(ctx context.Context, identifier string) (string, error)
```

`Resolve` 接受 DOI 或 PMID，依次尝试 mirror，返回第一个成功的 PDF URL。

### 3.2 Enricher

```go
e := enrich.NewSciHubEnricher("sci-hub.se,sci-hub.ru")
pipeline.Add(e)
```

在 `Pipeline.Run()` 中对每个 citation 调用 `Enrich()`，填充 `c.SciHubURL`。

### 3.3 CLI

```bash
# 默认禁用，必须显式启用
medit sci-hub --force-enable --mirrors "sci-hub.se,sci-hub.ru" "10.1038/s41586-021-03621-9"

# 使用 PMID
medit sci-hub --force-enable 31535829

# 抑制合规警告
medit sci-hub --force-enable --no-warn "10.1056/NEJMoa1911303"
```

### 3.4 配置 (`~/.medit/config.yaml`)

```yaml
sources:
  sci_hub:
    enabled: false          # 默认禁用
    mirrors: "sci-hub.se,sci-hub.ru,sci-hub.st"
    rate_limit: 1           # 1 req/s
```

## 4. Mirror 轮询策略

| 步骤 | 行为 |
|---|---|
| 1 | 按顺序尝试每个 mirror |
| 2 | HEAD 请求 → 如果返回 2xx/3xx 或 Content-Type=pdf → 成功 |
| 3 | HEAD 失败 → GET 请求（UA = "Mozilla/5.0 (via54Medit)") |
| 4 | 任一 mirror 成功 → 立即返回 PDF URL |
| 5 | 全部失败 → 返回 `all mirrors failed` 错误 |
| 6 | 失败 enricher 返回 nil（非 fatal）→ pipeline 继续 |

## 5. 合规说明

⚠️ **Sci-Hub 在法律灰色地带运营**。本实现的安全边界：

- **默认禁用**：`enabled: false`，必须显式启用（flag 或 config）
- **仅解析 URL，不下载**：enricher 只填 `SciHubURL`，不 fetch PDF 内容
- **合规警告**：CLI 调用时打印警告（`--no-warn` 可抑制）
- **审计日志**：每个 Resolve 调用写入 `~/.medit/audit/`
- **用户责任**：用户需自行了解所在管辖区的版权法律

## 6. 与其他源的差异

| 维度 | PubMed/OpenAlex/S2 | Sci-Hub |
|---|---|---|
| 角色 | 检索 + metadata | 全文 URL 解析 |
| Fan-out 成员 | ✅ | ❌ |
| 输入 | 自然语言 / keyword | DOI / PMID 唯一标识符 |
| 输出 | Citation (metadata) | SciHubURL (PDF link) |
| 默认启用 | ✅ | ❌ |
| Rate limit | 各自管理 | 1 req/s（保守） |

## 7. 依赖

- **零新增 Go 模块**：纯标准库实现（`net/http`, `regexp`, `strconv`, `strings`）
- **零 CGO**：符合 ARCHITECTURE §9 独立运行原则

---

*维护者*: 巫师叔叔 via Hermes Agent
*创建*: 2026-06-20
