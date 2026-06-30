# ClinicalTrials.gov v2 集成计划

> **优先级**: P0 (EBM + 商业双用)  
> **API**: https://clinicaltrials.gov/api/v2/  
> **鉴权**: 无 (推荐带 email header)  
> **GitHub MCP**: genomoncology/biomcp (主) / cyanheads/clinicaltrialsgov-mcp-server (备)

## 1. 数据能力

| 维度 | 范围 |
|---|---|
| 试验数 | 500,000+ |
| 更新 | 每日 |
| Rate limit | 推荐 1 req/sec |
| 字段 | NCT ID / 标题 / 状态 / 申办方 / 适应症 / 期 / 入组数 / 终点 / 结果 / 地理 |
| Schema | https://clinicaltrials.gov/api/v2/studies?format=json |

## 2. 跟现有 4 源互补

| 现有源 | 互补维度 |
|---|---|
| PubMed | 文献 vs 试验 (CT.gov 是试验注册) |
| OpenAlex | 论文 vs 试验 |
| S2 | 引用 vs 试验 |
| antfu | 中文 RAG vs 英文试验 |

## 3. 集成步骤

### Phase 5.0.1
- [ ] `internal/source/clinicaltrials.go` — 包装 v2 API
  - `Search(query)` → `[]Trial`
  - `FetchByNCT(nct_id)` → `*TrialDetail`
  - `SearchByCompany(sponsor)` → `[]Trial` (商业模式关键)
  - `SearchByDrug(intervention)` → `[]Trial`
- [ ] Rate limiter: 1 req/sec token bucket
- [ ] schema 适配: `Trial` → `Citation` (EBM) + `PipelineEntry` (商业)

### 数据模型映射
```go
type Trial struct {
    NCTId        string
    Title        string
    Status       string // "RECRUITING" / "COMPLETED" / etc.
    Phase        []string
    Sponsor      string
    Conditions   []string
    Interventions []Intervention
    Enrollment   int
    StartDate    time.Time
    EndDate      time.Time
    Results      *Results // 临床结果 (如已发布)
}
```

## 4. 测试

- [ ] `tests/unit/clinicaltrials_test.go` — mock 5 个 NCT IDs
- [ ] 黄金 9 案例: DAPA-HF (NCT03036124) / FOURIER (NCT01764633) / ODYSSEY (NCT01663402)
- [ ] 商业测试: 查"PCSK9"申办方 (Amgen / Regeneron / Novartis)

## 5. 文档

- [ ] `docs/SOURCE-CONNECTORS.md` 加 CT.gov v2 详解
- [ ] 更新 `README.md` 致谢 genomoncology/biomcp

## 6. 风险

- ⚠️ v2 API schema 比 v1 大很多,需要分页 (pageSizeToken)
- ⚠️ 商业模式需要从 CT.gov 提取"申办方 + 适应症 + 期",这是 PDF §3 矩阵的关键
- ⚠️ 中文 query 需要先翻译 (CT.gov 主英)

## 7. 工作量

约 3-4 天 (1 个 Go 开发者熟悉 API)