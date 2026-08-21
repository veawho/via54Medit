# TMA _pnx 目录全面审计结果 (2026-08-10)

## 总览

| 指标 | 数值 |
|------|------|
| CSV 期望PN数 | 106 |
| 实际_pnx目录数 | 111（含5个额外/空目录） |
| 有main.pdf | 106 |
| 有highlight.pdf | 106 |
| 空目录（无任何文件） | 5个 |
| 内容错误（搜索页） | 3个 |

## 空目录（需要重下或删除）

| 目录 | CSV对应引用 | 状态 |
|------|-----------|------|
| P12-3 | UpToDate. Diagnosis of hemolytic anemia | 付费订阅，无法自动下载 |
| P21-2 | （无文件） | 空目录 |
| P22-3 | （无文件） | 空目录 |
| P24-4 | （无文件） | 空目录 |
| P24-5 | （无文件） | 空目录 |

## 内容错误（CNKI下到搜索页）

| 目录 | 下载到的内容 | 真实论文 |
|------|-----------|---------|
| P25-2 | 高级检索/搜索页 | 非典型溶血尿毒综合征多学科诊疗实践专家共识2025版. 中华内科杂志. 2025;64(5):396-411 |
| P30-2 | 高级检索/搜索页 | 同上 |
| P9-5 | 高级检索/搜索页 | 同上 |

**下载正确DOI**: 10.3760/cma.j.cn112137-20250225-00338（中华内科杂志2025版共识）

## 真实同名不同论文（不是错误）

这些"重复"是同名论文的不同研究/不同期刊，**不是**下载错误：

| 组 | 论文1 | 论文2 |
|----|-------|-------|
| P25-5/P31-4 | Trojnar E, Front Immunol 2019 | Fakhouri F, AJKD 2016 |
| P25-6/P31-1 | Zheng XL, JTH 2020 | Noris M, CJASN 2010 |
| P25-7/P31-5 | Laurence J, Clin Adv Hematol Oncol 2016 | Licht C, Kidney Int 2015 |
| P22-1/P29-1 | TMA Care Pathway (不同机构) | Ronald S, Mayo Clin Proc 2016 |
| P22-2/P29-2 | Sridharan, Diagnostic Utility Complement | Azoulay Chest 2017 |

## 真实同名同一论文（已验证）

这些PN实际上指向同一篇论文的不同副本：

| 组 | 论文 | 说明 |
|----|------|------|
| P11-2 / P12-1 | Azoulay Chest 2017 | 同一篇（684KB） |
| P13-1 / P31-3 | Jodele/Dandoy相关 | 同一篇（273KB） |
| P23-23 / P23-4 | Sabulski Cerebral TMA 2022 | 同一篇（1981KB） |
| P23-8 / P28-1 | Lazana I, Int J Mol Sci 2023 | 同一篇（760KB） |
| P24-2 / P9-4 | 中华医学会共识2021 | 同一篇（837KB） |
| P3-2 / P4-2 | Luzzatto PNH 2020 | 同一篇（289KB） |
| P4-4 / P5-2 | Skattum Mol Immunol 2011 | 同一篇（359KB） |
| P23-2 / P24-1 | 不同Guideline版本 | 不同论文（1278KB vs 2147KB） |

## 已验证PDF内容正确的PN（选录）

通过fitz全文搜索验证：

| PN | PDF第一行（标题） | 页数 |
|----|----------------|------|
| P22-2 | Diagnostic Utility of Complement Serology... (Sridharan) | 12 |
| P29-2 | Diagnostic Utility of Complement Serology... (Sridharan) | 12 |
| P25-5 | Original Investigation Terminal Complement Inhibitor Eculizumab... | 10 |
| P31-4 | Original Investigation Terminal Complement Inhibitor Eculizumab... | 10 |
| P25-6 | Relative Role of Genetic Complement Abnormalities... (Noris) | 16 |
| P31-1 | Relative Role of Genetic Complement Abnormalities... (Noris) | 16 |
| P8-1 | Indexed through National Library of Medicine (Laurence) | 16 |
| P31-2 | Indexed through National Library of Medicine (Laurence) | 16 |
| P23-23 | Cerebral vascular injury in transplant-associated TMA (Sabulski) | 10 |
| P23-4 | Cerebral vascular injury in transplant-associated TMA (Sabulski) | 10 |
| P24-2 | 造血干细胞移植相关血栓性微血管病诊断和治疗中国专家共识（2021年版） | 8 |
| P9-4 | 造血干细胞移植相关血栓性微血管病诊断和治疗中国专家共识（2021年版） | 8 |

## 飞书表最终状态

- URL: https://hackhealth.feishu.cn/sheets/P41bsK7t8hMJHntV936cggbxnve
- Token: P41bsK7t8hMJHntV936cggbxnve
- Highlight: **105✅** / 106总
- 仅剩P12-3（UpToDate付费）无法自动获取

## 扩充PPT目录缺失（Step1未完成）

| 目录 | 状态 |
|------|------|
| `_1_ppt/_2_expanded/` | 空（需重建扩充尺寸PPT） |
| `_1_ppt/_3_images/` | 空（需导出扩充版图片） |

**扩充PPT目的**：灰色背景+白字引用区在原尺寸下不可见，需要扩大页面确保所有引用文献可见。
