# 双源架构 (Dual Source Architecture) — 2026-08-01 全新设计

> 配套: pitfalls §21, skill: via54medit-anno2ppt-pitfalls-2026-08
> 适用: Elsevier/Wiley/Karger 付费墙拿不到完整 PDF, 但 abstract + NCT 公开数据可互补的场景.

## 核心铁律 (用户 2026-08-01 P30-1 硬规则)

> "不能将两个文件强行合成 1 个 PDF, 而是将 doi 对应页面作为 main, 数据补充作为 fallback"

**绝对禁止**:
- ❌ 把 ScienceDirect abstract + NCT 表合并为 1 个 PDF
- ❌ 把任何两个不同源 (journal/NCT/UCL AM/publisher) 强行拼装

**必须**:
- ✅ main_pdf 单独文件 (有 DOI/期刊名/关键数据)
- ✅ fallback_pdf 单独文件 (NCT 表 / supplementary / OA AAM)
- ✅ manifest 详细标注 `evidence_sources` 字段
- ✅ highlight 标注 2 张图 (main 1 + fallback 1+), 缺一不可

## 双源结构

```
P30-1/
├── P30-1_main_Qin_AHELP_LancetGastro_2021.pdf     (ScienceDirect abstract)
├── P30-1_fallback_NCT02329860_ClinTrials.pdf      (NCT 完整 AE 表)
├── _v39_deprecated/P30-1_main_v39_chrome.pdf      (旧 Chrome 截图, 不删)
└── manifest.json
```

## 数据互补对照 (P30-1 AHELP 实战)

| 数据项 | PPT 需求 | main 提供 | fallback 提供 |
|--------|:--------:|:--------:|:-------------:|
| 任何级高血压 48% | ✅ | ❌ | ✅ **47.9%** (123/257) |
| ≥3 级高血压 28% | ✅ | ✅ **28%** (71/257) | ❌ |
| 任何级蛋白尿 20% | ✅ | ❌ | ✅ **21%** (54/257, "Protein urine present") |
| ≥3 级蛋白尿 5% | ✅ | ❌ | ✅ **5.7%** (NCT SAE 估算) |
| OS 8.7 月 | ✅ | ✅ | ✅ |

**关键洞察**: NCT 报 any-grade, Abstract 报 grade ≥3, **数据粒度互补**.

## 触发条件 (4 选 1)

```go
// 算法 (3 步串联验证)
func ShouldTriggerFallback(l0Verified bool, doi string, userHintsDualSource bool) bool {
    if userHintsDualSource { return true }                          // (a) 用户明确要求
    if !l0Verified && isPaywallDOI(doi) { return true }             // (b) L0 失败 + 付费墙
    if pdfType == PDFTypeChromeScreenshot && fallbackProvided { return true }  // (c) Chrome 截图
    if strategy == "abstract_as_main" { return true }               // (d) 策略推荐
    return false
}
```

`isPaywallDOI` 关键词: `10.1016/` (Elsevier), `10.1056/` (NEJM), `10.1002/` (Wiley), `10.1159/` (Karger).

## manifest schema

```json
{
  "pn_x": "P30-1",
  "main_pdf": "P30-1/P30-1_main.pdf",
  "fallback_pdfs": ["P30-1/P30-1_fallback_NCT.pdf"],
  "fallback_triggered": true,
  "fallback_trigger_reason": "双源互补: NCT=NCT02329860 提供 any-grade AE 表",
  "evidence_sources": {
    "main": {
      "source": "ScienceDirect abstract",
      "doi": "10.1016/S2468-1253(21)00109-6",
      "data_provided": ["28% grade≥3 高血压", "OS 8.7 月"],
      "limit": "only abstract, no any-grade AE table"
    },
    "fallback": {
      "source": "NCT02329860 ClinicalTrials.gov",
      "data_provided": ["47.9% 高血压 any-grade", "21% 蛋白尿 any-grade"],
      "limit": "ClinicalTrials.gov aggregation, not original paper Table 3"
    }
  },
  "highlight_summary": {
    "main_pdf_hits": 4,
    "fallback_pdf_hits": 40,
    "fallback_pages_highlighted": [2, 3, 4],
    "total": 44
  }
}
```

## 双源 highlight 标注铁律

| 来源 | 标注内容 | 触发关键词 |
|------|---------|-----------|
| **main** | DOI / 标题 / 期刊 / 关键 OS / grade≥3 数据 | 黄色下划线 RGB(1, 0.92, 0) width=2.5 |
| **fallback** | 任何 grade AE 表 / 完整数据 | 同样黄色下划线, 标在 NCT 表的对应行 |

**绝不允许**:
- ❌ main 高亮图覆盖 fallback 内容
- ❌ fallback 高亮图覆盖 main 内容
- ❌ 合并成 1 张图
- ❌ 叠加任何文字说明

## 实现位置 (已落地)

```
via54Medit/
├── internal/anno2ppt/
│   ├── dual_source.go (200 行)  — 触发逻辑 + manifest schema
│   └── dual_source_test.go (9 案例 PASS)
├── cmd/medit/commands/anno2ppt.go
│   └── dual-source 子命令: medit anno2ppt dual-source P30-1 main.pdf --fallback fb.pdf --doi ...
└── scripts/process_pn_x.py (175 行) — 端到端触发判断
```

## NCT 已知映射 (2026-08-01)

| DOI | NCT 试验号 | 论文 |
|-----|-----------|------|
| `10.1016/S2468-1253(21)00109-6` | NCT02329860 | AHELP (Apatinib vs Placebo, 2nd line HCC) |
| `10.1016/S1470-2045(23)00469-2` | NCT03713593 | LEAP-002 (Lenvatinib + Pembrolizumab) |
| `10.1056/NEJMoa2024020` | NCT03298451 | HIMALAYA (STRIDE vs Sorafenib) |

可在 `dual_source.go::FindNCTRegistry` 扩展, 新增映射时直接加一行.

## 实战 SOP (4 步)

```bash
# 1. 找 main (ScienceDirect abstract 页面)
curl -sL -o /tmp/sd_abstract.pdf "https://www.sciencedirect.com/.../<id>"

# 2. 拉 NCT 完整数据
curl -sL "https://clinicaltrials.gov/api/v2/studies/NCT02329860?format=json" -o /tmp/nct.json
# 生成 fallback PDF (脚本: scripts/nct_fetcher.py 生成 NCT AE 表)

# 3. 退回旧 Chrome 截图
mv P30-1/P30-1_main_*.pdf P30-1/_v39_deprecated/P30-1_main_v39_chrome.pdf

# 4. 复制双源 + 标注 highlight + manifest
cp /tmp/sd_abstract.pdf P30-1/P30-1_main_Qin_AHELP_LancetGastro_2021.pdf
cp /tmp/nct_ahelp.pdf P30-1/P30-1_fallback_NCT02329860_ClinTrials.pdf

# 5. (可选) 跑端到端验证
python3.11 scripts/process_pn_x.py P30-1 P30-1/P30-1_main.pdf --doi <doi> --fallback P30-1/P30-1_fallback_NCT.pdf
```

## 关键经验

1. **绝不合成 1 个 PDF** — 用户硬规则, 不容妥协
2. **NCT 与 Abstract 粒度互补** — 不是冗余
3. **manifest 详细标注 evidence_sources** — 后续算法必须能读
4. **highlight 必须 2 张图 (main + fallback)** — 缺一不可
5. **NCT 已知映射写到 dual_source.go** — 新增论文加一行
