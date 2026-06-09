# via54Medit 路线图

> 与 `ARCHITECTURE.md` 配合阅读。ARCHITECTURE 是"是什么", 本文件是"何时做"。

## 5 阶段总览

| Phase | 时间 | 核心目标 | 可用功能 |
|---|---|---|---|
| **0** | 1-2 天 | **骨架** | `medit version` + 13 stub 子命令可跑 |
| **1** | 1 周 | **蚂蚁阿福 + PubMed** | `medit antfu ask` + `medit pubmed search` |
| **2** | 1 周 | **4 源 + Router** | `medit ask` 4 源并发 + 融合 |
| **3** | 1 周 | **PICO + GRADE + PPT** | `medit pico` + `medit grade` + `medit anno2ppt` |
| **4** | 3 天 | **MCP + 跨平台 + scoop** | `medit-mcp` 4 工具 + 三平台 release |
| **5** | 持续 | **社区化** | GitHub public release + homebrew/apt |

## Phase 0 — 骨架（**已完成 2026-06-09**）

- [x] 建完整目录树 (22 子目录)
- [x] `go.mod` / `Cargo.toml` 初始化
- [x] `docs/ARCHITECTURE.md` (20 节, 5 层架构)
- [x] `AGENTS.md` (跨 AI 工具规约)
- [x] `README.md` / `README.zh-CN.md` / `CHANGELOG.md`
- [x] `LICENSE-AGPL-3.0` / `LICENSE-MIT` (双许可)
- [x] 4 个核心接口 (Source / Enricher / Router / Types)
- [x] `medit version` 可跑 + 13 stub 子命令
- [x] `go vet ./...` 零警告
- [x] GitHub 私库: github.com/veawho/via54Medit
- [x] 第一次 commit + push

**质量门禁**:
- ✅ `go build` 通过
- ✅ `go vet` 零警告
- ✅ 555 行 Go 代码
- ✅ 0 个 TODO 在生产代码路径

**未来每个 Phase 入口前**: 重读 ARCHITECTURE.md 对应章节 + 更新 CHANGELOG.md。

## Phase 1 — 蚂蚁阿福 + PubMed 适配器（**1 周**）

### 1.1 内部 (internal/)
- [ ] `internal/source/antfu.go` — 移植 cdp_client.py (Python → Go + gorilla/websocket)
  - [ ] 导航: `Page.navigate`
  - [ ] 注入查询: `Runtime.evaluate` 选 `textarea.ant-input`
  - [ ] 等待 RAG 响应: ~48s (deep_search=true)
  - [ ] 提取答案: 监听 DOM 变化
- [ ] `internal/source/antfu_extract.go` — 移植 extract_antfu_refs.py
  - [ ] 9 DOI 黄金测试 (来自 antfu v1.11 验证案例)
  - [ ] 解析 `div.quotedMaterials` 结构
- [ ] `internal/source/pubmed.go` — NCBI E-utilities
  - [ ] `esearch` (按 query → PMID list)
  - [ ] `efetch` (按 PMID → XML → Citation)
  - [ ] XML 解析 (encoding/xml)
  - [ ] Rate limiter: 3 req/s (无 API key)
- [ ] `internal/persist/qa.go` — 移植 persist_qa.py
  - [ ] 路径: `~/.medit/qa/<conv_id>.json`
  - [ ] SQLite FTS5 索引: `~/.medit/fts5.db`
  - [ ] Markdown 导出: `~/.medit/qa/<conv_id>.md`

### 1.2 CLI (cmd/medit/)
- [ ] `antfu.go` — 4 子命令
  - [ ] `medit antfu ask <query>` — 问 + 提取 + 持久化
  - [ ] `medit antfu screenshot` — 抓侧栏引用区截图
  - [ ] `medit antfu extract` — 从 HTML 提取引用
  - [ ] `medit antfu chat-list` — 列历史对话
- [ ] `pubmed.go` — 3 子命令
  - [ ] `medit pubmed search <query> --max N`
  - [ ] `medit pubmed fetch <PMID>`
  - [ ] `medit pubmed efetch <PMID>`

### 1.3 测试
- [ ] `tests/unit/source_antfu_test.go` — 9 黄金测试
- [ ] `tests/unit/source_pubmed_test.go` — mock NCBI 响应
- [ ] `tests/e2e/antfu_e2e.sh` — 真实 Chrome 9223 + 1 个问题

### 1.4 文档
- [ ] `docs/SOURCE-CONNECTORS.md` — 蚂蚁阿福 / PubMed 详解
- [ ] `docs/ADAPTERS-MIGRATION.md` — 从 antfu v1.11 迁移指南

**质量门禁**:
- ✅ `medit antfu ask "SGLT2 心衰"` 端到端跑通
- ✅ `medit pubmed search` 真实返回 ≥10 条
- ✅ 黄金测试 9/9 通过
- ✅ `go test -race -coverprofile=coverage.out` ≥80% 覆盖

## Phase 2 — OpenAlex + S2 + Router（**1 周**）

### 2.1 适配器
- [ ] `internal/source/openalex.go`
  - [ ] `/works?search=...` 端点
  - [ ] 解析 authorships / concepts / cited_by_count / FWCI
  - [ ] polite pool: `mailto=` 参数
- [ ] `internal/source/s2.go`
  - [ ] `/paper/search?query=...` 端点
  - [ ] 解析 TLDR / citationCount / influentialCitationCount
  - [ ] 5K req/day 限速

### 2.2 Router 核心 (internal/router/)
- [ ] `classify.go` — EBM 6 类问题分类 (LLM 调用)
  - [ ] 提示词模板: `templates/prompts/classify_ebm.txt`
  - [ ] 6 类: 治疗/诊断/预后/病因/预防/经济
- [ ] `plan.go` — 任务规划
  - [ ] 单源 / 多源 / 链式 三种执行图
- [ ] `dispatch.go` — 4 源并发
  - [ ] worker pool + semaphore
  - [ ] 30s 每源 timeout + 3 次指数退避
  - [ ] fallback 链: antfu → pubmed → openalex → s2
- [ ] `merge.go` — 结果融合
  - [ ] PMID/DOI 一等公民去重
  - [ ] simhash (title) 汉明距 < 3 合并
  - [ ] 加权排序: cited_by (0.3) + recency (0.2) + fwci (0.3) + multi_source (0.2)

### 2.3 Enrich 流水线
- [ ] `internal/enrich/pubmed_enrich.go`
- [ ] `internal/enrich/openalex_enrich.go`
- [ ] `internal/enrich/s2_enrich.go`
- [ ] `internal/enrich/pipeline.go` — 三方并发

### 2.4 CLI
- [ ] `ask.go` — 4 源并发 + 融合 + LLM 摘要
- [ ] `search.go` — 原始多源 (无 LLM 摘要)
- [ ] `enrich.go` — 三方 enrich 离线工具
- [ ] `index.go` — 入 Qdrant
- [ ] `query.go` — 检索本地

### 2.5 测试
- [ ] `tests/unit/router_classify_test.go` — 30 个分类案例
- [ ] `tests/unit/router_merge_test.go` — 黄金测试 (10 DOI, 验证权重)
- [ ] `tests/stress/ask_100x.sh` — 100 次 ask 压力

**质量门禁**:
- ✅ `medit ask "SGLT2 心衰"` 4 源并发 < 60s 完成
- ✅ Router 分类 30/30 准确
- ✅ 融合排序 top 5 与手工筛选一致
- ✅ 100 次压力零 panic

## Phase 3 — PICO + GRADE + anno2ppt（**1 周**）

### 3.1 PICO 抽取
- [ ] `internal/router/pico.go` — LLM 抽取 PICO 四要素
- [ ] `internal/router/pico_test.go` — 20 案例
- [ ] `cmd/medit/pico.go` — CLI 子命令

### 3.2 GRADE 半标准
- [ ] `internal/router/grade.go` — GRADE 算法
  - [ ] RCT vs 观察研究分桶
  - [ ] 多源印证 (≥3 源 = +1)
  - [ ] 不一致性 (I² proxy from S2 citation network)
  - [ ] 输出: A/B/C/D + 推理说明
- [ ] `cmd/medit/grade.go` — CLI

### 3.3 anno2ppt (Rust 热路径)
- [ ] `rust/src/pdf.rs` — PDF 文本提取
- [ ] `rust/src/chunk.rs` — 关键词定位
- [ ] `rust/src/ffi.rs` — cgo 暴露给 Go
- [ ] `internal/anno2ppt/card.go` — antfu 样式卡片
- [ ] `internal/anno2ppt/pptx.go` — python-pptx 子进程 (RUST 不可行, PPTX 仍走 Python)
- [ ] `cmd/medit/anno2ppt.go` — CLI

### 3.4 测试
- [ ] `tests/unit/router_grade_test.go` — 10 案例
- [ ] `tests/unit/anno2ppt_card_test.go` — 卡片视觉对比
- [ ] `tests/e2e/anno2ppt.sh` — 真实 DAPA-HF PDF → PPT

**质量门禁**:
- ✅ GRADE 评级 10/10 与医学专家一致
- ✅ anno2ppt 卡片视觉与 antfu 真实引用区像素差 <5%
- ✅ PDF 标注准确率 ≥95%

## Phase 4 — MCP + 跨平台 + scoop（**3 天**）

### 4.1 MCP Server
- [ ] `cmd/medit-mcp/main.go` — 真实 MCP transport
- [ ] `cmd/medit-mcp/tools.go` — 4 工具实现
  - [ ] `medit_ask`
  - [ ] `medit_pico`
  - [ ] `medit_grade`
  - [ ] `medit_anno2ppt`
- [ ] `cmd/medit-mcp/transport.go` — stdio (默认) + HTTP (可选)

### 4.2 跨平台
- [ ] `Makefile` — 5 平台 (darwin/linux/windows × amd64/arm64)
- [ ] `.goreleaser.yaml` — 自动化 release
- [ ] `scripts/release.sh` — 本地交叉编译
- [ ] GitHub Actions `.github/workflows/release.yml`

### 4.3 scoop manifest
- [ ] `scripts/scoop-bucket/medit.json`
- [ ] `scripts/scoop-bucket/README.md`
- [ ] PR 到自己的 `veawho/scoop-bucket` 仓库

### 4.4 测试
- [ ] `tests/integration/mcp_e2e.go` — Claude Desktop 真实调用
- [ ] 5 平台 binary 全跑 `medit version`

**质量门禁**:
- ✅ `medit-mcp` 在 Claude Desktop 中 4 工具全调通
- ✅ 5 平台 binary `medit version` 全 OK
- ✅ scoop install 一行装好

## Phase 5 — 社区化（**持续**）

- [ ] GitHub public release (改 `--public`)
- [ ] homebrew formula
- [ ] apt / dnf repo
- [ ] Docker image (medit + qdrant + bge-m3)
- [ ] 文档站: GitHub Pages + mkdocs
- [ ] 视频教程: 30 分钟 demo
- [ ] Discord / 微信群

## 进度跟踪

每个 Phase 完成后:
1. 更新本文档对应章节的复选框
2. `CHANGELOG.md` 写一行
3. `git commit -m "Phase X: <achievement>"`
4. `git push` 到 GitHub 私库
5. (Phase 5 后) 改 `--public` 公开

## 风险与回滚

每个 Phase 结束前, 跑 `git tag phaseN-done`。回滚:
```bash
git checkout phaseN-done
```
