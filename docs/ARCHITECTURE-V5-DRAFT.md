# via54Medit v5.0 — 双模式架构升级草案 (TalkMED PDF 触发)

> **触发**: 用户 2026-06-30 提交 TalkMED AgentPilot 7 页 PDF (123.pdf) 报告「降血脂药物市场前瞻性分析报告」, 要求融合 EBM 学术 + 商业医药情报 + TalkMED 类报告生成 3 个方向
> **状态**: DRAFT (待用户拍板)
> **版本**: v5.0-draft-2026-06-30
> **核心变更**: 从 5 层架构升到 **6 层 + 双模式路由** (EBM 学术 / 商业情报)

---

## 1. 一句话定位 (v5.0)

**`via54Medit` 是一个用自然语言驱动的双模式医药决策平台**:
- **EBM 学术模式**: 把临床问题路由到最合适的医学文献源 (4 现存 + 6 新 P0 = 10+ 源), 输出循证证据包 + GRADE + 引用 PPT
- **商业情报模式** (新): 把医药市场问题路由到商业数据源 (12+ 新源), 输出 TalkMED 风格 7 页市场报告 (全球/中国 CAGR + 管线矩阵 + 临床数据 + 投资关注点)

> **不是又造一个文献检索工具, 不是又造一个医药销售数据库, 是造「双模式医药决策调度器」**

---

## 2. 现有架构 vs v5.0 升级

### 2.1 v4.5 (现 5 层)
```
Layer 5: 入口 (CLI 13 + MCP 4)
   ↓
Layer 4: 语义路由 (PICO + 4 源并发)
   ↓
Layer 3: 源适配器 (antfu/PubMed/OpenAlex/S2)
   ↓
Layer 2: 数据加工 (enrich + dedupe + extract + anno2ppt)
   ↓
Layer 1: 基础 (embedder + vectorstore + llm + config + log)
```

### 2.2 v5.0 (6 层 + 双模式)
```
Layer 6: 输出渲染 (扩展, 双模式)
   ├── 6A: 学术报告 (GRADE + EBM 摘要 + 引用 PPT)
   └── 6B: 商业报告 (TalkMED 7 页市场报告 + 管线矩阵 + 投资 PPT)
   ↓
Layer 5: 入口层 (扩展)
   ├── CLI 13 (保留) + 新增 `medit intel` (商业情报子命令族)
   └── MCP 4 (保留) + 新增 3 商业 MCP tools (v5.0 = 7 tools)
   ↓
Layer 4: 双模式语义路由 (新增 4B 商业路由)
   ├── 4A: EBM 路由 (原 v4.5 升级)
   │    ├── 6 EBM 分类 (治疗/诊断/预后/病因/预防/经济) × 5 意图
   │    └── 10+ EBM 源并发调度
   └── 4B: 商业情报路由 (新)
        ├── 7 商业查询类型 (市场总览/管线/竞品/临床/专利/财报/投资)
        └── 12+ 商业源并发调度
   ↓
Layer 3: 源适配器 (扩展)
   ├── A. 学术源 (4 现存 + 6 P0 = 10)
   │    ├── antfu, pubmed, openalex, s2 (现有)
   │    ├── clinicaltrials_v2, europe_pmc, medrxiv_biorxiv (新 P0)
   │    └── openfda, dailymed, pubtator3 (新 P0)
   └── B. 商业源 (12 P0)
        ├── 销售: openfda, fda_orange_book, chembl, pubchem, cde, pdb
        └── 财报+试验: sec_edgar, clinicaltrials_v2 (双用), trialsitenews
   ↓
Layer 2: 数据加工 (扩展)
   ├── 2A: EBM pipeline (保留) — enrich + dedupe + extract + anno2ppt
   └── 2B: 商业 pipeline (新)
        ├── market_size_extractor (CAGR / 市场份额)
        ├── pipeline_matrix_builder (企业 × 阶段矩阵)
        ├── clinical_metrics_extractor (LDL-C 降幅 / CVOT)
        └── patent_landscape (专利地图)
   ↓
Layer 1: 基础层 (不变)
```

---

## 3. CLI 子命令 (v5.0 = 18 个, +5 新增)

### 现有 13 子命令 (保留)
```
ask / search / pico / systematic / grade
pubmed / openalex / s2 / antfu
enrich / index / query
anno2ppt
version
```

### 新增 5 商业情报子命令 (v5.0)
```bash
intel <query>           # 一句话商业情报 (默认 12 源 + 7 页 TalkMED 风格报告)
market <drug/therapy>   # 全球+中国市场总览 (CAGR, 销售, 厂商份额)
pipeline <drug/target> # 在研管线矩阵 (企业 × 阶段)
patent <drug>          # 专利地图 (Orange Book + Google Patents + SureChEMBL)
trial <drug/cond>      # 临床试验商业维度 (CT.gov + ASCO/AHA 摘要)
```

### MCP tools (v5.0 = 7 个, +3 新增)
```
# 现有 4
medit_ask / medit_pico / medit_grade / medit_anno2ppt

# 新增 3 (商业)
medit_intel            # 商业情报入口 (类似 medit_ask 但路由到商业源)
medit_market           # 市场总览
medit_pipeline         # 管线矩阵
```

---

## 4. 双模式路由器核心算法

### 4.1 EBM 路由 (保留 v4.5, 升级源数)
```
input: 自然语言临床问题
   ↓
[1] PICO 抽取 (现有 LLM)
   ↓
[2] EBM 6 类分类 × 5 意图 (现有)
   ↓
[3] 源调度 (10 源并发)
   ├── 必选: pubmed, openalex, s2 (基础)
   ├── 治疗 → 加 antfu, europe_pmc, dailymed
   ├── 诊断 → 加 clinicaltrials_v2, openfda, pubtator3
   ├── 预后 → 加 medrxiv_biorxiv, europe_pmc
   └── 经济 → 加 openfda, chembl, dailymed
   ↓
[4] 三方 enrich + 去重 + 加权排序 (现有)
   ↓
[5] LLM EBM 摘要 + GRADE 评级 + 引用 PPT
```

### 4.2 商业情报路由 (新)
```
input: 自然语言商业问题 (e.g. "PCSK9 注射剂市场")
   ↓
[1] 商业实体抽取 (新 LLM)
   - drug: [依洛尤单抗, 英克司兰]
   - target: [PCSK9]
   - indication: [高胆固醇血症]
   - region: [中国, 全球]
   - time_range: [2023-2030]
   ↓
[2] 7 类商业查询分类 (新)
   ├── 市场总览 (market_size)
   ├── 在研管线 (pipeline)
   ├── 竞品对比 (competitive)
   ├── 临床数据 (clinical_metrics)
   ├── 专利地图 (patent_landscape)
   ├── 财报分析 (financials)
   └── 投资关注 (investment)
   ↓
[3] 源调度 (12 源并发, 按查询类型)
   ├── 市场总览 → openalex + huaon + wiseguy + pdb + yaozh
   ├── 在研管线 → clinicaltrials_v2 + sec_edgar + pharmcube
   ├── 临床数据 → pubmed + europe_pmc + aha + acc + eas + medrxiv
   ├── 专利 → fda_orange_book + google_patents + surechembl + epo_ops
   └── 财报 → sec_edgar + hkexnews + sse_szse
   ↓
[4] 商业指标 enrich (新)
   ├── market_size_extractor: CAGR / 销售 / 市场份额
   ├── pipeline_matrix_builder: 企业 × 阶段 二维矩阵
   ├── clinical_metrics_extractor: LDL-C 降幅 / CVOT 结果
   └── patent_landscape: 核心专利 + 独占期
   ↓
[5] 7 页 TalkMED 风格 PDF 生成 (新)
   ├── §1 全球+中国市场总览
   ├── §2 注射剂/单抗/siRNA 详细市场
   ├── §3 在研管线矩阵
   ├── §4 临床数据矩阵
   └── §5 市场前瞻 + 投资关注点
```

---

## 5. 数据模型 (v5.0 扩展)

### 5.1 新增 BusinessQuestion (商业入口参数)
```go
type BusinessQuestion struct {
    Query       string
    Drug        []string          // 多个药物名 / INN / 商品名
    Target      []string          // 靶点 (PCSK9, Lp(a) 等)
    Indication  []string          // 适应症
    Region      []string          // [global, china, us, eu]
    TimeRange   *TimeRange
    QueryType   QueryType         // 7 类商业查询
    Sources     []string          // 默认 12 商业源
    MaxResults  int
}

type QueryType string
const (
    QtMarketSize      QueryType = "market_size"
    QtPipeline        QueryType = "pipeline"
    QtCompetitive     QueryType = "competitive"
    QtClinicalMetrics QueryType = "clinical_metrics"
    QtPatentLandscape QueryType = "patent_landscape"
    QtFinancials      QueryType = "financials"
    QtInvestment      QueryType = "investment"
)
```

### 5.2 新增 MarketInsight (商业输出)
```go
type MarketInsight struct {
    Question     BusinessQuestion
    
    // §1 市场总览
    GlobalSize   MarketSize         // 2023 / 2024 / 2032 预测 / CAGR
    ChinaSize    MarketSize
    TopPlayers   []Player           // 市场份额排序
    
    // §2 细分市场 (按药物类型 / 给药方式)
    Segments     []Segment          // {name, size_b, growth_rate, key_drugs}
    
    // §3 在研管线矩阵
    Pipeline     []PipelineEntry    // {drug, company, phase, indication, cvot_readout}
    
    // §4 临床数据
    ClinicalData []ClinicalResult   // {drug, trial, ldl_c_reduction, cvot_outcome}
    
    // §5 投资关注
    Investment   []InvestmentPoint  // {timeframe, key_event, market_impact}
    
    SourcesUsed  map[string]int
    PDFPath      string             // 7 页 TalkMED 风格 PDF
}
```

---

## 6. TalkMED 7 页 PDF 生成 (新模块)

参照 123.pdf 的结构,生成 7 页 PDF:

| 页 | 内容 | 数据源 |
|---|---|---|
| 1 | §1 全球+中国市场总览 (CAGR, 销售) | openalex + huaon + wiseguy + pdb |
| 2 | §2 注射剂/单抗/siRNA 详细市场 | openfda + chembl + clinicaltrials_v2 |
| 3 | §2 续 + 在研管线 | sec_edgar + clinicaltrials_v2 + aha/acc 摘要 |
| 4 | §3 在研管线矩阵 (企业 × 阶段) | clinicaltrials_v2 + sec_edgar |
| 5 | §3 续 + §4 临床数据 | pubmed + europe_pmc + medrxiv |
| 6 | §4 续 + 交易历史 | sec_edgar + biomcp 交易 + pharmcube |
| 7 | §5 市场前瞻 + 投资关注点 | sec_edgar + endpoints + biocentury |

### 实现选择
- **PDF 渲染**: 用 via54Design 的 `export pptx` 类似模式, hand-roll Go `gofpdf` 或 Rust `printpdf`
- **图表**: 用 Go `gonum/plot` 生成 (柱状/饼图/趋势线), PNG → 嵌入 PDF

---

## 7. ROADMAP 升级 (v4.5 → v6.0)

### Phase 4.5 (现 v4.5.0) ✅
- 6 个 GitHub 集成 (local-deep-research / paper-search-mcp / MetaScreener / asreview / pubmed_parser / pyalex)

### Phase 5.0 (本月) — 双模式 + 12 P0 源
- [ ] **5.0.1**: 新增 6 P0 学术源 (clinicaltrials_v2 / europe_pmc / medrxiv / openfda / dailymed / pubtator3)
- [ ] **5.0.2**: 新增 6 P0 商业源 (openfda / fda_orange_book / sec_edgar / chembl / pubchem / cde)
- [ ] **5.0.3**: 新增商业情报 CLI (intel / market / pipeline / patent / trial)
- [ ] **5.0.4**: 新增 3 商业 MCP tools
- [ ] **5.0.5**: 双模式路由器 (Layer 4B)
- [ ] **5.0.6**: TalkMED 7 页 PDF 生成器 (v1)

### Phase 5.5 (下月) — + 15 P1 源
- [ ] P1 EBM: chembl / opentargets / biothings / pubchem / orphanet / pharmgkb / lactmed_livertox
- [ ] P1 商业: google_patents / epo_ops / aha / acc / asco / hkexnews

### Phase 6.0 (3 月后) — TalkMED AgentPilot 类完整 AI Agent
- [ ] 商业情报 AI Agent (类似 PharmaPilot 但自研)
- [ ] LLM 驱动的市场预测 + 情景分析
- [ ] 自动监测新发表/新批准/新交易 (cron job)
- [ ] 多轮对话 refinement

### Phase 6.5 (持续) — 付费源
- [ ] 药智数据 / 医药魔方 / Citeline (按预算)

---

## 8. 兼容性 / 风险 / 决策

### 兼容性
- ✅ v4.5 CLI 13 + MCP 4 全部保留, 不破坏
- ✅ 双模式路由器共享 Layer 1-2 基础 (embedder / vectorstore / llm)
- ✅ `medit ask` 用户无感升级 (内部走 10 源 vs 4 源)
- ✅ `medit intel` 是全新子命令族

### 风险
- ⚠️ 12 P0 源中 6 个需要 API key (FDA / SEC / ChEMBL 等), 默认无 key 也可跑但有 rate limit
- ⚠️ TalkMED PDF 生成器需要新依赖 (PDF 渲染 + 图表)
- ⚠️ 商业数据中文质量参差 (CDE / PDB / 药智 vs OpenAlex / SEC)
- ⚠️ TalkMED PDF 7 页是单一示例,实际报告 6-20 页都有可能,需要模板化

### 待用户拍板
1. ✅ 架构方向 (已确认: 双模式融合 3 方向)
2. ❓ P0 源列表是否需要调整 (12 个符合 TalkMED PDF 7 页需求?)
3. ❓ 是否需要新增 layer 5B (商业 CLI),还是作为现有 CLI 子命令 (我倾向前者, 隔离干净)
4. ❓ TalkMED 7 页 PDF 是 v5.0 必交付, 还是 v6.0?
5. ❓ 商业付费源 (药智/医药魔方/Citeline) 预算?
6. ❓ 是否真要 fork genomoncology/biomcp (MIT) 进 via54Medit,还是 MCP 协议调用?

---

**待补决策展开**: 详见 [DECISIONS-PENDING.md](DECISIONS-PENDING.md) (10 大白话问题 + 默认值, 用户 6/30 15:50 TG 决策触发)
