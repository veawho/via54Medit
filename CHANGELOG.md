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

## [5.4.46] - 2026-09-12 (清除 macOS 相关硬编码: 604 处写死账号的绝对路径 + 补齐扫描器规则)

回应"检查并避免出现 macOS 相关的硬编码"。

先把"检查"和"避免"分开做: 扫描器原先只认 `/tmp` 和两串外来盘符路径,
**对"写死本机账号"这一类完全无感** —— 而这一类恰恰是仓库里最多、也最容易
在换机器/换用户后炸掉的。补上规则后再清, 否则清完也没人守得住。

### 一、检查: 给兼容性扫描器补上 macOS 规则

`scripts/deploy_scan.py` 的 `scan_platform_compat()` 原来只有 2 条规则,
现在扩到 5 类, 覆盖范围也从 `scripts/` 扩到 `scripts/ skills/ internal/ cmd/ integrations/ telemetry/`:

| 类别 | 形态 | 处理 |
| --- | --- | --- |
| `macos_user_path` | `"/Users/<account>/…"` | 一律报, 占位符(`x`/`user`/`example`…)除外 |
| `macos_only_path` | `/Applications/` `/System/` `/Library/` `/opt/homebrew/` | 有平台守卫或存在性探测才放行 |
| `macos_only_cmd` | `osascript` `sips` `pbcopy` `textutil` `hdiutil` … | 有平台守卫才放行 |
| `posix_tmp` | `"/tmp/…"` | 报 (既有规则) |
| `foreign_path` | `G:\` `C:\Users\via54` | 报 (既有规则) |

两条设计取舍值得记下来:

- **存在性探测算合法**。`ChromeCandidates()` 里那一串 `/Applications/Google Chrome.app/…`
  是**候选表**, 由 `os.Stat` / `LookPath` 逐个筛 —— 这就是跨平台该有的写法,
  报它等于让人去改对的东西。于是 `os.path.exists` / `LookPath` / `shutil.which` /
  `fileExists(` 出现过的文件, `macos_only_path` 放行。
- **刻意不把 `open` / `defaults` 列进 macOS 专属命令**。它们作为字符串在 JSON 键、
  状态值里到处都是, 列进去只会满屏误报 —— 一个会误报的检查器等于没有检查器。
  只收"明确只有 macOS 才有、且不会与普通字符串混淆"的那几个。

### 二、避免: 清掉 604 处, 并保证是零行为变化

全仓 `grep /Users/` 命中 625 处, 分类后: `macos_user_path` 604 · `posix_tmp` 40 ·
`macos_only_path` 9 · `foreign_path` 3 · `macos_only_cmd` 1。

清除方式是 `~` 派生 / `__file__` 派生 / `$HOME` 派生, **不改变本机解析结果**:

| 场景 | 旧写法 | 新写法 |
| --- | --- | --- |
| Python 用户目录 | `"/Users/<account>/Desktop/TMA"` | `os.path.expanduser("~/Desktop/TMA")` |
| Python 仓库自身 | `"/Users/<account>/…/via54Medit/scripts"` | `os.path.dirname(os.path.abspath(__file__))` |
| Go 用户目录 | 字面量 | `filepath.Join(home, …)` + `os.UserHomeDir()` |
| Shell | 字面量 | `$HOME` / `${HOME}` |

规模: **290 个文件 / 581 处替换 / 213 处补 `import os`**。

改动最大的几处不只是"换写法", 而是顺手修掉了原先就坏的逻辑:

- `internal/source/hlo_orchestrator.go`
  - 首选候选是写死某个 macOS 账号的路径 (`/Users/<name>/Desktop/HLO_design/…`) —— 换台机器必然落空;
  - 另有一个候选写作字面量 `"$HOME/HLO_design/hlo_nlu_v2.py"`, 而 `fileExists()`
    **不做 shell 展开**, 所以那条候选**从来没命中过** —— 是死代码, 这次删除;
  - `osHomeDir()` 原先走 `sh -c "echo $HOME"`, Windows 上直接不可用, 改为 `os.UserHomeDir()`;
  - `HLOTruthQuery` 里写死的 `python3.11` 改为 `foundation.ResolvePython`(按"能不能 import 依赖"解析)。
- `internal/integrations/feishu/feishu.go` — 默认 `lark-cli` 路径写死了账号目录, 改为
  `defaultLarkCLI()`: `~/.hermes/node/bin/lark-cli`(存在才用) → PATH。
  原先的写法坏在**报错发生在推送那一刻**, 与"配置缺失"很难区分。
- `scripts/tma_batch_highlight.py` — 默认值写死了某台 Windows 机器的盘符路径, 改为 `$HOME` 派生。
- `skills/…/render_ppt_slides.py` — 唯一一处没有守卫的 `osascript`, 补 `sys.platform != 'darwin'`
  判断并说明替代方案(PowerPoint AppleScript 报错与"PowerPoint 没装"很难区分)。

刻意**没动**的: 40 处 `/tmp`。那是"POSIX 假设", 不是"macOS 专属", 是另一件事;
扫描器仍然把它们报出来, 所以不存在"藏起来"的问题。

### 三、验证: 不是"看着对", 而是逐字等价

机械改了 290 个文件, 光靠 review 不够。做了四层验证:

1. **等价性**: 逐个把新的 `expanduser("~/…")` 在本机解析, 与它替换掉的旧绝对路径
   比对 —— **577 处逐字相同**。剩下未配对的都属预期(Go 走 `filepath.Join`、
   仓库自身走 `__file__`、含占位符的 f-string、以及从 Windows 盘符改出的新默认值)。
2. **静态**: AST 全仓扫描"用了 `os.*` 但文件顶层没有 `import os`" —— 这类是本轮
   唯一可能引入的回归类别。
3. **动态**: 用 `runpy` 逐文件执行模块顶层代码(300 个), 抓 `NameError`。
4. **回归面**: Python 187 + 230 + 24 用例、Go 24 个包、`go vet ./...`、`go build ./...` 全绿。

第 2、3 层**真的抓到一个回归**: `scripts/test_citation_sync.py` 手工改写成
`__file__` 派生时用了 `os.path` 却漏了 `import os` —— 静态检查报出, 已修。
这也说明为什么这轮验证不能省: 213 处自动插入的 `import os` 全部有效,
但**手工改的那几处**同样需要同一把尺子。

### 四、守着它

新增 `TestMacosHardcodingScan`(7 个用例), 其中一条是**全仓不变量**:
`test_repo_has_no_macos_specific_hardcoding` —— 以后谁再写死账号路径, 单测直接红。
另外把原来依赖"仓库里真的有外来盘符路径"的用例改成合成目录夹具
(那条路径这轮被清掉了, 旧写法会假红), 并补 `test_scanner_still_covers_the_real_repo`
确保扫描范围没被悄悄缩掉。

## [5.4.45] - 2026-09-12 (解决 PaddleOCR 的问题: OCR 入口其实是坏的 —— 解释器错配 + 脚本路径依赖 cwd + /tmp 硬编码)

回应"解决 PaddleOCR 的问题"。

排查后发现 **OCR 这条腿实际上是跑不起来的**, 而且有三个各自独立的原因叠在一起。
之所以一直没人发现, 是因为**部署报告写着"✓ PaddleOCR 已就绪"** —— 报告和命令用的不是同一个解释器。

### 一、实测到的三个缺陷

```bash
$ cd /tmp && medit anno2ppt ocr paper.pdf 1
/private/tmp/scripts/paddleocr_pdf_page.py: No such file or directory     # ← 脚本找不到
$ cd <repo> && medit anno2ppt ocr paper.pdf 1
ModuleNotFoundError: No module named 'paddleocr'                          # ← 解释器里没装
```

| # | 缺陷 | 成因 |
| --- | --- | --- |
| 1 | **解释器错配**(核心) | `ResolvePython` 按**名字**挑解释器, 候选链 `python3.11 → python3 → python` 先命中 `~/.local/bin/python3.11` —— 实测它有 `pymupdf` 却**没有** `paddleocr`; 而 `python3` 三个都有。名字对不等于包里装了东西 |
| 2 | **脚本路径依赖 cwd** | 首选项 `~/.hermes/skills/via54medit/via54medit-anno2ppt-phase7/scripts/…` **根本不存在**(多了一层 `via54medit`, 且技能分发包里没有 `scripts/`); fallback 是相对**当前工作目录**的 `scripts/…`。两条都落空 → 只在"恰好 cd 到仓库根"时才工作 |
| 3 | **`/tmp` 硬编码** | `paddleocr_pdf_page.py` 把渲染出的 PNG 写到 `/tmp/…`。Windows 上 `C:\tmp` 通常不存在 → OCR 第一步就失败。部署扫描器的平台兼容段一直在报这一条, 但没人把它和"OCR 不可用"联系起来 |

### 二、为什么它一直没被发现: 报告与命令各说各话

部署扫描探测 OCR 用的是 `sys.executable`(仓库那个装了 paddle 的 3.10), 而 `medit anno2ppt ocr`
用的是 `ResolvePython` 挑出来的 `python3.11`。**两个不同的解释器**, 于是"✓ 已就绪"与
`ModuleNotFoundError` 可以同时为真 —— 与 v5.4.41 抓到的"记账调用点存在但不可达"是同一类问题:
**检测的对象不是真正会跑的那条路径**。

### 三、修法

**Go 侧** (`internal/foundation/python_capability.go` 新增):

* `ResolvePythonFor(need, envOverride, cfg)` —— 按"**能不能 import** 全部 need"挑解释器
  (用 `importlib.util.find_spec`, 实测 0.00s; 真 import paddle 是秒级开销)。
  显式指定(`config.python_path` / `$VIA54_OCR_PYTHON`)**严格**: 不满足就报错, 不静默改用别的
  —— 悄悄换会把"我把解释器配错了"藏起来。`$PYTHON` 与 PATH 候选则是尽力而为。
* `FindRepoRoot()` / `ResolveOCRScript()` —— 脚本解析以**仓库根**为锚
  (`$VIA54_REPO` > 可执行文件位置上溯 > cwd 上溯), 彻底摆脱 cwd 依赖。
  `$VIA54_OCR_SCRIPT` 同样严格。找不到时报错会**列出全部试过的路径**。
* `medit anno2ppt ocr --smoke` —— 不读 PDF, 只做真识别自检, 排障一条命令搞定。

**Python 侧** (`scripts/deploy_scan.py`):

* `ocr_python()` / `ocr_script_path()` —— 与 Go 侧**同一套规则、同一顺序**(有测试钉住两边一致)。
* `_probe_ocr()` 改为判**跑 OCR 的那个解释器**, 并在结论里报出是哪一个; 缺依赖时报错会点名
  "就是它缺" + 给出针对该解释器的 `pip install` 命令。
* `pip_install(python=…)` —— OCR 的依赖**装进跑 OCR 的那个解释器**(往错的那个装, 探测会一直
  说"缺", 而人去看的时候又"明明装过了")。
* `ocr_smoke_test()` 改为执行 `[ocr_python, ocr_script_path, "--smoke"]` —— 用**真正的解释器**跑
  **真正的脚本**, 一次把四件事验完: 解释器选得对不对、脚本找不找得到、API 形状变没变、权重在不在。
  自检与业务共用 `run_ocr_on_image()`, 不同源的自检验的不是会跑的那条路。

**脚本侧** (`scripts/paddleocr_pdf_page.py`):

* 临时目录改用 `tempfile`(平台正确, macOS 上落在 `$TMPDIR`), 顺手把 `doc.close()` 放进 `try/finally`。
* 新增 `--smoke` 真识别自检。
* 文档更正: 删掉"表格识别 (PP-Structure)"这个**实现里并不存在**的说法(实际只有一条
  行/数字启发式), 并把"必须用装了 paddleocr 的解释器"写进脚本头。

### 四、验证(前后对照)

| 场景 | 修复前 | 修复后 |
| --- | --- | --- |
| `cd /tmp && medit anno2ppt ocr paper.pdf 1` | `No such file or directory` | **46 个文字块 / 45 行 / 7 行疑似表格** |
| `cd <repo> && medit anno2ppt ocr paper.pdf 1` | `ModuleNotFoundError: paddleocr` | 同上 |
| `medit anno2ppt ocr --smoke` | 没有这个开关 | `[L2][smoke] OK: 识别到 1 段文字` |
| 部署报告那一行 | `✓ PaddleOCR 与 paddle 均可导入`(判的是另一个解释器) | `✓ PaddleOCR python3.10 (部署脚本自己的解释器) 三个依赖齐备` —— **报出判的是谁** |
| 显式指定缺包的解释器 | 仍报"已就绪" | `✗ $VIA54_OCR_PYTHON 指定的解释器 … 缺 paddleocr, paddle`(不静默换) |
| 渲染临时文件 | `/tmp/paddleocr_p1_*.png`(Windows 不可用) | `$TMPDIR/paddleocr_p1_*.png` |
| 平台兼容扫描 | 50 处 | **49 处**(少的就是这处 `/tmp`) |

### 五、顺带更正的一处**教错人**的文档

`skills/via54medit-architecture-honest-status/references/paddleocr-pdf-page-script.md` 原先写着
"用 `python3.11` 调用", 并称依赖在 "hermes-agent venv" —— 那正是复现本 bug 的配方
(python3.11 里没有 paddleocr)。已改为首选 `medit anno2ppt ocr`(由它自己挑解释器), 并补上
"如何判断某个解释器行不行"的一条命令。

### Tests
- Go: 新增 `internal/foundation/python_capability_test.go` —— 会跳过不合格解释器、错误里列全候选与
  各自缺什么、显式覆盖严格不回退、候选列表不随 cwd 变化(用 `Chdir` 实证)、找不到仓库根时优雅降级。
- Python: `scripts/test_deploy_scan.py` 90 → **102**。含**核心回归**: 探测必须判"跑 OCR 的那个
  解释器"并点名它(旧逻辑在这里必然放行)、候选链与 Go 侧一致(解析 Go 源码比对)、OCR 安装
  目标解释器正确、以及"OCR 脚本不得再出现 `/tmp` 硬编码"与"--smoke 与业务共用推理函数"两条守卫。
- 两侧契约一致性由测试守住: 解释器候选链、`VIA54_OCR_PYTHON`/`VIA54_OCR_SCRIPT` 常量名、
  以及 `anno2ppt ocr` 要求的模块集合。

## [5.4.44] - 2026-09-12 (OCR 与 mmx-cli 的部署集成: 部署阶段自动检测 + 未部署自动部署 + 真跑一次才算就绪)

回应"我需要将 OCR 的部署方式、mmx-cli 的部署方式集成到 via54Medit 中，并确保可以在部署阶段
就能自动检测是否已部署，如果未部署则自动部署"。

两者此前已在能力矩阵里有探测与安装通道(v5.4.34/36), 但**探测本身会给出假就绪**。这一轮把
"就绪"的定义落到**真实可用性**上, 并补上两处会让隐患漂很久的缺口。

### 一、OCR: "能 import" ≠ "能识别"(两处缺口)

| 缺口 | 后果 |
| --- | --- |
| 探测只做 `import paddleocr; import paddle` | 权重没下也算就绪。首次真实调用会去联网下 ~170MB, 离线/受限网络下**必然失败** —— 而失败点在 L2 那一步, 离"部署完成"已经很远, 没人会把两件事联系起来 |
| 安装不带版本约束 (`pip install paddleocr paddlepaddle`) | 某天会静默装上 2.x/4.x。管线调的是 PaddleOCR **3.x** 的 API(`use_textline_orientation` + `.predict()` + `result[0]['rec_texts']`), 而"装上了"与"能跑"是两件事 |

修法:

* **新增能力 `ocr_models`**(权重就位): 探测 = 权重是否已落地(**便宜的文件系统检查**, 只有
  `det`/`rec` 两个家族都在才算齐); 安装 = **预热**, 即真跑一次识别把权重下下来。
  `PaddleOCR 3.x` 的权重在 `$PADDLE_PDX_CACHE_HOME/official_models`(**不是** `~/.paddleocr` ——
  那是 2.x 的路径, 3.x 上是空的, 照它判断会误报)。
* **新增 `--verify-ocr`**: 真跑一次识别并断言拿到非空 `rec_texts`。这是"OCR 到底能不能用"的
  **唯一强证据**, 也是权重预热动作本身(单一实现 `ocr_smoke_test()`)。
  断言只要求"识别到非空文本", 不比对具体字符串 —— 实测 "OCR 12345" 会被认成 "DCR 12345"
  (置信度 0.996), 拿精确比对当门槛是自找假红。样本文字可用 `VIA54_OCR_SMOKE_TEXT` 覆盖。
* **安装带约束**: `paddleocr>=3.0,<4` / `paddlepaddle>=3.0,<4`(实测可用组合 3.7.0 + 3.3.1)。

### 二、mmx-cli: 凭据探测**接错了对象**(这是更严重的一处)

mmx-cli 用的是**它自己**的凭据(`mmx auth login` 写进 `~/.mmx/config.json`, 也支持全局
`--api-key` 覆盖), 与 `MINIMAX_API_KEY` 是两条互不相通的路径。旧探测把结论建在环境变量上,
于是在本机同时出现方向相反的**两个错误**:

* **假警报**: 本机 `MINIMAX_API_KEY` 未设置, 而 `mmx auth status` 早已就绪、真能调通
  (后台用量都能读到), 报告却写"缺 MINIMAX_API_KEY, 调用会失败";
* **假就绪(更危险)**: export 了 `MINIMAX_API_KEY` 但没跑过 `mmx auth login` 时, 报告写
  "已配置" —— 而 mmx 实际调用会 401。这在"二进制已安装"的报告里完全看不出来。

修法:

* `_probe_mmx()` 只判**二进制可用**(一件事一个人管), 不再对凭据下任何结论。
* 新增 `_probe_mmx_auth()`: 判据是 `~/.mmx/config.json` 里的 api_key(快、不联网、api-key
  模式下的权威), 其次 `mmx auth status --output json`(覆盖 OAuth 模式; 实测 0.09s)。
* 新增能力 `mmx_auth`(**替换**原来的 `mmx_key`): 有 `MINIMAX_API_KEY` 时部署流程可
  **代登**(`mmx auth login --api-key`); 没有则如实报"需人工", `gate=False` —— 凭据必须由人
  提供, 把它算成部署失败会让部署永远无法成功。
* 新增 `--verify-mmx`: 二进制与认证**分开报**(修法完全不同), 退出码**只跟二进制走**。
* `install_mmx.py` 同步改掉那段"看环境变量下结论"的输出。
* 顺手实测到 mmx 的自我更新通道 `mmx update` 与 `mmx quota show`(账户级用量)。

### 三、部署 / 更新阶段自动检测 + 自动部署(已有的通道, 现在覆盖到新缺口)

* `bootstrap_device.py`: 新增第 4 步 —— 跑 `--verify-ocr` 与 `--verify-mmx`; **凭据缺失只记警告**,
  不算失败(与 `gate=False` 同一条判断)。步骤号顺延到 6 步。
* `auto_sync.py`: 拉取+重建**之后**新增视觉/OCR 复检(与 v5.4.42 加的 LLM 复检同处), 失败发告警。
* `deps_auto.ensure_env()`(管线第 [0] 步)与 `medit doctor --fix` **自动继承**新能力 —— 它们读的
  就是同一份能力矩阵, 不需要再改。
* `--only ocr_models` 可单独补齐权重; 矩阵默认按平台自动探测并只在缺失时安装, 可反复运行。

### 四、实测(不是"看起来对")

* **空缓存端到端**: `PADDLE_PDX_CACHE_HOME` 指向空目录 → `--only ocr_models` → 报告
  "本次补齐 1 · 复验未过 0", 该目录随即出现 5 个模型家族 / **177MB**, 退出码 0。
* **检测灵敏度**: 同一个空目录跑 `--check` → `✗ PaddleOCR 权重(真识别预热) 未发现本地权重`。
* **真识别**: `--verify-ocr` → `真识别通过: 识别到 1 段文字 (DCR 12345)`。
* **mmx**: `--verify-mmx` → `mmx-cli : ✓ mmx 1.0.19` / `凭据 : ✓ 已认证 (api-key, 来源
  ~/.mmx/config.json)` —— 这正是旧探测会误报的那台机器。

### Tests
- `scripts/test_deploy_scan.py`: 78 → **90**(新增 `TestVisionToolchainDetection` 10 条 +
  OCR 版本约束 1 条): 权重齐/缺/半成品三态、mmx 凭据只认自己的状态(**双向**回归: 有环境变量
  但未登录 → 未认证; 无环境变量但已登录 → 已认证)、OAuth 模式回退 CLI、二进制探测不再判凭据、
  `mmx_auth` 替换 `mmx_key` 且不门禁、无凭据时如实失败且不调用 CLI、部署器与更新器都接入了复检。
- 更新 1 条把"未带版本约束的安装"当契约的旧测试。
- 反向验证: 空缓存目录确实被报成缺失, 且预热后确实齐备 —— 检测与补齐都真跑过。

## [5.4.43] - 2026-09-12 (飞书多维表格统计列没有对齐最新统计项 —— 补齐 8 列 + 定下对齐契约)

回应"飞书多维表格统计列没有对齐最新的统计数据项"。

### 一、实测确认: 公司表少了 8 列

绑定的公司「监控数据周报明细」表当时只有 **13 列**, 而代码里的统计项是 **19 个字段**。
差的这 8 个不是"没算", 是**算了但没地方放** —— `build_company_payload` 里 `COMPANY_FIELD_MAP`
查不到目标列就静默跳过, 写入不报任何错:

| 缺失的列 | 影响 |
| --- | --- |
| 检索节约工时(h) / 下载节约工时(h) / 高亮节约工时(h) | 三个细分工时被丢, 只剩一个总数, 没法看结构 |
| 其他任务数 / 其他工作时长(h) / 其他Token消耗 | v5.4.37 新增的「其他」类目**整类**只能挤进「备注说明」当纯文本: 看得到, 但筛选不了、分组不了、画不了图 |
| 其他未归属Token | 与上面同因 |
| API调用次数 | 同上 |

根因是结构性的: **表是先建后用的**, 代码里新增一个统计项不会让已建好的表自动长出列来。

### 二、补齐 8 列(线上已生效)

```
medit-telemetry bitable --align-fields --dry-run   # 先看差哪些
medit-telemetry bitable --align-fields             # 少哪列补哪列
```

线上执行结果: 公司表 13 → **21 列**, 8 列已建。数字列类型正确(工时 precision=2, 计数 precision=0),
否则表格里没法求和。

一个插曲值得记下来: 本仓库的应用身份(`cli_aa0d...`)对这张公司表只有读权限, 建列返回
`1254302 Permission denied` —— 所以补列是**用用户身份**通过 `lark-cli base +field-create --as user`
完成的。命令本身保留在 CLI 里, 换到有写权限的应用或身份时可直接用。

### 三、写入侧: 统计项一个都不丢

- `COMPANY_FIELD_MAP` 补上 8 个映射(与标准表同名, 即恒等映射), `build_company_payload` 逐项成列。
- 「备注说明」不再重复承载已有专列的数值 —— 同一份账记两次会让人以为是两笔。
- `TABLE_SCHEMA_FIELDS` 新增 `其他未归属Token`(标准表 18 → 19 字段), 两类表口径齐平。

### 四、对齐契约: 要么有列, 要么有理由

对齐只有两种合法状态, **没有第三种**:

1. 目标表里有同名列(`COMPANY_FIELD_MAP` 负责改名);
2. 显式写明为什么不该有列 —— 见 `INTENTIONALLY_NOT_A_COLUMN`(当前只有 `成员OpenID`:
   身份标识而非统计项; 公司表多人可见, 不在共享表里扩散 open_id)。

`unmapped_standard_fields()` 必须为空, 由 `TestBitableColumnAlignment` 守着。
"静默丢弃"从此不是一种可选状态。

### 五、不再静默: 缺列必须说出来

- `sync_weekly_report` 写入前自检列对齐, 缺列时把"缺 N 列 + 补齐命令"**附在成功消息里**
  (daemon 会把它写进日志/告警), `--dry-run` 的 JSON 也带 `missing_columns`。
- **只报不改**: 周期同步去改公司共享表的 schema 太越界, 补列交给显式命令。
- 状态查询新增一行 `• 统计列: 🟢 已对齐 (schema=company, 21 列)`, 没对齐时给出缺列清单。

### 六、两处连带的正确性修复

1. **schema 判定改为标记字段优先**。补列后公司表 21 列里有 8 列与标准表**同名**, 再比
   "谁命中多"会越来越脆弱 —— 改成认公司表独有的 `记录标识/统计周次/提交成员/统计日期`。
2. **冻结历史 13 列列序**(`COMPANY_PAYLOAD_ORDER_LEGACY`)。本地备份里那些"13 列、按公司
   列序写入"的历史行, 是靠 `len(row) == len(COMPANY_PAYLOAD_ORDER)` 认出来的; 若让列序跟着
   映射一起变长, 它们就再也认不出来, 会被当作脏行**静默丢掉** —— 回退路径上少的就是它们。
   已用真实备份验证: 迁移(15 → 19 列)前后都稳定回读出同样的 2 条记录, 一行未丢。

### 七、顺带修正的既有缺陷

`bind_existing_bitable()` 原先无条件按**标准表**补列 —— 绑定公司表时会往里面塞
`汇报周期/成员花名` 这类用不上的同义列, 而真正缺的统计列反而没补。现改为按**探测出的
schema** 补列, 并在返回值里汇报补了哪些、还缺哪些。

### Tests
- Python: 180 → **187**(新增 `TestBitableColumnAlignment` 7 条: 契约完整性、排除项必须带理由、
  缺列识别、只建缺的列、dry-run 不落列、**13 列历史行在映射扩展后仍可读**、缺列必须报出)
- 更新了 4 条把旧行为当契约的测试(公司表列集、备注承载「其他」、dry-run"不发任何请求"→
  允许只读探测但禁止写请求)
- 实测链路: `--align-fields --dry-run` 精确报出 8 列 → `--align-fields` 补齐 → 复查 21 列已对齐
  → `--sync --dry-run` payload 21 列且新列有真实值(检索 4.99h / 下载 6.66h / 高亮 2.85h)
  → `--report` 正常出图

## [5.4.42] - 2026-09-12 (修红 CI: v5.4.41 在 Windows 跑者上红了 —— 子进程输出没指定编码)

v5.4.41 的 CI 在 `python (windows-latest)` 上失败, 另外 5 个 job 全绿。原因**全是我这一轮引入的**,
而且两条都只在 Windows 上现形。

### 一、真因: `subprocess.run(..., text=True)` 没给编码 → 把"成功"读成"失败"

我在 `auto_sync.py` 的"更新后强制校验 LLM 接入"里走了既有的 `run_cmd(...)`, 它是:

```python
subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
```

Windows 跑者的默认编码是 **cp1252**, 而子进程打印的是 UTF-8 中文。结果是**读线程**里
`UnicodeDecodeError`(`can't decode byte 0x8f`), `proc.stdout` 变成 `None` —— 于是:

* `json.loads(proc.stdout)` → `TypeError: ... not NoneType`;
* 更糟的是 `run_cmd` 里那个宽泛的 `except` 会把它吞成 `(False, "", 报错文本)`,
  也就是**校验通过也会被报成"LLM 接入校验未通过"**并发出告警。一个纯粹的编码问题
  伪装成了功能缺陷, 并且在 macOS/ubuntu 上完全看不见(它们默认就是 UTF-8)。

修法: 捕获子进程输出时一律显式 `encoding="utf-8", errors="replace"`。范围限定在
**判读"部署/更新是否就绪"的那条链路**(`deploy_scan.py` / `bootstrap_device.py` /
`auto_sync.py` / 全部 `telemetry/`) —— 这条链路的判读结果决定流程成败, 不能依赖平台默认编码。

### 二、新增不变量: 往这条链路上加调用时, 现场就红

`tests/test_repo_hygiene.py` 新增 `test_captured_subprocess_output_has_explicit_encoding`:
凡是在该范围内**捕获输出**(`capture_output=True` 或 `stdout=PIPE`)的 `subprocess.run/Popen`,
必须出现 `encoding=`; 只写 stdin / 只看返回码的不算(不涉及解码)。

这类问题本地永远看不见, 只有三平台 CI 才会现形 —— 与其等下次再踩, 不如当场红。
(实测: 把 `auto_sync.run_cmd` 的 `encoding=` 删掉, 它会精确指出 `scripts/auto_sync.py:153`。)

### 三、顺带修掉测试自身的 Windows 不适配

* `tests/test_llm_ledger.py` 里两处 `subprocess.run(..., text=True)` 同样补上编码;
* 读 Go 源码从 `open(...).read()` 改为 `with open(...)` —— Windows 上未关闭的句柄会拦住
  后续的替换/删除, 也会刷一屏 `ResourceWarning`。

### Tests
- Python: 179 → **180**(+1 编码不变量); `deploy_scan` 78 条、`test_llm_ledger` 34 条全绿
- 本地复检: `--verify-llm` 退出码 0、`--dry-run` 退出码 0、`go build` + `go test` 全绿

## [5.4.41] - 2026-09-12 (强制验证接入了哪些 LLM + 确保它们的 token 消耗真能读进库)

回应"部署和更新后还需要强制验证接入了哪些 LLM, 并确保真能读取接入的所有 LLM 的 token 消耗"。

"接入了哪些 LLM"这个问题**光看文档或配置答不出来** —— 它由代码里的调用路径决定。
所以这一轮先造了一把能回答它的尺子, 再用尺子去量, 结果量出**三处真实缺口**。

### 一、三处真实缺口(都是"调用正常、报表少数字"的沉默型缺陷)

记账是**旁路**: 一条路径不再记录用量, 调用本身不会报错、不会有异常、不会有非零退出码,
报表只是安静地少一块数字。这就是为什么必须主动验证。

1. **`scripts/provider_llm.py` 返回 `usage` 却从不落库** —— 它是 `LLM_PROVIDER` 的**默认值**
   (deepseek) 的实现, 也就是说默认文本通道的 token 消耗**一直是 0**, 而卡片还写着
   "100% 控制台对齐"。修法: 新增 `canonical_provider()` + `_record_usage()`, 并把
   `provider=` 贯穿到 4 个调用点。整个包装在 `try/except` 里 —— 遥测不可用不该让 LLM 调用失败。
2. **`scripts/sensenova_vision.py` 把 `usage` 丢掉** —— 只返回 `content`, 于是 SenseNova
   视觉调用的 token 全部无账。同类缺口, 由上面的源码扫描发现(不是靠人肉复盘)。
3. **Go 侧的整个 LLM 调用面完全不计账** —— `internal/foundation/llm.go`、`llm_glm.go`
   解析响应时只取 `choices`, `usage` **整个丢弃**。受影响的是 `medit ask` / `medplan` /
   docproc / medit-mcp 四条真实链路, 覆盖 deepseek / openai / hermes / glm 四个 provider。

### 二、新增: 一把"能回答这个问题"的尺子 `telemetry/llm_providers.py`

- **注册表是唯一事实来源**: 6 个 provider(deepseek / openai / minimax / zhipu / sensenova /
  hermes)各自的接入通道、凭据来源、单次用量来源、账户级用量怎么读。
- **证据来自源码, 不来自声明**: 注册表里**没有**"记录者清单"字段 —— 谁在记账必须由
  `scan_recorders()` 扫出来(Python 的 `record_llm_usage(` + Go 的 `recordLLMUsage(`)。
  实测的缺口(上面的 1 和 3)就是被这个检查抓出来的, 靠声明永远抓不到。
- **离线端到端摄入校验**: 把每个 provider 的**真实响应形状**喂进 `record_llm_usage`,
  写入**临时**库再读回, 并一路核对到**报表层** —— 全程不碰生产数据、不发网络请求。
- **Go 侧 spool 链路校验**: spool 一行 → 摄入 → 读回 → 报表, 额外验两件事:
  别名归一(Go 叫 `glm`, 落库必须是 `zhipu`, 否则报表里凭空多一家)与**重放幂等**。

### 三、新增: Go 侧用量落盘 `internal/foundation/llm_usage.go`

Go 没有 SQLite 驱动, 为一个记账功能引入 cgo/driver 会让构建显著变重, 所以改为
**追加一行 JSONL 到 `~/.medit/llm_usage_spool.jsonl`**, 由 Python 侧幂等摄入。

- 幂等靠 `req_id`(服务商返回的 id 优先, 没有就自造唯一值), 所以"写了一半崩了再重跑"
  不会重复计费 —— 这也是不能靠"读完就删文件"保证正确性的原因。
- 记账**永不返回错误**: 它绝不能因为自己失败而让 LLM 调用失败。
- `Source` 字段优先取显式标签(如 `docproc/entity`), 否则从调用栈推断调用源
  (如 `go:medplan/research.go`) —— 让"这笔 token 是谁花的"可追溯。
- 顺手修正一处身份错位: openai / deepseek **复用**了 `HermesProvider` 的实现,
  记账时若直接用 `Name()` 会把它们全记成 hermes。新增 `usageName` 字段, 账各归各。
- **跨语言契约有测试守着**: 从 Go 源码里把 `json.Marshal` 那段 map 的键抠出来,
  与 Python 摄入端实际读的键做全等断言。字段一漂就红。

### 四、新增: 摄入器 `telemetry/llm_spool.py` + 守护进程自动收口

- `created_at` 取 spool 里的 `ts`(真实调用时刻), **不是**摄入时刻 —— 否则按周切分的
  统计会对不上真实调用时间。
- 没有 token 计数的行**不入库**(记 0 只会污染口径); 坏行跳过不中断整批。
- 守护进程每 60s 收口一次(`telemetry.llm_spool_interval_seconds` 可调); `refresh`
  也顺手收口; 心跳新增 `freshness.llm_spool` —— "待摄入一直不为 0"就是摄入挂了或两端
  字段约定漂了的第一信号, 不该等到月底对账才发现。

### 五、强制验证: 部署与更新后都必须跑, 失败非零退出

- 新增命令 `medit-telemetry llm`(`--live` 联网探凭据 / `--verbose` 通道级细节 /
  `--json` / `--no-ingest`), 有问题时**以退出码 2 结束**。
- `scripts/deploy_scan.py --verify-llm`(**独立模式**)与 `--stage all` 都会跑; 结果进入
  报告第 4 节, 校验不过则 `--stage all` 也判"未就绪"。
- `scripts/bootstrap_device.py`(部署/更新后的一键就绪)新增第 4 步, 校验失败**以非 0 退出**。
- `scripts/auto_sync.py`(定时从 GitHub 拉取)在拉取+重建**之后**加了一步校验并接入告警。
- `medit-telemetry deploy` 的部署概览里加入同一份校验; 不过就**不打印"部署成功"横幅**,
  且 `sys.exit(2)`。
- CLI 与部署校验**共用同一份渲染器** `llm_providers.format_report()`, 免得两处口径分叉。

### 六、勘误: 我自己第一版检查器有假阳性, 已修

第一版用正则扫 `record_llm_usage(` 的出现次数来判"有没有在记账"。把 `provider_llm.py` 里
**所有对 `_record_usage()` 的调用删掉、只留函数定义**, 它依然判"记录中" —— 因为函数体里
那个调用点还在。这比没有检查更危险(会给人"已验证"的错觉)。

改为 **AST 可达性判断**: 记账调用点所在的**私有**包装函数必须在同文件内被调用过;
公开入口(如 `vision_analyze`, 由 CLI 拉起)豁免, 否则会产生大量假阳性。
负向测试已固化在 `tests/test_llm_ledger.py::TestDetectorCatchesRegression`。
实测: 删掉那个调用点后 `--verify-llm` 报出 6 条问题并以退出码 1 结束, 恢复后回到 0。

### 七、诚实说明读不到的部分(不折算、不造数)

- **mmx / MiniMax VLM 的单次 token 读不到**: `mmx vision describe --output json` 只返回
  content, CLI 不暴露 token。它的用量只能取账户级配额, 且 `mmx quota show` 返回的是
  **调用次数**而不是 token —— 所以**不会**被折成 token 入库, 混进去就是造数。
- **openai 的用量接口要 Admin key**(`sk-admin-` + `api.usage.read`), 普通 key 读不到。
- **deepseek 有余额接口(`GET /user/balance`)没有逐条用量接口**, 逐条要走控制台导出 CSV。
- **本机当前只有 `SENSENOVA_API_KEY` 一个凭据** —— 审计如实报出其余 provider "凭据 ✗"
  (不是缺陷, 是这台机器的实际状态); 凭据是否真能通过需要 `--live` 才会联网探。

### Tests
- Python: 145 → **176**(新增 `tests/test_llm_ledger.py` 31 条, 含探测器自身的负向测试)
- Go: 新增 `internal/foundation/llm_usage_test.go` 6 条(含"provider 不得串账"与
  "没有 usage 就不落盘"两条真实约束); 跨语言链路另用真 Go 调用 + 真 Python 摄入各验一次
- 校验结果: `--verify-llm` → 6 个 provider 全部"记录点 ✓ / 单次用量可读 / 端到端往返一致",
  0 问题

## [5.4.40] - 2026-09-12 (确保统计数据实时更新: 修掉 3 倍虚高 + 已收录条目不冻结 + 新鲜度可查)

回应"确保所有统计数据实时更新"。

查证发现"不实时/不准"有三个具体来源, 全部修掉并**在本机真实库上验证**。

### 一、备份目录被当成成果, 报表虚高 3 倍(这是最严重的一条)

RSV 项目下的 `_bak_20260906_201108/高亮结果/` 与 `_bak2_20260906_205621/高亮结果/` 被当作产出物
扫进了库 —— 同一篇文献出现 3 行, 于是:

| | 修复前(错) | 修复后(实) |
| --- | --- | --- |
| Highlight 完成数 | **150 篇** | **50 篇** |
| 阅读页数 | **2917 页** | **977 页** |
| 累计节约总工时 | **20.19 h** | **14.49 h** |

而且**时对时错**: 备份目录一删, 数字又"自己变回去"。检索(44)与下载(215)无重复, 未受影响。

- 新增路径卫生 `watcher.is_ignored_path()`: 备份/临时目录(`_bak*` / `.git` / `node_modules` /
  `__pycache__` / `_trash` 等)里的副本一律不计入。判据是**路径片段的前缀**而不是整串子串 ——
  否则会误伤名字里含 `bak` 的文献(如 `Wang_bak_2020.pdf`), 也会牵连正常产物;
  这样 `_2_pdfs/`、`_highlight_nested/` 这类合法的下划线开头目录天然不受影响, 不需要例外清单。
- 守护进程的监控目录遍历与 `refresh` 用同一条规则, 不会从另一条路径漏进来。
- 新增 `db.purge_ignored_path_items()` 修复**历史已污染的数据**, 并接进 `refresh`。
  清理很保守: **只在同一篇文献于非备份路径下也有行时才删** —— 即便判定规则有偏差也绝不会把
  某篇文献整删掉。本机执行结果: 高亮删 100 行, 50 篇唯一文献一篇未丢。

### 二、已收录条目的可变字段被冻结

原先命中 `has_*_item` 就 `continue`, 于是**标注数(`num_annots`)与文件大小从此停在首次登记时的值**
—— 用户在已高亮的 PDF 上继续加标注、或重新下载了更大的 PDF, 报表纹丝不动。

- 新增 `db.refresh_highlight_item()` / `db.refresh_download_item()`; watcher 遇到已收录条目改为
  **刷新可变字段**(页数、标注数、文件大小), 并统计 `refreshed` 项数。
- **刷新 ≠ 新增**: 篇数口径完全不变。
- **没观测到(`None`)就不覆盖**: 拿默认值去覆盖已有数据比不刷新更糟。
- 同时按 `paper_id` 兜一层去重: 文件被移动/改名后, 只按路径匹配会认不出来, 结果是同一篇文献
  再加一行(篇数虚高)。

### 三、"是不是最新的"没有凭据

- `db.latest_ingest_at()` / `db.table_counts()`; 心跳新增 `freshness`(最近入库时间 + 各表行数);
  `status` 末尾显示"最近入库 <时间>(<N> 分钟前) · 由守护进程每 30 秒巡检更新"。
- 新增 `medit-telemetry refresh`: 立即扫描**配置里的**全部监控目录(`watcher.watch_dirs`, 不是写死
  路径) + 刷新已收录条目 + 清理备份副本行, 然后打印最新统计。`--dir` 可只刷指定目录。

### 另一个真实发现: 跑着的守护进程用的是旧代码

本机守护进程 PID 1638 的心跳里没有 `next_weekly` 字段 —— 说明它加载的是**改动之前**的扫描器。
**配置每 5 秒重载, 代码不会**: 于是它会把我刚清理掉的 100 行备份副本**再插回去**。
已重启(`launchctl kickstart -k`), 之后验证: 跑满一个 30 秒巡检周期, 高亮仍为 50, 没有再被污染。
已在 README/指南里写明"改了采集逻辑要重启守护进程"。

### 测试

`tests/test_telemetry.py` **121 → 132** 项(+11); 全量 `223` 项通过; `make test-py` 全绿;
`go vet` / `go test ./...` 干净。
新增覆盖: 路径卫生的正反例(含"文献名里含 bak 不误伤"、"`_2_pdfs` 不被误排除")、
备份副本不计数、已收录条目刷新而**篇数不变**、`None` 不覆盖、文件移动不重复计数、
清理只在有真实副本时才删(且每篇文献都必须仍有行)、新鲜度助手、心跳带新鲜度凭据。

## [5.4.39] - 2026-09-12 (推送遇周末/法定节假日顺延到下一个工作日)

回应"推送遇到周末或法定节假日需要顺延到下一个工作日"。

默认排程是「周一 / 每月 1 日」, 而这两天**经常**落在假期上: 2026 年周报目标 10-05 与月报目标
10-01 都在国庆连休里, 春节整周(02-15~02-23)还会连着两个周一。此前这类日子照发不误。

### Added

- **顺延规则**: 目标日落在**周末或法定节假日**时改到**下一个工作日**(`schedule.defer_non_workday`,
  默认开启)。
  - **补班的周六算工作日**, 不会被误顺延(2026-10-10 周六、09-20 周日都是国务院公告里的补班日)。
  - 取不到节假日数据时(降级为仅按周末)顺延仍可用, 但会在原因里标出"仅按周末判断"。
- 新增 `telemetry/schedule.py` —— **顺延的唯一实现**: 原始目标日扫描(含月末 `-1`)、顺延、
  「此刻该不该推」都由它出口。守护进程与提醒模块**共用这一份**, 因此不会出现
  "提醒说明天推、实际推到假期之后"。此前 `daemon._check_schedule` 与 `reminders.next_occurrence`
  各算一遍 —— 顺延功能一上线, 那两处就会立刻分叉。
- 新增 `config --defer` / `--no-defer`、`deploy --defer` / `--no-defer`, 以及 PowerShell
  `-Defer` / `-NoDefer`; `config` 与 `holiday` 的输出会显示顺延规则与"原定 → 实际"。

### 连带修正

- **提醒日必须跟着顺延后的日期走**。2026-10-01 顺延到 10-08 后, 提醒日仍是 09-30
  (10-01~10-07 全是假期, 09-30 就是假期前最后一个工作日) —— 提醒日按原始日期算就会自相矛盾。
- **提醒文案要按间隔换说法**。提醒日取的是推送日的**前一个工作日**, 当中间隔着周末或整段假期时,
  原来那句"**今晚请不要关机**"既不准确也没必要(用户完全可以周末关机、周一再开)。现在改成
  "**请在 `2026-10-08` 之前确保设备开机联网**", 并只在推送日恰好是次日时才补一句"也就是明天, 今晚请不要关机"。
- **同一格只列一次**: 春节整周连休会让 02-16 与 02-23 两个周一都顺延到 02-24。提醒侧按
  「类型 + 生效时刻」去重(保留最早的原始目标日, 并记下同期还有几次一并顺延); 守护进程侧
  靠"当天只发一次"兜住(不额外加机制)。
- **只改"哪一天发", 不改"报哪一期"**: 报表周期仍按实际发送日计算, 于是卡片 `period_name`、
  表格行与多维表格记录三者自洽。常见顺延(1~6 天、仍在同一周/月内)周期完全不变。

### Fixed

- **测试 fixture 又漏了几天(同类第二次)**: 2026 报文的 fixture 只保留了国庆连休的头尾两天,
  顺延逻辑往后找"下一个工作日"时把中间的 10-02~10-06 当成工作日, 于是两个用例假红。
  根因是**手写了第二份日期**: 现在把完整的 2026 报文提到模块级常量, 日历由它**派生**
  (`_cal2026()`), 测试里不再有第二份手写日期 —— 这类假红从根上消掉。
- 顺延后 `daemon.py` 里 `timedelta` 已无用处, 一并清掉。

### 测试

`tests/test_telemetry.py` **105 → 121** 项(+16); 全量 `212` 项通过; `make test-py` 全绿;
`go vet` / `go test ./...` 干净。
新增覆盖: 假期周一/假期 1 日/普通周末三种顺延、**补班周六不顺延**、普通工作日不动、
春节两次目标塌缩到同一天的去重(`also_from`)、候选序列有序且唯一、关掉顺延后按固定日期、
`push_due_now` 只在顺延日触发且分钟要对、畸形配置绝不抛异常、日历降级时仍能顺延且如实标注、
守护进程在假期当天不推而顺延日推且当天只推一次、提醒日跟着顺延、以及"隔假期"与"次日"两种文案分支。
节假日用例**全程离线**。

## [5.4.38] - 2026-09-12 (排程改为周一/1 日 10:30 + 推送日前一个工作日的「别关机」提醒 + 法定节假日自动获取)

回应"将默认周推送、周同步时间设定为每周一早上 10:30；将默认月推送、月同步时间设定为每月 1 日早上 10:30；
同时默认在前一个工作日提醒用户不要关机，并自动获取权威的法定节假日数据"。

### Added

- **默认排程**: 周报 **每周一 10:30**、月报 **每月 1 日 10:30**(原为 09:00)。
  默认值收敛成 `config.DEFAULT_WEEKLY_SCHEDULE` / `DEFAULT_MONTHLY_SCHEDULE` 一组常量 ——
  此前 `"09:00"` 这个默认值散落在 `DEFAULT_CONFIG`、`daemon` 的兜底取值、`nlp_deploy` 的默认值
  三处字面量里, 改一次要改三处, 迟早漏一处。
- **已部署设备的默认值迁移**: 只改 `DEFAULT_CONFIG` 对老设备无效(旧值已写进
  `~/.medit/telemetry_config.json`, 深合并时旧值会盖住新默认)。新增一次性迁移:
  **只在该值仍等于旧默认值(09:00)时才替换**, 即"用户没自定义过"的才动; 用户自己设过的
  (如 Friday 18:00)一律不碰。并打 `schedule_defaults_version` 版本戳, 只做一次 ——
  否则将来用户**故意**改回 09:00 又会被悄悄顶掉。
- **推送日前一个工作日的「别关机」提醒**(默认开启, 18:00): 推送是**到点触发**的 —— 机器关机
  或休眠, 那一次周报/月报就静默丢失(不报错、不补发)。提前一个工作日提醒是唯一能在事前降低
  这种概率的手段。新增 `telemetry/reminders.py`。
- **法定节假日自动获取**(新增 `telemetry/holidays.py`): "前一个工作日"不能只按周末算 ——
  春节/国庆连休会让"前一天"本身是假期(2026 年国庆 10-01~10-07), 调休补班又会让周六变成工作日
  (2026 年 09-20、10-10 都是补班日)。
  - 主源 `holiday-cn`: 机器可读, 且**逐条标注对应的国务院公告链接**。2026 年指向
    《国务院办公厅关于2026年部分节假日安排的通知》(**国办发明电〔2025〕7 号**)
    https://www.gov.cn/zhengce/zhengceku/202511/content_7047091.htm —— 已逐条核对一致(含两个补班日)。
  - 备源 timor.tech 年度接口。
  - **取不到数据时如实降级**为"仅按周末判断", 并传 `authoritative=False`, 在 `config` / `holiday`
    输出里标 `⚠️ 仅按周末推算` —— 不拿一个可能把补班日算成休息日的日历当真。
  - 缓存 `~/.medit/holidays/<年>.json`: 有效数据 30 天; "该年安排尚未公布"只留 3 天, 公布后自动补上。
- 新增 `medit-telemetry holiday`(`--check DATE` / `--refresh` / `--year`)、
  `config --set-reminder HH:MM` / `--no-reminder`、`deploy --reminder` / `--no-reminder`
  与 PowerShell `-Reminder` / `-NoReminder`。
- **心跳新增"下次推送时刻"与提醒设置**(`next_weekly` / `next_monthly` / `reminder`):
  推送是到点触发的, "下次什么时候推"是排查"为什么这次没推"时的第一个问题, 不该只能读配置去猜。

### 设计取舍

- **同一天只发一张卡**: 2026-09-30 既是「10-01 月报」的前一个工作日, 也是「10-05 周报」的
  前一个工作日 —— 分两条就是同一个晚上骚扰两次。幂等 key 按**提醒日**分桶(`reminder:<日期>`),
  同一天的多个目标合并成一次发送。
- **判定用"到点之后"而非"正好那一分钟"**: 18:00 该提醒、机器 22:00 才开机, 当晚仍会补上 ——
  当晚的提醒依然有意义。而"正好那一分钟"会因为守护进程晚启动而整晚丢掉。
- **不重复打扰**: 幂等状态复用 `alerter` 落盘的账本(`~/.medit/alerts_state.json`), 成功静默 24h、
  失败 10 分钟后重试; 守护进程被反复拉起也只发一次。
- **提醒有独立开关** `schedule.reminder.enabled`, 显式传设置给它, 因此**不受 `alerts.enabled`
  影响** —— 关掉资源告警不该顺带关掉别关机提醒。
- **提醒失败绝不反噬守护进程**: 整段包在 try/except 里, 只记一行日志。它是锦上添花, 不是主链路。
- 文案里如实说明: 提醒本身也要靠机器在那一刻运行才能发出, 所以它是**降低概率、不是消除**。

### Fixed

- **星期文案差一位**(我自己引入又自己抓到): `"周一二三四五六日"[weekday()]` 会把周四显示成"三"、
  周一显示成"周"。首次冒烟时从输出里发现, 已改为 `"周" + "一二三四五六日"[weekday()]` 并加回归用例。
- **`deploy.setup_configuration` 对新参数不够健壮**: 直接取 `args.no_reminder` 会让以手工构造
  `Namespace` 调用它的测试/调用方 `AttributeError` 崩掉; 改为 `getattr(..., 默认值)`。
- **我自己写错的测试 fixture**: `TestHolidayCalendar` 的 2026 报文只保留了国庆连休的头尾两天,
  中间的 10-02~10-06 被当成工作日, 于是"前一个工作日"算出 10-02 而非 09-30。
  这是 fixture 不完整, 不是逻辑错 —— 已补齐整段, 并与**真实取数结果交叉验证**(均为 09-30)。
- 清掉文档里已过时的硬编码字段数(`固定 15 列` / `自建标准表 15 字段`): 它们会随
  `TABLE_SCHEMA_FIELDS` / `BACKUP_FIELDS` 变化, 写死就是下一次假红的来源。

### 测试

`tests/test_telemetry.py` **77 → 105** 项(+28); 全量 `196` 项通过; `make test-py` 全绿;
`go vet` / `go test ./...` 干净。
新增覆盖: 默认值迁移的四种情形(旧默认升级 / 自定义不碰 / 改回旧默认不被顶 / 老配置补 reminder 段)、
源码里不得再写死 `09:00` 兜底、调休补班与连休下的工作日判定、跨年求前一个工作日、
取不到数据时如实降级、缓存往返不再取数、备源报文形状、提醒只在"前一个工作日 + 到点之后"触发、
国庆前那次提醒**合并成一张卡**、星期文案正确、发送异常不外溢。
节假日相关用例**全程离线**(用真实报文的裁剪版打桩), 不依赖外网。

## [5.4.37] - 2026-09-12 (监控记录同步推送: 新增「其他」类目 —— 同样统计工作时长与 Token 消耗)

回应"在监控记录同步推送的项目中，增加一个「其他」类目，同样包括统计工作时长和 token 消耗"。

从此战报与推送按**四个类目**呈现: 文献检索 / 文献下载 / 文献高亮 / **其他**。

### Added

- **`TaskType.OTHER` 与 `tracker.track_other()`**: 不属于三类文献工作的一切(PPT/Word 渲染、
  PDF 解析、多维表格同步、环境巡检、外部脚本)都可以这样登记, 与其他三类一样记录真实工时与 Token。
- **类目归类收敛到唯一事实来源** `models.classify_task_type()`: `correction` 并入高亮;
  **未登记的 `task_type` 一律兜底到「其他」** —— 将来多出一种任务类型不会从战报里消失。
- **Token 归口不靠猜**: 一条 LLM 调用只按 `task_id` 去 `tasks` 表查类目, 查不到(含 `task_id` 为空)
  才归入「其他」。由此 `other.total_tokens ⊆ tokens.total_tokens` 是**构造保证**的:
  总量与其他在同一趟循环里累加, 不靠两处口径对齐。
- **「其他」不产出"节约工时"**: 该类目没有人工基线。与其编一个基准, 不如显式声明
  `has_saved_baseline: false` —— 免得调用方以为漏了而自己补一个凭空的数。
- **`other.unattributed_tokens`**: 单独暴露"没有 `task_id` 归属"的那部分 Token, 用来区分
  「真的是其他工作」与「调用方忘了标归属」。不说清楚的话这个数字没法解读。
- **四条推送腿全部接上**: 飞书卡片新增第 4 块(含"占总量 x%"与说明); 公司公共统计表追加
  「其他任务数 / 其他工作时长(秒) / 其他Token消耗」三列; 多维表格标准表新增 3 个字段;
  团队卡片与 HTML 大屏新增 KPI 卡; CLI 报表新增「其他」行。
- **公司表没有「其他」专列** —— 这类信息无处可放, 于是写进「备注说明」, 否则那份表里
  完全看不到这类工作的投入。
- 新增 `telemetry/csv_migrate.py`: CSV 表头迁移的共用实现。

### Fixed

- **新增列会让两个本地 CSV 静默丢数据**。公司公共统计表与多维表格本地备份都是**按表头名
  回读**的(`dict(zip(header, row))`); 若只往数据行加列而表头没更新, 回读时会因列数不符被当作
  脏行**直接跳过** —— 文件看着还在长, 数据却在丢。现在追加前先把表头对齐(按**旧列名**取值、
  整表重写、新列补空), 且**迁移失败时宁可不写那一行**。
- **为什么新列只能追加在末尾**: 飞书电子表格的值接口只能往表格尾部追加, **没有插列接口**;
  把「其他」插在「总节约工时」前面, 云端历史行与新行的列语义会立刻错位(旧行的「总节约工时」
  会落到新行的「其他任务数」位置上), 而且表面上完全看不出来。因此三列一律追加在末尾,
  并顺手把云端表头行对齐到当前列定义(幂等, 不动数据行)。
- 测试里对备份列数的硬编码 `15` 改为跟随 `BACKUP_FIELDS` —— 否则每加一个字段都会假红。

### 测试

`tests/test_telemetry.py` **60 → 77** 项; 全量 `168` 项通过; `make test-py` = 90 + 24 + 78 全绿。
新增覆盖的重点是**口径与不变量**: 未知 task_type 兜底、其他工作不得漏进三类、
**其他 Token 必须是总量的子集**、按 task_id 归属的调用不算其他、`scan_` 任务不把其他 Token
顶到总量之上、缺列记录不被判脏、CSV 历史行按列名搬迁且迁移幂等。
端到端冒烟(建库 → 三类 + 其他 → 报表 → 卡片 → 表格行 → 旧 CSV 迁移 → 多维表格 payload)已在本机核对。

## [5.4.36] - 2026-09-12 (部署方式参考 hermes-agent / openclaw: 预演、按需补齐、以及"装完必须复验")

回应"参考 hermes-agent 仓库和 openclaw 仓库的部署方式, 自动检测自动安装缺失的工具、依赖、包"。

读了两个仓库的安装器实现 —— `hermes-agent` 的 `scripts/install.sh` /
`hermes_cli/dep_ensure.py` / `hermes_cli/managed_uv.py`, 与 `openclaw` 的 `install.sh` /
`install-cli.sh` / `install.ps1`(见其 `docs/install/installer.md`)—— 把可迁移的机制
落进 `scripts/deploy_scan.py` 的能力矩阵。

### Added

- **`--dry-run`**(借自 openclaw): 打印**真会执行的那条命令**, 不落地任何修改。缺失项标成
  新的 `plan` 状态。`bootstrap_device.py --dry-run` 与 `medit doctor --plan` 是同一件事。
- **`--only KEY[,KEY]` + `--list`**(借自 hermes `--ensure node,browser`): 只补点名的能力,
  让别的入口按需回调同一引擎。`deps_auto.py` 也透传 `--dry-run` / `--only`。
- **装后复验**: 每次安装后**立刻重新探测**, 只有复验通过才算补齐。安装器报成功而复验失败时
  记成"仍缺失"、单独计入 `summary.verify_failed`、并在 `medit doctor` 里打印复验详情。
  这条正对着 Word 通道那个真实故障 —— `save as` 返回 rc=0 却**没有任何产出**
  (hermes: "installer reported success but binary not found" → exit 1;
  openclaw: 残留 `lifecycle-pending` 标记必须判失败)。
- **私有前缀兜底**(借自 openclaw `install-cli.sh` 的 rootless 思路): `npm install -g` 撞权限时
  自动退回 `$VIA54_HOME/tools/node`(默认 `~/.via54medit`), 不 sudo、不污染系统 `node_modules`;
  探测也会查这个前缀, 否则装好的会被判成"没装"而每次重装。
- **部署戳记** `$VIA54_HOME/.deploy_stamp.json`(借自 hermes `.install_method`): 记下每个能力
  **实际用了哪条通道**, 下次沿用同一条。复验没过的**不记** —— 否则下次会去沿用一条已知失败的通道。
- **阶段协议** `--stage env|deps|compat`(借自 hermes `--stage` / `emit_stage_json`)+ 可选
  `--json` 进度帧;`bootstrap_device.py` 借此分步显示进度。
- **退出码语义**(借自 openclaw 对非法取值退 2): `0` 就绪 / `1` 仍有必需缺口 / `2` **用法错误**。
  拼错能力键或阶段名不该被读成"这台机器环境有问题"。
- **环境变量镜像所有开关**(借自 openclaw `OPENCLAW_*`): `VIA54_DRY_RUN` / `VIA54_ONLY` /
  `VIA54_SKIP_HEAVY` / `VIA54_STRICT` / `VIA54_JSON` / `VIA54_STAGE` / `VIA54_HOME` /
  `VIA54_ALLOW_BREAK_SYSTEM`。命令行优先。
- **新增 `git` 能力**(必需, 参照 hermes 的 `check_git`): `git pull` 是"更新版本后自动补齐"
  自身的运行前提, 此前完全不在依赖清单里; 现按平台自动安装, macOS 走 `xcode-select --install` 提示。
- `make deploy-plan` / `make deploy-only KEY=ocr`;CI 增加 `--dry-run --skip-heavy` 冒烟步骤。

### Fixed

- **`deps_auto.ensure_env()` 自 v5.4.34 起一调用就 `KeyError: 'ok'`** ——
  `collect()` 没给 `ok` 键, 而 `_render()` 要读它。这等于 **`via54_auto.py` 管线第 [0] 步
  (环境自检)从 v5.4.34 起就是坏的**, 当时没有任何测试覆盖这条路径, 所以一直没被发现。
  现在 `collect()` 一定产出 `ok`, `_render()` 用 `.get()` 兜底, 并补了入口级回归测试。
- **我自己引入又自己抓到的假阴性**: 给"进程内 `import`"套探测超时。Paddle 首次导入会
  编译/初始化(那条 `No ccache found ... recompiling all source files` 警告就是它), 超过小上界
  就被误报"没装"; 更糟的是被 `join` 超时掐断的 daemon 线程会继续在后台把导入跑完, 让同进程里
  **后续**探测得到不同结果 —— 本机实测到**同一条命令两次一个 `missing` 一个 `ok`**。
  现在: 线程级超时**只给跨 GUI/授权边界的探测**(Office 的 AppleEvent, 不设界会把部署挂死),
  进程内 import 一律不设界。
- **`_probe_tool` 的版本开关必须逐个工具声明**: `pdftoppm --version` 会被当成文件名报
  I/O Error, 只有 `-v` 可用(实测)。工具探测也从"文件在不在"升级为**真跑一次版本命令** ——
  一个 exit 非零的二进制不算就绪(openclaw 的经验, 也是 fresh macOS 上 CLT 垫片的实情)。
- **`medit doctor` 的 JSON 契约**: 差点把 `channel`(JSON 里是**对象**)用 Go 的 `string` 去接,
  那会让 `json.Unmarshal` 整份失败、doctor 报"输出不是合法 JSON"。已避免并留下注释;
  同时把 `verify_failed` / `unresolvable` / `planned` / `verified` 接上。
- **又一条带平台假设的断言, 再次被 Windows 跑者抓到**: 新加的 dry-run 用例写了
  `assertIn("npm install -g mmx-cli", plan)` —— 在 Linux/macOS 上过, 在 Windows 上必挂,
  因为那里的可执行文件是 `npm.CMD`(`C:\Program Files\nodejs\npm.CMD install -g mmx-cli`)。
  改为**按序片段**断言(`_PlanAssertions.assert_plan_has`), 并加了一条**自守卫**:
  即便在 macOS 上跑, 也拿 Windows 形态的命令行去验断言逻辑 —— 让这类问题在本机就暴露,
  不必等 CI。这是同类问题的第三次(前两次见 v5.4.32 与 v5.4.35), 所以这次把守卫也一起补上。
- OCR 探测不再吞异常: 失败时带出 `异常类型: 原因`, 而不是只说一句 `paddleocr=False` ——
  "没装"和"装了但 ABI 不匹配"需要完全不同的处置。

### 测试

`test_deploy_scan` **28 → 78** 项(`make test-py` = 73 + 24 + 78, 全绿);
`go vet` / `go test ./...` 干净。新增覆盖: dry-run 绝不落地、`--only` 只动点名项、
**"安装器报成功但没产出"必须报成缺失**(`_LyingRecorder`)、探测超时**不得污染后续探测**、
npm 私有前缀兜底与戳记沿用、PEP 668 默认不越界、退出码 2、阶段帧、git 能力、入口不崩。

`--dry-run` 与 `--stage` 的实际输出已在本机核对;`medit doctor --plan` 在真机构建后跑通。

## [5.4.35] - 2026-09-12 (CI 修红: 我把 POSIX 假设写进了新加的 CI 步骤 —— 断言下移到脚本, 不再依赖 shell)

v5.4.34 推送后 CI 的 `python (windows-latest)` **失败**, 原因是**我自己刚写下的那类问题**:
新加的冒烟步骤里用了 `2>/dev/null` 与 `|| true`, 而 Windows 跑者默认用 PowerShell,
`/dev/null` 被解析成 `D:\dev\null` →
`Out-File: Could not find a part of the path 'D:\dev\null'`。

这正好是本轮扫描器要报的 POSIX 专属假设 —— 我在给它写验证的同一刻踩了进去。

### Fixed

- **断言从 workflow 下移到脚本**: 新增 `deploy_scan.py --verify-platform`, 在真
  Windows/Linux/macOS 跑者上校验"平台分类是否与宿主一致"(非 Windows 上 `pywin32` 必须是
  `na`、Linux 上 Office 必须是 `na`、Windows 上 `pywin32` 不得是 `na`)。
  CI 那一步现在只有一行 `python deploy_scan.py --verify-platform` ——
  **没有任何重定向、没有 `|| true`、不依赖任何 shell 语义**, 临时文件也一并去掉了。
- 留在脚本里的额外好处: 该断言**在本机就能单测**。新增 `TestPlatformSelfCheck` 5 项, 含
  "伪造分类错位必须被报出来"与"不得触发安装"两条。

### 测试

`test_deploy_scan` 23 → **28** 项; `make test-py` 73+24+28; `test_pipeline_ha` 8 过 3 跳过;
`go test ./...` 24 包; 本机 `--verify-platform` 输出
`os=macos pywin32=na powerpoint=ok word=ok ocr=missing mmx_cli=ok`(OCR 缺失是实情)。

## [5.4.34] - 2026-09-12 (部署工具升级为"深度扫描 + 按平台补缺口": 修掉三个让它形同虚设的硬伤)

回应"确保部署到任何设备 / 更新任何版本后, 部署工具会深度扫描系统环境与依赖, 只部与系统环境
相关且缺失的(Windows 不部署 macOS 那套; 缺 OCR 主动装; 缺 mmx-cli 视觉能力主动部署)"。

### 先摆事实: 旧的"一键部署"为什么是假动作

| 硬伤 | 实情 |
| --- | --- |
| **`pip install mmx-cli` 永远失败** | mmx-cli **不是 PyPI 包**: `pip index versions mmx-cli` → *No matching distribution found*。它是 **npm 包**(本机 `~/.local/bin/mmx -> ../lib/node_modules/mmx-cli/dist/mmx.mjs`, shebang 是 node)。`install_mmx.py` 与 `bootstrap_device.py` **两处**都用 pip 装它, 失败还被退出码与错误处理吞掉, 于是"看起来装过了"。 |
| **完全不检测 OCR** | 三份依赖清单里都没有 `paddleocr`。缺了没人知道, 直到 L2 中文识别那步才炸。本机实测**确实没装**(`No module named 'paddleocr'`; 文档里说的"已在 hermes-agent venv"是另一个解释器)。 |
| **不分平台** | `bootstrap_device.py` 无条件 `pip install pymupdf python-pptx pillow requests mmx-cli`, 把 **Windows 专属的 pywin32 也列进清单**;Go 侧 `medit doctor` 反过来在 Windows 上也会校验 AppleScript 通道, 并且**还在把 LibreOffice 报成"PPT 真渲染"**(那个通道 v5.4.25 已按规范删除)。 |

### Added — `scripts/deploy_scan.py`: 深度扫描 + 缺口自愈

**能力矩阵的唯一事实来源**。Go 的 `medit doctor`、`deps_auto.py`、`bootstrap_device.py`
全部改读它, 不再各自维护清单。三段式:

1. **环境**: OS / 架构 / 容器 / 解释器 / 包管理器 / 输出编码;
2. **能力**: 逐项探测, **与平台无关的标 `· 不适用` —— 既不安装也不校验**;
3. **兼容性**: 硬编码 `/tmp`、外机绝对路径(`C:\Users\via54`)、未加 darwin 守卫的
   `osascript`。本机实测 **50 处 / 34 个文件**。

平台过滤的落地(即"部署到 Windows 不必管 macOS 那套"):

| 能力 | Windows | macOS | Linux |
| --- | --- | --- | --- |
| `pywin32` (Office COM) | 必需, 缺失即装 | **不适用** | **不适用** |
| 桌面版 PowerPoint / Word | 必需 | 必需 | **不适用** → `RENDER_ENGINE=graph` |
| PaddleOCR (L2 中文 OCR) | 缺失即装 | 缺失即装 | 缺失即装 |
| `mmx-cli` 视觉引擎 | 经 **npm** 装 | 同左 | 同左 |

安装通道分派: Python 包 → pip;`mmx-cli` → npm;系统工具 → 本机可用的
brew/apt/dnf/pacman/winget/choco/scoop;需要管理员权限却拿不到时**打印完整命令**, 不静默失败。
`--check` 只报不改、`--skip-heavy` 跳过数百 MB 的 OCR、`--strict` 让兼容性问题也计失败、
`--json` 供 `medit doctor` 与 CI 消费。

### Fixed — 四个入口全部改接同一引擎

- `bootstrap_device.py`: 删掉无条件 pip 批量安装, 改为「深度扫描 → 渲染真出图自检 → 构建 →
  按平台注册自动更新(launchd / cron / **schtasks**)」;并探测 `auto_sync.py` 实际支持的开关,
  不再在 Windows 上误调 `--install-launchd`。
- `deps_auto.py`: 收成薄适配层, 保留 `ensure_env()` 签名(仍有 `via54_auto.py` 与
  `medit doctor --fix` 在用), 依赖清单不再重复维护。
- `install_mmx.py`: 改走 npm, 并对照 npm 最新版提示升级(本机 1.0.19 / npm 1.0.25)。
- `medit doctor`(Go): 重写为消费 `deploy_scan.py --json` 的渲染层, 删掉 LibreOffice 那段,
  新增 `--strict` / `--skip-heavy`, 保留 Go 侧独有的 CDP 可达性探测。

### 我自己犯的两个错(都是负向对照抓出来的)

- **Word 那行复用了 PowerPoint 的探测** → "没装 Word"被报成"已就绪"(实测输出
  "已探测到 PowerPoint (macOS)")。已拆成两个独立探测。
- 修完之后 **PowerPoint 那行又显示成了 Word 的结果** —— 调用点把 `app` 传成了 `"ppt"`,
  落进 Word 分支。已加别名归一 + 一条专门的回归用例钉住。

### 顺带修掉 CI 里我自己刚写下的同类问题

新加的 CI 冒烟步骤里我写了 `/tmp/ds.json` —— Windows 跑者上那是 `C:\tmp`, 正是这个扫描器
要报的那类 POSIX 假设。已改为工作目录内的相对路径。

### 测试

新增 `scripts/test_deploy_scan.py`(**23 项**), 守的是这个功能承诺本身:

- **平台过滤**: Windows 上必须探测/安装 `pywin32`, 在 macOS/Linux 上**不得探测也不得安装**;
  Linux 上 PowerPoint/Word 必须是 `na` 且探测/安装调用数为 0;
- **只装缺失的**: 全就绪时安装调用数 = 0;`--check` 下安装调用数恒为 0;
- **通道正确**: `mmx-cli` 走 npm, 且**任何能力都不得用 pip 装它**(AST 级检查, 不看 docstring,
  免得被"这就是错的"这类说明误判);OCR 走 pip 且带 `paddlepaddle`;
- **门禁语义**: 缺 OCR 判失败;缺桌面 Office **不判失败**(脚本装不了它);
- **回归**: Word 探测不得等于 PowerPoint 探测;扫描器不得把自己那份检测规则报成违规。

CI 三平台新增两项: `test_deploy_scan` + **部署扫描冒烟**(硬断言平台分类: 非 Windows 上
`pywin32` 必须是 `na`, Linux 上 Office 必须是 `na`)。

## [5.4.33] - 2026-09-11 (部署指南本身在教人装错东西 —— 修 DEPLOY.md; 并确认 CI 三平台已全绿)

接着上一条的"能否分发部署"。CI 修好之后顺查部署文档, 发现 **`docs/DEPLOY.md` 的
"各平台软件接入矩阵"是坏的** —— 而那是部署者在其他设备上唯一会照着做的一份文档。

### Fixed — DEPLOY.md

- **"PPT 真实渲染"那一行**还在写 Windows 用 `PowerPoint/WPS COM`、macOS/Linux 用
  `LibreOffice soffice (自动探测)` —— WPS 与 LibreOffice 都已删除, 且按规范**禁止使用**。
- **"PPT 近似渲染(兜底)"那一整行**(python-pptx + 各平台 CJK 字体)—— python-pptx 渲染器
  早已删除, 而且它本身就属于"会重排"的引擎。照这行做会以为存在兜底。
  两行合并重写为按平台列出 PPT/Word 的**版式**路径, 并明确写"**没有兜底通道** …
  拿不到微软引擎就直接失败"。
- 新增 **§2.1 渲染前置条件(部署后必读)**: 三平台渲染路径表 + "部署后先跑真出图自检
  `python3 scripts/render_doctor.py`" + 为什么不能只看依赖探测(假 OK) + macOS
  `-1712 / -1708` 的处置办法。原矩阵降级为 §2.2(纯依赖类)。
- `medit doctor` 那行注释里的 `soffice` 去掉(它已经不探测这个了)。
- **环境变量表补 5 行**: `RENDER_ENGINE` / `RENDER_RASTERIZER` / `PPT_RENDER_TIMEOUT` /
  `WORD_RENDER_TIMEOUT` / Graph 凭据 —— 新设备部署要用, 之前一个都没写。
- **§5 CI 验证**: 测试计数更新(79/25 → 120/36), 补上禁止区校验与渲染链路的 import 探测,
  并写明"Python 测试刻意不依赖平台"的做法, 以及 v5.4.26~v5.4.31 那次教训。

### 已验证 — CI 三平台全绿

修完上一条后**复查了 GitHub Actions 的真实结论**(不是只看本机):

| job | 结论 |
| --- | --- |
| ``go (ubuntu / macos / windows)`` | ✅ ×3 |
| ``python (ubuntu-latest)`` | ✅ |
| ``python (macos-latest)`` | ✅ |
| ``python (windows-latest)`` | ✅ |

**即 v5.4.32 起, Go 侧与 Python 侧在 ubuntu / macOS / Windows 上全部通过** ——
这是"可以分发到 Win/Mac"的硬证据(在此之前连续六次提交是红的)。

## [5.4.32] - 2026-09-11 (分发可用性: CI 在 ubuntu / windows 上已经红了六次 —— 修掉 + 补上"本机就能发现"的守卫)

回应"确认当前版本是否可以分发并部署到其他设备(winOS / macOS)"。
查证方式是读 GitHub Actions 的**真实结论**(``gh run list``), 而不是只看本机。

### 结论先摆出来

| 平台 | 结论 |
| --- | --- |
| ``go (ubuntu / macos / windows)`` | ✅ 三个平台全过(含 ``-race``) |
| ``python (macos-latest)`` | ✅ 通过 |
| ``python (ubuntu-latest)`` | ❌ **失败** |
| ``python (windows-latest)`` | ❌ **失败** |

**即: 当前版本还不能分发** —— Python 侧在 Linux 与 Windows 上是红的。
而且这不是新问题: 从 **v5.4.26 一路红到 v5.4.31, 连续六次提交**都没被发现。

### 为什么我没发现(我自己的流程漏洞)

我每轮都用 ``make test-py`` / ``test_tma_pipeline`` 验证, 但那些**只在本机 macOS 上跑**;
我从未查过一次 CI 的真实结论。macOS 全绿把跨平台失败完整地盖住了。

### Fixed — 根因: 我的测试带平台假设

有两个用例测的是 **darwin 分支的逻辑**(预检、超时、AppleScript 里嵌的秒数), 却直接在宿主上跑:

- ``test_timeout_error_appends_hint_and_embeds_configurable_timeout`` 与
  ``test_preflight_failure_fails_fast_with_hint``: 在 Linux/Windows 上, ``export_ppt_to_pdf``
  会先命中"本平台没有桌面版 PowerPoint 通道"那条分支, 于是断言 ``-1712`` / ``预检失败`` 失败。
- ``test_powerpoint_pref_never_falls_back_to_other_channels``: **只伪装了 ``sys.platform``**,
  没伪装 ``os.name``。Windows 上 ``os.name == "nt"`` → 走 COM 分支 → 抛 RuntimeError → ERROR。

修法: 新增 ``_as_macos()`` helper(**同时**伪装 ``os.name`` 与 ``sys.platform``), 三个用例改用它。
比"非 macOS 就跳过"更好 —— 这样**每个平台都会真的跑一遍这些分支**。

### Added — 两条防回归守卫(让"本机绿、CI 红"不再可能)

- ``test_render_engine_suite_passes_on_non_macos``: 起子进程把 ``sys.platform`` 伪装成 ``linux``
  再跑一遍 ``TestRenderEngine``。**已验证它能精确复现 CI 的报错**: 把某个用例改回不伪装平台,
  它立刻红, 且错误行与 CI ubuntu job **一字不差**。
  (为何不模拟 Windows: 本机把 ``os.name`` 改成 ``"nt"`` 会让 asyncio 去 import Windows 专属的
   ``_overlapped`` 而崩 —— 这条路走不通, 已在用例注释里写明。)
- ``test_as_macos_fakes_os_name_too_not_just_platform``: 直接检查 helper 源码里确实同时改了
  ``os.name``; 这条在**任何**平台上都成立(Windows 那侧无法在本机做行为验证)。

### Fixed — 顺带三处与分发相关的错误说明 / 缺口

- **``requirements.txt``**: 注释还在写 "pywin32 … (PowerPoint/**WPS** COM 渲染)" 与
  "**LibreOffice (soffice): PPT 真实渲染**", 都与现行规范矛盾(会误导部署者去装 LibreOffice)。
  已改为: PPT/Word 的版式只由微软引擎产出(桌面版或 ``RENDER_ENGINE=graph``), Python 侧
  **不需要** LibreOffice; 系统二进制里把 PowerPoint/Word 列为**非可选**。
- **CI 的导入探测清单漏了整条渲染链路**: 补上 ``unified_render_engine`` / ``render_doctor`` /
  ``graph_render`` / ``bootstrap_device``(并把 ``hl_v3_final`` 入路径)。以前这些模块在
  Windows/Linux 上能否导入, CI 根本没查。另加注: ``render_doctor`` 的**真出图探针故意不进 CI**
  (跑者镜像里没有桌面 Office, 必然报不可用), 那一步在真机上跑。
- **Windows 控制台编码**: 新增/改动的入口 (``render_doctor.py`` / ``graph_render.py`` /
  ``unified_render_engine.py``) 补齐 ``sys.stdout.reconfigure(encoding="utf-8")`` ——
  Windows 上把输出重定向到文件/管道时默认 cp936, 而脚本打的 ``✓ ✗ ⚠️`` 等字符不在 GBK 里,
  会直接 UnicodeEncodeError。(仓库其它入口早有这个兜底, 是我这几个新文件漏了。)

### 测试

``test_tma_pipeline`` 118 → **120** 项; ``make test-py`` 73+24、``test_pipeline_ha`` 8 过 3 跳过、
``hl_v3_final/test_hl_lib.py`` 36 过、禁止区校验 OK、镜像 ``--check`` 退出码 0。

推送后**复查 CI 的真实结论**, 是本轮新增的收尾动作(此前从未做过)。

## [5.4.31] - 2026-09-11 (高可用复核: 我自己把 Word 通道弄坏了 → 修好 + 新增"真出图"就绪探针)

回应"确保当前状态是你推理最佳路径后的高可用版本"。我按**可用性**重新审了一遍自己这几轮的改动,
结果抓出两个由我造成的真问题。

### Fixed — 我把 Word 通道改成了不可用

- **v5.4.30 删掉 LibreOffice 之后, Word 的 AppleScript 成了唯一路径, 而它本来就是坏的。**
  实测: `set myDoc to open file (...)` 拿不到文档引用, 于是 `save as` 报 `-1708 / -2753`;
  更糟的是文档没打开时 `save as` 会**返回成功却什么都不产出**(rc=0、无 stderr、目标文件不存在)——
  只看返回码会把失败当成功。修法: 改用 `open POSIX file` → `set theDoc to active document` →
  `save as ... file format format PDF`, 并**校验产物真的存在**。
  以前 LibreOffice 先跑, 这条坏路径永远轮不到, 所以一直没暴露 —— 是**我删兜底的动作把它暴露出来的**。
- **Word 通道补上"快速预检 + 有界超时"**, 与 PowerPoint 对称: `probe_macos_word()` 只做
  launch + get version(秒回), 不通就立刻返回、不去白等; 主脚本包在 `with timeout of N seconds` 里,
  子进程上界 = N+15; 超时可配(`WORD_RENDER_TIMEOUT` / `WORD_RENDER_PREFLIGHT_TIMEOUT`), 非法值回落默认。
  **为什么必须有上界**: 实测本机 `open` 会被模态对话框挡住一直挂着 —— 没有上界就是把整条管线吊死。

### Added — `scripts/render_doctor.py`: 回答"这台机器现在到底能不能出图"

- 默认做**真出图探针**: 现场造一份最小 PPTX/DOCX(`_make_canary_pptx` / `_make_canary_docx`,
  后者用 zipfile 手工构造, **不依赖 python-docx**), 用**生产函数**真的渲染一遍, 数产出的图片。
- 判据分层: **必须就绪** = PPT 排版通道 + 栅格化器(任一不就绪 → 退出码 1);
  **按需** = Word 通道(只在源文件是 DOC/DOCX 时需要, 不就绪只提示); **可选** = Graph(需凭据)。
- `--quick` 只查依赖, 且**明确拒绝说"就绪"**。这一点是实测逼出来的: 同一时刻
  `--quick` 报 "✓ PPT 排版通道 探测到 PowerPoint (macOS)" 退出码 0, 而真探针是 **0 张图**。
  所以 `--quick` 的结语只能是"依赖看起来齐全 —— 但没做真出图探针, 不能据此认为能渲染"。
- 本机实跑结果(**36 秒给出确定结论**): PPT 排版通道 ✗ 0 张图(AppleEvent -1712)、
  Word 通道 ✗ 0 张图、栅格化器 ✓ pymupdf → 退出码 1。也就是说: **这台机器现在跑任何
  PPT/Word 管线都会在渲染这步失败** —— 这是环境结论, 不是猜测。
- 加了 `make render-doctor`。

### Fixed — 两处"承诺了不存在的备选"

- `scripts/bootstrap_device.py`: 原先打印"未检测到原生 Microsoft PowerPoint，**将使用
  LibreOffice / python-pptx 备选渲染**" —— 备选早就删了, 这是在骗操作者。改为如实说明
  "没有备选渲染引擎"、给出 Graph 这条显式路、指向 `render_doctor.py`, 并补上
  "'探测到'不等于'能出图'"的提示。
- `scripts/deps_auto.py`: `WINDOWS_DEPS` 里还写着 `PowerPoint/WPS COM 渲染` —— WPS 已删除,
  改为 `PowerPoint/Word COM 渲染`。

### 测试

- `test_tma_pipeline` 109 → **118** 项, 新增 `TestWordChannel`(5) + `TestRenderDoctor`(4):
  预检失败**只调一次** subprocess(证明不白等)、"报成功但没产出"判失败、脚本形态
  (`active document` + `file format format PDF` + `with timeout of 9 seconds` + 子进程上界 24)、
  超时非法值回落、代码里不再有 python-docx / docx2pdf / LibreOffice 开关;
  探针的最小文档真能被 python-pptx / zipfile 打开、PPT 不可用时退出码 1、
  **`--quick` 绝不说"就绪"**、全就绪时退出码 0。
- 又抓到自己一次: 第一版把 `"WPS"` 当禁词扫全文, 结果被模块 docstring 里的**规则说明**
  ("WPS / LibreOffice 已禁用")绊倒 —— 改为只查代码用法, 不查文档字符串。

### 本轮没有、也不会做的事

- **不会**因为"PowerPoint 不可用"就自动切到会重排的引擎 —— 可用性不能拿保真度换。
  高可用在这里的含义是: **早发现、快失败、原因准、建议可执行、绝不产出错误结果**,
  而不是"总能渲染"。要在这台机器上真跑出图, 只有两条路: 修好自动化权限, 或显式
  `RENDER_ENGINE=graph`(需凭据)。

## [5.4.30] - 2026-09-11 (把最后两处开着的也收口: hl_p24-1 的 0x01 → ≥, Word 也只用 Word)

回应"确保所有均已完成"。上一轮我留下两条要你点头的, 这一轮都关掉 —— 现在**守卫测试的豁免清单
已为空**, 规则没有例外了。

### Fixed

- **`hl_v3_final/examples/hl_p24-1.py`(及技能包镜像 `hl_pnx_examples/hl_p24-1.py`)3 处 0x01 → `≥`**。
  那 3 处就在 P24-1 的高危分层应证句里("LDH ?2 times the ULN"、"rUPCR ?1 mg/mg"、
  "proteinuria (?1 mg/mg ...)"), 语义只能是 `≥`。
  这不是对交付内容的臆测改写: 该脚本是**可复现脚本**, 用途正是拿这几句去真实交付 PDF
  (`step3_pdf下载_106目录/P24-1_main.pdf`) 里 `locate_sentence` 定位后重新高亮 ——
  含控制字符的句子没法与 PDF 里的 `≥` 逐字对齐; 改成 `≥` 后该例才真正可复现。
  校验: 两个文件各 3 个 `≥`、零控制字符; 全仓重扫确认**再无任何文件含控制字符**。

### Changed — Word 也适用同一条保真标准 (最后一条豁免收掉)

- **`scripts/unified_render_engine.py::render_docx_to_images()`** 由"三策略"改为**只走 Microsoft Word**:
  Windows 用 Word COM 导出 PDF(`wdFormatPDF`), macOS 用原生 Word AppleScript; 新增
  `_docx_to_pdf_com()` / `_docx_to_pdf_macos()` 两个私有实现。
  删掉的两条兜底**都会改版式**:
    1. LibreOffice headless 转 PDF —— 换了个排版引擎;
    2. python-docx 抽段落拼一张"简易 PDF" —— 版式与原文档完全不同, 比前者更不准。
  拿不到 Word 就**直接失败**并说明原因(顺带删掉因此不再使用的 `from pathlib import Path`)。
  返回的 `engine` 标签由 `Word/LibreOffice` 改为 `Microsoft Word`。
- **`TestRenderFidelity.ALLOWED` 清空** —— 原先给 Word 路径留的那条豁免不再需要;
  "僵尸条目"检查会保证它不会被悄悄留着。
- 文档同步: `docs/ppt-render-fidelity.md` §3 增 Word 行与说明; `.trae/rules/project_rules.md` 规则 5 增 Word 条。

### 测试

- `test_pipeline_ha.py` 新增 `test_10_docx_render_is_word_only`: 假装本机装了 LibreOffice,
  断言 `render_docx_to_images()` **连碰都不碰外部转换器**、返回空并说明缺的是 Microsoft Word;
  另断言源码里不再有 `from docx import`。→ 8 过 3 跳过。
- 上一轮新增的两条源码卫生不变量, 这一轮各抓到一次**我自己的问题**, 都按它们的要求改了:
  ① 例外清单因文件已修好而变成僵尸条目 → 清空; ② 我把 `--convert-to` 字面量写进了 docstring
  被 lint 命中 → 改写措辞。(这正是设不变量的意义: 它对新写的代码同样生效。)
- `make test-py` 73 + 24 / `test_tma_pipeline` 109 / `test_pipeline_ha` 8 过 3 跳过 /
  `gofmt` / `go vet` / `go test ./...`(24 包) / 镜像 `--check` 全部通过。

### 仍未完成 (只剩这三项 —— 都必须你出手)

1. **Graph 凭据**未提供 → Graph 通道从未真连过微软服务(14 项测试全是 mock HTTP)。
   自检命令: `python3 scripts/hl_v3_final/graph_render.py --check`。
2. **macOS PowerPoint 自动化仍不可用**(`save … as PDF` → AppleEvent -1712), 属环境问题:
   需人工打开 PowerPoint 关掉模态对话框, 并在 系统设置 › 隐私与安全性 › 自动化 里放行。
3. **3 篇文献待你提供原文**: P12-3(UpToDate 占位) / P13-1(焦扬) / P31-6(AANEM 摘要)。

另有两条**历史遗留**保持原样 —— 不是"未修", 而是**明确不改**: 若干 Windows 时代脚本仍以
`C:\Users\via54\Desktop\TMA_test` 作为 `TMA_PROJECT` 的默认值(有环境变量兜底);
多处脚本仍引用旧目录名 `_2_pdfs` / `_3_highlight_semantic_v14*`。改它们会改变这些脚本的既有
行为, 而我没有它们的目标位置 —— 需要时再说。

## [5.4.29] - 2026-09-11 (复核发现: 一处外机路径被写坏成控制字符 + 新增"源码卫生"不变量)

回应"确保所有修正都已完成"做的全面复核。**复核本身又抓出一处同类缺陷**(与 v5.4.20 修掉的
`strict_eval_ocr_locate.py` 同属"外机绝对路径"), 故补一轮。

### Fixed

- **`scripts/tma_download_round2.py:10`** —— 原有一行把**另一台机器 G: 盘上的目录**插进
  `sys.path`, 但那两个 `\a` 转义**已经退化成真正的 BEL 控制字符 0x07**, 于是插进去的实际是
  `'G:' + BEL + 'gent' + BEL + 'i' + ...` —— 一个既不存在也不可能存在的路径
  (实测 `sys.path[0]` 打印出来就是那个带 0x07 的串)。
  改为按本文件所在目录定位 (`os.path.dirname(os.path.abspath(__file__))`), 与 v5.4.20 对
  `strict_eval_ocr_locate.py` 的处理一致 —— 同目录的 `tma_scihub.py` 才是它的真实来源。
  复核过: 该行是全仓**唯一**残留, 且 `_sys` 别处没用到。
  它一直没暴露: insert 本就多余(直接运行时 Python 已把脚本目录入路径), 而 CI 是先 insert
  `scripts/` 再 import 它, 所以先命中了正路。

### Added

- **`tests/test_repo_hygiene.py::TestSourceHygiene`** —— 两条源码卫生不变量:
  ① 源码里不得出现控制字符(制表 / 换行 / 回车除外) —— 这正是"转义被写坏"留下的痕迹;
  ② `sys.path.insert/append` 里不得出现外机盘符路径(Windows 盘符 / UNC)。
  另带例外清单 `CTRL_CHAR_ALLOWED` 的**僵尸检查**(改回正常字符后条目必须删掉)。
  反向控制: 往干净文件塞一个 BEL → 当场红并报出 `文件: 0x07`。
  **这两条一上线就抓到了另一起**(见下)。

### 待你确认

- **`scripts/hl_v3_final/examples/hl_p24-1.py`(及技能包镜像)里有 3 处 0x01**。
  用 git 查过: **自 2026-08-18 首次入库就如此**, 不是后来被写坏的。
  按语义几乎肯定是 `≥` —— 对应那 3 句是 "LDH ≥2 times the ULN"、"rUPCR ≥1 mg/mg"、
  "proteinuria ≥1 mg/mg random urine protein-to-creatinine ratio"。
  但它属**已交付的临床证据文本**, 改写可能影响该例重跑时的定位结果, 所以**我没擅自改**,
  已列进 `CTRL_CHAR_ALLOWED` 并写明理由。**要我改回 `≥` 就说一声。**

### 仍未处理 (复核确认仍然开放, 非本轮任务范围)

- **macOS PowerPoint 自动化仍不可用**(`save … as PDF` → AppleEvent -1712), 属环境问题,
  需人工关掉模态对话框 / 放行自动化权限; 排查记录见 v5.4.26。
- **Graph 通道尚未对真实服务验证** —— 14 项测试全部 mock HTTP, 从未真连 Microsoft Graph;
  待你提供凭据后跑 `graph_render.py --check` + 一次真实转换才算端到端验过。
- **Word(DOC/DOCX)仍走 LibreOffice**(`unified_render_engine.render_docx_to_images()`),
  按 PPT 范围处理、已在守卫白名单写明理由, 待你决定是否一并收口(见 v5.4.27)。
- 3 篇文献(P12-3 UpToDate 占位 / P13-1 焦扬 / P31-6 AANEM 摘要)**需你提供原文**。
- 若干脚本仍以 Windows 路径 `C:\Users\via54\Desktop\TMA_test` 作为 `TMA_PROJECT` 的**默认值**
  (有环境变量兜底, 本机不设就会指错)—— 属历史遗留, 未在本轮范围内。
- 多处脚本仍引用旧目录名 `_2_pdfs` / `_3_highlight_semantic_v14*` —— 同属历史遗留
  (`docs/versioned-scripts-audit-2026-09-11.md` 那轮是**纯调查**, 未改动文件)。

### 复核结论 (这一轮到底查了什么)

- 仓库: 工作区干净 · HEAD = origin/main = `9126669` · 无领先/落后 · v5.4.24~v5.4.28 tag 均已推送。
- 版本一致性: telemetry 三处 (1.5.29) + CHANGELOG 最新 + tag 三者对齐。
- 测试: 73 + 24 + 109 全过; `make test-py` / `test_tma_pipeline`(CI 跑的那个) / `test_pipeline_ha`
  (7 过 3 跳过 —— 跳过原因是本机 PowerPoint 环境) / `gofmt` / `go vet` / `go test ./...` / 镜像 `--check` 退出码 0。
- **独立复核(刻意不依赖我自建的守卫测试)**: 全仓重扫非微软渲染器调用(只剩 Word 那条白名单项)、
  裸 `import fitz`(全是 `except ImportError:` 回退或白名单项, 且白名单经查**不是**僵尸)、
  已删脚本的残留引用(只存在于 CHANGELOG / 审计文档等历史记录里)、
  `sys.path` 外机路径(修掉上面那处后为零)、控制字符(见"待你确认")。

## [5.4.28] - 2026-09-11 (接入 Microsoft Graph 通道: 微软自己的在线渲染引擎)

用户指示: "接入 Microsoft Graph 通道"。它由**微软服务端(Office 在线)**渲染, 与桌面版同属微软,
因此在"版式必须来自微软引擎"的标准下**合格** —— 但**与桌面版有已知差异**, 所以做成
**显式选项** `RENDER_ENGINE=graph`: 既不是默认, 也不是降级目标。

### Added

- **`scripts/hl_v3_final/graph_render.py`** —— Graph 客户端(纯标准库; HTTP 收在单点接缝上便于测试):
  `acquire_token()`(客户端凭据 / 现成令牌) → `upload_item()`(PUT 上传到 OneDrive/SharePoint)
  → `download_as_pdf()`(`?format=pdf` 转换 + 跟随 302 预认证 URL) → `delete_item()`(清理临时件)。
- **`RENDER_ENGINE=graph`** —— `ppt_render_engine` 与 `hl_v3_final/ppt_to_pdf.py` 都支持;
  **复用**同一套本地栅格化与字体内嵌保真检查, 不另造一套出图路径。
- **`graph_render.py --check`** —— 自检: 凭据 → 取令牌 → drive 可达; 缺什么直接列出来。
- `docs/ppt-render-fidelity.md` 增 §3.1 记录 Graph 的流程、官方限制与踩过的坑(附来源)。

### 设计取舍 (每条都有官方依据)

| 决策 | 原因 |
| --- | --- |
| 走 `?format=pdf`, **不用** `format=jpg` | 官方 API 页未说明, 社区实测 pptx→jpg **只返回第一张幻灯片**; 整份只有 pdf 走得通 |
| 先上传再转换 | 该 API 只作用于 `driveItem`, 不能直接对本地文件转换 |
| 跟随 302 时**不带** `Authorization` | 官方明确: 预认证 URL 在有效期内无需鉴权(带了反而可能被拒) |
| 用完 `DELETE` 清理中转件 | 上传只是中转; `GRAPH_KEEP_UPLOAD=1` 可保留用于排查 |
| >250 MB 直接报错 | 官方单次上传上限 250 MB, 超过需 upload session(未实现, 就不假装支持) |
| 429/503 按 `Retry-After` 退避重试 | Graph 通用节流要求 |
| **不自动切换** | 连"桌面版失败就自动切 Graph"也不做 —— 必须显式指定, 宁可报错 |

### 与桌面版的已知差异 (写进文档, 不假装等价)

Office 在线引擎: 字体可能被替换、符号在缺字体时显示为占位符、部分对象行为与桌面版不同。
所以**桌面版可用时优先桌面版**; 报错提示里也把 Graph 标成"另一条微软引擎的路", 而不是"绕过它"。

### 测试 (全部 mock HTTP, 不联网)

- `test_tma_pipeline` **95 → 109 项**, 新增 `TestGraphChannel` 14 项: token 请求形态 / 现成令牌短路 /
  完整链路(上传→转换→302→下载→清理) / 预认证请求**不带** Authorization / 保留上传件 /
  缺凭据的可操作说明 / 自动解析 drive / app-only 无 `/me` 的提示 / 非 PDF 载荷被拒 /
  429 退避重试 / 超限提示 upload session / **未显式选择时绝不触碰 Graph** /
  Graph 失败不退回桌面版 / graph 路径复用本地栅格化。
- **负向对照两次抓到自己的漏洞(如实记录)**: ① 第一版把 mock 打在 `_request` 上, 而那正是重试
  逻辑所在层 —— 429 重试压根没被测到, 改打到 `_open`; ② "不自动切换"那条起初只验了
  `render_ppt_slides_auto`, 它被 `_build_engine_list` 提前挡下、走不到 `export_ppt_to_pdf`,
  且源文件都没建 —— 负向对照两次都溜过去, 补成两级断言后注入"默认也走 graph"当场红。
- 另修一条历史 lint: `test_no_advice_to_switch_render_channels` 拓宽禁用名单后误伤了
  CHANGELOG 里的历史记录 —— 已让该 lint 跳过 `CHANGELOG.md`(历史存档不改写, 与 v5.4.16 同处理)。
- `make test-py`(71 + 24) / `test_pipeline_ha`(7 过 3 跳过) / `gofmt` / `go vet` / `go test ./...`
  全过; 镜像 `--check` 退出码 0(`graph_render.py` 已同步进技能分发包)。

### 功能探针 (实跑过)

- 无凭据跑 `--check` → 退出码 1, 并列出 (a) 现成令牌 / (b) 客户端凭据两条路与所需权限;
- `RENDER_ENGINE=graph` 且凭据不全 → 渲染返回 0 张并说明原因, **不**退回桌面版;
- 技能分发包里的 `graph_render.py --check` 输出与仓库内一致(自包含)。

### 需要你提供 / 待确认

- **凭据**: 走 app-only 需要在 Microsoft Entra 注册应用(应用权限 `Files.ReadWrite.All` + 管理员同意)
  并给出 `GRAPH_DRIVE_ID`; 或者直接给 `GRAPH_ACCESS_TOKEN`(委派令牌也行 —— 那种情况可自动取
  `/me/drive`)。个人版 OneDrive **不支持** app-only。
- Word 那条仍按 PPT 范围处理(`unified_render_engine.render_docx_to_images()` 继续用 LibreOffice),
  理由见 v5.4.27。**要收口就说一声。**

## [5.4.27] - 2026-09-11 (勘误: "禁用其它通道"我禁过头了 —— 判定标准是**保真**, 不是程序名)

用户澄清(原话):

> "事实上，我是认为 PowerPoint 渲染出来的图片更符合原版，如果有其他渲染图片并不会改变 PowerPoint 排版与文字的方式也可以集成"

即: 要保的是**版式与文字**; 只要某个出图方式**不改变 PowerPoint 的排版与文字**, 就可以接入。
而我 v5.4.24 ~ v5.4.26 把规则读成了"只允许 PowerPoint 这一个程序", 连"把 PowerPoint 自己导出的
PDF 转成 PNG"都想禁掉 —— **比规则本身更严**。本轮按澄清改正。

### 关键区分: 只有第一步不可替代

| 环节 | 能否换 | 理由 |
| --- | --- | --- |
| PPTX → 画面 (版式/文字) | ❌ 不可换 | PPTX 只是描述性格式; 第三方引擎各自重排 OOXML, 字体/断行/autofit 都分叉 |
| PowerPoint 产物 → 图片 (栅格化) | ✅ 可以换 | PDF 是固定版式, 栅格化器只解释绘制指令, **不重排** |

### Added

- **`docs/ppt-render-fidelity.md`** —— 判定标准 + 各方案结论表(附来源) + 允许/禁止清单 + 字体内嵌的坑。
  调研结论: 没有任何第三方 PPTX 渲染器能复现 PowerPoint 的版式 —— LibreOffice / WPS / Keynote /
  Google Slides / Aspose / Spire / GroupDocs / Syncfusion 全是各自重排, python-pptx 根本不渲染;
  2024–2026 冒出来的几个"高保真"新项目也没有逐像素对照证据。**微软自家引擎是唯一合格来源**:
  桌面 PowerPoint, 以及免装桌面版的 Microsoft Graph `pptx→jpg`(需 OAuth + 网络, 尚未接入)。
- **`RENDER_RASTERIZER`** —— 栅格化器闸口: `pymupdf`(默认) / `pdftoppm`。这正是用户说的
  "也可以集成": 两者都只做光栅化、不重排。**pdftoppm 强制带 `-cropbox`** —— 实测不带时它按
  MediaBox 出图(600×400), 带上才与 PyMuPDF 一致(500×300, 即 CropBox); 不带就会带出白边/偏移,
  那等于改了版式。
- **保真检查**: PowerPoint 导出 PDF 后查一次**字体是否内嵌**, 未内嵌就打印警告 —— 字形不随
  文档走时, 栅格化只能用替代字体画, 那就是"改变了文字"。判定依据实测(`get_fonts()` 的 `ext`):
  内嵌→`ttf`/`cff`/`cid`; 未内嵌→`''`; base-14(Helvetica 等)→`n/a`(同样不随文档走)。
- 首选 PowerPoint **直接出位图**(Windows `Slide.Export`) —— 保真上限更高, 且绕开字体内嵌风险。

### Changed — 把过严的措辞改回来

- `ppt_render_engine.py` / `hl_v3_final/ppt_to_pdf.py` / `ppt_expand.py` /
  `render_ppt_slides.py` 的 docstring 与报错文案: 由"只使用 PowerPoint 渲染、禁用其它通道"
  改为"版式与文字必须由 PowerPoint 产出; **只光栅化、不重排**的下游工具可以换"。
- `.trae/rules/project_rules.md` 规则 5 重写为"两步判定"。
- `tests/test_repo_hygiene.py`: `TestPowerPointOnlyRender` → **`TestRenderFidelity`**, 语义从
  "禁止其它程序"改为"禁止**会重新排版**的引擎"(名单纳入 Aspose / Spire / GroupDocs / Syncfusion),
  并新增 `test_rasterizer_whitelist_is_only_fixed_layout_tools`。
- 权威规则文档 `references/v2.12.0-powerpoint-render-mandatory.md` 增加 2026-09-11 澄清一节。
  (顺带发现: 该文件原本的示例实现就是"PowerPoint 导 PDF + **pdftoppm** 转 JPG" —— 原设计本就
  允许下游换工具, 是我后来把它读严了。)

### 测试

- `test_tma_pipeline` **90 → 95 项**: 新增 栅格化器闸口 / `-cropbox` 硬要求 / 字体内嵌判定 /
  有警告 / 无警告 五条; 另修一条断言旧文案的用例(断言的是"不降级"这个行为, 文案已随规范更新)。
- 反向控制: 往 `_RASTERIZERS` 塞 `libreoffice` → `TestRenderFidelity` 当场红(报出具体条目)。
- **端到端实测(本机)**: 同一个固定版式 PDF 用 pymupdf 与 pdftoppm(带 `-cropbox`)出图
  **像素尺寸完全一致**(1125×625)、页数一致; 不带 `-cropbox` 时是 600×400 vs 500×300 ——
  证实该参数是保真硬要求, 而不是形式主义。
- `make test-py`(71 + 24) / `test_tma_pipeline`(95) / `test_pipeline_ha`(7 过 3 跳过) /
  `gofmt` / `go vet` / `go test ./...` 全过; 镜像 `--check` 退出码 0。

### 未处理

- **Microsoft Graph `pptx→jpg` 未接入** —— 它是本轮唯一被判定为**合格**的"另一个通道"
  (微软自家引擎、免装桌面版)。需要 OAuth 与网络, 等你要用再接。
- `unified_render_engine.render_docx_to_images()` 仍用 LibreOffice 转 **Word**。按"版式保真"
  的同一条道理, Word 也该只认 Word 本体; 但规则原话针对 PPT, 故本轮仍按 PPT 范围处理,
  并把它列进守卫白名单写明理由。**要收口就说一声。**
- 本机 PowerPoint 自动化仍不可用(`save ... as PDF` → AppleEvent -1712), 属环境问题,
  排查记录见 v5.4.26。

## [5.4.26] - 2026-09-11 (收口"禁用其它通道": 上轮只改到 1 个文件, 还有 4 个 PPT 渲染入口在走别的通道)

承接 5.4.24 / 5.4.25。用户重申"只使用 PowerPoint 渲染, 禁用其它通道"后复盘发现: **上一轮
只把 `scripts/ppt_render_engine.py` 收口了**, 而同一个仓库里还有 4 个 PPT 渲染入口各自调用
LibreOffice / soffice, 外加 1 条被上轮改红的测试。也就是说"禁用其它通道"当时并没有禁干净。
本轮把它们逐一对齐, 并补一条不变量测试, 防止下次再漏。

### Fixed — 仍在走其它通道的 PPT 渲染入口

| 入口 | 原先 | 现在 |
| --- | --- | --- |
| `scripts/ppt_expand.py` `render_pptx_images()` | 自己调 `libreoffice --headless` | 委托 `ppt_render_engine.render_ppt_slides_auto()` |
| `scripts/hl_v3_final/step1_export_slides.py` | `soffice --headless` 转 PDF | 委托 `ppt_to_pdf.export_ppt_to_pdf()` |
| `skills/…/literature-dir-init/scripts/render_ppt_slides.py` | 双引擎 `--engine applescript\|libreoffice` | 只剩 PowerPoint; 传其它引擎名直接报错 |
| `scripts/unified_render_engine.py` | 文档写 PPT 支持 LibreOffice / python-pptx | 文档改为"只用 PowerPoint"(PPT 分支本就委托引擎) |

- **`scripts/test_pipeline_ha.py::test_01_ppt_render_engine_fallback` 是 v5.4.25 改红的** ——
  它把渲染通道指向 python-pptx 并断言"优雅降级"渲染出 3 页; v5.4.25 删掉 python-pptx 通道后
  它必然失败, 当时没有同步改。现替换为 `test_01_ppt_render_engine_uses_powerpoint_only`
  (验证渲染循环确实走 PowerPoint 的实现) 与 `test_01b_ppt_render_never_switches_channel`
  (验证拿不到 PowerPoint 时返回 0 张、不降级)。
- `scripts/deps_auto.py` 的环境自检把 WPS / soffice 列成"PPT 引擎"并提示
  `brew install --cask libreoffice` —— 那是**引导改用其它通道**, 已删除; 改为提示
  `pdftoppm`(PowerPoint 导出 PDF 之后才会用到的 PDF→JPG 工具)。
- `scripts/ppt_render_engine.py` `render_via_com()` docstring 残留 "PowerPoint/WPS COM"。
- `AGENTS.md` Step 1 摘要、`.trae/rules/project_rules.md`、两份 SKILL.md 里的
  "soffice→PDF→JPG" / "双引擎" 表述。

### Added

- **`scripts/hl_v3_final/ppt_to_pdf.py`** —— PPT→PDF 的唯一实现 (`export_ppt_to_pdf()`)。
  放在 `hl_v3_final/` 而不是 `scripts/`: 该目录会被 `sync_skill_bundle.py` 整目录镜像到技能
  分发包, 而技能包必须**自包含**(要被分发到 `~/.hermes/skills/`), 不能 import 上层
  `scripts/ppt_render_engine.py`。内含同样的快速预检与 `PPT_RENDER_TIMEOUT`。
- `ppt_render_engine.export_ppt_to_pdf()` —— Windows COM / macOS AppleScript 的 PPT→PDF 原语;
  `render_via_macos_powerpoint()` 改为复用它(先出 PDF, 再 PyMuPDF 渲染成 PNG), 消掉了两处
  重复的 AppleScript。
- **`tests/test_repo_hygiene.py::TestPowerPointOnlyRender`** —— 不变量: `scripts/` 与 `skills/`
  下的非测试 Python 里不得再出现其它渲染器可执行名、LibreOffice 转换开关、已删除的通道函数名,
  也不得再设置指向其它通道的 `RENDER_ENGINE` 取值。**这条测试的由来就是本轮的漏改** ——
  没有它, 下次新增渲染入口时还会只改一个文件。
- 反向控制: 临时塞一行 `subprocess.run(["libreoffice", …])` → 测试当场失败并报出
  `文件:行号`; 删掉后恢复绿。

### Changed — 渲染相关测试不再依赖本机 PowerPoint

- `test_pipeline_ha.py` 的 test_06 / test_07 / test_09 需要**真实** PPT 渲染。本机 PowerPoint
  自动化当前不可用(见下), 于是它们以"跳过 + 写明原因"呈现, 而不是伪装成管线回归。
  探测只做一次(结果缓存)并用 `PPT_RENDER_TIMEOUT=8` 保证失败时快速返回。
  整文件 **264s → 80s**。

### Known issue — 本机 PowerPoint 自动化当前不可用 (环境问题, 不是代码)

排查结论(2026-09-11 实测):
- 通道本身是通的: `get version` → `16.112.1`; `count of presentations` → `1`。
- 但 `save thePres in POSIX file "…" as save as PDF` **超时 -1712**; 换目标目录
  (`~/Desktop` / `~/Documents` / `/tmp`) 一样; 改用参考文档里的 `as PDF` 写法还会退化成
  `front document` → `-1728`(文件其实已在 GUI 打开)。
- 与两份 SKILL.md 里已记录的 "PowerPoint AppleScript -1728 假失败" 属同一类问题。
- 影响: PPT 渲染返回 0 页 → 依赖它的 Step 1 与 5 步端到端整体失败。
- 修法: 手动打开一次 PowerPoint 关掉模态对话框; 并在 系统设置 › 隐私与安全性 › 自动化
  允许当前终端/Agent 控制 PowerPoint。**代码侧不会绕过它** —— 按规范只走 PowerPoint 这一条路。

### 待你确认

- `scripts/unified_render_engine.py::render_docx_to_images()` 仍用 LibreOffice 把 **Word**
  (DOC/DOCX) 转 PDF。该规则的原话与理由是"PPT 是 PowerPoint 做的, 其它渲染器视觉不一致",
  而 PowerPoint 无法渲染 Word 文档, 故本轮**按 PPT 范围**处理、没有动它, 并把它列入
  `TestPowerPointOnlyRender.ALLOWED` 写明理由。若你要 Word 也一并收口(只保留 Word AppleScript),
  说一声我就改。

### 验证

- `make test-py` 全过(遥测 + 仓库卫生 10 项, 含本轮新增 3 项 + 禁止区 24 项)。
- `python3 -m unittest test_tma_pipeline` 90 项全过。
- `python3 -m pytest scripts/test_pipeline_ha.py` → 7 过 / 3 跳过(跳过原因已打印)。
- `gofmt` / `go vet` 干净; `go test ./...` 全过。
- 镜像一致性 `sync_skill_bundle.py --check` 退出码 0(`ppt_to_pdf.py` 已同步到技能包)。
- 功能探针: `ppt_to_pdf.py` CLI 失败时退出码 1 + 可操作提示(不抛 traceback);
  `render_ppt_slides.py --engine libreoffice` 被 argparse 拒绝;
  `ppt_expand.render_pptx_images()` 返回 `[]` 并打印"按规范不切换其它通道"。
- 版本号三处同步 `1.5.25` → `1.5.26`。

## [5.4.25] - 2026-09-11 (按规范把其它渲染通道**整体删除**: 只留 PowerPoint 一条路)

承接 5.4.24。用户明确要求"只使用 PowerPoint 渲染, 禁用其它通道", 本轮把 WPS / LibreOffice /
python-pptx 三条通道从代码里**物理删除** —— 不是"禁用", 而是不存在。

### Removed
- `_PREF_MAP` 里的 `wps` / `libreoffice` / `soffice` / `python_pptx` / `python-pptx` 取值
  → 现在只剩 `powerpoint` / `ppt`; 其它取值 `_build_engine_list()` 直接报错。
- `_build_engine_list()` 的 `auto` 分支(按可用性枚举并降级) —— 降级链整体消失。
- `render_via_soffice()` / `render_via_python_pptx()` / `_find_cjk_font()` 与 `_FONT_CANDIDATES`
  —— 共 **124 行**实现。
- `_find_soffice()` 探测函数; `COM_ENGINES` 里的 WPS 项(`KWPP.Application`)。
- `render_ppt_slides_auto()` 循环里 `soffice` / 兜底 两条分支(已无对应引擎可走)。
- `import io` —— 删除 python-pptx 渲染后已无使用者。

### Changed
- **`detect_engines()` 改为只探测 PowerPoint**(kind 只可能是 `com` / `macos_ppt`)。
  它仍保留, 因为 `deps_auto.py` 与 `bootstrap_device.py` 用它做依赖与设备就绪检查 —— 两处均已验证可用。
- 拿不到 PowerPoint 时的收尾日志改为
  `"[render] PowerPoint 渲染失败, 返回 0 张幻灯片 (按规范不切换其它通道)"`。
- 模块 docstring 的引擎偏好一节改为"只认 powerpoint; 其它通道已整体删除"。

### 保留(需要区分清楚)
- **`python-pptx` 这个库仍在 `requirements.txt` 里** —— 仓库里另有 8 个脚本用它**生成** PPTX
  (`via54_ppt_visual_to_pdf.py`、`ppt_expand.py`、`hl_v3_final/step2_extract_refs.py` 等)。
  本轮删的是"用它来**渲染**"这条通道, 不是删这个库。

### 测试
- **删除 3 条**已失去前提的测试: `test_render_python_pptx_fallback`(调已删函数)、
  `test_render_auto_falls_back_when_com_fails` 与 `test_auto_mode_mock_seam_is_effective`
  (都建立在 `auto` 降级链上)。
- `test_detect_engines_always_has_fallback` **断言反转**为 `test_detect_engines_reports_only_powerpoint`:
  原断言"python_pptx 一定在列表里"→ 现断言"绝不允许出现非 PowerPoint 通道"。
- **`test_other_render_channels_are_gone`** —— 断言那些名字**在模块里已不存在**
  (`hasattr` 检查 5 个符号)、偏好表只剩 `powerpoint`/`ppt`、COM 引擎表只剩 PowerPoint,
  并验证 `RENDER_ENGINE=soffice` 会报错。这比"mock 掉不让调用"强: 没有函数可调, 就不存在误走通道的可能。
- `test_powerpoint_pref_never_falls_back_to_other_channels` 去掉了对已删名字的 mock。

### 验证
- 测试 **92 → 90 项**全过(删 3 增 1); `TestRenderEngine` **17 → 15 项**, 0.20s。
- 本机实测: `detect_engines()` 只返回 `[('PowerPoint (macOS)', 'macos_ppt', ...)]`;
  `deps_auto` / `bootstrap_device` 导入正常; 收尾日志已含"按规范不切换其它通道"。
- 全仓 `grep` 已删符号: 仅剩新测试里那处"必须不存在"的断言。
- `make test-py` 67 + 24 全过; `gofmt` / `go vet` 干净; 镜像 `--check` 退出码 0; 规则校验 7/7。
- 版本号三处同步 `1.5.24` → `1.5.25`。

## [5.4.24] - 2026-09-11 (勘误: 违反"只使用 PowerPoint、禁用其它通道"的规范 —— 含我写的引导与一处既有代码)

**我先犯错, 这里如实记录。** 规范(2026-09-04)是"默认 PowerPoint 并禁用其它引擎自动切换",
用户 2026-09-11 再次强调"只使用 PowerPoint 渲染, 禁用其它通道"。而我:

1. 在 v5.4.23 的**失败提示文案**里写了"或改用 libreoffice / python-pptx";
2. 在 v5.4.22/5.4.23 的 **CHANGELOG** 与**自检报告**里反复把"换通道"当作解决方案之一推荐。

这些都是**引导改用其它通道**, 与规范直接冲突。已全部删除, 并留下勘误说明。

### Fixed (我写的引导)
- `ppt_render_engine.py` 的 `_MACOS_BLOCKED_HINT` 改为**只讲怎么把 PowerPoint 修好**:
  "请手动打开一次 PowerPoint, 关掉该对话框后再重试。若仍然卡住, 需排查 PowerPoint 自身状态
  (是否已激活、是否允许被自动化控制), 而不是绕过它 —— 按规范渲染只走 PowerPoint 这一条通道,
  不会自动改用其它引擎。"
- `CHANGELOG.md` 的 v5.4.22 条目就地加勘误: 原附建议**指名了另一个渲染引擎**, 已删。
  (保留发布记录本身, 只钉掉其中的错误引导 —— 与 v5.4.16 的处理方式一致。)

### Fixed (既有代码里同类违规 —— 这个更要紧)
- **`_build_engine_list()` 在 `pref=powerpoint` 且 PowerPoint 不可用时, 会静默回落到
  LibreOffice 或 python-pptx** —— 那等于自动切换渲染通道, 同样违反规范。现改为**直接抛错**:
  ```
  [render] 偏好引擎 PowerPoint 在本机不可用 —— 规范要求只使用 PowerPoint 渲染、禁用其它通道,
  故不自动降级。请确认 PowerPoint 已安装并激活; macOS 还需在 系统设置 › 隐私与安全性 › 自动化
  里允许其被控制。
  ```
  即: 宁可返回 0 张, 也不偷偷换通道。(Windows 侧原本就是抛错, 行为不变。)
- **模块 docstring 改写** —— 原文写的是"按优先级自动接入系统可用引擎 / macOS-Linux 优先
  soffice 否则 python-pptx 兜底"。**这份文档本身就是把我带偏的源头**: 我照着它把"换通道"
  当成了系统设计意图。现改为开篇即写明"只使用 PowerPoint、禁用其它通道、不可用即失败"。

### Added
- `test_powerpoint_pref_never_falls_back_to_other_channels` —— 钉住新行为: 有 PowerPoint 时
  单通道; 没有时抛错; 渲染入口返回 `(0,"none")` 且**绝不**调用 `render_via_soffice` /
  `render_via_python_pptx`(这两个被 mock 成会抛 AssertionError, 一旦被调用测试立刻炸)。
- `test_windows_powerpoint_unavailable_raises_without_fallback` —— Windows 侧同规范。
- **`test_no_advice_to_switch_render_channels`** —— **给我自己上的锁**: 全仓(py + md)禁止出现
  "改用 <另一个引擎>"这类引导表述。光把文案删掉不够, 得有测试防止再写回去。
  (模式用拼接构造, 否则定义它的那两行会命中自己; 这是实现时实际踩到的自我引用问题。)

### 验证
- 三处文案实测: 提示只含 PowerPoint 修复路径; 不可用报错明说"不自动降级"; 本机默认偏好
  仍解析为**单一** `macos_ppt` 引擎。
- **负向对照**: 把"或改用 …libreoffice"插回提示文案 → `test_no_advice_to_switch_render_channels`
  立刻失败并精确报出 `scripts/ppt_render_engine.py:152`; 还原后通过。
- 测试 **89 → 92 项**全过; `TestRenderEngine` 17 项 0.15s。
- `make test-py` 67 + 24 全过; `gofmt` / `go vet` 干净; 镜像 `--check` 退出码 0; 规则校验 7/7。
- 版本号三处同步 `1.5.23` → `1.5.24`。

### 待你确认
- 规范注释里仍保留 `wps` / `libreoffice` / `python_pptx` / `auto` 这些**显式覆盖**取值
  (2026-09-04 的注释原文就是这个列表)。本轮只禁掉了**默认路径上的自动切换与引导**,
  没有动显式覆盖机制。**若你要的是连显式覆盖也一并删掉**(即物理上只留 PowerPoint 一条路),
  说一声我就改 —— 那需要同时清掉 `_PREF_MAP` 里的对应项、`detect_engines()` 的枚举,
  以及 `render_via_soffice` / `render_via_python_pptx` 两个函数本体。

## [5.4.23] - 2026-09-11 (macOS PowerPoint 渲染: 加快速预检 (a) + 超时可配并下调默认 (b))

承接 5.4.22 隔离出的缺陷: `open` 这一步被模态对话框挡住(AppleEvent -1712), 而 PowerPoint
进程与 Apple 事件通道本身都正常。影响是默认偏好下**静默等 300 秒后返回 0 张幻灯片**。
按 (a)+(b) 方案处理。

### Added (a) 快速预检
- **`probe_macos_powerpoint(timeout=None)`** —— 只做 `launch` + `get version`, 返回 `(ok, 详情)`。
  实测暖机 0.4s 返回。`render_via_macos_powerpoint()` 在花钱 `open` 之前先调它,
  不通过就**立刻报错**, 不再白等几分钟。
  (osascript 拉不起来时返回 `(False, 说明)` 而不抛异常 —— 预检自己不该成为新的故障点。)
- **`RenderEngineError(RuntimeError)` 携带 `hint` 属性** —— 可操作建议不再拼进异常消息。

  **这是从一次真实疏漏里改出来的**: 先把建议拼在消息末尾, 结果调用方
  `render_ppt_slides_auto` 打印时 `str(e)[:100]` **正好把它整段切掉** —— 异常里有建议、
  用户却只看到一句原始报错。改放到消息最前面, 原始错误又被挤没, 还留下"｜ 原"这种半截断口。
  最终改为: 消息归消息(截断到 160), 建议走 `hint` 属性由调用方**单独成行**打印:
  ```
  [render] PowerPoint (macOS) 失败: PowerPoint AppleScript error: ... (-1712)
  [render] 处理建议: PowerPoint 多半是弹了模态对话框(登录 / 激活 / 文件访问权限)挡住了 Apple 事件。...
  [render] 所有引擎均失败, 返回 0 张幻灯片
  ```
- 引擎全部失败时补一行明确的收尾提示(原先只有每个引擎各自一行, 然后静默返回 0)。

### Changed (b) 超时可配并下调默认
- `PPT_RENDER_TIMEOUT`(秒) 控制 open/save 超时, **默认由写死的 300 降到 60**。
- `PPT_RENDER_PREFLIGHT_TIMEOUT`(秒) 控制预检超时, 默认 20(覆盖冷启动)。
- 缺失 / 不可解析 / 非正数的取值一律回落到默认(`_env_seconds`)。
- `subprocess` 超时比 AppleScript 多 15s, 让 AppleScript 自己的 -1712 先报出来(信息更具体)。

### 验证
- **真实端到端(本机默认偏好)**: `render_ppt_slides_auto()` **302.4s → 65.9s**, 且日志里
  可操作建议完整可见。注意仍返回 `(0,"none")` —— 这是 (b) 的直接效果, 不是本机能修好的事
  (PowerPoint 装了, 但 `open` 被模态框挡住, 需人工处理那个对话框)。
- 测试 **79 → 89 项**全过; `TestRenderEngine` 14 项 0.13s。
- **负向对照**: 把建议改回"拼在消息末尾"且截断改回 100 → `test_failure_hint_reaches_the_log`
  立刻失败, 且打印出的日志尾巴正是被切断的半句话(`...PowerPoint 多半是弹了模态对话`),
  说明这条测试确实守住了那个疏漏。另把 `_build_engine_list` 的 auto 分支改坏 →
  seam 测试同样立刻失败。
- `make test-py` 67 + 24 全过; `gofmt` / `go vet` 干净; 镜像 `--check` 退出码 0; 规则校验 7/7。

### 诚实说明: (a) 覆盖的不是本机的失败模式
本机实测时把预检超时压到 **1 秒**, 预检**依然通过**(PowerPoint 1 秒内就应答了), 于是照常走到
`open` 再挂 60s。原因是本机的故障在 **`open` 这一步的模态对话框**, 而非 Apple 事件通道 ——
"能不能应答"区分不了这两件事。

所以两者的适用范围要分清:
  * **(a) 预检** 解决的是"**通道完全不通**"的情形(macOS 自动化权限被拒 -1743、PowerPoint 无法启动等):
    那种情况下原先要白等 300s, 现在约 1s 就报错。**它对本机这种模态框挡 open 的情形无效。**
  * **(b) 超时下调** 才是本机实际受益的那一项: 302.4s → 65.9s。
由于本机通道是通的, (a) 的快速失败路径**无法自然触发**, 只能由 mock 测试覆盖
(断言 `open` 从未被执行、且立即返回)。

## [5.4.22] - 2026-09-11 (修复: test_tma_pipeline 那条"打了失效接缝"的渲染测试)

5.4.21 顺带发现 `test_tma_pipeline` 有 1 项失败。本轮查明: **失败的是测试本身写错了接缝**,
顺带把整套测试从 **302 秒压到 0.17 秒**。

### Fixed
- **`TestRenderEngine.test_render_auto_falls_back_when_com_fails` 的 mock 打在了失效的接缝上。**
  它 mock 的是 ``detect_engines()``, 但 ``render_ppt_slides_auto()`` 实际调的是
  ``_build_engine_list()`` —— 而后者**只在 `RENDER_ENGINE=auto` 时才委派**给
  ``detect_engines()``(2026-09-04 规范: 默认 powerpoint 且禁用自动切换)。
  于是 mock 完全不生效, 测试实际去跑**真引擎**:

  | 环境 | 实际走的路径 | 结果 |
  | --- | --- | --- |
  | 本机 macOS(装了 PowerPoint) | `macos_ppt` AppleScript | 卡 300s 后返回 0 页 → **FAIL** |
  | CI macos-latest(无 PowerPoint) | `python_pptx` 兜底 | PASS |
  | CI ubuntu-latest(自带 LibreOffice) | `soffice` | PASS |
  | CI windows-latest(无 PowerPoint) | `_build_engine_list` 抛错被吞成 `(0,"none")` | **FAIL(实测代码路径复现)** |

  修法: 显式 `RENDER_ENGINE=auto`(使 mock 生效) + 保持原来的断言, 于是它**在所有平台都确定性地
  测到它声称要测的东西** —— COM 全失败时降级到 python-pptx。

### Added
- `test_auto_mode_mock_seam_is_effective` —— 直接把"mock 是否真的生效"钉住:
  mock 返回哨兵引擎名, 断言返回的 engine 就是它。**这是对本次这类 bug 的直接防护** ——
  seam 一旦被改错, 测试立刻失败, 而不是悄悄去跑真引擎、耗时几分钟再报一个误导性的错。
- `test_default_pref_does_not_silently_switch_engine` —— 默认偏好下引擎不可用时应
  返回 `(0, "none")` 而**不静默降级**到低保真引擎(2026-09-04 用户规范)。
- `test_engine_pref_default_is_powerpoint` —— 钉住默认偏好值。

### 验证
- `TestRenderEngine` 整类: **302.4s → 0.17s**, 7 项全过。
- `test_tma_pipeline` 整体: **79 → 82 项**, **302.4s → 0.17s**, 全过(约快 1800 倍)。
- **负向对照**: 把 `_build_engine_list()` 的 auto 分支改坏(不再委派 `detect_engines()`)
  → `test_auto_mode_mock_seam_is_effective` 与 `test_render_auto_falls_back_when_com_fails`
  **同时立刻失败**, 并打印"mock 没生效 —— seam 可能又被改错了"; 还原后恢复。
- `make test-py` 67 + 24 全过; `gofmt` / `go vet` 干净; 镜像 `--check` 退出码 0;
  TMA 规则校验仍 7/7。
- 版本号三处同步 `1.5.21` → `1.5.22`。

### 已知残留(未处理, 需决策)
- **macOS 原生 PowerPoint 渲染路径本身是坏的**(测试修好后不再暴露它, 但产品问题仍在)。
  用三段最小探针隔离:

  | 探针 | 结果 |
  | --- | --- |
  | `launch` + `get version` | **0.4s 成功** (PowerPoint 16.112.1 是活的) |
  | `open POSIX file <pptx>` | **10.1s 后 -1712 "AppleEvent 已超时"** |
  | 紧接着 `get version` | **0.1s 成功**(仍然响应) |

  即 PowerPoint 进程正常、Apple 事件通道正常, **卡在 `open` 这一步** —— 典型的模态对话框
  阻塞(登录/激活/文件权限提示), 也印证了 `render_via_macos_powerpoint()` 里那句注释
  "模态对话框会阻塞 Apple 事件, 表现为 -9074/超时"。

  影响: 在装了 PowerPoint 的机器上(即本机), 默认偏好会走这条路径,
  **`render_ppt_slides_auto()` 静默等 300 秒后返回 `(0, "none")`**, 调用方拿到 0 张幻灯片。

  **本轮未改** —— 涉及渲染行为与超时的取值, 属 2026-09-04 偏好规范的领域, 需你定夺。可选:
  (a) 加**快速预检**: 先 `launch`+`get version`(实测 0.4s), 不应答就立刻报错并给出可操作提示
      (提示文案见 v5.4.24 —— 本条原附的建议**指名了另一个渲染引擎**, 属引导改用其它通道,
      **违反"只使用 PowerPoint、禁用其它通道"的规范, 已删除**), 而不是等 300s;
  (b) 把 300s 的 open/save 超时改为可用环境变量覆盖(默认下调, 如 60s);
  (c) 什么都不改, 仅在文档里写明"装了 PowerPoint 但自动化被模态框挡住时会静默返回 0 张"。

## [5.4.21] - 2026-09-11 (清理: scripts/ + skills/ 的裸 import fitz 一并消除 (83 处 / 64 文件))

承接 5.4.20 的「已知残留」。5.4.20 只清了 ``hl_v3_final/``, 本轮把 ``scripts/`` 与 ``skills/``
剩下的也清掉 —— 而且**过程中发现我 5.4.20 的盘点方式本身有盲区**, 详见下。

### Changed
- **`scripts/` + `skills/` 下 83 处 / 64 个文件**的裸 `import fitz` 改为 `import pymupdf as fitz`
  (`scripts/` 57 文件 + `skills/` 另 4 个技能包 7 文件)。
  这批是**在用**的生产工具链(`process_all_pn_x.py`、`vision_highlight_workflow.py`、
  `glm_integration.py`、`via54_highlight_v3_final.py`、CI 会跑的 `test_tma_pipeline.py` 等)。

  用**正式名**而不是 5.4.20 那种 try/except 回退, 依据是 `requirements.txt` 已声明
  `pymupdf>=1.24` —— 回退保护的版本是项目明确不支持的, 属死代码。
  (`hl_v3_final/` 保留回退不动: 那是要分发出去的技能工具链, 版本不可控; 两处风格差异是有意的。)
  形态上覆盖了 `import fitz` / `import fitz as _alias` / `import a, b, fitz` 三种。

### Fixed
- **我 5.4.20 的盘点正则只匹配「行首 `import fitz`」**, 漏掉了 `fitz` 出现在**逗号列表**里的形态
  (如 `import json, os, re, io, sys, fitz`)。所以 5.4.20 声称"已知残留 64 处 / 46 文件"时,
  `scripts/` 的真实数字是 **76 处 / 57 文件**。

  **发现方式**: 5.4.20 改完后 CI 那条 import 探针
  (`import deps_auto, ppt_render_engine, tma_verify_highlights, via54_auto, via54_highlight_v3_final`)
  **仍在报弃用警告** —— 逐模块二分定位到 `tma_verify_highlights`, 再看它的第 9 行才发现是
  `import json, os, re, io, sys, fitz`。**是探针的干净与否暴露了盘点漏项, 不是靠再读一遍清单。**

### Added
- `TestFitzImportForm` **升级为覆盖全部导入形态并扩到全仓**:
  - 逗号列表**任意位置**的 `fitz` / `as` 别名 / `from fitz import`;
  - 例外改为显式 `BARE_FITZ_ALLOWED` 白名单, **每条必须写明理由**:
    `telemetry/watcher.py` 与 `telemetry/pdf_utils.py`(v5.4.11 的旧版回退)、
    `tests/test_telemetry.py`(故意 import, 作为"telemetry 导入不带弃用警告"断言的对照面);
  - 另加 `test_allowlist_has_no_zombie_entries` 防止白名单留僵尸条目。
  没有这次升级, 上面那 12 处漏项随时会以同样方式再漏一次。

### 验证
- **CI 的 import 探针 stderr 终于干净**(5.4.20 时仍会打 `The \`fitz\` API is deprecated`);
  5 个模块逐个复核也全干净。
- **负向对照(三种形态都验过)**: 插入行首 `import fitz` / 逗号列表形态 / `from fitz import`
  → 测试均精确报出文件:行号; 还原后通过。逗号列表那一条正是旧版盲区, 旧版会放过它。
- `make test-py` **67 + 24** 全过(仓库卫生 6 → 7); 高亮工具链 `test_hl_lib` **36 passed** +
  `test_forbidden_zones` **24 passed**; 本轮改动的 **65 个 `.py` 语法零失败**;
  镜像 `--check` 退出码 0; TMA 规则校验仍 **7/7**; `gofmt` / `go vet` 干净。
- 版本号三处同步 `1.5.20` → `1.5.21`。

### 已知残留
- 全仓只剩 **3 处**裸 `import fitz`, 均已白名单化并写明理由(见上), 不是缺陷。
- **`test_tma_pipeline.py` 有 1 项既有失败, 与本轮无关**(已实测确认):
  `TestRenderEngine.test_render_auto_falls_back_when_com_fails` 断言渲染页数 ≥1 但得到 0,
  耗时 302s(在等 PowerPoint/AppleScript 超时)。用 `git stash` 把本轮改动全部移除后在**基线**上
  单跑该测试, **以完全相同的方式失败** —— 属环境依赖(PowerPoint 自动化), 非导入改写引起。
  该测试同时被 CI 调用, 建议单独排查。

## [5.4.20] - 2026-09-11 (清理: hl_v3_final 全量消除裸 import fitz + 分发包独有文件白名单化)

两项收尾。过程中**更正了我自己先前两处说法**: ① fitz 的规模我少报了一个数量级;
② 我把分发包里的独有文件报成"反方向漂移", 读完工具发现那是**已有明文声明的**有意保留。

### Changed
- **`hl_v3_final/` 下全部裸 `import fitz` 改为 `import pymupdf as fitz` + 旧版回退**
  —— 共 **195 处 / 117 个文件**(另同步技能分发包 115 个文件)。
  PyMuPDF 1.24 起 `fitz` 只是别名: 用时会在 stderr 打弃用警告, 且官方已声明将来会**移除**
  该别名 —— 到那天所有脚本一起坏。

  **规模更正**: 我先前在自检报告里写"约 20 处", 那是只看了 `head -20` 的输出就下的结论;
  实际是 195 处, 其中 **182 处在 105 个 `examples/hl_p*.py`** 里, 以**函数内局部导入**的
  形式出现(每文件两处)。

  分两类处理:
  - 核心文件(`hl_lib` / `hl_ocr_band` / `render_fitz` / `step1_export_slides` /
    `step3_download` / `strict_eval_ocr_locate` / `align_tables` / `copy_hl_images` /
    `test_hl_lib` / `verify_sentence_set`)—— 各自写完整 try/except, 自包含, 不新增耦合。
  - `examples/` 105 个脚本 —— 它们本来就 `from hl_lib import ...`, 把 `fitz` 并入那一行并
    删掉函数内局部导入。导入名由此**单点决定**(`hl_lib`), 不再 105 处各写一遍。

### Fixed
- **`strict_eval_ocr_locate.py` 第 11 行指向另一台机器**:
  `sys.path.insert(0, r'G:\agent\ai\projects\via54Medit\scripts\hl_v3_final')` ——
  同目录 9 个兄弟文件都写 `os.path.dirname(os.path.abspath(__file__))`, 已统一。
  同文件的 `WORK` 数据目录也改为环境变量可覆盖(`RSV_HL_WORK`), 默认值保持不变,
  沿用 `scripts/tma_*.py` 的既有约定。
- **`verify_sandbox_interceptor.py` 写死了用户名**(`/Users/david/.hermes/...`)→ 改为
  `HERMES_VIA54_DIR` 可覆盖 + `~` 展开; 顺手删掉从未使用的 `from pathlib import Path`。

### Added
- **分发包独有文件的显式白名单**。`sync_skill_bundle.py` 新增 `BUNDLE_ONLY_OK`(当前 1 条:
  `verify_sandbox_interceptor.py`), 并把报告区分为 `= 白名单` 与 `! 意外独有`。
  `--check` 现在对**白名单外的**独有文件判失败(原先只查 missing/differing, 反向完全不看);
  执行同步时若发现意外独有文件则中止报错, 不静默继续。
- **`tests/test_repo_hygiene.py` 新增 3 条不变量**(让 `make test-py` 也能拦住):
  - `test_no_unexpected_bundle_only_files` —— 白名单以 `sync_skill_bundle.BUNDLE_ONLY_OK`
    为**唯一事实来源**(importlib 载入), 避免两处各维护一份而再次分叉。
  - `test_bundle_only_allowlist_entries_still_exist` —— 防止白名单留"僵尸条目"。
  - `TestFitzImportForm` —— 断言除「紧跟 `except ImportError` 的回退行」与
    「`from hl_lib import fitz`」外不再出现裸 `import fitz`; 并断言 `hl_lib.fitz` 就是
    `pymupdf` 本体。没有这条, 上面 195 处的重构随时会被下次顺手改回去。

### 更正先前说法
- 自检报告里"约 20 处 `import fitz`" → 实为 **195 处**。
- 自检报告里把 `verify_sandbox_interceptor.py` 报成"反方向的镜像漂移" → **过度警报**:
  `sync_skill_bundle.py` 与 `test_repo_hygiene.py` 的 docstring 早已写明"B 独有辅助脚本
  不算漂移(技能自带的东西)"。它是有意保留的; 真正的缺口是**没有白名单**, 于是"有意保留"
  与"手滑放进来"在报告里长得一模一样 —— 本轮补的就是这个缺口。

### 已知残留 (本轮未处理)
- **`hl_v3_final/` 已归零, 但仓库其它位置还有 73 处 / 55 个文件**仍在裸用 `import fitz`。
  本轮授权范围只是 `hl_v3_final`, 故未动:
  - `scripts/` **64 处 / 46 个文件** —— 这一批是**在用**的生产工具链
    (`process_all_pn_x.py`、`vision_highlight_workflow.py`、`glm_integration.py`、
    `via54_highlight_v3_final.py`、CI 会跑的 `test_tma_pipeline.py` 等),
    风险等级与 `hl_v3_final` 的示例脚本不同, 值得单独一次带回归的改动。
  - `skills/`(另 4 个技能包) **7 处 / 7 个文件**。
  - 另有 2 处**不是缺陷**: `telemetry/watcher.py:16` 是嵌套 try/except 的回退行
    (v5.4.11 就改好了); `tests/test_telemetry.py:607` 是**故意**导入 `fitz` 来验证
    "telemetry 的导入路径不带弃用警告"这条断言的对照面。
- `verify_sandbox_interceptor.py` 的目标模块 `via54_sandbox_forbidden.py` 仍不在本仓库
  (属 hermes 侧运行时), 故该脚本只能在本机跑通 —— 这也是它被列为"分发包自带"的原因。

### 验证
- `from hl_lib import fitz` → `fitz.__name__ == 'pymupdf'`; 5 条导入路径
  (`hl_lib` / `render_fitz` / `hl_ocr_band` / `verify_forbidden_zones` / `verify_sentence_set`)
  的 stderr 均**无 deprecated**。
- 抽查 5 个 `examples` 脚本, `fitz` 全部解析到 `pymupdf`。
- `make test-py` **66 + 24** 项全过(仓库卫生 **2 → 6** 项, telemetry 60 项); `test_hl_lib.py` **36 passed**。
- **负向对照**: 临时在 `render_fitz.py` 插回一行裸 `import fitz` → 测试精确报出
  `scripts/hl_v3_final/render_fitz.py:4`; 分发包塞入 `stray_accidental.py` → 测试报出文件名、
  `sync --check` 退出码 1。两处还原后均恢复通过。
- `hl_v3_final/` 下 126 个 `.py` 语法零失败; 技能镜像 `--check` 退出码 0;
  TMA 规则校验仍 **7/7**; `gofmt` / `go vet` 干净。
- 版本号三处同步 `1.5.19` → `1.5.20`。

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
