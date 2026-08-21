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
medit doctor            # 全项探测: Python/包/浏览器/CDP/soffice/pdftotext/lark-cli
medit doctor --fix      # 自动 pip 安装缺失的 Python 包
medit browser start     # 自动探测 Chrome/Edge/Chromium 并启动 CDP 调试实例 (port 9223)
medit browser health    # 验证 CDP 可达
```

### 各平台软件接入矩阵

| 能力 | Windows | macOS | Linux |
|---|---|---|---|
| Python 3.10+ | `python.org` 安装包 | `brew install python@3.11` | `apt install python3.11` |
| Python 包 (fitz/pptx/PIL) | 自动 pip (`doctor --fix` / `deps_auto.py`) | 同左 | 同左 |
| PPT 真实渲染 | PowerPoint/WPS COM (自动探测+装 pywin32) | LibreOffice soffice (自动探测) | LibreOffice soffice |
| PPT 近似渲染 (兜底) | python-pptx (含 CJK 字体: 微软雅黑) | python-pptx (苹方/黑体探测) | python-pptx (Noto CJK 探测) |
| 浏览器 CDP | Chrome/Edge 自动启动 | Chrome/Chromium 自动启动 | chromium 自动启动 |
| PDF 文本 (pdftotext) | 需 poppler (可选) | `brew install poppler` | `apt install poppler-utils` |
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

`.github/workflows/ci.yml` 在 ubuntu/macos/windows 上自动执行:
- Go: `go build ./...` + `go vet ./...` + `go test -race ./...`
- Python: `pip install -r requirements.txt` + test_tma_pipeline (79) + hl_lib (25) + 工具链 import

## 6. 常见问题

| 症状 | 处理 |
|---|---|
| `chrome CDP unreachable` | `medit browser start` 自动启动; 或设 `$CHROME_PATH` |
| Python 包缺失 | `medit doctor --fix` |
| HLO 脚本找不到 | 设 `HLO_DIR` 指向含 hlo_nlu_v2.py 的目录 |
| 中文字体渲染模糊 | 装系统 CJK 字体 (Linux: fonts-noto-cjk; macOS 自带苹方) |
| antfu 登录 | `medit antfu open` 打开登录页 → `medit antfu capture` |
