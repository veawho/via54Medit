# via54Medit Architecture — 医学循证检索语义路由器

> **项目代号** via54Medit
> **副标题** Multi-Source Medical Literature Router for Evidence-Based Medicine
> **作者** 巫师叔叔 (via54) + Hermes Agent
> **版本** v0.1.0 (设计阶段)
> **创建日期** 2026-06-09
> **状态** DRAFT — 待拍板

---

## 1. 一句话定位

**`via54Medit` 是一个用自然语言驱动的多源医学文献语义路由器**——把医生/研究者的临床问题，路由到最合适的文献源（蚂蚁阿福 RAG / PubMed / OpenAlex / Semantic Scholar），融合检索结果，输出可标注、可入知识库、可生成 PPT 的循证证据包。

> 不是又造一个文献检索工具，是造**调度器**——下面 4 个源是"算子"，`via54Medit` 是"调度内核"。

---

## 2. 和 via54Design 的关系

| 维度 | via54Design | via54Medit |
|---|---|---|
| 领域 | 创意设计 | 医学循证 |
| 核心 | 确定性模板引擎 | 语义路由 + 证据融合 |
| 形态 | CLI + MCP | CLI + MCP（一致） |
| 语言 | Go + Rust + JS(1) | Go + Shell + Rust（一致） |
| 许可 | MIT + AGPL-3.0 | MIT + AGPL-3.0（一致） |
| Embedder | 插件式（默认 bge-m3） | **可借鉴 via54Design**——但 via54Medit **不强制依赖**，见 §21 独立运行原则 |
| VectorStore | 插件式（默认 Qdrant） | **可借鉴 via54Design**——但 via54Medit **不强制依赖**，见 §21 |
| 跨项目包 | `github.com/veawho/via54Design` | **可选依赖**——若 via54Design 仓库 ready 则 import；否则 via54Medit hand-roll 等价接口（见 §17 / §21） |

**关键设计原则**（2026-06-24 修订）：`via54Medit` 优先**独立运行**——`git clone` 后不依赖任何私有仓库即可编译运行。via54Design 的 embedder/vectorstore/llm/config/log 接口是**可借鉴设计**，不是**强制依赖**：
- 若你（开发者）已部署 via54Design + bge-m3 + Qdrant → 可选 import 共享
- 若新成员只想跑 medit → 0 外部业务依赖，只用 cobra 一个第三方包即可
- 后续若第三项目需要 → 抽出 `vea-kit` 公共包（见 §17.3 路径 ③）

---

## 3. 系统架构 5 层

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 5: 入口层 (Entry)                                          │
│  ├── cmd/medit/         CLI (13 subcommands, 1 binary)         │
│  ├── cmd/medit-mcp/     MCP Server (4 tools, 1 binary)          │
│  └── pkg/api/           公开 Go API（让第三方集成）                │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  Layer 4: 语义路由层 (Router) — 核心创新点                         │
│  ├── internal/router/                                             │
│  │   ├── classify.go     问题分类：EBM 6 类问题（治疗/诊断/预后/    │
│  │   │                   病因/预防/经济）+ 5 类用户意图            │
│  │   ├── plan.go         任务规划：单源/多源/链式                  │
│  │   ├── dispatch.go     源调度：并发 4 源，限速，重试，降级         │
│  │   └── merge.go        结果融合：去重（DoiPmid+title 相似度），   │
│  │                       排序（被引+时新+权威权重）                 │
│  └── internal/prompt/    提示词工程（医学 PICO 抽取）               │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  Layer 3: 源适配器层 (Source Adapters)                            │
│  ├── internal/source/                                             │
│  │   ├── pubmed.go      NCBI E-utilities（efetch/esearch）        │
│  │   ├── openalex.go    2 亿+ 论文，免费                          │
│  │   ├── s2.go          Semantic Scholar，5K req/day              │
│  │   ├── antfu.go       Chrome 9223 CDP driver（来自 antfu       │
│  │   │                  evidence-search，移植为 Go + Rust)         │
│  │   └── _interface.go  SourceAdapter 接口                        │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  Layer 2: 数据加工层 (Pipeline)                                   │
│  ├── internal/enrich/        三方 enrich (PubMed+OpenAlex+S2)     │
│  │                           字段：PMID/DOI/abstract/MeSH/         │
│  │                                 cited_by/FWCI/TLDR/OA PDF       │
│  ├── internal/dedupe/        去重引擎（DoiPmid 优先, title simd）  │
│  ├── internal/extract/       从 PDF/HTML 提事实（数字、结论、证据） │
│  └── internal/anno2ppt/      文献标注 → PPT（来自 medlit-anno-ppt） │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: 基础层 (Foundation) — **优先独立**（via54Design 可选）  │
│  └── via54Design/pkg/...              ？（可选，运行时 if-imported）  │
│  ├── embedder/         hand-roll bge-m3 + openai + sense-nova  │
│  │                      （若 via54Design ready 则 import 替换）   │
│  ├── vectorstore/      hand-roll qdrant + meilisearch + sqlite │
│  │                      （同上）                                  │
│  ├── llm/              hand-roll hermes + openai + anthropic    │
│  │                      + ollama 多 provider 抽象               │
│  ├── config/           hand-roll YAML 加载（gopkg.in/yaml.v3）  │
│  └── log/              hand-roll 结构化日志（log/slog）          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. 核心数据模型

### 4.1 EBMQuestion（入口参数）
```go
type EBMQuestion struct {
    Query       string            // 原始自然语言问题
    PICO        *PICO             // 自动抽取或用户指定
    Language    string            // "zh" / "en" / "auto"
    Intent      Intent            // 检索/综述/分析/标注/PPT
    Sources     []string          // 指定源，默认全 4 源
    MaxResults  int               // 默认 20
    TimeRange   *TimeRange        // 限定时间窗
    Filters     map[string]string // 期刊/Section/MeSH 等
    Context     string            // 已有背景资料（可选）
}
```

### 4.2 PICO 自动抽取
```go
type PICO struct {
    Population  string  // 人群（如 "2 型糖尿病合并心衰"）
    Intervention string // 干预（如 "SGLT2 抑制剂"）
    Comparator  string  // 对照（如 "安慰剂"）
    Outcome     string  // 结局（如 "心血管死亡"）
}
```

### 4.3 Citation（统一引用）
```go
type Citation struct {
    ID            string   // 内部 UUID
    Title         string
    Authors       []string
    Journal       string
    Year          int
    PMID          string
    DOI           string
    Abstract      string
    MeSH          []string
    CitedBy       int       // 来自 S2
    FWCI          float64   // 来自 OpenAlex
    TLDR          string    // 来自 S2 AI 摘要
    OAPDFURL      string    // 公开 PDF 链接
    SourceOrigin  []string  // 来源溯源（哪些源返回了它）
    FetchedAt     time.Time
    EnrichmentLog []string  // 丰富过程审计
}
```

### 4.4 EvidencePackage（输出）
```go
type EvidencePackage struct {
    Question     EBMQuestion
    Citations    []Citation      // 去重 + 排序后
    Summary      string          // LLM 生成的循证摘要
    GRADE        string          // 证据等级 A/B/C/D
    PPTPath      string          // 标注 PPT 输出
    JSONPath     string          // 原始数据
    BibTeXPath   string          // 引文格式
    Duration     time.Duration
    SourcesUsed  map[string]int  // 每个源返回了多少
}
```

---

## 5. 语义路由核心算法

### 5.1 6 类 EBM 问题分类

| 类型 | 关键词示例 | 首选源 |
|---|---|---|
| **治疗/干预** | "X 治疗 Y 是否有效" | 蚂蚁阿福（循证模式） + PubMed |
| **诊断** | "用 X 诊断 Y 的敏感性" | PubMed + OpenAlex |
| **预后** | "Y 患者 5 年生存率" | OpenAlex + S2 |
| **病因/危险因素** | "X 是否导致 Y" | OpenAlex + PubMed |
| **预防** | "如何预防 Y" | 蚂蚁阿福 + PubMed |
| **经济学/指南** | "Y 治疗的成本效益" | 蚂蚁阿福（指南模式） + S2 |

### 5.2 5 类用户意图

| 意图 | 触发词 | 行为 |
|---|---|---|
| **快速检索** | "找一下""查一下" | 4 源并发, 取 top 20 |
| **系统综述** | "综述""meta""系统评价" | PICO 抽取 + 严格筛选 + PRISMA 流 |
| **证据分析** | "分析""比较""GRADE" | 全量 + GRADE 评级 + 冲突检测 |
| **标注 PPT** | "做成 PPT""标注" | 检索 + 渲染为 antfu 样式 PPT |
| **知识库入库** | "入库""存进知识库" | 检索 + enrich + 写 Qdrant + 写 FTS5 |

### 5.3 调度策略

```go
type DispatchPolicy struct {
    Concurrency    int               // 默认 4 源并发
    Timeout        time.Duration     // 每源 30s
    RetryPolicy    BackoffPolicy     // 3 次指数退避
    FallbackOrder  []string          // 蚂蚁阿福超时 → PubMed → ...
    SourceWeight   map[string]float64 // 源权威性权重
}
```

### 5.4 结果融合算法

```
1. 归一化 (Normalize)
   - PMID/DOI 为一等公民
   - Title 去除标点 + 转为 lowercase

2. 去重 (Dedupe)
   - 同一 PMID 合并
   - 同一 DOI 合并
   - 无 PMID/DOI 时: title simhash 汉明距 < 3 合并

3. 加权排序 (Score)
   score = w1 * cited_by_norm
         + w2 * (1 / (year_now - pub_year + 1))  // 时新
         + w3 * fwci                            // 权威
         + w4 * source_count                    // 多源印证
   默认权重 w1=0.3, w2=0.2, w3=0.3, w4=0.2

4. 取 Top N（默认 20）
```

---

## 6. CLI 子命令设计（13 个）

```bash
medit [global flags] <subcommand>

GLOBAL FLAGS:
  --config string         配置文件 (default ~/.medit/config.yaml)
  --embedder string       bge-m3/openai/sense nova/... (default bge-m3)
  --vectorstore string    qdrant/meilisearch/sqlite (default qdrant)
  --provider string       LLM provider (default hermes)
  --endpoint string       自定义 API endpoint
  --model string          模型名
  --lang string           zh/en/auto
  --verbose               详细日志
  --no-color              禁用 ANSI 颜色

SUBCOMMANDS:

  # --- 检索类 (5) ---
  ask <query>              # 一句话检索 (默认: 4 源 + 融合 + 摘要)
  search <query>           # 原始多源检索，无摘要
  pico <query>             # PICO 抽取 + 结构化查询
  systematic <query>       # 系统综述 (PRISMA 流程)
  grade <query>            # GRADE 证据评级

  # --- 适配器类 (4) ---
  pubmed <subcmd>          # 直查 PubMed: search/fetch/efetch
  openalex <subcmd>        # 直查 OpenAlex: works/authors/concepts
  s2 <subcmd>              # 直查 S2: paper/search/tldr
  antfu <subcmd>           # 蚂蚁阿福: ask/screenshot/extract/chat-list

  # --- 富化 + 持久化 (3) ---
  enrich <refs.json>       # 三方 enrich
  index <file/dir>         # 入 Qdrant + FTS5
  query <query>            # 检索本地知识库

  # --- 渲染 (1) ---
  anno2ppt <package.json>  # 证据包 → antfu 样式 PPT

VERSION:
  version                  # 打印版本 + 编译信息
```

---

## 7. MCP 4 工具设计

```json
{
  "name": "medit_ask",
  "description": "自然语言医学问题 → 4 源并发检索 → 循证证据包",
  "inputSchema": {
    "query": "string, required",
    "intent": "enum: search|systematic|grade|annotate|index",
    "sources": "array of: pubmed|openalex|s2|antfu",
    "max_results": "integer, default 20",
    "language": "string, default auto"
  }
}

{
  "name": "medit_pico",
  "description": "从自然语言抽取 PICO 四要素",
  "inputSchema": {
    "query": "string, required",
    "language": "string"
  }
}

{
  "name": "medit_grade",
  "description": "对证据做 GRADE 评级",
  "inputSchema": {
    "package_id": "string, required"
  }
}

{
  "name": "medit_anno2ppt",
  "description": "证据包 → antfu 样式 PPT 文件路径",
  "inputSchema": {
    "package_id": "string, required",
    "template": "string, default antfu-card-v1"
  }
}
```

---

## 8. 配置系统（YAML）

```yaml
# ~/.medit/config.yaml
version: 1

# 文献源
sources:
  pubmed:
    enabled: true
    api_key: ""           # 选填，NCBI 提升限速
    rate_limit: 3         # req/s
  openalex:
    enabled: true
    email: "you@institution.edu"  # polite pool
  s2:
    enabled: true
    api_key: ""           # 5K/day 免费，提升到 100K
  antfu:
    enabled: true
    cdp_url: "http://localhost:9223"
    deep_search: true     # 48s vs 标准 8s

# Embedder
embedder:
  default: bge-m3
  bge-m3:
    model_path: "~/.medit/models/bge-m3"
    device: "cuda:0"     # auto 选 cpu
  openai:
    api_key: ""

# VectorStore
vectorstore:
  default: qdrant
  qdrant:
    url: "http://localhost:6333"
    collection: "medlit"

# LLM
llm:
  default: hermes
  providers:
    hermes:
      endpoint: "http://localhost:8642"
      model: "MiniMax-M3"
    openai:
      api_key: ""
      model: "gpt-4o-mini"

# 路由策略
router:
  concurrency: 4
  timeout_per_source: 30s
  fallback_order: [antfu, pubmed, openalex, s2]
  fusion:
    weights:
      cited_by: 0.3
      recency: 0.2
      fwci: 0.3
      multi_source: 0.2

# 持久化
storage:
  qa_dir: "~/.medit/qa"           # 每个问题一个 JSON
  index_db: "~/.medit/fts5.db"    # SQLite FTS5
  knowledge_base: "medlit"        # Qdrant collection
```

---

## 9. 关键依赖（**独立运行优先**，via54Design 改为可选借鉴）

> **2026-06-24 修订**:via54Design 不再是强制依赖。via54Medit 必须能 `git clone && go build` 跑起来，**不依赖**任何私有仓库。

### 9.1 via54Design（**可选借鉴**，非强制）

```go
// 可选：仅当开发者本地已部署 via54Design 且 import 路径可达时才启用
//
// import (
//     "github.com/veawho/via54Design/pkg/embedder"
//     "github.com/veawho/via54Design/pkg/vectorstore"
//     "github.com/veawho/via54Design/pkg/llm"
//     "github.com/veawho/via54Design/pkg/config"
//     "github.com/veawho/via54Design/pkg/log"
// )
```

实际策略（见 §21 独立运行原则）：
- **默认** = `internal/foundation/` hand-roll 等价接口 + 实现
- **可选** = 若 `go.mod` 的 `replace` 指令指向本地 via54Design 路径，则用 build tag `//go:build viadesign` 切换
- **永远不阻塞** = 主分支必须 0 via54Design 依赖也能编译

### 9.2 Go 运行时依赖（**强制最小集**）

| 包 | 用途 | 必要性 |
|---|---|---|
| `github.com/spf13/cobra` | CLI 框架 | ✅ 必装（Phase 0 已在用） |
| `gopkg.in/yaml.v3` | YAML 配置解析 | ✅ Phase 1+ |
| `golang.org/x/net` | HTTP / rate limit | ✅ Phase 1+ |
| `modernc.org/sqlite` | 纯 Go SQLite + FTS5（零 CGO） | ✅ Phase 2+ |
| `github.com/PuerkitoBio/goquery` | HTML 解析（蚂蚁阿福引文） | ✅ Phase 1+ |
| `github.com/gorilla/websocket` | CDP 客户端（蚂蚁阿福） | ✅ Phase 1+ |
| `github.com/modelcontextprotocol/go-sdk` | MCP Server SDK | ✅ Phase 4 |

> **Phase 0 真实依赖**:仅 `cobra v1.8.0` 1 个包。其它都是 Phase 1+ 引入。

### 9.3 Rust 热路径（cargo 子项目，Phase 3 启用）

| crate | 用途 |
|---|---|
| `pdf-extract` | PDF 文本+元数据提取 |
| `tokenizers` | HuggingFace tokenizers (Rust) |
| `rayon` | 并行分块 |

### 9.4 Shell 工具

- `scripts/setup.sh` 一键部署（bge-m3 + Qdrant + Chrome 9223）
- `scripts/migrate-from-antfu.sh` 从 antfu-evidence-search v1.11 迁移历史数据
- `scripts/release.sh` 跨平台构建

---

## 10. 部署形态

| 形态 | 大小 | 依赖 | 场景 |
|---|---|---|---|
| **A. 全量** | ~80MB | Go 二进制 + Qdrant + bge-m3 + Chrome | 本地主力，3 源 + 蚂蚁阿福 |
| **B. 最小化** | ~20MB | Go 二进制 + 在线 API | 4 源全走 API，无本地 LLM/向量库 |
| **C. MCP-only** | ~15MB | MCP Server 二进制 + Claude Desktop | 在 Claude 内调用 |

> **铁律**：和 via54Design v0.5.0 一致——本地不跑 LLM（7B 质量低+占 4-10GB RAM），一律走在线 API。bge-m3 (1GB) 是例外（embedding 必须本地，不能走 API 保护隐私）。

---

## 11. 数据流（一次 `medit ask` 的完整路径）

```
用户输入: "SGLT2 抑制剂对 2 型糖尿病合并心衰患者的预后如何？"
                              ↓
[1] LLM 抽取 PICO
    P="2型糖尿病+心衰" I="SGLT2抑制剂" C="安慰剂" O="心血管死亡+住院"
                              ↓
[2] Router 分类
    意图=search, 类型=治疗, 语言=zh
                              ↓
[3] 4 源并发调度
    ┌─ 蚂蚁阿福: "SGLT2抑制剂 心衰"  (deep_search, ~48s)
    ├─ PubMed:     "(SGLT2 inhibitor) AND (heart failure) AND (prognosis)"  (3s)
    ├─ OpenAlex:   "SGLT2 inhibitor heart failure"  (2s)
    └─ S2:         "SGLT2 inhibitor heart failure"  (4s)
                              ↓
[4] 三方 enrich (PubMed+OpenAlex+S2)
    每条 citation 补全 PMID/DOI/MeSH/cited_by/FWCI/TLDR
                              ↓
[5] 去重 + 加权排序
    320 条 → 去重 → 187 条 → top 20
                              ↓
[6] LLM 生成循证摘要 (EBM 风格)
    "基于 DAPA-HF (NEJM 2019, n=4744)、EMPEROR-Reduced (...)... 证据等级 A"
                              ↓
[7] GRADE 评级（可选）
                              ↓
[8] 持久化
    ~/.medit/qa/<conv_id>.json
    ~/.medit/fts5.db (FTS5 索引)
    ~/.medit/knowledge_base/ (Qdrant 入库)
                              ↓
[9] 输出 EvidencePackage
    JSON + 摘要 + GRADE + 引用列表
```

---

## 12. 错误处理与降级链

| 故障 | 降级 |
|---|---|
| 蚂蚁阿福超时 (48s+) | 标记 partial, 继续其他 3 源 |
| Chrome 9223 未启动 | 跳过 antfu, 用其他 3 源 + 提示启动命令 |
| PubMed 429 | 指数退避, 切换到 OpenAlex 作主源 |
| OpenAlex 网络失败 | 切到 S2 |
| bge-m3 加载失败 | 切到在线 embedder (openai) |
| Qdrant 不可达 | 用 SQLite FTS5 本地兜底 |
| LLM 调用失败 | 返回原始 citations, 不生成摘要 |

---

## 13. 安全/合规边界

- **不存储患者隐私**——所有 prompt 走本地或机构 LLM endpoint
- **蚂蚁阿福 ToS 灰色**——只用于检索, 不批量下载
- **PubMed/OpenAlex/S2** —— ToS 允许, 遵守 rate limit
- **PDF 全文** —— 仅在 `~/.medit/pdfs/` 本地, 不上传
- **审计日志** —— 每次 ask 写 `~/.medit/audit/<date>.jsonl`, 含 query/citations/duration/sources_used

---

## 14. 测试策略

| 层级 | 工具 | 覆盖 |
|---|---|---|
| 单元 | `go test` | 接口、router 算法、enrich、dedupe |
| 集成 | `go test -tags=integration` | 4 源真实请求（mock 兜底） |
| 端到端 | `tests/e2e_*.sh` | CLI 子命令全跑（VHS 录像） |
| 压力 | `tests/stress_*.sh` | 24h 跑 N 万次 ask |
| 视觉 | screenshots 对比 | anno2ppt 输出 vs antfu 真实引用区 |

---

## 15. 目录结构（最终）

```
via54Medit/
├── cmd/
│   ├── medit/                 # CLI 入口
│   │   ├── main.go
│   │   ├── ask.go             # ask 子命令
│   │   ├── search.go
│   │   ├── pico.go
│   │   ├── systematic.go
│   │   ├── grade.go
│   │   ├── pubmed.go          # pubmed 子命令组
│   │   ├── openalex.go
│   │   ├── s2.go
│   │   ├── antfu.go
│   │   ├── enrich.go
│   │   ├── index.go
│   │   ├── query.go
│   │   ├── anno2ppt.go
│   │   ├── version.go
│   │   └── root.go
│   └── medit-mcp/             # MCP Server
│       ├── main.go
│       └── tools.go           # 4 工具实现
├── internal/
│   ├── router/                # 语义路由核心
│   │   ├── classify.go
│   │   ├── plan.go
│   │   ├── dispatch.go
│   │   ├── merge.go
│   │   └── prompt.go
│   ├── source/                # 源适配器
│   │   ├── _interface.go
│   │   ├── pubmed.go
│   │   ├── openalex.go
│   │   ├── s2.go
│   │   └── antfu.go
│   ├── enrich/                # 三方 enrich
│   │   ├── enricher.go
│   │   ├── pubmed_enrich.go
│   │   ├── openalex_enrich.go
│   │   └── s2_enrich.go
│   ├── dedupe/                # 去重引擎
│   │   ├── simhash.go
│   │   └── merge.go
│   ├── extract/               # 文本/HTML 提事实
│   │   ├── html.go
│   │   └── pdf.go
│   ├── anno2ppt/              # 标注 → PPT
│   │   ├── card.go            # antfu 样式卡片
│   │   ├── pptx.go            # python-pptx 子进程
│   │   └── render.go
│   ├── persist/               # FTS5 + JSON 持久化
│   │   ├── json.go
│   │   ├── fts5.go
│   │   └── qa.go
│   └── version/               # 版本信息
├── pkg/                       # 公开 Go API
│   ├── types.go               # Citation/EvidencePackage
│   ├── client.go              # 高级客户端
│   └── errors.go
├── rust/                      # Rust 热路径
│   ├── Cargo.toml
│   ├── src/
│   │   ├── lib.rs
│   │   ├── pdf.rs
│   │   ├── chunk.rs
│   │   └── ffi.rs             # cgo 给 Go 调用
│   └── cbindgen.toml
├── scripts/
│   ├── setup.sh               # 一键部署
│   ├── migrate-from-antfu.sh
│   ├── release.sh
│   └── dev.sh
├── templates/                 # 模板
│   ├── pptx/
│   │   └── antfu-card-v1.pptx
│   ├── latex/
│   │   ├── gbt7714.tex
│   │   └── vancouver.tex
│   └── config.example.yaml
├── tests/
│   ├── e2e/
│   ├── stress/
│   └── unit/
├── docs/
│   ├── ARCHITECTURE.md        # 本文档
│   ├── ROADMAP.md
│   ├── SOURCE-CONNECTORS.md
│   ├── MCP-TOOLS.md
│   ├── CLI-REFERENCE.md
│   └── ADAPTERS-MIGRATION.md
├── configs/
│   └── default.yaml
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── release.yml
│       └── codeql.yml
├── go.mod
├── go.sum
├── Cargo.lock
├── Cargo.toml
├── AGENTS.md                  # 跨工具兼容
├── LICENSE-MIT
├── LICENSE-AGPL-3.0
├── README.md
├── README.zh-CN.md
├── CHANGELOG.md
└── .gitignore
```

---

## 16. 路线图

### Phase 0（1-2 天，骨架）— **现在**
- [ ] 建目录树（按 §15）
- [ ] `go mod init github.com/veawho/via54Medit`
- [ ] `cargo new --lib rust/`
- [ ] 写 `AGENTS.md` / `LICENSE` / `README.md` / `CHANGELOG.md`
- [ ] 4 个空接口（Source/Embedder/VectorStore/Enricher）的 Go 定义
- [ ] `medit version` 可跑

### Phase 1（1 周，蚂蚁阿福适配）
- [ ] `internal/source/antfu.go` — 移植 cdp_client + extract_antfu_refs + persist_qa
- [ ] `internal/source/pubmed.go` — efetch + esearch
- [ ] `cmd/medit/antfu.go` — 4 子命令可用
- [ ] E2E 测试：问 1 个问题 → 拿到引用 → enrich → 落盘

### Phase 2（1 周，4 源 + Router）
- [ ] OpenAlex + S2 适配器
- [ ] `internal/router/` 4 文件实现
- [ ] `cmd/medit/ask.go` — 4 源并发 + 融合
- [ ] E2E：4 源并发, 去重排序, top 20

### Phase 3（1 周，PICO + GRADE + PPT）
- [ ] LLM 抽取 PICO
- [ ] GRADE 评级（基于 ROBINS-I / Cochrane Risk of Bias 启发）
- [ ] anno2ppt Rust 渲染
- [ ] `cmd/medit/anno2ppt.go`

### Phase 4（3 天，MCP + 跨平台）
- [ ] `cmd/medit-mcp/main.go` — 4 工具
- [ ] 在 Claude Desktop 跑通
- [ ] 跨平台构建（Win/Mac/Linux）

### Phase 5（持续，社区化）
- [ ] GitHub Release v1.0
- [ ] AGPL-3.0 + MIT 双许可 PR
- [ ] homebrew / scoop / apt 安装

---

## 17. 与 via54Design 共享代码的策略（**2026-06-24 降级为可选借鉴**）

> **修订**: 本节原写"via54Medit 强制依赖 via54Design"。**修订后** — via54Medit 默认 hand-roll 等价接口,via54Design 是**可选借鉴**(若开发者本地已 ready)。

### 17.1 借鉴什么（**可选**,非必须）

- `pkg/embedder/` 接口设计 + bge-m3 配置参考
- `pkg/vectorstore/` 接口设计 + Qdrant collection schema 经验
- `pkg/llm/` 多 provider 抽象思路
- `pkg/config/` YAML 加载范式
- `pkg/log/` 结构化日志字段约定

### 17.2 完全独立

- 源适配器（pubmed/openalex/s2/antfu）—— via54Medit 自己写
- PICO/GRADE 医学领域逻辑 —— via54Medit 自己写
- anno2ppt 医学模板 —— via54Medit 自己写
- 全部 `internal/` 子包 —— **via54Medit 0 外部业务依赖**

### 17.3 共享方式（**3 选 1,默认 ②**）

- **方式 ①（推荐但非强制）** = 若 `github.com/veawho/via54Design` 公开可用,via54Medit import 其 embedder/vectorstore/llm 子包。**前提**:此仓库 public 且稳定。**Phase 0 现实**:此仓库 private,本路径阻塞。
- **方式 ②（默认,2026-06-24 选定）** = via54Medit hand-roll 等价接口在 `internal/foundation/`,独立可跑。**`go.mod` 0 via54Design 依赖**。
- **方式 ③（远期）** = 抽出 `github.com/veawho/vea-kit` 公共包,via54Medit + via54Design 都依赖之。**v0.5 之后**评估。

**Phase 1 落地**:走 ②。`internal/foundation/embedder.go`、`vectorstore.go`、`llm.go`、`config.go`、`log.go` 五个文件 hand-roll,接口签名与 via54Design 保持一致(便于未来切换)。

---

## 18. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 蚂蚁阿福改版 | antfu 适配器失效 | 适配器隔离 + 黄金测试（9 DOI 案例） |
| PubMed 限速 | 全量 ask 慢 | 适配器内置 rate limiter + 并发控制 |
| bge-m3 1GB 部署 | 体积大 | 文档化快速安装 + 提供 --embedder=openai 备选 |
| LLM 抽取 PICO 错误 | 路由错 | 允许用户手动覆盖 PICO + 置信度低时提示 |
| Chrome 9223 单点 | antfu 失效 | 设计上 antfu 是可选项, 不影响其他 3 源 |
| MCP 协议变更 | MCP Server 失效 | 跟官方 SDK 走, 锁版本 |

---

## 19. 开放问题（**2026-06-24 全部拍板**）

> **拍板结论**: 6 条全部按推荐方案落档。**原"开放问题"标题保留作历史**;本节为定稿版。
>
> 拍板人: 巫师叔叔 via Hermes Agent
> 时间: 2026-06-24

### 拍板总表

| # | 问题 | 选项 | 拍板 | 一句话理由 |
|---|---|---|---|---|
| 1 | 命名空间 via54Medit / medit | **A** 维持现状 | ✅ **A** | Go module = repo name 是生态硬约定;CLI 短/库长业界先例 (gh/cli, kubectl/k8s) |
| 2 | MCP 工具数 (4 够吗?) | **A** 维持 4 个 + 长尾走 CLI | ✅ **A** | ≤5 是 Anthropic 推荐上限;CLI 路径更适合本地查询 + 迁移工具 |
| 3 | GRADE 真做 vs 简化版 | **A** 完整 / **B** 简化 | ✅ **B** | 完整 = 1 周 + 需医学专家持续维护;简化版 = 2-3 天可跑,后续 v0.5 渐进升级 |
| 4 | Web UI FastAPI + 前端 | **A** 做 / **B** 不做 | ✅ **B** | Hermes + Claude Desktop + Cursor MCP = 天然 UI;3 周工时 ROI 低,Phase 5 评估 |
| 5 | Windows 安装包 MSI/NSIS | **A** MSI / **B** zip + scoop | ✅ **B** | scoop + winget 是 2024+ 主流;MSI 是 2010 年代方案;zip 资产跨平台一致 |
| 6 | GitHub 公开时机 | **A** 不公开 (内部 v0.5) / **B** 立即 | ✅ **A** | 维持 private;Phase 5 社区化时再开 `--public` |

### 拍板详情

#### 1. 命名空间 — 维持 via54Medit (module) / medit (CLI) ✅

- **Go module** = `github.com/veawho/via54Medit` (不改,Go 生态硬约定)
- **CLI 二进制** = `medit` (单数,简短好打)
- **包名 = module 名** 是 `cmd/medit/main.go` 等文件 `import "github.com/veawho/via54Medit/..."` 必需
- **业界先例**: `gh` (CLI) / `github.com/cli/cli` (module) ;`kubectl` (CLI) / `k8s.io/kubernetes` (module) ;`docker` (CLI) / `github.com/docker/docker` (module)
- **未来切换成本**: 0 (无)

#### 2. MCP 工具数 — 维持 4 个 ✅

- **MCP 工具** = `medit_ask` / `medit_pico` / `medit_grade` / `medit_anno2ppt` (Phase 0 已定,Phase 4 实装)
- **本地知识库查询** = 走 CLI `medit query` (已存在 stub,Phase 2 落)
- **antfu v1.11 数据迁移** = 单独 CLI `medit-migrate-antfu` 子命令,不放 MCP (避免工具 schema 膨胀)
- **Anthropic 推荐上限** = MCP server ≤5 工具,超出会显著拖慢 LLM 决策
- **未来扩展触发**: 临床医生朋友反复要求本地查询 UI → 加 `medit_search_local`

#### 3. GRADE 评级 — 简化版先行 ✅

- **Phase 3 落地版本** = 简化 GRADE
  - **算法**: `score = (n_citations ≥ 5 ? +2 : +1) + (multi_source_count ≥ 3 ? +2 : 0) + (RCT_ratio ≥ 0.5 ? +2 : 0) + (recency ≥ 3yr ? +1 : 0)`
  - **等级映射**: score 6-7=A, 4-5=B, 2-3=C, 0-1=D
  - **不依赖**: Cochrane RoB 2 偏倚风险评估工具 / GRADEpro 配套软件
  - **依赖**: 引用数 + 源数 + 研究类型 (RCT vs 观察) + 时新性
- **完整版延后评估**: 需 1 名医学方法学专家 + 1 周工时,**v0.5 之后**评估 ROI
- **第一性铁律** (AGENTS.md): 先有可跑示例,再迭代精度

#### 4. Web UI — 不做 ✅

- **理由 1**: 你日常用 Hermes / Claude Desktop / Cursor,MCP 工具 = 对话即查询,天然 UI
- **理由 2**: FastAPI + HTMX + DaisyUI 单页 ≈ 300 行,**3 周工时**
- **理由 3**: 维护成本双倍 (前端 + 后端) 违反"单二进制 + MCP+CLI"哲学
- **延后触发**: Phase 5 社区化时,若需要 demo 站 / 临床医生非技术用户,做 1 个静态站
- **替代方案**: CLI 输出支持 `--format html` (单文件,可邮件分享) 已在 ROADMAP 中

#### 5. Windows 安装包 — zip + scoop manifest ✅

- **Phase 4 跨平台交付物**:
  - `bin/medit-windows-amd64.zip` (含 medit.exe + medit-mcp.exe + 默认配置 + LICENSE)
  - `bin/medit-darwin-amd64.tar.gz` (macOS Intel)
  - `bin/medit-darwin-arm64.tar.gz` (M1/M2)
  - `bin/medit-linux-amd64.tar.gz`
  - `bin/medit-linux-arm64.tar.gz` (树莓派/OpenWrt)
  - `SHA256SUMS` (签名)
- **包管理器**:
  - Windows: `scoop bucket add veawho https://github.com/veawho/scoop-bucket && scoop install medit`
  - macOS: `brew install veawho/tap/medit` (v0.5 之后)
  - Linux: `apt install medit` (v0.5 之后,需打包仓库)
- **不做 MSI/NSIS 理由**: scoop + winget 是 2024+ 主流,MSI 是 2010 旧方案,且需 .NET Framework 运行时
- **企业用户 MSI 需求**: v0.5 之后用 NSIS 单脚本补(只为它,不为它牺牲架构)

#### 6. GitHub 公开 — 维持 private,Phase 5 再开 ✅

- **当前**: `origin/main` 配 `https://github.com/veawho/via54Medit.git`,**仓库 private**
- **公开触发条件** (任一):
  - Phase 5 社区化启动
  - 累计 ≥ 50 个 GitHub star (内部 + 朋友同事)
  - v0.5 stable release
- **提前公开风险**: 外部 PR 压力 + 文档 commit 频率被迫提高 + 4A 快速迭代节奏被破坏
- **替代方案**: 内部 mirror 到 Gitee (国内可访问性) 同步,等 v0.5 后再开 GitHub public
- **决策回滚点**: 若 v0.3 之前发现社区有强烈需求(知乎/微博/V2EX 有人问),提前到 v0.4 公开

### 拍板后的影响清单

| Phase | 受影响项 | 状态 |
|---|---|---|
| Phase 1 | MCP 工具数量维持 4,迁移工具做 CLI 不进 MCP | 无变化 |
| Phase 1 | GRADE 走简化版,接口预留 Cochrane 升级空间 | 已在 ARCHITECTURE §5.3 设计 |
| Phase 3 | Web UI 不写,CLI `--format html` 可替代 | 减 1 项交付 |
| Phase 4 | zip 资产 + scoop manifest,不做 MSI | 5 平台 zip 改 4 平台(去掉 NSIS) |
| Phase 5 | GitHub 公开 + brew/apt/Docker | 维持计划 |

---

## 19.1 Phase 0 实际状态注脚（2026-06-24 深度验证后补，**同日修订**）
> **2026-06-24 二次修订**: 本节原写"Phase 1 入口前必须拍板 via54Design"。**已修订** — 用户拍板走 §17.3 方式 ②(hand-roll),via54Medit **0 外部业务依赖**。本节作为**历史记录保留**。

### A. via54Design 实际接入状态：未接入（已降级为可选借鉴）

第 2 节、第 9 节、第 17 节原写"via54Medit 依赖 `github.com/veawho/via54Design/pkg/embedder`、`.../vectorstore`、`.../llm`、`.../config`、`.../log` 五套包"。

**修订后**：via54Medit **不强制依赖** via54Design。`go.mod` 维持只有 cobra 一个第三方包,内部走 `internal/foundation/` hand-roll 等价接口。

**Phase 0 真实状态**（`go.mod` + `go.sum` + 全代码 `grep` 验证,2026-06-24）：

| 维度 | 文档原声明 | Phase 0 现实 | 修订后定性 |
|---|---|---|---|
| `go.mod` require | via54Design 五个子包 | ❌ 0 依赖（仅 cobra v1.8.0） | ✅ 维持（强制最小集） |
| `go.sum` 哈希 | via54Design 模块哈希 | ❌ 0 行 | ✅ 维持 |
| `SourceAdapter` 接口 | import via54Design 后手薄 | ⚠️ hand-roll | ✅ 维持 hand-roll |
| `embedder` flag | via54Design 共享 | ⚠️ CLI 注册了 flag 但无后端实现 | 🔜 Phase 1 落 `internal/foundation/embedder.go` |
| `vectorstore` flag | via54Design 共享 | ⚠️ 同上 | 🔜 同上 |
| LLM provider (`--provider`) | via54Design 多 provider 抽象 | ⚠️ 同上 | 🔜 同上 |

### B. via54Design 接入路径（**已选 ②**）

```
路径 ① (推荐但非强制) 等 via54Design 仓库就绪 + public → 真实 import 五个子包
路径 ② (默认,2026-06-24 选定) via54Medit hand-roll 全部接口 + 客户端 → 0 外部业务依赖
路径 ③ (远期)  抽出第三方 vea-kit 包 → via54Medit + via54Design 都依赖 vea-kit
```

**用户拍板（2026-06-24）**:走 ②。本节"待拍板"标识作废,Phase 1 直接开干 `internal/foundation/`。

### C. Phase 0 质量门禁执行实况

| 门禁 | 声明 | 实跑结果 |
|---|---|---|
| `go build` | ✅ | ✅ |
| `go vet` 0 警告 | ✅ | ✅ |
| `gofmt -l` 0 输出 | ✅ (隐含) | ❌ 2 文件（已修） |
| 单元测试 ≥ 1 | ❌ 未声明 | ❌ 0 个 |
| `go test -race` | ✅ (AGENTS.md §9) | ❌ 无测试可跑 |
| 覆盖率 ≥ 80% | ✅ (AGENTS.md §9) | ❌ N/A |
| `git tag phase0-done` | ✅ (ROADMAP §回滚) | ❌ 缺失（本次补） |

AGENTS.md §9 列的"质量门禁 8 项"中，**3 项（lint / race / coverage）从未被机械验证过**。建议在 Phase 1 把"门禁"改写为"明文可跑的脚本"（`scripts/quality-gate.sh`），杜绝文档与现实脱节。

---

## 20. 一句话总结

**`via54Medit` = 独立运行的医学循证工具集**——**不强制依赖** via54Design 或任何私有仓库。借鉴同样的工程哲学（确定性 + 插件式 + 单二进制 + MCP+CLI），同样的接口设计（embedder/vectorstore/llm/config/log）但**通过 `internal/foundation/` hand-roll 等价实现**确保 `git clone && go build` 即可跑。用语义路由+多源融合解决医学证据检索的真实痛点。

> 巫师叔叔 4A 时代的核心能力是"信息整合 + 视觉表达"，`via54Medit` 是这两个能力在医学循证领域的 Rust 级产品化。

---

## 21. 独立运行原则（**2026-06-24 新增**）

> 本节是**最高优先级架构约束**——任何破坏独立运行的 PR 都不接受。

### 21.1 铁律

```
git clone https://github.com/veawho/via54Medit.git
cd via54Medit
go build -o bin/medit.exe ./cmd/medit
./bin/medit.exe version
```

**这三步必须 100% 成功,不依赖任何私有仓库。**

### 21.2 强制最小集（`go.mod` 真实依赖）

| 包 | 用途 | Phase |
|---|---|---|
| `github.com/spf13/cobra` | CLI 框架 | Phase 0 ✅ |

**Phase 0 当前 = 1 个包。** Phase 1 引入 yaml.v3 + net + goquery + websocket。**via54Design 永不在此列**。

### 21.3 借鉴 ≠ 依赖

| 维度 | via54Medit 策略 |
|---|---|
| 接口设计 | 借鉴 via54Design 的 embedder/vectorstore/llm 抽象（签名一致） |
| 实现 | hand-roll 在 `internal/foundation/embedder.go` 等文件 |
| 切换路径 | 若 via54Design 后续 public，可在 `internal/foundation/viadesign.go` 用 build tag `//go:build viadesign` 替换,主分支维持 0 依赖 |
| 跨项目包 | v0.5 之后评估 vea-kit 抽取,本期不做 |

### 21.4 internal/foundation 落地清单（Phase 1 新增）

```
internal/foundation/
├── embedder.go         # Embedder 接口 + bge-m3 / openai / sense-nova 实现
├── vectorstore.go      # VectorStore 接口 + qdrant / meilisearch / sqlite 实现
├── llm.go              # LLM Provider 接口 + hermes / openai / anthropic / ollama
├── config.go           # YAML 加载（gopkg.in/yaml.v3）
└── log.go              # 结构化日志（log/slog）
```

**5 个文件,500-800 行总代码量,Phase 1 一次性写完。**

### 21.5 与文档历史关系

- **§9** 关键依赖：via54Design 标记为"可选借鉴"
- **§17** 共享策略：明确选 ②(hand-roll)
- **§2** 与 via54Design 关系表：Embedder/VectorStore 列改为"可借鉴"
- **AGENTS.md** 关键约束 6：从"不依赖 Hermes 内部 API"扩展为"不依赖任何私有仓库"
- **README.md** 致谢：via54Design 从"共享基础层"改为"借鉴接口设计"

以上所有改动**保留文档历史**（通过 §19.1 注脚 + 时间戳标注）,不删旧表述,只加"已修订"标识。
