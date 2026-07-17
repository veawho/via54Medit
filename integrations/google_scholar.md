# Google Scholar 集成 — via54Medit 检索源

> **集成日期**: 2026-06-20 (Phase 2)
> **源 ID**: `gscholar`
> **定位**: 文献检索源（HTML 爬取），非官方 API
> **配置**: `sources.gscholar` — 默认 disabled

---

## 1. 设计定位

Google Scholar（scholar.google.com）是**引用聚焦的文献搜索引擎**。与 PubMed/OpenAlex/S2 不同：

- **无官方 API** — 必须 HTML 爬取
- **无稳定唯一 ID** — 返回 citation 中携带 PMID/DOI 当 Google Scholar 提供时
- **强限速** — 429 + CAPTCHA，无公开限速文档
- **默认禁用** — 爬取行为违反 Google Scholar ToS

## 2. 文件清单

| 文件 | 作用 |
|---|---|
| `internal/source/google_scholar.go` | `gScholarSource` 爬取适配器 |
| `internal/source/google_scholar_test.go` | 18 测试用例 |
| `cmd/medit/commands/gscholar.go` | CLI 子命令 |
| `cmd/medit/commands/root.go` | 注册 `gScholarCmd` |
| `internal/foundation/config.go` | 默认配置 `sources.gscholar` |

## 3. API 速览

```go
// 构建适配器
cfg := map[string]any{
    "enabled":    true,
    "rate_limit": 6, // req/min
    "user_agents": "Mozilla/5.0 custom1, Mozilla/5.0 custom2",
}
s, err := source.NewGScholarSource(cfg)

// 搜索
cites, err := s.Search(ctx, types.EBMQuestion{Query: "lung cancer"}, 10)
```

### 3.1 配置项

| 键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `enabled` | bool | false | 默认禁用 |
| `rate_limit` | int/float64 | 6 | 限速，≤60 → req/min，>60 → req/s |
| `user_agents` | string | 5-entry 默认池 | 逗号分隔，轮换使用 |

### 3.2 Health

```go
err := s.Health(ctx) // GET scholar.google.com, 非 2xx 即失败
```

### 3.3 返回的 Citation 字段

Google Scholar 返回 `types.Citation`，字段填充：

| 字段 | 来源 |
|---|---|
| `Title` | h3.gs_rt |
| `Authors` | div.gs_a 前半部分 |
| `Journal` | div.gs_a 后半部分（年份前） |
| `Year` | div.gs_a 中 4 位年份 |
| `Abstract` | div.gs_rs（snippet，非全文） |
| `DOI` | div.gs_fl 中的链接提取 |
| `PMID` | div.gs_fl 中的 PubMed 链接提取 |
| `CitedBy` | div.gs_fl 中 "Cited by N" 提取 |
| `OAPDFURL` | div.gs_fl 中 PDF 链接 |

## 4. 爬取实现

### 4.1 请求构建

- URL: `https://scholar.google.com/scholar?q=<query>&hl=en&as_sdt=0,5`
- `hl=en`：结果用英文
- `as_sdt=0,5`：不限定发表日期（全部）
- 轮换 User-Agent（5 个条目）
- 完整浏览器头：Accept, Accept-Language, Accept-Encoding, DNT, Sec-Fetch-*

### 4.2 速率限制

| 机制 | 行为 |
|---|---|
| Token-bucket | 6 req/min = 0.1 rps 默认 |
| 轮换 UA | 5 个浏览器 User-Agent 顺序轮换 |
| 自动退避 | 取 token 时若池子空则等待 |
| 健康检查 | GET 验证站点可达 |

### 4.3 HTML 解析（goquery）

Google Scholar 结果页 HTML 结构：

```html
<div class="gs_ri">
  <h3 class="gs_rt">标题</h3>
  <div class="gs_a">A Smith, B Jones - Nature, 2023</div>
  <div class="gs_rs">摘要片段...</div>
  <div class="gs_fl">
    <a href="https://doi.org/10.xxxx/...">All versions</a>
    <a href="#">Cited by 42</a>
  </div>
</div>
```

## 5. CLI 使用

```bash
# 必须显式启用
medit gscholar --force-enable "lung cancer immunotherapy"

# 限制结果数
medit gscholar --force-enable "heart failure" --limit 5

# 抑制合规警告 + JSON
medit gscholar --force-enable --no-warn "diabetes" --json

# 在 ask/search 中包含 gscholar
medit ask --sources "pubmed,openalex,s2,gscholar" "question"
```

## 6. 合规说明

⚠️ **爬取 Google Scholar 违反其 ToS**。本实现的安全边界：

- **默认禁用**：`enabled: false`，必须 `--force-enable` 或 config 启用
- **保守限速**：6 req/min（远低于 Google 的触发阈值）
- **合规警告**：CLI 调用时打印警告（`--no-warn` 可抑制）
- **审计日志**：每个请求写入 `~/.medit/audit/`
- **仅元数据**：返回 citation 元数据（标题/作者/摘要），不爬取全文 PDF

## 7. 与其他源的差异

| 维度 | PubMed/OpenAlex/S2 | Antfu | Sci-Hub | Google Scholar |
|---|---|---|---|---|
| 官方 API | ✅ | ❌ (CDP) | ❌ | ❌ (爬取) |
| 默认启用 | ✅ | ✅ | ❌ | ❌ |
| 限速 | 各自管理 | CDP session | 1 req/s | 6 req/min |
| 唯一 ID | PMID/DOI | 混合 | DOI/PMID | 无（引用时携带） |
| Fan-out 成员 | ✅ | ✅ | ❌ | ✅ |

---

*维护者*: 巫师叔叔 via Hermes Agent
*创建*: 2026-06-20
