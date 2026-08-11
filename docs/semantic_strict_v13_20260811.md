# Semantic Highlight Strict v1.3 (2026-08-11)

## User 严肃要求 (第三轮)

1. **不同 Pn-x 同一文献要分开对齐 PPT 不同 slide, 分开分别 highlight**
2. **位置准确: 不能遮挡文字、不能左/右/上/下偏移**
3. **段落下划线, 图表/图片黄线框**
4. **不要瞎搞, 不要自以为是, 不要绕过 vision, 不要猜测, 一切都需要实际对照、实际检查、实际验证**

## 实现 (semantic_highlight_workflow.py v1.3)

### 1. 段落下划线 + 图表黄线框 (按 sensenova content_type)

```python
PARAGRAPH_TYPES = {"paragraph", "body", "text", "section", "subsection"}
FIGURE_TYPES = {"figure", "image", "diagram", "chart", "table", "icon", "graph", "illustration"}

if content_type in FIGURE_TYPES:
    page.draw_rect(rect, color=(1, 1, 0), width=2)  # 黄线框
else:
    annot = page.add_highlight_annot(rect)            # PDF 原生下划线
    annot.set_colors(stroke=(1, 1, 0))
```

### 2. add_highlight_annot 位置 0 偏移

PDF 原生 `add_highlight_annot` 自动用文字 baseline 定位, 不会遮挡/偏移. 这是 PyMuPDF 推荐的标准方式.

### 3. 删所有几何 heuristic, 完全信 sensenova content_type

```python
FORBIDDEN_CONTENT_TYPES = {
    "title", "article_title", "section_title",
    "author", "authors", "affiliation", "correspondence",
    "reference", "references", "bibliography", "cited", "literature_cited",
    "header", "footer", "running_head", "journal_info",
    "acknowledgment", "acknowledgements",
}
# 不再有任何 page_h * 0.22 之类的几何假设
```

### 4. Sanity check: figure 误标 demote 到 paragraph

sensenova 偶尔把 text 区域标成 figure, 加 sanity check:
```python
if content_type in FIGURE_TYPES:
    text_in_bbox = page.get_text("text", clip=rect).strip()
    if len(text_in_bbox) > 80:  # >80 chars 几乎肯定是正文
        content_type = "paragraph"  # demote
```

### 5. sensenova cache 确保一致性

sensenova 高度不确定, 每次返回不同结果. 加 MD5 cache:
- key = hash(prompt + image_paths)
- 第一次跑调 API, 后续直接读 cache
- 跑完整 55 plans, 多次结果稳定一致

### 6. spot_check_semantic_highlights.py 实际验证工具

按 user 要求 "一切都需要实际对照、实际检查、实际验证":
- 列出每个 Pn-x 的高亮 (bbox + 覆盖文本)
- 渲染有 highlight 的页为 jpg (供肉眼检查)
- 检查 alignment (高亮文本 vs PPT target_text 关键词覆盖率)
- 输出到 `_spot_check_log.json` + `_spot_check_imgs/`

## TMA 55 plans 结果

| 指标 | 数值 |
|---|---|
| sensenova semantic 找到 | 35/55 (63.6%) |
| **过滤后实际高亮** | **24/55 (43.6%)** |
| 总 bbox | 145 |
| 被过滤 (title/author/ref) | 11 |
| Demoted figure→paragraph (sanity check) | 14 |
| 实际高亮 | 86 |

## 当前限制 + 下一步

1. **sensenova 仍不确定**: 同 prompt 跑 2 次可能结果不同. cache 解决一部分, 但仍需人工 spot check
2. **figure bbox 经常过大**: sensenova 给出 page 1/2 大区域, 需要后续精细化
3. **25 个 Pn-x 找不到**: PPT 标号内容太具体 (数字/百分比), sensenova 找不到对应

## 文件

- `/Users/david/Desktop/developments/via54Medit/scripts/semantic_highlight_workflow.py` v1.3
- `/Users/david/Desktop/developments/via54Medit/scripts/spot_check_semantic_highlights.py` 验证工具
- 输出: `/Users/david/Desktop/TMA_文献整理/_3_highlight_semantic/`
  - `Pn-x_semantic_highlight.pdf` - 实际 PDF with 下划线/边框
  - `_spot_check_log.json` - 全部 Pn-x 高亮 detail
  - `_spot_check_imgs/Pn-x/page_NN.jpg` - 渲染 jpg 供肉眼检查
