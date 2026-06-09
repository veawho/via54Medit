# via54Medit

> Multi-Source Medical Literature Router for Evidence-Based Medicine

[![License: AGPL-3.0](https://img.shields.io/badge/code-AGPL--3.0-blue.svg)](LICENSE-AGPL-3.0)
[![License: MIT](https://img.shields.io/badge/templates-MIT-green.svg)](LICENSE-MIT)
[![Go Version](https://img.shields.io/badge/go-1.22+-00ADD8.svg)](https://go.dev)
[![Rust Version](https://img.shields.io/badge/rust-1.75+-orange.svg)](https://www.rust-lang.org)

`via54Medit` 是一个用**自然语言驱动的多源医学文献语义路由器**——把临床问题路由到最合适的文献源（蚂蚁阿福 RAG / PubMed / OpenAlex / Semantic Scholar），融合检索结果，输出可标注、可入知识库、可生成 PPT 的循证证据包。

> **不是又造一个文献检索工具，是造调度器。**

## 特性

- 🔀 **语义路由** — 自然语言 → PICO 抽取 → 6 类 EBM 问题 × 5 类意图 → 4 源并发调度
- 📚 **多源融合** — 蚂蚁阿福 RAG + PubMed + OpenAlex + S2，去重 + 加权排序
- 🎯 **GRADE 评级** — 半标准 GRADE (RCT 分桶 + 多源印证 + I² 不一致性)
- 🎨 **标注 PPT** — antfu 样式引用卡片，PDF 关键词红框标注
- 🧠 **知识库** — 插件式 Embedder (bge-m3) + VectorStore (Qdrant) + SQLite FTS5
- 🔌 **MCP Server** — 4 工具 (`medit_ask` / `medit_pico` / `medit_grade` / `medit_anno2ppt`)
- ⚡ **CLI + 双二进制** — `medit` (13 子命令) + `medit-mcp` (4 工具)
- 🌐 **跨平台** — Windows / macOS / Linux

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

- [via54Design](https://github.com/veawho/via54Design) — 共享 embedder/vectorstore/llm/config/log 基础层
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
