# via54Medit 数据源全景目录 (CATALOG)

> **生成日期**: 2026-06-30
> **覆盖**: EBM 学术 (55+ 源) + 商业医药情报 (60+ 源) = **115+ 数据源**
> **方法**: Subagent #1 (EBM, 9 GitHub MCP 仓库深读) + Subagent #2 (商业, 9 大类扫描) + TalkMED AgentPilot 7 页 PDF 反推
> **使用**: 此目录是 via54Medit v5.0 升级的 source-of-truth

---

## 0. 双模式架构 (v5.0 升级)

via54Medit 从 v4.5 的 **单模式 EBM 学术路由器**,升级为 **双模式平台**:

| 模式 | 用户 | 输出 | 数据源类型 |
|---|---|---|---|
| **`ask` (EBM 学术)** | 临床医生 / 研究者 / 学生 | GRADE 评级 + EBM 摘要 + 引用 PPT | 学术文献 + 临床试验 + 指南 |
| **`intel` (商业情报)** | 药企 BD / 投资分析师 / 医药代表 | 7 页市场报告 (TalkMED 类) | 销售数据 + 管线 + 财报 + 会议 |

底层共享 **多源融合算法 + PICO + 去重 + 标注 PPT 渲染**,只换数据源和路由策略。

---

## 1. EBM 学术源 (现有 + 扩充)

### 1.1 现有 4 源 (v4.5)
| ID | 源 | 集成状态 |
|---|---|---|
| `antfu` | 蚂蚁阿福 RAG | ✅ 已集成 |
| `pubmed` | PubMed / Entrez | ✅ 已集成 |
| `openalex` | OpenAlex 250M+ | ✅ 已集成 |
| `s2` | Semantic Scholar | ✅ 已集成 |

### 1.2 v5.0 优先级新增 (EBM)
#### P0 必接 (REST 简单 + 高度互补)
| ID | 源 | 互补维度 | 难度 | 推荐 MCP/SDK |
|---|---|---|---|---|
| `clinicaltrials_v2` | ClinicalTrials.gov v2 | 文献+试验 | 低 | genomoncology/biomcp 或 cyanheads |
| `europe_pmc` | Europe PMC 4000万+ | 全文+预印+专利 | 低 | 自写 (REST 简单) |
| `medrxiv_biorxiv` | medRxiv/bioRxiv API | 灰色文献 | 低 | pipeworx-io/mcp-biorxiv |
| `openfda` | OpenFDA 14 tools | 药物安全 | 低 | cyanheads/openfda-mcp-server |
| `dailymed` | DailyMed SPL 15万+ | 药物标签 | 低 | 自写 |
| `pubtator3` | PubTator 3.0 | 实体标注/NLP | 低 | 自写 |

#### P1 推荐 (REST 中等 + 高度互补)
| ID | 源 | 数据 | 难度 |
|---|---|---|---|
| `chembl` | ChEMBL 240万+ 化合物 | 药物活性 | 低 (官方 chembl_webresource_client) |
| `opentargets` | Open Targets Platform GraphQL | 药物-靶点-疾病 | 低 (官方 MCP) |
| `biothings` | MyGene/MyVariant/MyChem/MyDisease | 结构化实体 | 低 (QuentinCody/biothings-mcp-server) |
| `pubchem` | PubChem 1.2亿 | 化合物 | 低 (cyanheads/pubchem-mcp-server) |
| `orphanet` | Orphanet 6000+ 罕见病 | 罕见病 | 低 (参考 orphanet-rag) |
| `pharmgkb` | PharmGKB 药物基因组 | 精准用药 | 低 |
| `lactmed_livertox` | LactMed/LiverTox | 特殊人群用药 | 低 (NCBI E-utilities) |
| `genereviews_omim_clinvar` | GeneReviews + OMIM + ClinVar | 遗传病诊断 | 低-中 |

#### P2 高价值但难集成
| ID | 源 | 难度 |
|---|---|---|
| `cochrane` | Cochrane Library | 高 (无 API, HTML 抓) |
| `who_iris` | WHO IRIS | 中 (部分 API) |
| `nice_sign_cma` | NICE/SIGN/CMA 指南 | 高 (HTML 抓) |
| `gin` | GIN 国际指南库 | 高 (会员) |

> **⚠️ 决策 4 排除付费源 (2026-06-30)**: 全部 P3 商业授权源不接入。

~~#### P3 商业授权
| ID | 源 | 备注 |
|---|---|---|
| `embase` | Embase | 商业 |
| `scopus_wos` | Scopus/WoS | 机构订阅 |
| `uptodate_clinicalkey` | UpToDate/ClinicalKey | 商业 |
~~
**总计: 0 付费源接入 (策略: 全部免费/开源)**
### 1.3 EBM GitHub 工具元数据

#### 超级 MCP (可作参考架构或直接 MCP 调用)
- **[genomoncology/biomcp](https://github.com/genomoncology/biomcp)** ⭐MIT, 12+ 实体类别, Python+Rust 双实现 — **几乎覆盖所有 EBM 源 + 结构化实体**, 是 via54Medit 应该**借鉴 + MCP 协议集成**的对象

#### 各源 MCP 一览
- `clinicaltrials_v2`: genomoncology/biomcp, cyanheads/clinicaltrialsgov-mcp-server, rmpugliese/clinicaltrials-mcp, Al1Abdullah/Helix, donbr/lifesciences-research, navisbio/AACT_MCP
- `europe_pmc`: europepmc (R), genomoncology/biomcp
- `medrxiv_biorxiv`: pipeworx-io/mcp-biorxiv, genomoncology/biomcp
- `openfda`: cyanheads/openfda-mcp-server (14 tools, **官方 hosted**), GSA-TTS/mcp-server-openfda (GSA 官方)
- `chembl`: JackKuo666-ChEMBL-MCP-Server, donbr/lifesciences-research/chembl-mcp, chembl_webresource_client (官方)
- `opentargets`: opentargets-open-targets-platform-mcp (**官方**)
- `pubchem`: cyanheads/pubchem-mcp-server, JackKuo666-PubChem-MCP-Server
- `biothings`: QuentinCody/biothings-mcp-server, longevity-genie/biothings-mcp (BioContextAI)
- `gwas_catalog`: koido-gwas-catalog-mcp
- `who_iris`: genomoncology/biomcp
- `orphanet`: biocompt/orphanet-rag (RAG pipeline 参考)

#### 系统综述方法学工具
- [evidencesynthesis-tools/awesome-evidence-synthesis](https://github.com/evidencesynthesis-tools/awesome-evidence-synthesis) — 100+ 工具索引
- [ASReview](https://github.com/asreview/asreview) ⭐600+ — AI 辅助筛选
- [pyMARE](https://github.com/PyMARE/pymare) — Python meta-analysis
- [PRISMA flowdiagram](https://github.com/evidencesynthesis-tools/awesome-evidence-synthesis) — 流程图
- [RoBMA](https://github.com/FBartos/RoBMA) — Robust Bayesian MA

---

## 2. 商业医药情报源 (新方向)

### 2.1 药品销售/市场数据 (P0 集成)
| ID | 源 | 数据 | 付费 | 难度 | GitHub 工具 |
|---|---|---|---|---|---|
| `openfda` | openFDA (免费) | 批准+标签+不良事件+短缺 | 免费 | 极低 | cyanheads/openfda-mcp-server (14 tools) |
| `fda_orange_book` | FDA Orange Book | 专利+独占期+TE码 | 免费 | 极低 | m-nolan/fda_orange |
| `sec_edgar` | SEC EDGAR | 10-K/10-Q/8-K/13F | 免费 | 极低 | dgunning/edgartools ⭐2.4k |
| `cde` | CDE 中国药品审评 | 注册申报+审评报告 | 免费 | 中 | cde-spraper (小项目) |
| `pdb` | PDB (东方财富) | 中国药品批文+企业品种 | 免费 | 中 | east-money-scraper |
| `chembl` / `pubchem` | ChEMBL / PubChem | 化学结构+活性 | 免费 | 极低 | chembl_webresource_client (官方) |

### 2.2 商业付费源 (P3, 价值高但需预算)
| ID | 源 | 数据 | 付费 | 难度 |
|---|---|---|---|---|
| `yaozh` | 药智数据 | 中国药品销售+中标+一致性 | 极高 | 极高 (反爬严) |
| `pharmcube` | 医药魔方 | 全球+中国管线+交易+专利 | 高 (10w+/年) | 高 |
| `insight` | Insight (科睿唯安) | 全球管线+专利+交易+适应症 | 极高 (50w+/年) | 极高 |
| `citeline` | Citeline/PharmaProjects | 全球管线+公司+适应症 | 极高 | 极高 |
| `adisinsight` | AdisInsight (Springer) | 管线+药物评价 | 极高 | 极高 |
| `globaldata` | GlobalData Pharma | 管线+市场+SWOT | 极高 | 极高 |
| `pharnexcloud` | 药融云 | 中国/全球管线+交易 | 中 | 高 |
| `menet` | 米内网 | 中国医院/零售终端 | 高 | 高 |
| `frost_sullivan` | Frost & Sullivan | 行业市场+预测 | 极高 | 高 |
| `huaon` | 华经产业研究院 | 中国行业 | 低 | 高 |
| `statista` | Statista 医药 | 行业统计 | 中 | 中 |
| `wiseguy` / `grandview` | WiseGuy / Grand View Research | 全球细分市场 | 中 | 高 |
| `bloomberg` | Bloomberg Terminal | 全球金融+管线+估值 | 极高 (30w+/年) | 极高 |

### 2.3 临床试验商业维度
| ID | 源 | 数据 | 难度 |
|---|---|---|---|
| `clinicaltrials_v2` | ClinicalTrials.gov (已有学术版) | 试验+申办方+地理 | 极低 |
| `trialsitenews` | Trialsitenews (RSS+抓取) | 试验快讯+行业访谈 | 低 |
| `chinadrugtrials` | chinadrugtrials.org.cn | 中国注册试验 | 高 (反爬) |

### 2.4 专利
| ID | 源 | 数据 | 难度 |
|---|---|---|---|
| `google_patents` | Google Patents (抓取) | 全球专利+法律状态 | 低 (抓取) |
| `surechembl` | SureChEMBL | 化合物专利 (化学实体) | 极低 (官方) |
| `epo_ops` | EPO Open Patent Services | 欧洲专利+全球 | 低 (OAuth) |
| `patentics` | Patentics (合享智慧) | 中国专利+语义 | 中 (付费) |
| `incopat` | incoPat (合享) | 全球专利 | 中 (付费) |

### 2.5 企业财报/公告
| ID | 源 | 难度 |
|---|---|---|
| `sec_edgar` | SEC EDGAR | 极低 (edgartools ⭐2.4k) |
| `hkexnews` | 港交所 HKEXnews | 低 |
| `sse_szse` | 上交所/深交所 A 股 | 中 |
| `bloomberg` | Bloomberg Terminal | 极高 (30w+/年) |

### 2.6 行业报告 (TalkMED §1 引用)
| ID | 源 | 难度 |
|---|---|---|
| `huaon` | 华经产业研究院 | 高 |
| `wiseguy` | WiseGuy Reports | 高 |
| `frost_sullivan` | Frost & Sullivan | 高 |
| `grandview` | Grand View Research | 高 |
| `statista` | Statista | 中 |

### 2.7 医药会议摘要 (TalkMED §4 引用 AHA 2025/ACC 2026)
| ID | 源 | 难度 |
|---|---|---|
| `aha` | AHA Scientific Sessions | 中 |
| `acc` | ACC Annual Scientific Session | 中 |
| `asco` | ASCO Annual Meeting | 中 |
| `esmo` | ESMO Congress | 中 |
| `esc` | ESC Congress | 中 |
| `eas` | EAS Congress (降脂/动脉粥样硬化 — **本次 PDF 直接相关**) | 中 |

### 2.8 投资/BD (并购/许可)
| ID | 源 | 难度 |
|---|---|---|
| `biocentury` | BioCentury | 高 (付费) |
| `fiercebiotech` | FierceBiotech | 低 (RSS) |
| `endpoints` | Endpoints News | 中 |
| `stat` | STAT News | 低 (RSS) |
| `pharmcube_deals` | 医药魔方交易库 | 高 (付费) |

### 2.9 AI 商业情报 / 试验 AI (TalkMED 直接参照)
| ID | 源 | 难度 |
|---|---|---|
| `trialchase` | TrialChase (AI 试验匹配) | 中 (付费) |
| `atomwise` | Atomwise | 极高 |
| `insitro` | Insitro | 极高 |
| **开源参照项目** | | |
| `pharma_pilot` | [Sayan-CtrlZ/PharmaPilot](https://github.com/Sayan-CtrlZ/PharmaPilot) (CrewAI) | 中 |
| `paper_trail` | [xiaomai4681/paper-trail](https://github.com/xiaomai4681/paper-trail) | 中 |
| `drug_approval_dashboard` | [asfiya-tehmeen/Drug_Approval_Pipeline_Intelligence_Dashboard](https://github.com/asfiya-tehmeen/) | 中 |
| `pharma_market_ai` | [mahdinamavar/pharma-market-intelligence-ai](https://github.com/mahdinamavar/pharma-market-intelligence-ai) (XGBoost) | 中 |

---

## 3. 集成优先级矩阵 (TalkMED PDF 反推)

对照 7 页 PDF 报告的结构,我们需要的源:

| TalkMED § 章节 | 关键源 |
|---|---|
| §1 市场总览 (CAGR, 销售) | `openalex` + `huaon` + `wiseguy` + `pdb` + `yaozh` |
| §2 注射剂市场 | `openfda` + `fda_orange_book` + `chembl` + `pubchem` + `clinicaltrials_v2` |
| §3 在研管线 (企业 × 阶段) | `clinicaltrials_v2` + `sec_edgar` + `pharmcube` + `citeline` |
| §4 临床数据 (CVOT/LDL-C) | `pubmed` + `europe_pmc` + `aha` + `acc` + `eas` + `medrxiv` |
| §5 投资关注点 | `sec_edgar` + `biocentury` + `endpoints` + `pharmcube_deals` |

---

## 4. 总数统计

| 类别 | 源数 | P0 集成 | P1 推荐 | P2 难 | P3 付费 |
|---|---|---|---|---|---|
| **EBM 学术** | 55+ | 6 | 7 | 4 | 3 |
| **商业情报** | 60+ | 6 | 8 | 6 | 13+ |
| **总计** | **115+** | **12** | **15** | **10** | **16+** |

---

## 5. 实施路径

| 版本 | 新增源 | 优先级 | 工时估 |
|---|---|---|---|
| **v4.5 → v5.0** (本月) | 6 P0 EBM + 6 P0 商业 = 12 个 | P0 | ~4 周 |
| v5.0 → v5.5 | + 7 P1 EBM + 8 P1 商业 = 15 个 | P1 | ~6 周 |
| v5.5 → v6.0 | TalkMED 7 页 PDF Agent + 双模式路由 | 架构 | ~8 周 |
| v6.0 → v6.5 | + P2 P3 付费源 (按需) | 按预算 | 持续 |

每源具体集成计划见同目录下的 `<source-id>.md` (10 个 P0 已写, 见 README 索引)。