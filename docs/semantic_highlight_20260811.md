# Semantic Highlight Pipeline (2026-08-11)

## 革命性改进: 不再用 keyword matching

### 你的需求 (user feedback)
> 先推理 PPT slide 的视觉语义，然后用语义匹配对应查询 PDF 中语义匹配的段落、图片、图标，进行 highlight 操作。

### 实现 (`semantic_highlight_workflow.py`)

**Stage 1 (PPT 视觉理解)**:
- sensenova 看 PPT slide 渲染图
- 抽 mark 位置 + target_text + data_points + keywords

**Stage 2 (Semantic PDF Search)**:
- sensenova 同时看 PPT slide + 1 个 PDF page (2 图 query)
- 让 model 找 PDF 中与 PPT 标号**语义对应**的段落/图/表/图标
- 给出 bbox (像素坐标) + content_type + semantic_description
- 不用 text 匹配, 纯 visual + semantic 推理

**Stage 3 (Bbox-based Highlight)**:
- 用 sensenova 返回的 bbox 直接画线 (`page.draw_line`)
- 不调 process_pn_x (避免 text search 误匹配)
- 转换 image bbox → PDF 坐标 (除以 actual_zoom)

**Fallback**:
- 35 个 sensenova 找到 (63.6%)
- 8 个 fallback 用 process_pn_x (14.5%)
- 12 个仍失败 (sensenova + keyword 都没找到)
- **总 43/55 = 78.2%**

## TMA semantic vs keyword 对比

| 方法 | ok | 比例 | 备注 |
|---|---|---|---|
| v10.4 keyword only (前 4 轮) | 100/106 | 94.3% | 全部 Pn-x |
| semantic only (sensenova 视觉) | 35/55 | 63.6% | 仅 vision plan 覆盖的 |
| **semantic + fallback** | **43/55** | **78.2%** | 混合方案 |

## 优势

1. **精准**: 不会把 "TMA" 在 header 或引用列表里的位置误标
2. **可解释**: bbox 来自 sensenova 推理, 不是字符串匹配
3. **多模态**: 能找图片/表格/图标, 不只是段落
4. **可扩展**: 未来可加 GLM/VL 进一步精确

## 失败的 12 个 Pn-x (待优化)

P5-20, P8-5, P8-15, P9-5, P12-14, P16-3, P16-5, P16-9, P17-13, P18-2, P19-1, P31-8

这些 PPT 标号内容可能太具体 (数字/百分比), sensenova 在 PDF 中找不到对应的语义段落. 需要:
- 拆 PPT 内容到更细的语义
- 调 sensenova prompt (用更多上下文)
- 加更多 PDF page 搜索范围

## 配置

```bash
# 单测
python3.11 scripts/semantic_highlight_workflow.py --project TMA --limit 5

# 全跑
python3.11 scripts/semantic_highlight_workflow.py --project TMA

# 雷管方案
python3.11 scripts/semantic_highlight_workflow.py --project 雷管方案
```

## API 修复

- 修 URL: `https://token.sensenova.cn/v1/llm/chat-completions` → `https://token.sensenova.cn/v1/chat/completions`
- 修 JSON parser: 处理 markdown code block 包装 (sensenova 偶包 ```json ... ```)
- 加 balanced {} 匹配 (处理嵌套 JSON)
- 修 _process_one 调用加 use_fallback=True

## 文件位置

- 脚本: `/Users/david/Desktop/developments/via54Medit/scripts/semantic_highlight_workflow.py`
- 输出: `/Users/david/Desktop/TMA_文献整理/_3_highlight_semantic/`
  - `Pn-x_semantic_highlight.pdf` - 实际 PDF with yellow line on bbox
  - `_semantic_summary.json` - 全部 55 plans 结果

## 4 thread 并行 (1 sensenova query ≈ 10s, 4 page × 4 thread = 10s/plan)

55 plans 全跑 ~15 分钟 (vs 4 thread serial 50 分钟).
