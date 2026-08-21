---
name: via54-highlight-strict
description: |
  TMA文献整理 PDF highlight 严格规则与禁止红线 (v3 FINAL 对齐, 2026-08-13 全量交付定稿)。
  触发词: "highlight" / "做黄线" / "标注" / "highlight PDF" / "应证段"
  
  🚨 核心禁止规则（高压红线，违者用户暴怒）:
  - 禁止 highlight 文章标题（paper title）
  - 禁止 highlight 作者名称（author names）
  - 禁止 highlight PDF 中的文献引用/参考文献列表（bibliography, references）
  - 禁止 highlight 关键词/单一数字 — 必须是支持 slide 的完整句子/段落
  - 禁止复制同一文献其他 Pn-x 的 highlight — 每个 Pn-x 按自己 slide 选句
  - 只允许 highlight 正文应证内容段落（method / result / discussion / data / findings）
---

# via54-highlight-strict v3 FINAL (2026-08-13 全量交付定稿)

> 机制权威版本: `via54medit-literature-pipeline/references/highlight-mechanism-v3-final.md`
> 算法代码: `via54medit-literature-pipeline/scripts/hl_lib.py`(25 用例单测)

## 🚨 五步标准流程（强制顺序）

1. **还原 PDF** — 从干净 `{Pn-x}_main.pdf` 出发, hl_lib 先清除旧 annots
2. **PPT 导出全部图片** → `slide_pp_NNN.jpg`(扩充版, 引用文字清晰)
3. **PDF 渲染图片** → fitz `get_pixmap()`(禁止 pdftoppm, cropbox≠0 时偏移 ~8pt)
4. **视觉对照选句** → PPT slide 视觉内容 ↔ PDF 页面, 选出**整句/整段**应证内容
5. **hl_lib 画 rect** → `highlight_sentences()` 逐行精确 rect, 渲染 + 验证

## 🚨 Highlight 禁止内容（高压红线）

以下内容**绝对禁止**画黄线，违者重做：

| 禁止类型 | 示例 |
|---------|------|
| 文章标题 | "Thrombotic Microangiopathy: A Review" |
| 作者名称 | "John Smith, MD" / "James N. George" |
| 期刊名+年份 | "N Engl J Med. 2006;354:1927" |
| DOI / DOI号 | "10.1056/NEJMoa2006" |
| 参考文献列表 | "References" / "Bibliography" 下的任何条目 |
| 页眉/页脚 | 期刊名、页码、running title |
| 作者行/机构行 | "From the Department of..." |
| 引用编号 | 句尾 `[1,2]`、句中 `[14,15]`(句子定义时截断在引用前) |
| **关键词/单一数字** | 只画 "14.4%" 或 "median OS" 几个字 |
| **图表标题**(除非图表即应证对象) | 纯 Figure/Table 标题行 |

## ✅ 只允许 highlight 的内容

- **正文完整句子/段落**：方法描述、结果数据、讨论内容(整句从首词到句末标点)
- **支持 slide 引用的图表说明**：Figure 1、Table 2 描述性标题(仅当图表即应证对象)
- **统计数据句子**：含 p值、HR、OR、CI、数值结果的完整句子
- **关键结论**：作者给出的临床建议或研究发现(整句)

## 🎯 内容规则(语义验收, 不可自动化替代)

1. 每个 Pn-x 必须对照**其对应 slide 的视觉内容**选句(同一文献的不同 Pn-x 禁止复制 highlight)
2. 高亮必须是支持 slide 的**完整句子/段落/图表说明**, 禁止关键词/单个数据
3. 句子被图表/双栏打断时, 选连续物理布局的子段(避免跨栏孤立色块)
4. 中文 PDF 用全角标点句子原文匹配; 句子文本必须保留 PDF 跨行连字符
5. 页面重复文本用 `(text, occurrence)` 元组消歧

## ⚙️ 样式与技术规范（唯一权威值）

| 项 | 值 | 禁止 |
|---|---|---|
| 颜色 | RGB(255, 217, 0) = (1.0, 0.85, 0.0) | RGB(255,230,100) 旧值 |
| 透明度 | **0.45** | 0.8 压暗文字 / 1.5pt 细线旧法 |
| annot 类型 | PDF Square(rect) `add_rect_annot` | `add_highlight_annot`(自动扩展 ~3.7pt) |
| 行级覆盖 | 每行一个 rect(行距法, 最小 8pt) | 大段色块 |
| 渲染 | fitz `get_pixmap()` 100dpi, 零补偿 | pdftoppm / offset 参数 |
| 验证 | 直接迭代 `page.annots()` | `list(annots())`(假损坏误报) |

## 📋 每步产出

| 步 | 动作 | 产出 |
|----|------|------|
| Step 1 | 还原干净 PDF + 清旧 annots | `{Pn-x}_main.pdf` |
| Step 2 | PPT导出JPG | `_ppt_renders/slide_pp_NNN.jpg` |
| Step 3 | PDF渲染JPG | `{Pn-x}_highlight_pages/page_NNN.png` |
| Step 4 | 视觉对照选句 | 句子脚本 `hl_p{Pn-x}.py` |
| Step 5 | hl_lib 画 rect + 验证 | `{Pn-x}_highlight.pdf` + 根目录仅高亮页图 + `verify.json` |

## 🔍 验证(交付前必做)

1. **像素泄漏检查**: 每个 annot rect 内黄色像素 > 0(R>180, G>160, B<170); TMA 全量 1325/1325 通过
2. **页号一致性**: 根目录图片页号 == annots 页号
3. **视觉验证**: 整句覆盖(句首→句末标点) / 无标题作者引用覆盖 / 文字可读 / 无偏移
4. **批量后二次重跑**: 偶发 annots 绑定问题, 重跑一遍即修复
