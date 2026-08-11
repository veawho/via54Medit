# Semantic Highlight v1.3 — 实际 fail 报告 (2026-08-11)

**status: v1.3 实际未达用户 4 个硬要求, 必须改 v1.4**

## 用户 4 个硬要求 (2026-08-11)

> 1. 不同 Pn-x 的同一文献要分开对齐 PPT 的不同 slide, 分开分别 highlight
> 2. 所有 highlight 必须位置准确, 不能遮挡文字、不能左/右偏移、不能上/下偏移
> 3. 所有 highlight 必须根据内容进行, 段落使用文字下划线, 图表/图片使用黄线框
> 4. 不要瞎搞, 不要自以为是, 不要绕过视觉 vision, 不要猜测, 一切都需要实际对照、实际检查、实际验证

## v1.3 实际效果 (spot check 34 Pn-x jpg)

实际渲染位置: `/tmp/spot_all/{Pn-x}/page_NN.jpg`
summary: `/tmp/spot_all/_summary.json`

### 严重问题 (13+ Pn-x 违规)

| Pn-x | Page | 实际高亮内容 | 违反要求 |
|---|---|---|---|
| P15-1 | p1 | 整页 18-82% 一坨黄, 盖 author+affiliation+DOI+Introduction | ❶❷❸ (author 区) |
| P20-1 | p2 | top 7-30% 盖 page header (Hofer et al.) + 段落 | ❶❷ (header 区) |
| P3-1 | p2 | top 70-94% 是 Figure 1 caption + 期刊 footer | ❶❷ (找错页) |
| P15-1 | p4 | Table 2 + footnote + 章节标题 (7-35%) | ❶❷ (bbox 太大) |
| P20-1 | p4 | Table 1 + "(Continued)" + footer (6-92%) | ❶❷ (bbox 太大, 跨整页) |
| P12-2 | p3 | Table 1 row 2/6 (用 fill 不是边框) | ❸ (Table 应是边框) |
| P30-2 | p1 | **中文综述 references [47] 整块黄** (整页 references section) | ❶❷ (reference 区) |
| P23-17 | p1 | author+affiliation "Christopher C. Dvorak...Alexion, AstraZeneca..." (42-48%) | ❷ (author 区) |
| P23-2 | p1 | affiliation "...Foundation and Leukemia Research Institute..." (43-67%) | ❷ (affiliation) |
| P15-2 | p3 | Table 1 整张 (3-56%) | ❶❷ (bbox 太大) |
| P30-1 | p2 | Figure 1 caption (46-64%) | ❶❷ (caption 应不算 figure 内容) |
| P31-5 | p3 | x-axis 数字 + Discussion 整段 (43-58%) | ❸ (figure 用 fill 不是边框) |
| P3-2 | - | **0 highlight, 完全失败** | ❶ (没找到) |

## 4 个根因 (实际证据)

### 根因 1: `add_highlight_annot` 是 fill 不是下划线

`semantic_highlight_workflow.py:397-401`:
```python
annot = page.add_highlight_annot(rect)
if annot:
    annot.set_colors(stroke=(1, 1, 0))
    annot.update()
```

**PDF native HIGHLIGHT 注释是 fill 背景色**, 不会变下划线. 即使设 stroke color, fill 还是 yellow. 这就是为什么所有"段落下划线"实际是黄色 fill, 遮住文字.

**正确做法**: `page.add_underline_annot(rect)` 只在文字 baseline 画线, 不遮字.

### 根因 2: sensenova 永远不标 title/author/reference

实测 cache 92 条 sensenova 返回, content_type 分布:
- paragraph: ~80%
- figure / image / table: ~15%
- title / author / reference: **0 条**

**FORBIDDEN_CONTENT_TYPES 完全没生效**.

v1.2 删了所有几何 heuristic 改"完全信 sensenova"是错的方向. v1.2 的 page 顶部 22% / 底部 8% / 文字特征判断 [n] / "et al." / "M.D." 必须加回.

### 根因 3: bbox 太大 (段落级大框, 不是句级)

sensenova 倾向给"段落级"大 bbox, 不是"句级". P15-1 page 1 bbox 18-82% 覆盖了整页 65% 高度. P20-1 page 4 bbox 6-92% 覆盖了 86% 高度.

必须加 sanity check:
- bbox width > 70% page width AND height > 30% page height → 拆/拒
- bbox 内文字 > 200 chars → 拆/拒

### 根因 4: P3-2 失败, "不同 Pn-x 同一文献分别处理" 没法验证

P3-1 (Walport Pt 1) 1 个 highlight (位置错)
P3-2 (Walport Pt 2) 0 highlight (失败)

实际 P3-1 P3-2 是不同 PDF, 不是"同一文献". 但 P3-2 完全失败说明 sensenova 在 Walport Pt 2 没找到任何 semantic match (max_pages=4 太少, 或 prompt 太严).

## v1.4 修复方案

| 修复点 | v1.3 | v1.4 |
|---|---|---|
| 段落样式 | `add_highlight_annot` (fill) | **`add_underline_annot` (仅 baseline 画线)** |
| 图表样式 | `draw_rect` (OK) | 不变 |
| 禁 author/title | sensenova 自标 (0 命中) | **加文字特征**: M.D./Ph.D./Department of/University/@/et al. → author; bbox 顶部 22% on page 0 → title/author |
| 禁 header/footer | sensenova 自标 (0 命中) | **加几何**: page bottom 8% → footer; page top 5% 任何 page → header |
| 禁 reference | sensenova 自标 (0 命中) | **加文字特征**: bbox 文字含 [1] [2] 引用格式 + "References" 标题 → reference; 整页以 "References" 开头 → 整页 reference |
| bbox 大小 | 任意大 | **sanity check**: width>70% AND height>30% page → 拒; 文字 > 200 chars → 拒 |
| confidence | ≥0.4 | **≥0.7** |
| 多 PDF page | max_pages=4 | max_pages=8 |
| P3-2 等失败 | 不修 | 加 PDF 摘要反向抽英文 keywords 注入 plan.keywords (TMA 4 轮已验证有效) |

## next step

1. commit 当前 v1.3 存档 (代码要在)
2. 改 v1.4 关键代码
3. 重跑 P3-1 P3-2 P15-1 P20-1 P12-2 P31-5 6 个最关键 case
4. 渲染 jpg 让人眼确认 4 个硬要求
5. 等用户拍板跑全量
