<div align="center">

# via54Medit

> **🌐 语言 / Language**: 本文为双语版本 (This file is bilingual) · [🇨🇳 中文版](./README.zh-CN.md) · [🇺🇸 English](./README_EN.md)

[![CI](https://github.com/veawho/via54Medit/actions/workflows/ci.yml/badge.svg)](https://github.com/veawho/via54Medit/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/veawho/via54Medit?include_prereleases&color=blue)](https://github.com/veawho/via54Medit/releases)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE-AGPL-3.0)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE-MIT)

**面向循证医学 (EBM) 的多源文献检索、PICO 抽取、GRADE 评级与证据融合引擎**
**Multi-source medical literature retrieval, PICO extraction, GRADE grading & evidence fusion engine for Evidence-Based Medicine (EBM)**

</div>

---

## 📌 定位与核心价值 / Positioning & Core Value

`via54Medit` 是面向临床循证、系统综述与医药决策的多源学术文献检索与融合系统：

- **自然语言提问**：输入临床问题，自动分发调度 **3 个文献源（PubMed + OpenAlex + Semantic Scholar）**（蚂蚁阿福 antfu 已剥离，无需 Chrome CDP）；
- **去重与语义融合**：SimHash 汉明距离去重，结合被引量、时效性、FWCI 与多源重合度加权排序；
- **智能抽取与评级**：**DeepSeek 默认驱动**（`--llm deepseek`，deepseek-flash）的 PICO 要素抽取与 GRADE 证据质量评级；
- **引用与版式**：L0-L6 证据推理架构，引文真伪校验（cite/citation/anno2ppt），Office 版式渲染与 PPT 引用卡片导出；
- **团队协同与人效度量**：解耦 `telemetry` 模块，Token 账单对齐 + 实时用量采集（medit / DeepSeek-cli / mmx-cli 全通道）→ 飞书多维表格自动同步与周一校验。

`via54Medit` is a multi-source academic retrieval & fusion system for clinical evidence, systematic reviews, and pharma decisions:

- **Natural-language queries** dispatch to **3 sources (PubMed + OpenAlex + Semantic Scholar)** — the Antfu RAG source has been **removed** (no Chrome CDP required);
- **Deduplication & semantic fusion**: SimHash Hamming-distance dedup with weighted ranking (citations / recency / FWCI / multi-source overlap);
- **LLM-driven extraction & grading** default to **DeepSeek** (`--llm deepseek`, model `deepseek-flash`) for PICO extraction and GRADE rating;
- **Citation & layout pipeline**: L0–L6 evidence reasoning, citation authenticity checks (cite / citation / anno2ppt), Office-fidelity rendering and PPT citation cards;
- **Team collaboration & productivity telemetry**: a decoupled `telemetry` module with token billing alignment and real-time usage collection (medit / DeepSeek-cli / mmx-cli) synced to Feishu Bitable with Monday finalization.

> ℹ️ **2026-10 架构变更 / Architecture changes (2026-10)**:
> - 默认 LLM → **DeepSeek**（`--llm deepseek`，模型 deepseek-flash；PPT/文献/highlight/视觉统一走 DeepSeek）—— Default LLM is now **DeepSeek**.
> - **hermes 已剥离**：`--llm hermes` 不再可用，config 无 hermes 段 —— **hermes removed** (`--llm hermes` unavailable).
> - **antfu（蚂蚁阿福）已剥离**：源路由 4→3，`medit antfu` 命令注销 —— **antfu removed** (4→3 sources).
> - 新增 **飞书/豆包工作伙伴**（workmate）一步部署 + 跨平台（Windows / macOS / Linux）—— New **Doubao Work workmate** package: one-step deploy, cross-platform.

---

## 🚀 跨平台安装与部署 / Cross-platform Installation

支持 **Windows (amd64/arm64)**、**macOS (Apple Silicon / Intel)**、**Linux (amd64/arm64)**，纯 Go 静态编译（`CGO_ENABLED=0`），零系统动态库依赖。
Supports Windows, macOS (Apple Silicon / Intel), Linux — pure-Go static binaries (`CGO_ENABLED=0`), no system dynamic-library dependencies.

### 方式 A: 包管理器 / Package managers

```powershell
# Windows (Scoop)
scoop bucket add veawho https://github.com/veawho/scoop-bucket
scoop install medit
```

```bash
# macOS / Linux (Homebrew)
brew install veawho/tap/medit
```

### 方式 B: 预编译包 / Prebuilt binaries

前往 [GitHub Releases](https://github.com/veawho/via54Medit/releases) 下载对应平台二进制（`.zip` / `.tar.gz`），解压后加入 `PATH`。
Download platform binaries from GitHub Releases, extract and add to `PATH`.

### 方式 C: 源码编译 / Build from source

```bash
git clone https://github.com/veawho/via54Medit.git
cd via54Medit
make build        # 输出至 bin/medit 与 bin/medit-mcp
```

---

## 🤖 飞书/豆包工作伙伴（Workmate）— 一步部署 · 跨平台

via54Medit 的全部能力已封装为 **豆包工作伙伴「循证医学助手 Medit」**（个人自定义伙伴）：

- **一步完成**：豆包/飞书工作 →「插件·技能·伙伴 → 工作伙伴 → 从本地导入」安装包 → 召唤伙伴，在对话中回复 **DeepSeek API Key** 即完成全部部署；
- **跨平台**：`deploy_medit.py` / `deepseek.py` / `usage_collector.py` / `monday_finalize.py` / `create_sched.py` 均为 Python 跨平台；medit 引擎按平台分发（Windows `medit.exe` / macOS `medit-arm64`·`medit-amd64`）；定时任务 Windows schtasks / macOS·Linux crontab；
- **自动部署**：依赖（Python/FFmpeg/PaddleOCR/配置）、DeepSeek CLI、lark-cli 飞书账号绑定、多维表格绑定、实时用量采集（5 分钟）+ 周一校验（10:30）全部自动。

The full capability set is packaged as the Doubao Work **workmate "循证医学助手 Medit"**:

- **One step**: Doubao/Feishu Work →「Plugins·Skills·Workmates → Workmates → Import from local」→ summon the workmate and reply with your **DeepSeek API Key** in the chat — deployment finishes automatically;
- **Cross-platform**: all engine scripts are Python (Windows / macOS / Linux); the Go engine ships per-platform (Windows `medit.exe`, macOS `medit-arm64`/`medit-amd64`); schedulers use schtasks on Windows and crontab on macOS/Linux;
- **Auto-deploy**: dependencies, DeepSeek CLI, lark-cli account binding, Bitable binding, 5-min usage collection and Monday 10:30 finalization are all set up automatically.

详情见 [`workmate/README-workmate.md`](./workmate/README-workmate.md)，安装包见 **Release v5.4.51**（`via54medit-workmate-installer-v5.4.51.zip` + `via54medit-skill-v5.4.51.zip`）。
See [`workmate/README-workmate.md`](./workmate/README-workmate.md); installers live in **Release v5.4.51**.

---

## 🛠️ 新设备一键就绪与自愈 / Bootstrap & Doctor

```bash
# 1. 深度扫描 + 按平台自动补齐缺口 + 渲染自检 + 全量测试
python3 scripts/bootstrap_device.py

# 2. 仅深度扫描（只报不改）
python3 scripts/deploy_scan.py --check

# 3. 预演安装命令（不落地修改）
python3 scripts/bootstrap_device.py --dry-run

# 4. Go 侧部署自检
medit doctor
```

---

## 💻 CLI 常用子命令 / Common CLI Commands

```bash
# 循证检索与分析 / Evidence retrieval & analysis
medit ask "晚期肝细胞癌一线系统治疗进展"              # 3 源并发检索 + DeepSeek 证据摘要
medit pico "阿替利珠单抗联合贝伐珠单抗治疗晚期肝癌"     # PICO 四要素抽取（--llm deepseek）
medit grade evidence_package.json                    # GRADE 证据质量评级
medit systematic "你的临床问题/干预对比"              # PICO→检索→去重→归纳→GRADE→存档

# 直查文献源 / Direct source queries
medit pubmed search "Nivolumab HCC"
medit openalex search "Immunotherapy Hepatocellular"
medit s2 search "Atezolizumab Bevacizumab"

# DeepSeek CLI（跨平台）/ DeepSeek CLI (cross-platform)
python bin/deepseek.py chat "问题"                   # chat
python bin/deepseek.py vision 图片.png "描述图片"      # vision（图像理解）
python bin/deepseek.py models / balance

# 医学策略策划与合规 / Medical strategy & compliance
medit medplan run --instruction "上市医学策略" --name DrugX --indication "HCC"

# 系统自检与版本 / Health & version
medit doctor
medit version
```

> LLM provider：`--llm deepseek`（默认，推荐）| `openai` | `glm`（hermes 已剥离）。

---

## 🤖 AI Agent 与 MCP 接入 / MCP Integration

内置标准 Stdio MCP 服务器（`bin/medit-mcp`），提供核心医学检索与评级 Tool（3 源）：
Built-in Stdio MCP server (`bin/medit-mcp`) exposing core medical retrieval & grading tools (3 sources):

* `medit_ask` / `medit_pico` / `medit_grade` / `medit_anno2ppt`

```json
{
  "mcpServers": {
    "medit": { "command": "medit-mcp", "args": [] }
  }
}
```

---

## 📊 监控度量与飞书同步 / Telemetry & Feishu Sync (`medit-telemetry`)

解耦的效能收益与大模型 Token 账单追踪模块，支持守护进程、定时巡检与飞书多维表格直推：

- **跨平台 Python 一键部署**：`python telemetry/deploy.py --silent`
- **实时多源用量采集（v2.3）**：`usage_collector.py` 每 5 分钟增量采集 medit 引擎 + DeepSeek-cli + mmx-cli 的 token/耗时 → 飞书「实时使用明细」；周一 10:30 `monday_finalize` 校验并标记「最终修订 / 已校验-最终」
- 人效收益核算（检索/下载/高亮工时折算）、Token 账单对齐、告警（Alert）通道

A decoupled productivity & token-billing module with daemon, scheduled checks, and Feishu Bitable push:

- **Cross-platform one-step**: `python telemetry/deploy.py --silent`
- **Real-time multi-source usage collection (v2.3)**: `usage_collector.py` incrementally collects tokens/elapsed time from the medit engine + DeepSeek-cli + mmx-cli every 5 min into Feishu "实时使用明细"; Mondays 10:30 `monday_finalize` validates and marks "最终修订 / 已校验-最终"
- Productivity-hour accounting, token-billing alignment, and Feishu alert channel

完整指南详见 / Full guide: [docs/TELEMETRY_DEPLOY.md](docs/TELEMETRY_DEPLOY.md)。

---

## 🧪 自动化测试 / Automated Tests

```bash
make test        # Go 竞态测试 (go test -race)
make test-py     # Python 测试（遥测、仓库卫生、LLM 记账、部署扫描器）
```

---

## 🧹 完全卸载与环境清理 / Uninstallation & System Cleanup (v5.4.52)

若需要从当前系统中完全卸载已部署的 `via54Medit`（含终止常驻后台、注销计划任务、删除自启动、清理 `~/.via54medit` 与 `~/.medit` 数据、清理工作伙伴及本地仓库），可直接运行内置的一键卸载脚本。
详见 [README-uninstall.md](./README-uninstall.md)。

To completely uninstall deployed `via54Medit` components from your system (including daemons, scheduled tasks, autostart scripts, `~/.via54medit`, `~/.medit`, partner workspaces, and local repository), run the uninstaller directly. See [README-uninstall.md](./README-uninstall.md).

```powershell
# Windows PowerShell (全量卸载 + 清理本地仓库)
powershell -ExecutionPolicy Bypass -File uninstall.ps1 -CleanRepo
```

```bash
# 跨平台 Python 3 / Cross-platform Python 3
python uninstall.py --clean-repo
```

```bash
# macOS / Linux Shell
chmod +x uninstall.sh && ./uninstall.sh --clean-repo
```

---

## 📄 开源许可与规范 / License & Conduct

- **双许可 / Dual license**：核心源码 [AGPL-3.0](LICENSE-AGPL-3.0)；模板、配置与文档 [MIT](LICENSE-MIT)
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) · [CONTRIBUTING.md](CONTRIBUTING.md) · [SECURITY.md](SECURITY.md) · [CITATION.cff](CITATION.cff)
