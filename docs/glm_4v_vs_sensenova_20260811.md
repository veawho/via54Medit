# GLM-4.1V-Thinking-Flash vs Sensenova 对比 (2026-08-11)

## 测试方法

- 6 Pn-x 跑 v1.4 sensenova + GLM-4.1V-Thinking-Flash
- 严 prompt: 完全照 v1.4 stage 2 (禁 title/author/reference)
- 宽 prompt: 允许 figure caption, 找"任何相关"

## 实际效果 (P3-1 + P3-2)

| Backend | P3-1 (Walport Pt 1) | P3-2 (Walport Pt 2) | 单次调用 | 全量 55 plans |
|---|---|---|---|---|
| **sensenova 严 prompt** | **4 matches, 位置对** | 0 matches (PPT 引用错?) | ~10s | ~2 min |
| **GLM-4.1V 严 prompt** | 0 matches | 0 matches | ~30s | ~7 min |
| **GLM-4.1V 宽 prompt** | 1 match (整图 figure) | 0 matches | ~60-180s | ~25-40 min |

### P3-1 GLM-4.1V 宽 prompt 实际找到 (page 3):

```json
{
  "found": true,
  "matches": [{
    "bbox": [123, 143, 854, 886],
    "content_type": "figure",
    "description": "补体通路三条活化途径示意图",
    "relevance": "包含经典途径、凝集素途径、旁路途径的标注及相互作用，与PPT中三条活化途径的描述语义相关",
    "overall_confidence": 0.9
  }],
  "reason": "在图2中找到补体通路三条活化途径的图..."
}
```

### P3-2 sensenova 0 matches 原因 (重要!)

P3-2 是 Walport 2001 NEJM Pt 2 (Complement Deficiency), **不讲"三条活化途径"**(那是 Pt 1).
PPT 标号 2 引用文字"补体三条活化途径...1,2" - **mark 2 实际应该引用 Pt 1, 不是 Pt 2**.

这是**引用错误, 不是视觉模型召回问题**. sensenova 和 GLM-4.1V 都正确拒绝.

## 结论: 不切换到 GLM-4.1V

| 维度 | sensenova | GLM-4.1V |
|---|---|---|
| 召回率 | 中 (严 prompt) / 中高 (v1.3) | 低 (严) / 中 (宽) |
| 速度 | **10s/call** | 30-180s/call |
| 中文 PPT 引用 | 召回好 | 召回差 |
| 英文 PDF 描述 | 召回中 | 召回差 |
| 思维链解释 | 无 | 有 (但占空间) |
| bbox 风格 | 多小 bbox (段落级) | 1 大 bbox (整图级) |

## next step

继续用 sensenova + 修 P3-2 等引用错误 case. GLM-4.1V 留着做"复审"用, 不做主召回.

## GLM 4V 集成代码

`scripts/glm_vision.py` 写了完整 wrapper (含 MD5 cache, OpenAI 兼容), 暂未接到 v1.4 stage 2. 留作后续:
- 复审 sensenova 找到的 bbox (GLM 4V 思维链强)
- 混合方案: sensenova 召回 + GLM 4V 复审 (但慢)
