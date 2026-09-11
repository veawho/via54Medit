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

```bash
medit doctor            # 全项探测: Python/包/浏览器/CDP/pdftotext/lark-cli
medit doctor --fix      # 自动 pip 安装缺失的 Python 包
medit browser start     # 自动探测 Chrome/Edge/Chromium 并启动 CDP 调试实例 (port 9223)
medit browser health    # 验证 CDP 可达
python3 scripts/render_doctor.py   # 渲染通道**真出图**自检 —— 跑管线前必做, 见 §2.1
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
