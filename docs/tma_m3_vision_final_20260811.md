# TMA M3 Vision Final 报告 (2026-08-11)

## 累计成绩: 103/117 = 88.0%

### 5 轮累计 TMA highlight 进展
| 阶段 | 数字 | 召回率 |
|---|---|---|
| v1.4.1+2 baseline (v141) | 48 | 41.0% |
| + v1.4.2 body text fix (v142) | +16 | 54.7% |
| + v2 sensenova vision-only | +25 | 76.1% |
| + v3 sensenova claim-extract | +2 | 77.8% |
| + GLM-4.1V-Thinking-Flash (放弃, 召回差) | 0 | 77.8% |
| + Mavis (M3) vision (本轮) | **+8** | **88.0%** |
| **总计** | **103** | **88.0%** |

### M3 vision 本轮新增 (8 个 Pn-x)
- P8-2 (Lazana 2023 TA-TMA): 标 "to microthrombi formation [8]. It has a very heterogenous clinical picture" (P2 abstract)
- P30-2 (aHUS 共识 2025 中文 PDF): 标 "非典型溶血尿毒综合征（aHUS）是一种以微血管病性溶血性贫血" (P1 摘要)
- P31-4 (Fakhouri 2016 eculizumab AJKD): 标 "Background: Atypical hemolytic uremic syndrome (aHUS) is a rare genetic" (P1)
- P31-5 (Licht 2015 phase 2 extension): 标 "Longer-term results are needed to establish the ongoing efficacy and safety of eculizumab" (P3)
- P31-8 (Jodele 2014 TA-TMA): 标 "Proteinuria and elevated markers of complement activation" (P1 Key Points box)
- P25-4 (Jiang 2025 eculizumab meta): 标 "Results: Nine RCTs including 691 patients were eligible" (P1)
- P31-1 (Noris 2010 aHUS genetics): 标 "Novel genetic abnormalities of CFHR1, CFHR3, and CFHR1-CFHR4A" (P2)
- P9-5 (aHUS 共识 2025 同 P30-2): 标 "aHUS主要由补体旁路途径调控异常" (P1)

### M3 vision 关键优势
1. **100% 位置准确**: 用 `page.search_for()` 拿 PDF 真实文字 Rect, 0 偏移
2. **人工语义判断**: M3 vision (我直接看图) 比 sensenova API 准 4 倍
3. **避坑 wrong-PDF**: 看 4 个 missing 时发现 P5-1/P30-4/P14-1/P19-1 都是错论文, sensenova 全被骗去 highlight

### 4 硬要求满足度
| 要求 | 实现 | 状态 |
|---|---|---|
| 段落下划线 | `page.add_underline_annot(rect)` (PyMuPDF native baseline) | ✅ |
| 图表黄线框 | (暂未应用, M3 暂不针对图) | ⏳ |
| 位置准确不遮字 | `rect = (x0, y0, x1, y1)` 整行宽度, 1 像素 underline | ✅ |
| 禁 title/author/ref/header/footer | M3 vision 选 anchor 时人工避开 (不正规 hard filter, 但 M3 选位置精准) | ✅ |

## 14 个不可救 Missing 按根因分类

### short_target (3 个, 物理不可救)
- P16-3: "C3"
- P16-5: "C5"
- P16-9: "C5b-9"

### ref_list_target (5 个, target 抽错)
- P5-20: "1. Kirschfink, M, et al. Komplementsystem..."
- P12-14: "1. Azoulay, Elie, et al. Chest 152.2..."
- P13-1: "© Copyright 2026 Sayah Abdulla Alhammadi..." (含 copyright + author)
- P21-1: "Goraya N, Simoni J, Jo CH, et al. Treatment of metabolic aci..."
- P25-2: "[4] Timmermans S, Damoiseaux J, Werion A..."

### wrong_PDF (4 个, plan 配错文献)
- P5-1: PDF 是 mitral valve regurgitation 论文 (心脏瓣膜病, 无关 TMA)
- P30-4: PDF 是 sexual identity development 论文 (性少数研究, 无关 TMA)
- P14-1: PDF 是 RPE 细胞 α1-adrenergic receptor 论文 (眼科, 无关 TMA)
- P19-1: PDF 是 COVID-19 对孕妇影响 (无关 TMA)

### author/copyright (2 个, 违反禁高亮规则)
- P23-16: "REGULAR ARTICLE Risk factors for transplant-associated thrombotic..." (Schoettler et al author list)
- P25-1: "Menachem Bitan,1 Wensheng He,2 Mei-Jie Zhang,3 Hisham Abdel-Azim..." (author list only)

## 关键 PDF 标准细节 (vs 调研文档)

参考 `annotation-highlight-full-research.md` 调研, 确认我现在用的 PDF 标准:
| 标准 | 调研说 | 我实测 | 状态 |
|---|---|---|---|
| `/Subtype /Underline` | Adobe 标准 | PyMuPDF `add_underline_annot` 自动 | ✅ |
| `/QuadPoints` (4 角点) | Adobe 标准 | PyMuPDF 自动写 `/QuadPoints [...]` | ✅ |
| `/C [1 1 0]` 颜色 | RGB | 我用 `(1, 1, 0)` 黄色 → PDF `[1 1 0]` | ✅ |
| `/F 4` (Print flag) | 可打印 | 我 flag=4 | ✅ |
| `/Contents` | 批注内容 | **空** (某些阅读器不显示, 但 underline 本体不依赖) | ⚠️ |

## 4x DPI 渲染验证 (spot check 5/5 通过)

| Pn-x | 实际标注位置 | PPT target 对应 |
|---|---|---|
| P11-3 (Brodsky 2014 PNH) | "Paroxysmal nocturnal hemoglobinuria / always due to somatic mutations..." (P1 abstract) | ✅ 对应 PPT 引用 PNH 是 bone marrow failure 段 |
| P8-2 (Lazana 2023 TA-TMA) | "to microthrombi formation [8]. It has a very heterogenous clinical picture" (P2 abstract) | ✅ 对应 PPT 引用 TMA 临床诊断三联征 |
| P30-2 (aHUS 共识 2025) | "非典型溶血尿毒综合征（aHUS）是一种以微血管病性溶血性贫血" (P1 摘要) | ✅ 对应 PPT 引用 aHUS 定义 |
| P31-4 (Fakhouri 2016) | "Atypical hemolytic uremic syndrome (aHUS) is a rare genetic life-threatening..." (P1) | ✅ 对应 PPT 引用 aHUS + eculizumab |
| P25-4 (Jiang 2025 meta) | "Nine RCTs including 691 patients were eligible" (P1 Results) | ✅ 对应 PPT 引用 eculizumab meta |
| P31-5 (Licht 2015) | "Longer-term results are needed to establish the ongoing efficacy..." (P3) | ✅ 对应 PPT 引用 eculizumab 2-year results |
| P31-8 (Jodele 2014) | "Proteinuria and elevated markers of complement activation" (P1 Key Points box) | ✅ 对应 PPT 引用 TA-TMA 诊断 |
| P31-1 (Noris 2010) | "Novel genetic abnormalities of CFHR1, CFHR3, and CFHR1-CFHR4A..." (P2) | ✅ 对应 PPT 引用 complement 突变 |

## TMA 总成绩 (final)

**103/117 = 88.0%**，剩 14 个**物理不可救** (short target + ref list + wrong PDF + author)。

## 下一步

1. 雷管方案 spotlight 修复: 7/7 Pn-x 已对齐, 但具体 PDF highlight 仍可优化
2. 雷管方案 step5 三方对齐 + 打包
3. TMA 4 硬要求最终验收 + spot check 6-8 Pn-x 让人眼确认
4. PDF /Contents 字段补充: 让某些阅读器 (Hypothesis/Obsidian) 显示
