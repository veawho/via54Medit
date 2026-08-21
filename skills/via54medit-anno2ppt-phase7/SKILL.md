---
name: via54medit-anno2ppt-phase7
description: via54Medit Phase 7 算法驱动应证推理机 (4 维要素对齐 + 集合结论评分). 用于 PPT 引文标注自动寻找 PDF 中对应的证据位置 (文字/表格/图表/图片). 触发关键词 - anno2ppt, 应证推理, 信息要素, 4 维对齐, 集合结论, P3-2 27 行癌肿, process_pn_x v4.0.
---

# via54Medit Phase 7 — 算法驱动应证推理机 (anno2ppt)

## 1. 核心问题（2026-08-01 用户原话）

> "文字说明和图片对应不上" + "PPT 图表中举例的几个癌肿只是因为图表容量有限, 所以给出了几个常见癌肿, 并不是要求只标注这几个, 只有标注了所有比肝癌的 14.4 高的癌肿"
> → **集合结论推理** vs **关键词匹配**

v3.x 算法缺陷：纯关键词 + 段落合并，无法处理「远低于其他癌种」这类语义命题。

## 2. 4 层架构（基于 GitHub 调研 2026-08-01）

| 层 | 技术 | GitHub Star |
|---|------|-----------|
| L1 文字加速 | PyMuPDF + PyMuPDF4LLM | 10k + 2k |
| L2 结构化 | docling + PaddleOCR PP-Structure + Marker | 64k + 86k + 38k |
| L3 视觉理解 | InternVL + DeepSeek-VL2 + Nougat | 10k + 5k + 10k |
| L4 应证推理 | 本算法包 `internal/anno2ppt` | (新增) |

## 3. 信息要素 4 维对齐（核心创新）

```go
type InformationElement struct {
    Geography, Disease, Indicator, Value, Conclusion, Unit string
    ValueNum float64
}
```

4 维权重：`0.20/0.30/0.20/0.20/0.10`（地理/病种/指标/数值/结论）

## 4. 集合结论评分 (P3-2 应证核心)

`SetConclusionScore(subjectValue, "below_all", tableRows)` →

- 数 27 行癌肿 vs 肝癌 14.4
- nHigh=25, nLow=1 (pancreas 8.5) → 应证得分 0.95
- 决策: ShouldHighlight=true, BBoxes=27 行全标

## 5. 实现位置

```
/Users/david/Desktop/developments/via54Medit/
├── internal/anno2ppt/
│   ├── algorithm.go       (4 维对齐 + 集合结论 + 应证评分)
│   └── algorithm_test.go  (9 案例 / 9 PASS, P3-2 驱动)
├── cmd/medit/commands/anno2ppt.go  (CLI: parse/confirm)
└── docs/PHASE7-ANNO2PPT.md (待写)
```

## 6. CLI 调用

```bash
# 编译
cd /Users/david/Desktop/developments/via54Medit
go build -o /tmp/medit ./cmd/medit/

# 解析 PPT 文本
medit anno2ppt parse "中国肝癌5年生存率仅14.4%, 远低于其他癌种"
# → 4 维要素 + conclusion="below_all"

# 应证推理 (输入 PDF 表格 JSON)
medit anno2ppt confirm "<allegation>" /path/to/table_rows.json
# → confirm_score=0.95, bbox_count=27, should_highlight=true
```

## 7. JSON 输入格式

```json
[
  {"Disease": "肝癌", "Value": 14.4, "Unit": "%", "Geography": "中国"},
  {"Disease": "甲状腺癌", "Value": 84.3, "Unit": "%", "Geography": "中国"},
  ...
  {"Disease": "胰腺癌", "Value": 8.5, "Unit": "%", "Geography": "中国"}
]
```

## 8. 关键用户反例沉淀

- 「远低于其他癌种」是**集合结论**, 不是关键词 → 必须 SetConclusionScore
- 27 行 = subject(1) + N_high + N_low = 25 + 1 例外 → 应证得分 0.95
- 集合结论允许 1 个例外（用户原话: "仅有胰腺癌的8.5%低于肝癌的14.4%"）
- 中英映射: "far below other" → below_all / "远低于其他" → below_all / "普遍高于" → mostly_above
- 疾病同义: HCC ↔ 肝癌 ↔ hepatocellular ↔ liver cancer

## 9. 经验闭环

用户修正 → `corrections.json` → 算法权重微调 → 重新跑 9 个测试 → CI 验证

## 10. ⚠️ 应证 ≠ 全量标注（P22-1 + P22-2 教训, 2026-08-01）

**核心铁律**: 应证推理的驱动源是 **PPT 引用语义 (位置 1 文字)**, **不是** PDF/mmx 视觉列出的所有数字。

### 反例

我曾让 `mmx vision describe --image xxx` 列出图里所有数字 (HR 0.68 / 17.1% / 8.9% / 16.43 / 13.77 / N=479 / TRAE 19.9%...), 然后把 mmx 列出的所有数字都当成"应标内容"高亮。

**这是错的**。用户 P22 页引用的语义是:

> 「HIMALAYA III期 全球人群、中国人群1,2」(P22 左框上方)

**PPT 完全没有要求** 应证 HR 0.68 / 72-month 17.1% / N=479 / TRAE 等。

### 正确流程

```
1. 读 PPT 引用语义 (CSV C 列 "位置1" 文字)
   → 提取 PPT 真正应证的要素 (4 维)

2. 在 PDF 里搜这些要素 (文字层 search_for)
   → 找到匹配的 bbox

3. 只标这些 bbox
   → 不标 PPT 没说 + PDF 里有的数字
```

### 错误 vs 正确对照

| 决策 | 错误 (mmx 主导) | 正确 (PPT 主导) |
|------|-----------------|-----------------|
| 应证来源 | mmx vision 列出的所有数字 | **PPT 位置 1 文字** |
| 要素提取 | mmx 说"图里有 X 数据" | **PPT 说"我要证 X"** |
| 标注判定 | mmx 列了什么就标什么 | **PPT 提了什么、PDF 也有，才标** |
| 例子 (P22-2) | HR 0.68 / TRAE 19.9% / N=479 全标 | **只标 HIMALAYA + phase III + Asian subgroup + Asia-Pacific** |

### mmx vision 工具的正确用法

`mmx vision describe` 是**视觉问答复核工具**，用于:
- 验证图里有什么数据存在
- 验证高亮位置是否准确 (mmx 数到几处)
- 核对 bbox 是否对齐文字

**不是**用于驱动"该标什么"。

### 算法改造方向

下一步 L4 应证推理机应加新约束:
- **`allegation_elements` 优先**: 用 PPT 文本抽出的 4 维要素作为查找 query
- **bbox 必须包含 `allegation_keyword`**: bbox 字符串数组里至少要命中 1 个 PPT 关键词
- **拒绝裸 bbox**: 没有 allegaton 关键词的 bbox 自动剔除

## 11. 下一步（用户给绿灯后做）

1. L2 docling + PaddleOCR 真实 PDF 解析，喂 bbox 给 confirm
2. process_pn_x.py v4.0 调 `medit anno2ppt confirm`
3. P3-2 真实 PDF 跑通 → 27 行 bbox 全部高亮 + 文字说明 100% 对应
4. **L4 加 `allegation_keyword` 约束**: bbox 必须包含 PPT 引用语义中的关键词，否则拒绝
5. **mmx vision 用法约束**: 只用于验证，不用于驱动标注

## 12. ⚠️ L0 PDF 真实性验证（用户 2026-08-01 P22-1 教训, 已落地）

**核心问题**: v3.9 算法假设 P22-1 main PDF 是 Bruno Sangro ESMO 2025 #1494P，但实际是 liangyihui.net 截图包壳的 ReportLab PDF。**算法只看文件存在，不验证文件内容真实性**。

### L0 验证 (在 L1-L4 之前强制执行)

```
score = 0.45*TitleSim + 0.30*AuthorSim + 0.15*DateMatch + 0.10*MetadataCompleteness
```

| 维度 | 算法 | 来源 |
|------|------|------|
| TitleSim | Jaccard 词集合相似度 | PDF metadata.Title vs Crossref Title |
| AuthorSim | 字符串包含 | PDF metadata.Author vs Crossref Authors[0].Family |
| DateMatch | 时间比较 | PDF metadata CreationDate >= Crossref Published Date |
| MetadataCompleteness | 4 字段非空检查 | title / author / subject / creator |

### 决策阈值

- score >= 0.70 → verified=true (可以进入 L4)
- 0.45 <= score < 0.70 → warning (LLM 复核)
- score < 0.45 → reject (走 fallback)

### 实现位置

```
/Users/david/Desktop/developments/via54Medit/
├── internal/anno2ppt/
│   ├── l0_verify.go        (新增, 280 行)
│   └── l0_verify_test.go   (新增, 9 案例 / 9 PASS)
├── cmd/medit/commands/anno2ppt.go  (新增 l0verify 子命令)
└── scripts/l0_extract_pdf_meta.py  (Python 抽 PDF metadata)
```

### CLI 用法

```bash
# 验证 P22-1 v4.0 (真原文 PDF) → PASS
medit anno2ppt l0verify <pdf_path> 10.1016/j.annonc.2025.08.2124
# 真实结果: verified=true, score=0.925, title_sim=1.0

# 验证 P22-1 v3.9 (截图包壳) → REJECT
medit anno2ppt l0verify <pdf_path> 10.1016/j.annonc.2025.08.2124
# 真实结果: verified=false, score=0.075, title_sim=0.0
```

### GitHub 调研基座

- **djui/pdftitle** (低 star) — PDF 标题提取启发式
- **sckott/habanero** ★40+ — Crossref Python client
- **ropensci/rcrossref** ★400+ — Crossref R client
- **Crossref API 官方** — `https://api.crossref.org/works/{doi}`

### Key 经验

1. **不要相信文件存在 = 文件正确** — 必须 L0 验证
2. **Jaccard 相似度足够** — 不用 TF-IDF / sentence embedding
3. **4 维要素** (Title/Author/Date/Meta) 互补 — 单维度太弱
4. **Placeholder 严格识别** — `untitled / anonymous / unspecified / anon` 都视为空
5. **不要 Placeholder 假阳性** — "Anon" 也视为占位符

### 测试结果 (2026-08-01)

- Real ESMO 1494P → verified=true, score=0.92, title_sim=1.0
- Screenshot wrapper → verified=false, score=0.075, title_sim=0.0
- No DOI → verified=false, score=0.50, issue="no DOI provided"
- 9 个单元测试全部 PASS, 端到端验证 P22-1 v4.0 vs v3.9 区分成功

## 13. 触发流程 (updated 2026-08-01)

新 Pn-x 抓 PDF 必须按这个流程：

```
1. L0 验证 (medit anno2ppt l0verify)
   ↓ verified=true
2. L1 PyMuPDF 文字提取
   ↓
3. L2 PaddleOCR (中文, 含图)
   ↓
4. L3 sensenova vision 复核 (替代 mmx vision)
   ↓
5. L4 应证推理机 (4 维要素)
   ↓
6. 输出 bbox + highlight
```

**L0 不过就走 fallback, 不要硬标.**

## 14. sensenova-6.7-flash-lite 多模态集成 (2026-08-01)

**替代 mmx vision** 做 highlight 图视觉复核。

### 为什么选 sensenova

| 对比项 | mmx vision | sensenova-6.7-flash-lite |
|--------|-----------|--------------------------|
| 费用 | 按 Token 计费, 上限低 | **全部免费** (pricing=0) |
| 安装 | 需 npm 安装 mmx-cli | 0 安装, 纯 API |
| 可用性 | 需 Token Plan, 常超限 | 无限制 (国内 API) |
| Context | 有限 | **262K tokens** |
| 敏感词 | "Hong Kong" 等触发审查 | 无审查 (国内 API) |

### 实现位置

```
via54Medit/scripts/
├── sensenova_vision.py    (核心: base64 + API 调用)
└── l3_vision_verify.py    (集成包装器: 接收图片+语义, 返回复核结果)
```

### CLI 用法

```bash
# 单次复核
python3.11 scripts/sensenova_vision.py <image.jpg> "PPT引用语义"

# 结构化 JSON 输出
python3.11 scripts/sensenova_vision.py <image.jpg> "prompt" --json

# 保存结果到文件
python3.11 scripts/sensenova_vision.py <image.jpg> "prompt" --save

# L3 集成包装器
python3.11 scripts/l3_vision_verify.py <image.jpg> "allegation_text"
```

### 实测验证

P3-1 (Kudo HBSN 2022): 正确识别 3 处高亮, 覆盖 HIMALAYA + ORR 20.1% + CR 3.1%
P29-1 (Song YG 2024): 正确识别 4 处高亮, 覆盖 8.42%/4.42%/2.06%/2.11x
P33-11 (Song YG 2024): 正确识别 4.42% 3/4级出血数据

### API 详情

```python
model: sense

**触发条件**:
- "anno2ppt" / "应证推理" / "信息要素" / "4 维对齐"
- "集合结论" / "SetConclusionScore"
- "P3-2 27 行癌肿" / "远低于其他癌种"
- "P22-1 / P22-2 / HIMALAYA / 全球人群 / 中国人群 / 一线获益"
- "process_pn_x v4.0"
- 用户质疑 "该标什么 / 不该标什么"
- 用户指出 "标签跟 PPT 要求不一致"
- 用户质疑 "标注位置与说明对应不上"
- "L0 验证" / "PDF 真实性" / "Crossref" / "DOI 反查"
- 用户质疑 "PDF 是不是真的" / "main PDF 是不是该文献"
- "sensenova" / "视觉复核" / "多模态" / "vision verify"