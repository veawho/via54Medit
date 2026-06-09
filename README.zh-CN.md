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

## 4 个 MCP 工具

在 Claude Desktop / Cursor / VS Code Copilot 中:

```json
{
  "mcpServers": {
    "medit": {
      "command": "medit-mcp",
      "args": []
    }
  }
}
```

工具:
- `medit_ask` — 一句话循证检索
- `medit_pico` — PICO 抽取
- `medit_grade` — GRADE 评级
- `medit_anno2ppt` — 证据包 → PPT

## 路线图

- **Phase 0** (现在) — 骨架
- **Phase 1** (1 周) — 蚂蚁阿福 + PubMed 适配器
- **Phase 2** (1 周) — OpenAlex + S2 + Router + 4 源融合
- **Phase 3** (1 周) — PICO + GRADE + anno2ppt
- **Phase 4** (3 天) — MCP Server + 跨平台 + scoop
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
