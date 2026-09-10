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
powershell -ExecutionPolicy Bypass -File .\telemetry\deploy.ps1 -Nickname "张三" -Weekly "Friday 18:00" -Monthly "last 18:00" -Silent
```

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
| `-Weekly` | `--weekly` | 每周定时报告与表格同步时间 | `"Friday 18:00"`, `"周一 09:00"` |
| `-Monthly` | `--monthly` | 每月定时报告与历史战报时间 | `"1 09:00"`, `"last 18:00"` |
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

# 7. 后台主动监控守护进程状态与启停
medit-telemetry daemon --status    # 查询存活 PID 与最近心跳
medit-telemetry daemon --stop      # 停止后台服务
medit-telemetry daemon --start     # 重新拉起后台服务
```

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
