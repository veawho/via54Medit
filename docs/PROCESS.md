# 商业市场报告生成流程 (PROCESS)

> **目的**: 任何设备 + 任何 agent 部署 via54Medit 后, 按此流程能生成与 2026-06-30 痛风报告同等质量的 7-章节商业市场报告.
> **生成日期**: 2026-06-30
> **样本报告**: `market-reports/gout-2026-q2.html` (66KB, 7 章节, 8 SVG 图表)
> **关键原则**: 本流程设计为**可重放** — 任何部署, 任何 agent, 任何时间, 同样输入 → 同样输出.

---

## 0. 前置条件 (任何设备)

### 0.1 工具
- Python 3.11+ (fitz/PyMuPDF, 用于 PDF 渲染)
- Edge 或 Chrome (HTML 截图)
- git, curl, gh CLI

### 0.2 仓库
```bash
git clone https://github.com/veawho/via54Medit.git
cd via54Medit
```

### 0.3 数据源依赖
- `integrations/CATALOG.md` (115+ 源, 2023-2026 优先)
- `docs/ARCHITECTURE-V5.md` (v5.0 双模式架构)
- `configs/default.yaml` (数据源配置)
- `templates/market-report-v1.html` (报告 HTML 模板, 7 章节结构)

---

## 1. 流程总览 (5 步)

```
[输入: 主题 + 数据范围 + 优先年份]
  ↓
[步骤 1] 源收集 (10-30 min)
  ↓
[步骤 2] 数据合成 (30-60 min)
  ↓
[步骤 3] HTML 模板填充 (10-20 min)
  ↓
[步骤 4] 图表生成 (SVG 内嵌) (20-30 min)
  ↓
[步骤 5] 验证 + commit + push (10 min)
  ↓
[输出: market-reports/<topic>-<year>-<quarter>.html]
```

---

## 2. 详细流程

### 步骤 1: 源收集 (Step 1 — Source Collection)

**输入**: `<TOPIC>` (e.g. `gout`, `hypertension`, `copd`), `<YEAR_RANGE>` (e.g. `2023-2026`), `<PRIORITY_YEAR>` (e.g. `2026`)

**操作**:
```bash
# 1.1 查 integrations/CATALOG.md 找相关源
# 1.2 用 firecrawl/exa/arxiv 拉新源 (2024-2026)
# 1.3 列 11 核心源 + 候选 5-10 个
# 1.4 每个源附: 数据范围, URL, 截止日期
```

**输出**: 源清单 (11-21 个) — 表格格式

**时间**: 10-30 min

**可重放性**: ✅ 100% — 只用公开 API + 固定源清单

### 步骤 2: 数据合成 (Step 2 — Data Synthesis)

**输入**: 步骤 1 源清单

**操作**:
```bash
# 2.1 按 <TOPIC> 分类 (市场规模 / 已上市药 / 在研 / 中国)
# 2.2 按 <YEAR_RANGE> 填 2023 实际 / 2024 实际 / 2025 估 / 2026 估
# 2.3 <PRIORITY_YEAR> 数据优先 (有 2026 真数据 vs 估数据, 用真的)
# 2.4 算 YoY / CAGR (2023→2026)
# 2.5 加 4 关键洞察 (💡): 增速解读 + 区域分布 + 风险
```

**输出**: 完整数据表 (4-6 个表格, 30-60 数据点)

**时间**: 30-60 min

**可重放性**: ✅ 100% — 数据有源标注, 可交叉验证

### 步骤 3: HTML 模板填充 (Step 3 — Template Fill)

**输入**: 步骤 2 数据

**操作**:
```bash
# 3.1 复制 templates/market-report-v1.html
# 3.2 替换 6 个占位符:
#     {{TITLE}} - 报告标题
#     {{TOPIC}} - 主题
#     {{YEAR_RANGE}} - 数据范围
#     {{PRIORITY_YEAR}} - 优先年份
#     {{METRICS_BLOCK}} - 4 个关键指标
#     {{TABLES_BLOCK}} - 数据表
#     {{INSIGHTS_BLOCK}} - 数据洞察
#     {{SOURCES_BLOCK}} - 数据源
# 3.3 加自定义 CSS (蓝色 gradient header, metric grid, callouts)
# 3.4 写 7 章节内容
```

**输出**: HTML 文件 (50-80KB)

**时间**: 10-20 min

**可重放性**: ✅ 100% — 模板固定, 替换规则明确

### 步骤 4: 图表生成 (Step 4 — SVG Charts)

**输入**: 步骤 2 数据 + 步骤 3 HTML

**操作**:
```bash
# 4.1 折线图 (Line) - 趋势数据 (如市场规模 2023-2030)
# 4.2 饼图/环图 (Pie/Donut) - 份额数据 (如区域 / 药物)
# 4.3 柱状图 (Bar) - 对比数据 (如各国销售)
# 4.4 气泡图 (Bubble) - 投资主题 (x=风险, y=回报, size=市场)
# 4.5 甘特图 (Gantt) - 在研管线
# 4.6 时间线 (Timeline) - 关键事件
# 4.7 SVG 内嵌到 HTML (无需外部库)
```

**输出**: 6-8 个 SVG 图表

**时间**: 20-30 min (1 个图表 3-5 min)

**可重放性**: ✅ 100% — SVG 是文本格式, 可嵌入 HTML

### 步骤 5: 验证 + 提交 (Step 5 — Validate + Commit)

**输入**: 完整 HTML

**操作**:
```bash
# 5.1 用 Edge headless 截图
edge --headless --screenshot=preview.png --window-size=1100,2200 <html>

# 5.2 用户审阅
# 5.3 反馈: OK / 需修改

# 5.4 反馈 OK 后, 提交:
cp <html> market-reports/<topic>-<year>-<quarter>.html
git add market-reports/ docs/MARKET-REPORTS.md CHANGELOG.md
git commit -m "feat(v5.0-market-intel): add <topic> <year> <quarter> report"
git push origin main

# 5.5 CHANGELOG +4.5.X 标"v5.0 商业情报第 N 份样本"
```

**输出**: GitHub 上线, TG 通知

**时间**: 10 min

**可重放性**: ✅ 100% — git push + TG send 是原子操作

---

## 3. 总时间: 80-150 min / 报告

| 步骤 | 时间 | 可重放 |
|------|------|--------|
| 1. 源收集 | 10-30 min | ✅ |
| 2. 数据合成 | 30-60 min | ✅ |
| 3. HTML 模板 | 10-20 min | ✅ |
| 4. 图表生成 | 20-30 min | ✅ |
| 5. 验证+提交 | 10 min | ✅ |
| **合计** | **80-150 min** | **100%** |

---

## 4. 质量门禁 (任何报告必须通过)

- [ ] 7 章节齐全 (总览 / 已上市 / 急性 / 中国 / 在研 / 投资 / 来源)
- [ ] ≥6 SVG 图表 (折线/饼/柱/气泡/甘特/时间线)
- [ ] ≥4 数据洞察 (💡 紫色) — 不是描述, 是判断
- [ ] ≥3 投资判断 (✅ 绿色) — 明确结论
- [ ] ≥1 风险提示 (⚠️ 红色) — 3 大风险
- [ ] 1 个整体结论 + 3 档配置建议 (保守/平衡/激进)
- [ ] ≥10 数据源标注 (来源 + 截止日期)
- [ ] 数据范围 2023-2026, **2026 优先**
- [ ] 用户测试 OK (浏览器打开 + 审阅)
- [ ] 复制到 `market-reports/`, git commit + push

---

## 5. 已知问题与处理

| 问题 | 处理 |
|------|------|
| 用户说"看不懂" | 重写为通俗版, 每题 5 选项 + 推荐 + 默认 |
| 2026 数据不足 | 用 2024 实际 + 2025 估 + 2026 估, 标 (估) 区别 |
| 数据冲突 | 用公司财务年报 (Takeda/Amgen) 优先, 第三方报告交叉验证 |
| 设备差异 | 模板 + 步骤固定, 不依赖具体 OS / Python 版本 |
| 模型幻觉 | 每数据点附源 URL, 不可验证的不写 |

---

## 6. 后续可优化 (v5.5+)

- **PDF 导出**: 当前只 HTML, v5.5 加 PDF (用 weasyprint)
- **交互图表**: 当前静态 SVG, v5.5 加 plotly.js 交互
- **自动化流水线**: v6.0 集成 Claude / Hermes agent, 自动跑 5 步
- **多语言**: 当前中文, v5.5 加 EN (双语报告)
- **模板库**: v6.0 加 5+ 行业模板 (肿瘤 / 心血管 / 罕见病 / 儿科 / 中药)

---

## 7. 规则: 任何修订必须可重放

> **铁律 (2026-06-30 制定)**:
> 任何对此流程的修订, 必须:
> 1. 在另一台设备上**测试通过** (从 clone 仓库到生成报告, 全流程 ≤ 2 小时)
> 2. 在 PROCESS.md 顶部 "修订记录" 表加一行 (日期 + 修订人 + 内容 + 测试设备)
> 3. 在 CHANGELOG.md 加 entry
> 4. **commit message 必须含 "reproducibility-test"**
> 5. **不能"只在本地 work"** — 必须可重放

详见 `docs/REPRODUCIBILITY.md`.

---

## 8. 修订记录 (按时间倒序)

| 日期 | 修订人 | 内容 | 测试设备 |
|------|--------|------|----------|
| 2026-06-30 | 巫师叔叔 (via54) | 首次发布, 痛风报告样本 | WTG Windows 11 |
| | | | |
| | | | |
