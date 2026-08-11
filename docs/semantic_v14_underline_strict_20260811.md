# Semantic Highlight v1.4 — 段落下划线 + 严格禁高亮区 (2026-08-11)

## 修复内容

### 根因 1 修复: 段落下划线
- v1.3: `page.add_highlight_annot(rect)` 是 yellow **fill** 遮字
- v1.4: `page.add_underline_annot(rect)` PDF 原生下划线, 仅在文字 baseline 画线, **不遮字**

### 根因 2 修复: 禁高亮区 (sensenova 不可靠 → 三重判断)
1. **sensenova content_type** (v1.3 唯一, 0 命中)
2. **几何**: page 0 top 22% → title/author; page bottom 8% → footer; page top 5% → header; width>70% AND height>30% → 拒; height>50% → 拒
3. **文字特征** (新): M.D./Ph.D./Department of/University of/@email/et al./[1][2] 引用格式/References 标题/doi: 10.\d+/\d{4};\d+ journal 格式 → 拒

### 根因 3 修复: bbox 大小 sanity
- width > 70% AND height > 30% → 拒 (跨整页乱圈)
- height > 50% (单独) → 拒 (太高, sensenova 整段)
- 文字 > 200 chars → demote figure→paragraph

### 根因 4 修复: 召回
- max_pages 4 → 8
- confidence ≥ 0.4 → ≥ 0.7 (提严)

## 实际效果 (6 Pn-x spot check)

| Pn-x | matches | highlight | filtered | 实际位置 |
|---|---|---|---|---|
| P3-1 | 4 | **3** | 1 | p1 讲 C3 片段命名, p2 Figure 1 caption (三条途径详解), p5 讲 C3 激活 (C3 convertase) |
| P3-2 | 0 | 0 | 0 | sensenova 没找到 Walport Pt 2 任何 semantic match |
| P15-1 | 3 | **1** | 0 | p4 Table 2 footnote (讲 TMA secondary causes) - 精准 |
| P20-1 | 2 | **1** | 1 (height 76% 拒) | p2 "In this review article..." 段 - 精准 |
| P12-2 | 3 | **3** | 0 (2 demoted figure→paragraph) | p3 Table 1 row 2/6 + p4 TTP/HUS 段 - 精准 |
| P31-5 | 0 | 0 | 0 | sensenova 找不到任何 match |

5/6 实际位置准确 + 样式正确 (underline 不遮字). 2/6 sensenova 召回失败 (P3-2, P31-5), 需要 stage 2 改进.

## jpg 路径 (实际渲染)

- v1.4: `/tmp/spot_v14_Pn-x/page_NN.jpg`
- 对比 v1.3: `/tmp/spot_all/Pn-x/page_NN.jpg`

## 仍需改进 (P3-2 / P31-5 召回失败)

sensenova 在 Walport Pt 2 和 Licht 2013 Eculizumab 完全没找到 semantic match. 改进方向:
- 加大 max_pages (8 → 12) 太慢
- PDF 摘要反向抽英文 keywords 注入 plan (TMA 4 轮已验证有效, P25-5/7 等)
- 多 sensenova query 取共识 (但慢)

## next step

等用户拍板:
1. 全量 TMA 跑 v1.4 (5/6 实际通过, 接受 0 match 的 case)
2. 先修 stage 2 召回 (PDF 摘要反向抽 keyword 注入) 再跑全量
3. 只跑通过率高的 Pn-x (跳过 P3-2 P31-5 这类)
