# 商业报告生成解决方案 (SOLUTION)

> **目的**: 任何设备部署 via54Medit 后, 自动按此架构生成高质量商业市场报告.
> **生成日期**: 2026-06-30
> **架构版本**: v5.0 (双模式: ask 学术 + intel 商业)
> **关键原则**: **架构 + 工具 + 数据 + 模板 = 自包含**, 无外部依赖即可生成.

---

## 1. 解决方案总览

### 1.1 一句话定位
**via54Medit v5.0 intel 模式 = 本地化商业市场报告生成器**, 输入主题 → 输出 7 章节 HTML 报告.

### 1.2 5 层架构 (从输入到输出)

```
┌──────────────────────────────────────────────────────────┐
│ Layer 5: 输出层 (Output)                                  │
│ → market-reports/<topic>-<year>-<quarter>.html (66KB)    │
│ → 7 章节 + 8 SVG 图表 + 4 洞察 + 3 判断 + 3 风险         │
└──────────────────────────────────────────────────────────┘
                            ↑
┌──────────────────────────────────────────────────────────┐
│ Layer 4: 模板层 (Template) — templates/market-report-v1.html│
│ → 6 占位符: TITLE / METRICS / TABLES / INSIGHTS / ...    │
│ → 7 章节结构, 4 象限 insight/verdict/risk/callout        │
└──────────────────────────────────────────────────────────┘
                            ↑
┌──────────────────────────────────────────────────────────┐
│ Layer 3: 图表层 (Charts) — SVG 内嵌                         │
│ → 折线 / 饼 / 柱 / 气泡 / 甘特 / 时间线                    │
│ → 无外部库 (matplotlib/plotly), 纯 SVG 文本               │
└──────────────────────────────────────────────────────────┘
                            ↑
┌──────────────────────────────────────────────────────────┐
│ Layer 2: 数据层 (Data) — integrations/CATALOG.md + 公开源   │
│ → 115+ 数据源, 2023-2026 优先                              │
│ → 11 核心源: Coherent / FMI / Data Bridge / GVR / Takeda  │
│              / Amgen / CPA / CRA / Evaluate / CT.gov / FDA   │
└──────────────────────────────────────────────────────────┘
                            ↑
┌──────────────────────────────────────────────────────────┐
│ Layer 1: 输入层 (Input) — 用户指定                          │
│ → 主题 (gout) + 数据范围 (2023-2026) + 优先年份 (2026)    │
│ → 输出路径 (market-reports/gout-2026-q2.html)             │
└──────────────────────────────────────────────────────────┘
```

---

## 2. 核心组件 (8 个)

### 2.1 数据源注册表 (Source Registry)
- **位置**: `integrations/CATALOG.md`
- **内容**: 115+ 数据源 (EBM 55+ + 商业 60+), 分类 + 集成状态
- **格式**: Markdown 表格 (源 ID / 类型 / 难度 / 备注)
- **2026 更新**: 减 16 付费源 (Frost/Grand View/Citeline 等), 锁 0 付费

### 2.2 报告模板 (Template)
- **位置**: `templates/market-report-v1.html` (待创建)
- **结构**: 7 章节 HTML 骨架 + CSS 样式 (蓝/绿/红/紫/黄 4 象限)
- **占位符**:
  - `{{TITLE}}` - 报告标题
  - `{{METRICS_BLOCK}}` - 4 个关键指标 (大数字)
  - `{{TABLES_BLOCK}}` - 数据表
  - `{{CHARTS_BLOCK}}` - SVG 图表 (6-8 个)
  - `{{INSIGHTS_BLOCK}}` - 紫色洞察
  - `{{VERDICTS_BLOCK}}` - 绿色判断
  - `{{RISKS_BLOCK}}` - 红色风险
  - `{{SOURCES_BLOCK}}` - 11+ 数据源

### 2.3 图表生成器 (Chart Generator)
- **位置**: `scripts/gen_chart.py` (待创建, Python 3.11+)
- **类型**: 6-8 个 SVG 内嵌图表
  - `line_chart(metrics, years)` - 折线 (趋势)
  - `donut_chart(segments)` - 环形 (份额)
  - `bar_chart(items)` - 柱状 (对比)
  - `bubble_chart(items)` - 气泡 (x=风险, y=回报, size=市场)
  - `gantt_chart(items)` - 甘特 (管线)
  - `timeline_chart(events)` - 时间线
- **输出**: SVG 字符串, 可直接嵌入 HTML

### 2.4 数据合成器 (Data Synthesizer)
- **位置**: `scripts/synthesize_data.py` (待创建)
- **输入**: 源清单 (Layer 2)
- **操作**:
  1. 分类 (市场规模 / 已上市 / 在研 / 中国)
  2. 按年填 (2023 实际 / 2024 实际 / 2025 估 / 2026 估)
  3. 优先年份数据优先生效
  4. 算 YoY / CAGR
  5. 加源标注
- **输出**: 结构化 JSON (4-6 表格, 30-60 数据点)

### 2.5 洞察生成器 (Insight Generator)
- **位置**: `scripts/gen_insights.py` (待创建)
- **输入**: 数据表
- **规则**:
  - 增速解读 (vs 同类赛道对比)
  - 区域分布含义
  - 关键风险/机会
  - 投资建议
- **输出**: 4-5 个 insight-box (💡 紫色)

### 2.6 判断生成器 (Verdict Generator)
- **位置**: `scripts/gen_verdicts.py` (待创建)
- **输入**: 洞察 + 数据
- **规则**:
  - 明确结论 ("X 优于 Y, 因为 Z")
  - 风险偏好分层 (保守/平衡/激进)
  - 3 档配置建议
- **输出**: 3-4 个 verdict-box (✅ 绿色)

### 2.7 质量门禁 (Quality Gate)
- **位置**: `scripts/validate_report.py` (待创建)
- **检查**:
  - 7 章节齐全
  - ≥6 SVG 图表
  - ≥4 洞察 / ≥3 判断 / ≥1 风险
  - ≥10 数据源
  - 数据范围 2023-2026
  - 2026 优先标注
- **输出**: Pass/Fail + 改进建议

### 2.8 Git 自动化 (Git Automation)
- **位置**: `scripts/commit_report.sh` (待创建)
- **操作**:
  1. 复制报告到 `market-reports/`
  2. 更新 `docs/MARKET-REPORTS.md`
  3. 更新 `CHANGELOG.md`
  4. `git add + commit + push`
  5. TG 通知 (`hermes send --to telegram:USER_ID`)
- **commit message 模板**: `feat(v5.0-market-intel): add <topic> <year> <quarter> report`

---

## 3. 完整数据流 (数据 → 报告)

```
1. 用户输入: "Gout, 2023-2026, 2026 优先"
   ↓
2. scripts/synthesize_data.py
   → 读 integrations/CATALOG.md 找 gout 相关源
   → 拉 11 核心源 + 5 候选源
   → 合成 30+ 数据点 (按年 + 分类)
   → 输出: data/gout-2026-q2.json
   ↓
3. scripts/gen_charts.py
   → 读 JSON, 生成 8 个 SVG
   → 输出: charts/gout-2026-q2/*.svg
   ↓
4. scripts/gen_insights.py + gen_verdicts.py
   → 读 JSON + 业务规则, 生成 4 洞察 + 3 判断 + 1 风险
   → 输出: insights/gout-2026-q2.json
   ↓
5. scripts/render_report.py
   → 读 templates/market-report-v1.html
   → 替换 {{}} 占位符 (TITLE, METRICS, TABLES, CHARTS, ...)
   → 输出: market-reports/gout-2026-q2.html (66KB)
   ↓
6. 用户审阅 (Edge 打开)
   → 反馈 OK / 需修改
   ↓
7. scripts/commit_report.sh
   → git add + commit + push + TG notify
   → 输出: GitHub updated, TG notified
```

---

## 4. 可重放性设计 (跨设备可工作)

### 4.1 自包含
- ✅ 模板内置 (`templates/market-report-v1.html`)
- ✅ 数据源内置 (`integrations/CATALOG.md`)
- ✅ 脚本内置 (`scripts/`)
- ✅ 样式内置 (CSS 嵌入 HTML)
- ✅ 图表 SVG 内嵌 (无外部库)

### 4.2 无外部依赖
- ❌ 不依赖 `pip install` (脚本可纯 stdlib 实现)
- ❌ 不依赖网络 (除源数据)
- ❌ 不依赖云服务 (除 LLM, 可本地模型)
- ❌ 不依赖 GUI (HTML 文本 + Edge 截图)

### 4.3 平台无关
- ✅ Windows (本机测试 OK)
- ✅ macOS (用 Python + Edge 即可)
- ✅ Linux (同上)
- ✅ WSL (同 Linux)

### 4.4 工具链最小化
- Python 3.11+ (可选, 大部分可用 stdlib)
- Edge/Chrome (截图)
- Git
- 可选: LLMs (本地或 API)

---

## 5. 关键技术决策 (为什么这样设计)

### 5.1 为什么 HTML 而不是 PDF?
- ✅ 图表 SVG 内嵌, 可交互
- ✅ 文件小 (66KB vs PDF 1MB+)
- ✅ Git diff 友好 (可看 HTML 文本变化)
- ✅ 浏览器直接打开, 无需 PDF reader
- ⚠️ 缺点: 打印不如 PDF
- **未来**: v5.5 加 PDF 导出 (weasyprint)

### 5.2 为什么 SVG 而不是 PNG/Plotly?
- ✅ 无外部 JS 库 (无需 plotly.js)
- ✅ 文本格式, Git 友好
- ✅ 高 DPI, 矢量缩放
- ✅ 颜色精确 (代码控制)
- ✅ 体积小 (1-2KB / 图)

### 5.3 为什么 11 数据源不是 100?
- ✅ 核心源 = 数据可信 + 公开可访问
- ✅ 11 源 足够交叉验证
- ✅ 加源增加维护成本
- ✅ 数据源以"权威机构"为标准 (Coherent/FMI/Data Bridge 是市场研究 Top 3)
- **未来**: v6.0 加自动源发现 (LLM 爬虫)

### 5.4 为什么 7 章节不是 10?
- ✅ 7 章节 = TalkMED AgentPilot 标准
- ✅ 覆盖 学术/急性/中国/在研/投资/数据 全维度
- ✅ 不冗余
- ✅ 心理负担小 (用户读完 7 章节 < 30 min)

### 5.5 为什么 4 洞察 3 判断不是 10 10?
- ✅ 4 + 3 = 7 = 一致 (1 章节 1 洞察, 1 章节 1 判断)
- ✅ 质量 > 数量
- ✅ 洞察是"非显然结论", 多则水
- ✅ 判断是"明确行动", 多则模糊

---

## 6. 性能 & 扩展

### 6.1 单报告性能
- 数据合成: 30-60 min (LLM 主导)
- HTML 渲染: 10-20 min
- 图表生成: 20-30 min
- **总: 80-150 min / 报告**

### 6.2 批量能力
- 1 份/2 小时 (单 agent)
- 5 份/天 (多 agent 并行)
- 20 份/周 (自动化流水线, v6.0+)

### 6.3 成本
- 1 份 报告: $2-5 (LLM API) 或 $0 (本地模型)
- 0 边际成本 (模板 + 脚本复用)

---

## 7. 与 v4.5 (ask 学术) 关系

| 维度 | ask (学术) | intel (商业) |
|------|------------|--------------|
| 输出 | 文献包 + GRADE 评级 | 7 章节商业报告 |
| 用户 | 临床医生 / 研究者 | 药企 BD / 投资分析师 |
| 数据源 | 学术 (PubMed/S2/OpenAlex) | 商业 (Coherent/FMI) |
| 时间 | 10-30 秒/查询 | 80-150 min/报告 |
| 频率 | 高频 (日均 100+ 查询) | 低频 (周均 1-5 报告) |
| 决策 | 直接查询即结果 | 需多源交叉验证 |

**共享**: Layer 1-3 基础 (embedder / vectorstore / llm)

---

## 8. v5.5 / v6.0 路线图

| 版本 | 内容 | 状态 |
|------|------|------|
| v5.0 (现) | 手动流程 + 模板 (痛风样本) | ✅ |
| v5.5 | Python 脚本 5 个 (gen_data/gen_charts/...) | 计划 |
| v6.0 | Agent 集成 (LLM 跑流程) | 计划 |
| v6.5 | 20 行业模板 + 自动化 | 长期 |

---

## 9. 测试设备记录

| 日期 | 测试设备 | 操作系统 | 报告 | 状态 |
|------|----------|----------|------|------|
| 2026-06-30 | WTG | Windows 11 | gout-2026-q2 | ✅ OK (用户验收) |
| | | | | |
| | | | | |

---

## 10. 修订规则 (铁律)

> **任何对此 SOLUTION 的修订必须**:
> 1. **在 PROCESS.md 的 7 步骤框架内** (新步骤需加, 不删)
> 2. **保持自包含** (不引入外部云服务/库)
> 3. **跨设备测试** (至少 1 个非开发机)
> 4. **更新文档** (本文件 + PROCESS.md + REPRODUCIBILITY.md)
> 5. **commit message 含** `solution-refactor` + 简短理由
> 6. **CHANGELOG entry** (标注前后行为差异)

详见 `docs/REPRODUCIBILITY.md`.
