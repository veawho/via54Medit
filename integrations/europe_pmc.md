# Europe PMC 集成计划

> **优先级**: P0 (EBM)  
> **API**: https://www.ebi.ac.uk/europepmc/webservices/rest/  
> **鉴权**: 无 (REST, JSON/XML)  
> **覆盖**: 4000万+ 摘要, 部分全文 + 专利引用

## 1. 数据能力

| 数据 | 备注 |
|---|---|
| 摘要 | 跟 PubMed 大幅重叠 (~88%) |
| 全文 (Open Access) | 区别于 PubMed,Europe PMC 含更多 OA 全文 |
| 预印本 | bioRxiv / medRxiv 索引 |
| 专利 | EPO / WIPO patent citations (PubMed 没有) |
| Author manuscripts | 作者手稿 |
| AGRICOLA | 农业索引 (EBM 边缘相关) |
| Bookshelf | NCBI Bookshelf 内容 (GeneReviews 等) |

## 2. 跟 PubMed 互补

- ✅ 专利引用 (TalkMED §4 临床数据可补充)
- ✅ 预印本正式索引
- ✅ 全文获取概率更高
- ⚠️ 跟 PubMed 重复率 88%, 去重要做

## 3. 集成步骤

### Phase 5.0.1
- [ ] `internal/source/europe_pmc.go`
  - `Search(query)` → `[]Citation`
  - `FetchByPMCID(pmcid)` → `*FullText` (含 PDF URL)
  - `PatentCitations(pmid)` → `[]Patent` (EBM+商业双用)
- [ ] 跟 PubMed 去重: 同 PMID 合并, 专利引用单独索引

## 4. 测试

- [ ] 黄金 9: 已知 PMID 在 Europe PMC 也能搜到
- [ ] 验证 1 个 patent citation (如 Lp(a) PCSK9 相关)

## 5. 工作量

约 2 天 (API 极简单)