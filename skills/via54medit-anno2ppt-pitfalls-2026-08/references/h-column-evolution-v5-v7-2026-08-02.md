# H 列 v5.0 → v7.6 完整演进实录 (2026-08-02)

> 这是单日 (2026-08-02) 内 H 列写作算法的 6 次迭代, 每次用户都指出"还差一层",
> 必须看完整演进才能理解为什么现在 H 列是这样. 配套主技能:
> `via54medit-anno2ppt-phase7` (L4 应证推理) + `feishu-h-column-v2-template`.

## 上下文

用户在单日 8+ 小时里对 H 列做出 6 次重大修正指令, 每次都是"修完之后又发现还差什么".
我犯的根因: **没有把整个 H 列写作当作一个完整的"推理展示"任务, 而是一个"信息填表"任务**.

## v5.0 — H 列基本结构 (用户: "H 列 v5.0 结构")

4 个修正指令:
1. 不需要本地路径, 只需要本地文件名 (消除路径噪音)
2. 主文件列出文献信息 (标题/作者/期刊/年/卷/期/页/出版/DOI)
3. 不重复 C 列的"多引用结构" (C 列已有)
4. 应证推理合并为: 视觉对齐/数据对齐/语义推理

新模块: `h_column_builder.py` (parse_d_field + parse_c_field + build_h_md + markdown_to_rich_text)

验证: P3+P4+P5 H2-H28 全部 27 行通过.

## v5.5 — rich_text 排版根因 (用户: "排版又丢了??")

3 个根因:
1. 排版保留: rich_text 文本段必须含 `\n` 换行符, 不能按行拆分多段 (飞书多段内联渲染无换行).
2. 裸 URL 也转链接: 不仅 `[text](url)` 格式, `https://doi.org/xxx` 等裸 URL 也必须转成 `{type:"link", text, link}` 段.
3. 每个本地文件对应下载链接: 4-tier 链接中 🥇 一级 (本地 PDF) 必须有对应互联网下载链接 (DOI/PubMed/Europe PMC).

升级: `markdown_to_rich_text()` v3 同时检测 `[text](url)` 和裸 URL, 保留 `\n` 换行.

## v6.0 — 文件清单 + 应证评分 + 时效性 (用户: "修正 H 列: 与 _literature_citation_index 目录一致")

3 个修正:
1. 文件清单 = Pn-x 目录: 扫描 main/fallback/supplementary 三类 PDF. main 不够时显示【🔄 Fallback 补充材料】.
2. 应证评分: 每个 PDF 都显示 `应证评分: 0.XX (step2 hits N/M)`. 从 manifest.step2_score 读取.
3. 时效性: DOI 永久 / GLOBOCAN 时效差异 / NHC 政府文件 / 会议摘要 1-2 年.

升级: `h_column_builder.build_h_md_v6()` 新增 `scan_pn_x_dir` + `calculate_main_score` + `identify_link_eternality`.

**根因 bug**: 旧 `fallback_triggered` 字段基于 `main_n_highlights < min_main` (高亮图数量), 不是应证评分.
导致 P3-2 (main_score=1.0 但 triggered=True) 错误显示【🔄 Fallback 补充材料 (main 不足以应证时启用)】.

修复: 6 个 manifest 旧标记触发修正 (P3-2, P3-4, P4-4, P5-1, P5-16).
`calculate_fallback_score()` 加政府文件分支 (卫健委/令汇编/nhc/gov/regulation → 0.75).

## v6.x — Fallback 完整显示 (用户: "main 应证评分低的, 是不是有必要的 fallback")

根因 #1: `scan_pn_x_dir` 漏了 `manifest.fallback_pdfs` 字段 — 该字段含 Pn-x 目录外的引用
(跨标号: P4-3 引 P4-1/P4-2), 之前 fb 字段只扫本目录 `_fallback_/_fb_` PDF 文件名.
结果: P3-1 有 2 个 fallback 但 H 列显示 0; P4-3 有跨标号引用但 H 列显示 0.

根因 #2: 当 `main_score < 0.7` 但 `fallback_triggered=False` 时, H 列不显示 fallback.

根因 #3: 评分低时 H 列没有任何警告说明.

根因 #4: `markdown_to_rich_text` 的 regex `\[([^\]]+)\]\(([^)]+)\)` 用 `[^)]+` 匹配 URL,
但 DOI `10.1016/S0140-6736(25)00403-9` 含 `(25)`, 在第一个 `)` 截断 — H25 显示重复 `00403-9)`.

修复:
1. `scan_pn_x_dir` 升级: 解析 manifest.fallback_pdfs (跨标号 → fb_cross_refs).
2. `build_h_md_v6` fallback 块升级: 3 个触发条件 (fallback_triggered=True / main_score<0.7 / fb_cross_refs 非空).
3. 加【⚠️ 应证评分低】段 (main<0.7 且无 fb 时, 显示 found/missing 数据点).
4. `calculate_fallback_score` 重写: 跨标号优先 (target_score), 本地用文件名推断.
5. `markdown_to_rich_text` 重写: 手写 parser 处理嵌套括号.

## v7.0 — 语义等同性推理 (用户: "P3-3 例子: 14.4 vs 14.4%")

根因: 旧 v6 算法只做精确文本匹配, 14.4% vs 14.4 字符不同就标 missing.

修复: `numerical_equivalence_variants()` 生成数值等价变体:
- `14.4` → `['14.4', '14.40', '14.400', '14.4%', '14.40%', '14.400%']`
- `27.9` → `['27.9', '27.90', '27.900', '27.9%', ...]`

`compute_semantic_alignment_score()` 计算最终评分 (同一数值只要任一变体命中即 found).

效果:
- P3-3: 0.44 → **1.00** (21 个等价)
- P5-17: 0.58 → 0.77 (19 个等价)
- P5-18: 0.64 → **0.95** (24 个等价)
- 总: 217 个等价命中跨 27 行

H 列加【🧠 语义等同性推理】段显示每个等价变体.

## v7.1 — main 完整应证 + PDF 应证位置 (用户: "P3-2 main 文件已找到, 应证评分应该是满分")

升级:
1. 满分标注: `main_score ≥ 1.0` → 应证评分后加 `⭐满分`.
2. PDF 应证位置: manifest.found_data_point_locations 存每个 found_data_point 的 `{page_no, text_snippet}`.
3. 推理链: 显示 PPT 引文 → PPT 语义 → main PDF 应证位置 (页 + 上下文).

P3-2 例:
```
应证评分: 1.00 ⭐满分 (step2 hits 4/4)
✅ main 完整应证 PPT 内容 ⭐满分
📍 main PDF 应证位置 (核心数据):
  ✓ '46.6' → page 3: （二）主要目标。到2030年...总体癌症5年生存率达到46.6%
```

## v7.3 — 完整 5 步推理链 (用户: "还在用关键词匹配" — 用户最强烈反弹)

**这是用户最关键的反馈**: H 列只列 found data points 列表, 没显示完整推理链.

修复: 【🎯 应证推理】段重写为 5 步:
1. PPT 标号指向位置 (视觉): shape 位置 + 类型 + 视觉文字
2. PPT 视觉内容 (完整信息要素): 视觉得到的文字/图表/表格数据
3. 推理 (信息要素匹配): 提取需要匹配的数据点和文字
4. main PDF 应证位置 (语义推理匹配): PDF 找到的 page + context
5. 推理结果: ✅/⚠️/❌ + 满分标注

**排序优化 (v7.4)**: 应证位置按 mOS/PFS/HR/survival 关键词优先 → 百分比 → 大数字.
例: P5-15 (Yau PLS) 应证位置优先显示 "23.7 months" (mOS 数据), 不是 "15" "15%".

P3-2 例:
```
① PPT 标号指向位置 (视觉): 《健康中国行动——癌症防治行动实施方案（2023-2030年）》(P3 右半区主标题文字框)
② PPT 视觉内容 (完整信息要素): 中央大字目标: 到2030年我国总体癌症5年生存率达到 46.6%
③ 推理 (信息要素匹配): 需在 main PDF 中找到 2023, 2030, 46.6
④ main PDF 应证位置 (语义推理匹配):
  ✓ '46.6%' → page 3: （二）主要目标。到2030年...总体癌症5年生存率达到46.6%
  ✓ '2023' → page 1: 关于印发健康中国行动...
⑤ 推理结果: ✅ main 完整应证 (⭐满分)
```

## v7.6 — 多层级 PDF 下载链接 (用户: "缺 PDF 文件的下载链接")

新函数: `get_publisher_pdf_urls(doi, journal)` 根据 DOI 模式返回多个 PDF 直链.

17 个出版商模式映射:
- 10.1016/* → ScienceDirect + Lancet 官网
- 10.1056/NEJM* → NEJM 全文 + PDF
- 10.1038/* → Nature
- 10.1002/* / 10.1111/* → Wiley
- 10.1200/JCO* → ASCO 全文 + PDF
- 10.1158/* → AACR
- 10.1053/j.gastro* → Gastroenterology
- 10.1186/* → BMC
- 10.1371/* → PLOS
- 10.1093/* → Oxford
- 10.3322/caac* → CA Cancer J Clin
- 10.1097/* → LWW
- 10.1177/* → SAGE
- 10.18632/* → Oncotarget
- 10.3389/* → Frontiers

下载链接段结构 (3 类互不重复):
- 📥 出版商 PDF 直链 (基于 DOI 模式)
- 🔍 数据库搜索 (PubMed + Europe PMC)
- 🌐 DOI 通用链接 + OpenAccess

每个 Pn-x 4-8 个真实可点击链接.

## 关键经验 (适用所有未来 H 列写作)

1. **H 列不是"信息填表", 是"完整推理展示"** — 用户期望看到 PPT→信息要素→PDF 的完整过程, 不是 found data points 列表
2. **每条修正指令背后都是一类问题** — "缺 PDF 下载链接"=下载链接缺失类; "还在用关键词匹配"=推理链展示不充分类; 不能逐条修, 要识别一类
3. **AGENTS.md 铁律 #29-#35 是这次进化的产物** — 6 次迭代沉淀 7 条根因级铁律
4. **算法沉淀 vs 表面修复** — 用户每次都要求"根因修正", 不能只满足症状修复

## 关联技能

- `feishu-h-column-v2-template` — H 列 9 段必含 (主结构)
- `feishu-h-column-schema` — 飞书 H 列 schema
- `via54medit-anno2ppt-phase7` — L4 应证推理机 (4 维要素 + 集合结论)
- `via54medit-architecture-honest-status` — 设计 vs 已实现 诚实声明