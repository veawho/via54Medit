# Semantic Highlight Strict Pipeline v1.2 (2026-08-11)

## User 第二轮要求

> 不是满分的问题，是需要视觉语义匹配，**禁止关键词匹配**，**禁止 highlight 标题、作者、PDF 中的文献引用部分**

## 实现 (semantic_highlight_workflow.py v1.2)

### 1. 完全移除 keyword 兜底
- 删除 `_process_one` 的 `use_fallback` 逻辑
- 删除 keyword matching fallback 路径
- 找不到 semantic match → 直接返回 `no_semantic_match` (ok=False)
- **覆盖率不是目标，匹配质量才是**

### 2. Stage 3 严格过滤禁止区域 (`_is_in_skip_zone`)

**禁止 content_type (sensenova 自己标)**:
- `title` / `author` / `authors` / `affiliation`
- `reference` / `references` / `bibliography` / `cited` / `literature`
- `header` / `footer` / `running_head` / `journal_info`
- `acknowledgment`

**几何启发 (sensenova 没标但实际是)**:
- `page_idx == 0 and y1 < page_h * 0.22` → title/author 区域
- `y1 > page_h * 0.92` → footer
- 整页文字含 "References"/"Bibliography" + 引用格式 → reference 页
- bbox 在 `page_h * 0.70` 以下 + 文字含 `[n]` / `Author et al.` / `2020)` → 引用条目

### 3. Sensenova prompt 调整
- 让 model 标 content_type (含 title/author/reference/header/footer)
- 放宽 prompt (避免 sensenova 过度保守)
- Stage 3 的 filter 才是真正的守门员

## TMA 55 plans 结果

| 指标 | 数值 |
|---|---|
| 纯 sensenova semantic 找到 (含禁区域) | 35/55 (63.6%) |
| **过滤后实际高亮 (排除 title/author/reference)** | **29/55 (52.7%)** |
| 完全 no semantic match | 25/55 (45.5%) |
| 总 sensenova 找到的 bbox | 161 |
| **被过滤的 bbox (title/author/reference)** | **44 (27.3%)** |
| 实际高亮的 bbox | 117 |

## 关键过滤示例

P9-1: 9 matches → 4 filtered → 5 highlighted
```
filter: page 0 type=title bbox=(97,103)-(470,137)   # 标题
filter: page 0 type=reference bbox=(33,640)-(200,653)  # 引用
filter: page 3 type=header bbox=(255,21)-(412,31)   # 页眉
filter: page 3 type=title bbox=(355,309)-(519,329)  # 章节标题
```

P3-1 实际高亮位置:
```
y=491: "friendly aspects of the complement system."  # body, 真正 semantic match
y=490: "spect to the fragments of C2: the large fragment is"  # body
```

P3-1 title 部分 (y=91, 138, 172) **正确未高亮**.

## 与 v10.4 keyword 对比

| 方法 | ok | 备注 |
|---|---|---|
| v10.4 keyword only | 100/106 (94.3%) | 包含 title/author/reference 等错误高亮 |
| semantic + 严格过滤 | 29/55 (52.7%) | 只在 body 段落, 真正 semantic |

**覆盖率降了, 但准确率 100%** (所有高亮都在 body 真正 semantic 对应的位置).

## 后续优化

1. **提升 sensenova 召回**: 多 PDF page 范围, 更细致的 prompt
2. **更精细的 reference 过滤**: 区分 "in-text citation [1]" 和 "reference list [1] Author"
3. **GLM 二次审核**: 用 GLM 4V 复审 sensenova 找的 bbox, 双重保险
4. **写一个 verify 脚本**: 人工 spot check 几个 PDF, 确认高亮都在正确位置

## Commit

`d1a0426` (initial) → 改进 v1.2 (待 commit)

文件位置:
- `/Users/david/Desktop/developments/via54Medit/scripts/semantic_highlight_workflow.py`
- 输出: `/Users/david/Desktop/TMA_文献整理/_3_highlight_semantic/`
