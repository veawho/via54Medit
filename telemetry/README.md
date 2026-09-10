# medit-telemetry (TraeWork 文献整理 AI 监控统计与飞书同步工具)

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Token Exact](https://img.shields.io/badge/Token%20Mode-100%25%20Exact-brightgreen.svg)](#token-控制台-100-对齐)
[![Zero-Dependency](https://img.shields.io/badge/Dependencies-Zero%20Mandatory-success.svg)](#技术架构与零依赖设计)

`medit-telemetry` 是面向 `via54Medit` 与 `TraeWork`（文献检索、文献下载与文献 Highlight 智能管线）打造的高可用、完全解耦的**人效收益度量、大模型 Token 真实账单对齐与飞书全自动同步**独立系统。

---

## 核心特性

1. **一句话跨设备部署 (One-Liner Deployment)**：
   - 适配 Windows / Linux / macOS。
   - 一行 PowerShell、Python 或双击批处理即可自动完成环境自检、包注册、花名与飞书授权、开机静默守护及桌面伴随启动器生成。
2. **零外部强制依赖 (Zero Mandatory Dependencies)**：
   - 核心引擎完全基于 Python 3.8+ 标准库（`sqlite3`, `urllib`, `json`, `subprocess`, `argparse`），内网与离线环境秒级即启。
   - PDF 物理页数计算内置三重引擎（`pypdf` -> `fitz` -> 原生二进制 `/Count` 正则解析），无第三方库也能精准统计。
3. **大模型 Token 与服务商控制台 100% 绝对一致 (`exact` 模式)**：
   - 彻底告别虚构或估算倍率。仅当大模型真实网关响应（DeepSeek, Zhipu, OpenAI 等）返回实际 `usage` 时精准计入 `llm_token_logs`。
   - 本地缓存未消耗 API 时计入 0 tokens，杜绝虚高。
4. **文献去重与真实物理页数求和**：
   - 针对多次运行生成的 Highlight 产物实施唯一 PDF 去重。
   - 真实提取并累加每个文献的物理总页数（而非单页抽取数）。
5. **主动文件感知与多周期调度守护**：
   - 30 秒周期性自动巡检工作区与桌面目录，自动识别新增文献并实时入库 SQLite。
   - 支持自定义每周汇报时间（如“周五 18:00”）与每月汇报时间（如“月末 18:00”）。
   - 到期自动推送飞书战报卡片并向公司多维表格同步。

---

## ⚡ 一句话快速部署 (One-Liner Quickstart)

### 选项 A: Windows PowerShell 黄金单行 (推荐)
打开 PowerShell 窗口，直接执行：
```powershell
powershell -ExecutionPolicy Bypass -File .\telemetry\deploy.ps1 -Silent
```
> 若需指定花名与汇报时间，可追加参数：
> `powershell -ExecutionPolicy Bypass -File .\telemetry\deploy.ps1 -Nickname "wtg" -Weekly "Friday 18:00" -Silent`

### 选项 B: 跨平台 Python 命令行
在任何已安装 Python 3.8+ 的系统上执行：
```bash
python telemetry/deploy.py --silent
```

### 选项 C: Windows CMD / 双击运行
直接在资源管理器中双击 `telemetry/deploy.bat`，或在命令行中运行：
```cmd
telemetry\deploy.bat
```

---

## 常用 CLI 命令

安装完成后，系统全局可用 `medit-telemetry` 或 `traework-telemetry`：

```bash
# 1. 查看当前效率总览与 Token 真实消耗
medit-telemetry status

# 2. 生成战报 (周报/月报/历史总览)
medit-telemetry report --period week
medit-telemetry report --period month --json

# 3. 手动向飞书会话推送报告卡片
medit-telemetry push --period week

# 4. 同步数据至飞书多维/电子表格
medit-telemetry sync --period week

# 5. 查询与管理大模型 Token 账单
medit-telemetry token --status
medit-telemetry token --mode exact

# 6. 守护服务管理
medit-telemetry daemon --status     # 查询后台守护存活状态与 PID
medit-telemetry daemon --stop       # 停止后台服务
medit-telemetry daemon --start      # 重新拉起后台服务

# 7. 团队飞书多维表格 (Bitable) 与图表报告
medit-telemetry bitable --create           # 在飞书云端直接新建团队监控多维表格
medit-telemetry bitable --bind <TOKEN/URL> # 绑定团队已有多维表格
medit-telemetry bitable --sync             # 手动将本周战报同步到团队多维表格
medit-telemetry bitable --report           # 自动汇总全员数据生成可视化图表大屏

# 8. 修改花名与定时汇报时间
medit-telemetry config --nickname "星云"
medit-telemetry config --set-weekly "Friday 18:00"
medit-telemetry config --set-monthly "last 18:00"
```

---

## 📊 团队多维表格与人效排行榜

团队多人模式下，每位成员的周报自动通过 Upsert 算法汇入公共多维表格（以“汇报周期 + 成员花名”为主键避免重复）。同时内置两种全景呈现：
1. **飞书互动富媒体卡片**：每周推送团队排行榜（🥇 🥈 🥉 勋章、全员节约工时汇总、人均阅读量），点击按钮直达多维表格；
2. **离线与本地交互式图表大屏 (`HTML Dashboard`)**：自动渲染生成 KPI 统计卡片与全员横向工时节省柱状对比图，双击即可直接在浏览器交互。

---

## 人工效率计算模型

| 指标维度 | 人工基线耗时 | AI 自动化耗时 | 节约时间计算 |
| :--- | :--- | :--- | :--- |
| **文献检索** | 7 分钟 / 篇 | 自动记录真实检索用时 | $\text{count} \times 7\text{min} - \text{实际耗时}$ |
| **文献下载** | 2 分钟 / 篇 | 自动记录真实下载用时 | $\text{count} \times 2\text{min} - \text{实际耗时}$ |
| **文献高亮** | 4 分钟 / 篇 | 自动记录真实高亮用时 | $\text{count} \times 4\text{min} - \text{实际耗时}$ |

### 统计口径（唯一文献去重）

| 指标 | 计数口径 | 数据来源 |
| :--- | :--- | :--- |
| **文献检索** | 去重后的**唯一被引文献**数（重复引用同一篇只计 1 篇） | `高亮结果/*_meta.json` 的 `reference_field` / `doi`；缺失时回退 `高亮结果清单.tsv` |
| **文献下载** | 去重后的**唯一 PDF 文献文件**数 | 项目内 `*.pdf` |
| **文献高亮** | 去重后的**唯一高亮产物 PDF** 数 | `*_highlight.pdf`（TMA）或 `高亮结果/*.pdf`（RSV 等中文项目）；页数取真实物理页数之和 |

> **检索数说明**：早期版本仅从 `*doi_map*.json` / `*inventory*.json` 读取检索记录，因此在没有这类清单的项目（如 RSV）中恒为 0。现改为按「高亮引用清单」折算 —— 每条 Pn-x 记录对应其被引文献，按文献去重后计为检索数。**清单缺 DOI 时以引用串归一化（忽略大小写与空白）去重**，故同一文献的不同著录写法（标点差异、附录后缀等）可能被计为多条，属已知口径边界。

---

## 目录结构

```
telemetry/
├── __init__.py           # 模块导出定义
├── __main__.py           # python -m telemetry 入口
├── setup.py              # setuptools 打包规范
├── pyproject.toml        # PEP 517/621 标准构建配置
├── deploy.py             # 跨平台一键部署核心引擎
├── deploy.ps1            # Windows PowerShell 单行脚本
├── deploy.bat            # Windows CMD 批处理脚本
├── nlp_deploy.py         # 自然语言解析部署引擎
├── cli.py                # 全功能命令行工具
├── config.py             # 跨设备配置与交互向导
├── daemon.py             # 主动监控与时钟排程守护进程
├── db.py                 # SQLite 存储与去重算法
├── aggregator.py         # 战报聚合与工时节省计算
├── token_tracker.py      # LLM 网关拦截与 100% 控制台对齐
├── pdf_utils.py          # 三重容灾真实 PDF 物理页数计算
├── watcher.py            # 工作区产出物主动感知器
├── feishu_sync.py        # 飞书卡片构建与消息推送
├── bitable_sync.py       # 飞书多维表格 (Bitable Base) OpenAPI 与 Upsert
├── chart_reporter.py     # 团队多人数据汇总与可视化图表报告
└── README.md             # 本说明文档
```
