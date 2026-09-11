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
   - **默认排程：周报 每周一 10:30 / 月报 每月 1 日 10:30**，均可自定义；目标日遇**周末或法定节假日顺延到下一个工作日**（补班的周六算工作日）。
   - **推送日的前一个工作日自动提醒"别关机"**：推送是到点触发的，机器关机或休眠那一次就静默漏推。
     提醒日期按**法定节假日**推算（会避开春节/国庆连休，并把调休补班的周六算作工作日），
     数据取自国务院办公厅公告（见下文「法定节假日与别关机提醒」）。
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

> **关于「解释器由外部管理」(PEP 668)**：uv 托管的解释器、发行版自带 Python、Homebrew Python 都会拒绝常规 `pip install -e`（`uv pip install` 同样拒绝）。部署脚本**默认不绕过**这道保护 —— 那是解释器管理方划下的边界，不该由部署脚本擅自突破。此时改为注入 `.pth` 保证模块可导入，而 `medit-telemetry` 命令由启动器直接落到 PATH，**功能照常可用**；差别只是没有向该解释器登记包元数据（pip 无法追踪它的升级 / 卸载）。
>
> 若确实要写入该解释器，显式开启开关重跑：
> ```bash
> python telemetry/deploy.py --allow-break-system-packages
> ```
> 该开关等价于 pip / uv 的 `--break-system-packages`，可以用别名 `--break-system-packages` 书写；Windows 单行脚本对应参数为 `-AllowBreakSystemPackages`。

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
medit-telemetry bitable --sync --dry-run   # 仅打印 schema 判定与将写入的字段, 不落库不写备份
medit-telemetry bitable --report           # 自动汇总全员数据生成可视化图表大屏

# 8. 修改花名与定时汇报时间
medit-telemetry config                       # 总览: 排程 + 提醒 + 下次推送/提醒日
medit-telemetry config --set-weekly "Monday 10:30"
medit-telemetry config --set-monthly "1 10:30"
medit-telemetry config --set-reminder "18:00"   # 开启/修改「别关机」提醒时刻
medit-telemetry config --no-reminder            # 关闭「别关机」提醒
medit-telemetry config --no-defer               # 关闭顺延(按固定日期发送); --defer 重新开启

# 8.1 法定节假日日历 (提醒日的推算依据)
medit-telemetry holiday                          # 数据来源/依据公告/排程与提醒日
medit-telemetry holiday --check 2026-10-01       # 判断某天是否工作日 + 前一个工作日
medit-telemetry holiday --refresh                # 清缓存重新取数

# 8.2 立即刷新统计 (不等下一个 30 秒巡检周期)
medit-telemetry refresh                  # 扫描全部监控目录 + 刷新已收录条目 + 清理备份副本行
medit-telemetry refresh --dir ~/Desktop/RSV   # 只刷新指定目录 (可重复)
medit-telemetry status                   # 末尾显示"最近入库时间 + 距今多久"

# 9. 运行环境自检 (排查 PYTHONHOME / PYTHONPATH 冲突)
medit-telemetry --env-check
# 10. 关键事件外部告警 (飞书)
medit-telemetry alert                      # 查看通道状态与最近发送记录
medit-telemetry alert --test               # 发一条测试告警, 验证通道是否打通
medit-telemetry alert --disable            # 关闭告警 (--enable 重新开启)
medit-telemetry alert --min-interval 30    # 调整同类告警静默期 (分钟, 默认 60)
```

> **关于告警**: 守护进程的「资源耗尽但不崩溃」型故障 (如文件描述符耗尽) 不会让进程退出,
> 因此 `KeepAlive` 之类的手段无从感知 —— 5.4.5 那次就静默了十余小时。现在这类信号会通过
> 飞书 Bot 主动推给你。同一类告警默认静默 60 分钟 (发送失败则 10 分钟后重试), 限流状态
> 落盘在 `~/.medit/alerts_state.json`, 因此守护进程被反复拉起也不会重复刷屏。
>
> 目前接入两类来源:
> 1. **守护进程资源吃紧** (文件描述符占用达软上限 80%) —— 由守护进程自身触发;
> 2. **定时同步失败** —— `scripts/auto_sync.py` 的构建失败 (`critical`) 与代码未同步 (`warning`)。
>
> 同步成功时保持安静; 工作区有未提交改动导致「跳过拉取」属预期情况, 不告警。

**定时同步的退出码**: `0` = 部署已更新 (含「脏工作区跳过同步」这种预期情况); `1` = 构建失败, 部署确实未更新; `2` = 二进制已重建但代码未同步 (暂时性网络 / 代理故障)。日志每行带时间戳, 落在 `~/.medit/autosync.log`。

**守护进程的资源观测**: `medit-telemetry daemon --status` 会显示实时文件描述符占用 (如 `文件描述符: 4/4096`), 该值同时写入心跳文件的 `fd` 字段, 便于外部巡检直接读取。

---

## 🩺 运行环境自检

部分 IDE、沙箱与构建工具会在终端里预置指向**它们自带 Python** 的 `PYTHONHOME` / `PYTHONPATH`。若该 Python 与本工具所用解释器不一致，可能出现两类故障：

| 现象 | 原因 |
| :--- | :--- |
| 报错 `Fatal Python error: init_fs_encoding ... No module named 'encodings'` | `PYTHONHOME` 指向了另一个解释器，解释器在**启动阶段**就崩溃 |
| 导入 PDF 相关扩展报 ABI 不兼容 / 找不到模块 | `PYTHONPATH` 注入了别的 Python 版本的 `site-packages` |

本工具用两层机制处理，且**不改变正常环境下的行为**：

1. **外壳启动器**（`medit-telemetry` 命令本身）：启动前先比对 `PYTHONHOME` 与本解释器前缀、以及 `PYTHONPATH` 里的版本目录。发现冲突时改用 `-E` 执行（忽略全部 `PYTHON*` 变量）并打印一行说明，把一个唬人的崩溃变成可用的命令。这一步必须在解释器启动前完成，因为上面第一种故障发生时任何 Python 代码都来不及执行。
2. **运行时自检**（`telemetry/envcheck.py`）：在 `cli.main()` 入口复查一次，覆盖「解释器还能起来」的情形（如仅 `PYTHONPATH` 被污染），给出冲突明细与修复命令。两条路径都会提示，因此用 `MEDITELEMETRY_ENV_ISOLATED` 标记交接，避免重复刷屏。

排查与修复：

```bash
medit-telemetry --env-check                    # 打印解释器、变量值与冲突结论
env -u PYTHONHOME -u PYTHONPATH medit-telemetry status   # 临时规避 (立即生效)
unset PYTHONHOME PYTHONPATH                    # 或在当前终端先清掉
```

根治方式是在 shell 启动脚本（`~/.zshrc` / `~/.bashrc`）中删除对这两个变量的 `export`。本工具只依赖标准库，移除后不影响任何功能。后台守护进程由 LaunchAgent / 计划任务拉起，不继承终端环境，因此始终不受影响。

> 部署时 `telemetry/deploy.py` 会把外壳启动器安装为 `medit-telemetry` / `traework-telemetry`，原命令备份为同目录下的 `*.orig`；重复部署幂等。启动器模板通过 `package-data` 随包分发，因此源码安装与 wheel / sdist 安装都能装出启动器。若 pip 未能创建命令（例如解释器由外部管理），启动器会直接在 PATH 上的用户级 bin 目录（POSIX 为 `~/.local/bin`）新建它，并在该目录不在 PATH 中时明确提示。若之后又执行了 `pip install -e`，命令会被还原成 pip 版本，重新跑一次部署即可再次接管。

---

## 📊 团队多维表格与人效排行榜

团队多人模式下，每位成员的周报自动通过 Upsert 算法汇入公共多维表格（以“汇报周期 + 成员花名”为主键避免重复）。同时内置两种全景呈现：
1. **飞书互动富媒体卡片**：每周推送团队排行榜（🥇 🥈 🥉 勋章、全员节约工时汇总、人均阅读量），点击按钮直达多维表格；
2. **离线与本地交互式图表大屏 (`HTML Dashboard`)**：自动渲染生成 KPI 统计卡片与全员横向工时节省柱状对比图，双击即可直接在浏览器交互。

周报与卡片按四个类目呈现：**文献检索 / 文献下载 / 文献高亮 / 其他**（其他类目只报工作时长与 Token，
不计节约工时）。公司公共统计表在原有 18 列之后追加了「其他任务数 / 其他工作时长(秒) / 其他Token消耗」三列。

### 接入公司既有表（字段自适应）

目标表的字段命名与本模块自建表不同也能直接写入：同步前先读取目标表实际字段名，自动判定 schema —— 自建标准表（字段见 `bitable_sync.TABLE_SCHEMA_FIELDS`）或公司既有「监控数据周报明细」表（13 字段）。写入时按映射改名，目标表没有的列自动丢弃、不报错；读取时反向归一化为标准字段名，因此图表大屏与战报逻辑无需改动。

| 配置键（`feishu` 段） | 说明 |
| :--- | :--- |
| `company_bitable_schema` | `standard` / `company` / 留空则自动识别 |
| `company_bitable_project` | 目标表「项目任务类型」的单选值，如 `via54Medit` |
| `company_bitable_member` | 目标表「提交成员」显示名，留空则用 `user.nickname` |
| `company_bitable_field_map` | 自定义「标准字段名 → 目标表字段名」覆盖 |

- **幂等**：以「汇报周期 + 成员」为 upsert 键；显示名映射同时作用于写入与查找，避免写成 A、查找按 B 而重复新增记录。
- **备注保护**：目标表备注列已有人工内容时，同步不会覆盖该格。
- **dry-run 无副作用**：`--sync --dry-run` 只输出 schema 判定结果与将写入的字段，不提交、也不写本地备份。
- **本地备份固定口径**：`~/.medit/team_bitable_backup.csv` 恒以标准字段名、按 `BACKUP_FIELDS` 固定列序落盘，与目标表是哪一种 schema 无关，便于回读与排查。追加前会先把表头对齐到当前列定义（见下方「新增列为什么只能追加在末尾」）。

---

### 新增列为什么只能追加在末尾

新增一个类目就是新增列。列**只能追加在末尾**，不能插在中间：

- 飞书电子表格的值接口只能往表格尾部追加，**没有插列接口** —— 云端插不了而本地插了，两边的列语义会立刻分叉；
- 中间插列会让**历史行整体错位**：旧行的「总节约工时」会落到新行的「其他任务数」位置上，而且表面上完全看不出来；
- 本地两个 CSV（公司公共统计表、多维表格备份）都是**按表头名回读**的（`dict(zip(header, row))`）。表头没更新就写入更宽的行，回读时会因列数不符被当作脏行**静默丢弃** —— 文件看着还在长，数据却在丢。

因此升级时由 `csv_migrate.migrate_header()` 统一处理（公共统计表与多维表格备份共用同一实现）：按**旧列名**取值、整表重写为新表头、新列补空；**绝不按位置硬搬**。迁移失败时**宁可不写**那一行，也不留下一个说不清的文件。

---

### 默认排程与「别关机」提醒

| 项 | 默认值 | 说明 |
| :--- | :--- | :--- |
| 周报推送与同步 | **每周一 10:30** | `schedule.weekly` |
| 月报推送与同步 | **每月 1 日 10:30** | `schedule.monthly`（可设 `-1` 表示月末） |
| **遇周末/法定节假日** | **顺延到下一个工作日** | `schedule.defer_non_workday`，默认开启 |
| 「别关机」提醒 | **推送日的前一个工作日 18:00** | `schedule.reminder`，默认开启 |

### 顺延规则（遇周末/法定节假日）

目标日落在**周末或法定节假日**时，顺延到**下一个工作日**：

| 原定 | 实际 | 原因 |
| :--- | :--- | :--- |
| 2026-10-01（周四） | 2026-10-08（周四） | 国庆连休 10-01 ~ 10-07 |
| 2026-10-05（周一） | 2026-10-08（周四） | 国庆连休 |
| 2026-11-01（周日） | 2026-11-02（周一） | 周末 |
| 2026-10-10（周六） | **不顺延** | 调休补班日，**是**工作日 |

要点：

- **补班的周六算工作日**，不会被误顺延（这是只按周末判断会踩的坑）。
- **目标日顺延，提醒日也跟着顺延后的日期走** —— 否则会出现"提醒说明天推、实际推到假期之后"。两者共用 `schedule.py` 这一份实现（`daemon` 与 `reminders` 都调它），不会分叉。
- **相邻两次目标可能落到同一天**：春节整周连休时，02-16 与 02-23 两个周一都顺延到 02-24。提醒侧按「类型 + 生效时刻」去重（只列一次并说明同期还有几次安排一并顺延），守护进程侧靠"当天只发一次"兜住。
- **只改"哪一天发"，不改"报哪一期"**：报表周期仍按实际发送日计算，于是卡片上的 `period_name`、表格行与多维表格记录三者自洽。常见顺延（1~6 天、仍在同一周/月内）周期完全不变。
- **顺延后文案会跟着变**：提醒日与推送日之间隔着整段假期时，不会再说"今晚请不要关机"（既不准确也没必要），改成"请在推送日之前确保设备开机联网"。
- 取不到节假日数据时（降级为仅按周末）顺延仍然可用，但会在原因里标出"仅按周末判断"，提醒卡片也会带 ⚠️ 提示。
- 关掉顺延：`config --no-defer`（或把 `schedule.defer_non_workday` 设为 `false`）。

**为什么需要「别关机」提醒**：推送是**到点触发**的 —— 守护进程必须在目标时刻正在运行。
机器关机或休眠，那一次周报/月报就**静默丢失**：不报错、不补发。提前一个工作日提醒，是唯一能在事前降低这种概率的手段。

（提醒本身也要靠机器在那一刻运行才能发出，所以它是降低概率、不是消除。为减少漏掉的可能，判定条件是"到了提醒时刻之后"而非"正好那一分钟"——18:00 该提醒、机器 22:00 才开机，当晚仍会补上。）

**同一天只发一张卡**：2026-09-30 既是「10-01 月报」的前一个工作日，也是「10-05 周报」的前一个工作日 —— 两条分开就是同一个晚上骚扰两次，因此合并成一张。

#### 为什么"前一个工作日"必须查法定节假日

不能只按周末算：

- **连休**：春节/国庆放假时，"前一天"本身可能是假期（2026 年国庆从 10-01 放到 10-07）；
- **调休补班**：某些周六要上班（2026 年 09-20 周日、10-10 周六都是补班日）。

不查安排就会提醒错日子。

#### 数据来源（权威性）

| 层级 | 来源 | 说明 |
| :--- | :--- | :--- |
| 主源 | [holiday-cn](https://github.com/NateScarlet/holiday-cn) | 机器可读，且**逐条标注对应的国务院公告链接**。2026 年指向《国务院办公厅关于2026年部分节假日安排的通知》（国办发明电〔2025〕7 号）：https://www.gov.cn/zhengce/zhengceku/202511/content_7047091.htm |
| 备源 | timor.tech 年度接口 | 主源不可达时使用（同样的放假/补班数据） |
| 降级 | 仅按周末判断 | **取不到数据时如实降级**，并把 `authoritative=false` 传出来；`config` / `holiday` 会标 `⚠️ 仅按周末推算` |

年份尚未公布（例如 2027 年安排通常在上一年 11 月前后发布）也走降级路径 —— 缓存里把"该年暂无数据"只留 3 天，公布后会自动补上。

缓存落在 `~/.medit/holidays/<年>.json`；有效数据缓存 30 天。`medit-telemetry holiday --refresh` 可强制重新取数。

## 人工效率计算模型

| 指标维度 | 人工基线耗时 | AI 自动化耗时 | 节约时间计算 |
| :--- | :--- | :--- | :--- |
| **文献检索** | 7 分钟 / 篇 | 自动记录真实检索用时 | $\text{count} \times 7\text{min} - \text{实际耗时}$ |
| **文献下载** | 2 分钟 / 篇 | 自动记录真实下载用时 | $\text{count} \times 2\text{min} - \text{实际耗时}$ |
| **文献高亮** | 4 分钟 / 篇 | 自动记录真实高亮用时 | $\text{count} \times 4\text{min} - \text{实际耗时}$ |
| **其他工作** | —— **无人工基准** | 自动记录真实用时 | **不计算**（见下） |

### 其他类目

不属于上面三类的一切工作都落在「其他」里：PPT/Word 渲版、PDF 解析、多维表格同步、环境巡检、
外部脚本…… 它与三类**一样统计工作时长与 Token 消耗**，但**不产出"节约工时"** ——
其他类目没有人工基线，与其编一个数出来，不如明确不给。

| 项 | 口径 |
| :--- | :--- |
| **归类规则** | 唯一事实来源是 `models.classify_task_type`。`correction` 并入高亮（修正属于高亮质检环节）；**未列出的 `task_type` 一律兜底到「其他」** —— 将来多出一种任务类型不会从战报里消失。 |
| **工作时长 / 任务数** | `tasks` 表中类目为 other 的任务（含用 `tracker.track_other()` 显式登记的）。 |
| **Token 消耗** | 与总量**同源同口径**累加，因此 `other.total_tokens ⊆ tokens.total_tokens` 由构造保证：① 归入其他的任务所携带的 token；② `llm_token_logs` 中 `task_id` 归不到三类任务的调用（含 `task_id` 为空的）。 |
| **`unattributed_tokens`** | 上面 ② 里"没有 `task_id`"的那部分。把它单列出来，是为了区分「真的是其他工作」与「调用方忘了标归属」—— 否则这个数字没法解读。 |
| **登记方式** | `with tracker.track_other(project_name="RSV", label="ppt_render") as col: col.add_tokens(...)` |

`scan_` 开头的扫描任务属于 watcher 的产出物折算，其 token 在 `exact` 模式下本就不计入总量，
因此也不计入「其他」（否则子集关系会被破坏）；它们的**工时仍计入其他**。

### 统计口径（唯一文献去重）

| 指标 | 计数口径 | 数据来源 |
| :--- | :--- | :--- |
| **文献检索** | 去重后的**唯一被引文献**数（重复引用同一篇只计 1 篇） | `高亮结果/*_meta.json` 的 `reference_field` / `doi`；缺失时回退 `高亮结果清单.tsv` |
| **文献下载** | 去重后的**唯一 PDF 文献文件**数 | 项目内 `*.pdf` |
| **文献高亮** | 去重后的**唯一高亮产物 PDF** 数 | `*_highlight.pdf`（TMA）或 `高亮结果/*.pdf`（RSV 等中文项目）；页数取真实物理页数之和 |
| **其他** | `tasks` 表中类目为 other 的任务数 | `tracker.track_other()`；以及任何未在归类表中登记的 `task_type` |

### 数据准确与实时

统计要做到"准"和"新"，靠三件事：

**1. 只统计真实产出物。** 备份/临时目录里的副本一律不计入（`watcher.is_ignored_path`）。判据是**路径片段的前缀**：`_bak*` / `.git` / `node_modules` / `__pycache__` 等视为备份，而 `_2_pdfs/`、`_highlight_nested/` 这类合法的下划线开头目录不受影响；文献名里恰好含 `bak` 也不会被误伤。

> 实测过这件事的代价：RSV 项目下的 `_bak_20260906_201108/高亮结果/` 与 `_bak2_20260906_205621/高亮结果/` 被当成成果扫了进来，同一篇文献在库里出现 3 行 —— 报表因此虚高到 3 倍（**150 篇 / 2917 页**，实际 **50 篇 / 977 页**；节约工时 20.19h → 14.49h）。而且**时对时错**：备份目录一删，数字又"自己变回去"。

**2. 已收录的条目也会刷新，不会冻结。** 命中去重后不再简单跳过，而是把**可变字段**跟到最新观测值：高亮的页数与标注数（用户在已有 PDF 上继续加标注）、下载的文件大小（重新下载后可能变大）。

- **刷新 ≠ 新增**：篇数口径完全不变，只有字段更新。
- **没观测到就不覆盖**：这次读不出值（`None`）时保持原值 —— 拿默认值去覆盖比不刷新更糟。
- 同时按 `paper_id` 兜一层去重，文件被移动/改名也不会让同一篇文献再加一行。

**3. 实时性是默认状态，不是额外功能。** 守护进程每 30 秒（`watcher.poll_interval_seconds`）巡检一次监控目录；报表是**当场从 SQLite 算出来的**，不做缓存。想立刻看到结果而不等下一个周期：

```bash
medit-telemetry refresh      # 立即扫描全部监控目录 + 刷新已收录条目 + 清理备份副本行
medit-telemetry status       # 末尾会显示"最近入库时间 + 距今多久"
```

`refresh` 的目录来自配置（`watcher.watch_dirs`），不是写死的路径；它也会**清理历史遗留的备份副本行**（清理很保守：只在同一篇文献于非备份路径下也有行时才删，绝不会把某篇文献整删掉）。

**怎么确认"数据是最新的"**：`daemon --status` 与心跳文件都带新鲜度凭据。

```jsonc
// ~/.medit/daemon_heartbeat.json
"freshness": {
  "latest_ingest_at": "2026-09-10T18:19:52",      // 最近一次明细入库时间
  "counts": {"retrieval_items": 44, "download_items": 215, "highlight_items": 50, "tasks": 10}
}
```

> ⚠️ **改了采集逻辑要重启守护进程**：配置每 5 秒重载，但**代码不会**。旧进程会继续用内存里的旧扫描器 —— 例如路径卫生修好之前启动的进程，会把你刚清理掉的备份副本行再插回去。改完代码用 `launchctl kickstart -k gui/$UID/com.via54medit.telemetry`（或 `daemon --stop && daemon --start`）重启一次。

> **检索数去重规则**：早期版本仅从 `*doi_map*.json` / `*inventory*.json` 读取检索记录，因此在没有这类清单的项目（如 RSV）中恒为 0。现改为按「高亮引用清单」折算 —— 每条 Pn-x 记录对应其被引文献，按文献去重后计数。去重分两层：
>
> 1. **DOI 精确层** —— 清单带 `doi` 时以归一化 DOI 为身份（去掉 `https://doi.org/`、`doi:` 前缀并忽略大小写），跨著录写法稳定；
> 2. **引用身份层** —— 无 DOI 时，按引用串归一化（忽略大小写与空白，并剔除 `Available at:` / `Accessed` / URL / 文档编号等样板尾巴）取得身份，并对「同一文献的不同著录写法」做**保守前缀归并**：仅当其一为另一者的前缀、且多出的尾巴属纯数字/日期/文号一类良性噪声时才判为同一篇；尾巴若含 `supplementary` / `appendix` / `erratum` / `reply` 等有独立意义的限定词则**不合并**，避免把正文与其补充附录误并成一篇。

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
├── csv_migrate.py        # CSV 表头迁移 (新增类目 = 新增列, 只能追加在末尾)
├── tracker.py            # 三段式埋点上下文 (检索 / 下载 / 高亮 / 其他)
├── token_tracker.py      # LLM 网关拦截与 100% 控制台对齐
├── pdf_utils.py          # 三重容灾真实 PDF 物理页数计算
├── watcher.py            # 工作区产出物主动感知器
├── feishu_sync.py        # 飞书卡片构建与消息推送
├── bitable_sync.py       # 飞书多维表格 (Bitable Base) OpenAPI 与 Upsert
├── envcheck.py           # 运行环境自检 (PYTHONHOME / PYTHONPATH 冲突识别与提示)
├── platform_paths.py     # 跨平台路径解析 (应用数据目录 / 桌面 / 启动项 / 用户级 bin 目录)
├── chart_reporter.py     # 团队多人数据汇总与可视化图表报告
├── scripts/
│   └── medit-telemetry   # 外壳启动器模板 (环境冲突拦截, 由 deploy.py 安装)
└── README.md             # 本说明文档
```
