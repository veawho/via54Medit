# DailyMed 集成计划

> **优先级**: P0 (EBM 药物)  
> **API**: https://dailymed.nlm.nih.gov/dailymed/services/v2/  
> **鉴权**: 无  
> **GitHub**: genomoncology/biomcp (集成)

## 1. 数据能力

| 数据 | 用途 |
|---|---|
| SPL (Structured Product Label) | FDA 批准药物官方标签全文 (15万+) |
| 适应症 | Indications & Usage section |
| 剂量 | Dosage & Administration |
| 警告 | Warnings / Precautions |
| 不良反应 | Adverse Reactions |
| 药物相互作用 | Drug Interactions |
| 特殊人群 | Pediatric / Geriatric / Pregnancy |

## 2. 跟 openFDA / EuropePMC 互补

- openFDA `/drug/label`: 同源数据 (FDA 标签)
- DailyMed: NIH 维护, **更新更频繁**, 部分含厂家直接提交的最新标签
- 推荐: 2 个并行查询, 以 openFDA 为基线, DailyMed 为增量

## 3. 集成步骤

### Phase 5.0.1
- [ ] `internal/source/dailymed.go`
  - `SearchByName(name)` → `[]SPL`
  - `FetchBySetId(set_id)` → `*SPL` (含全部 sections XML)
  - `FetchSection(set_id, section_name)` → `string` (e.g. "adverse_reactions")

## 4. 测试

- [ ] Repatha (evolocumab) SPL setid
- [ ] Leqvio (inclisiran) SPL setid

## 5. 工作量

约 1.5 天 (API 简单, 主要是 XML 解析)