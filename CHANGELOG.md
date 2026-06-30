# Changelog

All notable changes to via54Medit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).




## [4.5.2.1] - 2026-06-30 (重写通俗版)

### Changed
- DECISIONS-PENDING.md 重写为通俗版 (大白话 + 表格, 不用技术术语)
- 之前版本太技术 (binary/MCP/layer 等), 用户看不懂, 现重写

## [4.5.2] - 2026-06-30 (decision lock round 2)

### Decision Lock (用户 ~15:50 TG 决策)
- **2. 暂时不变** = 12 P0 源列表保留 (EBM 6 + 商业 6, TalkMED 7 页 PDF 需求)
- **3. 信息太少无法决策** = 待用户补细节. 已展开成 5 明确问题 (见 DECISIONS-PENDING.md)
- **6. 信息太少无法决策** = 待用户补细节. 已展开成 5 明确问题 (见 DECISIONS-PENDING.md)

### Total
- 已锁: 决策 1 (架构), 2 (P0 源), 4 (付费源 = 0)
- 待补: 决策 3 (CLI 隔离), 5 (锁定 ✅), 6 (biomcp 集成)
- 实际 5 个决策点 (§8) 中 2/3/5/6 待补, 5 已锁=4 一致
## [4.5.1] - 2026-06-30 (decision lock)

### Decision Lock (用户 15:42 TG 决策)
- **1. 暂不调整** = 接受现状, 双模式 EBM 学术 + 商业情报架构保留
- **4. 不适用付费源** = 排除所有付费源 (Frost/Grand View/Citeline/GlobalData/AdisInsight/BioCentury/Endpoints/STAT/PharmCube 交易库/Bloomberg/WiseGuy/Statista/Huaon/Menet/PharnexCloud 等)
- **2/3/5/6. 决策需更多细节** = 暂搁, 等用户补决策

### Changed
- CATALOG.md P3 商业授权表 + 商业情报 P1/P2 表格标 ~~删除线~~ (排除付费)
- CHANGELOG 锁决策: 不接付费源
- ARCHITECTURE-V5-DRAFT.md §8 决策点 4 (商业付费源预算) 锁: 不接付费

### Total
- EBM 学术: 52+ 免费源 (保留)
- 商业情报: 16+ P0 全部免费/开源 (保留)
- 商业付费源: **0** (排除, 决策 4)
## [4.5.0] - 2026-06-29

### Added
- integrations/ 目录: 6 个高星医学文献项目 (local-deep-research, paper-search-mcp, MetaScreener, asreview, pubmed_parser, pyalex)
- integrations/paper-search-mcp.md: 集成计划 (3 个新 MCP tools)
- REFERENCES.md: 6 个高星项目

### Changed
- 升级 v4.0 -> v4.5
- 从 "4 MCP tools" -> "7 MCP tools planned"
## [4.0 -> 4.5] - 2026-06-29

- Upgrade to v4.5 - integrate local-deep-research 8.6K patterns
- Plan: paper-search-mcp 2K integration (we have MCP, they have search)
- Plan: MetaScreener 1.3K PDF full-text screening
- Plan: asreview 937 active learning

## [Unreleased]

### Phase 5.0 升级 (2026-06-30) — 双模式医药决策平台
> **触发**: 用户提交 TalkMED AgentPilot 7 页 PDF 报告 (123.pdf), 要求融合 EBM 学术 + 商业医药情报 + TalkMED 类报告生成 3 个方向
> **状态**: 架构升级草稿完成, 等用户拍板

#### Added
- `integrations/CATALOG.md` — **115+ 数据源全景目录** (EBM 55+ + 商业 60+)
- `integrations/clinicaltrials_v2.md` — ClinicalTrials.gov v2 P0 集成计划
- `integrations/openfda.md` — OpenFDA P0 集成计划 (14 tools MCP)
- `integrations/sec_edgar.md` — SEC EDGAR P0 集成计划 (TalkMED 财报核心)
- `integrations/europe_pmc.md` — Europe PMC P0 集成计划
- `integrations/medrxiv_biorxiv.md` — 预印本 P0 集成计划
- `integrations/fda_orange_book.md` — Orange Book P0 集成计划 (专利+独占期)
- `integrations/chembl_pubchem.md` — ChEMBL/PubChem P0 集成计划 (化学实体)
- `integrations/dailymed.md` — DailyMed P0 集成计划 (药物标签)
- `integrations/pubtator3.md` — PubTator 3.0 P0 集成计划 (NLP 实体)
- `integrations/aha_acc_eas.md` — AHA/ACC/EAS 会议摘要 P1 集成计划 (TalkMED §4 直接相关)
- `docs/ARCHITECTURE-V5-DRAFT.md` — v5.0 双模式架构升级草案 (6 层 + 双模式路由)

#### Changed
- 项目定位: 单模式 EBM 路由器 → **双模式医药决策平台** (EBM 学术 + 商业情报)
- 架构: 5 层 → **6 层 + 双模式路由** (Layer 4A EBM / Layer 4B 商业)
- CLI: 13 子命令 → **18 子命令** (+5 商业: intel/market/pipeline/patent/trial)
- MCP: 4 tools → **7 tools** (+3 商业: medit_intel/medit_market/medit_pipeline)
- 数据源: 4 现存 → **16 P0** (10 学术 + 12 商业 - 6 重复)

#### Methodology
- **Subagent #1 (EBM 方向)**: 扫描 GitHub biocontext-ai/registry (60+ MCP) + awesome-evidence-synthesis, 找到 55+ 学术源 + genomoncology/biomcp 超级 MCP (MIT, 12+ 实体类别, 应当借鉴)
- **Subagent #2 (商业方向)**: 扫描 9 类商业源 (销售/管线/专利/财报/报告/会议/BD), 找到 60+ 商业源 + TalkMED PDF 反推 7 页报告需哪些源
- **整合**: CATALOG.md + 10 个 P0 集成计划 .md (1-3 天工作量/源)

#### Reference
- TalkMED AgentPilot (https://agent-pilot.talkmed.com) — DXY 旗下医药商业情报 AI 平台, 7 页 PDF 报告为参照样本

### Phase 0 (2026-06-09)

#### Added
- 项目初始化
  - `docs/ARCHITECTURE.md` — 5 层架构 + 20 节设计文档
  - `AGENTS.md` — 跨 AI 工具协作规约
  - `README.md` / `README.zh-CN.md` — 中英双语文档
  - `LICENSE-AGPL-3.0` / `LICENSE-MIT` — 双许可
  - 完整目录树 (22 个子目录)
  - Go module: `github.com/veawho/via54Medit`
  - Cargo workspace (rust/)
  - 4 个空接口 (Source / Embedder / VectorStore / Enricher)
  - `medit version` 可跑
  - GitHub 私库: github.com/veawho/via54Medit

### Phase 0 修订 (2026-06-24)

#### Changed
- **架构决策**: via54Design 强制依赖 → **可选借鉴** (走 ARCHITECTURE §17.3 路径 ② hand-roll)
- **新增铁律**: `git clone && go build` 必须 100% 成功,0 外部业务依赖 (ARCHITECTURE §21)
- **AGENTS.md 关键约束**: 新增第 7 条"不依赖任何私有仓库"
- **README.md 致谢段**: via54Design 改为"借鉴接口设计,实现独立"
- **configs/default.yaml**: 头部加修订说明
- **gofmt**: 2 个未格式化文件落地
- **单元测试**: 新增 8 cases (pkg/types 4 + internal/version 4)
- **git tag**: `phase0-done` annotated tag 落地

#### Closed (ARCHITECTURE §19 开放问题 6 条全部拍板)
- §19.1 命名空间: 维持 via54Medit (module) / medit (CLI)
- §19.2 MCP 工具数: 维持 4 个,本地查询走 CLI
- §19.3 GRADE 评级: 走简化版,完整版 v0.5 评估
- §19.4 Web UI: 不做,MCP 路径覆盖
- §19.5 Windows 安装包: zip + scoop/winget,不做 MSI
- §19.6 GitHub 公开: 维持 private,Phase 5 再开

[Unreleased]: https://github.com/veawho/via54Medit/compare/v0.0.0...HEAD
