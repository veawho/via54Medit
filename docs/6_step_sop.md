# 6 步文献整理 SOP (2026-08-10 用户版, 2026-08-14 v3 FINAL 对齐)

> 任何 PPT + 文献场景（医药/学术/商业）, 按这 6 步走, 输出合规的 `_3_highlight_v10/` 目录 + 8 列标准 CSV + 三方对齐报告。
>
> **本文件是执行手册**, 规则文本定义在 `scripts/via54_rules.py` 的 `RULES_TEXT` 里, 校验工具是 `python3 scripts/via54_rules.py check <project_dir>`。
>
> **⚠️ 2026-08-14 v3 FINAL 对齐(重要变更)**:
> - **Step 4 新标准 = v3 FINAL rect 模式**(`scripts/hl_v3_final/hl_lib.py`, opacity 0.45, RGB 255,217,0, 逐行精确 rect);
>   v10.1 line 细线模式降级为历史参考。完整规范: `docs/HIGHLIGHT机制与算法规范_v3_FINAL.md`
> - **Step 6 合并格式变更**: `Pn1-x1Pn2-x2`(无下划线) → **`P3-1_P4-1`**(下划线按序连接);
>   合并判定 = 引用文本指向同一文献(不能只看 MD5)。详见 `docs/8列标准与合并规则_2026-08-14.md`
> - **Step 3 新下载链**: `scripts/hl_v3_final/step3_download.py`(CrossRef/OpenAlex/Unpaywall/S2 四级降级, TMA 实测 90-95% 成功率)
> - 新 PPT 三步流程: `scripts/hl_v3_final/step1_export_slides.py` → `step2_extract_refs.py` → `step3_download.py`

---

## 0. 前置条件

### 0.1 环境

| 工具 | 用途 |
|---|---|
| Python 3.11+ (Hermes venv: `~/.hermes/hermes-agent/venv/bin/python3.11`) | 跑所有 v10 脚本 |
| python-pptx | PPT 扩页 (`ppt_expand.py`) |
| PyMuPDF (`fitz`) | PDF 文字/坐标/渲染 |
| LibreOffice (可选) | PPT 渲染 jpg, 没装也能跑 (只是 Step 2 没法生成预览图) |
| GLM API key (`~/.hermes/.env` 的 `GLM_API_KEY=...`) | v10.2 GLM 兜底增强 (推荐) |

### 0.2 项目结构约定 (两种都支持)

```
# 约定 A: nested (推荐, 雷管方案用)
<project_dir>/
├── step1_ppt_目录/                  # 或 _1_ppt/
│   ├── 原版.pptx
│   ├── 原版_expanded.pptx           # 扩页后
│   └── _ppt_renders/slide_NNN.jpg   # 导出图
├── step3_pdf下载_160目录/           # 或 _2_pdfs/
│   ├── P11-1/main.pdf
│   ├── P11-1/page_001.jpg
│   └── P11-2/main.pdf
└── step4_highlight_v10/             # 或 _3_highlight/
    ├── P11-1/main.pdf               # highlight 后
    ├── P11-1/page_001.jpg
    └── P11-2/main.pdf

# 约定 B: flat (TMA 用)
<project_dir>/
├── TMA临床路径的诊断与鉴别.pptx     # 顶层
├── _ppt_renders/                    # 顶层
├── _2_pdfs/
│   ├── P11-1_main.pdf               # flat 命名
│   └── P11-2_main.pdf
└── _3_highlight_v10/
    ├── P11-1_highlight.pdf
    └── P11-2_highlight.pdf
```

**`via54_rules.py check` 自动识别两种约定**, 不需要手动指定。

### 0.3 8 列标准 CSV 表头 (AGENTS.md Rule 12)

```csv
A,B,C,D,E,F,G,H
PPT页,第几条,引用语义,PPT引文完整字段,DOI,类型,对应PDF文件,来源链接
5,1,"mOS 23.7月","Cheng AL, et al. Lancet 2025","10.1016/...","LITERATURE","Cheng_Lancet_2025.pdf","DOI 主链接 + PubMed + 应证推理..."
```

| 列 | 名 | 示例 |
|---|---|---|
| A | PPT页 | 5 |
| B | 第几条 | 1 (单引文) / "1,2" (多引文) |
| C | 引用语义 | "标准与讨论" / "mOS 应证" |
| D | PPT引文完整字段 | "Cheng AL, et al. Lancet 2025" |
| E | DOI | "10.1016/S0140-6736(25)00001-1" (含超链接) |
| F | 类型 | LITERATURE / DATABASE / GOVERNMENT / CONFERENCE / OTHER |
| G | 对应PDF文件 | "Cheng_Lancet_2025.pdf" (仅文件名) |
| H | 来源链接 | DOI + PubMed + Europe PMC + 应证推理 + Highlight file:// |

---

## 1. Step 1 — 建立文献整理目录

**目标**: 3 个内容齐 — PPT 目录、PDF 下载、Highlight 目录 (现在先建空壳)。

```bash
# 1.1 建 3 个目录
mkdir -p <project_dir>/step1_ppt_目录
mkdir -p <project_dir>/step3_pdf下载_160目录
mkdir -p <project_dir>/step4_highlight_v10
```

**Step 1 完成标志**: 3 个目录都存在, PPT 目录里有 `.pptx` 原版文件。

**Step 1b (PPT 扩页)**:
```bash
# 1.2 审计 PPT 看哪些页需要扩
python3 scripts/ppt_expand.py audit <input.pptx>
# 例: 雷管方案 30/43 页需扩
# 1.3 扩页 + 导出 jpg
python3 scripts/ppt_expand.py expand <input.pptx> <output_expanded.pptx> --margin-pt 20
python3 scripts/ppt_expand.py render <output_expanded.pptx> <renders_dir> --dpi 150
```

**Step 1b 完成标志**: PPT 目录同时有 `原版.pptx` + `原版_expanded.pptx` + `_ppt_renders/slide_*.jpg`。

---

## 2. Step 2 — 分析 PPT 视觉

**目标**: 提取每页的引文标号 + 视觉内容, 输出 `_vision_report.json` + 导出 jpg。

### 2.1 跑视觉分析

```bash
# 一键跑全 PPT (生成 _vision_report.json + _ppt_renders/)
python3 scripts/ppt_vision_analyze.py <project_dir> [--start 3] [--end 43] [--no-render]
# 例:
python3 scripts/ppt_vision_analyze.py /Users/david/Desktop/雷管方案_文献整理
```

**输出**:
- `<project_dir>/step1_ppt_目录/_vision_report.json` — 每页的 `citation_marks` + `tables` + `text_blocks`
- `<project_dir>/step1_ppt_目录/_ppt_renders/slide_*.jpg` — 每页 jpg (Step 1b 也用)

### 2.2 解析 citation_marks

`_vision_report.json` 的 `citation_marks` 结构:
```json
{
  "slide_5": {
    "marks": [
      {"position": "P5-左下", "label": "1", "context": "T+A方案...mOS 19.2月", "D_candidate": "Finn RS, et al. NEJM 2020 IMbrave150"},
      {"position": "P5-右下", "label": "2,3", "context": "STRIDE...mOS 16.4月", "D_candidate": "Abou-Alfa GK, et al. NEJM 2022 HIMALAYA"}
    ]
  }
}
```

### 2.3 填 CSV 前 4 列

从 `_vision_report.json` 抽出:
- A=slide, B=label, C=context, D=D_candidate (暂定, 后续可调)

**Step 2 完成标志**: `_vision_report.json` 存在 + `citation_marks` 数量 == PPT 引文总数。

---

## 3. Step 3 — 搜索并下载文献

**目标**: 按 D 列 (PPT 引文完整字段) 下载所有 PDF, 按 Pn-x 归档。

### 3.1 准备下载 (用 5 策略兜底)

```python
# scripts/via54_pdf_download.py 的 5 策略
# 1. Direct DOI redirect
# 2. PubMed Central (PMC)
# 3. Europe PMC
# 4. Google Scholar
# 5. Sci-Hub (兜底, 视情况)
```

### 3.2 L0 错论文校验 (根治"名字相近"问题)

```bash
# 3.2 校验每个下载的 PDF 是否真的是 D 列引用的那篇
python3 scripts/l0_paper_match.py verify <pdf_path> <expected_d_citation>
# 例:
python3 scripts/l0_paper_match.py verify P11-1/main.pdf "Cheng AL, et al. Lancet 2025"
# 5 维评分: 作者 / 期刊 / 年份 / 标题关键词 / DOI 后缀
# 评分 >= 0.7 才认, < 0.4 拒绝重下
```

### 3.3 L4 关键词抽取 (避免"2020/99%"通用词)

```bash
# 3.3 抽 D 列的关键词, 5 维可信度评分
python3 scripts/l4_keyword_extract.py "Cheng AL, et al. Lancet 2025. CheckMate 9DW. mOS 23.7月"
# 或 demo 看效果:
python3 scripts/l4_keyword_extract.py demo
```

### 3.4 下载并归档

```bash
# 3.4 批量下载
python3 scripts/process_all_pn_x.py <project_dir> [--use-glm]
# 或手动:
python3 scripts/via54_pdf_download.py <d_citation> --out <Pn-x_dir>
```

**下载约定**:
- **nested**: `step3_pdf下载_160目录/P11-1/main.pdf` + 同目录 `page_001.jpg` ... `page_005.jpg`
- **flat**: `_2_pdfs/P11-1_main.pdf`
- 不去重, 即使同 PDF 也要按 Pn-x 独立目录 (Step 6 合并)

**Step 3 完成标志**: D 列每个引文都有 PDF (或 PDF + 摘要), Pn-x 数量 == D 列非空数。

---

## 4. Step 4 — Highlight PDF (按 slide 顺序)

**目标**: 按 PPT 视觉分析结果, 在 PDF 中画**半透明黄色 rect** highlight 应证内容(整句/整段)。

### 4.1 算法选型

| 算法版本 | 模式 | 说明 | 推荐度 |
|---|---|---|---|
| v9.7 add_highlight_annot | fill | 矩形 annotation, 颜色经常丢 | ❌ |
| v9.7 fill | fill | 矩形填充, 位置错 | ❌ |
| v10.1 line | line | 文字下方细黄线 | 历史参考(已降级) |
| **v3 FINAL rect** | **rect** | **opacity 0.45 半透明逐行 rect, 精确对齐, 用户验收通过** | **✅ 唯一标准** |

### 4.2 跑 highlight (v3 FINAL, 2026-08-13 定稿)

```bash
# 每个 Pn-x 一个句子脚本(按 slide 视觉选整句, 禁止复制其他 Pn-x):
#   模板: scripts/hl_v3_final/examples/hl_p11-1.py (105 个示例)
# 批量重跑(幂等: 先清旧 annots 再加) + fitz 渲染 + 根目录只留高亮页
python3 scripts/hl_v3_final/rerun_all.py
python3 scripts/hl_v3_final/copy_hl_images.py
# 单元测试
/usr/bin/python3 scripts/hl_v3_final/test_hl_lib.py   # 25 passed
```

**样式唯一权威值**:
1. fill/stroke RGB(255, 217, 0) = (1.0, 0.85, 0.0)
2. opacity **0.45**(0.8 压暗文字, 禁止)
3. `add_rect_annot`(PDF Square, border 0); **禁止 `add_highlight_annot`**(自动扩展 ~3.7pt)
4. 每行一个 rect, 行高 = 行距法(下一行 y0 - 本行 y0 - 1, 最小 8pt)
5. 句首尾精确对齐 + 引用编号保护(不盖 `[1,2]`)
6. 渲染 = fitz `get_pixmap()` 零补偿; **禁止 pdftoppm**(cropbox≠0 偏移 ~8pt)和 offset 参数
7. 验证 = 直接迭代 `page.annots()`(`list(annots())` 报假损坏)

**Step 4 关键规则**:
- 高亮 = 支持 slide 的**完整句子/段落/图表说明**, 禁止关键词/单一数字
- 禁止: 标题/作者/文献信息/页眉页脚/引用编号/参考文献列表
- 同一文献的不同 Pn-x 必须按各自 slide 选句, 禁止复制 highlight
- 页面重复文本用 `(text, occurrence)` 元组消歧
- 句子被图表/双栏打断时, 选连续物理布局的子段

**Step 4 完成标志**: highlight 目录 = PPT 引用序号条数个 Pn-x 目录, 每目录 1 个 highlight PDF + 根目录仅高亮页图 + `verify.json`。

### 4.3 GLM 增强 (v10.2, 可选但推荐)

```python
# scripts/glm_integration.py 5 能力
from glm_integration import (
    verify_paper_match_with_glm,        # L0 兜底
    supplement_keywords_with_glm,        # L4 补抽
    extract_evidence_for_highlight,       # 应证段
    find_highlight_coordinates,          # 应证段→PDF 坐标
    semantic_align_step5,                # Step 5 5#3 语义对齐
)
```

GLM 默认 `glm-4-flash-250414` (免费 + 128K context)。所有函数都接受 `use_glm: bool`, 默认 False (向后兼容)。

---

## 5. Step 5 — 三方对齐 (PPT 视觉 / 表格 / PDF highlight)

**目标**: 验证 3 处一致 — PPT 标号、CSV D+E 列、PDF highlight。

### 5.1 跑三方对齐

```bash
# 5.1 跑 step5 alignment
python3 scripts/step5_alignment.py --project 雷管方案
# 或:
python3 scripts/via54.py step5 --project 雷管方案 [--use-glm]
```

**5 个子检查**:
- 5#1: PPT 标号 ↔ 下载目录 (每标号都有 PDF)
- 5#2: D+E ↔ PDF (DOI 与 PDF 一致)
- 5#3: PPT 视觉 ↔ highlight 图片 (视觉对应)
- 5#4: 表格 H 列 (应证推理段) ↔ highlight
- 5#5: 多引文 (1,2) 展开对齐

### 5.2 GLM 增强 (救回 5#3 0%)

```python
# 5#3 0% 的情况 (slide 6+ 无 docling 应证), GLM 语义对齐
# TMA 案例: 5#3 0% → 17.6% (救回 19 个 Pn-x)
# 雷管方案: 5#3 99.4% → 98.1% (微降, 因为 GLM 严格化)
python3 scripts/step5_alignment.py --project TMA --use-glm
```

**Step 5 完成标志**: 5 个子检查都 >= 95% (GLM 模式下), 或 5#1/5#2/5#4/5#5 = 100% (本地模式)。

---

## 6. Step 6 — 合并目录 + 打包

**目标**: 相同文献 (引用文本一致, 或同 DOI) 的 Pn-x 合并为 **`P3-1_P4-1`** 格式目录(下划线按序连接)。

### 6.1 合并 (2026-08-14 定稿规则)

```bash
# 合并判定: 引用文本指向同一文献 (⚠️ 不能只看 MD5: 同一文献不同下载版本 MD5 不同仍要合并)
# 新目录名: 成员 Pn-x 按数字顺序下划线连接
#   P3-1 + P4-1 → P3-1_P4-1
#   P11-2 + P12-1 + P22-2 + P25-8 → P11-2_P12-1_P22-2_P25-8
# 旧格式 Pn1-x1Pn2-x2 (无下划线) 已废弃
# TMA 全量清单 (12 组合并, 106→90 目录): docs/8列标准与合并规则_2026-08-14.md
```

**合并后结构**:
```
step4_highlight_v10/
├── P11-1/                     # 唯一文献
├── P3-1_P4-1/                 # 合并 (同文献)
│   ├── P3-1_highlight.pdf     # 各成员文件全部保留
│   ├── P4-1_highlight.pdf
│   ├── P3-1_main.pdf
│   └── P4-1_main.pdf
├── P40-10/                    # 唯一
└── P11-2_P12-1_P22-2_P25-8/   # 合并 4 个
```

**合并后检查**: 各成员 highlight.pdf / main.pdf / verify.json 齐全; 打包前全量验证 annots > 0、根目录图片页号一致; 本地表/在线表仍按 106 Pn-x 逐行(合并只影响目录)。

### 6.2 最终检查

- [ ] 原始 PPT ✓
- [ ] 扩尺寸 PPT ✓
- [ ] 扩尺寸 PPT 图片 ✓
- [ ] 下载目录 (nested: Pn-x/main.pdf) ✓
- [ ] highlight 目录 (merged: P3-1_P4-1/main.pdf, 下划线格式) ✓
- [ ] PPT-文献逐页引用表 (8 列 CSV) ✓
- [ ] 三方对齐报告 (Step 5) ✓

**Step 6 完成标志**: `via54_rules.py check` 返回 7/7 步通过 (或 6/7 + 1 known issue)。

---

## 7. 一键跑全部

```bash
# via54.py 统一入口 (v10.1)
python3 scripts/via54.py all
# 默认跑 2 个项目 (雷管方案 + TMA):
#   - rules check
#   - step5 alignment
#   - multi_project_diff
```

子命令:
```bash
python3 scripts/via54.py rules <project_dir> [--verbose]        # 6 步校验
python3 scripts/via54.py step5 --project 雷管方案 [--use-glm]    # 三方对齐
python3 scripts/via54.py highlight --project TMA --mode line      # 重跑 highlight
python3 scripts/via54.py paper-match verify <pdf> <citation>      # L0 单条
python3 scripts/via54.py keyword "<citation>" "[context]"         # L4 抽词
python3 scripts/via54.py ppt audit|expand|render <input.pptx>     # PPT 扩页
python3 scripts/via54.py glm verify|supplement|extract|align      # GLM 兜底
python3 scripts/via54.py diff                                       # 双项目对比
```

---

## 8. 自动化建议 (2026-08-10 状态)

| 项 | 工具 | 状态 |
|---|---|---|
| Step 1 目录建立 | mkdir | ✓ 100% |
| Step 1b PPT 扩页 | `ppt_expand.py` | ✓ 雷管方案 30/43 页扩, TMA 待跑 |
| Step 2 PPT 视觉 | `ppt_vision_analyze.py` | ✓ 雷管方案已跑, TMA 待跑 |
| Step 3 PDF 下载 | `process_all_pn_x.py` + `via54_pdf_download.py` | ✓ 雷管 160, TMA 106 |
| Step 3 L0 错论文 | `l0_paper_match.py` (5 维) | ✓ 16 个 wrong paper 识别 |
| Step 3 L4 关键词 | `l4_keyword_extract.py` (5 维) | ✓ 通用词问题修复 |
| Step 4 Highlight v10.1 | `via54_highlight_fix_v10.py` | 历史参考 (雷管 99.4% / TMA 85.8%) |
| Step 4 Highlight v3 FINAL | `hl_v3_final/rerun_all.py` + `hl_lib.py` | ✅ **唯一标准** (TMA 106/106, 1325/1325 像素验证) |
| Step 4 GLM 应证 | `glm_integration.py` | ✓ TMA 5#3 0%→17.6% |
| Step 5 三方对齐 | `step5_alignment.py` | ✓ 雷管 100/100/99.4%, TMA 98/98/0% (GLM 后 17.6%) |
| Step 6 目录合并 | `literature_v8_fix_merge_dirs.py` | ✓ 雷管 1 个 (P4-1P36-1) |
| 6 步规则校验 | `via54_rules.py check` | ✓ 雷管 6/7, TMA 5/7 |
| CI gate | `.github/workflows/rules_check.yml` | ✓ PR 自动跑 |

---

## 9. 故障排查 (Cheat Sheet)

| 现象 | 根因 | 修复 |
|---|---|---|
| Step 1b ❌ "无 .pptx 原版" | PPT 在顶层不在 `_ppt`/`_1_ppt` | 复制到 `step1_ppt_目录/` 或改 `via54_rules.py` 加候选 |
| Step 2 ❌ "无 _vision_report.json" | 没跑 `ppt_vision_analyze.py` | 跑一遍 |
| Step 3 ❌ "Pn-x 缺 PDF" | 下载失败 | 跑 `l0_paper_match.py` 验错论文, 用 `auto_redownload.py` 兜底 |
| Step 4 ❌ "0 hits" | 关键词太通用 | 跑 `l4_keyword_extract.py` 加医学术语 |
| Step 4 ❌ "highlight 标错位置" | 还在 v9.7/v10.1 line | 切到 v3 FINAL rect 模式 (`scripts/hl_v3_final/`) |
| Step 4 ❌ "无高亮色块/空 rect" | 句末标点漏 ASCII `.` / 句号跳位 | 用 hl_lib(已修复); 批量后重跑一遍 |
| Step 5#3 0% | slide 6+ 没 docling 应证 | 加 `--use-glm` 跑 GLM 语义对齐 |
| Step 6 ❌ "合并冲突" | DOI 解析不同 | 按**引用文本一致**判定(非 MD5/DOI 文件名), 新命名 `P3-1_P4-1` |

---

## 10. 关键文件索引

| 文件 | 作用 |
|---|---|
| `scripts/via54.py` | 统一入口 (8 子命令) |
| `scripts/via54_rules.py` | 6 步规则 + 校验 (23 tests) |
| `scripts/via54_highlight_fix_v10.py` | v10.1 line 模式 highlight (40 tests, 历史参考) |
| `scripts/hl_v3_final/hl_lib.py` | ⭐ v3 FINAL 精确逐行 rect 算法 (25 tests) |
| `scripts/hl_v3_final/rerun_all.py` | 批量重跑 (幂等 + fitz 渲染) |
| `scripts/hl_v3_final/step1/2/3_*.py` | 新 PPT 三步流程 (导出/提取引用/下载) |
| `scripts/hl_v3_final/align_tables.py` | 8 列本地表 + 在线表同构生成 |
| `scripts/hl_v3_final/leiguan_table.py` | 雷管方案在线表 + H 列卡片 + 写飞书 |
| `scripts/glm_integration.py` | GLM 5 能力兜底层 |
| `scripts/l0_paper_match.py` | 5 维论文匹配 (根治错论文) |
| `scripts/l4_keyword_extract.py` | 5 维关键词 (根治通用词) |
| `scripts/ppt_expand.py` | PPT 扩页 + 审计 + 渲染 |
| `scripts/ppt_vision_analyze.py` | PPT 视觉分析一键跑 |
| `scripts/step5_alignment.py` | 三方对齐 + GLM |
| `scripts/multi_project_diff.py` | 双项目对比报告 |
| `scripts/auto_redownload.py` | 错论文自动重下 (5 策略) |
| `scripts/process_all_pn_x.py` | 批量下载主入口 |
| `AGENTS.md` | 全局铁律 (H 列 v8.x 规则 + 6 步) |

---

**最后更新**: 2026-08-14
**维护者**: Devin 魏宇浩 + Mavis
**版本**: v3 FINAL (Step 4 rect 模式 + Step 6 新合并格式 + 8 列标准, 取代 v10.2 line)
