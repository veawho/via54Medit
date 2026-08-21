---
name: via54medit-ppt-citation-analysis
description: >
  via54Medit PPT 引用分析 4 列规范 (rules #1-6, 2026-08-05)。
  拿到 PPT 后, 第二件事: 视觉分析所有元素可见性 → 扩大 PPT 页面 → 按 4 列 (A=slide, B=mark, C=cite, D=visual+text 暂定) 输出 CSV。
  关键铁律: 标号 N 对应引用文献 依赖视觉理解 (不写启发式规则 — 用户原话 "人类也是靠视觉理解, 我无法给你固定规则")。
  多引用共享 (17,18) 拆 2 行, 每个 slide 的每条引用序号 = 1 行, D 列必真调 vision_analyze 而不是仅文字。
  工具: ~/.medit/scripts/{expand_slide_for_visibility, export_ppt_to_images, analyze_ppt_citations}.py
  配套测试: ~/.medit/tests/test_ppt_citation_rules.py (6 个, 锁住规则 #1-6)
metadata:
  author: via54
  version: 1.0.0
  tags: via54medit ppt-citation citation-csv vision-analyze 4-column-rules literature-management double-track slide-expansion
---

# via54Medit PPT 引用分析 4 列规范

## 触发

拿到新 PPT 后, **第二件事**: 
1. 视觉分析所有元素可见性 (底部引用文献可能超出页面)
2. 把 PPT 引用解析为 4 列 CSV (A=slide, B=mark, C=cite, D=visual+text 暂定)

第一个动作是建目录, 详见 skill `via54medit-algorithm-driven-upgrade-v2` v1.8.0 文献整理目录规范。

## ⚠️ 2026-08-14 对齐: 最终交付表 = 雷管方案 8 列

> 本 skill 的 4 列 CSV 是**中间分析产出**。最终交付的本地表/在线表必须是雷管方案 8 列:
> `PPT页 | 第几条 | 引用语义（上下文） | PPT中的文献引用 完整字段 | DOI | 类型 | 对应PDF文件 | 来源链接 → 阅读全文`
> 完整标准(列/规则/H 列卡片/生成脚本): `~/.hermes/skills/via54medit-literature-pipeline/references/leiguan-8col-table-standard.md`
> TMA 项目新 PPT 引用提取用 `~/.hermes/skills/via54medit-literature-pipeline/scripts/step2_extract_refs.py`
> (106 条全量回归验证, 支持同行多引用/跨段落续行; 本 skill 的脚本适用于 HCC 等项目)。

## 用户原话 (硬规则, 2026-08-05)

> 1. 文献标注分为两个部分: 引用序号, 以及 slide 底部对应引用序号的引用文献
> 2. 视觉分析所有元素的可见性, 如果发现引用文献超出了页面范围, 则重新扩大 PPT 页面, 确保所有引用文献可见. 扩大 PPT 页面时, 需要分析引用文献的文字颜色, 扩大后的 PPT 页面底色需要保证引用文献内容可见, 可以被视觉识别出正确的文字
> 3. 分析引用序号, 需要使用视觉理解+文字理解, 对引用序号指向的相关 PPT 内容进行分析理解, 并将结果记录到表格的 D 列
> 4. A 列、B 列、C 列在对齐 PPT 后就是固定不变的
> 5. D 列内容因为缺少引用文献 PDF 校准, 所以为暂定内容, 后续可调整
> 6. 一定要视觉分析, 如果需要导出图片后再分析, 则需要建立一个 PPT 导出图片的目录

**用户后续修正**:
> "标号 N 对应了什么内容需要你视觉理解, 因为人类也是靠视觉理解, 我无法给你固定规则"
> "17,18 这种, 需要两行"
> "D 列必须真调视觉, 再+文字"

## 4 列输出 (严格 A/B/C/D 顺序)

| 列 | 字段 | 来源 | 性质 |
|----|------|------|------|
| A | slide_num | PPT slide 序号 (1-43) | 固定 |
| B | mark_num | 引用序号 (1-50, 每标号 1 行) | 固定 |
| C | citation_text | slide 底部对应引用文献 | 固定 (对齐后) |
| D | d_content_provisional | 视觉+文字分析 引用序号指向的相关 PPT 内容 | **暂定** (缺 PDF 校准) |

输出示例:
```csv
slide_num,mark_num,citation_text,d_content_provisional
3,1,"The Global Cancer Observatory 2022. https://gco.iarc.fr/...",标号 1 出现: 「中国肝癌新发和死亡病例占全球近半数1」 | 视觉: ...
3,2,"《健康中国行动——癌症防治行动实施方案（2023-2030年）》",标号 2 出现: 「《健康中国行动——...》2」 | 视觉: ...
5,3,"Qin S, et al. Lancet Oncol. 2025...",标号 3 出现: 「索拉非尼3,4」 | 视觉: ...
5,4,"Qin S, et al. Lancet Oncol. 2025...",标号 4 出现: 「索拉非尼3,4」 | 视觉: ...
```

## 工具链 (3 个脚本)

### 1. `expand_slide_for_visibility.py` — 规则 #2 扩大 PPT 页面

**触发**: 任何 PPT 引用分析前必跑, 检测底部超出

```bash
python ~/.medit/scripts/expand_slide_for_visibility.py <pptx>           # dry-run
python ~/.medit/scripts/expand_slide_for_visibility.py <pptx> --apply  # 实际扩大
```

**核心逻辑**:
- 扫描全部 slide, 找 `bottom > slide_height` 的 shape
- 算 max_bottom + 0.3" padding, 扩 `prs.slide_height`
- 读 shape 文字色 + slide 背景色 → **WCAG contrast ratio ≥ 4.5** 决定改不改文字色
- 输出 `<原名>_expanded.pptx`

**已知问题 (2026-08-05)**: 雷管方案 PPT 6 个 slide 底部超出 (P5/P7/P24/P30/P40/P42)

### 2. `export_ppt_to_images.py` — 规则 #6 视觉导出

**触发**: 视觉分析前必跑

```bash
python ~/.medit/scripts/export_ppt_to_images.py <pptx> <out_dir> --dpi 150
```

**已知坑 (2026-08-05)**: 
- LibreOffice/soffice 没装 → 当前不可用
- 备选: macOS qlmanage 只导出首页
- 真跑必须先 `brew install --cask libreoffice` (~5 分钟)

### 3. `analyze_ppt_citations.py` — 主分析器

```bash
python ~/.medit/scripts/analyze_ppt_citations.py --no-vision           # 仅文字, C 列标 [need_vision]
python ~/.medit/scripts/analyze_ppt_citations.py --images <dir>        # 真视觉
python ~/.medit/scripts/analyze_ppt_citations.py --slide 5            # debug 单 slide
```

**核心函数**:
- `extract_bottom_citations(slide)` — 找 y>5 的 text frame, 排除 PPT 脚注 (`* 唯一:` / `# HIMALAYA`)
- `_find_marks_in_slide(slide)` — 复用 ppt_understand v2 语义驱动 (table_v2 + text_v3)
- `heuristic_map_marks(slide_idx, marks, citations, image_path, no_vision)` — **调 vision_analyze** 让 VLM 判断标号→引用对应, **不写启发式**
- `analyze_d_column(slide_idx, mark_num, mark_context, image_path)` — D 列视觉+文字

## 关键 Pitfall (用户已经吃过亏)

### 🔴 **不要写标号→引用的启发式规则**

我之前写"启发式映射: 标号按出现顺序对应引用文献", P3 标 1 拿了 4 条引用 (错的, 标 1 应该只对应 GLOBOCAN 1 条).

**用户原话**: "标号 N 对应了什么内容需要你视觉理解, 因为人类也是靠视觉理解, 我无法给你固定规则"

**正确做法**: 调 `vision_analyze(image_url=slide_NNN.jpg, question=...)`, 让 VLM 看完 slide 视觉后逐标号给引用文献索引.

### 🔴 **多引用共享 → 2 行**

P5 标号 `17,18` 共享同一文献 (STRIDE 论文), 但 CSV 必须 2 行:
```csv
5,17,"Qin S, ...STRIDE...",标号 17 出现: 「雷管方案17,18」 | 视觉: ...
5,18,"Qin S, ...STRIDE...",标号 18 出现: 「雷管方案17,18」 | 视觉: ...
```

### 🔴 **D 列必真调 vision, 不准仅文字**

我之前 D 列只写"标号 X 出现在「...」", 用户说"D 列必须真调视觉, 再+文字". 即使 vision_analyze 还没接上, 路径必须留 (用 `[vision 待实装: image=..., mark=...]` 占位).

### 🔴 **每个 slide 的每条引用序号 = 1 行**

不是"每个唯一 DOI 1 行", 不是"每个 Pn-x 1 行". **每条引用序号 1 行**, 跨 slide 共享也多次出现.

### 🔴 **底部引用文献排除 PPT 脚注**

`extract_bottom_citations` 必须排除:
- `* 唯一:` (PPT 脚注)
- `# HIMALAYA` (注解)
- 纯数字 (页码)
- 装饰矩形 (`name` starts with `矩形`)

否则会把 PPT 注解当成引用文献填 C 列.

## 视觉 prompt 模板 (vision_analyze)

```python
prompt = f"""
PPT 第 {slide_idx} 页, 有以下引用文献 (底部, 按 y 排序):
  [0] {cite[0][:100]}
  [1] {cite[1][:100]}
  ...

有以下引用序号 (B 列), 标号 = 数字, 出现在:
  标号 1: 「{mark_1_context}」
  标号 2: 「{mark_2_context}」
  ...

请视觉理解 PPT, 对每个标号, 给出它对应的引用文献索引 (0-based).
格式: 标号1=idx, 标号2=idx, ... (多个标号可共享同一 idx)
如果某个标号无法判断, 写 skip.
"""
```

## 6 个回归测试

`~/.medit/tests/test_ppt_citation_rules.py` 锁住规则 #1-6:

| 测试 | 锁什么 |
|------|--------|
| `test_extract_bottom_citation_y5` | 规则 #1: 底部 y>5 的 text frame |
| `test_extract_citation_marks_ends_with_digit` | 规则 #3 text_v3: 末尾数字 |
| `test_output_csv_4_columns` | 规则 #4: 4 列固定 |
| `test_d_column_provisional` | 规则 #5: D 列含 "PPT 标号" |
| `test_expand_dry_run_no_file` | 规则 #2: dry-run 不写文件 |
| `test_export_images_creates_dir` | 规则 #6: 目录自动建 |

跑 `cd ~/.medit/tests && python test_ppt_citation_rules.py` → 6/6 passed.

## 测试用例 (已知 P3 / P5)

### P3 标号 1-4 (4 个标号, 4 行)
```csv
3,1,"The Global Cancer Observatory 2022. https://gco.iarc.fr/"        ← P3 左半区 (GLOBOCAN)
3,2,"《健康中国行动——癌症防治行动实施方案（2023-2030年）》"        ← P3 右半区 (政府文件)
3,3,"Zeng H, et al. J Natl Cancer Cent. 2024 Jun 22;4(3):203-213."  ← P3 中央 (远低于其他癌种)
3,4,"Wang, Chun-Yan, and Shengmian Li. Medicine vol. 98,4 (2019): e14070."  ← P3 中央 (拉低总生存率)
```

### P5 标号 17,18 (共享 1 篇, 2 行)
```csv
5,17,"Sangro B, et al. ESMO 2025 abstract 1494P..."  ← P5 表格行 17 (STRIDE)
5,18,"Sangro B, et al. ESMO 2025 abstract 1494P..."  ← P5 表格行 18 (共享 STRIDE)
```

## 关键教训 (2026-08-10 实战沉淀)

### 🔴 Pn-x编号 ≠ PPT引用序号（最常见错误）

Pn-x目录是按**下载顺序**编号的。和PPT里的引用序号**完全不是一回事**。

- P4-1 ≠ Slide 4第1条引用（P4-1实际是中文指南，不是George NEJM 2006）
- 不能用"slide_num + ref_num → P{n}-{n}"的假设
- 关键词全文搜索匹配准确率仅65%——匹配到的是PDF参考文献列表，不是正文

**正确流程（不可跳步）：**
1. vision_analyze读PPT slide图片 → 确认作者+期刊
2. vision_analyze读候选PDF第一页 → 找匹配的
3. 确认后 → highlight

### 🔴 Highlight禁止内容（高压红线）

- 禁止：文章标题、作者名称、DOI、参考文献列表、页眉页脚
- 只允许：正文应证段落（方法/结果/讨论/数据）

### 🔴 Step 3视觉对照不可省略

不做视觉对照直接用关键词匹配 → 65%的概率画在错误内容上

## 错误陷阱 (2026-08-05 真实踩过)

| 错误 | 原因 | 修正 |
|------|------|------|
| 启发式映射 P3 标 1 拿 4 条引用 | 我写"按出现顺序 1:1" | 删, 改 vision_analyze |
| `--no-vision` 时 C 列留空 | 不知道 vision 还没接通 | 标 `[need_vision: 标号→引用需 vision_analyze]` |
| D 列只写文字 | 偷懒 | vision_analyze 路径 + prompt 模板 |
| Aspose.Slides 缺 libgdiplus | 默认 install 缺 GDI+ | 装 LibreOffice (aspose 写在脚本里 fallback) |
| import vision_analyze_tool 失败 | 没这模块 | hermes 内置 vision_analyze 单独 tool, 用它 |

## 待你给的后续规则

- 标号 N 在表中 (e.g. `索拉非尼3,4`) 与底部文献的视觉对应, 多引用共享时 C 列写 1 条还是迭代?
- 跨 slide 共享 (P5 标 17 在 P24 也出现) 在 4 列 CSV 里 1 次还是 2 次?
- D 列 prompt 是不是要分段 (banner / 表格 / 段落 视觉元素分类)?
- vision_analyze 当前 VLM 是 sensenova 6.7-flash-lite, 是否够准?

## 相关引用

- `~/.medit/scripts/expand_slide_for_visibility.py` — 规则 #2 底部超出 + 文字色保可见
- `~/.medit/scripts/export_ppt_to_images.py` — 规则 #6 视觉导出 LibreOffice
- `~/.medit/scripts/analyze_ppt_citations.py` — 主分析器 (4 列 + vision_analyze 路径)
- `~/.medit/tests/test_ppt_citation_rules.py` — 6 个回归测试
- `~/.hermes/skills/via54medit-algorithm-driven-upgrade-v2/SKILL.md` — 算法升级 v1.8.0 (目录规范 + 8 步 fallback)
- `~/.hermes/skills/pdf-download-tool-composition/SKILL.md` — 工具组合调用
- `~/Desktop/developments/via54Medit/scripts/ppt_understand.py` — 标号提取 v2 (复用 _find_marks_in_slide)
- `~/Desktop/developments/via54Medit/AGENTS.md` — 30 条铁律 (via54Medit 跨工具规约)