# TMA 11 WRONG_PDF 重下进展 (2026-08-11)

## 总览

- 11 个 TMA WRONG_PDF 标记需替换
- 11/11 跑通 PubMed E-utilities + Europe PMC 搜索
- 8/11 找到 OA 候选
- **1/11 实际替换 + 验证成功**: P8-2 (Palma KIR → Lazana 2023 Transplant-Associated TMA)
- 10/11 维持原 PDF (PDF 重下需要逐个验证, 留待后续批处理)

## 替换案例: P8-2

**原 PDF**: Palma LMP 2020 "Acute Kidney Injury Associated with Immune Checkpoint Inhibitors" (KIR 6(1):11-23)
- vision verify 报告: 黄线落在 journal disclaimer, 与 PPT 标号"TMA三联征"完全无关

**新 PDF**: Lazana 2023 "Transplant-Associated Thrombotic Microangiopathy" (Int J Mol Sci 24:1159, MDPI, OA)
- PubMed PMID: 36674666
- DOI: 10.3390/ijms24021159
- 13 页, 内容与 PPT 标号匹配 (TMA, MAHA, thrombocytopenia, organ damage)
- 来源: Europe PMC fullTextUrl
- 备份: `_downloads/_pdfs_real/P8-2.pdf` 保留原 Palma KIR

**结果对比**:

| 指标 | 原 PDF (Palma KIR) | 新 PDF (Lazana TMA) |
|---|---|---|
| Pages | 8 | 13 |
| Highlight hits (line mode) | 6 | 347 (~58x) |
| Yellow pixel % | 0.011% | 0.087% (~8x) |
| Topic match | ❌ KIR/PD-1 | ✅ TMA |
| 来源 | KIR 2021 | MDPI OA |

## 11 个候选清单 (来自 `wrong_pdf_replacement_candidates_20260811.json`)

| Pn-x | Topic | 候选 PMID | OA | Status |
|---|---|---|---|---|
| P3-1 | 补体三条途径 | 42136966, 42112359, 41978671 | 🟢 3 | 主题不匹配, 维持原 |
| P3-2 | 补体激活调节 | 42493353, 42484484, 42467713 | 🔴 | 维持原 |
| P4-5 | 近端补体调理 | (无候选) | - | 维持原 |
| P8-2 | TMA 三联征 | **36674666** | 🟢 1 | ✅ **已替换** |
| P12-1 | 血涂片 schistocytes | 28447424, 8488374 | 🔴 | 维持原 |
| P12-2 | MAHA 血涂片 | 41630338 (错), 40384402 | 🟢 1 | 维持原 (主题错) |
| P14-1 | TMA 内皮损伤 | 23411690 | 🔴 | 维持原 |
| P15-1 | TMA 病因分类 | (无候选) | - | 维持原 |
| P17-2 | ADAMTS13 TTP | 41970181, 42461718, 41770788 | 🟢 1 | 维持原 (HTML 错) |
| P20-1 | STEC-HUS 肾外 | 40722309 | 🟢 1 | 维持原 (HTML 错) |
| P28-3 | TTP 死亡 | 37331965, 23455401 | 🔴 | 维持原 |

## 教训

1. **OA 标记不等于可下载**: Europe PMC `isOpenAccess: Y` 但 fullTextUrl 是 HTML 页面, 不是真 PDF
2. **MDPI URL 最稳**: `https://www.mdpi.com/.../pdf?version=...` 直接返回 PDF
3. **必须 verify title**: HTML 页面伪装成 PDF 容易误判
4. **PDF 替换不能批量**: 每个 Pn-x 都要单独 verify alignment, 否则换错更糟

## 下一步建议

1. **继续人工 review**: 1/11 已替换, 10/11 待办
2. **优先 P3-1, P3-2 (补体综述)**: Walport 2001 NEJM, Janeway 2001 综述 都是经典, 但都 paywall
3. **P15-1 (TMA 病因)**: 改搜 "TMA classification" 或 "primary TMA secondary TMA"
4. **保守策略**: 维持原 PDF, 在 vision verify 报告里标记 WRONG_PDF, 用户决定是否替换
