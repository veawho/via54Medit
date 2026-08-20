# TMA 文献 Highlight 流水线 (2026-08-20 交付)

> 项目数据: `C:\Users\via54\Desktop\TMA_test\` (PPT: `TMA临床路径的诊断与鉴别.pptx`, 33 页, 89 个引用标号 S3_1..S31_6)

## 流水线 (按 6 步 SOP 的第 3-6 步)

| 步骤 | 脚本 | 说明 |
|---|---|---|
| Step 3 下载 | `scripts/tma_cascade_download.py` | 多级 OA 级联: OpenAlex → Unpaywall → EuropePMC → NCBI PMC → doi.org (已知 DOI) |
| Step 3 恢复 | `scripts/tma_download_round2.py` | CrossRef 重解析 DOI + 首页内容三维核验 (期刊全词+年份+作者) + Sci-Hub 兜底 (`tma_scihub.py`) |
| Step 3 核验 | `scripts/tma_verify_pdfs.py` | 逐 PDF 首页文本 vs 引文: 期刊/年份/作者匹配, 输出 ok/suspicious/mismatch |
| Step 4 高亮 | `scripts/tma_batch_highlight.py` | 每 Pn-x 用其所在 slide 视觉定位 → `via54_ppt_visual_to_pdf.py` v3 FINAL rect 模式 (9 铁律), 嵌套目录 `_highlight_nested/` |
| Step 5 验证 | `scripts/tma_verify_highlights.py` | annot 数 / 黄色像素 / 图片完整性 / pages 子目录 |
| Step 6 打包 | `scripts/tma_package.py` + `tma_final_report.py` + `tma_manual_list.py` | 89 行 8 列 CSV + 交付报告 md + 人工下载清单 |

## 用法 (路径可经环境变量覆盖)

```bash
# 默认指向 C:\Users\via54\Desktop\TMA_test, 可用 TMA_PROJECT 覆盖项目根
export TMA_PROJECT=/path/to/project        # Windows: set TMA_PROJECT=...
python scripts/tma_cascade_download.py --limit 5      # 试跑 5 个
python scripts/tma_download_round2.py                 # 缺失文献恢复下载
python scripts/tma_verify_pdfs.py                     # 下载后内容核验
python scripts/tma_batch_highlight.py                 # 全量 highlight (每 Pn-x 用其 slide)
python scripts/tma_verify_highlights.py               # highlight 质量验证
python scripts/tma_final_report.py                    # 交付报告 + 8 列 CSV
python scripts/tma_manual_list.py                     # 人工下载清单
```

`tma_batch_highlight.py` 额外支持: `TMA_PYTHON` / `TMA_SCRIPT` / `TMA_PPTX` / `TMA_PDF_DIR` / `TMA_OUT_BASE`。

## 交付统计 (2026-08-20)

- 引用 89 个; **52 个有 PDF + highlight (58%)**; 37 个付费墙/中文期刊 → `_人工下载清单.md` (含 DOI/PubMed/万方/知网链接)
- highlight 58 个嵌套目录全部 OK (annot > 0, 图片完整), 唯一轻微标记: S23_23 p9 单条稀疏高亮 (黄色像素 0.002%)
- 下载按用户要求 1 小时截止, 不再自动重试
- 错配下载已隔离到项目 `_2_pdfs_wrong/` (24 篇)

## 关键修复 (本轮)

1. DOI 表 3 处错误: S9_1 (PM ID 冒充 DOI) / S11_6 (10.1242/jeb.013219 错配) / S31_1 (10.2215/CJN.04950610 非目标) → CrossRef 重解析
2. zip 孤儿 PDF 复用: Pn-S17_2 (Zheng JTH 2020) → S18_1; Pn-S22_1 (Laurence 2016 增刊) → S8_1
3. S20_2 手动 MDPI 直链 (mdpi-res.com), S31_2 Frontiers 直链 (fphar.2025.1538563)
4. 下载器 stdout GBK 崩溃修复 (sys.stdout.reconfigure utf-8)
5. 内容核验门收紧: 期刊缩写展开表 (N Engl J Med→new england journal of medicine 等 40+) + 整词匹配 + 三维评分
