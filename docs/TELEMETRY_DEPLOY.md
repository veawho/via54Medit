# via54Medit 监控统计与飞书同步工具 (`medit-telemetry`) 独立部署指南

`medit-telemetry` 是面向 `via54Medit` 与 `TraeWork`（文献检索、文献下载与文献 Highlight 智能管线）打造的高可用、完全解耦的**人效收益度量、大模型 Token 真实账单对齐与飞书全自动同步**独立系统。

本文档提供面向新设备、团队成员机器或无网络/内网环境的**“一句话单独部署”**与运维指引。

---

## 🚀 一句话极速部署 (One-Liner Deployment)

部署脚本全程全自动执行：
1. **Python 环境自检**（需 Python >= 3.8，跨平台适配）；
2. **零外部硬依赖注册**（开发模式挂载或写入 `.pth`，无需额外三方网络包下载）；
3. **用户花名与飞书凭据绑定**（支持从本机 TraeWork 自动嗅探或交互/参数指定）；
4. **开机无感自启注册**（macOS 用 LaunchAgent、Windows 用 Startup VBS，登录自动存活）；
5. **桌面 TraeWork 伴随启动器生成**（点击 Trae 时自动连带启动监控）；
6. **后台守护进程即刻拉起**（30秒周期主动巡检文献产物，准时推送周报/月报）。

---

### 1. Windows PowerShell 黄金单行 (最常用)

打开 PowerShell 窗口，直接执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\telemetry\deploy.ps1 -Silent
```

#### 自定义花名与定时排程单行示例:
```powershell
# 默认即为 每周一 10:30 / 每月 1 日 10:30; 下面演示改成自定义时间
powershell -ExecutionPolicy Bypass -File .\telemetry\deploy.ps1 -Nickname "张三" -Weekly "Friday 18:00" -Monthly "last 18:00" -Silent
```

> **默认排程**: 周报推送与同步 **每周一 10:30**、月报 **每月 1 日 10:30**；目标日遇**周末或法定节假日顺延到下一个工作日**（补班的周六算工作日）；并在推送日的**前一个工作日 18:00** 自动提醒「别关机」（推送是到点触发的，关机或休眠那一次会静默漏推）。顺延与提醒日都按**法定节假日**推算 —— 避开春节/国庆连休，并把调休补班的周六算作工作日，数据取自国务院办公厅公告。查看: `python -m telemetry.cli holiday`；关闭提醒: `-NoReminder`；关闭顺延: `-NoDefer`。

#### 跨机器/内网远程管道单行 (下载即跑):
```powershell
powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/veawho/via54Medit/main/telemetry/deploy.ps1 | iex"
```

---

### 2. 跨平台 Python 单行 (Windows / macOS / Linux)

在任何已安装 Python 3.8+ 的系统上执行：

```bash
# 全自动静默部署 (复用本机已有凭据或默认值)
python telemetry/deploy.py --silent

# 携带花名与飞书 OpenID 部署
python telemetry/deploy.py --silent --nickname "李四" --openid "ou_4366ab3e3c42c5e5d2a1fce4db0c4af7"

# 交互式向导部署 (逐步输入花名、飞书凭据与汇报时间)
python telemetry/deploy.py
```

亦可通过已安装的统一入口直接触发：
```bash
python scripts/via54.py telemetry deploy --silent
```

---

### 3. Windows CMD / 双击运行

适合不便打开终端的用户：
* 直接在文件资源管理器中双击 `telemetry\deploy.bat`；
* 或在 CMD 中执行：
```cmd
telemetry\deploy.bat --silent
```

---

## 🛠️ 参数全景表

| 参数名 (PowerShell) | 参数名 (Python CLI) | 说明 | 示例 |
| :--- | :--- | :--- | :--- |
| `-Nickname` | `--nickname`, `-n` | 用户的企业花名或姓名缩写（必填项，影响卡片署名与公共表格） | `"wtg"`, `"星云"` |
| `-OpenId` | `--openid` | 用户个人的飞书 OpenID，周报月报卡片将直接推送至此人会话 | `"ou_4366ab3e..."` |
| `-AppId` | `--app-id` | 企业自建飞书应用 App ID (若不传则自动继承 TraeWork) | `"cli_a1b2c3d4..."` |
| `-AppSecret` | `--app-secret` | 企业自建飞书应用 App Secret | `"your_app_secret"` |
| `-Bitable` | `--bitable` | 团队飞书多维表格 (Bitable Base) App Token 或完整 URL | `"bascny4kK..."` 或 `"https://feishu.cn/base/..."` |
| `-Weekly` | `--weekly` | 每周定时报告与表格同步时间（**默认 每周一 10:30**） | `"Monday 10:30"`, `"周一 10:30"` |
| `-Monthly` | `--monthly` | 每月定时报告与历史战报时间（**默认 每月 1 日 10:30**） | `"1 10:30"`, `"last 18:00"` |
| `-Reminder` | `--reminder` | 「别关机」提醒时刻（推送日的**前一个工作日**，按法定节假日推算；默认 18:00 开启） | `"18:00"` |
| `-NoReminder` | `--no-reminder` | 关闭「别关机」提醒 | 标志位 |
| `-Defer` | `--defer` | 目标日遇周末/法定节假日时顺延到下一个工作日（**默认已开启**） | 标志位 |
| `-NoDefer` | `--no-defer` | 关闭顺延，按固定日期发送 | 标志位 |
| `-Silent` | `--silent`, `-s` | 无交互静默模式，直接应用参数或嗅探凭据 | 标志位 |
| `-NoStartup` | `--no-startup` | 不注册开机自启（macOS LaunchAgent / Windows Startup VBS） | 标志位 |
| `-NoLauncher` | `--no-launcher` | 不在桌面生成 TraeWork 伴随启动器快捷方式 | 标志位 |
| `-Uninstall` | `--uninstall` | 停止后台服务并清理开机自启脚本 | 标志位 |

---

## 📊 团队多人多维表格 (Bitable) 与图表报告

本工具专为**多人团队**设计，支持全员数据集中归集与可视化：

### 1. 建立团队多维表格 (二选一)
- **方式 A (飞书授权后全自动云端新建)**：
  1. 点击应用管理员授权链接开通权限（将 `<APP_ID>` 替换为您企业的飞书应用 ID，或直接运行命令自动获取直达链接）：
     `https://open.feishu.cn/app/<APP_ID>/auth?q=bitable:app,base:app:create&op_from=openapi&token_type=tenant`
  2. 授权后运行：`medit-telemetry bitable --create`，自动在飞书新建并初始化 15 个标准化统计字段。
- **方式 B (快速手动新建并绑定)**：
  1. 在飞书网页端或客户端右键点击任意空间新建一个多维表格（耗时 5 秒）；
  2. 将飞书自建应用添加为协同编辑成员；
  3. 执行绑定：
     ```bash
     medit-telemetry bitable --bind https://feishu.cn/base/bascn...
     ```
     工具将自动识别数据表结构并注入全套字段！

### 2. 多人数据自动汇聚与可视化
- **防重复幂等写入 (Upsert)**：每周排程推送时，自动以“汇报周期 + 成员花名”为主键更新对应行的记录，多次运行不重不漏。
- **团队周报富媒体卡片**：每周五自动计算团队总人效并推送 Top 5 勋章排行榜至飞书群/个人。
- **本地交互式图表看板**：
  ```bash
  medit-telemetry bitable --report
  ```
  自动聚合生成独立的 HTML 可视化大屏，包含全员节省工时对比柱状图与明细列表，自动在默认浏览器中开启预览。

---

## 📋 常用运维与管理命令

部署成功后，系统全局可直接使用 `medit-telemetry` 或 `traework-telemetry`：

```bash
# 1. 查询当前累计人效收益与 Token 真实消耗
medit-telemetry status

# 2. 查看或修改当前设备配置
medit-telemetry config
medit-telemetry config --nickname "王小明"
medit-telemetry config --set-weekly "Friday 18:00"
medit-telemetry config --set-monthly "last 18:00"

# 3. 手动生成与导出报告
medit-telemetry report --period week
medit-telemetry report --period month --json

# 4. 手动推送飞书卡片与同步多维表格
medit-telemetry push --period week
medit-telemetry sync --period week

# 5. 团队多维表格管理与图表报告
medit-telemetry bitable --create           # 云端新建表格
medit-telemetry bitable --bind <TOKEN/URL> # 绑定已有多维表格
medit-telemetry bitable --sync             # 手动同步周报至表格
medit-telemetry bitable --report           # 自动汇总全员数据生成图表看板

# 6. 服务商控制台 Token 真实账单核验
medit-telemetry token --status
medit-telemetry token --mode exact

# 7. LLM 接入与 Token 用量读取能力校验 (部署/更新后**强制**跑)
medit-telemetry llm              # 审计: 接入了哪些 LLM、token 真能读进库吗(有事退出码 2)
medit-telemetry llm -v           # 展开到通道级: 每条通道在记 / 不返回 token / 没接记录
medit-telemetry llm --live       # 额外联网探凭据可达性, 并读 mmx 账户级配额
medit-telemetry llm --json       # 机器可读(供部署脚本消费)

# 8. 后台主动监控守护进程状态与启停
medit-telemetry daemon --status    # 查询存活 PID 与最近心跳
medit-telemetry daemon --stop      # 停止后台服务
medit-telemetry daemon --start     # 重新拉起后台服务
```

### 部署 / 更新后为什么必须跑 `llm`

记账是**旁路**: 一条调用路径不再记录 token, 调用本身不会报错、不会有异常、不会有非零
退出码, 报表只是安静地少一块数字。所以"部署成功"不能只等于"守护进程起来了"。

```bash
# 部署或更新后 (任选其一, 都会强制校验并以非 0 退出告警)
python3 scripts/bootstrap_device.py            # 第 4 步就是该校验
python3 scripts/deploy_scan.py --verify-llm    # 独立跑一次
medit-telemetry deploy                         # 部署概览里会跑同一份校验
```

`auto_sync.py`(定时从 GitHub 拉取)在拉取+重建**之后**也会跑一遍, 失败会发告警。

它验证三类**可确证**的事实(全部离线, 不联网、不花钱):

| 校验 | 内容 | 为什么非它不可 |
| --- | --- | --- |
| 源码级证据 | 扫仓库里真实的记账调用点(Python `record_llm_usage(` / Go `recordLLMUsage(`), 并判断该调用点**可达** | 注册表说自己被记录不算数; 实测抓到过"包装函数定义了却没人调用"的假性记录 |
| 端到端摄入 | 各 provider 的**真实响应形状** → 落库 → 读回 → 报表层(写临时库, 不碰生产数据) | 有 `usage` 字段不等于落得了库、更不等于统计口径算得进去 |
| Go 侧 spool 链路 | 落盘 → 摄入 → 读回, 含别名归一(`glm`→`zhipu`)与重放幂等 | Go 没有 SQLite 驱动, 用量先落盘再由本模块摄入; 这条链路断了不会报错 |

读不到的部分会**如实报出**, 不折算、不造数: mmx-cli 只返回 content 不暴露 token(其账户级
配额是**调用次数**而非 token); openai 用量接口需 Admin key; deepseek 逐条用量需控制台导出。

---

## 🔒 核心机制保证

### 1. 为什么无需依赖外部三方库即可运行？
- 数据库驱动：采用 Python 内置 `sqlite3`；
- 网络通信：采用 Python 内置 `urllib.request` 结合 SSL 上下文直连飞书 OpenAPI；
- 定时守护：内部轻量级轮询时钟与心跳引擎，无需安装 Celery、APScheduler 等沉重组件；
- PDF 真实物理页数解析：内置 `pypdf` $\to$ `fitz` (PyMuPDF) $\to$ **原生二进制 `/Count` 正则解析引擎** 三重降级防护，在离线未安装任何 PDF 库的新设备上依然能 100% 正确统计文档页数。

### 2. 开机自启与伴随启动如何工作？
- **开机自启（macOS）**：写入 `~/Library/LaunchAgents/com.via54medit.telemetry.plist` 并 `launchctl bootstrap`，`RunAtLoad` + `KeepAlive` 使守护服务登录后常驻、异常退出自动拉起；注册前会先停掉手工启动的游离实例，避免双跑。
- **开机自启（Windows）**：在 `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup` 下写入 `traework_telemetry_silent.vbs`，通过 `WScript.Shell.Run ..., 0, False` 在系统登录时无黑框静默启动。
- **伴随启动（仅 Windows）**：在桌面生成 `启动 TraeWork (带自动监控).vbs`，用户点击时自动检查守护进程是否存活（已存活则跳过，未启动则唤醒），随后直接拉起 TraeWork 主界面。
- **Linux**：无内置开机自启实现，`deploy.py` 步骤 4 会跳过并提示；可自行用 systemd user unit 承载 `python -m telemetry.cli daemon --foreground`。

### 3. 大模型 Token 账单与控制台 100% 对齐
- 默认采用 `exact` 模式，所有指标严格读取真实 API 网关回执的 `prompt_tokens` 与 `completion_tokens`；
- 若某次操作复用本地缓存或未真实产生大模型外呼，则绝对计入 0 tokens，坚决避免人为虚构与财务对账偏差。
