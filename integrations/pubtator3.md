# PubTator 3.0 集成计划

> **优先级**: P0 (EBM NLP 增强)  
> **API**: https://www.ncbi.nlm.nih.gov/research/pubtator3/  
> **鉴权**: 无 (推荐 NCBI API key)  
> **GitHub**: ncbi-tagger/pubtator

## 1. 数据能力

| 数据 | 用途 |
|---|---|
| 自动实体标注 | 基因 / 疾病 / 化学 / 变异 / 物种 |
| 标注数 | 3600万+ 摘要 (PubMed 全量) |
| 输出格式 | BioC JSON / XML |

## 2. EBM 价值

- ✅ 自动抽取 PICO 中的 P (population) 和 I (intervention)
- ✅ 化学药物名识别 (跟 ChEMBL 自动关联)
- ✅ 疾病名识别 (跟 MeSH / Orphanet 关联)

## 3. 集成步骤

### Phase 5.0.1
- [ ] `internal/source/pubtator3.go`
  - `Annotate(pmids)` → `map[PMID][]Entity`
  - `AnnotateText(text)` → `[]Entity` (实时)
- [ ] 跟 PICO 抽取集成 (Layer 4A PICO 步骤)

## 4. 测试

- [ ] PMID 30543681 (DAPA-HF) → 标注 dapagliflozin / heart failure

## 5. 工作量

约 1 天