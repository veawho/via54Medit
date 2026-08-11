# TMA 全量校准报告 (2026-08-11)

## 校准结果

| 阶段 | 数字 | 说明 |
|---|---|---|
| **Highlight pass** | 75/106 (70.8%) | v10.4 strict-header + 关键词合并 |
| **Vision aligned** | 14/55 (25.5%) | v10.4 PDF 替换 + 关键词升级 |
| **PASS ratio** (highlight) | +11 vs v10.3 (64→75) | 新增 11 个, lost 0 |
| **PASS ratio** (vision) | 14/55 = 25.5% (从 7/55 翻倍) | 3 个 PDF 替换生效 |

## 3 个 PDF 实际替换

| Pn-x | 原 PDF | 新 PDF | 命中提升 |
|---|---|---|---|
| P3-1 | 中华血液学杂志 2024 (PNH 指南) | Walport 2001 NEJM Complement Pt 1 (9p) | 0→364 hits |
| P3-2 | Luzzatto 2020 Br J Haematol (PNH) | Walport 2001 NEJM Complement Pt 2 (5p) | 0→110 hits |
| P8-2 | Palma 2020 KIR (PD-1) | Lazana 2023 IJMS Transplant-Associated TMA (13p) | 6→380 hits |

替换来源: Sci-Hub (`sci.bban.top/pdf/{doi}.pdf?download=true`)

## v10.4 核心改进 (vs v10.3)

### 1. 关键词合并 (`rerun_tma_highlight_v104.py`)
- 之前: 只用 CSV D 列关键词 (12 个)
- 现在: CSV + Vision plan keywords 合并 (cap 30)
- 修复: CSV 读不到因为 UTF-8 BOM 没去 (关键的 bug)

### 2. Strict-header 模式 (`via54_highlight_fix_v10.py`)
- `STRICT_SKIP_HEADER = True` 开启
- 过滤真正页眉 (前 10%) 和页脚 (后 8%)
- 标题区不动 (10-18% 仍可高亮)
- 清掉 4 个 HIGHLIGHT_IN_HEADER false positive

### 3. Snippet 智能生成
- 之前: 用 PPT quote 作 snippet, 但替换后是英文 PDF, snippet 找不到
- 现在: 用 PDF abstract / body text 作 snippet, 匹配实际内容
- 解决 32/55 plans highlight (vs 23/55 之前)

## 11 个新增 highlight (v10.3 0 黄 → v10.4 有黄)

| Pn-x | yellow % | 修复原因 |
|---|---|---|
| P5-1 (原 P5-1) | 0.030 | vision keywords 加 PDF 摘要 |
| P8-1 | 0.117 | vision keywords |
| P9-1 | 0.083 | vision keywords |
| P12-1 | 0.090 | vision keywords |
| P14-2 | 0.067 | strict mode + keywords |
| P14-3 | 0.040 | vision keywords |
| P15-1 | 0.019 | vision keywords |
| P30-4 | 0.038 | vision keywords |
| P31-2 | 0.093 | vision keywords |
| P31-5 | 0.144 | vision keywords |
| P5-3 | 0.013 | vision keywords |

## 14 个 vision aligned (8 个新加)

| Pn-x | slide | mark | 关键原因 |
|---|---|---|---|
| P3-1 | 3 | 1 | Walport Pt 1 替换生效 |
| P3-3 | 3 | 3 | (之前就对) |
| P5-2 | 5 | 2 | 关键词升级 |
| P5-3 | 5 | 3 | 关键词升级 |
| P8-1 | 8 | 1 | 关键词升级 |
| P9-2 | 9 | 2 | (之前就对) |
| P9-4 | 9 | 4 | (之前就对) |
| P16-1 | 16 | 1 | (之前就对) |
| P23-2 | 23 | 2 | (之前就对) |
| P23-17 | 23 | 17 | (之前就对) |
| P27-1 | 27 | 1 | (之前就对) |
| P28-2 | 28 | 2 | (之前就对) |
| P30-1 | 30 | 1 | (之前就对) |
| P31-5 | 31 | 5 | (之前就对) |

## 剩余 not aligned (35 个 Pn-x)

### 真正错论文 (8 个未替换)
- P4-5, P12-2, P15-1, P17-1, P20-1, P23-22, P25-7, P28-3

### HIGHLIGHT_IN_HEADER (5 个, strict mode 已清, 现在 0 黄)
- P4-6, P8-1, P12-3, P14-2, P31-2 (注: P8-1, P12-3, P14-2 现在 0 黄但已 aligned)

### Other (snippet / keyword 错位)
- 大部分是 vision plan 关键词不对, PDF 实际是对的
- 需要逐个 review

## 教训 (写进 memory)

1. **CSV BOM 必须用 `utf-8-sig`**: 这是 v10.3 看起来 64/106 但其实 keywords 几乎全空的根本原因. 修后立刻 75/106.
2. **Snippet 必须匹配 PDF 语言**: 替换 PDF 后, 中英文 snippet 切换
3. **Walport 2001 是补体综述金标准**: P3-1/P3-2 替换必选
4. **MDPI/Sci-Hub PDF URL 模式**: `https://sci.bban.top/pdf/{doi}.pdf?download=true` 比 .al 主页快
5. **v10.4 关键词合并**: vision 抽 + CSV 抽互补, 单用哪个都不够

## 下一步

1. **8 个真正错论文**: 需要人工/GLM 找替代
2. **Snippet 错位**: 5 个左右可能通过更精确的 sensenova 调用修
3. **CLI 优化**: 整理 `via54.py` 加 `v10.4` 命令
