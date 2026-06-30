# 可重放性规则 (REPRODUCIBILITY)

> **目的**: 任何对 via54Medit 的修订, 必须确保**任何设备**部署后能**产生同等产出**.
> **生成日期**: 2026-06-30
> **铁律**: 通过本规则 = 任何后续开发者能"接力" 你的工作, 不需要"问原作者".

---

## 1. 三层保障 (确保可重放)

### Layer 1: 文档先行 (Document-First)
- ✅ `docs/PROCESS.md` 详细 5 步骤流程 (任何人都能 follow)
- ✅ `docs/SOLUTION.md` 架构 + 组件 + 决策 (理解"为什么")
- ✅ `docs/REPRODUCIBILITY.md` (本文件) 规则

### Layer 2: 自包含 (Self-Contained)
- ✅ 模板内置 (`templates/market-report-v1.html`)
- ✅ 脚本内置 (`scripts/`)
- ✅ 数据源清单内置 (`integrations/CATALOG.md`)
- ✅ 样式 + 图表 SVG 内嵌 (无外部库)

### Layer 3: 自动化测试 (CI/CD)
- ✅ `.github/workflows/report-reproducibility.yml` (待加)
  - 触发: PR / push to main
  - 检查: 模板可渲染 / 脚本可执行 / 输出 7 章节
- ✅ "Reproducibility test pass" badge (README.md)

---

## 2. 修订规则 (8 条铁律)

### Rule 1: 文档先行
任何**功能变更 / 模板改动 / 流程优化**, 必须**先更新** `PROCESS.md` 和 `SOLUTION.md`, **再**改代码.

### Rule 2: 自包含测试
任何新加的依赖 (库 / API / 工具), 必须:
- 在 `requirements.txt` 或 `docs/DEPENDENCIES.md` 列明
- 至少在 2 个不同 OS (Windows + macOS/Linux) 测试通过
- 不引入"必须联网才能工作" 的外部服务

### Rule 3: 可重放 (Reproducibility)
任何报告生成流程, **必须**:
- 从 `git clone` 仓库到生成报告 ≤ 2 小时
- 不依赖原作者口述
- 不依赖特定硬件/OS
- 任何步骤有"如果失败" 的 fallback 路径

### Rule 4: Git 提交规范
commit message 格式:
```
<type>(<scope>): <subject> [reproducibility-test]

<body>

<footer>
```

**types**: feat / fix / docs / refactor / test / chore
**scope**: v5.0-market-intel / template / scripts / docs
**reproducibility-test** tag: **必须** 出现在涉及"输出/流程" 的 commit (PROCESS.md, SOLUTION.md, templates, scripts, market-reports)

示例:
- ✅ `feat(v5.0-market-intel): add gout 2026 Q2 report [reproducibility-test]`
- ✅ `fix(scripts/render_report.py): handle missing chart data [reproducibility-test]`
- ❌ `feat(v5.0-market-intel): add report` (缺 [reproducibility-test])

### Rule 5: 测试设备记录
任何 commit 涉及 `templates/` 或 `scripts/` 必须在 CHANGELOG.md "测试设备" 段加:
- 测试设备 (e.g. "MacBook Pro M2 2023")
- OS + 版本
- Python 版本
- 浏览器 (Edge/Chrome)
- 测试日期

### Rule 6: 模板验证
任何 `templates/*.html` 改动必须:
- 通过 `scripts/validate_report.py` (待加) — 7 章节 + ≥6 图表 + ≥4 洞察 + ≥3 判断 + ≥1 风险 + ≥10 数据源
- 至少 1 份**新报告样本** 验证 (用 `templates/market-report-v1.html` 生成)
- 用户验收 "OK" 后, 才能 commit

### Rule 7: 数据源不增付费
CATALOG.md 数据源**只能增加免费/开源源**, 不能增加付费源 (决策 4 锁).

### Rule 8: 旧设备兼容
任何 Python 脚本必须支持 Python 3.9+ (不依赖 3.11+ 新特性), 跨 Windows/macOS/Linux.

---

## 3. 修订流程 (5 步)

```
[Step 1] 提出修订 (PR 或 issue)
   - 描述: 改什么 + 为什么 + 怎么测
   ↓
[Step 2] 更新文档 (PROCESS.md / SOLUTION.md)
   - 同步反映新设计
   - "修订记录" 表格加一行
   ↓
[Step 3] 改代码 (scripts/ templates/ integrations/)
   - 保持自包含
   - 写测试
   ↓
[Step 4] 跨设备测试 (至少 2 设备)
   - Windows + macOS/Linux
   - 跑完整 5 步流程
   - 验证输出与修订前一致 (或更好)
   ↓
[Step 5] commit + push
   - commit message 含 [reproducibility-test]
   - CHANGELOG 加 entry (含测试设备)
   - 通知 TG 用户 "修订 X 已通过可重放测试"
```

---

## 4. "可重放" 验收标准

| 维度 | 验收 |
|------|------|
| **时间** | 设备从 clone 仓库到生成第 1 份报告 ≤ 2 小时 |
| **依赖** | 不需要"问原作者" (文档齐全) |
| **跨 OS** | Windows / macOS / Linux 至少 2 个能跑 |
| **跨 Python** | 3.9+ 至少 2 个版本能跑 |
| **网络** | 除"源数据拉取" 外, 0 网络依赖 |
| **GUI** | 0 强 GUI 依赖 (Edge 截图可选) |
| **LLM** | 0 强依赖 (可本地模型替换 API) |
| **Git** | 0 特殊 git 操作 (clone + 标准 git 命令) |

---

## 5. 设备测试矩阵 (理想状态)

| 设备 | OS | Python | Edge | 状态 |
|------|-----|--------|------|------|
| WTG (本机) | Windows 11 | 3.11.4 | 126 | ✅ 已测 |
| MacBook M2 | macOS 14 | 3.11 | 119 | 待测 |
| Ubuntu 24.04 | Linux | 3.12 | Chrome | 待测 |

---

## 6. 修订记录 (按时间倒序)

| 日期 | 修订人 | 内容 | 测试设备 |
|------|--------|------|----------|
| 2026-06-30 | 巫师叔叔 (via54) | 首次发布 (8 条铁律 + 5 步流程) | WTG Windows 11 |
| | | | |
| | | | |
