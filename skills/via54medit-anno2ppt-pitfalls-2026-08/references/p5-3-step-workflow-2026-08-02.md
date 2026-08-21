# P5 3 步验证工作流完整实录 (2026-08-02)

## 背景

用户纠正了 Pn-x 文献标注的执行顺序：
1. 旧流程：数据体检 → 缺文件修复 → 信息要素推理 → bbox 高亮 → 写飞书 H 列
2. 新流程（用户纠正）：① PPT 视觉理解 → ② PDF highlight 对齐验证 → ③ 五方校验

## 步骤 1: PPT 视觉理解

**工具**: `ppt_understand.py` (v2 语义驱动, 2026-08-02 新建)

**核心函数**:
- `extract_ppt_slide(ppt_path, slide_num)` → 17 shapes, 1 表格 14x5
- `find_citation_marks_v2(ppt_path, slide_num)` → 语义提取 18 标号
- `get_ppt_mark_context(ppt_path, slide_num, N)` → 单标号上下文
- `build_ppt_vision_report(ppt_path, slide_num, [1..18])` → 18/18 匹配

**提取规则（排除期刊年份/ISSN/疗效数据噪音）**:
1. 方案名称列 / 药物列中「中文词+数字」 → 仑伐替尼5、奥沙利铂+5-FU+亚叶酸钙2、索拉非尼3,4
2. 「方案+数字」 → T+A方案8,9、双达方案11、雷管方案17,18
3. 「O+Y+数字」 → O+Y15,16
4. 标题横幅 → uHCC一线治疗方案1

**排除**: 泛化正则（会把期刊年份/ISSN/疗效数据 mOS 12.1月 误当标号）

**输出示例 (P5)**: 标号 1 → 标题横幅 "uHCC一线治疗方案1"; 标号 2 → Row1 药物 "奥沙利铂+5-FU+亚叶酸钙2" → EACH → mOS 6.47月; ...

## 步骤 2: PDF Highlight 对齐验证

**工具**: `pdf_understand.py verify_highlight_alignment(pdf_path, highlight_path, ppt_context, data_points)`

**输出**: aligned (bool) + score (found/total) + issues + matches

**P5 验证结果 (15/18 可验证)**:
- 全部 aligned=True (score 0.60-1.00)
- P5-16 (Galle JCO 2026 会议摘要) score=0.40 → 内容有限
- P5-17 (Bruno ESMO 1494P) → skip (PDF 不存在)

## 步骤 3: 五方校验

| 维度 | 来源 | 说明 |
|------|------|------|
| ① PPT 引文位置视觉+文本理解 | 步骤 1 输出 | 标号位置、表格行/列、文本内容 |
| ② PPT 中的文献引用字段 | 表格 D 列 | 作者、期刊、年份 |
| ③ PDF 全文内容 | pdf_understand.py Docling 解析 | 文本、表格、图片 |
| ④ PDF 的 Highlight 区域 | 步骤 2 输出 | highlight 区域、位置、对齐 |
| ⑤ H 列（PPT 与 PDF 内容对齐 + 文献信息 + 下载链接） | 表格 H 列 | 最终写入飞书 |

## 算法修复 (2026-08-02)

### 修复 1: extract_ppt_data_points 假阳性

**问题**: 百分比变体过度生成 — RATIONALE-301→301%, IMbrave150→150%, mOS 13.6月→13.6%

**3 条修复规则**:
1. 数字 > 100 不生成 `%` 变体（避免试验名 301/150/310 误生成）
2. 中文单位后缀（月/年/天/人/例/周/个）不生成 `%` 变体（避免 mOS 13.6月→13.6%）
3. 纯个位数 (0-9) 跳过，除非带小数点或 `%`（避免 5/2/7 到处匹配）

### 修复 2: Docling segfault → PyMuPDF fallback

**问题**: P5-12 (Zhao STTT 2025, 2.5MB) Docling segfault 崩溃

**修复**: `parse_pdf_with_docling()` 非 0 退出码时自动 fallback 到 PyMuPDF 文本抽取

### 修复 3: bbox 高亮从 797 降噪到 5 个精准匹配

**问题**: 「5」「2」「7」个位数匹配 797 个表格单元格 → bbox 高亮是半页黄色

**修复**: 修复 1 的规则 3 消除个位数 → 只有 6.47 和 OS 两个有意义数据点 → 5 个精准 OS 匹配

## 工具链

| 工具 | 单测 | 状态 |
|------|------|------|
| `ppt_understand.py` | 8/8 ✅ | NEW (2026-08-02) |
| `pdf_understand.py` | 12/12 ✅ | 修复 3 个根因 |
| `citation_sync.py` | 26/26 ✅ | 不变 |
| `link_health.py` | — | 不变 |
| 合计 | 46/46 ✅ | — |

## 关键决策 (自主推断, 未问用户)

| 标号 | 问题 | 决策 |
|------|------|------|
| P5-1 | 卫健委指南无DOI | NHC 官网 + Wayback 存档 |
| P5-13 | Chen CCR 2024 付费墙, 2KB 占位 | ⚠️ 无法下载, Wayback 元数据 |
| P5-16 | Galle JCO 2026 71KB 会议摘要 | 标注【内容有限, 仅摘要】 |
| P5-17 | Bruno ESMO 1494P 无 PDF | ⚠️ 跳过, 走 fallback |

## AGENTS.md 铁律新增 (#26-#28)

- #26: PPT 视觉理解是 Step 1 起点, 禁止泛化正则
- #27: 3 步流程不可逆 (①PPT→②Highlight→③五方校验)
- #28: 信息要素推理取代关键词匹配