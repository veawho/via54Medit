# paper-search-mcp 集成计划

> **Source**: https://github.com/openags/paper-search-mcp (1.9K stars)
> **目的**: via54Medit Phase 4.0 已 MCP transport, 整合 paper-search-mcp 的 search 能力

## paper-search-mcp 核心

| 工具 | 描述 |
|------|------|
| search_arxiv | 搜索 arXiv 论文 |
| search_pubmed | 搜索 PubMed |
| download_paper | 下载 PDF |

## 集成步骤

### Phase 4.5: v0.5.0
- 加 3 个 MCP tools (search_arxiv, search_pubmed, download_paper)
- 跟现有 4 tools (ask, search, list, persist_qa) 整合
- 文档化: 7 MCP tools for medical research

### Phase 5.0: v0.6.0
- 集成 local-deep-research 8.6K 思路
- local LLM 推理 (无 OpenAI 依赖)
