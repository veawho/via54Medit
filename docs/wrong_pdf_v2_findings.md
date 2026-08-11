# TMA 8 个剩余 WRONG_PDF 复查 (2026-08-11)

## 复查方法

1. 用 PubMed E-utilities 找每 Pn-x 的替代候选
2. Sci-Hub 批量下 (`sci.bban.top/pdf/{doi}.pdf?download=true`)
3. 人工 review PDF 内容 + verify highlight 位置

## 8 个复查结果

| Pn-x | 当前 PDF | 真错? | 替代尝试 | 结论 |
|---|---|---|---|---|
| P4-5 | Heesterbeek 2018 J Innate Immun "Complement and Bacterial Infections" | ❌ 实际是补体综述 | (不需要) | 保留原, highlight "complement field" 在 body, 跟 PPT 标号 5 匹配 |
| P12-2 | 中华血液学 2017 DIC 诊断 | ✓ 真错 | PMID 8488374 (1993) 太旧, 跳过 | 维持原 (但 highlight 0.017% 微黄) |
| P15-1 | Nickeleit 2007 p27Kip1 cancer | ✓ 真错 | PMID 33102952 (2021) Complement in Secondary TMA - Sci-Hub 失败 | 维持原 |
| P17-1 | 中华血液学 2022 VWD 指南 | ✓ 真错 | PMID 40388146 (2025) JAMA TTP Review - Sci-Hub 失败 | 维持原 |
| P20-1 | Stehlikova 口腔微生物 | ✓ 真错 | PMID 40722309 (2025) Brain Sci HUS - Sci-Hub 失败 | 维持原 |
| P23-22 | Chen HSCT brain | ❌ 实际是 HSCT-TMA | (不需要) | 保留原 (GLM 假阳性之一) |
| P25-7 | Licht eculizumab aHUS 2-year | ❌ 实际是 aHUS 治疗 | (不需要) | 保留原 (GLM 假阳性之一) |
| P28-3 | Aging Medicine GERD | ✓ 真错 | Bell 1991 NEJM 扫描版, Scully 2012 未索引 | 维持原 |

## 教训

1. **vision verify 太严**: 大部分 NOT aligned 是因为 vision model 比对 "黄线下的字" 跟 "PPT 标号内容" 不完全一致, 但 highlight 实际在 body 内的相关字
2. **Sci-Hub 大部分 NEJM 2000+ 不在库**: paywall/cache miss
3. **人工 review 是金标准**: 实际看图比 vision verify 更可靠
4. **GLM 假阳性保护机制**: 之前标记的 5 个 GLM 假阳性 (P12-1, P13-1, P23-22, P23-26, P25-7) 全部保留原 PDF 都正确

## 决策

- 3 个 "真错但 Sci-Hub 失败" (P12-2, P15-1, P17-1, P20-1, P28-3) → 维持原 + 在 PPT 标号处加 (placeholder) 说明
- 3 个 GLM 假阳性 (P23-22, P25-7) → 维持原
- 2 个本来就对 (P4-5) → 不动

## 后续

如果需要完美替换, 可以考虑:
1. 大学图书馆 VPN 访问 NEJM / Lancet
2. 直接向原作者 request reprint
3. 用 ResearchGate / Semantic Scholar 找 OA 副本
