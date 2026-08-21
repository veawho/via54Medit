---
name: via54medit-anno2ppt-pitfalls-2026-08
description: via54Medit Phase 7 anno2ppt 实战 pitfalls 与真实案例. 触发 - P3-3, 跨 Pn-x 应证, mmx vision, sensenova 替代, PaddleOCR 踩坑, bbox 配对错位, 设计 vs 已实现 强约束, 双源架构, NCT fallback, Producer 分类, Chrome vs ReportLab, 经验沉淀 callback, P22-1 KM 曲线, P22-2 HK/Taiwan, HR 0.68 错标反例, UCL AAM 突破付费墙.
---

# anno2ppt Phase 7 — 实战 Pitfalls 与真实案例

> 配套技能: `via54medit-anno2ppt-phase7` (核心算法). 本技能是**实战踩坑 + 真实数据 transcript**.

## 关联支持文件 (References)

- `references/p22-2-page8-hk-taiwan-and-8-to-2-cleanup.md` — P22-2 page8 v4.0 + 8 张清理到 2 张
- `references/p22-multiquote-confirmation-fallacy.md` — P22-1+P22-2 多引用应证 transcript
- `references/p3-3-real-case-transcript.md` — P3-3 Fig.2 27 行癌肿真实案例
- `references/l0_pdf_authenticity_scan.md` — L0 扫描报告与 Producer 黑白名单
- `references/dual-source-architecture.md` — **双源架构完整设计 (P30-1 实战, 用户硬规则)**
- `references/sensenova-vision-replacement.md` — **sensenova-6.7-flash-lite 替代 mmx vision 完整记录**

## 关联脚本 (Scripts)

- `scripts/extract_table_bboxes.py` — 表格 bbox 提取
- `scripts/nct_fetcher.py` — **ClinicalTrials.gov 抓取 → fallback PDF (双源架构 fallback 端)**
- `scripts/vision_verify.py` — **L3 sensenova vision cascade 3 级 (新 2026-08-01)**
- `scripts/csv_feishu_sync.py` — **CSV 8 列表头守门员 (新 2026-08-01)**
- `scripts/process_pn_x.py` — process_pn_x v4.0 标注算法 (P3-3 集合结论 24 黄 + 2 橙)

## 关联 Support 文件 (references)

- `references/p3-page-by-page-calibration-2026-08-01.md` — **P3 4 标号逐标号校准完整 transcript**
- `references/p5-3-step-workflow-2026-08-02.md` — **P5 3 步验证工作流完整实录 (2026-08-02)**
- `references/h-column-evolution-v5-v7-2026-08-02.md` — **H 列 v5.0 → v7.6 完整 6 次演进实录 (2026-08-02)**
- `references/highlight-pages-vs-pdf-data-points-calibration.md` — **🆕 P3-3 高亮页 vs 数据点 PDF 校准算法 (2026-08-02)**

## 关键用户硬规则 (本次 session 强化)

1. **不合成 1 个 PDF** — Elsevier/Wiley/Karger 付费墙 → main + fallback 双文件互补, manifest 详细标注
2. **经验沉淀 = 默认动作** — 每次 L0/L1/L2/L3/L4 任务后自动 `persist_session_learnings()`
3. **诚实声明** — 任何能力表格必须区分"设计"和"已实现"
4. **设计 vs 已实现 强约束** — §5/§14 已记录

## §48. 🆕 每个 Pn-x 必须独立 highlight — "同 main 复用" 假设是错的 (2026-08-02 用户硬规则)

**症状**: 我之前的判断 "P5 表格内多引用（P5 表格 Row12-28 / P24 / P33 / P41 / P43 同 main 复用），不需独立 highlight" — 完全错误.

**用户原话** (2026-08-02): "我判断的标准，是PPT页面中的真实内容，而不是是否同一文献。同一文献，在不同PPT的slide中，对应的引用标记处的内容不同，所以 需要不同的highlight，这也就是为什么，同一文献，不同Page不同引文标号，都需要有一个副本。"

**根因**: 我混淆了 "同 main 复用" 与 "同文献". 实际上 P5 表格 17 行 (Row 12-28) = 17 个不同 RCT:
- Row 12 P5-2 = FOLFOX (Cheng Qin JCO 2022)
- Row 13 P5-3 = 索拉非尼 (Stras 2021)
- Row 14 P5-4 = 索拉非尼 (Llovet NEJM 2008)
- Row 27 P5-17 = ESMO 1494P (Sangro 2025)
- Row 28 P5-18 = Lau J Hepatol 2025

每个标号 = 不同 main PDF, 各自有各自的 highlight. **严禁"同 main 复用"假设**.

**修正算法 (v9.4)**:
```python
1. 每个有 main PDF 的 Pn-x 必须至少 1 张 highlight (page1 = 标题/作者页)
2. 多页 PDF 用 PPT 数据点搜索 (PPT C 列数字 + 方案名 + D 列第一作者 + 期刊)
   找最匹配页, 补 highlight
3. Pn-x highlight_pages 写入 manifest
```

**修正结果对比**:
| 指标 | v9.3 | v9.4 |
|------|------|------|
| 总 Pn-x | 160 | 160 |
| 总 highlight 图 | 315 | 455 (+140) |
| 无 highlight | 80 ❌ | 0 ✅ |
| 仅 page1 | 0 | 58 (会议摘要 1-2 页, page1 已足够) |
| 多张 highlight | 80 | 102 |

**实战升级清单 (2026-08-02 完成)**:
1. 80 个 0 highlight Pn-x 全部补 page1 highlight (PyMuPDF `page.get_pixmap(matrix=Matrix(2,2))` 渲染)
2. P3-3 从 3 张 (page1,4,5) → 4 张 (+ page7 Table 3 趋势)
3. P4-3 从 1 张 → 2 张 (+ page3 Cell Culture 异质性数据)
4. 多页 PDF 找 PPT 数据点最匹配页, 补 highlight (例: P5-14, P33-8)
5. 更新 manifest.highlight_pages 字段

**触发条件 (任何时候都应用)**: 任何 Pn-x 标注 / 飞书 H 列写入 / 应证评分计算前

**相关代码**: `scripts/verify_highlight_calibration.py` (在原 skill 的 scripts/ 下)

## §49. 🆕 PPT ↔ PDF ↔ Highlight 三方对齐校验方法学 (2026-08-02)

**校验逻辑** (algorithm-driven):

```
1. PPT C 列提取数据点 (visual_alignment + data_alignment)
   ↓ 数字提取: \b\d+\.?\d*\b, 过滤 len ≥ 2, 1 ≤ float ≤ 100
2. Main PDF 搜数据点 → 找到出现页号 (PyMuPDF text scan, 前 20 页)
   ↓ Docling segfault 时 fallback PyMuPDF (Pitfall #36)
3. Highlight 是否覆盖该页 (manifest.highlight_pages ∩ pdf_data_pages)
4. 三方对齐状态:
   ✅ 对齐: PDF 数据页 ⊂ highlight 页
   ❌ 无数据点: PPT 标号纯文字 (无数字), 无法用数字校验 (38.1% 案例)
   ⚠️ PDF 无数据: PPT 数据在 PDF 图片/截图中 (PyMuPDF 提取不到, 3.8% 案例)
   ❌ HL 不覆盖: PDF 数据在多页, highlight 只标 page1 (已修复 2 个)
   ❌ main PDF 错位: manifest.main_pdf 与 D 列文献不匹配 (1.9% 案例)
```

**v9.4 校验结果**:
| 状态 | 数量 | 占比 |
|------|------|------|
| ✅ PPT ↔ PDF ↔ HL 对齐 | 90 | 56.3% |
| ❌ PPT 无数据点 | 61 | 38.1% |
| ⚠️ PDF 无数据（图/截图） | 6 | 3.8% |
| ❌ main PDF 错位 | 3 | 1.9% |
| **总计** | **160** | 100% |

**真对齐率**: 90/160 = 56.3%. 排除无数字标号 (61) 后: 90/99 = 90.9%

**3 个 main PDF 错位案例** (待修正):
- P31-2: D=Galle ASCO LBA4008, main=Galle CheckMate Lancet 2025 (错位)
- P33-4: D=Shukui APASL OP0102, main=STRIDE APASL TPS628 (错位)
- P33-9: D=Cheng J Hepatol 2022, main=Galle CheckMate Lancet 2025 (错位)

**根因**: `scan_pn_x_dir` 选择 main PDF 时, 文件名相似度匹配错位. 修法: 修正 `_manifest.json` 中的 main_pdf 字段或重新下载正确 PDF.

**触发条件**: 任何"全部 Pn-x 已校验" / "highlight 完成度报告" / "三方对齐状态" 任务

## §27. 160 个 Pn-x 全量标注 — 107 归档目录全部 PASS (2026-08-01)

**用户原话**: "不是18个是160个" + "完成所有文献标注工作" + "自检自修"

### 流程 (L0-L6 算法驱动)

1. `process_all_pn_x.py` 跑 160 个 Pn-x (含 shared 目录子 ID 拆解)
2. L0 分类 → L0 验证 → 文字提取 → L4 应证 → Highlight → L3 sensenova → manifest
3. `self_check.py` 自检 107 个归档目录 (manifest + highlight + main PDF)
4. 自修 (5 个 shared 目录 manifest 字段补全 + 3 个缺失 highlight 生成)
5. 再次自检 → 107/107 PASS

### 关键 bug 修复

| Bug | 修复 |
|-----|------|
| `fmt.Sprintf` % 字符冲突 | heredoc 改用 here-string, 不用 Go 模板 |
| MuPDF `non-page object` | 警告抑制 + try/except |
| medit CLI JSON 解析失败 | inline Python 降级, 不依赖 CLI |
| shared 目录 manifest 缺失 | pnx_list 从 ARCHIVE_ROOT 拆子 ID |
| Python heredoc 缺 `import json` | 首行加 import |

### 交付数据

- 160/160 处理成功, 1,337 总 highlight hits, 平均 12.5/目录
- 107/107 归档 PASS (manifest + highlight JPG + main PDF 完整)

详见 `references/160-pn-x-batch-workflow.md`

## 18 个 Pn-x 截图包壳全部修复 (2026-08-01 完结)

- 10 个 ReportLab 截图包壳 (P12-1/P22-1/P24-3/P33-1/P43-1/P5-17 = ESMO #1494P; P3-1 = Kudo HBSN; P29-1/P33-11/P41-10 = Song YG)
- 4 个 Chrome Skia 截图 (P24-6/P30-1/P30-8/P41-12 = Llovet LEAP-002 via UCL AAM)
- 4 个 PDFmake/Karger/Elsevier (P28-2/P33-5/P43-8 = Kuwano; P5-13 = Chen Y)
- 1 个双源架构 (P30-1 = ScienceDirect + NCT02329860)

## §28. 🆕 P3 4 标号逐标号校准 — 集合结论推理 + GLOBOCAN 冲突 + L3 cascade (2026-08-01 完结)

**用户原话** (2026-08-01 完整 4 段):
1. "文字说明和图片对应不上" — highlight 图与 PPT 说明对不上
2. "页面中有 4 个标号才对啊" — P3 实际有 4 个标号 (1, 2, 3, 4), 不是 3 个
3. "为什么又出现了本地文件与飞书文档（逐页引用表）不一致的情况" — P3-1 完全没在 CSV
4. "为什么本地不能和飞书一样有表头呢" / "确保以后做其他文献整理时也能有表头"

### 4 标号实况 (P3)

| 标号 | Pn-x | PPT 语义 | 高亮图 | 状态 |
|:----:|:----:|---------|:------:|:----:|
| 1 | P3-1 | GLOBOCAN 2020 China 36.8万/42.5% | 2 张 (Kudo HBSN OS/ORR) | ⚠️ **错位** (GLOBOCAN 冲突) |
| 2 | P3-2 | 健康中国2030 → 46.6% | 1 张 (page3 46.6%+80%) | ✅ |
| 3 | P3-3 | 肝癌 14.4%, 远低于其他癌种 | **3 张** (page1+4+5) | ✅ v4.1 集合结论 |
| 4 | P3-4 | 中晚期肝癌拉低生存率 | 3 张 (page1+2+4) | ✅ |

### 🆕 Pitfall 27: P3-1 GLOBOCAN 数据版本冲突 (3 个数据时序错位)

**症状**: 飞书 D 列写"GLOBOCAN 2020 China 36.8万肝癌 / 42.5% / 41.7% / 31.7万", DOI 是 `10.3322/caac.21834` (Bray 2024 CA Cancer J Clin, GLOBOCAN 2022 论文), 本地 PDF 是 GLOBOCAN 2024 (2 页速览) + GLOBOCAN 2022 (Bray 35 页全文). 3 个时序错位!

**根因**: 飞书 D 列数据采集自 GLOBOCAN 2020 (中国肝癌新发/死亡 36.8万/31.7万), 引用 DOI 来自 2024 出版 (Bray 2022 data), 本地 fallback 来自 2022+2024 — **3 个版本混搭**

**Crossref 验证**:
```
DOI 10.3322/caac.21834:
  标题: "Global cancer statistics 2022: GLOBOCAN estimates of incidence and mortality worldwide for 36 cancers in 185 countries"
  期刊: CA: A Cancer Journal for Clinicians
  出版年: 2024 (Bray F, Laversanne M, Sung H)
  Volume: 74
  → 论文是 2024 出版, 但 GLOBOCAN 数据是 2022 年
```

**修复决策树** (3 选 1):
- A. 修飞书 D 列 → 改成 Kudo HBSN 2022 (HIMALAYA OS/ORR)  — 改最少
- B. 修本地 PDF → 删 Kudo HBSN, 补 GLOBOCAN 2020 China PDF (DOI 10.3322/caac.21654)  — 找 2020 论文
- C. 都修 → 飞书改成 GLOBOCAN 2022 (Bray 2024 caac.21834), 本地保留 GLOBOCAN 2024 China fallback

**算法升级方向**: 在 L0 验证加 "数据时序一致性" 维度 — D 列数据采集年份 + DOI 出版年份 + PDF 文件内容年份必须 3 方位一致

**详细 transcript**: `references/p3-page-by-page-calibration-2026-08-01.md`

### 🆕 Pitfall 28: 集合结论词不展开全部数据 (P3-3 v4.1 实战)

**症状**: PPT 说"中国肝癌5年生存率仅14.4%, 远低于其他癌肿", 算法只标 PPT 列举的 5 种癌肿 (肝癌 14.4% / 食管 27.9% / 胃 35.2% / 结直肠 55.7% / 乳腺 80.9%), 漏了 Table 2 完整的 26 种癌肿 (实际 24 种 > 14.4%, 1 种 = 14.4%, 1 种 8.5%).

**根因**: 关键词匹配 vs 集合结论推理. 算法把"远低于其他" 当成"PPT 列举的几种", 没数完整 Table.

**用户原话**: "PPT 图表中举例的几个癌肿只是因为图表容量有限, 所以给出了几个常见癌肿, 并不是要求只标注这几个, 只有标注了所有比肝癌的14.4高的癌肿"

**P3-3 修复 (v4.1)**:
- 新增 `P3-3_page5_highlight.jpg` — Table 2 整表高亮
- 24 种 > 14.4% (黄色高亮) + 1 种 = 14.4% (肝癌本身, 橙色) + 1 种 < 14.4% (胰腺癌 8.5%, 橙色)
- L4 集合结论推理得分: 0.95
- l4_key_terms 扩展: 8 个 → 34 个 (含 Table 2 全量百分比)
- l4_collection_conclusion 字段新增

**算法升级 (via54medit-anno2ppt-phase7)**: SetConclusionScore 已经在 phase7 设计里, 实战验证 P3-3 完整 26 行.

**触发条件**: 任何 PPT 出现
- "远低于 X" / "far below other"
- "普遍高于 X" / "mostly above"
- "大部分 X" / "all except Y"
- "其他癌种/组织/方案" 集合词

**修复 SOP**:
1. 读 PDF Table 完整数据 (所有行, 不是 PPT 列举的几个)
2. 算 N_high + N_low + N_equal (vs 基准)
3. 高亮所有 N-1 行 (基准除外)
4. 颜色区分: 黄色 = 高于基准, 橙色 = 低于/等于基准
5. 应证得分 ≥ 0.95 = 完整应证

### 🆕 Pitfall 29: L3 sensenova vision cascade 3 级架构 (2026-08-01)

**症状**: L3 视觉复核 (highlight 图 vs PPT 语义) 之前只靠 mmx vision, 经常 rate limit / 配额耗尽.

**根因**: mmx vision 按 Token 计费, 上限低, 敏感词触发 ("Hong Kong" 等).

**3 级 cascade (新)**:
1. **sensenova-6.7-flash-lite** (主) — 免费 + 262K context + 无敏感词 + 实测 5-11s/次
2. **MiniMax-M3** (备) — 速度最快, 但经常 429 限流/2056 配额用尽
3. **PyMuPDF local** (兜底) — 只读 metadata, 无视觉理解, 用于 API 全失败时

**实现**: `scripts/vision_verify.py --provider cascade --json`

**P3 实战验证**:
- P3-2 page3 (健康中国): sensenova 正确识别 46.6% + 80% 2 处高亮
- P3-3 page1 (Abstract): sensenova 正确识别 8 个数字 (43.3/43.7/8.5/92.9/60/20/46.6%)
- P3-3 page4 (Fig.2): sensenova 正确识别 27 个癌症名标签
- P3-3 page5 (Table 2): sensenova 确认黄色 + 橙色高亮分布

**注意**: sensenova API 名是 `sensenova-6.7-flash-lite` (小写), 不是 `sensenova-6.7-flash-lite` / `MiniMax-VL-01` / `sense`
lark-cli 文档说用 `model: sense` 是错的 (API 报 "unknown model"). 实测 2026-08-01.

**SKIP 环境变量**:
- `SKIP_SENSENOVA=1` 跳过主视觉
- `SKIP_MINIMAX=1` 跳过备选
- `VISION_TIMEOUT=60` 单调用超时

### 🆕 Pitfall 30: CSV 8 列表头铁律 (用户原话 "确保以后做其他文献整理时也能有表头")

**症状**: 本地 CSV 没表头, 跟飞书表 Row 1 (表头) 错位 1 行. `csv.reader` 默认把 Row 1 当表头, 后续所有行错位 → 7 列校核"全错".

**用户原话 (2026-08-01)**: "为什么本地不能和飞书一样有表头呢" + "确保以后做其他文献整理时也能有表头"

**铁律 R 落地**:
- 8 列固定表头 (frozen 2026-08-01): `PPT页,第几条,引用语义（上下文）,PPT中的文献引用 完整字段,DOI,类型,对应PDF文件,来源链接 → 阅读全文`
- Go 守门员: `via54Medit/internal/citation/sync/csv_sync.go` (CanonicalHeader 冻结, 14 单测 100% PASS)
- Python 守门员: `via54Medit/scripts/csv_feishu_sync.py` (validate + sync 子命令)
- 任何新项目从 `templates/citation_table.csv` 复制模板

**已沉淀到**: `citation-table-cell-truthflow` skill 铁律 R (v1.7.0)

### 🆕 Pitfall 31: P3-1 凭印象幻觉 (CSV 漏行 + 错误补录)

**症状**: 本地 CSV Row 2 (P3-1) 完全没记录. 我凭印象 (本地有 `Kudo_HBSN_2022.pdf`) 补录"P3-1 = Kudo HBSN 2022 ORR 数据", 实际飞书表 Row 2 指向 `The_Journal_2022.pdf` (GLOBOCAN 数据库).

**根因**: 补录前没先读飞书真值. 凭本地 PDF 文件名推断内容.

**用户原话**: "为什么又出现了本地文件与飞书文档（逐页引用表）不一致的情况"

**修复** (铁律 P 已落地): 任何"补录"前必 lark-cli +cells-get 飞书表对应 Row 拉真值.

### 🆕 Pitfall 32: lark-cli `--spreadsheet-token` vs `--sheet-id` 颠倒

**症状**: `--spreadsheet-token b03e59 --sheet-name "逐页引用表"` → API 1310251 invalid request

**雷管方案正确**:
```bash
lark-cli sheets +cells-get \
  --spreadsheet-token FEISHU_SHEET_TOKEN(已轮换,勿复用) \
  --sheet-id b03e59 \
  --range A{N}:F{N}
```

**区分**:
- `spreadsheet_token` (整表 ID) 在 URL 路径 `/sheets/{TOKEN}` — 雷管方案 = `FEISHU_SHEET_TOKEN(已轮换,勿复用)`
- `sheet_id` (子表 ID) 在 URL 末尾或 `?sheet=...` — 雷管方案 = `b03e59`
- 飞书 URL `https://xxx.feishu.cn/sheets/b03e59` 里的 `b03e59` 是**子表 ID**, 不是 spreadsheet_token

**检测**: 报 1310251 = `Path param :spreadsheet_token invalid` → 99% 是参数填反.

### 🆕 Pitfall 33: 7 列校核时 cells 索引错位

**症状**: 循环 `for r in range(159): fs = cells[r+1]` → 所有行错位 1 (csv row[0] ≠ 飞书 Row 2)

**根因**: 飞书 API 返回的 `cells[]` 数组已跳过表头 (Row 1), `cells[0]` = 飞书 Row 2 (不是 Row 1)

**修复**:
```python
for r in range(len(csv_rows)):
    fs = cells[r]  # ← 直接 r, 不是 r+1
    cs = csv_rows[r]
    # 飞书 Row = r + 2 (因为 cells[0] = Row 2)
```

---

(以下内容保留, 包含 26 个实战 pitfall + transcript)

### 🆕 Pitfall 34: 3 步执行顺序不可逆 + 自主决策铁律 (2026-08-02 用户纠正)

**症状**: 旧流程先体检→缺文件→推理→高亮→写H, 被用户纠正"顺序不对".

**用户原话**: "顺序不对, 现在是验证修复的顺序: 步骤1 视觉理解PPT → 步骤2 视觉理解PDF的highlight → 步骤3 校验 PPT引文位置+PDF内容+PDF highlight+表C-H列"

**铁律 #27 落地**: 3 步流程不可逆:
1. **PPT 视觉理解** — `ppt_understand.py find_citation_marks_v2()` 语义提取标号
2. **PDF highlight 对齐验证** — `pdf_understand.py verify_highlight_alignment()` 输出 aligned/score/issues
3. **五方校验** — ① PPT理解 + ② D列引文 + ③ PDF全文 + ④ Highlight区域 + ⑤ H列

**自主决策铁律** (2026-08-02 用户纠正):
- 用户说 "你是算法驱动的接入了LLM的超级智能体，要学会自己推断最有路径"
- **禁止** 问琐碎选择题 (P5-1 卫健委无DOI→自动选NHC+Wayback; P5-13 付费墙→自动标记⚠️; P5-16 71KB→自动标注内容有限)
- 标准操作直接执行, 不需要逐条确认

### 🆕 Pitfall 35: extract_ppt_data_points 假阳性 (百分比变体过度生成 + 个位数噪声)

**症状**: `RATIONALE-301` 生成 `301%`, `IMbrave150` 生成 `150%`, `mOS 13.6月` 生成 `13.6%`, `5`/`2`/`7` 个位数匹配 797 个表格单元格

**根因**: 正则 `\d+\.?\d*%?` 太贪婪, 把试验名数字和月份值当百分比, 个位数到处匹配

**3 条修复规则 (2026-08-02)**:
1. **数字 > 100 不生成 `%` 变体** — 避免试验名 301/150/310 误生成 (RATIONALE-301, IMbrave150, CARES-310)
2. **中文单位后缀不生成 `%` 变体** — `月/年/天/人/例/周/个/个月` 跳过 (mOS 13.6月→13.6%, 随访52.5月→52.5%)
3. **纯个位数 (0-9) 跳过** — 除非带小数点或 `%` (6.47 保留, 5/2/7 跳过)

**验证**: 16/16 测试通过, P5-2 数据点从 7 个降到 2 个 (6.47, OS), bbox 匹配从 797 降到 5 个

### 🆕 Pitfall 36: Docling segfault → PyMuPDF fallback

**症状**: P5-12 (Zhao STTT 2025, 2.5MB, 10 页) `docling convert` → `Segmentation fault: 11`

**根因**: Docling 2.115.0 在某些 PDF 上 segfault (已知 issue, 与 PyMuPDF 版本冲突)

**修复**: `parse_pdf_with_docling()` 非 0 退出码时自动 fallback 到 PyMuPDF 文本抽取:
```python
if result.returncode != 0:
    import fitz
    doc = fitz.open(pdf_path)
    text = "".join(page.get_text() for page in doc)
    doc.close()
    fallback_doc = {
        "texts": [{"text": t} for t in text.split("\n") if t.strip()],
        "tables": [], "pictures": [], "pages": {},
        "_fallback": "Docling segfault → PyMuPDF fallback (2026-08-02)",
    }
    # 写入缓存
    json.dump(fallback_doc, open(cache_file, "w"))
    return fallback_doc
```

**注意**: fallback doc 不含 tables/pictures (只有 text), 后续 `find_data_point_in_doc` 在 fallback 中只搜 texts, 不搜 tables. 可用于文本对齐验证, 但 bbox 高亮需要重新渲染.

---

## 1. 🚨 跨 Pn-x 数据源定位 (最重要)