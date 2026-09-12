<div align="center">

# via54Medit

> **🌐 Language**: [🇨🇳 完整中文文档](./README.zh-CN.md) | [🇺🇸 English](./README_EN.md)

[![CI](https://github.com/veawho/via54Medit/actions/workflows/ci.yml/badge.svg)](https://github.com/veawho/via54Medit/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/veawho/via54Medit?include_prereleases&color=blue)](https://github.com/veawho/via54Medit/releases)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg)](LICENSE-AGPL-3.0)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE-MIT)

**面向循证医学 (EBM) 的多源文献检索、语义路由、PICO 抽取与证据融合引擎**

</div>

---

## 📌 定位与核心价值

`via54Medit` 是面向临床循证、系统综述与医药决策的多源学术文献检索与融合系统：
- **自然语言提问**：输入临床问题，自动分发调度 4 个文献源（蚂蚁阿福 RAG + PubMed + OpenAlex + Semantic Scholar）；
- **去重与语义融合**：SimHash 汉明距离去重，结合被引量、时效性、FWCI 与多源重合度加权排序；
- **智能抽取与评级**：大模型驱动的 PICO（人群、干预、对照、结局）要素抽取与 GRADE 证据质量评级；
- **双源互补与版式保真**：L0-L6 6层证据推理架构，支持期刊正文与临床试验注册库（ClinicalTrials.gov）双源互补，原生支持微软 Office 引擎版式出图与 PPT 引用卡片导出 (`anno2ppt`)；
- **团队协同与人效度量**：解耦的 `medit-telemetry` 独立模块，实现 API Token 真实账单对齐与飞书多维表格大屏全自动同步。

---

## 🚀 跨平台安装与部署

支持 **Windows (amd64/arm64)**、**macOS (Apple Silicon / Intel)**、**Linux (amd64/arm64)**，采用纯 Go 静态编译（`CGO_ENABLED=0`），零系统动态库依赖。

### 方式 A: 包管理器安装 (推荐)

#### Windows (Scoop)
```powershell
scoop bucket add veawho https://github.com/veawho/scoop-bucket
scoop install medit
```

#### macOS / Linux (Homebrew)
```bash
brew install veawho/tap/medit
```

### 方式 B: 直接下载预编译包
前往 [GitHub Releases](https://github.com/veawho/via54Medit/releases) 下载对应平台的二进制压缩包（`.zip` / `.tar.gz` / `.deb` / `.rpm` / `.apk`），解压后将可执行文件加入系统 `PATH`。

### 方式 C: 源码编译
```bash
git clone https://github.com/veawho/via54Medit.git
cd via54Medit

# 使用 Makefile 构建带有完整版本信息的静态二进制 (输出至 bin/medit 与 bin/medit-mcp)
make build
```

---

## 🛠️ 新设备一键就绪与自愈 (Bootstrap & Doctor)

针对开发机、计算节点或团队新设备，提供 8 阶段幂等自愈脚本：

```bash
# 1. 深度扫描本机环境 + 按平台自动补齐缺口 + 渲染通道真出图自检 + 全量测试
python3 scripts/bootstrap_device.py

# 2. 仅深度扫描本机环境（只报不改）
python3 scripts/deploy_scan.py --check

# 3. 预演将要执行的安装命令（不落地修改）
python3 scripts/bootstrap_device.py --dry-run

# 4. 运行 Go 侧部署自检
medit doctor
```

---

## 💻 CLI 常用子命令

```bash
# 循证检索与分析
medit ask "中国肝癌5年生存率现状及靶向联合免疫治疗进展"   # 一句话 4 源并发检索 + LLM 证据摘要
medit pico "阿替利珠单抗联合贝伐珠单抗治疗晚期肝细胞癌"    # PICO 临床四要素抽取
medit grade evidence_package.json                        # GRADE 证据质量评级
medit anno2ppt evidence_package.json                     # 生成 PPT 结构化引用卡片

# 直查特定文献源
medit pubmed search "Nivolumab HCC"                      # PubMed 直查
medit openalex search "Immunotherapy Hepatocellular"     # OpenAlex 直查
medit s2 search "Atezolizumab Bevacizumab"               # Semantic Scholar 直查
medit antfu search "肝癌一线系统治疗"                     # 蚂蚁阿福临床 RAG

# 医学策略策划与合规
medit medplan run --instruction "上市医学策略" --name DrugX --indication "HCC"

# 系统自检与版本
medit doctor                                             # 部署与依赖项健康巡检
medit version                                            # 打印编译构建版本
```

---

## 🤖 AI Agent 与 MCP (Model Context Protocol) 接入

项目内置标准 Stdio MCP 服务器（`bin/medit-mcp`），提供 4 项核心医学检索与评级 Tool：
* `medit_ask`：自然语言 4 源循证检索与摘要
* `medit_pico`：临床问题 PICO 结构化抽取
* `medit_grade`：证据包 GRADE 等级评定
* `medit_anno2ppt`：证据包导出为 PPT 幻灯片

### Claude Desktop / Cursor / Trae 配置示例：

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

---

## 📊 监控度量与飞书同步 (`medit-telemetry`)

独立解耦的效能收益与大模型 Token 账单追踪模块，支持 30 秒主动巡检、全时段守护与飞书多维表格（Bitable）直推：

* **Windows PowerShell 一键部署**：
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\telemetry\deploy.ps1 -Silent
  ```
* **跨平台 Python 一键部署**：
  ```bash
  python telemetry/deploy.py --silent
  ```
* **核心功能**：
  * **人效收益核算**：检索（7min/篇）、下载（2min/篇）、高亮（4min/篇）精准折算工时节约；
  * **Token 100% 绝对一致**：`exact` 模式精准对齐大模型服务商网关回执账单；
  * **开机静默常驻**：macOS 走 LaunchAgent，Windows 走 Startup，遇法定节假日自动顺延；
  * **外部主动告警 (Alert)**：`medit-telemetry alert --test` 可测试飞书卡片告警通道，守护进程资源吃紧或同步失败时触发告警；
  * **定时自动同步与重建 (Exit codes)**：`scripts/auto_sync.py` 定时拉取并重建自测，通过退出码（exit codes: `0` 已更新 / `1` 构建失败 / `2` 已重建但代码未同步）精确反映状态。

完整指南详见 [docs/TELEMETRY_DEPLOY.md](docs/TELEMETRY_DEPLOY.md)。

---

## 🧪 自动化测试

```bash
make test        # 运行全部 Go 竞态测试 (go test -race)
make test-py     # 运行全部 Python 测试 (遥测模块、仓库卫生、LLM 记账、禁止区规则、部署扫描器)
```

---

## 📄 开源许可与规范

- **双许可协议**：
  - 核心源码：[AGPL-3.0 License](LICENSE-AGPL-3.0)
  - 模板、配置与文档：[MIT License](LICENSE-MIT)
- **代码行为规范**：[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- **贡献指引**：[CONTRIBUTING.md](CONTRIBUTING.md)
- **安全漏洞报告**：[SECURITY.md](SECURITY.md)
- **学术引用规范**：[CITATION.cff](CITATION.cff)
