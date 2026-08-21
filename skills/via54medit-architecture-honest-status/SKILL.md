---
name: via54medit-architecture-honest-status
description: >
  via54Medit 4 层架构与诚实声明原则. 每次汇报架构时必须区分"设计"和"已实现",
  用状态列标注每一层的真实配置情况. 基于 2026-08-01 用户纠正, 必须诚实回答.
  触发关键词 - 架构状态, 设计 vs 实现, 是否配置了, 是否最佳路径, 是否还有提升空间,
  双源架构, sensenova, Producer 分类, 不合成 1 个 PDF.
---

# via54Medit 架构诚实声明原则

## 1. 触发条件

用户问以下任何问题，必须用附表回答：
- "这些是否都配置了"
- "是否已经是你找到的最佳路径"
- "是否还有提升空间"
- "是否对齐了我的完整诉求"
- "双源架构" / "main + fallback" / "不合成 1 个 PDF"
- "sensenova" / "sensenova-6.7-flash-lite" / "替代 mmx vision"
- "Producer 分类" / "ReportLab 截图" / "Chrome 截图包壳"

## 2. 4 层架构状态表（必须严格执行）

| 层 | 技术栈 | 实现状态 | 真话 |
|---|--------|----------|------|
| L1 文字加速 | PyMuPDF / PyMuPDF4LLM | ✅ 已用 / ⚠️ 已装但未接 | 纯文字提取 PyMuPDF 更快，4LLM 不需要 |
| L2 结构化 | **PaddleOCR PP-Structure** (86k★) | ✅ **已装 + 验证通过** | 中文场景最优，已替代 docling 64k★ |
| L3 视觉理解 | **sensenova-6.7-flash-lite** (NEW 2026-08-01) | ✅ **已用 + 4 Pn-x 验证** | **替代 mmx vision**, 免费+262K context+无敏感词 |
| L4 应证推理 | `internal/anno2ppt` | ✅ **已落地 + 9/9 测试** | 唯一真落地的核心 |
| **L4+ 双源架构** | `internal/anno2ppt/dual_source.go` (NEW) | ✅ **已落地 + 9/9 测试** | 2026-08-01 P30-1 实战, ScienceDirect abstract (main) + NCT02329860 (fallback) |
| **L4+ Producer 分类** | `internal/anno2ppt/l0_producer_classifier.go` (NEW) | ✅ **已落地 + 33/33 测试** | 区分 ReportLab / Chrome Skia / 真 PDF / Meeting abstract |
| L5 错行修复 | PaddleOCR + 行对齐 | ⚠️ 已装但逻辑未写 | 规划中有 |

## 3. 设计 != 实现（用户纠正 2026-08-01）

**不要做**: 把设计文档和已实现混在一起写，让用户以为代码全跑了。

**必须做**:
- 每次汇报架构时，用独立的状态列标注每层的真实完成度
- 诚实列"提升空间"表（缺口 + 影响 + 优先级）
- 如果某个方案是"设计"而不是"已实现"，必须说"这个还没接"

## 4. 提升空间模板

| 缺口 | 影响 | 优先级 |
|------|------|--------|
| **C 类应证 (KM 曲线/森林图/流程图) 未实现** | **图 PDF (P22-1 类) v3.9 标了图外元数据漏图内关键数据, v4.0 也没补** | **🚨 高** |
| P22-1 类单页图 PDF | 必须 PaddleOCR + sensenova vision 联合, 不能只靠文字层 | 高 |
| 错行修复逻辑未写 | PaddleOCR 裸输出, 没做行对齐 | 中 |
| L4 不是动态权重 | 4 维权重是手调的 | 低 |
| L4+ Producer 分类器 ↔ Crossref API 联动 | 拿到 PDF 立即查 Crossref, 不靠 producer 关键词 | 中 |
| L4+ 双源 manifest 自动生成 | 手动构造 manifest 易漏字段 | 低 |

## 4.5. ⚠️ v4.0 实战诚实 (2026-08-01)

**本次 session 验证结论**: v4.0 现在覆盖 **2 / 3 类** 应证:

| 类 | 真实案例 | v4.0 算法 | 实战结果 |
|----|---------|-----------|---------|
| A. 政策文字 | P3-2 健康中国 46.6% 目标 | PyMuPDF 文字层匹配 | ✅ 1 段高亮正确 |
| B. 集合结论 | P3-3 Fig.2 27 行癌肿 | PyMuPDF 文字层 + y 坐标配对 + L4 | ✅ 应证得分 0.95, 27 行全标 |
| **C. 临床图表** | **P22-1 KM 曲线图 (单页, 数据全在图里)** | **❌ v4.0 没实现** | **❌ v3.9 标图外漏图内** |

**诚实声明**: 用户说 "你挑选一个其他类型的, 我们继续测试". 我选了 P22-1 (C 类), 验证 v4.0 是否覆盖, **结论是 v4.0 不覆盖 C 类**. P22-1 highlight 还是错的.

**下次拿新 Pn-x 之前, 必须先看 PDF 是文字/表格/图 哪种类型**:
- A 类 → v4.0 ✅
- B 类 → v4.0 ✅
- C 类 → **必须先实现 PaddleOCR 联合 sensenova vision 才能跑**

## 4.6. 🚨 v4.1 双源架构 (NEW 2026-08-01, P30-1 截图包壳教训)

### 触发场景

L0 验证发现 main PDF 是 ReportLab / Chrome Skia/PDF 截图包壳, **真原文 PDF 无法直接获取** (Elsevier 付费墙 / 期刊订阅墙 / PubMed 没有 OA / 各种 source 都失败).

### v4.0 之前的错法

- ❌ 保留 Chrome 截图当 main, manifest 标 "unverified"
- ❌ 强行合成 1 个 PDF (用 ReportLab 把 abstract + 表格拼起来) — **用户硬规则: "不能强行合成 1 个 PDF"**
- ❌ 用任何 source 拿到的"残缺"内容当 main, 标 "publisher_pdf_unavailable"

### v4.1 双源架构 — 不合成, 用互补

```
P30-1/
├── main PDF         = ScienceDirect abstract 截图 (1 页, 有 DOI + 期刊名 + 关键数据 28% 高血压)
├── fallback PDF(s)  = NCT02329860 完整 AE 表格 (4 页, 任何级高血压 47.9% + 蛋白尿 21%)
├── _v39_deprecated/Chrome 截图 (旧版, 留底)
└── manifest.json    = 详细标注 evidence_sources, 哪条数据从哪来
```

### 双源 manifest 必填字段 (NEW v4.1)

```json
{
  "main_pdf": "P30-1/P30-1_main_Qin_AHELP_LancetGastro_2021.pdf",
  "fallback_pdfs": ["P30-1/P30-1_fallback_NCT02329860_ClinTrials.pdf"],
  "fallback_triggered": true,
  "fallback_trigger_reason": "ScienceDirect abstract 提供 28% grade >=3, NCT02329860 提供 47.9% any-grade, 双源互补",
  "evidence_sources": {
    "main": {"source": "ScienceDirect abstract", "limit": "only abstract, no any-grade AE table"},
    "fallback": {"source": "NCT02329860 ClinicalTrials.gov", "limit": "aggregation, not original paper Table 3"}
  },
  "highlight_summary": {
    "main_pdf_hits": 4,
    "fallback_pdf_hits": 40,
    "fallback_pages_highlighted": [2, 3, 4],
    "total": 44
  }
}
```

### 双源 highlight 标注铁律

- main 高亮 = 标在 main PDF 关键文字 (DOI, 标题, 关键数据)
- fallback 高亮 = 标在 fallback PDF 对应数据 (不能重复标 main)
- 必须 2 张图 (main 1 + fallback 1+), 缺一不可

### 双源架构实现位置 (✅ 已落地)

```
via54Medit/internal/anno2ppt/
├── dual_source.go           (新, 234 行) - DualSourceManifest schema, ShouldTriggerFallback, FindNCTRegistry
├── dual_source_test.go      (新, 142 行) - 9/9 PASS
├── l0_producer_classifier.go (新, 215 行) - PDF 黑白名单分类, 4 种策略推荐
├── l0_producer_classifier_test.go (新, 165 行) - 33/33 PASS
└── (与原 algorithm.go, l0_verify.go 并存)
```

## 4.7. 🚨 L4+ Producer 分类器 (NEW 2026-08-01, 18 个 Pn-x 修复实战)

### 背景

L0 之前只验证 L0 score, 误判率 71%. 18 个 Pn-x 修复发现必须先看 producer / creator 关键词.

### PDF 4 种类型分类 + 5 种修复策略

| PDF Type | Producer/Creator 特征 | 修复策略 |
|----------|----------------------|---------|
| `pdf_type_real_pdf` | Veeva Vault / Adobe InDesign / Arbortext | `keep_as_is` |
| `pdf_type_reportlab_wrap` | ReportLab PDF Library + 文字层 "Image: fig2.png" | `replace_with_real_pdf` |
| `pdf_type_chrome_screenshot` | Skia/PDF mXXX + Mozilla creator | `find_oa_am` |
| `pdf_type_meeting_abstract` | pdfmake + 文字层 "ASCO/GI Symposium" | `keep_as_is` |
| `pdf_type_unknown` + L0 失败 | 无 metadata | (L0 失败 + 付费墙) → `use_abstract_as_main` 双源 |
| `pdf_type_unknown` + 无 DOI | 无 metadata | `inspect_manually` |

### Producer 黑白名单 (实测)

| 名单 | Producer/Creator 关键词 | 来源 |
|------|------------------------|------|
| 🚨 黑名单 | `ReportLab PDF Library` / `WeasyPrint` / `Skia/PDF` + `Mozilla` | liangyihui.net / 网页→PDF / Chrome 截屏 |
| ✅ 白名单 | `Veeva Vault` / `Adobe InDesign` / `Adobe PDF Library` / `Arbortext` / `Acrobat Distiller` / `XPP` / `pdfmake` | ASCO/JCO 会议摘要 / 期刊排版 / 期刊工具 / Elsevier 工具 / GI Cancer Symp |

### 已知 18 个截图包壳 Pn-x 全修复 (2026-08-01)

| 数量 | 类型 | 真原文来源 |
|:----:|------|-----------|
| 10 | ReportLab (liangyihui.net 截图包壳) | 6 个 ESMO #1494P 复用 + 3 个 Song YG 复用 + 1 个 Kudo HBSN |
| 4 | Chrome Skia/PDF (NIH PubMed 截图) | 3 个 UCL AAM LEAP-002 + 1 个 AME 期刊 |
| 4 | (含混合) | 1 个 ASCO 2022 abstract + 3 个 clean abstract |

## 4.8. 🚨 sensenova 替代 mmx vision (NEW 2026-08-01, 4 Pn-x 验证)

| 对比项 | mmx vision | **sensenova-6.7-flash-lite** (NEW) |
|--------|-----------|--------------------------|
| 费用 | Token Plan, 经常超限 | **免费** (pricing=0) |
| Context | 有限 | **262K tokens** |
| 敏感词 | "Hong Kong" 触发 `input prompt sensitive` 错误 | **无审查** (国内 API) |
| 安装 | npm mmx-cli | 0 安装, 纯 API |
| 速度 | 慢 | **快** |
| 实测 Pn-x | (Token 用尽报错) | P3-1, P29-1, P33-11, P30-1 全部成功 |

### 集成位置 (✅ 已落地)

```
via54Medit/scripts/
├── sensenova_vision.py    (新, 188 行) - 核心 API 调用 + base64 + --json / --save
└── l3_vision_verify.py    (新, 79 行)  - L3 流程包装器
```

### CLI 用法

```bash
# 单次复核
python3.11 scripts/sensenova_vision.py <image.jpg> "PPT引用语义"

# 结构化 JSON 输出
python3.11 scripts/sensenova_vision.py <image.jpg> "prompt" --json

# L3 集成包装器
python3.11 scripts/l3_vision_verify.py <image.jpg> "allegation_text"
```

### API 详情

```python
base_url: https://token.sensenova.cn/v1
model: sensenova-6.7-flash-lite
input_modalities: ["text", "image"]
output: image base64 in content array
pricing: 0 (免费)
```

### 经验沉淀 (用户硬规则 2026-08-01)

1. **不要预设 Token Plan 还能用** — 立即改 sensenova
2. **sensenova 对 1 页 PDF 的 highlight 图** < 30s 响应
3. **--json 模式** 比 non-JSON 模式偏差大, 默认用 non-JSON
4. **图像分辨率不需要太高** — 150 DPI 已够用

## 5. 实现位置

```
/Users/david/Desktop/developments/via54Medit/
├── internal/anno2ppt/                     (L4 应证推理机 + L4+ 双源 + L4+ Producer 分类)
│   ├── algorithm.go                       (4 维要素对齐, 9/9 测试)
│   ├── l0_verify.go                       (L0 Crossref 验证, 9/9 测试)
│   ├── dual_source.go                     (NEW 双源架构 v4.1, 9/9 测试)
│   ├── l0_producer_classifier.go          (NEW Producer 黑白名单 v4.1, 33/33 测试)
│   └── *_test.go                          (共 60+ 测试全 PASS)
├── cmd/medit/commands/anno2ppt.go         (CLI: parse/confirm/ocr/l0verify)
├── scripts/paddleocr_pdf_page.py          (L2 OCR 脚本)
├── scripts/sensenova_vision.py            (NEW L3 sensenova 集成, 替 mmx vision)
├── scripts/l3_vision_verify.py            (L3 流程包装器)
├── scripts/process_pn_x_learnings.py      (NEW 经验沉淀 callback, 每次任务后自动触发)
└── (已弃用) ~/.local/bin/mmx             (L3 mmx-cli vision, Token Plan 经常超限)
```

## 6. 参考文件

- `references/2026-08-01-session-findings.md` — 第一次 session (P3-2 应证 + PaddleOCR 集成 + mmx 状态)
- `references/2026-08-01-p22-1-verification-and-pn-x-pollution.md` — 第二次 session (P3-2/P3-3 验证 + P22-1 实战 + Pn-x 目录污染事件)
- `references/paddleocr-pdf-page-script.md` — PaddleOCR 脚本调用方式和依赖
- `references/v4.1-dual-source-architecture.md` — **NEW** 双源架构实战 (P30-1 AHELP 案例)
- `references/v4.1-sensenova-replace-mmx-vision.md` — **NEW** sensenova 集成 + 4 Pn-x 验证
- `references/v4.1-producer-classifier.md` — **NEW** Producer 分类器 + 18 Pn-x 修复实战

## 7. 触发关键词

- "架构状态" / "设计 vs 实现" / "是否配置了"
- "是否最佳路径" / "是否还有提升空间"
- "是否对齐了我的完整诉求"
- **NEW** "双源架构" / "main + fallback" / "不合成 1 个 PDF"
- **NEW** "sensenova" / "sensenova-6.7-flash-lite" / "替代 mmx vision"
- **NEW** "Producer 分类" / "ReportLab 截图" / "Chrome 截图包壳"