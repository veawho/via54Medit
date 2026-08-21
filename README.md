# via54Medit v4.0 — Multi-Source Medical Literature Router

> Algorithm-driven Pn-x processor with 6-layer architecture for PPT citation verification.

## v4.0 状态 (2026-08-01)

| 层 | 技术 | 状态 | 证据 |
|---|------|:----:|------|
| **L0** PDF 真实性 | PyMuPDF + Crossref | ✅ | `internal/anno2ppt/l0_verify.go` (9 案例 PASS) |
| **L0+** 分类器 | Producer 黑白名单 | ✅ | `l0_producer_classifier.go` (9 案例 PASS) |
| **L1** 文字加速 | PyMuPDF | ✅ | 内置 |
| **L2** OCR 中文 | PaddleOCR 3.7+ | ✅ | `scripts/paddleocr_pdf_page.py` |
| **L3** 视觉理解 | sensenova-6.7-flash-lite | ✅ | `scripts/sensenova_vision.py` (实测 P3-1/P29-1) |
| **L4** 应证推理 | 4 维要素 + 集合结论 | ✅ | `internal/anno2ppt/algorithm.go` (9 案例 PASS) |
| **L5** 双源架构 | main + fallback | ✅ | `dual_source.go` (9 案例 PASS) |
| **L6** 经验沉淀 | 自动 callback | ✅ | `scripts/process_pn_x_learnings.py` |

## CLI 入口

```bash
# 编译
cd /Users/david/Desktop/developments/via54Medit
go build -o /tmp/medit ./cmd/medit/

# Phase 7 应证推理
medit anno2ppt parse "中国肝癌5年生存率仅14.4%, 远低于其他癌种"        # 4 维要素抽取
medit anno2ppt confirm "..." /path/to/rows.json                       # 应证推理
medit anno2ppt ocr paper.pdf 3                                         # PaddleOCR 第 3 页
medit anno2ppt l0verify paper.pdf 10.1016/...                         # L0 PDF 真实性
medit anno2ppt classify paper.pdf                                      # L0+ PDF 分类
medit anno2ppt dual-source P30-1 main.pdf --fallback fb.pdf --doi ...  # 双源 manifest

# Phase 5 HLO (Hermes Literature Orchestrator)
medit hlo ask "处理 P5-7"
medit hlo audit
medit hlo truth P5-7
medit hlo corr 5-7 d "Qin S" "Meyer T"

# Phase 6 Feishu 集成
medit feishu verify
medit feishu push --dry-run
medit citation match <ref> <pdf>
medit citation replayer

# medplan 医学策划 (2026-08-21)
medit medplan run --instruction "为 DrugX 上市撰写三档医学传播策略" \
  --name DrugX --indication "2型糖尿病" --rx-status rx     # 调研→提炼→三档大纲→合规
medit medplan optimize <项目> --audience hcp --instruction "扩充县域市场"
medit medplan compliance <项目> --audience all             # 中国大陆医学合规验证
```

## 完整流程 (Python 入口)

```bash
# 端到端: L0 分类 + L0 验证 + 双源 + 经验沉淀
python3.11 /Users/david/Desktop/developments/via54Medit/scripts/process_pn_x.py \
  P30-1 /path/to/main.pdf \
  --doi "10.1016/S2468-1253(21)00109-6" \
  --fallback /path/to/fallback_NCT.pdf

# 输出: JSON report (L0_classify / L0_verify / dual_source / persist_learnings)
```

## 18 个 Pn-x 截图包壳修复实战 (2026-08-01)

| 批次 | Pn-x | 修复方式 |
|:----:|------|---------|
| **P0 已修** | P12-1, P22-1, P24-3, P33-1, P43-1, P5-17 | ESMO #1494P (Sangro) |
| **P0 已修** | P3-1 | Kudo HBSN 2022 Editorial |
| **P0 已修** | P29-1, P33-11, P41-10 | Song YG Liver Cancer 2024 |
| **P1 已修** | P28-2, P33-5, P43-8 | Kuwano Anticancer Res 2025 |
| **P1 已修** | P5-13 | Chen Y ASCO 2022 abstract |
| **P1 已修** | P24-6, P30-8, P41-12 | Llovet LEAP-002 (UCL AAM) |
| **P1 已修** | **P30-1** | **双源: ScienceDirect abstract + NCT02329860** |

**18/18 全部修复**

## 双源架构 (Dual Source Architecture)

针对 Elsevier/Wiley/Karger 付费墙无法下载全文的场景：

```
P30-1/
├── P30-1_main_Qin_AHELP_LancetGastro_2021.pdf    (ScienceDirect abstract)
├── P30-1_fallback_NCT02329860_ClinTrials.pdf     (NCT 完整 AE 表)
├── _v39_deprecated/P30-1_main_v39_chrome.pdf     (旧 Chrome 截图)
└── manifest.json
```

### 数据互补对照

| 数据项 | PPT 需求 | main 提供 | fallback 提供 |
|--------|:--------:|:--------:|:-------------:|
| 任何级高血压 48% | ✅ | ❌ | ✅ 47.9% (NCT) |
| ≥3 级高血压 28% | ✅ | ✅ 28% (Abstract) | ❌ |
| 任何级蛋白尿 20% | ✅ | ❌ | ✅ 21% (NCT) |
| ≥3 级蛋白尿 5% | ✅ | ❌ | ✅ 5.7% (NCT SAE) |

## 测试

```bash
cd /Users/david/Desktop/developments/via54Medit
go test ./...                     # 全部 Go 测试
go test ./internal/anno2ppt -v    # Phase 7 详细
```

## 关键 Skills (沉淀到 ~/.hermes/skills)

- `via54medit-anno2ppt-phase7` — L4 核心算法 + sensenova 集成
- `via54medit-anno2ppt-pitfalls-2026-08` — 26 个实战 pitfall + transcript
- `via54medit-architecture-honest-status` — 4 层架构 + 诚实声明
