# TMA 文献整理 — Highlight 机制与算法规范 v3 FINAL(via54Medit 复现基线)

> 版本:v3 FINAL(2026-08-13 全量交付后定稿)
> 覆盖:106 个 Pn-x 全量重做、全部视觉/像素验证、经验沉淀。
> 目标:via54Medit 与算法均可**独立复现**同一套 highlight 结果。

---

## 0. 复现一句话总结

```
句子定义脚本(/tmp/hl_p{Pn-x}.py)
  → hl_lib.highlight_sentences()   # 清除旧 annots + 逐句逐行精确 rect
  → render_fitz.py                 # fitz 渲染 PNG(无偏移)
  → 根目录只留高亮页图片
  → verify.json(记录句子/md5/渲染)
```

---

## 一、目录结构规范(交付基线)

每个 Pn-x 文件夹根目录**只包含**:

| 文件 | 说明 |
|---|---|
| `{Pn-x}_highlight.pdf` | 高亮 PDF(清除旧 annots 后重加) |
| `{Pn-x}_highlight_pNNN.png` | **有 highlight 的页面**图片(无高亮的页面不放入根目录) |
| `{Pn-x}_highlight_pages/` | 全部页面图(含无高亮页,完整存档) |
| `{Pn-x}_main.pdf` | 源文献 PDF(与 slide 引用一致,md5 记录在 verify) |
| `{Pn-x}_verify.json` | 验证记录:md5/pages/title/highlights 句子/渲染参数 |

## 二、样式规范(via54Medit 渲染参数)

| 项 | 值 | 备注 |
|---|---|---|
| 颜色 | RGB(255, 217, 0) = (1.0, 0.85, 0.0) | 与 PPT 附件一致 |
| 透明度 | **0.45** | 0.8 会压暗文字,禁止 |
| annot 类型 | PDF Square(rect) | 禁用 add_highlight_annot(自动扩展 ~3.7pt) |
| 行级覆盖 | 每行一个 rect | 高度=行距(下一行 y0 - 本行 y0 - 1),最小 8pt |
| 水平精度 | 行首尾各收窄 0.6pt,pad 0.35pt | 不盖空白、不盖相邻字符 |
| 句首对齐 | 从行中开始时,rect x0 = 首字符 x0 - 0.5 | 不吞首字符 |
| 句尾对齐 | rect x1 = min(句尾字符 x1+0.5, 同行下一字符 x0-0.5) | 不盖句后引用编号 |

## 三、算法规则(hl_lib.py 可复现要点)

### 3.1 文本获取与规范化
- `page.get_text('rawdict')` 逐字符流(含 bbox)
- canon 规范化:全角→半角、ligature 展开(ﬁ/ﬂ/ﬀ/ffi/ffl)、去 soft-hyphen/nbsp、德语 €u/€o/€a→ü/ö/ä、中文 PDF 标点变体(ꎬ→, 等)、\x01→≥
- 句子定位:canon_keys 规范化子串匹配,返回原始索引区间

### 3.2 行分组(关键参数)
- 同行判定:y0 差 **< 4.0pt**(2.5 会把同一视觉行 bbox 微差拆成两行)
- **离群行过滤**:≤2 字符且与主体行 y 中位数差 > 15pt 的行丢弃——PDF 文本层错位字符(句号跳位)会产生孤立错误色块
- 行高:`next_y0 = min(所有 y0 > 本行y0+6 的字符 y0)`——用 min 而非流内首个,避免把本行内 bbox 偏大的字符误当下一行

### 3.3 句末标点判定(重要教训)
```python
if last_ch not in '。！？!?.' and last_ch != '.':   # 必须含 ASCII 句号!
```
- 漏掉 `.` 会让所有英文句子误入末行收窄逻辑:句号错位时产生空 rect / 错误收窄(曾致 P5-3 崩溃)

### 3.4 引用编号保护
- 句尾引用:`min(句尾x1+0.5, 引用x0-0.5)` 为末行 x1 目标(预加 0.6 抵消统一收窄)
- 句中引用(如 `[14,15]` 在句中):句子定义时截断在引用前,或换用无引用句子
- 句子文本必须保留 PDF 跨行连字符(thrombocyto-penia、de-scription、deple-tion)

### 3.5 渲染(偏移根因,最重要)
- **统一 fitz `page.get_pixmap()` 渲染**;annots 与文字同坐标系,零补偿
- **禁止 pdftoppm**:对 cropbox 原点非零的 PDF 偏移 ~8pt(P4-4/P5-2/P11-5/P15-1/P23-3/P31-1/P3-2/P4-2)
- **禁止 offset 参数**:offset 是 pdftoppm 时代的补偿;fitz 渲染下残留 offset 反而引入偏移(P15-1 曾盖 "Recent findings" 小标题)。offset 已从全部脚本移除,hl_lib 默认 (0,0)

## 四、质检流程(可复现)

1. **像素泄漏检查**:渲染 PNG,每个 annot rect 内黄色像素 > 0(阈值 R>180,G>160,B<170)
2. **页号一致性**:根目录图片页号 == annots 页号
3. **视觉验证**:vision API(SenseNova 6.8-flash-lite → M3 → GLM 降级)逐项检查:
   - 整句覆盖(句首→句末标点)/ 无标题作者引用覆盖 / 文字可读 / 无偏移
4. **annots 完整性**:验证时**直接迭代 `page.annots()`**;`list(annots())` 在 PyMuPDF 该版本会报 "not bound to any page" 假损坏(文件本身完好)
5. **批量后二次重跑**:批量脚本生成的文件偶发 annots 绑定问题,重跑一遍即可修复;交付前用独立进程逐文件验证

## 五、工具链清单(全部在 _highlight_toolkit/)

| 文件 | 用途 |
|---|---|
| `hl_lib.py` | 核心:canon/locate/sentence_rects/highlight_sentences |
| `render_fitz.py` | fitz 渲染全部页面 PNG(100dpi,page_NNN.png) |
| `rerun_all.py` | 批量重跑所有 /tmp/hl_p*.py(逐个执行+渲染+失败收集) |
| `hl_p{Pn-x}.py` | 句子定义脚本(dict {page: [sentences]} 或 SENTENCES+build) |

### hl_p{Pn-x}.py 统一模板
```python
#!/usr/bin/env python3
import sys
sys.path.insert(0, '/tmp')
from hl_lib import highlight_sentences, page_char_stream, locate_sentence

SRC = ".../step3_pdf下载_106目录/{Pn-x}_main.pdf"
OUT = ".../step4_highlight_106目录_合并DOI/{Pn-x}/{Pn-x}_highlight.pdf"

SENTENCES = [ ... ]  # 整句文本, 保留跨行连字符

def build():
    import fitz
    doc = fitz.open(SRC)
    S = {}
    for s in SENTENCES:
        for pi in range(len(doc)):
            chars, text = page_char_stream(doc[pi])
            if locate_sentence(text, s) is not None:
                S.setdefault(pi, []).append(s); break
        else:
            print('NOT FOUND:', s[:55])
    doc.close()
    return S

if __name__ == "__main__":
    highlight_sentences(SRC, OUT, build(), verbose=True)
```

## 六、完整复现步骤(从零)

```bash
# 1. 准备: 句子定义脚本(按 slide 视觉内容选整句, 禁止复制其他 Pn-x)
#    - 每个 Pn-x 一个 /tmp/hl_p{Pn-x}.py

# 2. 重跑全部(清除旧 annots + 生成新 highlight.pdf + fitz 渲染)
python3 /tmp/rerun_all.py          # 逐个执行, 失败记录到 rerun_fail.log
#    若批量后有 annots 假损坏: 再跑一遍 rerun_all.py 即可

# 3. 全量验证(独立进程, 直接迭代 annots)
#    a. annots 数 > 0 且 rect 可读
#    b. 每个 rect 内黄色像素 > 0
#    c. 根目录图片页号 == annots 页号
#    d. verify.json 含 highlights 句子记录

# 4. 根目录图片: 只复制有高亮的页面图
python3 copy_hl_images.py          # 见第七节规则

# 5. 视觉抽查(每 slide 区间至少 1 个): vision_check.py
```

## 七、根目录图片规则

- `{Pn-x}_highlight_pages/` 保留**全部**页面图(存档)
- 根目录只放**有 annots 的页面**图,命名 `{Pn-x}_highlight_pNNN.png`
- 无高亮页面图不放入根目录(用户明确要求)

## 八、内容规则(语义验收,不可自动化替代)

1. 每个 Pn-x 必须对照**其对应 slide 的视觉内容**选句(同一文献的不同 Pn-x 禁止复制 highlight——如 P25-2 与 P30-2 同文献但按各自 slide 选句)
2. 高亮必须是支持 slide 的**完整句子/段落/图表说明**,禁止关键词/单个数据
3. 禁止高亮:标题、作者、文献信息、页眉页脚、引用编号、图表标题(除非图表即应证对象)
4. 句子被图表/双栏打断时,选连续物理布局的子段(避免跨栏孤立色块)
5. 中文 PDF:全角标点句子原文匹配;超长页 PDF(P25-2/P30-2 16098pt)按 annots 坐标裁切验证

## 九、via54Medit 复现要点

via54Medit 若需复现同一效果,必须实现:
1. **渲染**:使用与 PyMuPDF 相同坐标语义的渲染器(正确应用 cropbox),或直接读取 annot 矩形坐标渲染
2. **样式**:fill RGB(255,217,0)、opacity 0.45、border 0
3. **高亮生成**:整句→逐行 rect(行距法),句首尾精确对齐,引用编号保护
4. **验证**:像素级黄色检测 + annots 页号一致性 + 视觉检查
5. **批量**:重跑幂等(先清 annots 再加),交付前二次重跑防绑定问题

## 十、经验教训清单(2026-08-13 全量修正)

| # | 现象 | 根因 | 修复 |
|---|---|---|---|
| 1 | 覆盖标题/作者/引用 | 早期批量版"大段色块" | 句子级重做+先清 annots |
| 2 | 颜色压暗文字 | opacity 0.8 | 0.45 |
| 3 | 偏移(盖空白/文字不全) | pdftoppm 对 cropbox≠0 PDF 偏移~8pt | fitz 渲染零补偿 |
| 4 | 无高亮色块 | 旧图残留/渲染竞态/句号错位空 rect | 全量重渲染+离群过滤 |
| 5 | 英文末行错误收窄 | 句末标点集合漏 ASCII `.` | 补 `.` |
| 6 | 句号跳位孤立色块 | 文本层句号 bbox 错位 | 离群行过滤 |
| 7 | annots 假损坏 | PyMuPDF `list(annots())` | 直接迭代验证 |
| 8 | P15-1 盖小标题 | 残留 offset 在 fitz 渲染下反向偏移 | 全部脚本移除 offset |
| 9 | 批量后 annots 绑定异常 | 保存/渲染竞态 | 二次重跑+独立进程验证 |
| 10 | 同一视觉行拆两行 | 分组阈值 2.5 过小 | 4.0 |
| 11 | 行高错取本行字符 | next_y0 取流内首个 | min()+6pt 阈值 |

## 十一、算法审查修复记录(2026-08-13 二次审查)

| # | 问题 | 修复 |
|---|---|---|
| 1 | `locate_sentence` 用 find() 只取首个匹配,页面重复文本歧义 | 新增 `locate_sentence_all()`(返回全部匹配)与 `occurrence` 参数;highlight_sentences 句子可传 `(text, occurrence)` 元组 |
| 2 | canon 未映射 `\x01`(部分期刊 PDF 的 ≥ 编码) | canon 增加 `\x01 → ≥` |
| 3 | highlight_sentences 页索引越界抛异常 | 增加 BAD PAGE 保护 |
| 4 | rerun_all.py 无 `__main__` 保护(import 即全量重跑) | 加 `if __name__ == "__main__"` |
| 5 | rerun_all.py 双目录扫描未按 basename 去重(重复跑 210 次) | 按 basename 去重(toolkit/scripts 优先) |
| 6 | 句子脚本未沉淀,依赖 /tmp | 全部 105 个脚本沉淀至 `_highlight_toolkit/scripts/`,rerun_all 优先从该目录扫描 |
| 7 | 单元测试缺失 | 新增 `test_hl_lib.py`(25 用例:canon/locate/rects/边界),全部通过 |

## 十二、测试套件

```bash
python3 _highlight_toolkit/test_hl_lib.py   # 25 passed, 0 failed
```

覆盖:canon 规范化(全角/连字/\x01/€变音/中文标点变体)、canon_keys 索引映射、
locate_sentence(occurrence 消歧/多匹配/规范化匹配/空句子)、sentence_rects(行分组/行距/
离群过滤/微差合并/空区间)、highlight_sentences(页越界/元组/空句子/找不到)。

## 十三、雷管方案对齐记录(2026-08-13 交付基线)

「雷管方案」= Pn-x 目录交付结构,最终基线:

```
step4_highlight_106目录_合并DOI/{Pn-x}/
├── {Pn-x}_highlight.pdf           # 高亮 PDF(先清旧 annots 再生成)
├── {Pn-x}_highlight_pNNN.png      # 根目录: 仅"有高亮"的页面图
├── {Pn-x}_highlight_pages/        # 全部页面图(存档, 含无高亮页)
├── {Pn-x}_main.pdf                # 源文献(与 slide 引用匹配, md5 记录)
└── {Pn-x}_verify.json             # md5/pages/highlights 句子/annot_count/下载状态
```

对齐验证(全量):
1. 根目录图片页号 == highlight.pdf 的 annots 页号(copy_hl_images.py 保证)
2. annots 数 == verify.json annot_count
3. 每个 annot rect 内黄色像素 > 0(1325/1325 通过, 仅 P12-3 占位除外)
4. highlight 句子可在 main.pdf 中定位(句子源自该 PDF)

本轮同步修正:
- P12-1: 脚本改用 P12-1_main.pdf(King's 版) + 自动定位页 + 表格行 0.45 样式
- P23-2: 句子对照 slide23 引用2 重新选句(共识 incidence 句)
- P23-8: 用户提供 Lazana TA-TMA 文献重做
- P13-1: 标记下载不匹配(待用户提供焦扬论文)

via54Medit 同步要求:根目录图片规则(仅高亮页)、verify 字段(annot_count/download_status)、
文献下载校验(下载后 md5+页数+首页标题与 slide 引用匹配, 占位必须标注)。

## 十四、本地表与在线表对齐(2026-08-14 最终规则)

### 核心规则(用户明确要求)
**本地表与在线表在逻辑、列、规则上与雷管方案完全一致**:
- 列完全相同(14 列,见下);两表逐行同数据
- 唯一数据源 = 雷管方案目录(step4_highlight_106目录_合并DOI/{Pn-x}/) + verify.json + 引用表
- 每行一个 Pn-x(106 行);Pn-x 编号、引用文本、MD5/页数/图片数均从雷管方案实测派生

### 统一列(两表相同)
PN | 幻灯片 | 引用序号 | 引用 | PPT内容 | 文献标题 | 作者 | 已Highlight |
高亮句子数 | 高亮图片数 | PDF大小KB | MD5 | 页数 | 文献状态

### 生成(自动化, 保证一致)
```bash
python3 _highlight_toolkit/pipeline/align_tables.py
# 输出: _citation_table/tma_citation_table.csv(本地表)
#       _citation_table/tma_citation_table_feishu_ALIGNED.csv(在线表, 同列同数据, 回传飞书)
```

### 规则细节
- 引用文本: 来自引用表(slide/num → 文本), 与 PPT 提取(step2)一致
- PPT内容: verify.json slide_topic(优先 _highlight_plan.md 应证上下文 → 在线表 D 列 → 人工)
- MD5/页数/PDF大小: main.pdf 实测; 高亮图片数: 根目录 highlight_p*.png 计数
- 已Highlight: annots>0; 文献状态: OK / 待提供(P12-3 等)
- P31-8/P31-9 不存在; slide31 重复编号(Laurence/Jiang)以 106 Pn-x 体系为准
