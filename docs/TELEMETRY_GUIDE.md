# TraeWork 文献整理与 Highlight 监控统计及飞书同步工具全维指南

本文档介绍 `via54Medit` 中面向 TraeWork 的全维度耗时监控、Token 消耗统计、人效折算、飞书会话推送、企业公共表同步，以及**跨设备授权部署、花名配置与主动后台监控**的完整功能。

---

## 1. 核心功能特性

1. **全维度自动化统计**：
   - **文献检索**：统计总耗时、总检索篇数（去重后的唯一被引文献数）、单篇平均检索耗时、Token 消耗。检索记录来自 `高亮结果/*_meta.json` 的引用字段，缺失时回退 `高亮结果清单.tsv`；去重优先按 DOI 精确匹配，无 DOI 时按引用身份并做保守前缀归并（补充附录等独立文献不合并）。
   - **文献下载**：统计成功下载文献总数、逐篇下载耗时、单篇平均下载耗时、成功率。
   - **文献 Highlight**：统计总耗时、阅读文献总页数、单篇高亮平均耗时、单篇检查修正平均耗时、Token 消耗。
2. **人效节约收益模型**：
   - **检索基准**：人工检索平均 **7 分钟 / 篇**。
   - **下载基准**：人工下载平均 **2 分钟 / 篇**。
   - **Highlight 基准**：人工高亮平均 **4 分钟 / 篇**。
   - 自动按周、按月计算净节约工时（小时/分钟）。
3. **跨设备部署与花名自主授权**：
   - **多设备初始化向导**：`python -m telemetry.cli init` 交互式引导填写花名、授权飞书账号。
   - **免密自动感知**：若目标设备已安装 TraeWork，自动复用本机飞书凭据，免去重复配置。
   - **花名随时修改**：支持随时通过命令调整用户花名，并与所有统计报表实时联动。
4. **主动监控与排程守护 (Daemon)**：
   - **后台主动嗅探**：守护进程每 30 秒主动轮询工作区，发现新下载/新高亮成果实时自动入库。
   - **周报/月报自由排程**：支持自定义每周、每月推送时间（如“每周五 18:00”、“每月 1 日 09:00”）。
   - 到点自动推送交互式战报卡片至绑定飞书账号，并自动同步至公司公共统计表。
5. **飞书多维表格 (Bitable) 团队协作**：
   - **字段自适应**：同步前读取目标表实际字段名自动判定 schema（自建标准表 15 字段 / 公司既有「监控数据周报明细」表 13 字段）。写入时按映射改名并丢弃目标表没有的列，读取时反向归一化为标准字段名，因此接入公司既有表无需改动图表大屏与战报逻辑。
   - **幂等上传**：以「汇报周期 + 成员」为 upsert 键，同一周重复上传只更新原记录不新增；目标表备注列已有人工内容时不覆盖。
   - **演练与备份**：`bitable --sync --dry-run` 先看 schema 判定与将写入字段，不提交也不写备份；本地 `~/.medit/team_bitable_backup.csv` 恒以标准字段名、固定 15 列落盘，与目标表 schema 无关。

---

## 2. 命令行使用速查表

### A. 首次部署与配置
```bash
# 1. 在新设备上运行初始化向导 (设置花名、飞书授权、排程时间)
python -m telemetry.cli init

# 2. 查看当前设备配置与排程状态
python -m telemetry.cli config

# 3. 随时修改用户花名 (例如修改为 "星云")
python -m telemetry.cli config --nickname "星云"

# 4. 灵活修改每周报告时间 (例: 每周五 18:00)
python -m telemetry.cli config --set-weekly "Friday 18:00"
# 或中文
python -m telemetry.cli config --set-weekly "周五 18:00"

# 5. 灵活修改每月报告时间 (例: 每月 1 日 09:00 或 月末最后一天 18:00)
python -m telemetry.cli config --set-monthly "1 09:00"
python -m telemetry.cli config --set-monthly "last 18:00"
```

### B. 主动监控守护服务 (Daemon)
```bash
# 1. 在后台启动主动监控守护进程 (实时嗅探 + 到点自动推送)
python -m telemetry.cli daemon --start

# 2. 查看守护进程运行状态与心跳
python -m telemetry.cli daemon --status

# 3. 停止后台守护进程
python -m telemetry.cli daemon --stop

# 4. 开机自启与伴随启动 (两种联动方案任选):
# 方案 A (推荐): 注册开机自启 (macOS 写入 LaunchAgent; Windows 写入 Startup VBS; 登录后后台自动静默自启)
python -m telemetry.cli daemon --install-startup
# (若需取消自启): python -m telemetry.cli daemon --uninstall-startup

# 方案 B: 在桌面生成 TraeWork 伴随启动器 (点击图标即同时启动 TraeWork + 监控守护服务)
python -m telemetry.cli daemon --create-launcher

# 方案 C: 注册为 Windows 计划任务
python -m telemetry.cli daemon --install-task
```

### C. 手动报表与推送测试
```bash
# 1. 查看当前效率与工时节约总览
python -m telemetry.cli status

# 2. 生成周报 / 月报
python -m telemetry.cli report --period week
python -m telemetry.cli report --period month
python -m telemetry.cli report --period all --json

# 3. 手动推送周报/月报卡片至飞书会话
python -m telemetry.cli push --period week
python -m telemetry.cli push --period month --dry-run  # 演练预览

# 4. 同步成绩至公司公共统计表 (追加一行)
python -m telemetry.cli sync --period week

# 4b. 团队飞书多维表格 (Bitable): 创建 / 绑定 / 上传 / 图表看板
python -m telemetry.cli bitable --create             # 云端新建团队监控多维表格
python -m telemetry.cli bitable --bind <URL_OR_TOKEN>  # 绑定团队已有多维表格
python -m telemetry.cli bitable --sync               # 上传本周数据 (按「周期+成员」幂等 upsert)
python -m telemetry.cli bitable --sync --dry-run     # 演练: 只看 schema 判定与将写入的字段, 不落库
python -m telemetry.cli bitable --report             # 汇总全员数据生成图表大屏

# 5. 扫描指定项目目录成果并自动入库
python -m telemetry.cli scan C:\Users\via54\Desktop\RSV --name RSV

# 6. 一键补录全部历史交付物 (RSV, TMA)
python -m telemetry.cli backfill

# 7. 大模型 Token 账单管理 (默认 100% 控制台绝对一致)
python -m telemetry.cli token --status             # 查询真实调用明细
python -m telemetry.cli token --log 3200 800       # 手动核对补登控制台账单
python -m telemetry.cli token --mode exact         # 设置默认模式 (exact / estimated)

# 8. 运行环境自检 (排查 PYTHONHOME / PYTHONPATH 冲突)
python -m telemetry.cli --env-check
```

---

## 3. 在 Python 流水线中集成探针

在自定义脚本中，使用 ContextManager 即可无缝纳管：

```python
from telemetry import TelemetryTracker

tracker = TelemetryTracker()

# 1. 监控文献检索
with tracker.track_retrieval(project_name="RSV") as col:
    col.add_item(paper_id="P3-1", url="https://doi.org/10.1016/...", duration_seconds=12.5)
    col.add_tokens(prompt_tokens=1500, completion_tokens=300)

# 2. 监控文献下载
with tracker.track_download(project_name="RSV") as col:
    col.add_item(paper_id="P3-1", pdf_path="P3-1.pdf", file_size_bytes=1048576, duration_seconds=6.2, success=True)

# 3. 监控文献 Highlight
with tracker.track_highlight(project_name="RSV") as col:
    col.add_item(paper_id="P3-1", pdf_path="P3-1_highlight.pdf", page_count=12, num_annots=8, 
                 highlight_duration_seconds=28.0, correction_duration_seconds=8.0)
    col.add_tokens(prompt_tokens=2200, completion_tokens=500)

# 4. 任意脚本直接记录大模型真实网关 Usage (100% 对齐控制台)
from telemetry import record_llm_usage

response = client.chat.completions.create(...)
record_llm_usage(response, provider="deepseek", model="deepseek-chat", project_name="RSV")
```

---

## 4. 本地持久化与凭据文件分布

本机状态统一落在 `~/.medit/` 下，跨平台一致：

- **统一主配置文件**：`~/.medit/telemetry_config.json`
- **本地 SQLite 数据库**：`~/.medit/telemetry.db`
- **守护进程日志与心跳**：`~/.medit/daemon.log`、`~/.medit/daemon_heartbeat.json`
- **公共表本地双备份**：`~/.medit/company_public_stats.csv`
- **多维表格本地备份**：`~/.medit/team_bitable_backup.csv`（恒以标准字段名、固定 15 列落盘，与目标表采用哪种 schema 无关）
- **TraeWork 预装飞书源** (`channel_config.json`)：由 `telemetry/platform_paths.py` 统一解析，当前平台根目录优先，其余平台根目录兜底：

| 平台 | 应用数据根 | 完整路径 |
| --- | --- | --- |
| Windows | `%APPDATA%` | `%APPDATA%\TRAE SOLO CN\User\globalStorage\cloudide.icube-im-bridge\feishu-bridge\<workspace>\channel_config.json` |
| macOS | `~/Library/Application Support` | `~/Library/Application Support/TRAE SOLO CN/User/globalStorage/cloudide.icube-im-bridge/feishu-bridge/<workspace>/channel_config.json` |
| Linux | `$XDG_CONFIG_HOME` 或 `~/.config` | `<XDG>/TRAE SOLO CN/User/globalStorage/cloudide.icube-im-bridge/feishu-bridge/<workspace>/channel_config.json` |

`<workspace>` 为 workspace 槽位号；解析器会扫描 `feishu-bridge` 下的任意子目录，换机后槽位号变化仍可命中。

---

## 5. 故障排查

### 5.1 报错 `Fatal Python error: init_fs_encoding ... No module named 'encodings'`

**原因**：终端里被预置了指向**另一个 Python** 的 `PYTHONHOME`（常见于 IDE、沙箱、构建工具链），本工具的解释器在**启动阶段**就崩溃，因此任何 Python 层的自检都来不及执行。

**自检**：

```bash
python -m telemetry.cli --env-check
```

会打印解释器路径、`PYTHONHOME` / `PYTHONPATH` 的实际取值与冲突结论。

**修复**：

```bash
env -u PYTHONHOME -u PYTHONPATH medit-telemetry status   # 临时规避 (立即生效)
unset PYTHONHOME PYTHONPATH                              # 或在当前终端先清掉
```

根治方式是在 shell 启动脚本（`~/.zshrc` / `~/.bashrc`）中删除对这两个变量的 `export`。本工具只依赖标准库，移除后不影响任何功能；后台守护进程由 LaunchAgent / 计划任务拉起，不继承终端环境，始终不受影响。

**自动拦截**：`medit-telemetry` 命令本身是一个环境自检启动器（由 `telemetry/scripts/medit-telemetry` 安装）。它在解释器启动前比对 `PYTHONHOME` 与本解释器前缀、以及 `PYTHONPATH` 里的版本目录，发现冲突时改用 `-E` 忽略全部 `PYTHON*` 变量执行并打印一行说明——把崩溃变成可用的命令。未检测到冲突时行为与直接调用解释器完全一致，原命令备份为同目录下的 `*.orig`。

### 5.2 仅 `PYTHONPATH` 被污染（解释器能启动，但导入异常）

`PYTHONPATH` 若注入了别的 Python 版本的 `site-packages`，可能导入到 ABI 不兼容的扩展模块。此类情形解释器能正常启动，因此在 `cli.main()` 入口的运行时自检（`telemetry/envcheck.py`）会直接给出冲突明细与修复命令，无需依赖外壳启动器。两条路径用 `MEDITELEMETRY_ENV_ISOLATED` 标记交接，只提示一次、不重复刷屏。
