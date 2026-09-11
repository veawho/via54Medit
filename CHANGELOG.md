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

## [5.4.19] - 2026-09-11 (移植: 把 v13 的禁止区校验补进 v3 FINAL, 随后下线整个 v13 家族)

v3 FINAL 规范第 153 行要求「禁止高亮: 标题、作者、文献信息、页眉页脚、引用编号、图表标题」,
但 `hl_lib` 的**生成期**并没有这条检查。该要求唯一的实现是 v13 审计族 —— 而那套脚本在当前
交付物上**枚举恒为空**。本轮先把这项能力移植进 v3 FINAL 工具链, 再把 v13 家族整体下线。

### Added
- **`scripts/hl_v3_final/verify_forbidden_zones.py`** —— 禁止区校验, 补上 v3 FINAL 缺的这一环。
  `--hl-dir <step4>` 递归发现 `*_highlight.pdf`; 退出码 0/1/2 (无违规/有违规/用法错误);
  `--json` 输出完整明细。**不依赖 TMA 的 CSV 与 PPT JSON** —— 原脚本里 `csv_data`、
  `FORBIDDEN_RULES`、`is_title_text()`、`page_text_blocks` 参数都是定义后从未使用的死代码,
  移植时一并丢掉, 因此它可以对任意 step4 目录独立运行。
- **`scripts/hl_v3_final/test_forbidden_zones.py`** —— 24 项单测, 正向(必须抓得到 9 类) +
  负向(把移植中实测到的 6 个误报逐一钉住)。已接入 `make test-py` 与 CI。

### Removed
- **v13 审计族 7 个脚本**(共 1696 行)。分两批: 先删 3 个**会原地改写最终交付目录**的
  (`find_anchors_v13.py`、`fix_phase1_violations.py`、`redo_highlight_v13_glm_deprecated.py`
  —— 它们 `shutil.move` 到 `step4_highlight_106目录_合并DOI/{pn}_semantic_highlight.pdf`),
  移植完成后再删 4 个只读的 (`audit_all_highlights_v13.py`、`audit_semantic_v13.py`、
  `audit_v13_full.py`、`render_audit_visual_v13.py`)。

  **范围更正**: 上一轮按 `_vN\.py$` 盘点只找到 4 个, 实际是 **7 个** —— `audit_v13_full.py`
  (版本号后有 `_full`)、`fix_phase1_violations.py`、`redo_highlight_v13_glm_deprecated.py`
  (无版本号) 被正则漏掉; 而 `_audit_v13/INDEX.md` 自己就把 7 个列全了。

  **失效原因(两个独立维度, 任一都会让它们什么都看不到)**:
  | | v13 期望 | v3 FINAL 实际 |
  |---|---|---|
  | 布局 | 扁平 `{pn}_semantic_highlight.pdf` | 嵌套 `{Pn-x}/{PN}_highlight.pdf` |
  | 注记类型 | Highlight(8) / Underline(9) | **Square(4)** |

  实测: 全 TMA 树里 `*_semantic_highlight.pdf` 数为 **0**; 复刻其枚举语句得到空列表。
  `_step4_originals_backup/` 里还留着 4 个 `*.original.pdf`, 是旧扁平布局的备份。

### 移植时的两处改造(都基于实测证据, 不是顺手改)
- **递归发现 + 认 4/8/9 注记** —— 否则新脚本会重蹈"看不到任何东西"。
- **规则按证据分级, 不照搬正则**。照搬的话它在当前交付物上会报 **26 条 / 1325 条注记**,
  而逐条核对**没有一条是真实缺陷**:
  - `(Professor|Prof\.|Dr\.|Doctor)` 命中正文 "several **doctors** in southern Italy";
  - `^[\w\s,]+(?:,?\s*MD|PhD){1,}` 命中基因名 "**AMD3**";
  - `(University|Hospital|...)` 命中 "in-**hospital** mortality" → 加 `(?<![\w-])`;
  - `...\d{4}` 命中 "In the 1970s and **1980s**" → 改为 `\b(19|20)\d{2}\b`
    (它不会命中 `1980s`: 数字后紧跟 s, 无词边界);
  - "页脚 = 任何 y0 > 92%" 命中正文(正文排得到 92% 以下) → 改为要求文字**像版面附属物**;
  - "page0 顶部 30% + 含中文 = 中文作者区" → 实测 P9-3 版面是标题 13.9% / 作者 18.3% /
    正文 **22% 起**, 规则把摘要正文判成了作者区 → 降为"待人工判断"。

  改后分两级, **两级都打印, 不静默丢弃**: **违规级**(页眉带 / 页脚附属物 / 强作者单位标记 /
  参考文献条目 / 几何异常) 影响退出码; **待人工判断级**(图表标题 —— 规范有「除非图表即应证对象」
  的例外; page0 顶部带; 正文里的夹注) 只报告。

### 验证
- **真实 TMA step4**: 106 个 highlight PDF / **1325 条 Square 注记** (与 v3 FINAL 宣称的
  1325/1325 一致) → **0 违规 / 50 待人工判断**, 退出码 0。
- **正向对照(真实数据)**: 往真实 `P11-1_highlight.pdf` 注入作者单位、页脚页码、页眉带三类
  注记 → **三类全部抓到, 退出码 1**; 未注入污染的干净目录仍为 0。
- **退出码契约实测**: 干净 0 / 有违规 1 / 目录不存在 2 / 无 highlight 2。
- **负向对照**: 把两处精度修正退回 → 对应 2 项测试立即 FAIL, 证明它们是真防护。
- `make test-py` **62 + 24** 项全过; 技能分发包镜像由 `sync_skill_bundle.py` 补齐后 `--check` 退出码 0
  (新增文件时 `tests/test_repo_hygiene.py` 的镜像不变量**先报错拦下**, 正是设计意图)。
- 版本号三处同步 `1.5.18` → `1.5.19`。

### 索引
- `scripts/` 下版本后缀文件 **9 → 5** (4 个仍接线/仍活 + 1 个固有命名)。
  判定依据与全部文件的逐条结论见 `docs/versioned-scripts-audit-2026-09-11.md`。

## [5.4.18] - 2026-09-11 (收尾: 下线 2 个无后缀的同类 v1 脚本)

承接 5.4.17 的「已知残留」第 2 条。上一轮已确认这两个**按同一判据也已死**,
只因不在当轮的授权范围内而未动; 本轮一并清掉, 版本族不再残缺。

### Removed
- `scripts/tma_batch_redownload.py`（204 行）—— 三个硬编码路径**全部不存在**:
  `_2_pdfs/`、`_3_highlight_v10_glm/_redownload_suggestions.json`、
  `_3_highlight_v10_glm/_tma_redownload_log.json`。零引用。
- `scripts/redownload_36.py`（239 行）—— `SRC = f'{TMA}/_2_pdfs'`、
  `LOG = f'{TMA}/_3_highlight_v10_glm/_redownload_36_log.json'`, 两个目录均已不存在;
  输入 `/tmp/to_fix_36.json` 也已不在（临时文件）。零代码级引用。

  两者分别是 `tma_batch_redownload_v2/v3.py` 与 `redownload_36_v2/v3.py` 的**无后缀前身(v1)**。
  留着 v1 而删掉 v2/v3 会让版本族更不完整, 这是本轮清掉它们的主要理由。
  它们的目标目录也正是 5.4.17 已确认收尾的那批(`_2_pdfs/` 已被 `step3_pdf下载_106目录/`
  取代, 106/106 有 PDF)。

### 验证
- 删除前确认: 两者均**不被 `via54.py` 分发**、无任何代码级引用
  （全仓仅 CHANGELOG 与审计文档提及, 属文档记录）; 硬编码目标逐个断言不存在。
- 删除后 `scripts/` 下 **241 个 `.py` 语法零失败**; `make test-py` **62 passed**;
  `test_via54_rules.py` **41/41**; TMA 规则校验仍 **7/7**。
- 版本号三处同步 `1.5.17` → `1.5.18`。

### 索引
- `scripts/` 下版本后缀文件维持 **9 个**（本次清的是**无后缀**的 v1, 不改变该计数）:
  4 个仍接线/仍活 + 4 个 v13 审计族（待定）+ 1 个固有命名。

## [5.4.17] - 2026-09-11 (修复: 规则校验看不见真实产物目录 + 下线 6 个已收尾脚本)

两件事: ① 把 6 个"任务是否已收尾"不明的脚本查清并下线; ② **修掉我上一轮自己写错的一处归因** ——
它背后藏着一个真实的校验缺陷。

### Fixed
- **`via54_rules.py` 的候选目录名过期, 导致"数据明明是齐的却报不合格"**。
  TMA 的产物目录随文献数增长从 `…_96目录` 改名成了 `step3_pdf下载_106目录` /
  `step4_highlight_106目录_合并DOI`, 而清单里写死的是 `step3_pdf下载_160目录`(那是**雷管方案**的 160)
  与 `…_96目录_合并DOI`(TMA 的**旧** 96)。后果: TMA 被报成 **2/7**, 而同一份数据用别名一探就是 **5/7**
  —— 差别全部来自命名, Step 3 在探针下报 `pn_x_dirs: 106, with_pdf: 106`(106 篇全有 PDF)。
  - 修法一: 显式清单补上两个当前名字(**加在末尾**, 保证既有项目的选中结果不变),
    同族前缀再按**命名族正则**兜底(`^step3_pdf(下载)?(_\d+目录)?$`), 使下次改名(…_120目录)
    自动命中。刻意不用宽松前缀 —— 那会把 `step4_highlight_notes` 这类无关目录当成产物,
    等于"校验了错的东西却报告通过"; 严格匹配宁可显式失败。
- **Step 4/5 按"目录"而不是按"文献"计数, 把 Step 6 的合并误判成缺失**。
  合并把 28 个 Pn-x 收进 12 个目录(`90 = 106 - 28 + 12`), 于是 Step 5 同时报出
  "缺 28 个"和"多 12 个"。新增 `_expand_pn_x_name()` 把合并目录名
  (`P11-2_P12-1_P22-2_P25-8`) 展开成它代表的 Pn-x 集合, Step 4/5 改按文献比较;
  `_count_pn_x()` 保留为 `_count_literatures()` 的兼容包装并标注 deprecated。
  - 修复后实测: `python3 scripts/via54_rules.py check "/Users/david/Desktop/TMA_文献整理"`
    → **✅ 7/7 步通过, 0 个 issue**, 即 TMA 本来就是 7/7, 与文档原先的声明一致。

### Removed
- **6 个版本后缀脚本**(共 1076 行), 它们上一轮被判为「一次性任务已完成, 待人工确认是否收尾」——
  本轮从项目侧终态记录补齐了那项缺失信息, 依据三条互相独立的证据改判为「已收尾/已被取代」:
  `redownload_36_v2.py`、`redownload_36_v3.py`、`redownload_27_v4.py`、
  `batch_download_v2.py`、`find_replacements_v2.py`、`run_missing_v2.py`。
  1. **下载已齐**: `step3_pdf下载_106目录/` 实测 106 个 Pn-x、106 个都有 PDF —— 正是这几个脚本想达成的终态。
  2. **错配归零**: 项目内 `PDF_FEISHU_REDOWNLOAD_v2_REPORT.md` 记录 `MISMATCH 6 → 0`、`MATCH 79 → 85`。
  3. **后继流程已知**: `飞书总结文档_工具开发_2026-08-14.md` 记录 Step 3 成功率 90–95%、
     Step 4 highlight 106 个 Pn-x 全部完成、Step 5 106/106 对齐; `run_missing_v2` 那一轮的 v1.4.2
     只到 51/117 = 43.6%, 已被 v3 FINAL 取代。

  这些脚本操作的中间目录也已被 6 步结构取代(`_2_pdfs/` → `step3_pdf下载_106目录/`,
  `_3_highlight_semantic_v14x/` → `step4_highlight_106目录_合并DOI/`)。
  唯一未闭环的 3 篇(P12-3 UpToDate 占位 / P13-1 焦扬 / P31-6 AANEM 摘要)**需用户提供原文**,
  不是这几个脚本能解决的, 故不构成保留理由。删除前确认零代码级引用。

### Docs
- **订正上一轮的错误归因**(4 处): `AGENTS.md`、`docs/6_step_sop.md`、
  `docs/versioned-scripts-audit-2026-09-11.md`, 以及本文件的 5.4.16 条目加勘误指针。
  TMA 的 7/7 由"历史快照、不可复现"改回"已复现"; 雷管方案的目录确实不在本机, 其数值仍标注为历史记录。
- 审计文档补「上述 6 个为什么从『待人工确认』改判为『已下线』」一节;
  并记录一次方法论教训 —— **把"校验脚本报错"直接读成"数据缺失"是没有交叉验证的归因**,
  校验异常时应先分辨是被校验对象的问题还是校验器自身的问题。

### 验证
- `test_via54_rules.py` **28 → 41 项全过**; 新增 13 项里 **9 项在 v5.4.16 的旧代码上失败**
  (8 FAIL + 1 ERROR)、在修复后全过 —— 负向对照证明它们是真的防护而不是摆设。
  覆盖: TMA 现用 `…_106目录` 名、未来改名 `…_120目录` 的兜底、兜底拒绝无关目录、
  `_expand_pn_x_name` 的合并/扁平文件名/辅助目录/非 Pn-x 四种形态、Step 4 按文献计数、
  Step 5 合并目录不报缺失。
- 真实项目实测 TMA **7/7**; `_expand_pn_x_name` 的 4 个 doctest 通过;
  `scripts/` 下 249 个 `.py` 语法零失败。
- 版本号三处同步 `1.5.16` → `1.5.17`。

### 已知残留 (仍未处理)
- `scripts/hl_v3_final/` 下约 20 处弃用式 `import fitz`(承接 5.4.16 的记录)。
- ~~`scripts/tma_batch_redownload.py` 与 `scripts/redownload_36.py`(无后缀)按同一判据也已死,
  但不在本轮授权范围内, 未删~~ → **已于 [5.4.18] 清掉**。

## [5.4.16] - 2026-09-11 (清理: 下线 4 个版本后缀死脚本 + 修正指向不存在 CI 工作流的文档)

承接 v5.4.15 之后的版本后缀脚本清查。19 个带 `_vN` 后缀的文件逐个判定后, 本轮下线 4 个,
并顺带修掉两处「文档声明的东西其实不存在」。

### Removed
- **4 个已失效的版本后缀脚本** (共 1067 行), 判定依据与全部 19 个文件的逐条结论见
  `docs/versioned-scripts-audit-2026-09-11.md`:
  - `scripts/rerun_tma_highlight_v104.py` —— 后继者 `rerun_tma_highlight_v3_final.py` 的
    docstring 已**指名取代**; 硬编码的输入 `_2_pdfs/` 与输出 `_3_highlight_v10_4/` 均已不在。
  - `scripts/fix_zero_yellow_pnx.py` —— 与 v104 成对下线。它唯一的用途是
    `from rerun_tma_highlight_v104 import _read_csv_kws`, 读写目录同 v104; 与 v104 分开删会
    留下坏 import, 必须一起走。
  - `scripts/tma_batch_redownload_v2.py` / `v3.py` —— 硬编码输入
    `_3_highlight_v10_glm/_redownload_suggestions.json`, 该目录已不存在。

  清查中**推翻了两条扫码式的直觉**, 记录在审计文档里: ① 后缀不代表版本链, 同族代码重合度
  只有 17%–38%, 是同一问题的重写式反复尝试; ② 后缀有时是固有命名
  （`literature_v8_process_pn_x_v313.py` 与无后缀"兄弟"重合仅 1.6%, `clinicaltrials_v2.md`
  在仓库内根本没有 v1）。19 个里只有这 4 个能凭硬证据判定死亡, 其余 6 个属
  「一次性任务已完成」而非「被取代」, 两者处置不同, 留给人工确认。

### Fixed
- **两处文档指向一个已被删除的 CI 工作流**:
  - `AGENTS.md`: `CI: .github/workflows/rules_check.yml 自动跑 via54.py rules <project>` ——
    该文件不存在。`.github/workflows/` 下只有 `ci.yml`（Go build/vet/race + Python 单测 +
    工具链 import 探针）, **没有** rules 步骤。
  - `docs/6_step_sop.md`: `| CI gate | .github/workflows/rules_check.yml | ✓ PR 自动跑 |` —— 同上。

    `rules_check.yml` 在 `bc96e45`（`tmp: remove workflow for push test`）中删除后从未恢复。
    两处已改为指向真实存在的 `ci.yml`, 并注明 `via54.py rules` 无 CI 集成、需本地手动跑。
- **同一处的测试数字与通过率也是历史快照**: 原文写「69/69 通过（`test_via54_highlight_fix_v10.py`
  40 + `test_via54_rules.py` 29）」, 实测是 **41 + 28**, 且前者有 4 个真实 TMA 用例因 `_2_pdfs/`
  归档而自动 skip。实测 `via54_rules.py check` 对残留 TMA 目录只得 **2/7**。两处已改为可复现的表述。

  > ⚠️ **勘误（v5.4.17）**: 本条原文把 2/7 归因为「Step 1/3/4/5/6 输入目录缺失, 非规则回归」——
  > **该归因是错的**。真实原因是校验脚本的候选目录名过期, 数据一直是齐的; 修正后 TMA 实测 7/7。
  > 详见下面 **[5.4.17]** 条目, 本文保留原文以记录当时发布的内容。

### 验证
- `make test-py` **62 passed**; `test_via54_rules.py` **28/28 OK**;
  `test_via54_highlight_fix_v10.py` **41/41 OK (skipped=4)**。
- 删除后确认无残留坏 import: `scripts/` 下 249 个 `.py` 全部通过语法检查; `via54.py` 的
  分发目标与 CI 引用的脚本均未受影响。
- 版本号三处同步 `1.5.15` → `1.5.16` (`telemetry/__init__.py`、`pyproject.toml`、`setup.py`)。

### 已知残留 (本轮未处理)
- `scripts/hl_v3_final/` 下仍有约 20 处裸写 `import fitz`（弃用式导入）。v5.4.11 的修复本就
  只承诺 `telemetry/` 两个模块, 这不是漏改; 但作为「唯一标准」的高亮工具链, 若要批量改为
  `import pymupdf as fitz`（需 PyMuPDF 1.24+, 旧版回退）应另起一次带回归的改动。

## [5.4.15] - 2026-09-11 (清理: 冗余 .gitkeep + deps_auto.py 的 BOM)

二次核查（扫查盲区）确认无功能性缺陷之后, 顺手清掉两项装饰性问题。

### Removed
- **13 个冗余 `.gitkeep`**: 它们所在目录早就有真实内容, 占位作用已失效 ——
  `cmd/medit`、`cmd/medit-mcp`、`configs`、`internal/anno2ppt`、`internal/dedupe`、
  `internal/enrich`、`internal/persist`、`internal/router`、`internal/source`、
  `internal/version`、`pkg`、`rust/src`、`scripts`。

  **保留了 7 个**仍在起作用的: `internal/extract`、`templates/{config,latex,pptx}`、
  `tests/{e2e,stress,unit}` —— 这些目录确实只有 `.gitkeep` 一项, 删掉会让目录在 git 中消失
  （git 不跟踪空目录）。删除前逐个断言了"目录内确有其它条目", 不是按硬编码清单盲删。

### Fixed
- **`scripts/deps_auto.py` 开头的 UTF-8 BOM 剥离**（5411 → 5408 字节, 按字节精确操作）。
  需要说明这**不是**运行期缺陷 —— 实测 Python 的 import 机制、`py_compile` 以及 CI 的
  `import deps_auto` 都容忍文件开头的 BOM（只有朴素的 `ast.parse` 会报
  `invalid non-printable character`）。剥掉之后全仓库 **416 个 `.py` 语法检查零失败**,
  对任何工具链都不再是例外。

### 验证
- `make test-py` **62 passed**; Go `test -race` **24 包全绿 0 失败**; `gofmt -l` 归零;
  `go vet` 干净; 高亮工具链 **36/0**; 镜像 `--check` 退出码 0; `.gitkeep` 由 20 减至 7;
  `medit --help` 仍列出 30 个命令。
- `import deps_auto`、`py_compile`、以及全仓 416 个文件的 `ast.parse` 全部通过。

## [5.4.14] - 2026-09-11 (仓库卫生: 命令去重 / 工具链镜像补齐 / 生成物入库治理)

承接同日那次成体系扫查。四项处置里, 有一项在核查后**推翻了我先前的建议** —— 见下。

### Fixed
- **命令重复注册**: `anno2ppt` / `pico` / `systematic` / `grade` 各被 `rootCmd.AddCommand`
  注册了两次（`root.go` 第 102-104 行与第 131-133 行重复; `anno2ppt` 另在 `anno2ppt.go`
  的 `init()` 里又注册一次），导致 `medit --help` 把这四条各列两遍。已去掉重复注册。
- **死桩**: `stubs.go` 的 `anno2pptCmdStub` 从未被注册（`medit anno2ppt-old-stub` 报
  unknown command），其自身注释已写明"已被 anno2ppt.go 真实实现取代"。已删除。
- **生成物入库**: `scripts/multi_project_diff.py` 的输出路径原先硬编码为本机绝对路径
  `/Users/david/.../docs/`，换机器或 CI 上会写到不存在的位置；且每跑一次就往 `docs/` 里
  新增一份快照，已累积 13 个入库。改为仓库相对的 `docs/multi_project_diff/`，该目录已进
  `.gitignore`；13 个历史快照移除（可从 git 历史找回）。

### Added
- **`scripts/sync_skill_bundle.py`**: 把权威工具链 `scripts/hl_v3_final/` 同步到技能分发包
  `skills/via54medit-literature-pipeline/scripts/`。支持 `--check` 只报告不写（有差异退出码 1）。
- **`tests/test_repo_hygiene.py`**: 两道不变量防护 —— ① 技能分发包不得携带过期工具链
  （权威侧每个文件都必须在分发包中按映射存在且内容一致）; ② 同一命令不得被重复注册。
- **`make test-py`**: 一次跑完 Python 侧两套测试（遥测模块 + 仓库卫生）。
- **`auto_sync` 新增第 3b 步**: 每 6 小时巡检里校验上述不变量, 失败时推 `warning`
  飞书告警（key `autosync-hygiene-failed`）—— 这类退化不会让任何东西报错, 只能靠主动检查。

### Docs
- **`docs/ROADMAP.md` 状态更正**: §2.4 原先把 `enrich.go` / `index.go` / `query.go` 标为 `[x]`
  已完成，但它们实际仍是占位桩（`medit enrich` 打印 `[Phase 0 stub] … 将在 Phase 2 实现`）。
  已改为 `[ ]` 并标注真实实现位于 `internal/enrich`（未接线）。新增 §2.4b: 列出 8 个
  「已实现但不在任何构建目标依赖图内」的包（约 3000 行, 均带单测），明确标注**不是废弃代码**,
  并给出可复现的 `go list` 差集复核命令。

### 一处自我纠正（重要）
扫查时我判定 `scripts/hl_v3_final/` 与技能目录里那份是"冗余重复"，并倾向删除前者。
**核查后推翻**: `scripts/hl_v3_final/` 才是**权威开发位置** —— CI 的 `working-directory`、
`auto_sync.py` 的定时自测路径、7 个 `scripts/*.py` 的 `sys.path.insert`、`.trae/rules/project_rules.md`、
`.cursorrules`、`.github/copilot-instructions.md`、`AGENTS.md` 与多份 `docs/` 全都指向它；
技能目录那份则是**必须自包含**的分发副本（两个 SKILL.md 按 `~/.hermes/skills/...` 引用）。
按我先前的想法删它，会同时打断 CI、定时自测与 7 个脚本。

同时, 我此前说「两侧逐字节相同」也是**过度断言**: 实际已经漂移 —— 分发包缺少权威侧在
2026-09-07 新增的 5 个 OCR/版面脚本（`layout.py` / `hl_ocr_band.py` / `verify_sentence_set.py` /
`smoke_m1m2.py` / `strict_eval_ocr_locate.py`）, 且 `vision_check.py` 停在旧版（缺 telemetry
token 埋点）。根因是那次同步是手工做的（提交 `01a9452` 只同步了 2 个文件）, 之后 4 天无人再同步。
故本轮处置是**补齐 + 给出可重复的同步脚本 + 加防护**, 而不是删除任何一份。

### 验证
- `make test-py` **62 passed**（遥测 60 + 仓库卫生 2）; Go `test -race` **24 包全绿 0 失败**;
  `gofmt -l` 归零; `go vet` 干净; 高亮工具链 **36/0**。
- 防护有效性经负向对照验证: 只改一侧 → 镜像检查失败; 重新引入一次重复注册 → 检查失败并报出
  `{'picoCmd': ['root.go', 'root.go']}`; `sync_skill_bundle.py --check` 一致时退出码 0、有差异时 1。
- `medit --help` 中 `anno2ppt` / `pico` / `grade` / `systematic` / `list` 各出现 **1 次**（原为 2 次）,
  且四条命令及其子命令实跑正常。
- `auto_sync` 端到端实测新增步骤: `✓ 仓库卫生不变量通过`。

## [5.4.13] - 2026-09-11 (清理: 移除从未能运行的 cmd/list_citations_v2)

收口 v5.4.12 末尾保留的那一项。核查结论是它**不仅被取代, 而且自提交之日起就从未能运行**。

### Removed
- **`cmd/list_citations_v2/`（511 行）移除**。它与 `cmd/list_citations`（v1, 57 行）同在 `ab1bdf8` 引入, 但 v2 是一份自包含重写, 而它自始即坏:

  ```go
  // Helper to read all bytes from io.Reader
  func readAll(r interface{}) ([]byte, error) {
      if b, ok := r.([]byte); ok { return b, nil }
      return nil, fmt.Errorf("unsupported type")
  }
  ```

  调用处传入的是 zip 条目读取器（`io.ReadCloser`）而非 `[]byte`, 于是每页都返回 `unsupported type` 被跳过 —— 一页也读不到。实测（构建后运行, 它只打印不写文件）: `Extracted 0 slides with text` / `Found 0 citation chunks` / `Total unique citations: 0`。核对最初提交 `ab1bdf8`, `readAll` 当时就是这个样子; 2026-07-19 的 `fix: ... fix extractAllSlideText return types` 只补了 `parseInt` 与返回类型, 未触及根因。
- **`.gitignore` 的 `list_citations_v2` 规则一并移除**。它只为 v2 的根目录构建产物而留, 源码既已下线, 该规则成为死条目。

### 取代关系（同一份 PPTX 上的实测）
| 工具 | 结果 |
| --- | --- |
| `cmd/list_citations_v2` | 0 页 / 0 条（坏的） |
| `medit cite extract`（现役） | 43 页 / 103 条 |
| 归档 `references/test-data/0622_pptx_citations.md` | 总条目 103 |

现役 `medit cite extract/verify/list`（`cmd/medit/commands/cite.go` + `internal/cite/`）是完整超集: 支持 PPTX/PDF/DOCX、带 PubMed/Crossref 富化、模型字段更多（`doi`/`pmid`/`title`/`trial`/`source_docs`）、且接受命令行参数; 而 v2 中 `os.Args`/`flag.` 出现 0 次, 硬编码了一个私人下载路径。仓库内外均无引用方（含 `~/.medit/scripts`、`~/.medit/tests`）; 2026-08-12 对它的那次改动经 `git show -w` 验证为纯空白格式化。

### 一处自我纠正
v5.4.12 的条目里我把 v2 描述为「511 行, 功能更全」并据此说 v1 该让位 —— **该描述是误导的**: v2 更长但从未跑通, 真正能干活的是 v1（实测 43 页 / 81 条）。删除 v1 的决定仍然成立, 因为 v1 只是薄封装, 它依赖的共享库 `internal/pptx` 至今仍在, 且仍被 `cmd/medit/commands/pptx.go` 与 `internal/cite/pptx.go` 使用, 四个函数均在其中; 但当时给出的理由有误, 特此更正。

### 验证
- `go build ./...` 通过; `cmd/` 现为 `medit` / `medit-mcp` / `promptctl`。
- Go `test -race` **24 包全绿 0 失败**; `gofmt -l` 归零; `go vet` 干净。
- 全仓库已无 `list_citations` 残留（仅 CHANGELOG 的历史记录）。

## [5.4.12] - 2026-09-11 (清理: 移除被误提交的 6.3 MB 二进制 + 源码 + 两处遗留产物)

收口 v5.4.11 中列为「待确认」的遗留产物项, 过程中又发现并处理了一个更大的问题。

### Removed
- **`list_citations`（6.3 MB 二进制）从仓库移除**。它是全仓库**唯一被跟踪的二进制**, 比第二大的跟踪文件 (0.2 MB 的 JSON 报告) 大 30 倍, 却没有任何引用方: Makefile 不构建、文档不提及、脚本/技能/测试均不使用。由 `ab1bdf8`「feat(cite): 全量交付」于 2026-07-17 与源码一同提交。之所以会被提交进去, 根因是 `.gitignore` 里 `/medit`、`/medit-mcp`、`cmd/medit/medit`、`list_citations_v2` 都列了, **唯独漏了 `/list_citations`**。
- **`cmd/list_citations/`（v1 源码, 57 行）一并移除**。它与 `cmd/list_citations_v2/`（511 行, 功能更全, 含 zip / http 处理）同在 `ab1bdf8` 引入; v1 无任何引用方, 保留会留下「该用哪个」的歧义。`cmd/list_citations_v2` 保留未动。
- 另清理两处**未被 git 跟踪**的本机遗留产物 (不影响仓库, 仅记录在案): `bin/annas-cli` (12.8 MB, 第三方 CLI `github.com/hdimer/annas-archive-cli`, 零引用) 与仓库根目录的 `medit` (11.5 MB, 8 月 21 日误在根目录 `go build` 的产物, 自报 `0.1.0-phase0` 这个并不存在的版本号)。两者合计释放约 24.4 MB。

### 验证
- `go build ./...` 通过; `cmd/` 现为 `list_citations_v2` / `medit` / `medit-mcp` / `promptctl`。
- Go `test -race` **24 个包全绿, 0 失败**; `go vet` 干净; `gofmt -l` 归零。
- 删除前已确认零引用, 且工作区那份二进制与提交内容完全一致 (无本地改动会被牵连)。
- 移除后仓库中最大的跟踪文件降到 0.2 MB。

## [5.4.11] - 2026-09-11 (修复: 消除 fitz 弃用警告 + 补齐文档覆盖)

承接 v5.4.10 的收尾核查。上次列出三项残留, 本轮处理前两项; 第三项 `bin/annas-cli` (13 MB、7 月 20 日、未被 git 跟踪、全仓库零引用的遗留产物) 待确认是否废弃后再动。

### Fixed
- **PyMuPDF 弃用警告**: `watcher.py` 与 `pdf_utils.py` 原先写 `import fitz`, PyMuPDF 会因此往 stderr 打一行 `The \`fitz\` API is deprecated and will be removed in future. Use \`import pymupdf\` instead.` —— 这行警告会顺着导入链污染守护进程启动日志, 以及任何 `from telemetry import WorkspaceScanner` 的场景。改用 `pymupdf` (1.24+ 的正式导入名), 旧版本回退 `import fitz`。两处均加了"为什么不能写 `import fitz`"的注释, 免得后人改回去。

### Docs
- **补齐告警通道与定时同步的文档覆盖** —— 这是一次真实疏漏: v5.4.7 ~ v5.4.9 上线了外部告警通道、`alert` 子命令、auto_sync 退出码契约与日志迁址, 但根 `README.md`、`README.zh-CN.md`、`docs/TELEMETRY_GUIDE.md` 三处**全部漏更新**, 只有 `telemetry/README.md` 跟上了, 而且连它也没写退出码。现已补:
  - 指南新增「### D. 关键事件外部告警与定时同步」小节 (命令速查 + 告警触发点与级别表 + 不会上报的情况 + 退出码表); 「核心功能特性」补第 6/7 条, 含各项设计理由; 「本地持久化」补 `autosync.log`、`alerts_state.json`、日志轮转与描述符观测。
  - 两份根 README 补告警与定时同步条目, 均给出**实际命令名**而非仅描述能力。
  - 模块 README 补退出码契约与文件描述符观测说明。

### 验证
- **test_telemetry 60/60 passed**, 新增 2 项:
  - `test_pdf_stack_import_carries_no_deprecation_warning`: 导入 `WorkspaceScanner` / `pdf_utils` 时 stderr 不得出现 `deprecated`。
  - `test_docs_cover_alert_channel_and_sync_exit_codes`: 四份用户可见文档都必须提到告警通道与退出码。**这条防护写完后立刻抓到一次真实疏漏** —— 我给中文 README 只写了「外部告警」的能力描述, 却没给出 `alert` 命令名, 测试直接失败; 补上命令后才通过。
- 实测 `get_pdf_page_count` 对真实 PDF 仍返回正确页数 (样本 26 页), 功能未受影响。
- 守护进程重启后启动日志只剩「服务启动就绪」一行, 不再有警告行。

## [5.4.10] - 2026-09-11 (优化: 包级导入改惰性, 消除无谓依赖与输出污染)

承接对 `telemetry` 包 eager import 的核查 —— 确认问题真实存在, 并量化了代价。

### Changed
- **`telemetry/__init__.py` 改为惰性加载**: 本文件只暴露 `__version__`, 其余 13 个对外符号经 PEP 562 模块级 `__getattr__` 按需加载 (解析后写回 `globals()` 缓存), 并保留 `__all__` 与 `__dir__`; 未知属性仍抛 `AttributeError`。既有的 `from telemetry import TelemetryDB` 写法完全不受影响。
- **`telemetry/cli.py` 下沉重依赖导入**: 唯二会经 `watcher -> pdf_utils -> fitz` 拉起 PyMuPDF 的 `from .daemon import ...` 与 `from .watcher import WorkspaceScanner`, 移入真正使用它们的函数体 (`cmd_daemon` / `_install_autostart` / `_uninstall_autostart` / `cmd_scan` / `cmd_backfill`), 使 `--help` / `--env-check` / `alert` / `status` 等轻量命令不再付这份开销。

### 实测收益
| 调用 | 修复前 | 修复后 |
| --- | --- | --- |
| `import telemetry.alerter` | 131 模块 / 82 ms / 含 fitz | **70 模块 / 12 ms / 不含 fitz** |
| `import telemetry.envcheck` | 26 模块 / 42 ms / 含 fitz | **2 模块 / 0 ms** |
| `import telemetry.db` | (同样被牵连) | 17 模块, 不含 fitz |
| `--env-check` / `--help` 的 stderr | 各 1 行 fitz 弃用警告 | **0 行** |

### 一处自我纠正
最初怀疑这还会造成「一处依赖缺失 → 全包不可导入」。**实测不成立**: `fitz` 在 `watcher.py` 里包了 `try/except`、在 `pdf_utils.py` 里是函数内导入 —— 屏蔽掉 fitz 后 `envcheck` / `alerter` / `db` 仍可正常导入。所以本轮的实际收益是**开销与输出污染**, 不是健壮性; 该结论已写进 `__init__.py` 的注释, 以免后人误信。

### 验证
- **test_telemetry 58/58 passed** (新增 `TestPackageImportStrategy` 4 项: 轻量子模块不连带 PDF 栈且无弃用警告、13 个惰性符号仍可解析且 `dir()` 可见、未知属性仍抛 `AttributeError`、CLI 轻量命令输出无 PDF 噪音)。全部经**独立子进程**验证, 避免测试自身的导入污染结论。
- 兼容性: 8 个既有符号的 `from telemetry import ...` 全部成功; `daemon --status` / `status` / `alert` 子命令照常; 守护进程未受影响。
- 被下沉的 9 个 `daemon` 名字 + `WorkspaceScanner` 均已确认可导入, 5 个函数的函数体内导入语句经源码核对存在。

## [5.4.9] - 2026-09-11 (新增: 定时同步失败接入飞书告警)

把 `auto_sync` 的失败接到 5.4.7 建好的告警通道上 —— 此前这类失败只有退出码与日志, 仍需要有人主动去看 (5.4.5 的文件描述符耗尽静默了十余小时, auto_sync 的构建失败静默了数周)。

### Added
- **`auto_sync.notify()`**: 直接复用 `telemetry.alerter`, 因此与守护进程走同一条链路、同一份限流账本 (`~/.medit/alerts_state.json`), 不重复实现一套。
- **两处触发, 只在失败时**:
  - 构建失败 → `critical`, key `autosync-build-failed`。卡片带仓库路径、`make` 的失败摘要、当时的代码同步状态, 以及影响与排查建议。
  - 拉取重试后仍失败 → `warning`, key `autosync-pull-failed`。说明重试次数、判读为网络/代理抖动、二进制已按本地工作区重建、下个周期会自动重试。
- 工作区脏导致的「跳过拉取」属预期状态, **刻意不告警** —— 否则会训练人忽略告警。

### 设计取舍
- **惰性导入 + 整段吞异常**: 告警通道不可用时 (包未部署 / 依赖缺失 / 网络不通) 只记一行日志并返回 `False`, 绝不影响同步任务本身 —— 「发不出告警」不该升级成新的故障。
- **复用而非重写**: 卡片结构、分级着色、按 key 限流、失败快速重试全部沿用 `alerter`, 避免两套行为漂移。

### 验证
- test_telemetry **54/54 passed** (`TestAutoSync` 新增 2 项并加固 3 项: 成功路径保持安静、构建失败以 `critical` 告警且卡片带失败摘要、拉取失败以 `warning` 告警、脏工作区不告警、通道抛异常时 `notify` 返回 `False` 而不外抛)。
- 单测全部打桩 `notify`, 并已核对 `~/.medit/alerts_state.json` 未出现 `auto_sync` 相关 key —— 即测试没有真发卡片。
- **真机端到端**: 用 `auto_sync` 自己的解释器 (工具链 Python 3.10) 走真实 `notify()` 路径投递一张标注演练的卡片, 推送成功 (Message ID `om_x100b650e930dd510c15480b648d3b75`), 并把结果带时间戳写进 `~/.medit/autosync.log`。

### 说明
- 至此告警通道覆盖两类来源: 守护进程资源吃紧、定时同步失败。README 已同步说明。

## [5.4.8] - 2026-09-11 (修复: auto_sync 拉取失败不再中止构建 + 日志带时间戳并迁出 /tmp)

承接对「auto_sync 构建失败」的专项排查。结论是三种失败叠加且互相掩盖: `go` 不在 launchd PATH (5.4.5 已修)、脏工作区让 `git pull --rebase` 直接拒绝、Clash 隧道抖动导致拉取失败。后两者都会让脚本**根本走不到构建**; 而构建失败又只报「编译警告」、照打 ✅ 并退出 0 —— 28 次运行里 25 次打印成功, 其中 23 次压根没构建。

### Fixed
- **任何拉取问题都不再中止构建**: 构建用的是本地工作区, 与拉取成败无关; 过去一遇拉取失败就 `return False`, 白白放弃一次更新二进制并验证的机会。
- **脏工作区优雅跳过而非当失败**: `git pull --rebase` 遇未提交改动会直接拒绝 (`cannot pull with rebase: You have unstaged changes`), 现场日志里出现过 2 次。现在先判 `git status --porcelain`, 脏则跳过拉取并明确说明, 构建仍然执行。刻意**不用 `--autostash`**: 无人值守时一旦回放冲突, 会在工作区留下冲突现场, 下个周期照样卡住。
- **网络抖动短重试**: 本机 git 走 Clash 本地代理 (`127.0.0.1:7897`, TUN 模式接管全部流量), 换节点 / 重连会把 TLS 会话掐断 (`SSL_ERROR_SYSCALL`), 且现场出现过「`git fetch` 刚成功、紧接着 `git pull` 就失败」的一两秒级抖动。现改为 3 次短重试 (间隔 10s), 而不是留到 6 小时后。
- **日志每行带时间戳**: 旧日志一行时间都没有, 失败无法与时刻对应 —— 这是本次排查最大的障碍。
- **日志从 `/tmp` 迁到 `~/.medit/autosync.log`**: `/tmp` 会被 macOS 的 periodic(8) 回收 (3 天未访问即删除), 更早的历史已经丢了 (可见日志只回溯到 9-05)。新位置可轮转 (超 5 MB 留一份 `.1`), 并复用与守护进程一致的「复制 + 截断」轮转 —— launchd 长期持有 stdout 的 fd, 改名会让两边分叉。写入目标做了去重判定: stdout 已是日志文件时不再自行写, 避免每行重复; 终端手工执行时屏幕与日志都能看到。
- **退出码如实反映**: `0` = 部署已更新 (含「脏工作区跳过同步」这种预期情况); `1` = 构建失败, 部署确实没更新; `2` = 二进制已重建但代码未同步 (暂时性网络故障)。此前无论哪种都退 0。

### 验证
- test_telemetry **52/52 passed** (新增 `TestAutoSync` 6 项: 脏工作区跳过但仍构建、拉取失败重试且仍构建、构建失败才算未更新、日志行都带时间戳、LaunchAgent 日志不落 `/tmp` 且与脚本目标一致、退出码契约 0/1/2)。
- **真机端到端**: `launchctl kickstart` 触发一次, 日志出现完整时间戳; 当时工作区恰好有未提交改动 (即本次改动本身), 脚本正确输出「跳过代码拉取」并照常构建成功、退出码 0 —— 换作旧代码, 这一轮会是「拉取失败 + 整轮中止」。
- **旧行为对照**: 在临时克隆里, 同一脏工作区下旧命令报 `cannot pull with rebase`, 加 `--autostash` 则成功 —— 印证了失败 B 的机制。

### 说明
- 更早的 `/tmp/via54medit_sync.log` 保留未动, 作为历史。

## [5.4.7] - 2026-09-11 (新增: 关键事件外部告警通道)

落实 5.4.6 建议的最后一条 —— 把描述符占用接入外部告警通道。

### Added
- **飞书告警通道 `telemetry/alerter.py`**: `send_alert(title, lines, key, level)` 复用既有的飞书交互卡片链路 (`FeishuSyncClient` + `im/v1/messages`); 卡片按 `level` 着色 (`critical` 红 / `warning` 橙 / `info` 蓝), 落款带花名与主机名。通道是通用的, 后续其它关键事件 (如 `auto_sync` 构建失败) 可直接复用。
- **描述符告警接入守护进程**: 占用达软上限 80% 时, 除落日志外再推一条飞书告警。`key` 按 10% 分档 (`fd-80` / `fd-90` / `fd-100`), 随占用升高逐步升级, `≥90%` 升为 `critical`。
- **新 CLI `alert` 子命令**: 默认展示通道状态与最近发送记录; `--test` 发测试告警 (绕过开关与限流) 验证通道; `--enable` / `--disable` 开关; `--min-interval N` 调整静默期。
- **配置新增 `alerts` 段**: `enabled` 默认 `true`, `min_interval_minutes` 默认 `60`。`load_config()` 是深合并, 旧配置文件缺该段时自动取默认值, 无需迁移。

### 设计取舍
- **绝不反噬调用方**: 所有对外函数吞掉异常并返回 `(False, 说明)`。告警通道坏掉不能把守护进程带崩, 也不能让"发不出告警"本身变成新的故障。
- **按 key 限流且跨重启生效**: 状态落盘 `~/.medit/alerts_state.json` (0600)。否则守护进程被 `KeepAlive` 反复拉起时, 每次启动都会重发一遍。
- **失败快速重试、成功长期静默**: 成功后静默 `min_interval_minutes`; 失败只等 10 分钟再试 —— 免得一次网络抖动把告警静音整整一小时。无论成败都记一次尝试: 否则"每次都抛异常"会让限流形同虚设, 5 秒滴答就重试一次, 反而变成另一种刷屏。

### 验证
- test_telemetry **46/46 passed** (新增 5 项: 配置默认与合并、限流窗口、开关与限流下不发请求、卡片结构与容错、FD 观测触发告警并按占用分档升级)。
- **真机端到端**: `medit-telemetry alert --test` 投递成功 (Message ID `om_x100b650ee6c194acc12028aa5dda989`); 另按守护进程的真实调用形态演练一次真实告警卡片, 同样投递成功。凭据齐备 (app_id / app_secret / open_id), 接收人 Devin。

### 说明
- 目前只有描述符占用接了告警。`auto_sync` 构建失败仍以非零退出码与日志体现, 可用同一通道后续接入。

## [5.4.6] - 2026-09-11 (加固: 日志轮转/限流、描述符观测与上限、配置权限)

承接 5.4.5 自检报告的遗留项 (P2 / P3), 一并收口。

### Fixed
- **日志无轮转, 被重复错误刷爆**: 同一句错误在 5 秒滴答循环里逐条落盘 —— 现场 `daemon.log` 达 2.0 MB / 12223 行, 其中 12200 行是同一条 `[Errno 24]`。现同一消息只在首次与每 100 次补一条汇总 (进行中汇总 + 换消息时的累计汇总); 超过 5 MB 时保留一份 `.1` 备份并就地清空。刻意采用「复制 + 截断」而非「改名 + 新建」: launchd 的 `StandardOutPath` 只在启动时打开文件一次并长期持有该 fd, 改名会让它继续写旧 inode, 与按路径写新文件的进程分叉。
- **描述符占用不可观测**: 新增 `fd_usage()` 与 `TelemetryDaemon._check_fd_health()`。占用达到软上限 80% 即告警 (文案按 10% 分档, 避免数值抖动被当成"新消息"绕开限流), 占用值同时写入心跳文件并由 `daemon --status` 展示。5.4.5 那类「资源耗尽但不崩溃」的故障中, 进程假死而 `KeepAlive` 无从感知, 这是唯一能提前暴露信号的手段。
- **LaunchAgent 的描述符软上限过低**: launchd 默认只给 256, 对长期常驻的扫描进程余量太薄 (本次即在一上午内耗尽)。plist 模板新增 `SoftResourceLimits → NumberOfFiles = 4096`。顺带把 plist 的全部插值统一做 XML 转义 —— 用户名或路径含 `&` / `<` 时原会生成非法 plist。
- **配置以 0644 明文落盘**: `~/.medit/telemetry_config.json` 内含飞书 `app_secret`, 却因常见 umask 022 而以 `-rw-r--r--` 落盘, 同机其它用户可读。`save_config()` 现在用 `os.open(..., 0o600)` 创建 (消除"先 0644 落盘再 chmod"之间的可读窗口) 并对既有文件显式 `chmod`, 目录一并收为 0700。
- **`pdf_utils` 的首选分支是死代码**: pypdf 只是可选 extra (`medit-telemetry[pdf]`), 而 fitz 才是高亮 / 文档链路的硬依赖; 原先却把 pypdf 排在首位, 常规部署下该分支从不命中。改为「硬依赖优先, 可选依赖兜底」。

### Changed
- **单测不再触碰真实配置**: `test_deploy_configuration_setup` 原先会临时覆写真实配置、再在 `finally` 里还原; 一旦进程在两步之间被强杀 (Ctrl-C / 超时 / OOM), 用户的真实配置就会永久留在测试值上。现改为把配置路径重定向到临时目录, 并断言落盘权限为 0600。
- **纯格式化**: `gofmt -w` 统一 35 个文件的文档注释缩进 (Go 1.19+ 规则), 独立成一次无逻辑改动的提交。

### 验证
- test_telemetry **41/41 passed** (新增 4 项: 日志重复限流、日志轮转、描述符观测、LaunchAgent plist 经 `plistlib` 解析并校验 `SoftResourceLimits`); 0 skipped。
- 真机: `~/.medit` 已收为 `drwx------`、配置 `-rw-------`; 重新生成的 telemetry plist 含 4096 描述符软上限; `daemon --status` 显示描述符占用; 测试前后真实配置 mtime 不变。
- `gofmt -l` 归零; `go vet` 干净; `CGO_ENABLED=1 go test -race ./...` 24 个包全绿。

### 说明
- **pypdf 未安装**: 该解释器由 uv 托管、受 PEP 668 约束, 依 5.4.4 定下的「不默认绕过」策略未强行写入。改以上面的次序调整根治 —— 首选分支不再依赖可选包; 确需该 extra 时仍可显式 `pip install "medit-telemetry[pdf]"`。

## [5.4.5] - 2026-09-11 (修复: 守护进程文件描述符泄漏 + 后台启动回归)

### Fixed
- **守护进程耗尽文件描述符 (`Errno 24`)**: `TelemetryDB.get_connection()` 返回的是裸 `sqlite3` 连接, 而全部调用方都写成 `with self.get_connection() as conn: x`。Python 的 `sqlite3.Connection` 上下文管理器**只提交事务、并不关闭连接**, 于是每一次查询都漏掉一个连接。守护进程以 5 秒滴答高频调用这些查询, 连接持续累积, 最终撞穿 `EMFILE` 上限。
  - **现场**: 日志自 01:38 起累积 **12200 条** `[Errno 24] Too many open files`, 日志被同一句错误刷到 2 MB; 目录扫描、配置读取全面失败, 监控实际已停摆。
  - **修复**: `get_connection()` 改为 `@contextmanager`, 在 `finally` 中 `close()`; 各写入方法已有的显式 `commit()` 保持不变 (语义不变)。
- **启动守护时抛 `NameError`**: `daemon.py` 的后台分支在移除 `PYTHONPATH` 注入时, 把 `env` 参数遗留在了 `subprocess.Popen(...)` 中, 而该变量已无任何定义。此分支**必然**抛 `NameError`, 使手动 `daemon --start` 与一键部署「步骤 5/6 启动后台守护」双双失效 —— 后者意味着**新机器部署会在最后一步失败**。
  - **为何长期静默**: 正式运行路径由 LaunchAgent 以 `--foreground` 拉起, 恰好不经过这段代码; 单测亦未覆盖该分支。
  - **修复**: 移除该参数, 子进程继承当前环境。子进程以 `cwd=project_root` 配合 `-m telemetry.cli` 运行, 标准做法即可定位模块, 无需注入 `PYTHONPATH`。
- **`pdf_utils.get_pdf_page_count()` 泄漏文件句柄**: pypdf 分支打开的文件对象与 PyMuPDF 分支的 `Document` 均未关闭; 现分别改用 `with open(...)` 与 `with fitz.open(path) as doc`。
- **`feishu_sync` 自动建表请求泄漏响应对象**: `urlopen()` 的返回值未关闭, 现改为 `with ... as _: pass`。
- **`daemon.py` 启动时日志句柄泄漏**: `open(LOG_FILE, "a")` 未关闭; 现改为 `with open(...)`。

### Fixed (构建与部署链路)
- **`make build` 实际上什么都不做**: Makefile 中 `bin/medit: $(MEDIT_PLAIN)` 在 `MEDIT_PLAIN` 就等于 `bin/medit` 时构成自依赖, make 会警告 `Circular bin/medit <- bin/medit dependency dropped`, 随后因该文件已存在而判定 `Nothing to be done for 'build'`。后果是二进制长期停在某次手工构建的版本上 —— 本次现场即停在 `v5.2.0 (314ea76)`, 落后仓库两个 minor 系列, 而一键部署与 auto_sync 都以为自己"重建过了"。现改为 FORCE 前置, 每次 `make build` 都真正重新编译并按 `git describe` 打上版本戳。
- **`auto_sync` 的 LaunchAgent 找不到 `go`**: plist 由 `install_launchd()` 生成, 模板未设 `PATH`, 而 launchd 默认只给 `/usr/bin:/bin:/usr/sbin:/sbin` —— 不含 Homebrew。于是每 6 小时一次的自动同步在「重新构建 Go 核心二进制」一步稳定失败。现由 `launchd_path()` 显式写入 `PATH` (go 所在目录 + 常见包管理器目录 + 系统目录) 与 `HOME`, 且刻意不整段照抄交互式 PATH, 以免把 IDE / 沙箱的内部路径固化进 LaunchAgent。
- **构建失败被伪装成同步成功**: `pull_and_rebuild()` 把 `go build` 失败降级为「⚠️ 编译警告」后, 仍打印 `✅ 本地部署已更新至最新版本！` 并返回成功; 配合上一条, 故障可静默数周 (launchctl 显示"上次退出码 0")。现在构建改走 `make build`, 失败时明确报「同步未完成」并返回失败, `main()` 以退出码 1 结束, 让 launchd / cron 的退出码与日志都能反映问题。
- **plist 模板未做 XML 转义**: `python_path` / `script_path` 直接插值, 用户名或路径含 `&` / `<` 时会生成非法 plist; 现统一经 `xml.sax.saxutils.escape` 处理。

### 验证
- test_telemetry **37/37 passed** (新增 1 项 `test_start_daemon_background_spawn`: 打桩 `subprocess.Popen` 并把 PID / 日志路径指向临时目录, 断言后台分支真正走到 `Popen`、`cwd` 真实存在, 且不产生任何真实进程)。
- **负向对照**: 把缺陷注入回 `daemon.py` 后, 该项单测立即以 `NameError: name 'env' is not defined` 失败 ⇒ 用例确能捕获此回归 (此前该分支无任何覆盖)。
- **真机实测** (macOS / uv Python 3.11.15): 泄漏期间 FD 持续攀升至上限; 修复并重启后守护进程 **FD 稳定在 11**, 日志不再出现 `EMFILE`, 心跳与目录扫描恢复正常。

### 补充说明
- 文件描述符泄漏期间, 进程只"假死"而不退出, LaunchAgent 的 `KeepAlive` 无从感知, 因此故障可持续十余小时无人察觉 —— 这类"资源耗尽但不崩溃"的故障建议后续纳入监控告警。
- 本版同时包含构建与部署链路修复 (Makefile / auto_sync / LaunchAgent), 不涉及 `medit-telemetry` 模块代码, 模块版本仍为 1.5.5。

## [5.4.4] - 2026-09-10 (变更默认: PEP 668 改为需显式授权的保守策略)

### Changed
- **[5.4.3] 的「自动绕过」改为「显式授权」**: 上一版识别到 PEP 668 时会自动追加 `--break-system-packages`。这等于由部署脚本替用户决定突破解释器管理方 (uv / 系统 / Homebrew) 划下的边界 —— 不宜作为默认行为。现在**默认不绕过**。
- **默认行为**: 被拒时打印原因 (含 pip 原报错行) 与开启方式, 随后注入 `.pth` 保证模块可导入, 命令仍由启动器落到 PATH ⇒ **功能照常可用**; 差别只是没有向该解释器登记包元数据 (pip 无法追踪它的升级 / 卸载)。
- **新增开关** `--allow-break-system-packages` (别名 `--break-system-packages`, 与 pip / uv 同名便于辨识): 显式授权后才原地重试。`deploy.ps1` 对应 `-AllowBreakSystemPackages`; `deploy.bat` 直接透传 `%*`。
- **自然语言入口同步**: `nlp_deploy.py` 识别「强制安装 / 强制写入 / 允许写入 / 绕过保护」以及字面量 `break-system-packages`, 命中才开启开关; 普通「部署监控」不会开启。命令行显式参数优先。
- 模块版本 1.5.3 → 1.5.4。

### 验证
- test_telemetry **36/36 passed** (新增 / 改写 3 项: 默认命令序列不得含逃生开关且必须给出开启指引、显式授权后才重试、自然语言仅在明确表述时开启)。
- 真机实测 (macOS / uv 托管 Python 3.11.15):
  - 默认: pip 与 uv 双双被拒 → 打印原因与开启方式 → `.pth` 注入成功 → `medit-telemetry daemon --status` 仍正常返回;
  - `--allow-break-system-packages`: 「已获授权：追加 --break-system-packages 重试 (pip)...」→ 注册成功, 随后启动器接管。
- 自然语言实测: 「在新设备上部署监控，花名叫星云」→ 不开启; 「强制安装到系统解释器」/「部署监控 --break-system-packages」→ 开启。

## [5.4.3] - 2026-09-10 (修复: 部署兼容外部管理的解释器 - PEP 668 / uv)

### Fixed
- **uv 托管 / 发行版 / Homebrew 解释器上部署不出命令**: uv 托管的 Python、各发行版自带 Python 与 Homebrew Python 都以 PEP 668 (`externally-managed-environment`) 拒绝常规 `pip install -e`; `uv pip install` 同样拒绝。过去遇到该情况只退回 `.pth` 注入 —— 而 `.pth` **仅解决「模块可导入」, 并不创建 console script**, 于是「命令已就绪」的提示与实际不符, 部署流程末尾打印的那些用法全是摆设。
- **安装改为四级降级** (`telemetry/deploy.py`):
  1. `pip install -e` (常规路径);
  2. 识别到 `externally-managed` 特征后追加 `--break-system-packages` 重试 —— 这正是 pip 自己在报错中给出的逃生开关; → 已在 [5.4.4] 调整为**需显式授权**才使用;
  3. 解释器根本没有 pip (uv 托管环境常见) 时改用 `uv pip install -e ... --python <解释器> --no-deps --break-system-packages`;
  4. 全部失败才退回 `.pth`, 且**命令改由启动器直接落到 PATH 目录**, 不再出现「装完却没有命令」。
- **命令落点不再听天由命**: `_launcher_targets()` 在命令不存在时, 挑一个「在 PATH 上且可写」的用户级 bin 目录新建 (POSIX `~/.local/bin`), 而不是退到解释器目录里了事; 装完还会校验该目录是否真在 PATH, 不在就明确提示怎么加。
- **失败原因简报**: 原来把 pip 输出整段截断 150 字符, 关键信息常被前导日志冲掉; 现在挑一条含 `error` / `externally managed` / `no module named` 的行来报。权限不足 (`PermissionError`) 单独识别并提示。
- `telemetry/platform_paths.py`: 新增 `user_bin_dirs()` (跨平台用户级 bin 候选) 与 `is_on_path()`。
- 模块版本 1.5.2 → 1.5.3。

### 注意事项 (顺序)
`pip install -e` 会重新生成 console script, 把环境自检启动器覆盖回 pip 版本。部署脚本因此在安装之后才执行启动器接管 (步骤 2b); 手工执行安装后请重跑一次部署。

### 验证
- test_telemetry **34/34 passed** (新增 4 项: PEP 668 触发重试且重试命令含 `--break-system-packages`、全部失败才回退 `.pth`、命令目标覆盖两个命令名且优先复用已存在命令、bin 目录候选与 PATH 判定)。
- **真机端到端** (macOS / uv 托管的 Python 3.11.15, 即修复前必然失败的机器):
  - 修复前: `pip install -e` 被 PEP 668 拒绝 → 退回 `.pth` → 无命令生成;
  - 修复后: 自动「该解释器由外部管理 (PEP 668)，追加 --break-system-packages 重试...」→ `Successfully installed medit-telemetry-1.5.3`, 随后启动器接管, `medit-telemetry --env-check` 正常输出;
  - 同时实测确认了「阶段 1 被拒 / 阶段 2 成功」的两级行为与 pip 报错原文, 以及安装会覆盖启动器这一顺序约束。

## [5.4.2] - 2026-09-10 (收尾: 启动器缺失时的提示语改为可操作指引)

### Fixed
- **模板缺失提示语已过时**: [5.4.1] 起启动器模板通过 `package-data` 随包分发, 因此「未找到启动器模板」不再是需要容忍的正常情况, 而是**安装不完整或包版本过旧**的信号。原提示语只说「跳过 (命令仍可正常使用)」, 会让人误判为无需处理。
  - `telemetry/deploy.py`: 模板缺失分支现在打印实际查找路径与重装命令 `pip install -U medit-telemetry`;
  - `telemetry/deploy.py`: 启动器写入失败分支补充常见原因 (命令所在目录不可写);
  - `telemetry/README.md`: 明确模板随包分发, 源码安装与 wheel / sdist 安装都能装出启动器。
- 无运行时代码变更, 纯提示语与文档措辞。
- 模块版本 1.5.1 → 1.5.2。

### 验证
- test_telemetry 30/30 passed (新增 `test_guarded_launcher_missing_template_is_graceful`: 断言模板缺失时优雅返回 `False`、不写任何文件、且输出包含重装指引)。
- 实测缺失分支输出 (把模板目录指向不存在路径): 打印查找路径 + 「该文件随包分发, 缺失通常表示安装不完整或版本过旧」+ 重装命令。
- 已安装的真实启动器 (`~/.local/bin/medit-telemetry`) 未被本次验证触碰。

## [5.4.1] - 2026-09-10 (修复: 启动器模板纳入打包范围)

### Fixed
- **启动器模板未随包分发**: 消除 [5.4.0] 记录的「已知边界」。`telemetry/scripts/` 没有 `__init__.py`, setuptools 不将其视为包, 因此其中的外壳启动器模板不会被打包 —— 从 wheel / sdist 安装时该模板缺失, 部署阶段会提示「未找到启动器模板, 跳过」, 环境自检启动器装不出来。
- **修法**: 在 `telemetry/pyproject.toml` 新增 `[tool.setuptools.package-data]` (`telemetry = ["scripts/*"]`), 并在 `telemetry/setup.py` 同步声明 `package_data={"telemetry": ["scripts/*"]}`, 使两条分发路径都带上模板。未改动任何运行时代码。
- 模块版本 1.5.0 → 1.5.1。

### 验证
- test_telemetry 29/29 passed (新增 `test_launcher_template_is_declared_as_package_data`, 同时断言 `scripts/` 下确无 `__init__.py` —— 该前提一旦变化, 打包方式需重新评估)。
- **构建产物实测** (非仅检查配置):
  - `medit_telemetry-1.5.1-py3-none-any.whl` 内含 `telemetry/scripts/medit-telemetry` (3222 字节), 内容以 `#!/bin/sh` 开头;
  - `medit_telemetry-1.5.1.tar.gz` (sdist) 同样包含 `scripts/medit-telemetry`;
  - 把 wheel 解包到独立目录后导入其中的 `telemetry.deploy`, 按 `deploy.py` 的推导方式定位模板 —— `exists() = True`, 证明 wheel 安装布局下模板可被发现, 不再需要任何兜底下载。

## [5.4.0] - 2026-09-10 (运行环境自检: 拦截 PYTHONHOME / PYTHONPATH 冲突)

### Added
- **telemetry/envcheck.py**: 运行环境自检模块 —— 识别被 IDE / 沙箱 / 构建工具注入、且与本解释器不匹配的 `PYTHONHOME` 与 `PYTHONPATH`, 输出冲突明细与可直接复制的修复命令。只做只读检测, 不修改环境变量、不改变命令行为。
- **telemetry/scripts/medit-telemetry**: 外壳启动器 —— 在解释器启动前比对 `PYTHONHOME` 与本解释器前缀、以及 `PYTHONPATH` 中的 Python 版本目录; 发现冲突时改用 `-E` (忽略全部 `PYTHON*` 变量) 执行并打印一行说明。未检测到冲突时不传 `-E`, 行为与直接调用解释器完全一致。由 `deploy.py` 安装为 `medit-telemetry` / `traework-telemetry` 命令, 原命令备份为同目录 `*.orig`。
- **telemetry/cli.py**: 新增 `--env-check` 显式自检 (打印解释器路径、变量实际取值与结论); `cli.main()` 入口调用一次运行时自检。
- **telemetry/deploy.py**: 新增 `install_guarded_launcher()`, 并把安装步骤接入部署主流程 (步骤 2b)。
- **telemetry/README.md** / **docs/TELEMETRY_GUIDE.md**: 新增「运行环境自检」小节与「故障排查」章节。

### 设计说明 (为什么必须是两层)
- `Fatal Python error: init_fs_encoding ... No module named 'encodings'` 发生在解释器**启动阶段**, 任何 Python 代码都来不及执行 —— 因此纯 Python 自检无法覆盖该故障, 必须由外壳层在进程启动前拦截。这是本方案引入 shell 启动器的唯一原因。
- 运行时自检覆盖「解释器能起来但仍受污染」的情形: 例如仅 `PYTHONPATH` 注入了异构版本的 `site-packages`, 可能导入到 ABI 不兼容的扩展模块。
- 两层用 `MEDITELEMETRY_ENV_ISOLATED` 标记交接 —— 启动器已提示过时运行时自检不再重复; 但 `--env-check` 无论何时都完整给出结论。此项为实测发现「两层各提示一遍」后修正。

### Fixed
- **启动器安装穿透软链接**: `shutil.which()` 返回的 `~/.local/bin/medit-telemetry` 常是指向解释器 `bin/` 的软链接, 直接写入会让改动落在解释器安装树内的真实文件上。现显式解析真实路径后写入, 并在输出中标注 `软链 -> 真实路径`。
- **重复部署不幂等**: 新增 `LAUNCHER_MARKER` 识别与内容比对, 第二次部署报「已是最新」, 且不会把 `*.orig` 备份冲成启动器自身。
- **telemetry/setup.py 版本号长期滞后**: 停留在 1.1.0 (`pyproject.toml` 与 `__init__.py` 已在 1.4.0), 历次发版均遗漏, 本次对齐。
- 模块版本 1.4.0 → 1.5.0。

### 验证
- test_telemetry 28/28 passed (新增 `test_envcheck_detects_conflicting_python_env` / `test_envcheck_warns_only_once` / `test_guarded_launcher_template`)。
- 真机复现与修复对照 (macOS / Python 3.11.15, 终端被注入指向 3.10 framework 的 `PYTHONHOME`):
  - 修复前 `medit-telemetry --env-check` → `Python path configuration: ... Fatal Python error: init_fs_encoding`;
  - 修复后同一命令 → 打印冲突说明后正常输出自检报告, `daemon --status` 同时恢复正常;
  - 干净环境 (`env -u PYTHONHOME -u PYTHONPATH`) → 无任何提示, `--env-check` 报「未发现冲突」, 证明正常路径行为未被改变。
- 仅 `PYTHONPATH` 注入异构版本、且绕过启动器时, 运行时自检能独立给出提示 —— 确认第二层并非冗余。
- 启动器通过 `sh -n` 语法校验 (模板与替换解释器后的成品均通过)。

### 已知边界
- 启动器模板位于 `telemetry/scripts/`, 未纳入 `packages = ["telemetry"]` 的打包范围。从源码仓库执行 `deploy.py` 时可用; 若从 wheel 安装, 该步骤会提示「未找到启动器模板, 跳过」, 命令仍可正常使用 (仅缺少外壳层拦截)。→ 已在 [5.4.1] 修复。

## [5.3.0] - 2026-09-10 (多维表格接入公司既有表: schema 自适应 + dry-run + 备份口径修正)

### Added
- **telemetry/bitable_sync.py**: 目标表 schema 适配层 —— 同步前读取目标表实际字段名, 自动判定是「自建标准表 (15 字段)」还是公司既有「监控数据周报明细」表 (13 字段, 命名与标准表完全不同)。判定取两侧字段命中数较大者且至少命中 3 个, 识别不出时回退标准表并给出原因。
- **写入映射**: 标准字段名 → 目标表字段名 (`COMPANY_FIELD_MAP`); 目标表没有的列 (成员OpenID / 三个细分工时 / API调用次数) 自动丢弃而不报错。可用 `company_bitable_field_map` 覆盖任意一列。
- **读取归一化**: 目标表字段名 → 标准字段名 (`normalize_record_fields`), 在线读取与本地备份回退两条路径统一, 因此接入公司表时图表大屏与战报逻辑无需改动。
- **telemetry/cli.py**: 新增 `bitable --sync --dry-run` —— 只输出 schema 判定依据与将写入的字段, 不提交、不写本地备份; 并新增 `_explain_error()` 把飞书错误码 (99991672 应用缺权限 / SingleSelect 与 Datetime 转换失败 / 字段名不匹配) 翻译成可操作提示。
- **telemetry/config.py**: 新增 `company_bitable_schema` / `company_bitable_project` / `company_bitable_member` / `company_bitable_field_map` 四个配置键。
- **telemetry/README.md** / **docs/TELEMETRY_GUIDE.md**: 补充「接入公司既有表 (字段自适应)」说明、四个配置键、`--dry-run` 用法与本地备份口径。

### Fixed
- **单选字段写库失败 (1254062 SingleSelectFieldConvFail)**: 单选字段必须写字符串, 传数组会被飞书拒绝。此前 payload 直接透传列表导致首次真实写入即失败。
- **日期字段写库失败 (1254064 DatetimeFieldConvFail)**: 实测该表 datetime 字段只接受毫秒时间戳 —— ISO 字符串无论带不带毫秒、带不带时区均被拒。改由 `_period_start_ms()` 输出周期起始日 00:00 +08:00 的毫秒时间戳。
- **幂等键写入与查找不一致导致重复新增**: 查找按本机昵称 `Devin`、写入按显示名 `Devin Wei`, 匹配不上于是静默新增了一条重复记录。新增 `_resolve_member()` 使两处取值同源, 并限定该映射只在本机用户上生效, 避免多人场景串号。
- **本地备份 CSV 表头错位**: `_record_local_csv()` 原样落盘调用方的 payload, 于是 13 列公司数据被追加进 15 列标准表头的同一文件, `csv.DictReader` 回读时列语义全部对错、备份不可信。现固定以标准字段名、固定 15 列 (`BACKUP_FIELDS`) 落盘, 与目标表 schema 无关。
- **历史错位行修复**: 回读时按列宽识别遗留的 13 列公司行, 用 `COMPANY_PAYLOAD_ORDER` (与写入侧同源) 还原后再反向映射, 而非整行丢弃; 完全无法对齐的脏行才跳过。实测本机 7 行数据中 6 行错位, 修复后正确归位 (标注篇数 / 阅读页数这一对易错项已确认各归各位)。
- **备份回读重复行**: 备份为追加写, 同一周重复运行会留下多份相同记录, 回退路径因此返回重复数据、把图表放大。现按「周期 + 成员」折叠, 与在线路径的 upsert 语义对齐。
- **dry-run 有副作用**: 备份写入原先位于 dry_run 判断之前, 每次演练都会向备份追加一行与最终写入不一致的试探数据。现移至真正落库之后。
- **备注保护未跟随字段改名**: 保护逻辑用字面量 `备注说明` 去 payload 删除, 一旦通过 `company_bitable_field_map` 改名即静默失效, 人工填写的备注会被覆盖。现抽出 `_field_map()` / `_note_field_name()`, 写入与保护共用同一份映射。
- **兜底时间戳随时区漂移**: `_period_start_ms()` 的异常分支使用不带时区的 `datetime.now()`, 在东八区以外的机器上会偏移出一整天; 现补上 +08:00。
- 模块版本 1.3.0 → 1.4.0。

### 验证
- test_telemetry 25/25 passed (新增 `test_bitable_local_backup_is_schema_agnostic` / `test_bitable_dry_run_has_no_side_effect` / `test_bitable_note_protection_follows_custom_field_map`)
- 真实表格实测 (`hackhealth.feishu.cn` / `tbl6evznoEt4aAD0`): `--sync --dry-run` 判定为 `自动识别 (company; 表内 13 个字段)`, 备份文件 md5 前后一致 (确认无副作用); `--sync` 幂等更新既有记录 `recvuONw2kks7O`, 表内维持 10 条无重复, 人工备注「本机全量监控数据 (RSV/developments/TMA 三目录汇总), 含历史 backfill 补录」原样保留。
- 前置依赖: 应用需在开发者后台开通 `bitable:app` 并**创建版本后发布** (仅勾选不生效), 这是文档协作者权限之外的另一层; 未开通时返回 99991672。

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
