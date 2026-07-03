# via54Medit (中文 README)

> 多源医学文献循证语义路由器

`via54Medit` 是面向**循证医学 (EBM)** 的多源文献检索 + 融合工具，通过自然语言提问，自动调度 4 个文献源（蚂蚁阿福 RAG + PubMed + OpenAlex + Semantic Scholar），返回去重 + 加权排序 + GRADE 评级的循证证据包。

## 一句话定位

**自然语言问题 → 4 源并发检索 → 循证证据包（JSON + 摘要 + GRADE + PPT）**

## 与 via54Design 的关系

- via54Design = 创意设计 (确定性模板引擎)
- **via54Medit = 医学循证 (语义路由 + 证据融合)**
- 共享同一套基础层：embedder / vectorstore / llm / config / log
- 同一组织 (veawho)、双许可 (MIT + AGPL-3.0)、同一形态 (MCP + CLI)

## 适用场景

- 临床医生快速查证 (治疗 / 诊断 / 预后 / 病因 / 预防)
- 医学生做系统综述 (PRISMA 流程)
- 医学研究者写综述 (PICO 抽取 + GRADE 评级)
- 任何需要"中文 + 英文 + 蚂蚁阿福 AI 整合"的医学文献查询

## 4 文献源速览

| 源 | 优势 | 限制 |
|---|---|---|
| 蚂蚁阿福 (chat.antafu.com) | RAG + 循证中文医学 | 需 Chrome 9223, 48s/次 |
| PubMed | NCBI 权威, MeSH | 英文为主, 3 req/s |
| OpenAlex | 2 亿+ 论文, 免费, 全领域 | 时延高 |
| Semantic Scholar | AI 摘要 (TLDR), FWCI | 5K req/day 免费 |

## 安装

### 方式 A: scoop (推荐, Windows)
```bash
scoop bucket add veawho https://github.com/veawho/scoop-bucket
scoop install medit
```

### 方式 B: 手动下载
从 [GitHub Releases](https://github.com/veawho/via54Medit/releases) 下载 zip，解压到 `PATH`。

### 方式 C: 源码编译
```bash
git clone git@github.com:veawho/via54Medit.git
cd via54Medit
go build -o bin/medit.exe ./cmd/medit
go build -o bin/medit-mcp.exe ./cmd/medit-mcp
```

## 配置

```bash
# 复制默认配置
medit init  # 生成 ~/.medit/config.yaml

# 编辑
vim ~/.medit/config.yaml
```

详见 [configs/default.yaml](configs/default.yaml)。

## 13 个 CLI 子命令

```bash
medit ask <query>           # 一句话检索 (推荐入口)
medit search <query>        # 原始多源检索
medit pico <query>          # PICO 抽取
medit systematic <query>    # 系统综述 (PRISMA)
medit grade <package>       # GRADE 评级
medit pubmed <subcmd>       # 直查 PubMed
medit openalex <subcmd>     # 直查 OpenAlex
medit s2 <subcmd>           # 直查 S2
medit antfu <subcmd>        # 蚂蚁阿福
medit enrich <refs.json>    # 三方 enrich
medit index <file/dir>      # 入 Qdrant
medit query <query>         # 检索本地知识库
medit anno2ppt <package>    # 证据包 → PPT
medit version               # 版本信息
```

## 🤖 AI Agent 智能体与 Skill 接入

本项目为各类 AI Agent 提供了开箱即用的对接方式：

### A. MCP (Model Context Protocol) 协议接入
项目提供了基于 Stdio 的 MCP 服务实现（位于 [cmd/medit-mcp](cmd/medit-mcp)，可编译为 `bin/medit-mcp`），注册并暴露了以下 4 个 Tools：
* `medit_ask`：一句话循证检索 (4 源并发 + LLM 摘要)。
* `medit_pico`：临床问题 PICO 要素提取。
* `medit_grade`：对会话证据包执行 GRADE 证据质量评级。
* `medit_anno2ppt`：将证据包导出为 PPT 幻灯片。

在 Claude Desktop / Cursor 配置文件中添加以下配置即可调用：
```json
{
  "mcpServers": {
    "medit": {
      "command": "/path/to/via54Medit/bin/medit-mcp",
      "args": []
    }
  }
}
```

### B. 本地 Workspace 技能 (Antigravity/Claude Skill)
项目已打包好可供本地 Agent 自动扫描与装载的 Workspace Customization Skill：
* **技能路径**：[.agents/skills/via54medit/SKILL.md](.agents/skills/via54medit/SKILL.md)
* **作用**：当智能体在此工作区工作时，会自动发现并学会自主调用 `bin/medit` 的各个 CLI 命令（包含 `systematic` 等）来处理您的医学和文献相关任务。

### C. 外部平台自定义技能 (Dify / FastGPT OpenAPI)
项目在 `api/` 目录下提供了标准的 OpenAPI 3.0 接口规范文档：
* **规范文件**：[api/openapi.yaml](api/openapi.yaml)
* **使用方式**：您可以直接在 Dify 或 FastGPT 的“自定义工具 (Tools/Skills)”中粘贴此 OpenAPI yaml 定义，即可为您的云端 AI 助手配置标准的循证医学联合检索与分析能力。

## 路线图

- **Phase 0** — 骨架
- **Phase 1** — 蚂蚁阿福 + PubMed 适配器
- **Phase 2** — OpenAlex + S2 + Router + 4 源融合
- **Phase 3** — PICO + GRADE + anno2ppt
- **Phase 4** — MCP Server + 跨平台 + scoop (当前已实装 stdio 传输)
- **Phase 5** (持续) — 社区化

详见 [ROADMAP.md](docs/ROADMAP.md)。

## 安全/合规

- 不存储患者隐私
- 蚂蚁阿福 ToS 灰色 — 只检索, 不批量下载
- PubMed/OpenAlex/S2 遵守 rate limit
- 审计日志: `~/.medit/audit/<date>.jsonl`

## 贡献

本项目目前**私库**, 由巫师叔叔 via Hermes Agent 迭代。
v0.5 后考虑公开 (Phase 5)。

## 许可

- 源码: AGPL-3.0
- 模板/配置/文档: MIT

---

**作者**: 巫师叔叔 (via54)
**创建**: 2026-06-09
