---
name: via54-tma-literature-workflow
description: |
  TMA（血栓性微血管病）文献整理专项工作流。覆盖 PPT 引用→PDF 映射的视觉核查、highlight 严格规则、中文文献处理。适用：任何 TMA 医学幻灯片文献整理项目（如 TMA临床路径诊断与鉴别.pptx）。
category: via54
---

# via54-tma-literature-workflow (v1.2, 2026-08-14 对齐 v3 FINAL + 8列表)

> v1.2 变更: Highlight 机制切换到 hl_lib(v3 FINAL, 废除关键词 span 细线代码);
> 在线表切换到雷管方案 8 列; 合并规则见 `via54medit-literature-pipeline/references/merge-rules.md`;
> 完整规范见 `via54medit-literature-pipeline/references/`。

## ⚠️ P0 铁律：B列 = PPT页码 = A列Pn-x的n值 (2026-08-10用户暴怒纠正)

**这是本项目最高频错误根源。已导致18处B列修正。**

```
A列 = PN编号（格式：P{幻灯片号}-{序号}，如P4-2，P23-1）
B列 = PPT页码（必须等于A列的n值！P4-2 → B=4，P23-1 → B=23）
C列 = 标记（PPT内引用编号，是另一个独立编号系统）
```

**错误示例（修前 → 修后）**：
| Row | PN | 修前B | 修后B | 原因 |
|-----|-----|-------|-------|------|
| 5 | P4-1 | 3 | 4 | P4-1的n=4 |
| 52 | P23-1 | 26 | 23 | P23-1的n=23 |
| 53 | P23-2 | 24 | 23 | P23-2的n=23 |
| 60 | P23-9 | 26 | 23 | P23-9的n=23 |
| 91 | P30-1 | 14 | 30 | P30-1的n=30 |

**⚠️ 禁止假设**：不能从C列（标记）反推B列。B列必须等于A列Pn-x的n值。

## ⚠️ 项目确认：两个飞书表格

| 项目 | 飞书URL | 内容 |
|------|---------|------|
| **TMA（血栓性微血管病）** | `https://hackhealth.feishu.cn/sheets/Nf84sqBbqh0zcjtUCAZcGRkknMe` | 当前项目，106行，8列与雷管方案完全一致 |
| HCC（肝癌项目） | `https://hackhealth.feishu.cn/sheets/FEISHU_SHEET_TOKEN(已轮换,勿复用)` | 雷管方案模板来源，不要混淆 |

**TMA飞书在线表（2026-08-14 定稿）**：
- **URL**: https://hackhealth.feishu.cn/sheets/Nf84sqBbqh0zcjtUCAZcGRkknMe
- **Token**: `Nf84sqBbqh0zcjtUCAZcGRkknMe`
- **列结构（雷管方案 8 列）**: A=PPT页, B=第几条, C=引用语义（上下文）, D=PPT中的文献引用 完整字段, E=DOI, F=类型, G=对应PDF文件, H=来源链接 → 阅读全文
- **数据**: 106行（本地表 + verify + CrossRef DOI + H列卡片格式）
- 生成/写入: `via54medit-literature-pipeline/scripts/align_tables.py` + `leiguan_table.py --write`
- 旧表 P41bsK7t8hMJHntV936cggbxnve / AuPvsIPE1hLMQ2tAP5acl9Ydnof 已被取代, 勿再引用

**HCC表（另一项目，勿混淆）**：`https://hackhealth.feishu.cn/sheets/FEISHU_SHEET_TOKEN(已轮换,勿复用)`

**lark-cli写操作必须用user身份**：不加 `--as bot`，否则报 `91403 Forbidden`（bot身份对cells-set无效，但drive+delete可以）。读操作bot/user均可。

## v2.0 (2026-08-10): 新飞书表 + 重建 SOP + C列6组错误记录

### 2026-08-10 新飞书表(已被 2026-08-14 8列表取代)
- **URL**: https://hackhealth.feishu.cn/sheets/P41bsK7t8hMJHntV936cggbxnve
- **⚠️ 已废弃**: 2026-08-14 起在线表 = 雷管方案 8 列 Nf84sqBbqh0zcjtUCAZcGRkknMe(见上节)

### 重建新表 SOP（当旧表损坏或API写权限问题时）
1. 读本地CSV + _pnx/verify.json 构建完整数据
2. `lark-cli sheets +create --title 'TMA文献整理2026'`
3. 批量写入：`cells_2d = [[{"value": str(cell)} for cell in row] for row in all_rows]`
4. 验证：拉取前3行确认header正确

### C列6组错误（已在新表修正）
P5-2 C=4→2, P5-3 C=6→3, P9-2 C=1→2, P12-1 C=2→1, P18-1 C=2→1, P30-1 C=2→1, P31-3 C=3→2

---

## 已知完成状态（v2.0, 2026-08-10完成）

- ✅ **104/106** 已Highlight（_pnx目录中已有highlight.pdf）
- ❌ **3** 缺失PDF无法Highlight：P12-3（UpToDate付费）、P25-8（P22-3 Laurence 2016重复）、P31-2（P31 Laurence 2016重复）
- ✅ 飞书表已重建（F列✅=103，F列❌=3）

**批量highlight生成**：62+个同时处理会导致PyMuPDF SIGSEGV崩溃。必须单entry处理+立即close()。
```python
def robust_highlight(pn):
    doc = fitz.open(src)
    # ... process ...
    hl_doc.save(dst)
    hl_doc.close()
    doc.close()  # 立即关闭，不能等
    return size > 5000
```

## 铁律：Pn-x编号 ≠ PPT引用序号（不变）

```
TMA项目/
  _1_ppt/
    _1_original/TMA临床路径的诊断与鉴别.pptx
    _2_expanded/              ← 扩充尺寸 PPT（灰色背景+白字引用区）
    _3_images/slide_pp_NNN.jpg  ← 扩充版截图书证
  _ppt_renders/
    slide_pp_NNN.jpg          ← 扩充版 PPT 图片（PPT视觉对照真值）
    slide_NNN.jpg             ← 原版 PPT 图片
  _pnx/                      ← 每篇独立目录
    P{n}-{m}/
      main.pdf                ← 唯一真实来源（⚠️编号≠PPT引用序号！）
      _pdf_images/page_NNN.jpg  ← PDF 渲染图（highlight 对照用）
      highlight.pdf            ← 黄线标注版本
  _citation_table/
    tma_citation_table.csv    ← 引用表（PPT引用真值）
```

## ⚠️ 铁律：Pn-x 编号 ≠ PPT 引用序号

**这是整个 TMA 文献整理最常见的错误根源。**

Pn-x 目录编号是**下载顺序**，由 fetch_plan 或 DOI 解析顺序决定。
PPT 引用序号（如 Slide 4 的"引用② Luzzatto 2024"）是**另一个独立编号系统**。

同一篇文献在不同项目中可能：
- fetch_plan 里编号是 P23-18
- PPT Slide 23 里引用序号是 ⑧
- 实际上内容是 "Kraft S BMT 2019"

**正确流程**：永远从 PPT 视觉出发 → 匹配 PDF 内容 → 确认后才 highlight。

## ⚠️ C列（标记）核查：XML正则不可用，必须vision (2026-08-10教训)

**C列 = PPT内引用编号（标记），与A/B列是独立编号系统。**

**根本性问题**：python-pptx XML正则提取引用编号存在系统性失败：
- 中文引用用全角句号"．"而非半角"."，正则`\d+\.`无法匹配
- 引用文本跨多个XML`<a:t>`块，正则分割会把多条引用合并
- 正文内容和引用区在同一文本块，正则会把正文编号误认为引用编号
- 81条"错误"中大量是**误报**（正则分割失败导致找不到引用）

**唯一可靠方法：vision_analyze逐页读取**
```python
# 错误做法（XML正则，必然失败）：
for slide_num in range(3, 34):
    xml = z.read(f'ppt/slides/slide{slide_num}.xml').decode('utf-8')
    texts = re.findall(r'<a:t>([^<]+)</a:t>', xml)
    # → 文本跨块、合并、丢失

# 正确做法（vision，逐页读）：
for slide_num in [3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 17, 23, 25, 28, 30, 31]:
    vision_analyze(
        f'/Users/david/Desktop/TMA_文献整理/_ppt_renders/slide_pp_{slide_num:03d}.jpg',
        "Slide N底部引用区。列出所有引用编号和对应的作者/期刊（逐条）。"
    )
```

**已知PPT真实引用结构（vision核对）**：
```
Slide 3: [1]中华血液学杂志2024 [2]Luzzatto [3]West EE
Slide 4: [1]中华血液学杂志2024 [2]Luzzatto [3]West EE [4]Skattum [5]Heesterbeek [6]Figueroa
Slide 5: [1]Kirschfink [2]Skattum [3]Figueroa
Slide 6: [1]Nat Rev Nephrol 2018 (aHUS)
Slide 8: [1]Laurence J [2]Palma LM P
Slide 9: [1]George [2]Timmermans [3]戴艳玲 [4]中华医学会 [5]非典型溶血尿毒综合征共识
Slide 11: [1]任宏 [2]Azoulay [4]浙江省医学会 [5]中华医学会 [6]Luzzatto [7]Yerigeri
Slide 12: [1]Azoulay [2]中华血液学杂志2017 [3]UpToDate
Slide 14: [1]Nguyen [2]Brocklebank [3]Thompson
Slide 17: [1]中华医学会血栓学组+Zheng XL [4]Issa
Slide 23: [2]Schoettler [3]Ho VT [4]Gavrilaki [5]Dvorak [6]Khaled [7]Wanchoo
         [9]Jodele [10]Dandoy [11]Dandoy [12]Jodele [13]Jodele [14]Rampogal
         [15]Schoettler [16]Schoettler [17]Wang [18]Kraft [19]Li [20]Postalcioglu
         [21]Liu W [22]Chen BT [23]Sabulski [24]Schoettler [25]Dandoy [26]Jodele
Slide 24: [1]Schoettler [2]中华医学会共识 [3]张赵光
Slide 25: [1]Jodele [2]非典型溶血尿毒综合征共识2025 [3]Timmermans [4]Yerigeri [5]Trojnar [6]Zheng XL [8]Azoulay
Slide 28: [1]Lazana [2]Renaud [3]Limin [4]Mahmoud
Slide 30: [1]Brocklebank [2]非典型溶血尿毒综合征共识 [3]Uriol Rivera [4]Gordon
Slide 31: [1]Noris [2]Jiang [4]Fakhouri [5]Licht [7]Sami Fam
```

## Step 1-2: PPT 视觉读取引用（⚠️ 禁止跳过）

**必须用 vision_analyze 逐页读取**，不能用 python-pptx 文字提取（合并引用被截断）。

```python
# 错误做法（导致 P8-2/P9-2 内容混淆）：
python-pptx 提取文字 → 多个引用被合并 → 关键词匹配 → 假阳性

# 正确做法：
vision_analyze(slide_pp_NNN.jpg) → 读取引用列表 → 搜索 PDF 第一页验证内容
```

**逐 Slide 视觉读取模板**：
```
vision_analyze(slide_pp_NNN.jpg, "Slide N：标题、底部引用区所有文献（逐条完整读出来）")
```

**每张 Slide 记录**：
| 字段 | 说明 |
|------|------|
| slide_num | PPT 页码 |
| ref_num | 底部引用编号（①②③...） |
| author | 第一作者 |
| year | 年份 |
| journal | 期刊名 |
| pnx_matched | 匹配的 Pn-x（如有） |
| verified | ✅正确 / ❌错误 / ⏳需下载 |

## Step 3: PPT→PDF 内容核查（核心步骤）

**流程**：PPT 视觉引用 → 搜索全部 Pn-x main.pdf 第一页文本 → 匹配作者名 → 验证内容相关性。

```python
import fitz, os

PNX = '/Users/david/Desktop/TMA_文献整理/_pnx'

# 示例：找 George NEJM 2006（TMA 经典文献，PPT Slide 3 引用①）
target = 'George'
results = []

for pnx_dir in sorted(os.listdir(PNX)):
    if not pnx_dir.startswith('P'): continue
    main = os.path.join(PNX, pnx_dir, 'main.pdf')
    if not os.path.exists(main): continue
    try:
        doc = fitz.open(main)
        txt = ''.join(doc[i].get_text()[:800] for i in range(min(4, len(doc))))
        doc.close()
        if target.lower() in txt.lower():
            # 提取第一行（标题/作者行）
            first_line = txt.split('\n')[0][:100]
            results.append((pnx_dir, first_line))
    except:
        pass

for pnx, line in results:
    print(f"{pnx}: {line}")
```

**常见错误匹配**：
- 关键词 "George" 匹配到参考文献列表里的 George S. 而非正文 James N. George
- 解决方案：检查匹配行上下文，确保是正文方法/结果段而非 bibliography

**中文文献处理**：
- 18 条中文引用全部需要下载（知网/万方）
- 现有 Pn-x 中文 PDF 大多是其他主题（如溶血危象、骨髓增殖性疾病）

## Step 4: Highlight 严格规则

### 4.1 正确流程（4步，禁止跳过）

1. **PPT 截图**：`slide_pp_NNN.jpg` → vision_analyze 读取引用序号
2. **PDF 截图**：`_pdf_images/page_NNN.jpg` → 对应内容定位
3. **视觉对照**：PPT 引用序号 ↔ PDF 正文应证段落
4. **验证后标注**：确认内容后才画黄线

### 4.2 禁止 highlight 的内容（高压红线）

| 禁止类型 | 示例 |
|---------|------|
| 文章标题 | "Thrombotic Thrombocytopenic Purpura" |
| 作者名称 | "James N. George, M.D." |
| 期刊名/doi | "N Engl J Med", "doi:10.1056/..." |
| 参考文献列表 | bibliography 里所有条目 |
| 页眉页脚 | 出版社名称、页码 |

### 4.3 只允许 highlight 的内容

- **正文应证段落**：方法、结果、讨论中的具体临床数据/诊断标准/治疗方案
- **表格内容**：临床数据表格里的数值
- **图表引用**：正文对图表的引用说明

### 4.4 Highlight 机制（v3 FINAL，2026-08-13 定稿）

> **⚠️ 本节旧版"关键词 span 过滤 + draw_rect 1.5pt 细线"代码已被废除**（用户多次暴怒:
> 关键词匹配、细线压字、标题作者引用被盖）。唯一权威机制 = hl_lib:

```bash
# 1. 每个 Pn-x 一个句子脚本(按 slide 视觉内容选整句, 禁止复制其他 Pn-x)
#    模板与 105 个示例: via54medit-literature-pipeline/scripts/hl_pnx_examples/
# 2. 批量重跑(幂等: 先清旧 annots 再加)
python3 via54medit-literature-pipeline/scripts/rerun_all.py
# 3. fitz 渲染(禁止 pdftoppm) + 根目录只留高亮页
python3 via54medit-literature-pipeline/scripts/render_fitz.py <hl.pdf> <pages_dir> 100
python3 via54medit-literature-pipeline/scripts/copy_hl_images.py
# 4. 验证: 像素黄色检测 + annots 直接迭代 + 视觉抽查
```

样式唯一权威值: fill/stroke RGB(255,217,0)、opacity 0.45、add_rect_annot(border 0)、逐行 rect(行距法)、
句首尾精确对齐、引用编号保护。详见 `via54medit-literature-pipeline/references/highlight-mechanism-v3-final.md`。

## Step 5: 三方对齐验证

**三个来源必须完全一致**：

1. **PPT 引用序号**（vision_analyze 读出来的）
2. **PDF 文件内容**（fitz 第一页验证的）
3. **highlight 标注位置**（黄线在应证段而非标题/引用区）

## 已知正确映射（v1.1, 2026-08-10实测）

以下Pn-x内容已通过PDF第一页文本+DOI交叉验证：

| Pn-x | 文献 | DOI | 关联Slide | 备注 |
|------|------|-----|-----------|------|
| P4-2 | Luzzatto PNH 2020 | 10.1111/bjh.17147 | Slide 4 | ✅首行含"Paroxysmal nocturnal haemoglobinuria (PNH)" |
| P4-3 | West EE Complement 2023 | 10.1038/s41581-023-00704-1 | Slide 4/16 | ✅Nat Rev Nephrol |
| P5-2 | Skattum Mol Immunol 2011 | 10.1016/j.molimm.2011.05.001 | Slide 5 | ✅Molecular Immunology 48 |
| P5-3 | Figueroa CMR 1991 | 10.1128/cmr.4.3.359 | Slide 5 | ✅Clin Microbiol Rev |
| P8-1 | Laurence 2016 | — | Slide 8 | ✅aHUS/TTP |
| P9-1 | George NEJM 2014 | 10.1056/NEJMoa1314323 | Slide 9 | ✅TTP overview |
| P9-2 | Timmermans JCM 2021 | 10.1016/j.ocarto.2021.100231 | Slide 9 | ✅Complement TMA |
| P11-2 | Azoulay Chest 2017 | — | Slide 22 | ✅ICU TMA |
| P12-1 | Azoulay Chest 2017 | 10.1093/ckj/sfx059 | Slide 12 | ✅同P11-2 |
| P14-2 | Brocklebank CJASN 2018 | 10.2215/cjn.00620117 | Slide 14 | ✅TMA diagnosis |
| P14-3 | Thompson 2022 | — | Slide 14 | ✅Schistocyte |
| P17-2 | Campistol 2013 | — | Slide 17 | ✅Transplant TMA |
| P17-3 | George NEJM 2006 | 10.1056/nejmcp053024 | Slide 17 | ✅TTP经典文献 |
| P17-4 | Issa 2024 | — | Slide 17 | ✅NEJM 2024 |
| P18-1 | Zheng XL JTH 2020 | 10.30498/IJB.2020.2538 | Slide 18 | ✅ADAMTS13 |
| P22-2 | Timmermans 2021 | — | Slide 22 | ✅Complement aHUS |
| P23-9 | Jodele Blood Rev 2015 | — | Slide 23 | ✅HSCT-TMA |
| P23-12 | Jodele Blood | — | Slide 18/23 | ✅HSCT-TMA criteria |
| P23-13 | Schoettler 2022 | — | Slide 23 | ✅GVHD-TMA |
| P23-15 | Schoettler | — | Slide 23 | ✅BBMT |
| P23-16 | Schoettler | — | Slide 23 | ✅Transplant |
| P23-18 | Kraft 2019 | — | Slide 23 | ✅BMT mortality |
| P23-19 | Li A 2019 | — | Slide 23 | ✅TA-TMA |
| P23-20 | Postalcioglu 2022 | — | Slide 23 | ✅TMA outcomes |
| P23-21 | Jiang 2022 | — | Slide 23 | ✅ |
| P23-22 | Wanchoo 2022 | — | Slide 23 | ✅Kidney TMA |
| P23-23 | Sabulski 2022 | — | Slide 23 | ✅Cerebral TMA |
| P25-4 | Jiang 2023 | — | Slide 18 | ✅Eculizumab meta |
| P25-5 | Falazoun 2022 | — | Slide 25 | ✅Amancha |
| P30-1 | Brocklebank CJASN 2018 | 10.2215/cjn.00620117 | Slide 30 | ✅同P14-2 |
| P31-1 | Ramgopal 2021 | — | Slide 31 | ✅Pediatric HSCT |
| P31-4 | Campistol 2023 | — | Slide 18 | ✅aHUS eculizumab |
| P4-6 | Figueroa CMR 1991 | 10.1128/cmr.4.3.359 | Slide 4 | ✅同P5-3 |
| P23-4 | Sabulski 2024 cerebral | — | Slide 23 | ⚠️2024版，不是Bhatt |

## 常见错误PDF（需重新下载，不可用）

| Pn-x | 错误内容 | 正确文献 |
|------|---------|---------|
| P3-1, P4-1 | PNH/骨髓增殖性/溶血危象 | 中文期刊需下载 |
| P4-2 | PNH论文（Luzzatto，目录名对但内容非TMA补体） | 实际是PNH非TMA |
| P23-3 | Ho VT?北京论文 | Ho VT BBMT 2005需下载 |
| P23-5 | 口腔微生物 | Dvorak Front Pediatr 2019需下载 |
| P23-6 | 沙特心脏病学 | Gavrilaki 2020需下载 |
| P19-1 | COVID-19 | Sukumar Blood 2021需下载 |
| P20-2 | 毒素/微生物 | Liu Y STEC需下载 |
| P25-1 | AML儿童移植 | Jodele TMA需下载 |

## ⚠️ Step 6 整合失败会导致目录大混乱（2026-08-10严重教训 → 2026-08-14 合并规则定稿）

**根本原因**：历史merge脚本按文件名/标题去重合并，把**不同论文**错误合并到同一目录，同时把**同一论文**错误分散到多个目录。

**✅ 2026-08-14 定稿规则（取代一切历史 merge 脚本）**：
- 合并判定 = 引用文本指向同一文献（**不能只看 MD5**：同一文献不同下载版本 MD5 不同仍要合并）
- 新目录名 = 成员 Pn-x 按数字顺序下划线连接: `P3-1 + P4-1 → P3-1_P4-1`
- TMA 全量清单（12 组合并, 106→90 目录）: `via54medit-literature-pipeline/references/merge-rules.md`
- 合并前必须确认引用一致或同 DOI, 合并保留各成员全部文件

**历史教训（保留）**：
- `P23-24-P24-1`：合并脚本产物，目录名不合法（含两个PN）
- `P25-2/P30-2/P9-5`（3个目录）：CNKI下载到"高级检索"搜索页PDF，真实论文未下到
- `P12-3/P21-2/P22-3/P24-4/P24-5`（5个空目录）：完全无文件
- 16组"重复"中大部分是**同名不同论文**（如P25-5和P31-4都是eculizumab相关但是不同研究），不是错误

**正确的Step 6执行流程**：
1. 用fitz全文搜索验证每个PN的真实内容（不只是查verify.json标题）
2. 发现内容与CSV引用不符→标记→搜索正确PDF重下
3. 发现空目录→搜索正确PDF重下
4. **绝对不能按文件大小/标题名判断两个PN是否重复**
5. 合并前必须fitz.open()读内容确认是同一篇论文

**快速审计脚本**（每行单独处理，不批量）：
```python
import fitz, os
PNX = '/Users/david/Desktop/TMA_文献整理/_pnx'
for pnx_dir in sorted(os.listdir(PNX)):
    if not pnx_dir.startswith('P'): continue
    main = os.path.join(PNX, pnx_dir, 'main.pdf')
    if not os.path.exists(main):
        print(f"EMPTY: {pnx_dir}")
        continue
    try:
        doc = fitz.open(main)
        text = ''
        for i in range(min(2, len(doc))):
            t = doc[i].get_text().strip()
            if t:
                text = t
                break
        doc.close()
        if '检索' in text or '想找什么' in text:
            print(f"WRONG (search page): {pnx_dir}")
    except Exception as e:
        print(f"ERROR {pnx_dir}: {e}")
```

## References

- `references/tma-b-column-18-errors-2026-08-10.md` — B列18处错误修正记录（含修正脚本）
- `references/tma-ppt-slide-reference-structures-2026-08-10.md` — PPT各slide引用编号结构（vision核对版）
- `references/tma_pnx_full_audit_2026-08-10.md` — 2026-08-10全面审计结果：空目录/错误内容/同名不同论文/真实同名论文完整清单 + 飞书表最终状态
- `references/tma_ppt_pdf_mapping_2026-08-10.md` — PPT引用→PDF映射完整核查记录
- `references/tma_pnX_content_inventory.md` — 全部Pn-x main.pdf第一页文本清单
