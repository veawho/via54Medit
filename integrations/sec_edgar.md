# SEC EDGAR 集成计划

> **优先级**: P0 (商业核心, **TalkMED 7 页 PDF 反复引用**)  
> **API**: https://www.sec.gov/cgi-bin/browse-edgar  
> **鉴权**: User-Agent header (免费, 必填)  
> **GitHub SDK**: **dgunning/edgartools** ⭐2.4k (Python) — 官方级

## 1. 数据能力

| 数据 | 用途 |
|---|---|
| 10-K (年报) | 公司战略 + 收入 + 风险 |
| 10-Q (季报) | 季度业绩 |
| 8-K (重大事件) | 收购 / 管线变动 / 监管批准 |
| 13F (机构持仓) | 机构投资者动向 |
| S-1 / S-4 (募资/并购) | BD / 并购详情 |
| Form 4 (内部人交易) | 高管增持/减持 |

## 2. TalkMED 关键来源

TalkMED §3 §6 §7 大量引用:
- 诺华 / 安进 / 默沙东 / 赛诺菲 / 礼来 / 再生元 财报
- "2024年 10月 石药集团 × 阿斯利康 (YS2302018 口服 Lp(a) 小分子) 20.2亿美元" → Form 8-K + S-4
- "2025年 3月 恒瑞医药 × 默沙东 (HRS-5346) 19.7亿美元" → Form 8-K

## 3. 集成步骤

### Phase 5.0.2
- [ ] `internal/source/sec_edgar.go` — Go client (基于 SEC API 文档)
  - `SearchCompany(cik_or_ticker)` → `*Company`
  - `Filings(cik, form_types)` → `[]Filing`  (e.g. 10-K, 8-K, 4)
  - `FilingContent(filing_url)` → `string`
  - `FullTextSearch(query)` → `[]Filing`
- [ ] User-Agent 头必填: `"via54Medit admin@via54.com"`
- [ ] Rate limit: 10 req/sec (官方)

### 数据模型
```go
type Filing struct {
    CIK          string
    Ticker       string
    Form         string  // 10-K / 8-K / 4
    FiledDate    time.Time
    AccessionNo  string
    PrimaryDoc   string
    Description  string
}

type Company struct {
    CIK           string
    Ticker        string
    Name          string
    SIC           string
    SICDescription string
    State         string
}
```

## 4. 测试

- [ ] Amgen (CIK 318154) — 最近 8-K
- [ ] Novartis (CIK 1114448) — 10-K 2024
- [ ] 默沙东 (Merck, CIK 310158) — 8-K (含 HRS-5346 交易)

## 5. 风险

- ⚠️ 财报 PDF 解析复杂 (XBRL + 文本混合)
- ⚠️ 中国/欧洲公司不在 SEC 范围 (用 HKEXnews / SSE)
- ⚠️ 财报关键数字常在表格中, 需智能抽取 (LlmExtract)

## 6. 工作量

约 3 天 (含 PDF/XBRL 解析层)