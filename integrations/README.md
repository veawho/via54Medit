# via54Medit 数据源集成索引

> **v5.0 升级 (2026-06-30)**: 项目从单模式 EBM 学术路由器升级为**双模式医药决策平台** (EBM 学术 + 商业情报)。本目录现含 **115+ 数据源候选** + **10 个 P0 集成计划**。

## 索引

| 类别 | 文件 |
|---|---|
| **总目录** | [CATALOG.md](./CATALOG.md) — 115+ 源全景目录 (EBM 55+ + 商业 60+) |
| **架构升级草案** | [../docs/ARCHITECTURE-V5-DRAFT.md](../docs/ARCHITECTURE-V5-DRAFT.md) — v5.0 双模式架构 |
| **集成计划 (10 P0 + 1 P1)** | 见下表 |

## 10 个集成计划 (按 P0 优先级)

### EBM 学术 P0 (6 个)

| 源 | 文件 | GitHub MCP / SDK |
|---|---|---|
| ClinicalTrials.gov v2 | [clinicaltrials_v2.md](./clinicaltrials_v2.md) | genomoncology/biomcp / cyanheads/clinicaltrialsgov-mcp-server |
| Europe PMC | [europe_pmc.md](./europe_pmc.md) | 自写 (REST 简单) |
| medRxiv + bioRxiv | [medrxiv_biorxiv.md](./medrxiv_biorxiv.md) | pipeworx-io/mcp-biorxiv |
| OpenFDA (EBM 部分) | [openfda.md](./openfda.md) | cyanheads/openfda-mcp-server (14 tools) |
| DailyMed | [dailymed.md](./dailymed.md) | 自写 |
| PubTator 3.0 | [pubtator3.md](./pubtator3.md) | 自写 (NCBI E-utilities) |

### 商业情报 P0 (6 个, 含与 EBM 重叠)

| 源 | 文件 | GitHub MCP / SDK |
|---|---|---|
| OpenFDA (商业部分) | [openfda.md](./openfda.md) | 同上 |
| FDA Orange Book | [fda_orange_book.md](./fda_orange_book.md) | m-nolan/fda_orange |
| SEC EDGAR | [sec_edgar.md](./sec_edgar.md) | **dgunning/edgartools ⭐2.4k** |
| ChEMBL + PubChem | [chembl_pubchem.md](./chembl_pubchem.md) | chembl_webresource_client (官方) / cyanheads/pubchem-mcp-server |
| (CDE / PDB 中国商业) | 待写 | 暂无现成 SDK |
| (ClinicalTrials.gov 商业维度) | [clinicaltrials_v2.md](./clinicaltrials_v2.md) | 同上 |

### P1 (1 个)

| 源 | 文件 | 备注 |
|---|---|---|
| AHA / ACC / EAS 会议摘要 | [aha_acc_eas.md](./aha_acc_eas.md) | TalkMED §4 直接相关 (降脂领域) |

### 历史 (v4.5)

- [paper-search-mcp.md](./paper-search-mcp.md) — v4.5 计划集成, v5.0 已通过 clinicaltrials_v2.md 升级
- [README.md](./README.md) — 原 6 GitHub 集成清单 (保留供 v4.5 历史参考)

## 关键决策点 (v5.0 待用户拍板)

参见 [../docs/ARCHITECTURE-V5-DRAFT.md §8 待用户拍板](../docs/ARCHITECTURE-V5-DRAFT.md):

1. P0 源列表是否需要调整 (12 个)?
2. 是否需要新增 layer 5B (商业 CLI) 还是并入现有 CLI?
3. TalkMED 7 页 PDF 是 v5.0 必交付还是 v6.0?
4. 商业付费源 (药智/医药魔方/Citeline) 预算?
5. 是否真要 fork genomoncology/biomcp 进 via54Medit 还是 MCP 协议调用?

## TalkMED AgentPilot 对照

via54Medit v5.0 升级触发来自 TalkMED AgentPilot (https://agent-pilot.talkmed.com) 生成的 7 页 PDF 报告 (用户提交的 123.pdf)。TalkMED 是 DXY 旗下医药商业情报 AI 平台, via54Medit v5.0 的"商业情报模式"将参照其报告结构。