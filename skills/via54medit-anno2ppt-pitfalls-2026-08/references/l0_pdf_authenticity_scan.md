# L0 PDF 真实性验证 — 扫描报告与黑白名单

生成: 2026-08-01 (P22-1 教训驱动)
配套 skill: via54medit-anno2ppt-pitfalls-2026-08 §19

## 背景

v3.9 算法假设 P22-1 main PDF 是 Bruno Sangro ESMO 2025 #1494P，实际是 liangyihui.net 截图用 ReportLab 包装成 PDF (1 页, producer=`ReportLab PDF Library - (opensource)`, 文字层只含 `"Image: fig2.png"`).

## Producer 黑白名单

纯 L0 score 误判率 71% (35 个可疑中 25 个是真 PDF). **先用 producer 关键词过滤, 再调 Crossref API**.

### 🚨 黑名单 (直接判截图包壳)
| producer / creator 关键词 | 类型 |
|---------------------------|------|
| `ReportLab PDF Library` | ReportLab 截图包壳 |
| `Chromium` + `Skia/PDF mXXX` | Chrome 截屏 |
| `WeasyPrint` | HTML→PDF 包装 |

### ✅ 白名单 (直接判真 PDF)
| producer / creator | 说明 |
|-------------------|------|
| `Veeva Vault` | ASCO/JCO 会议摘要标准 (19 页) |
| `Adobe InDesign` / `Adobe PDF Library` | 期刊标准排版 |
| `Arbortext` / `Acrobat Distiller` | 期刊生成工具 |
| `XPP` | Elsevier 工具 |
| `pdfmake` | GI Cancer Symp 摘要 |

辅助: pages=1 + 文字层只含 `"Image: fig2.png"` = 截图包壳 (100% 置信度)

## 批量扫描结果 (161 个 Pn-x 源目录)

筛选: placeholder_count >= 3 → 35 个可疑, 10 个确认截图包壳, 25 个假警报

### 10 个确认截图包壳

| Pn-x | 类型 | DOI | 真 PDF | 修复 |
|------|------|-----|--------|------|
| P12-1 | ReportLab | 10.1016/j.annonc.2025.08.2124 | ESMO #1494P | ✅ |
| P22-1 | ReportLab | 同上 | ESMO #1494P | ✅ (之前会话) |
| P24-3 | ReportLab | 同上 | ESMO #1494P | ✅ |
| P33-1 | ReportLab | 同上 | ESMO #1494P | ✅ |
| P43-1 | ReportLab | 同上 | ESMO #1494P | ✅ |
| P5-17 | ReportLab | 同上 | ESMO #1494P | ✅ |
| P3-1 | Chromium/Skia | 10.21037/hbsn-22-143 | Kudo HBSN 2022 (从 P13-1 复制) | ✅ |
| **P29-1** | ReportLab | 10.1159/000539423 | Song YG Liver Cancer 2024 | 🔴 待修 |
| **P33-11** | ReportLab | 同上 | 同上 | 🔴 待修 |
| **P41-10** | ReportLab | 同上 | 同上 | 🔴 待修 |

### 25 个假警报 (真 PDF, 只是不带 title metadata)

Veeva Vault (P15-1/P16-1/P17-1/P24-4/P31-2/P33-9), Adobe InDesign (P13-1/P30-9/P39-2/P41-2/P43-7), Arbortext/Acrobat Distiller (P3-4/P31-1/P32-1/P36-4/P4-5/P40-7), XPP (P5-2), pdfmake (P30-6), 无 creator (P30-4/P5-1/P40-10) 等.

## 实现位置

```
/Users/david/Desktop/developments/via54Medit/
├── internal/anno2ppt/
│   ├── l0_verify.go        (280 行, 4 维算法)
│   └── l0_verify_test.go   (9 案例 / 9 PASS)
├── cmd/medit/commands/anno2ppt.go  (l0verify 子命令)
└── scripts/
    ├── l0_extract_pdf_meta.py
    └── l0_batch_scan.py
```

## 算法

```
score = 0.45*TitleSim + 0.30*AuthorSim + 0.15*DateMatch + 0.10*MetadataCompleteness
```

- TitleSim: Jaccard 词集合相似度 (PDF metadata.Title vs Crossref Title)
- AuthorSim: PDF metadata.Author 包含 Crossref Authors[0].Family
- DateMatch: PDF CreationDate >= Crossref Published Date
- MetadataCompleteness: title/author/subject/creator 4 字段非空 (排除 untitled/anonymous/unspecified/anon)

阈值: score >= 0.70 → verified; 0.45-0.70 → warning; < 0.45 → reject

## 待修 PDF 手动下载

**Song YG, et al. Liver Cancer. 2024.** "Risk of Bleeding in HCC Patients Treated with Atezolizumab/Bevacizumab: A Systematic Review and Meta-analysis"

| 项目 | 值 |
|------|-----|
| DOI | 10.1159/000539423 |
| 影响 Pn-x | P29-1 / P33-11 / P41-10 |
| 获取失败原因 | Karger 网站 Cloudflare 防护 (HTTP 200 → challenge page) |
| 操作步骤 | 浏览器打开 `https://doi.org/10.1159/000539423` → Download PDF → 放到 P29-1/ 目录, 同样文件复制到 P33-11/ 和 P41-10/ |

## Key 经验

1. **不要相信文件存在 = 文件正确** — 必须 L0 验证
2. **Producer 黑白名单比纯 L0 评分精确 10 倍**
3. **Jaccard 相似度足够** — 不用 TF-IDF
4. **Veeva Vault / Adobe InDesign / Arbortext 都是白名单 producer** (真 PDF 不带 title metadata)
5. **不要 Placeholder 假阳性** — "Anon" 也视为占位符
