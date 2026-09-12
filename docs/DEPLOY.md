# DEPLOY — 任意设备部署指南 (Windows / macOS / Linux)

> 2026-08-21 跨平台化: Go 核心 + Python 工具链 + skills 均可在新设备自动接入。
> 新设备三步走: **安装二进制 → `medit doctor` 自检 → `medit browser start` 起 Chrome**。

## 1. 安装二进制

### 方式 A: 官方发布 (推荐)

| 平台 | 安装方式 |
|---|---|
| macOS | Homebrew tap (见发布说明) 或下载 `medit_darwin_*.tar.gz` |
| Linux | `.deb` / `.rpm` / `.apk` 包 (goreleaser nfpm) 或 tar.gz |
| Windows | Scoop bucket (见发布说明) 或 zip 解压 (含 `medit.exe` / `medit-mcp.exe`) |

支持矩阵: **windows/amd64 + arm64, darwin/amd64 + arm64, linux/amd64 + arm64** (CGO=0, 纯静态)。

### 方式 B: 源码构建

```bash
git clone https://github.com/veawho/via54Medit.git
cd via54Medit
go build -o bin/medit ./cmd/medit/          # 或 make build
```

## 2. 环境自检与自动接入 (核心)

**部署到任何新设备、或更新到任何版本之后, 先跑这一条**:

```bash
python3 scripts/bootstrap_device.py   # 深度扫描 + 按平台补齐缺口 + 渲染自检 + 构建 + 注册自动更新
```

只想看、不想改:

```bash
python3 scripts/deploy_scan.py --check   # 深度扫描(只报不改); 退出码 0 = 必需能力齐备
python3 scripts/deploy_scan.py --dry-run # 预演: 打印**将执行的完整命令**, 不落地任何修改
medit doctor                              # 同一份扫描结果的 Go 侧渲染(多一项 CDP 可达性)
medit doctor --plan                       # 同上, 但只报计划 (= deploy_scan.py --dry-run)
medit browser start / health              # CDP 调试实例 (port 9223)
python3 scripts/render_doctor.py          # 渲染通道**真出图**自检 —— 跑管线前必做, 见 §2.1
```

先预演、再决定装不装:

```bash
python3 scripts/bootstrap_device.py --dry-run          # 一键部署的预演(不落地)
python3 scripts/deploy_scan.py --only ocr               # 只补一个能力
python3 scripts/deploy_scan.py --list                   # 列出所有能力键(配合 --only)
```

### 2.1 渲染前置条件 (部署后必读)

PPT / Word 的**版式**只能由微软的引擎产出 —— 第三方引擎会各自重排 OOXML, 字体与断行都和原版
分叉, 已整体删除(判定标准与证据见 `docs/ppt-render-fidelity.md`)。所以各平台的渲染路径是:

| 能力 | Windows | macOS | Linux |
|---|---|---|---|
| PPT 版式渲染 | 桌面版 **PowerPoint** (COM, 需 pywin32) | 桌面版 **PowerPoint** (原生 AppleScript) | ✗ 需显式 `RENDER_ENGINE=graph` |
| Word 版式渲染 | 桌面版 **Word** (COM) | 桌面版 **Word** (原生 AppleScript) | ✗ 先用 Word 另存为 PDF 再传入 |
| 微软在线渲染 | `RENDER_ENGINE=graph` (Microsoft Graph, 需凭据) | 同左 | 同左 |
| PDF / 图片 → 分页图 | pymupdf (pip, 只光栅化不重排) | 同左 | 同左 |

**没有兜底通道**: WPS / LibreOffice / Keynote / python-pptx / Aspose / Spire / GroupDocs /
Syncfusion 都已删除。拿不到微软引擎就**直接失败**, 不会产出"看起来像"的近似渲染。

**部署后先跑真出图自检, 别跳过**:

```bash
python3 scripts/render_doctor.py           # 真出图探针: 现场造最小文档, 用生产函数真渲染一遍
python3 scripts/render_doctor.py --quick    # 只查依赖(快, 但**不能**据此认为能渲染)
```

为什么不能只看依赖探测: 实测 `launch` + `get version` **秒回**, 但真正 `open` 文档时会被
模态对话框挡住一直挂着 —— 只查依赖会给**假 OK**, 管线跑到渲染那步才炸。
`render_doctor.py` **退出码非 0 就说明这台设备现在渲染不出来**, 先解决它再跑管线。

macOS 上若报 `AppleEvent -1712` / `-1708`: 手动打开一次 PowerPoint / Word 关掉模态对话框,
并在 系统设置 › 隐私与安全性 › 自动化 里放行当前终端(或 Agent)。

### 2.2 各平台依赖接入矩阵

| 能力 | Windows | macOS | Linux |
|---|---|---|---|
| Python 3.10+ | `python.org` 安装包 | `brew install python@3.11` | `apt install python3.11` |
| Python 包 (pymupdf/pptx/PIL) | 自动 pip (`doctor --fix` / `deps_auto.py`) | 同左 | 同左 |
| 桌面版 Office (渲染必需) | Microsoft PowerPoint / Word | Microsoft PowerPoint / Word | ✗ (或用 `RENDER_ENGINE=graph`) |
| 浏览器 CDP | Chrome/Edge 自动启动 | Chrome/Chromium 自动启动 | chromium 自动启动 |
| pdftoppm (`RENDER_RASTERIZER=pdftoppm` 时) | 需 poppler (可选) | `brew install poppler` (可选) | `apt install poppler-utils` (可选) |
| 飞书 CLI | `$LARK_CLI` 指定 | 内置默认 | `$LARK_CLI` 指定 |

### 2.3 深度扫描: 按平台只装"相关且缺失"的

能力矩阵的**唯一事实来源**是 `scripts/deploy_scan.py`。Go 侧的 `medit doctor`、
`deps_auto.py`、`bootstrap_device.py` 都读它, 不再各自维护清单 ——
历史上三份清单互相打架, 其中两份还写着 `pip install mmx-cli`, 而它**不是** PyPI 包
(是 npm 包), 于是那一步**从来没能成功过**, 还被退出码吞掉。

扫描分三段:

| 段 | 内容 |
| --- | --- |
| 1. 环境 | OS / 架构 / 容器 / 解释器 / 包管理器 / 输出编码 |
| 2. 能力 | 逐项探测; **与平台无关的标 `· 不适用`, 既不安装也不校验** |
| 3. 兼容性 | 硬编码 `/tmp`、外机绝对路径、未加 darwin 守卫的 `osascript` 等平台相关代码点 |

**平台过滤的实际效果**(这就是"部署到 Windows 不必管 macOS 那一套"的落点):

| 能力 | Windows | macOS | Linux |
| --- | --- | --- | --- |
| `pywin32` (Office COM) | 必需, 缺失即装 | **不适用**(不装、不校验) | **不适用** |
| 桌面版 PowerPoint / Word | 必需(装不了则强力提示) | 同左 | **不适用** → 用 `RENDER_ENGINE=graph` |
| PaddleOCR (L2 中文 OCR) | 缺失即装 | 缺失即装 | 缺失即装 |
| PaddleOCR **权重** | 缺失即预热 | 同左 | 同左 |
| `mmx-cli` 视觉引擎 | 经 **npm** 装 | 同左 | 同左 |
| mmx **凭据** | 有 `MINIMAX_API_KEY` 则代登 | 同左 | 同左 |

### OCR 与 mmx-cli 的"部署"到底包含什么

这两条通道各有一个很隐蔽的**假就绪**, 都实测到过。所以它们的部署不是"看到文件在":

| 通道 | 假就绪的样子 | 真实代价 | 本仓库怎么判 |
| --- | --- | --- | --- |
| OCR | 两个包能 `import` 就报"已就绪" | 权重没下 —— 首次真实调用会去联网下 ~170MB, 离线/受限网络下必然失败, 而失败点是 L2 那一步 | ① 包可导入 ② **权重已落地**(`$PADDLE_PDX_CACHE_HOME/official_models` 有 det/rec) ③ `--verify-ocr` **真跑一次识别** |
| mmx | 二进制在 PATH 里就报"已就绪" | 没认证 —— 视觉调用直接 401; 而报告里完全看不出来 | ① 二进制可用 ② `mmx auth status` / `~/.mmx/config.json` **已认证** |

**关键更正**: mmx 用的是**它自己**的凭据(`mmx auth login` 写进 `~/.mmx/config.json`),
与 `MINIMAX_API_KEY` 是两套。旧探测把结论建在环境变量上, 于是本机出现了方向相反的两个错误:
MINIMAX_API_KEY 未设置而 mmx 早已认证且能调通(假警报)、以及配了环境变量但没登录时
报"已配置"而实际 401(假就绪)。现在凭据只认 mmx 自己的状态; 有 `MINIMAX_API_KEY` 时
部署流程可以**代登**(`mmx auth login --api-key`), 没有则如实报"需人工"。

**版本约束**: OCR 包按 `paddleocr>=3.0,<4` / `paddlepaddle>=3.0,<4` 安装 —— 管线调的是
PaddleOCR 3.x 的 API(`use_textline_orientation` + `.predict()` + `result[0]['rec_texts']`),
不约束就会有一天静默装上 2.x/4.x, 而"装上了"与"能跑"是两件事。

**部署后复检**(部署器与更新器都会跑, 也可单独跑):

```bash
python3 scripts/deploy_scan.py --verify-ocr    # 真跑一次识别(顺带预热权重)
python3 scripts/deploy_scan.py --verify-mmx    # 二进制 + 认证, 两件事分开报
```

`--verify-mmx` 的**退出码只跟二进制走**: 凭据必须由人提供, 把它算成"部署失败"会让部署
永远无法成功(与矩阵里 `mmx_auth` 的 `gate=False` 是同一条判断)。

**安装通道**: Python 包 → pip;`mmx-cli` → npm;系统工具 → 本机可用的
brew / apt / dnf / pacman / winget / choco / scoop。需要管理员权限却拿不到时会
**打印该执行的完整命令**, 而不是静默失败。

**只装缺失的**: 已就绪的能力不会被重装, 所以本命令可以反复运行 —— 版本更新后再跑一次即可。

| 开关 | 作用 |
| --- | --- |
| `--check` | 只扫描, 不安装 |
| `--dry-run` | 预演: 打印将执行的完整命令, **不落地任何修改** |
| `--only KEY[,KEY]` | 只处理指定能力 (配合 `--list`) |
| `--list` | 列出所有能力键 |
| `--json` | 机器可读(供 `medit doctor` / CI 消费) |
| `--skip-heavy` | 跳过重依赖(OCR/Paddle, 数百 MB) |
| `--strict` | 平台兼容性问题也计入失败 |
| `--verify-ocr` / `--verify-mmx` | 真机复检: OCR 真识别 / mmx 可用与认证 |
| `--stage env\|deps\|compat\|all` | 只跑一个阶段(供外层部署器分步显示进度) |
| `make deploy-check` / `make deploy-fix` | 上面前两条的快捷方式 |
| `make deploy-plan` / `make deploy-only KEY=ocr` | 预演 / 只补一个能力 |
| `make deploy-only KEY=ocr_models` | 只预热 OCR 权重(真识别一次) |

**退出码**: `0` = 必需能力齐备; `1` = 仍有必需缺口; `2` = **用法错误**(能力键或阶段名拼错)。
三者刻意分开 —— 拼错一个开关不该被读成"这台机器环境有问题"。

**环境变量**(CI / 无人值守部署): 与开关一一对应 ——
`VIA54_DRY_RUN` / `VIA54_ONLY` / `VIA54_SKIP_HEAVY` / `VIA54_STRICT` / `VIA54_JSON` /
`VIA54_STAGE` / `VIA54_HOME`(私有前缀, 默认 `~/.via54medit`) / `VIA54_ALLOW_BREAK_SYSTEM` /
`VIA54_OCR_SMOKE_TEXT`(OCR 真识别探针用的样本文字, 默认 `OCR 12345`)。
命令行开关优先于同名环境变量。

OCR 的权重缓存根目录认 **`PADDLE_PDX_CACHE_HOME`**(PaddleX 自己读的变量, 默认 `~/.paddlex`;
权重在其下的 `official_models/`)。用别的名字覆盖是无效的 —— 探针会去看一个 PaddleX 根本
不写的位置, 于是永远报"权重缺失"。

### 2.4 装完凭什么算"装好了"

这一节的机制参考了两个成熟项目的部署方式 —— `hermes-agent`(`scripts/install.sh`、
`hermes_cli/dep_ensure.py`、`hermes_cli/managed_uv.py`)与 `openclaw`(`install.sh` /
`install-cli.sh` / `install.ps1`, 见其 `docs/install/installer.md`)。借来的做法:

| 机制 | 来自 | 本仓库的落点 |
| --- | --- | --- |
| **装后复验** | hermes: "installer reported success but binary not found" → 退出 1;openclaw: 残留 `lifecycle-pending` 标记时必须判失败 | 每次安装后**立刻重新探测**;复验不过就记成"仍缺失", 并单独报出复验详情。这条正是 Word 通道踩过的坑:`save as` 返回 rc=0 却**没有任何产出** |
| **探测"真的能跑"** | openclaw: "probe the exact executable it will use" | 工具探测从"文件在不在"升级为**真跑一次版本命令**。实测教训:`pdftoppm --version` 会把 `--version` 当文件名报 I/O Error, 只有 `-v` 可用 —— 所以版本开关逐个工具声明 |
| **私有前缀兜底** | openclaw `install-cli.sh`(全程无 root);hermes 把 node/uv 装进 `$HERMES_HOME` | `npm install -g` 撞权限时自动退回 `$VIA54_HOME/tools/node`;不 sudo、不污染系统 `node_modules`。探测也会查这个前缀, 否则装好的会被判成"没装"而反复重装 |
| **不静默越过边界** | openclaw: "unreadable npm version stops before package mutation";本项目 v5.4.3 的既定决定 | 撞上 PEP 668(`externally-managed-environment`)时**默认不追加** `--break-system-packages`, 而是报出三个可执行选项(venv / `--user` / 显式授权 `VIA54_ALLOW_BREAK_SYSTEM=1`) |
| **单能力补齐** | hermes `--ensure node,browser` | `--only KEY` —— 别的入口按需回调同一引擎, 不必各写一份清单 |
| **安装方式戳记** | hermes 的 `.install_method` | `$VIA54_HOME/.deploy_stamp.json` 记下每个能力**实际用了哪条通道**, 下次沿用同一条。复验没过的**不记**(否则下次会去沿用一条已知失败的通道) |
| **阶段 + 进度帧** | hermes `--stage` / `emit_stage_json` | `--stage env\|deps\|compat`;`bootstrap_device.py` 借此分步显示进度 |
| **`--dry-run`** | openclaw | 见上 |
| **不做交互** | 两者都规定 CI 里绝不提示 | 本工具**从不提示**。因此不提供 `--no-prompt` —— 它已是默认行为 |

**探测超时只给"跨 GUI / 授权边界"的探测**(Office 走 AppleEvent, 系统弹窗没人点时会
永远卡住, 把部署挂死)。**不给进程内 `import` 设超时** —— 那是个假阴性发生器:重的包
(如 Paddle) 首次导入会编译/初始化, 超过小上界就被误报"没装";而且被 `join` 超时掐断的
线程会继续在后台把导入跑完, 使同进程里**后续**探测得到不同结果。本机实测到过同一条命令
两次结论不同(一次 `missing` 一次 `ok`), 这条已由 `TestProbeTimeoutPolicy` 守住。

### 环境变量覆盖点 (新设备无需改代码)

| 变量 | 作用 |
|---|---|
| `PYTHON` | 指定 Python 解释器 (优先级: 配置 > $PYTHON > python3.11 > python3 > python) |
| `CHROME_PATH` | 指定浏览器可执行文件 |
| `HERMES_HOME` | skills/venv 数据根 (默认 ~/.hermes) |
| `HLO_DIR` / `HLO_PYTHON` / `HLO_SQLITE` | HLO 编排脚本/解释器/修正库 |
| `TMA_PROJECT` | TMA highlight 项目根 (所有 tma_* 脚本) |
| `LIT_ROOT` | 文献库根 (self_check) |
| `LARK_CLI` | 飞书 CLI 可执行文件 |
| `MEDIT_HOME` | via54Medit 数据根 (默认 ~/.medit) |
| `RENDER_ENGINE` | 排版引擎: `powerpoint`(默认, 桌面版) / `graph`(Microsoft Graph 在线渲染) |
| `RENDER_RASTERIZER` | 只光栅化不重排的下游: `pymupdf`(默认) / `pdftoppm`(强制 `-cropbox`) |
| `PPT_RENDER_TIMEOUT` / `WORD_RENDER_TIMEOUT` | 渲染等待上界(秒), 默认 60; 另有 `*_PREFLIGHT_TIMEOUT`(默认 20) |
| `GRAPH_TENANT_ID` / `GRAPH_CLIENT_ID` / `GRAPH_CLIENT_SECRET` / `GRAPH_DRIVE_ID` | `RENDER_ENGINE=graph` 所需凭据(或直接给 `GRAPH_ACCESS_TOKEN`) |

## 3. skills 接入 (经验库)

仓库 `skills/` vendored 了 9 个与代码/算法强绑定的核心 skills
(anno2ppt phase7 + pitfalls、highlight-strict、literature-pipeline 等):

```bash
python scripts/skills_bootstrap.py --list     # 查看将安装项
python scripts/skills_bootstrap.py            # 同步到 ~/.hermes/skills (幂等)
python scripts/skills_bootstrap.py --force    # 覆盖本机已修改版本
```

不随仓库分发的个人/机密 skills (客户项目、个人工作流) 仍留在本机
`~/.hermes/skills/`, 不会进入公开仓库。

## 4. Python 工具链独立部署

```bash
pip install -r requirements.txt               # 可复现安装 (pywin32 自动仅 Windows)
python scripts/deps_auto.py --check           # 只探测不安装
python scripts/deps_auto.py                   # 探测 + 自动安装
```

## 5. CI 验证 (三平台)

`.github/workflows/ci.yml` 在 **ubuntu / macos / windows** 上自动执行:
- Go: `go build ./...` + `go vet ./...` + `go test -race ./...`
- Python: `pip install -r requirements.txt` + `test_tma_pipeline`(120) + `hl_lib`(36) +
  禁止区校验 + **工具链 import 探测**(含整条渲染链路: `unified_render_engine` /
  `render_doctor` / `graph_render` / `bootstrap_device`)

Python 测试**刻意不依赖具体平台**: 测 darwin 分支的用例用 `_as_macos()` 伪装平台(同时伪装
`os.name` 与 `sys.platform`), 另有一条 `test_render_engine_suite_passes_on_non_macos` 在本机就把
`sys.platform` 伪装成 linux 重跑一遍 —— 防止再出现"本机绿、CI 红"。
(**教训**: v5.4.26~v5.4.31 连续六次提交在 ubuntu/windows 上是红的, 却因为只在本机 macOS 上
验证而一直没被发现。)

渲染通道的**真出图探针故意不进 CI** —— 跑者镜像里没有桌面版 Office, 它必然报不可用。
那一步在真机上跑: `python3 scripts/render_doctor.py`。

## 6. 常见问题

| 症状 | 处理 |
|---|---|
| `chrome CDP unreachable` | `medit browser start` 自动启动; 或设 `$CHROME_PATH` |
| Python 包缺失 | `medit doctor --fix` |
| HLO 脚本找不到 | 设 `HLO_DIR` 指向含 hlo_nlu_v2.py 的目录 |
| 中文字体渲染模糊 | 装系统 CJK 字体 (Linux: fonts-noto-cjk; macOS 自带苹方) |
| antfu 登录 | `medit antfu open` 打开登录页 → `medit antfu capture` |
