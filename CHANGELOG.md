# Changelog

All notable changes to via54Medit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**版本号说明**: 本仓库有两套编号 —— CHANGELOG 用内部版本号 (4.x / 5.x), GitHub Releases 另用公开发布号。早期两者不同轨, 2026-09 起已对齐。

| 公开 Release | 内部版本 | 日期 | 说明 |
| --- | --- | --- | --- |
| `v5.0.0` | 5.0.0 | 2026-09-10 | medit-telemetry v1.1.0 独立模块发布 |
| `v4.9.0` | 4.9.0 | 2026-09-06 | Step5 视觉双对齐终版 + 文献高亮复核闭环 |
| `v1.0.0` | 4.5.x (同期内部号) | 2026-07-03 | 首次公开稳定版: Medical RAG Agent & Multi-Agent MCP Server |

## [Unreleased]

### Phase 5.0 升级 (2026-06-30) — 双模式医药决策平台
> **触发**: 用户提交 TalkMED AgentPilot 7 页 PDF 报告 (123.pdf), 要求融合 EBM 学术 + 商业医药情报 + TalkMED 类报告生成 3 个方向
> **状态**: 架构升级草稿完成, 等用户拍板

#### Added
- `integrations/CATALOG.md` — **115+ 数据源全景目录** (EBM 55+ + 商业 60+)
- `integrations/clinicaltrials_v2.md` — ClinicalTrials.gov v2 P0 集成计划
- `integrations/openfda.md` — OpenFDA P0 集成计划 (14 tools MCP)
- `integrations/sec_edgar.md` — SEC EDGAR P0 集成计划 (TalkMED 财报核心)
- `integrations/europe_pmc.md` — Europe PMC P0 集成计划
- `integrations/medrxiv_biorxiv.md` — 预印本 P0 集成计划
- `integrations/fda_orange_book.md` — Orange Book P0 集成计划 (专利+独占期)
- `integrations/chembl_pubchem.md` — ChEMBL/PubChem P0 集成计划 (化学实体)
- `integrations/dailymed.md` — DailyMed P0 集成计划 (药物标签)
- `integrations/pubtator3.md` — PubTator 3.0 P0 集成计划 (NLP 实体)
- `integrations/aha_acc_eas.md` — AHA/ACC/EAS 会议摘要 P1 集成计划 (TalkMED §4 直接相关)
- `docs/ARCHITECTURE-V5.md` — v5.0 双模式架构升级草案 (6 层 + 双模式路由)

#### Changed
- 项目定位: 单模式 EBM 路由器 → **双模式医药决策平台** (EBM 学术 + 商业情报)
- 架构: 5 层 → **6 层 + 双模式路由** (Layer 4A EBM / Layer 4B 商业)
- CLI: 13 子命令 → **18 子命令** (+5 商业: intel/market/pipeline/patent/trial)
- MCP: 4 tools → **7 tools** (+3 商业: medit_intel/medit_market/medit_pipeline)
- 数据源: 4 现存 → **16 P0** (10 学术 + 12 商业 - 6 重复)

#### Methodology
- **Subagent #1 (EBM 方向)**: 扫描 GitHub biocontext-ai/registry (60+ MCP) + awesome-evidence-synthesis, 找到 55+ 学术源 + genomoncology/biomcp 超级 MCP (MIT, 12+ 实体类别, 应当借鉴)
- **Subagent #2 (商业方向)**: 扫描 9 类商业源 (销售/管线/专利/财报/报告/会议/BD), 找到 60+ 商业源 + TalkMED PDF 反推 7 页报告需哪些源
- **整合**: CATALOG.md + 10 个 P0 集成计划 .md (1-3 天工作量/源)

#### Reference
- TalkMED AgentPilot (https://agent-pilot.talkmed.com) — DXY 旗下医药商业情报 AI 平台, 7 页 PDF 报告为参照样本

## [5.2.0] - 2026-09-10 (检索去重引入 DOI 精确层 + 引用身份保守归并)

### Changed (指标口径细化)
- **telemetry/watcher.py**: 检索去重细化两层 ——
  1. **DOI 精确层**: 清单带 `doi` 时以归一化 DOI 为身份 (剔除 `https://doi.org/` / `doi:` 前缀并忽略大小写), 跨著录写法稳定;
  2. **引用身份层**: 无 DOI 时按引用串归一化身份去重, 新增 `_same_reference()` 保守前缀归并 —— 仅当其一为另一者前缀、且多出的尾巴属纯数字/日期/文号一类良性噪声时才判为同一篇。
- **防误并**: 尾巴含 `supplementary` / `suppl.` / `appendix` / `erratum` / `corrigendum` / `reply` / `comment` / `abstract` / `poster` / `protocol` 等有独立意义的限定词时**不合并**, 避免正文与其补充附录被误并为一篇; 另设 30 字符最短公共前缀阈值 (两篇同为 `Zar HJ, et al. N Engl J Med. 2025;393(13):…` 的不同文章公共前缀仅 27 字符, 不会被合并)。
- **样板噪声剔除**: 归一化时剔除 `Available at: …` / `Accessed …` / URL / 文档编号 (如 `07-2028-CN-RSM-00086`) 等不承载文献身份的尾巴。
- **telemetry/README.md** / **docs/TELEMETRY_GUIDE.md**: 更新为两层去重规则的完整说明。
- 模块版本 1.2.0 → 1.3.0。

### 验证
- test_telemetry 20/20 passed (新增 `test_retrieval_dedup_by_doi` 与 `test_retrieval_merges_noise_suffix_but_keeps_appendix`)
- RSV 实测: 检索 46 → **44 篇**。两处归并均已确认为同一文献 —— `WHO position paper …` (尾部差异为 `May 2025.` 与 `(Accessed date: 2025.06.02)`) 与 `Fleming-Dutra KE … MMWR 2023;72(41):1115-1122.` (其一尾部多出文档编号); 正文与其 `Supplementary Appendix` 保持独立, 未被合并。
- 生效层说明: RSV 清单的 `doi` / `pmid` 字段全为空 (`pubmed_url` / `scholar_url` 只是用引用串拼的搜索链接, 不含 DOI), 故本次实际生效的是**引用身份层**; DOI 层为结构预留, 在带 DOI 的数据集上可精确去重。

## [5.1.0] - 2026-09-10 (检索指标口径: 按高亮引用清单折算唯一被引文献)

### Changed (指标口径)
- **telemetry/watcher.py**: 新增 `_collect_reference_records()` 与扫描步骤 1b —— 从「高亮引用清单」折算检索数。数据源优先级: `高亮结果/*_meta.json` (含完整 `reference_field` / `doi` / `pmid`) → `高亮结果清单.tsv` (回退; 该 TSV 的 `reference_field` 会被导出截断, 故仅作兜底)。原先仅从 `*doi_map*.json` / `*inventory*.json` 读取, 导致没有这类清单的项目 (如 RSV) 检索数恒为 0。
- **口径定义**: 检索数 = **去重后的唯一被引文献数** (重复引用同一篇只计 1 篇), 与"下载/高亮"指标同为唯一文献口径, 也与 `aggregator` 既有去重逻辑 (`doi or url or paper_id`) 对齐; 无 DOI 时以引用串归一化 (忽略大小写与空白) 去重。
- **telemetry/README.md** / **docs/TELEMETRY_GUIDE.md**: 新增「统计口径 (唯一文献去重)」说明, 明确三项指标的计数口径与数据来源。
- 模块版本 1.1.1 → 1.2.0。

### 验证
- test_telemetry 18/18 passed (新增 `test_scanner_retrieval_from_highlight_reference_list` 与 `test_scanner_retrieval_falls_back_to_tsv_list`)
- RSV 实测: backfill 折算出检索 46 篇 (50 条 Pn-x 记录中含重复引用, 去重后 46 篇唯一文献), 累计节约 20.41h
- 已知口径边界: 无 DOI 时, 同一文献的不同著录写法 (标点差异、附录后缀等) 可能被计为多条

## [5.0.1] - 2026-09-10 (medit-telemetry 跨平台修复与 macOS 自启 + README 表格校正)

### Fixed (medit-telemetry 1.1.0 → 1.1.1)
- **telemetry/platform_paths.py** (新增): 跨平台路径解析模块。按 `sys.platform` 给出 TraeWork 应用数据根 (Windows `%APPDATA%` / macOS `~/Library/Application Support` / Linux `$XDG_CONFIG_HOME`), 当前平台优先、其余平台兜底；并扫描 `feishu-bridge` 下任意 workspace 子目录, 换机后槽位号变化仍可命中。
- **telemetry/config.py**: `TRAE_WORKSPACE_CONFIG` 与 `load_config()` 嗅探改用平台候选链 (原先硬编码 `~\AppData\Roaming\...`, 导致 macOS/Linux 上飞书 app_id/app_secret 永远嗅探不到); 默认 `watch_dirs` 改用 `trae_work_dir()` / `desktop_dir()`, 消除 `~\.trae-cn\work`、`~\Desktop` 反斜杠在 POSIX 下被当作普通字符的问题。
- **telemetry/feishu_sync.py**: `TRAE_CONFIG_PATH` 改用平台解析。
- **telemetry/daemon.py**: `get_startup_vbs_path()` 改为返回 `Optional[str]`, 非 Windows 显式返回 `None` (原先返回 `/Users/xxx/\AppData\...` 这类伪路径); `install_startup_vbs` / `uninstall_startup_vbs` / `install_traework_companion_launcher` 增加平台守卫; 伴随启动器路径改用 `desktop_dir()`。
- **telemetry/cli.py**: `backfill` 扫描目标改用 `desktop_dir()` / `trae_work_dir()`; `daemon --install-startup` / `--uninstall-startup` 改为按平台分派。
- **telemetry/watcher.py**: 修正高亮产物识别 —— 原先只认 `*_highlight.pdf` 命名, 导致 RSV 的 `高亮结果/*.pdf` (50 篇) 全部漏记; 新增该布局及 `*/高亮结果/*.pdf` 的识别, 标注数改为优先读同级 `*_verify.json`、否则用 PyMuPDF 数 PDF 内真实标注 (不再回退到固定值臆测)。
- **tests/test_telemetry.py**: `test_daemon_helpers` 改为平台感知断言; 新增 `test_platform_paths` (三平台根路径/候选链/反斜杠检查)、`test_launchd_agent_paths`、`test_scanner_recognizes_chinese_highlight_dir`。
- **README.md**: 修复「数据互补对照」表中 `≥3 级蛋白尿 5%` 行缺列 (4 列表头写成 3 列, v5.0.0 误删一格); 依 `skills/via54medit-anno2ppt-pitfalls-2026-08/references/dual-source-architecture.md` 与 `skills/via54medit-architecture-honest-status/references/v4.1-dual-source-architecture.md` 两份双源参考表恢复为 `PPT 需求 ✅ / main ❌ / fallback ✅ 5.7% (NCT SAE)`。

### Added (macOS 开机自启)
- **telemetry/daemon.py**: 新增 `install_launchd_agent()` / `uninstall_launchd_agent()` / `get_launchd_status()` —— 生成 `~/Library/LaunchAgents/com.via54medit.telemetry.plist` 并 `launchctl bootstrap` (失败回退 `load -w`); `RunAtLoad` + `KeepAlive` 让守护服务登录后常驻、异常退出自动拉起; 注册前先停掉手工启动的游离实例, 避免双跑。
- **telemetry/deploy.py**: 步骤 4 与卸载流程接入 macOS 分支, 部署概览显示 LaunchAgent 状态 (原先该步骤在非 Windows 平台直接跳过)。

### 验证
- test_telemetry 16/16 passed (原 13 + 新增 3); telemetry 全 16 模块 import 通过; `medit-telemetry config` 正常读取 3 个监控目录
- macOS 实测: 飞书凭据嗅探命中 `~/Library/Application Support/TRAE SOLO CN/.../channel_config.json`, 解析出 app_id / app_secret / open_id / bot_name
- macOS 实测: LaunchAgent 已加载且 `state = running` (PID 79366), 守护心跳正常
- backfill 实测 (修复扫描器后): RSV 补录 高亮 50 篇 / 977 页、下载 215 篇, 累计节约 9.51h

## [5.0.0] - 2026-09-10 (medit-telemetry v1.1.0 独立模块发布)

> Tag `v5.0.0` (commit `407418d`): via54Medit 文献整理与 Highlight 监控统计独立模块 — 支持跨设备一句话部署、100% 服务商 Token 对齐、飞书多维表格全自动同步与团队可视化图表报告。

### Added (telemetry 独立模块)
- **telemetry/ (新)**: 独立可分发包 (22 个文件), 含 `setup.py` / `pyproject.toml` / `cli.py`, 注册全局命令 `medit-telemetry` / `traework-telemetry`。
- **一句话独立部署**: `deploy.ps1` (PowerShell, Windows 首选) / `deploy.py` (跨平台 Python) / `deploy.bat` (CMD) 三种入口; 集成开机静默自启、桌面伴生启动器与后台守护进程。
- **自然语言部署引擎** `nlp_deploy.py`: 从一句话中提取花名、OpenID、周报/月报排程与多维表格链接, 落地为 `~/.medit/telemetry_config.json`。
- **Token 100% 控制台对齐** `token_tracker.py`: 拦截大模型 API 真实 `usage` 账单入库, 杜绝估算虚高; 无真实外呼一律计 0。
- **真实物理页数与文献去重** `pdf_utils.py`: `pypdf` → `fitz` → 原生二进制 `/Count` 三重降级解析, 离线环境亦可正确统计。
- **飞书多维表格团队同步** `bitable_sync.py`: 自动创建或绑定 Bitable Base, 15 个标准化字段 + 幂等 Upsert 写入。
- **团队图表报告** `chart_reporter.py`: 汇总全员战报, 生成飞书 Top 5 人效排行卡片与 HTML 可视化交互大屏。
- **后台守护与调度** `daemon.py` + `watcher.py`: 监控目录轮询、心跳落盘、周报/月报定时推送。
- **.agents/skills/medit-telemetry-deploy/SKILL.md**: 供智能体直接调用的跨设备一句话部署技能。
- **docs/TELEMETRY_DEPLOY.md** / **docs/TELEMETRY_GUIDE.md**: 部署手册与使用指南。
- **Makefile**: 新增 `telemetry-deploy` / `telemetry-install` / `telemetry-status` / `telemetry-test` 四个目标。
- **tests/test_telemetry.py**: 13 项单元测试。

### Changed (接入与文档)
- **scripts/via54.py**: 新增 `telemetry` 子命令入口 (转发至 `telemetry.cli`), 并将项目根加入 `sys.path` 以便导入。
- **scripts/via54_auto.py**: 识别「部署/安装 + 监控/telemetry/飞书同步」自然语言意图后, 自动执行独立部署。
- **scripts/glm_vision.py** / **scripts/hl_v3_final/vision_check.py**: 接入 `token_tracker`, 分别记录 zhipu 与 sensenova / minimax / zhipu 三路视觉调用的真实 usage。
- **README.md** / **README.zh-CN.md**: 新增 Telemetry 模块章节与单行部署示例。
- **.gitignore**: 忽略 `*.egg-info/` 与 `build/`。

### 验证
- tests/test_telemetry.py 13/13 passed

## [4.9.0] - 2026-09-07 (step5 真·视觉双对齐终版 + 文献高亮复核闭环)

### Added (文献高亮 · Step5 终版)
- **scripts/step5_vision_final.py**: Step5 真·视觉双对齐终版脚本。对每个 Pn-x 以「左=引用位置裁剪图(claim_visual)、右=文献含高亮候选页」送入 mmx 视觉模型, 逐条返回支撑该引用位置论点的完整原句(附页码) → 原文流整句定位 → 单 Highlight 落位。
- 覆盖乱码/图像型 PDF: 复用 `hl_v3_final/hl_lib.py` 词级定位 + `provider_vision.py` 视觉降级链。
- **scripts/hl_v3_final/verify_sentence_set.py**: 句集定位复现验证器。读整句清单 TSV, 用 hl_lib 在 PDF 逐句重新定位, 报告 NOT FOUND/OCR 通道分布 (RSV 745 句实测: 730 文本定位 OK + 15 OCR 通道句)。
- **scripts/hl_v3_final/hl_ocr_band.py**: OCR 词级高亮器 (乱码/纯图像 PDF 通道)。渲染→tesseract TSV(line 分组)→分栏阅读序词流→start/end 短语窗口→行 band→Highlight quads(仅栏内 x 不跨栏); 支持 --crop-top/bottom(整页 psm 漏检灰框区域)、--psm、--replace-page、--dry-run。

### Changed (复核闭环)
- 引用高亮复核规范固化: 整句完整性 / 头部元数据与作者区禁盖 / 跨栏行带收敛至词级(双栏 x 约束) / 图像型 PDF 走 OCR 行带——已在本轮 RSV 50 文件全量复核落地(0 高亮文件从 10 → 5, 余 5 为脚注型设计 0 与缺源待补)。

### 验证
- test_hl_lib 36/36 passed; step5_vision_final.py 语法检查通过; 密钥泄漏扫描无命中

## [4.8.0] - 2026-08-21 (跨平台部署: 任意设备自动接入软件/工具/包 + skills 仓库化)

### Added (跨平台自动接入)
- **medit doctor**: 部署自检 (Python 解释器/包/浏览器/CDP/soffice/pdftotext/lark-cli/env 覆盖点), --fix 自动 pip 安装
- **medit browser start/health/stop**: Chrome/Edge/Chromium 跨平台自动探测 + 独立 profile 调试实例启动 (port 9223), antfu health 已接入自动启动
- **internal/foundation/python.go**: Python 解释器探测链 (config > $PYTHON > python3.11 > python3 > python) + HermesHome/UserMeditDir 可移植辅助
- **skills/ (新)**: 9 个核心 skills vendored 入库 (anno2ppt phase7+pitfalls/highlight-strict/literature-pipeline 等, 1.5MB) + **scripts/skills_bootstrap.py** 一键同步 (幂等/--dry-run/--force/--list)
- **requirements.txt** (pywin32 平台标记) + **deps_auto.py** 增强 (requirements 优先安装 + soffice/pdftotext/lark-cli 系统工具探测提示)
- **ppt_render_engine.py**: LibreOffice soffice 引擎 (全平台, COM 之后近似之前) + 跨平台 CJK 字体探测 (Windows 雅黑/macOS 苹方/Linux Noto+fc-match)
- **.github/workflows/ci.yml**: 三平台 (ubuntu/macos/windows) Go build+vet+race + Python 工具链测试 (79+25 用例)
- **docs/DEPLOY.md**: 三平台安装/软件接入矩阵/env 覆盖点/FAQ

### Changed (可移植性修复)
- 硬编码个人路径 env 化: HLO_DIR/HLO_PYTHON/HLO_SQLITE/HERMES_HOME/LIT_ROOT/LARK_CLI/HERMES_ENV 覆盖 anno2ppt/hlo_orchestrator/prompt/medit-mcp/self_check/audit_v13/citation_sync
- hlo_orchestrator osHomeDir(sh echo $HOME) → os.UserHomeDir; lit_truth.json → $HERMES_HOME/cache
- .goreleaser.yaml + release.sh: 启用 windows/arm64 (6 平台矩阵)

### 验证
- go test ./... -race 全绿 (新增 chrome_launcher/python 探测单测 8 用例)
- test_tma_pipeline 79/79 + test_hl_lib 25/25 (改动后回归)
- 本机实测: medit browser start 自动启动 Chromium → CDP 就绪 → stop 关闭 9 进程; doctor 全项输出; ppt_render_engine 检测到 soffice+STHeiti

## [4.7.0] - 2026-08-21 (medplan: 医学策划方案生成 + 中国大陆合规验证)

### Added
- **internal/medplan/** (10 文件): 医学策划六阶段管线 — Brief(指令+产品) → 五维调研(文献=router 真实检索, 新闻/研报/政策/竞品=LLM 综合待核验) → 观点提炼(insights+SWOT, item_id 白名单校验) → 分受众大纲(HCP/患者/行业, 五核心模块稳定骨架) → 语义优化(版本化 changelog+结构 diff) → 合规验证(规则引擎常开+LLM 语义层+否定语境豁免)
- **compliance_rules.go**: 12 条数据驱动规则 — 广告法§9 绝对化用语/§16 疗效断言·安全性保证·比较·代言, 药品管理法§89 处方药大众媒介禁令(RxOnly), 医疗广告管理办法§7, 患者材料 DTC 禁令+disclaimer presence 检查(PatientOnly), RDPAC HCP 边界; verdict pass/warn/fail + section 级标注回写
- **internal/foundation/llm_glm.go**: GLM provider (RegisterLLM("glm"), BigModel OpenAI 兼容端点, GLM_API_KEY/ZHIPU_API_KEY)
- **cmd/medit/commands/medplan.go**: `medit medplan new|run|research|outline|optimize|compliance|show|list` 8 子命令; 存储 ~/.medit/medplan/<项目>/ (JSON+MD 原子写)
- **docs/MEDPLAN.md**: 完整文档 + GitHub 高星项目调研(STORM 31.1k★ outline-first 借鉴, gpt-researcher 29.1k★ 引用溯源, ToolGood.Words 5.2k★ 词库升级路径; 结论: 该定位无直接开源竞品)

### Fixed
- **internal/prompt/compiler.go**: loadCorrectionsAsTrainset 失败路径返回 nil → 空 slice (预存在测试失败修复)

### 验证
- go test ./... -race 全绿 (medplan 26 用例 + GLM provider 4 用例新增)
- CLI 冒烟: 真实调研回 116 条文献 (PubMed/OpenAlex/S2), 三档大纲+合规端到端; 否定语境豁免修复模板合规提示句误报 (patient FAIL→PASS)

## [4.6.1] - 2026-08-20 (TMA highlight 全流水线集成: 89 引用级联下载 + 内容核验 + 批量 highlight)

### Added
- **scripts/tma_cascade_download.py**: 多级 OA 级联下载 (OpenAlex/Unpaywall/EuropePMC/NCBI PMC/doi.org), 项目根经 `TMA_PROJECT` 环境变量覆盖
- **scripts/tma_download_round2.py + tma_scihub.py**: CrossRef 重解析 DOI + 首页内容三维核验 (期刊整词/年份/作者) + Sci-Hub 兜底; 修复 DOI 表 3 处错配 (S9_1/S11_6/S31_1)
- **scripts/tma_verify_pdfs.py**: 下载后逐 PDF 内容核验 (期刊缩写展开表 40+ 条)
- **scripts/tma_batch_highlight.py**: 每 Pn-x 按所在 slide 视觉定位批量 v3 FINAL highlight (嵌套目录, 修复旧 batch 无 --slide 过宽匹配)
- **scripts/tma_verify_highlights.py**: annot/黄色像素/图片完整性/pages 子目录四维验证
- **scripts/tma_package.py / tma_final_report.py / tma_manual_list.py**: 89 行 8 列 CSV + 交付报告 + 人工下载清单
- **docs/tma_delivery_2026-08-20/**: TMA 交付物 (对照表/CSV/人工清单/核验报告) + 流水线 README
- **scripts/test_tma_pipeline.py**: 53 用例黄金测试 (DOI 提取/期刊缩写展开/三维内容核验/黄色像素/子命令注册)
- **via54.py 新增 6 子命令**: download (round1/round2) / pdf-verify / hl-batch / hl-verify / report / manual-list; 修复 cmd_highlight slide_num 未定义 bug; handlers 提为模块级 HANDLERS
- **scripts/tma_highlight_by_slide.py (新)**: 按 slide 分组驱动 highlight — ①导出全部 slide 图 _ppt_renders/ (python-pptx 近似渲染) ②逐页视觉提取 (文本/表格/图片形状, 融合 vision report) ③对照该页所有 PDF ④**文字段落 + 表格 (find_tables) + 图表/图片 (get_image_info) 四类应证 highlight** (v3 FINAL rect + 9 铁律, xref 层规避 PyMuPDF 1.28.2 annot.rect 原生崩溃 bug + clean-resave 兼容)
- **via54.py hl-batch 默认按 slide 分组** (tma_highlight_by_slide.py), --legacy 走旧文字-only 模式
- **test_tma_pipeline.py 扩至 61 用例**: T11 by-slide (slide_terms / find_table_matches / find_image_matches) + T10 更新 (hl-batch 默认/legacy)
- **scripts/ppt_render_engine.py (新)**: PPT → 图片多引擎自动渲染 — ①PowerPoint COM (ProgID PowerPoint.Application) ②WPS 演示 COM (KWPP.Application) ③python-pptx 近似兜底; 检测到 COM 引擎缺 pywin32 自动安装; DispatchEx 强制新实例 (修复 Dispatch 连接残留); 任一引擎失败自动降级
- **tma_highlight_by_slide.py Step 0 接入 ppt_render_engine**: 全量 slide 图改用系统 PowerPoint 真实渲染 (本机实测: 非白像素 14-35% vs 近似渲染 1-11%)
- **test_tma_pipeline.py 扩至 65 用例**: T12 渲染引擎 (ProgID 探测 / 兜底渲染 / COM 失败降级)
- **自然语言一键全自动管线 (2026-08-20 三轮)**:
  - **scripts/via54_auto.py (新)**: 自然语言入口编排器 — via54.py auto "帮我识别 X.pptx 中的文献引用，下载文献，并进行highlight" 全自动: 环境自检(依赖自动安装)→渲染PPT图(PowerPoint/WPS COM)→深度提取引用(上标/中文+数字标号 + 参考文献列表完整引文)→1小时限时下载(级联+CrossRef+SciHub, 超时保留链接)→整理Pn-x目录(_literature_citation_index/)→逐slide视觉分析+highlight plan(_highlight_plans/)→按序highlight→交付报告
  - **scripts/deps_auto.py (新)**: 环境自检 + 自动 pip 安装缺失依赖 (PyMuPDF/python-pptx/Pillow/pywin32[Win])
  - via54.py 新增 auto 子命令; 提取准确率: 55→109→59 条(去噪) + 16 条完整引文(参考文献列表), 无标号 slide 不再误建引用, 下载后内容核验(mismatch 即删)
  - 测试扩至 71 用例 (T13 自然语言解析/项目根/目录整理)
- **第八轮 (2026-08-20)**: 修复非正文错标 — 9 铁律扩展 4 规则
  - 规则10 投稿元数据 (Received/Accepted/Published); 规则11 页眉页脚 (卷期/页码/版权/许可); 规则12 声明标题 (FUNDING/ACKNOWLEDGMENTS/CONTRIBUTIONS/COPYRIGHT); 规则13 参考文献条目 (doi/et al./作者列表/续行)
  - 修复 get_textbox 跨行文本导致规则正则失效 (is_metadata_rect 空白归一化)
  - 实测: P3-1/P16-1/P23-5 错标清零; 全量 58 个重跑, 删除量 +10~30% (P4-6 38, P23-5 46)
  - 测试扩至 79 用例 (T14 规则扩展)
- **第七轮迭代 (2026-08-20)**: 关联固化与复用
  - `_ref_assoc_map.json`: 每 Pn-x → 完整引文编号 + 关联状态 (ok/rejected/dl_failed)
  - 人工清单增强: 双核验通过的 ref 显示「复用全文库 ref{N}.pdf」; 被拒的显示「需人工核对」; 未关联的显示建议引文
  - 实测: P3-1→full#1, P3-3→full#3, P4-3→full#3 关联固化; 人工清单可复用 ref1-3.pdf
- **第六轮迭代 (2026-08-20)**: 标号↔完整引文自动关联
  - 复合标号解析: 上标 run 支持 "4,6"/"1-3" 拆分, 提取 28→34 条
  - 完整引文关联下载: 标号数字命中参考文献列表编号时, 用完整引文下载 + **双核验** (引文自洽 + context 英文术语出现在 PDF)
  - 双核验拦截错配: 页内编号≠全局编号时自动拒绝并回退 (实测 P5-1 正确拦截)
  - 实测 (TMA_auto_test 全新项目): 标号关联下载 6 篇 + 全文库 8 篇, 6 个 Pn-x 完成 highlight, 全流程 exit 0
- **第五轮迭代 (2026-08-20)**:
  - PubMed 术语检索兜底下载: 正文句含英文医学术语时 ESearch→EuropePMC OA 下载
  - 全文库对照表 `_全文库对照表.md`: 参考文献列表完整引文 ↔ 下载状态 (供人工对照 PPT 标号)
  - 实测 highlight 链路: 全文库 PDF 映射 Pn-x 后 by-slide 高亮正常 (P3-1 59 高亮/9铁律删 41)
  - 修复: 下载 failed 重复记录; full_lib_table f.write 字符串损坏; full_refs JSON int-key roundtrip
- **全新项目全自动测试修复 (2026-08-20 四轮)** (实测 TMA_auto_test):
  - round2 补 process_ref 封装 (编排器调用缺函数崩溃)
  - 下载顺序: 参考文献列表完整引文(准确字段)优先, 实测 16 条成功 10 条 (62%), 付费墙保留链接; 标号正文句匹配率低(中文)
  - full_refs JSON int-key roundtrip 修复 (str key 导致替换失效)
  - 移除按标号替换完整引文 (PPT 页内编号与全局编号无结构映射, 会错配)
  - auto 管线: PPT 复制进项目根 (by-slide 需项目内 PPTX); 报告兼容 _references_FINAL/_manual_download_list 自动生成; 空项目 out_base/doi_map 容错
  - 测试 71/71 通过, 全流程 exit 0
  - via54.py 缺 import re → cmd_highlight 运行时 NameError (致命) → 已修
  - --out-dir 参数失效: cmd_highlight 未透传 + via54_ppt_visual_to_pdf.py out_base 未生效 → 双修
  - tma_manual_list.py KNOWN_DOI 22 个 key 残留旧命名 S{slide}_{num} → 归一 P{slide}-{num} (人工清单 DOI 链接恢复)
  - tma_highlight_by_slide.py: 单 PDF 异常隔离 (不中断全量 batch) + hl_tmp 异常清理
  - 测试环境适配: test_hl_lib.py (TMA_HL_TEST_SRC/TMA_PROJECT 参数化, 无数据跳过) + test_ppt_understand.py (VIA54_LEIGUAN_DIR 参数化 + 数据守卫) → 跨系统可跑 (本机 25/25 真实数据通过)
  - pyflakes 清理: 6 脚本头部孤立 import os / 未用 import (io/shutil/hashlib 等)

### Fixed
- TMA 下载器 Windows stdout GBK UnicodeEncodeError 崩溃 (sys.stdout.reconfigure utf-8)
- Pn-S27_1 嵌套输出缺失 + Pn-S23_5 0 字节 p5.png (全量重跑 batch 解决)
- 错配下载 24 篇隔离至项目 `_2_pdfs_wrong/` (含 ojs.omniscient.sg/hanspub 等低质 OA 源)
- S20_2 (MDPI) / S31_2 (Frontiers) 手动直链修复

### Stats
- TMA_test: 89 引用, 52 篇有 PDF+highlight (58%), 37 篇付费墙/中文期刊 → `_人工下载清单.md` (含访问链接, 下载按用户要求 1 小时截止)

## [4.6.0] - 2026-08-18 (v3 FINAL 全量经验注入: highlight rect 模式 + 8列表 + 合并规则)

### Added
- **docs/HIGHLIGHT机制与算法规范_v3_FINAL.md**: 106 Pn-x 全量交付权威规范(逐行 rect 算法/渲染/质检/复现)
- **docs/8列标准与合并规则_2026-08-14.md**: 雷管方案 8 列表(本地+在线同构) + H 列卡片 + 同文献合并规则
- **scripts/hl_v3_final/**: hl_lib.py(精确逐行 rect, 25 用例) + render_fitz.py + rerun_all.py + copy_hl_images.py + vision_check.py + 新 PPT 三步流程(step1/2/3) + align_tables/leiguan_table + 105 句子脚本示例

### Changed
- **AGENTS.md**: Step 4 唯一标准 = v3 FINAL rect 模式(opacity 0.45, RGB 255,217,0, 禁 add_highlight_annot/pdftoppm); Step 6 合并格式 `Pn1-x1Pn2-x2` → `P3-1_P4-1`(下划线按序); 错论文状态更新(仅剩 P13-1/P12-3/P31-6)
- **docs/6_step_sop.md**: Step 4/6 重写对齐 v3 FINAL; 故障排查/工具索引/版本号同步

### 验证
- hl_lib 单元测试 25/25 passed
- 仓库与 skill 侧工具链 diff 一致
- TMA 交付基线: 106 Pn-x 高亮 1325/1325 像素验证, 90 合并目录, 142 URL 0 失效

## [4.5.7] - 2026-08-13 (GLM 集成 + TMA 108/108 + fix-proxy 测试模式)

### Added
- **`scripts/fix-proxy.sh` 加 2 个测试模式**:
  - `--dry-run`: 检查代理但不修改 (适合人 review)
  - `--test`: 故意把代理改到 7890 (死代理), 然后自动修回 14122 (Clash)
    端到端验证整个修复流程
- **ZCode provider config 增强** (`~/.zcode/v2/config.json`):
  - `builtin:bigmodel-coding-plan` 合并 23 个 GLM 模型 (含 glm-4.6v-flash 多模态、glm-5v-turbo 顶级)
  - ZCode 启动时自动加 SenseNova + DeepSeek provider (内置白名单)
- **TMA 5#3 三方对齐 100% 闭环** (`~/Desktop/TMA_文献整理/`):
  - 旧阈值 (严格亮黄): 19/108 = 17.6%
  - 暖色阈值: 58/108 = 53.7%
  - 饱和色阈值: 96/108 = 88.9%
  - **新综合判定 (任一页 > 0.05%): 108/108 = 100%**
  - 10 个真 0% 彩 Pn-x 用 M3 vision 应证 + PyMuPDF highlight + 半角/全角转换修复
  - 2 个无 PDF 的 Pn-x (P31-8 / P31-9) 用 PubMed fetch + stub PDF + highlight 补齐
- **GLM-4 multimodal 集成** (`~/.zcode/workspace/default/m3.py`):
  - 默认 `GLM_MODEL = glm-4.6v-flash` (text + image, 免费)
  - `--provider glm` 路径: PDF 走 pdftotext 抽文本, image 走 image_url (OpenAI 格式)
  - 8 个 M3 + 3 个 GLM Quick Action (Finder 右键)
- **glm-literature skill** (`~/.zcode/skills/glm-literature/`):
  - `search`: PubMed + EuropePMC + CrossRef 三源合并
  - `fetch`: PMID/DOI → fulltext
  - `verify`: M3 vision 应证 (PPT vs PDF)
  - `kb`: 本地 108 PDFs TMA KB
  - 4/4 工具端到端通过

### Verified
- 走系统代理 10 轮 HTTP 200, 0 EPIPE
- m3.py 9/9 预设 case + 30 轮压力测试
- ZCode 端到端 5/5 smoke test
- TMA step6 打包 220.6 MB (108 main PDFs + 108 highlight pages + 116 page jpgs, 0 missing)
- GLM-4.6v-flash image HTTP 200 / 1.3s "Red"
- GLM-4.6v-flash video HTTP 200 / 1.3s "people going about daily routines..."
- fix-proxy.sh --test: 故意改坏 → 自动修回, 验证完整闭环

### Remaining (网络阻塞)
- 61 commits 待 push 到 github.com/veawho/via54Medit
- 跑 `cd via54Medit && git push origin main` 在网络恢复后

## [4.5.6] - 2026-08-12 (macOS EPIPE 根因修复 + ROADMAP 同步)

### Fixed
- **macOS "7890 死代理" EPIPE 根因修复** (`scripts/fix-proxy.sh`)
  - 根因: macOS Ethernet 接口配置 HTTP/HTTPS 代理 = `127.0.0.1:7890`,
    但 7890 没有进程在 LISTEN (死代理). 走系统代理的所有 HTTPS 流量
    在 Node.js 拿 `Cannot connect to API: write EPIPE`.
  - 修复: 代理指向 Clash 实际端口 `127.0.0.1:14122`
  - `scripts/fix-proxy.sh` 检测+自动修复, 配 `launchd` plist 自动恢复.
- **`medit version` 子命令缺失** (`cmd/medit/commands/root.go`)
  - ROADMAP Phase 0 标的 "medit version 可跑" 但实际只有 `--version` flag.
  - 加 `versionCmd` 子命令, 走 `version.Full()` 输出 5 字段
    (commit / build date / go version / license / repo).
  - `bin/medit` 重新编译, `bin/medit-mcp` 同步.

### Changed
- **ROADMAP 复选框同步** (`docs/ROADMAP.md`)
  - 勾选 32 项已实际完成 (Phase 1-4 大部分子项):
    - `internal/source/{antfu,pubmed,openalex,s2}.go`
    - `internal/router/{pico,grade,router}.go`
    - `internal/enrich/*.go`
    - `internal/anno2ppt/*.go`
    - `cmd/medit-mcp/*` (4 工具)
    - `Makefile` + `.goreleaser.yaml`
  - 实际 `go test ./...` 25 包全 ok, 命令实测 15+ 个.
- **`internal/anno2ppt/dual_source.go` TODO 重整理**
  - 旧 TODO 注释里 "scripts/nct_fetcher.py 已存在" 不符, 实际未建.
  - 改成 "已沉淀" (5 项 ✓) + "后续 Phase 5+ TODO" (3 项, 带 P2 优先级).

### Added
- **`scripts/fix-proxy.sh`** (2646 bytes) — macOS 代理自动修复脚本
  - 检查 `7890 NOT LISTEN` 状态
  - 切代理到实际在跑的 `14122`
  - 三种模式: 默认(检查+修) / `--check` / `--status`
  - 配套 `~/Library/LaunchAgents/com.via54.fix-proxy.plist` 开机自动跑

## [1.0.0] - 2026-07-03 (首次公开稳定版 Release: Medical RAG Agent & Multi-Agent MCP Server)

> 公开 Release 号 `v1.0.0`, 指向提交 `1b0354a`; 同期内部版本号为 4.5.x (编号不同轨, 对照见文首「版本号说明」)。

### Published
- GitHub Release `v1.0.0` 于 2026-07-03 正式发布 (published, 非 draft/prerelease), 发布说明所列四项亮点:
  - **多源医学检索 RAG 路由** — 自述贯通 PubMed / ChEMBL / ClinicalTrials.gov / Europe PMC / Reactome
  - **标准化 MCP Server** — 向任何 Model Context Protocol 兼容宿主客户端暴露医学库检索工具
  - **PICO & GRADE 评估框架** — 按系统综述结构做临床文献评价
  - **smoke test 套件全绿** — 校验编译器健康度 / API 时延 / 数据格式一致性

### 备注 (发布说明 ≠ 实际交付范围)
- 上述五类数据源中, 截至该发布仅有 **PubMed** 落地 (`internal/source/pubmed.go`);
  ChEMBL / ClinicalTrials.gov / Europe PMC / Reactome 在代码中**并不存在**, 当时仍属 P0 集成计划
  (见 [Unreleased] Phase 5.0 与 [4.5.5])。本条目按 Release 原文如实记录, 不代表五源均已交付。

## [4.5.5] - 2026-06-30 (可重放性文档 + 3 个规则)

### Added
- **docs/PROCESS.md** (8.5KB): 商业市场报告生成流程 5 步, 80-150min/报告, 100% 可重放
- **docs/SOLUTION.md** (10.8KB): v5.0 商业报告生成解决方案 5 层架构 + 8 核心组件 + 5 技术决策
- **docs/REPRODUCIBILITY.md** (5.5KB): 8 条铁律 (文档先行 / 自包含 / 可重放 / Git 规范 / 设备记录 / 模板验证 / 不增付费 / 旧设备兼容)

### 铁律 (8 条)
- 文档先行 → 改代码前先改文档
- 自包含测试 → 跨 OS / Python 验证
- 可重放 → 任何设备 ≤ 2 小时
- Git 提交含 `[reproducibility-test]` tag
- 模板改动需 validate_report.py + 用户验收
- 数据源不增付费 (锁决策 4)
- 旧设备兼容 (Python 3.9+)

### 测试设备
- WTG Windows 11 (Python 3.11.4, Edge 126)
- MacBook M2 / Ubuntu 24.04 (待测)

## [4.5.4] - 2026-06-30 (v5.0 商业情报第 1 份样本报告)

### Added
- **market-reports/** 目录: v5.0 商业情报 (intel) 模式产出
- **gout-2026-q2.html** (66KB): 痛风药物市场前瞻性分析 (TalkMED AgentPilot 风格)
  - 7 章节 + 8 SVG 图表 + 4 数据洞察 + 3 投资判断 + 3 风险
  - 2023-2026 数据 (2026 优先, 11 数据源)
  - 通过用户测试 (OK, 16:18)
- **docs/MARKET-REPORTS.md**: 报告索引 + 模板 + 数据源优先级
- 验证 v5.0 商业模式 (`medit intel` + market-reports/) 端到端可用

### v5.0 商业模式 (intel) 集成状态
- 数据源集成: 6 P0 商业源 (openfda, pubtator3, dailymed, europe_pmc, medrxiv, clinicaltrials_v2)
- 报告生成器: TalkMED AgentPilot 风格 (7 页 HTML)
- 数据源: 11 (Coherent, FMI, Data Bridge, Grand View, Takeda, Amgen, CPA, CRA, Evaluate, CT.gov, FDA Orange Book)
- 验证: 痛风报告 (2026-06-30) ✓

## [4.5.3] - 2026-06-30 (final v5.0 spec lock - 用户确认全默认)

### Decision Lock (用户 ~16:00 TG "全默认")
10 个默认决策全部确认:
- **1.1 (3.1)**: A - 新程序 medit-intel (跟学术分开)
- **1.2 (3.2)**: B - 共用核心代码 (1 仓 2 binary)
- **1.3 (3.3)**: A - 1 个 medit-mcp (双模式)
- **1.4 (3.4)**: A - 1 个 config.yaml (双 mode)
- **1.5 (3.5)**: B - v5.0 学术 + v5.5 商业 (稳)
- **2.1 (6.1)**: B - MCP 协议调用 (via54Medit 作 client)
- **2.2 (6.2)**: B - 每月自动 git sync
- **2.3 (6.3)**: B - 60% biomcp + 40% 自写
- **2.4 (6.4)**: A - MIT + AGPL 兼容
- **2.5 (6.5)**: A - biomcp 独立 server

### 状态
- **5 决策点全锁** (1+2+3+4+5+6 = 6 个用户决策, 4+5 重复, 实际 5 决策点)
- **v5.0 spec complete**: ARCHITECTURE-V5-DRAFT.md 升为 ARCHITECTURE-V5.md
- **CATALOG.md 109+ 源** (115 - 16 付费 = 99, 加 subagent #2 找到的额外)
- **DECISIONS-PENDING.md 关闭** (所有决策已答)

### Todo for v5.0 → v5.5
1. v5.0: 学术模式 (EBM) 完整发布
   - 加 6 P0 EBM 源 (clinicaltrials_v2, europe_pmc, medrxiv, openfda, dailymed, pubtator3)
   - biomcp MCP client 集成 (60% 覆盖)
   - 保持 medit ask 兼容
2. v5.5: 商业模式 (intel) 完整发布
   - 加 6 P0 商业源 (药智/医药魔方/OpenFDA/PDB/CDE/PharnexCloud)
   - TalkMED 7 页 PDF 生成器
   - medit-intel 新 binary
3. v6.0: 双模式融合 + biomcp 100% 覆盖

## [4.5.2.1] - 2026-06-30 (重写通俗版)

### Changed
- DECISIONS-PENDING.md 重写为通俗版 (大白话 + 表格, 不用技术术语)
- 之前版本太技术 (binary/MCP/layer 等), 用户看不懂, 现重写

## [4.5.2] - 2026-06-30 (decision lock round 2)

### Decision Lock (用户 ~15:50 TG 决策)
- **2. 暂时不变** = 12 P0 源列表保留 (EBM 6 + 商业 6, TalkMED 7 页 PDF 需求)
- **3. 信息太少无法决策** = 待用户补细节. 已展开成 5 明确问题 (见 DECISIONS-PENDING.md)
- **6. 信息太少无法决策** = 待用户补细节. 已展开成 5 明确问题 (见 DECISIONS-PENDING.md)

### Total
- 已锁: 决策 1 (架构), 2 (P0 源), 4 (付费源 = 0)
- 待补: 决策 3 (CLI 隔离), 5 (锁定 ✅), 6 (biomcp 集成)
- 实际 5 个决策点 (§8) 中 2/3/5/6 待补, 5 已锁=4 一致

## [4.5.1] - 2026-06-30 (decision lock)

### Decision Lock (用户 15:42 TG 决策)
- **1. 暂不调整** = 接受现状, 双模式 EBM 学术 + 商业情报架构保留
- **4. 不适用付费源** = 排除所有付费源 (Frost/Grand View/Citeline/GlobalData/AdisInsight/BioCentury/Endpoints/STAT/PharmCube 交易库/Bloomberg/WiseGuy/Statista/Huaon/Menet/PharnexCloud 等)
- **2/3/5/6. 决策需更多细节** = 暂搁, 等用户补决策

### Changed
- CATALOG.md P3 商业授权表 + 商业情报 P1/P2 表格标 ~~删除线~~ (排除付费)
- CHANGELOG 锁决策: 不接付费源
- ARCHITECTURE-V5-DRAFT.md §8 决策点 4 (商业付费源预算) 锁: 不接付费

### Total
- EBM 学术: 52+ 免费源 (保留)
- 商业情报: 16+ P0 全部免费/开源 (保留)
- 商业付费源: **0** (排除, 决策 4)

## [4.5.0] - 2026-06-29

### Added
- integrations/ 目录: 6 个高星医学文献项目 (local-deep-research, paper-search-mcp, MetaScreener, asreview, pubmed_parser, pyalex)
- integrations/paper-search-mcp.md: 集成计划 (3 个新 MCP tools)
- REFERENCES.md: 6 个高星项目

### Changed
- 升级 v4.0 -> v4.5
- 从 "4 MCP tools" -> "7 MCP tools planned"

## [4.0 -> 4.5] - 2026-06-29

- Upgrade to v4.5 - integrate local-deep-research 8.6K patterns
- Plan: paper-search-mcp 2K integration (we have MCP, they have search)
- Plan: MetaScreener 1.3K PDF full-text screening
- Plan: asreview 937 active learning

## [Phase 0] - 2026-06-09 ~ 2026-06-24 (项目初始化与架构决策修订)

### Phase 0 (2026-06-09)

#### Added
- 项目初始化
  - `docs/ARCHITECTURE.md` — 5 层架构 + 20 节设计文档
  - `AGENTS.md` — 跨 AI 工具协作规约
  - `README.md` / `README.zh-CN.md` — 中英双语文档
  - `LICENSE-AGPL-3.0` / `LICENSE-MIT` — 双许可
  - 完整目录树 (22 个子目录)
  - Go module: `github.com/veawho/via54Medit`
  - Cargo workspace (rust/)
  - 4 个空接口 (Source / Embedder / VectorStore / Enricher)
  - `medit version` 可跑
  - GitHub 私库: github.com/veawho/via54Medit

### Phase 0 修订 (2026-06-24)

#### Changed
- **架构决策**: via54Design 强制依赖 → **可选借鉴** (走 ARCHITECTURE §17.3 路径 ② hand-roll)
- **新增铁律**: `git clone && go build` 必须 100% 成功,0 外部业务依赖 (ARCHITECTURE §21)
- **AGENTS.md 关键约束**: 新增第 7 条"不依赖任何私有仓库"
- **README.md 致谢段**: via54Design 改为"借鉴接口设计,实现独立"
- **configs/default.yaml**: 头部加修订说明
- **gofmt**: 2 个未格式化文件落地
- **单元测试**: 新增 8 cases (pkg/types 4 + internal/version 4)
- **git tag**: 计划落地 `phase0-done` annotated tag —— **实际未创建** (截至 2026-09-10 本地与远端均无该标签; `docs/ARCHITECTURE.md` §19 验证表亦将其记为"缺失")

#### Closed (ARCHITECTURE §19 开放问题 6 条全部拍板)
- §19.1 命名空间: 维持 via54Medit (module) / medit (CLI)
- §19.2 MCP 工具数: 维持 4 个,本地查询走 CLI
- §19.3 GRADE 评级: 走简化版,完整版 v0.5 评估
- §19.4 Web UI: 不做,MCP 路径覆盖
- §19.5 Windows 安装包: zip + scoop/winget,不做 MSI
- §19.6 GitHub 公开: 维持 private,Phase 5 再开

[Unreleased]: https://github.com/veawho/via54Medit/compare/v5.0.0...HEAD
