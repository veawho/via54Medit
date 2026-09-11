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

## 📊 文献整理与 Highlight 监控统计独立模块 (`medit-telemetry`)

面向 `via54Medit` 与 `TraeWork` 文献管线（检索、下载、Highlight）打造的独立解耦**人效收益度量、大模型 Token 真实账单 100% 对齐与飞书全自动同步**系统。

* **独立包定义**：标准 Python 独立分发包，零外部强制依赖（纯标准库实现），注册全局命令 `medit-telemetry` 与 `traework-telemetry`。
* **一句话单独部署**：
  ```powershell
  # Windows PowerShell 单行极速部署
  powershell -ExecutionPolicy Bypass -File .\telemetry\deploy.ps1 -Silent
  ```
  ```bash
  # 跨平台 Python 单行极速部署
  python telemetry/deploy.py --silent
  ```
* **核心亮点**：
  1. **人效收益自动核算**：文献检索（7min/篇）、成功下载（2min/篇）、文献高亮（4min/篇）精准折算工时节约。
  2. **Token 与控制台 100% 绝对一致**：默认 `exact` 模式，仅记录真实 API 网关回执，杜绝估算与虚高。
  3. **PDF 物理真实总页数求和**：自动去重唯一文献并解析累加真实物理总页数。
  4. **全时段主动守护与飞书同步**：30秒工作区主动巡检，周报/月报自动推送飞书并同步公共表格。默认排程 **周报每周一 10:30 / 月报每月 1 日 10:30**。
  5. **开机无感自启与桌面伴随启动**：macOS 走 LaunchAgent、Windows 走 Startup，登录自动静默拉起；点击桌面 TraeWork 自动同启监控。
  6. **关键事件外部告警（飞书）**：守护进程资源吃紧、定时同步失败会主动推卡片（同类默认静默 60 分钟，限流账本落盘，进程重启不会重复刷屏）；同步成功与「脏工作区跳过拉取」保持安静，不训练人忽略告警。用 `medit-telemetry alert --test` 可随时验证通道是否打通。
  7. **定时同步与自愈**：每 6 小时自动拉取 + 重建 + 自测；网络抖动短重试 3 次，工作区有未提交改动则跳过拉取但仍从当前工作区重建。退出码如实区分：`0` 已更新 / `1` 构建失败 / `2` 已重建但代码未同步。
  8. **推送日的前一个工作日的「别关机」提醒**：推送是**到点触发**的 —— 机器关机或休眠，那一次周报/月报就静默丢失（不报错、不补发）。默认在推送日的**前一个工作日 18:00** 自动提醒一次。推送目标日遇**周末或法定节假日顺延到下一个工作日**（补班的周六算工作日）。提醒日与顺延判断都按**法定节假日**推算，数据来自国务院办公厅公告（`medit-telemetry holiday` 可查看来源与依据）。

完整部署与参数指南详见：[docs/TELEMETRY_DEPLOY.md](docs/TELEMETRY_DEPLOY.md) 与 [telemetry/README.md](telemetry/README.md)。

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
