# medRxiv + bioRxiv 集成计划

> **优先级**: P0 (EBM 灰色文献)  
> **API**: https://api.biorxiv.org/  
> **鉴权**: 无  
> **GitHub MCP**: pipeworx-io/mcp-biorxiv (4 tools, MIT)

## 1. 数据能力

| 数据 | medRxiv | bioRxiv |
|---|---|---|
| 预印本数 | 40,000+ | 230,000+ |
| 学科 | 临床/医学 | 生物/基础 |
| 更新 | 每日 | 每日 |
| 全文 | PDF | PDF |

## 2. EBM 价值

- ✅ 最新临床研究 (未正式发表, 可能影响指南)
- ✅ 罕见病 / 新发传染病第一时间发布
- ✅ negative results (PubMed 较少)
- ⚠️ 未 peer review, GRADE 评级时需标注

## 3. 集成步骤

### Phase 5.0.1
- [ ] `internal/source/medrxiv.go` (合并 bioRxiv)
  - `Search(query, days_back)` → `[]Preprint`
  - `FetchByDOI(doi)` → `*PreprintDetail`
  - `Recent(category, days)` → `[]Preprint` (订阅式)
- [ ] 跟 PubMed 关联: 论文正式发表后, 链接 DOI

## 4. 测试

- [ ] 黄金 9: COVID-19 早期论文 (2020 Jan-Feb)
- [ ] Lp(a) PCSK9 最近 90 天预印本

## 5. 工作量

约 1.5 天 (API 简单)