# via54Medit


> **🌐 Language**: [🇨🇳 中文](#) (current) | [🇺🇸 English](./README_EN.md)
>
> _This document is in Chinese. For English, click above._
> Multi-Source Medical Literature Router for Evidence-Based Medicine

[![License: AGPL-3.0](https://img.shields.io/badge/code-AGPL--3.0-blue.svg)](LICENSE-AGPL-3.0)
[![License: MIT](https://img.shields.io/badge/templates-MIT-green.svg)](LICENSE-MIT)
[![Go Version](https://img.shields.io/badge/go-1.22+-00ADD8.svg)](https://go.dev)
[![Rust Version](https://img.shields.io/badge/rust-1.75+-orange.svg)](https://www.rust-lang.org)

`via54Medit` 是一个用**自然语言驱动的双模式医药决策平台** —— 

- **EBM 学术模式** (原方向): 把临床问题路由到最合适的医学文献源（蚂蚁阿福 RAG / PubMed / OpenAlex / Semantic Scholar + 6 个新增 P0），融合检索结果，输出可标注、可入知识库、可生成 PPT 的循证证据包
- **商业情报模式** (新方向): 把医药市场问题路由到商业数据源（OpenFDA / SEC EDGAR / FDA Orange Book / ChEMBL / 药智 / 会议摘要 等 12+ 个 P0），输出 TalkMED 风格 7 页市场报告（全球/中国 CAGR + 管线矩阵 + 临床数据 + 投资关注点）

> **不是又造一个文献检索工具，不是又造一个医药销售数据库，是造「双模式医药决策调度器」**

## 特性

- 🔀 **双模式语义路由** — 自然语言 → PICO + 商业实体抽取 → 6 类 EBM / 7 类商业查询 → 16+ 源并发调度
- 📚 **EBM 多源融合** — 蚂蚁阿福 RAG + PubMed + OpenAlex + S2 + ClinicalTrials.gov + Europe PMC + medRxiv + OpenFDA + DailyMed + PubTator，去重 + 加权排序
- 💼 **商业多源融合** — OpenFDA + FDA Orange Book + SEC EDGAR + ChEMBL/PubChem + CDE + SEC 10-K/8-K → 市场总览 + 管线矩阵 + 财报分析 + 投资 PPT
- 🎯 **GRADE 评级** (EBM) — 半标准 GRADE (RCT 分桶 + 多源印证 + I² 不一致性)
- 📊 **7 页 TalkMED 报告** (商业) — 全球市场 + 注射剂市场 + 在研管线 + 临床数据 + 投资关注点
- 🎨 **标注 PPT** — antfu 样式引用卡片，PDF 关键词红框标注
- 🧠 **知识库** — 插件式 Embedder (bge-m3) + VectorStore (Qdrant) + SQLite FTS5
- 🔌 **MCP Server** — 7 工具 (`medit_ask` / `medit_pico` / `medit_grade` / `medit_anno2ppt` / `medit_intel` / `medit_market` / `medit_pipeline`) *(Phase 0: stub，打印预期工具名后退出；Phase 4 实装)*
- ⚡ **CLI + 双二进制** — `medit` (18 子命令: 13 学术 + 5 商业) + `medit-mcp` (7 工具, Phase 0 stub)
- 🌐 **跨平台** — Windows / macOS / Linux

## 🔗 集成 (v5.0 升级中, **115+ 数据源**)

详见 **[integrations/CATALOG.md](integrations/CATALOG.md)** (EBM 55+ + 商业 60+)

### v5.0 P0 必集成 (12 个源)
**EBM 学术 (6)**: ClinicalTrials.gov v2 / Europe PMC / medRxiv+bioRxiv / OpenFDA / DailyMed / PubTator 3
**商业情报 (6)**: OpenFDA (双用) / FDA Orange Book / SEC EDGAR / ChEMBL / PubChem / ClinicalTrials.gov (商业维度)

### 关键参考项目 (借鉴或 MCP 协议调用)
- [LearningCircuit/local-deep-research](https://github.com/LearningCircuit/local-deep-research) (8.6K) - Local LLM 95% SimpleQA
- [openags/paper-search-mcp](https://github.com/openags/paper-search-mcp) (1.9K) - MCP for arXiv/PubMed
- [ChaokunHong/MetaScreener](https://github.com/ChaokunHong/MetaScreener) (1.3K) - AI systematic review screening
- [asreview/asreview](https://github.com/asreview/asreview) (937) - Active learning for systematic review
- [titipata/pubmed_parser](https://github.com/titipata/pubmed_parser) (734) - PubMed XML parser
- [J535D165/pyalex](https://github.com/J535D165/pyalex) (391) - OpenAlex Python library
- [dgunning/edgartools](https://github.com/dgunning/edgartools) (**2.4K**) - SEC EDGAR Python ⭐
- [genomoncology/biomcp](https://github.com/genomoncology/biomcp) - **12+ 实体类别超级 MCP (MIT)** ⭐⭐
- [cyanheads/openfda-mcp-server](https://github.com/cyanheads/openfda-mcp-server) - 14 tools OpenFDA ⭐
- [Sayan-CtrlZ/PharmaPilot](https://github.com/Sayan-CtrlZ/PharmaPilot) - CrewAI 医药情报 Agent (TalkMED 参照)
- [mahdinamavar/pharma-market-intelligence-ai](https://github.com/mahdinamavar/pharma-market-intelligence-ai) - OpenFDA + XGBoost 市场预测

详见 [integrations/README.md](integrations/README.md) 和 [REFERENCES.md](REFERENCES.md).

---

## 快速开始

```bash
# 安装 (scoop 用户)
scoop install medit

# 或下载 zip: github.com/veawho/via54Medit/releases

# 验证
medit version

# 一句话检索
medit ask "SGLT2 抑制剂对 2 型糖尿病合并心衰患者的预后如何？"

# 抽取 PICO
medit pico "阿司匹林能否预防 50 岁以上人群的心血管事件？"

# 直查 PubMed
medit pubmed search "SGLT2 heart failure" --max 20

# 系统综述
medit systematic "GLP-1 受体激动剂减重"

# 启动 MCP Server (在 Claude Desktop / Cursor 中调用)
# Phase 0: 打印预期工具名后退出；Phase 4 才有真实 stdio transport
medit-mcp
```

## 文档

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — 5 层架构 + 数据模型 + 路由算法
- [ROADMAP.md](docs/ROADMAP.md) — Phase 0-5 路线图
- [CLI-REFERENCE.md](docs/CLI-REFERENCE.md) — 13 子命令详解
- [MCP-TOOLS.md](docs/MCP-TOOLS.md) — 4 MCP 工具 schema
- [SOURCE-CONNECTORS.md](docs/SOURCE-CONNECTORS.md) — 4 文献源适配器实现
- [ADAPTERS-MIGRATION.md](docs/ADAPTERS-MIGRATION.md) — 从 antfu-evidence-search v1.11 迁移

## 致谢

- [via54Design](https://github.com/veawho/via54Design) — 借鉴接口设计（embedder/vectorstore/llm/config/log 抽象）;**实现独立**走 `internal/foundation/`（2026-06-24 修订,见 ARCHITECTURE §21）
- [antfu-evidence-search](https://github.com/) (v1.11.0) — 蚂蚁阿福 driver / 引用提取 / persist_qa 移植源
- [medlit-anno-ppt](https://github.com/) — antfu 样式 PPT 卡片设计移植源
- [PubMed E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25500/) — NCBI 官方 API
- [OpenAlex](https://openalex.org) — 2 亿+ 论文全免费
- [Semantic Scholar](https://www.semanticscholar.org/product/api) — 5K req/day 免费
- [蚂蚁阿福](https://chat.antafu.com) — 蚂蚁集团/支付宝医疗 AI 助手

## 许可

- **源码**: [AGPL-3.0](LICENSE-AGPL-3.0)
- **模板/配置/文档**: [MIT](LICENSE-MIT)

继承 via54Design 双许可策略。

---

**作者**: 巫师叔叔 (via54) + Hermes Agent
**创建**: 2026-06-09
**状态**: Phase 0 (骨架初始化)
