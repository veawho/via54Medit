# via54Medit 多项目对比报告 (TMA vs 雷管方案)

生成时间: 2026-08-11T05:54:24.955975

## 项目概览

| 项目 | 磁盘 (MB) | PDF | PPTX | JPG | CSV | Pn-x 目录 (nested) | 高亮 PDF |

|------|------------|-----|------|-----|-----|-------------------|----------|

| 雷管方案 (uHCC/HCC 三重获益 PPT) | 4800.6 | 1385 | 7 | 6345 | 35 | 1076 | 1 |

| TMA (临床路径诊断与鉴别 PPT) | 2389.8 | 897 | 4 | 3185 | 9 | 107 | 465 |


## 目录结构对比


| 项目 | PPT 目录 | 下载目录 | Highlight 目录 | 步 5 | 步 6 |

|------|----------|----------|----------------|------|------|

| 雷管方案 (uHCC/HCC 三重获益  | step1_ppt_目录/ | step3_pdf下载_160目录/ | step4_highlight_96目录_合并DOI/ | step5_三方对齐/  ← 刚生成 | step6_打包归档/ |

| TMA (临床路径诊断与鉴别 PPT) | _1_ppt/ | _2_pdfs/  (flat 约定, Pn-x_main.pdf) | _3_highlight/  (flat, Pn-x_highlight.pdf) | _step5_三方对齐/  ← 刚生成 | (无) |


## 6 步规则校验


| 项目 | Step 1 | 1b | 2 | 3 | 4 | 5 | 6 | 总分 |

|------|--------|-----|---|----|----|----|-----|------|

| 雷管方案 (uHCC/HCC 三重获益 PPT) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 7/7 |

| TMA (临床路径诊断与鉴别 PPT) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 7/7 |


## CSV 格式对比


| 项目 | CSV 文件 | 列数 | 列定义 |

|------|----------|------|--------|

| 雷管方案 | step2/PPT_citations_8col_aligned.csv | 12 | A_slide/B_mark/C_citation/D_ppt_visual/E_DOI/F_download_url/G_actual_pdf/H_highlight_status/I_alignment_A_B/J_alignment_C_PDF/K_alignment_D_HL/L_merged_dir |

| 雷管方案 | step2/PPT_citations_4col.csv | 4 | A_slide/B_mark/C_citation/D_visual_text_analysis |

| TMA | _citation_table/tma_citation_table.csv | 4 | A_slide/B_mark/C_citation/D_ppt_content |

| AGENTS.md 标准 (Rule 12) | - | 8 | PPT页/第几条/引用语义/PPT引文完整字段/DOI/类型/对应PDF文件/来源链接 |


## Highlight 状态对比


| 项目 | 算法 | 高亮位置 | 颜色持久 | 黄色像素 (健康检查) | 阈值通过率 |

|------|------|----------|----------|----------------------|------------|

| 雷管方案 step4 | v9.7 fill 模式 | ⚠️ 标错位置 (header/author) | ✓ 直接画 PNG | 0.1-0.8% (旧) | 99% |

| TMA _3_highlight (旧) | v9.7 add_highlight_annot | ⚠️ 标错位置 + annotation 颜色丢失 | ❌ 丢失 | 0-8% (差异大) | 48% |

| TMA _3_highlight_v10 (新) | v10.1 line 模式 | ✓ 文字下方 (正) | ✓ 走内容流 | 0.003-0.087% (line 模式) | 80% (剩 20% 是 wrong paper) |


## 主要差异 + 建议


### 1. 目录命名约定

- 雷管方案: `step{N}_xxx` (工作流步骤)

- TMA: `_N_xxx` (内容类型)

- **建议**: 选一种做标准, 推荐 `_1_ppt` / `_2_pdfs` / `_3_highlight` (更紧凑)


### 2. PDF 存储约定

- 雷管方案: **nested** (`step3/Pn-x/main.pdf`)

- TMA: **flat** (`_2_pdfs/Pn-x_main.pdf`)

- **建议**: 统一为 nested, 便于扩展 (main + fb + supplementary)


### 3. CSV 列数

- 雷管方案: 12 列 (含 alignment tracking + merged_dir)

- TMA: 4 列 (最简, 缺 H 列)

- **建议**: 统一为 AGENTS.md 8 列标准 (冻结表头, 飞书 + CSV 同步)


### 4. Highlight 算法

- 雷管方案 step4: v9.7 fill 模式, 标错位置但可见

- TMA _3_highlight (旧): v9.7 add_highlight_annot, annotation 颜色丢失

- **建议**: 全部迁移到 v10.1 line 模式 (符合 6 步规则, 跳 header/author)


### 5. Step 5 三方对齐

- 雷管方案: **已完成** (本会话生成)

- TMA: **已完成** (本会话生成)

- **建议**: 加到 CI gate, 每次 commit 前跑


### 6. 自动化缺口 (两项目共有)

- ❌ PPT 扩页工具 (需 python-pptx)

- ❌ PPT 视觉分析自动化 (需 ppt_understand + 写 _vision_report.json)

- ❌ L0 论文匹配 (错论文问题, 上游)

- ❌ L4 关键词抽取 (通用词问题, 上游)


## 下一步建议


1. **统一目录命名**: 选定 `_1_ppt` / `_2_pdfs` / `_3_highlight` 为标准

2. **统一 CSV 为 8 列标准** (AGENTS.md Rule 12)

3. **迁移雷管方案 step4 到 v10.1** (用 `via54_highlight_fix_v10.process_pn_x`)

4. **CI 集成 `via54_rules.py check`** (每次 PR 跑 6 步校验)

5. **修 PPT 扩页工具** (python-pptx 30 行)

6. **修 L0/L4 算法** (根治错论文 + 错关键词)

