# via54Medit 文献全自动管线 (任何设备部署即用)

> 自然语言一句话: **"帮我识别 X.pptx 中的文献引用，下载文献，并进行highlight"**
> → 自动完成: 渲染PPT图 → 提取引用字段 → 限时下载PDF → 整理Pn-x目录 → 逐slide高亮分析+plan → 按序highlight → 交付报告

## 一、部署 (新系统自动接入)

```bash
git clone <via54Medit> && cd via54Medit/scripts
# 环境自检 + 自动安装依赖 (PyMuPDF/python-pptx/Pillow/pywin32[仅Win])
python deps_auto.py
```

- **PPT → 图片**: 自动接入系统 PowerPoint COM (ProgID `PowerPoint.Application`) / WPS 演示 (`KWPP.Application`), 都没有则 python-pptx 兜底
- **下载**: 自动接入 OpenAlex/Unpaywall/EuropePMC/NCBI PMC/CrossRef/Sci-Hub 多级级联
- 任一依赖/引擎缺失自动尝试安装, 失败降级不中断

## 二、自然语言一键全自动

```bash
python via54.py auto "帮我识别 D:/文献/某方案.pptx 中的文献引用，下载文献，并进行highlight"
# 或指定参数
python via54.py auto --ppt X.pptx --download --highlight --budget 3600
python via54_auto.py "识别 X.pptx 引用并下载高亮" --project-dir D:/out
```

**流程**:
| 步骤 | 内容 | 产物 |
|---|---|---|
| [0] | 环境自检+自动安装 | — |
| [1] | 渲染全部 slide 图 (自动接 PowerPoint/WPS) | `_ppt_renders/slide_NNN.png` |
| [2] | 提取文献引用 (上标/中文+数字标号 + 参考文献列表页) | `_refs.json` + `_references_full.json` (完整引文) |
| [3] | 下载 PDF (**1 小时硬限**; 超时剩余保留访问链接到表格提示人工) | `_2_pdfs/P3-1.pdf` + `_download_auto_report.json` |
| [4] | 整理下载目录 | `_literature_citation_index/P3-1/P3-1_main.pdf` |
| [5] | 逐 slide 视觉分析 → highlight plan | `_highlight_plans/slide_003_plan.json` |
| [6] | 按 slide 顺序完成 highlight (文字/表格/图表/图片四类应证) | `_highlight_nested/P3-1/` |
| [7] | 交付报告 | 8列 CSV + 交付报告 + 人工下载清单 |

**目录结构** (下载目录 / highlight 目录):
```
<project>/
├── _ppt_renders/                          # slide 图片
├── _literature_citation_index/            # 下载目录: Pn-x 子目录 + Pn-x 前缀 PDF
│   └── P3-1/P3-1_main.pdf
├── _highlight_plans/                      # highlight plan
│   └── slide_003_plan.json
├── _highlight_nested/                     # highlight 目录: Pn-x 子目录
│   └── P3-1/
│       ├── P3-1_main.pdf                  # 文献 PDF
│       ├── P3-1_highlight.pdf             # 高亮 PDF
│       ├── P3-1_highlight_pages/         # 导出图片目录 (全部页)
│       └── P3-1_highlight_p1.png         # 有 highlight 的图片
└── _citations_8col.csv                   # 8 列表 (H 列含访问链接)
```

**下载时间限制**: `--budget <秒>` (默认 3600 = 1 小时)。预算内逐条下载+内容核验 (期刊/年份/作者), 超时停止; 未下载成功的保留 DOI/PubMed/万方/知网链接在表格 H 列并写入 `_人工下载清单.md`, 提示用户手动下载后放入 `_2_pdfs/P3-1.pdf` 重跑即可。

## 三、TMA 案例交付 (2026-08-20)


> **Pn-x 命名规范**: Pn = PPT 的 slide 页码 (即 P{页码}), x = 该 slide 中第几条引用。
> 正确格式: P3-1 = PPT 第 3 页 (slide 3) 的第 1 条引用; P23-5 = 第 23 页第 5 条引用。
> ⚠️ 错误命名 Pn-S3_1 已废弃: 所有文件/目录/代码均归一为 P3-1 格式。
> highlight 时每个 Pn-x 用其所在 slide 的视觉内容定位应证段。
> 项目数据: `C:\Users\via54\Desktop\TMA_test\` (PPT: `TMA临床路径的诊断与鉴别.pptx`, 33 页, 89 个引用标号 S3_1..S31_6)

## 流水线 (按 6 步 SOP 的第 3-6 步)

| 步骤 | 脚本 | 说明 |
|---|---|---|
| Step 3 下载 | `scripts/tma_cascade_download.py` | 多级 OA 级联: OpenAlex → Unpaywall → EuropePMC → NCBI PMC → doi.org (已知 DOI) |
| Step 3 恢复 | `scripts/tma_download_round2.py` | CrossRef 重解析 DOI + 首页内容三维核验 (期刊全词+年份+作者) + Sci-Hub 兜底 (`tma_scihub.py`) |
| Step 3 核验 | `scripts/tma_verify_pdfs.py` | 逐 PDF 首页文本 vs 引文: 期刊/年份/作者匹配, 输出 ok/suspicious/mismatch |
| Step 4 高亮 | `scripts/tma_highlight_by_slide.py` | **按 slide 分组驱动 (推荐)**: ①`ppt_render_engine.py` 自动接入系统 PowerPoint/WPS COM 导出全部 slide 图 `_ppt_renders/` ②逐页视觉提取 (文本/表格/图片形状) ③对照该页所有 PDF ④**文字段落 + 表格 (find_tables) + 图表/图片 (get_image_info) 四类应证 highlight** (v3 FINAL rect + 9 铁律, 嵌套目录) |
| Step 4 高亮 (legacy) | `scripts/tma_batch_highlight.py` | 旧文字-only 模式 (历史参考; `via54.py hl-batch --legacy`) |
| Step 5 验证 | `scripts/tma_verify_highlights.py` | annot 数 / 黄色像素 / 图片完整性 / pages 子目录 |
| Step 6 打包 | `scripts/tma_package.py` + `tma_final_report.py` + `tma_manual_list.py` | 89 行 8 列 CSV + 交付报告 md + 人工下载清单 |

## 用法 (路径可经环境变量覆盖)

```bash
# 默认指向 C:\Users\via54\Desktop\TMA_test, 可用 TMA_PROJECT 覆盖项目根
export TMA_PROJECT=/path/to/project        # Windows: set TMA_PROJECT=...
python scripts/tma_cascade_download.py --limit 5      # 试跑 5 个
python scripts/tma_download_round2.py                 # 缺失文献恢复下载
python scripts/tma_verify_pdfs.py                     # 下载后内容核验
python scripts/tma_highlight_by_slide.py              # 全量 highlight (按 slide 分组, 文字+表格+图表/图片)
python scripts/tma_batch_highlight.py --legacy           # 旧文字-only 模式 (历史)
python scripts/tma_verify_highlights.py               # highlight 质量验证
python scripts/tma_final_report.py                    # 交付报告 + 8 列 CSV
python scripts/tma_manual_list.py                     # 人工下载清单
```

`tma_batch_highlight.py` 额外支持: `TMA_PYTHON` / `TMA_SCRIPT` / `TMA_PPTX` / `TMA_PDF_DIR` / `TMA_OUT_BASE`。

## PPT → 图片渲染引擎 (部署新系统自动接入)

`scripts/ppt_render_engine.py` 按优先级自动选择可用引擎:

| 优先级 | 引擎 | 条件 | 保真度 |
|---|---|---|---|
| 1 | Microsoft PowerPoint COM | Windows + 安装了 MS Office (ProgID `PowerPoint.Application`) | 真实渲染 (推荐) |
| 2 | WPS 演示 COM | Windows + 安装了 WPS (ProgID `KWPP.Application`, 接口兼容) | 真实渲染 |
| 3 | python-pptx + Pillow 近似渲染 | 兜底 (任何平台) | 近似 (仅文本/表格/图片形状) |

- 检测到系统有 PowerPoint/WPS 但 venv 缺 pywin32 时, 自动 `pip install pywin32` (仅 Windows)
- COM 用 `DispatchEx` (强制新实例, 避免 Dispatch 对 PowerPoint 的连接残留问题)
- 任何引擎失败自动降级下一级, 全程不中断
- 单测: `test_tma_pipeline.py` T12 (引擎探测 / COM 失败降级 / 兜底渲染)

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
