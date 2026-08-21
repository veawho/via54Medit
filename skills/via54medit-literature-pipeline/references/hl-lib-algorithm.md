# hl_lib 精确逐行 highlight 算法(2026-08-13 v3 FINAL 定稿)

> 权威代码: `scripts/hl_lib.py`(本 skill 内, 与项目交付版一致)。
> 句子脚本模板: `scripts/hl_pnx_examples/hl_p11-1.py` 等 105 例。
> 完整规范: `references/highlight-mechanism-v3-final.md`。

## 一句话

```
句子定义脚本(hl_p{Pn-x}.py)
  → hl_lib.highlight_sentences()   # 清除旧 annots + 逐句逐行精确 rect
  → render_fitz.py                 # fitz 渲染 PNG(无偏移)
  → copy_hl_images.py              # 根目录只留高亮页图片
  → verify.json(记录句子/md5/渲染)
```

## 样式参数(唯一权威值)

| 项 | 值 | 禁止 |
|---|---|---|
| fill/stroke 颜色 | RGB(255, 217, 0) = (1.0, 0.85, 0.0) | 其他黄色 |
| opacity | **0.45** | 0.8 压暗文字 |
| annot 类型 | PDF Square(rect) `add_rect_annot` | `add_highlight_annot`(自动扩展 ~3.7pt) |
| border | width=0 | 有边框 |
| 行高 | 行距法: next_y0 - cur_y0 - 1, 最小 8pt, 最大 20pt | 固定高度 |
| x 收窄 | 行首尾各 0.6pt, pad 0.35pt | 无收窄 |
| 句首对齐 | rect x0 = 首字符 x0 - 0.5 | 吞首字符 |
| 句尾对齐 | x1 = min(句尾字符 x1+0.5, 同行下一字符 x0-0.5) | 盖句后引用编号 |

## 核心函数

### canon / canon_keys(文本规范化)
- 全角→半角(标点/字母/数字)、去空白(\xa0/\xad/\u200b 等)、连字展开(ﬁ/ﬂ/ﬀ/ffi/ffl→fi/fl/ff/ffi/ffl)
- 德语 PDF 变音组合 `€u/€o/€a → ü/ö/ä`(rawdict 组合形式)
- 中文 PDF 字体编码变体标点:`ꎬ→,  ꎮ→.  ꎻ→;  ꎺ→:  ꎨꎩ→()  ꎰ→,  ꎯ→.` 等
- **`\x01 → ≥`**(部分期刊 ToUnicode 映射)
- `canon_keys(text)` 返回 (norm_str, raw_idx), 支持规范化子串→原始索引映射

### page_char_stream(page)
`page.get_text('rawdict')` 逐字符流, 返回 (chars, text), chars=[(c, rect)] 按阅读顺序。
**禁止** `get_text('text')` + `search_for()`(合并/丢失字符 bbox, 无法逐行精确对齐)。

### locate_sentence(text, sentence, occurrence=0)
- 规范化匹配, 返回原始 (start, end) 字符索引; 找不到返回 None
- **occurrence 参数**: 页面重复文本消歧(第 occurrence 次匹配, 0-based)
- 句子可传 `(text, occurrence)` 元组给 highlight_sentences

### locate_sentence_all(text, sentence)
返回**全部**匹配索引列表(排查歧义用)。

### sentence_rects(chars, start, end, pad=0.35)
按行分组 + 逐行 rect:
1. **同行判定**: y0 差 < **4.0pt**(2.5 会把同一视觉行 bbox 微差拆成两行)
2. **离群行过滤**: ≤2 字符且与主体行 y 中位数差 > 15pt 的行丢弃(PDF 文本层句号跳位等错位字符)
3. **行高**: `next_y0 = min(所有 y0 > 本行y0+6 的字符 y0)` —— 用 min 而非流内首个(避免本行内 bbox 偏大的字符被误当下一行)

### highlight_sentences(pdf_path, out_path, sentences, verbose=True)
- `sentences = {page_idx(0-based): [str | (str, occurrence)]}`
- **先清除已有 annots 再重加**(幂等, 批量重跑安全)
- 页索引越界 → 'BAD PAGE' 保护, 不抛异常
- 句末标点判定**必须含 ASCII '.'**: `if last_ch not in '。！？!?.'` —— 漏掉 `.` 会让英文句子误入末行收窄逻辑(空 rect / 错误收窄, 曾致 P5-3 崩溃)
- 末行收窄 + 引用编号保护 + 首行对齐(见样式参数)
- `offset` 参数已弃用, 恒 (0,0)

## 渲染(fitz, 无偏移)

```python
pix = doc[pi].get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))
```

- **统一 fitz `get_pixmap()`**: annots 与文字同坐标系, 零补偿
- **禁止 pdftoppm**: 对 cropbox 原点非零的 PDF 偏移 ~8pt(P4-4/P5-2/P11-5/P15-1/P23-3/P31-1/P3-2/P4-2 曾全部中招)
- **禁止 offset 参数**: offset 是 pdftoppm 时代的补偿; fitz 渲染下残留 offset 反而引入偏移(P15-1 曾盖 "Recent findings" 小标题)

## 验证(交付前必做)

1. **像素泄漏检查**: 渲染 PNG, 每个 annot rect 内黄色像素 > 0(阈值 R>180, G>160, B<170)
2. **页号一致性**: 根目录图片页号 == annots 页号(copy_hl_images.py 保证)
3. **annots 完整性**: 验证时**直接迭代 `page.annots()`**; `list(annots())` 在 PyMuPDF 该版本报 "not bound to any page" 假损坏(文件本身完好)
4. **批量后二次重跑**: 批量脚本生成的文件偶发 annots 绑定问题, 重跑一遍即修复; 交付前用独立进程逐文件验证

## 单元测试

```bash
python3 scripts/test_hl_lib.py   # 25 passed, 0 failed
```

覆盖: canon 规范化(全角/连字/\x01/€变音/中文标点变体)、canon_keys 索引映射、
locate_sentence(occurrence 消歧/多匹配/规范化匹配/空句子)、sentence_rects(行分组/行距/
离群过滤/微差合并/空区间)、highlight_sentences(页越界/元组/空句子/找不到)。

## 批量重跑

```bash
python3 scripts/rerun_all.py
```

- 脚本来源: 优先 toolkit 沉淀目录(scripts/hl_pnx_examples/), 回退 /tmp
- **按 basename 去重**(双目录不重复跑)
- **必须有 `if __name__ == "__main__"` 保护**(无保护时 import 即全量重跑, 曾重复跑 210 次)
- 逐个执行 + 渲染 + 失败收集(rerun_fail / rerun_all.log)
