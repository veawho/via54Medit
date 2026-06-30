# ChEMBL + PubChem 集成计划

> **优先级**: P0 (EBM + 商业双用)  
> **API**:
> - ChEMBL: https://www.ebi.ac.uk/chembl/api/data/
> - PubChem: https://pubchem.ncbi.nlm.nih.gov/rest/pug/  
> **鉴权**: 均无  
> **GitHub**: chembl/chembl_webresource_client (官方 ⭐200), cyanheads/pubchem-mcp-server

## 1. 数据能力

### ChEMBL (24万+ 化合物, 2000万+ 活性数据)
| 数据 | 用途 |
|---|---|
| 化合物结构 (SMILES / InChI) | 化学结构检索 |
| 靶点 (Target) | 药物-靶点关系 |
| 生物活性 (Bioactivity) | IC50 / Ki / EC50 |
| 临床试验 | 关联药物-试验 |
| 文献引用 | 化合物-文献链 |

### PubChem (1.2亿+ 化合物)
| 数据 | 用途 |
|---|---|
| 化合物属性 (MW / LogP / TPSA) | 类药性评估 |
| 安全性 (GHS hazards) | 监管标签 |
| 文献关联 | PubMed cross-ref |
| 生物测定 (BioAssays) | 活性筛选 |
| 专利 (SureChEMBL) | 专利链接 |

## 2. 跟 TalkMED 关系

- §2 注射剂市场: PCSK9 单抗 / siRNA (Inclisiran 是 GalNAc-siRNA,化学结构在 ChEMBL)
- §3 在研管线: 口服 Lp(a) 小分子 (HRS-5346 / YS2302018 / Muvalaplin) 都在 ChEMBL
- §4 临床数据: LDL-C 降幅机制解释 (分子-靶点结合)

## 3. 集成步骤

### Phase 5.0.2
- [ ] `internal/source/chembl.go`
  - `CompoundByName(name)` → `*Compound`
  - `SearchByTarget(target_id)` → `[]Compound`
  - `Bioactivity(compound, target)` → `[]Activity`
- [ ] `internal/source/pubchem.go`
  - `CompoundByName(name)` → `*PubChemCompound`
  - `Synonyms(name)` → `[]string`
  - `Assays(compound_cid)` → `[]Assay`

## 4. 测试

- [ ] Inclisiran (CHEMBL4650520)
- [ ] Evolocumab (ChEMBL: monoclonal, find target/sequence)
- [ ] Olpasiran (CHEMBL5095669)
- [ ] Pelacarsen (CHEMBL4650423)

## 5. 工作量

约 3 天 (2 个 API + schema 映射)