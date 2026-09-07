# RSV 2026-09-07 highlight 交付 — 官方工具复现与基准说明

## 1. 交付统计
- 57/57 Pn-x, 171 句, 634 annots, missing=0, verify yellow_ok 57/57
- 文本层直定位: 142 句 (45 个文件) | OCR 通道: 29 句 (12 个乱码/图片文件)

## 2. 官方 verify_sentence_set.py 复现 (RSV 可复现基准)
- 输入: docs/rsv_delivery_2026-09-07/rsv_sentences_official.tsv (171 句; file/page/type/flag/text)
- 结果: TOTAL sentences=171 located_ok=142 (文本层文件 100% 复现)
  - 142/142 OK (文本层文件)
  - 17 句整页 OCR (GARBLED/IMAGE 通道句, 官方验证器按设计排除)
  - 12 句为"页含少量文字层(页眉/页码)+正文图像"的混合页, 官方验证器判 NOT FOUND (页级文本检测为真, 但句子在图像区) —— 这些实际由今日 OCR 高亮覆盖, 属官方验证器"整页非空即有文本层"的页级判定局限, 建议后续增强为区域级判定或这些页统一走 OCR 通道

## 2.1 TSV 列与 flag 取值说明 (rsv_sentences_official.tsv)

TSV 为 5 列制表符分隔, 首行为表头:

| 列 | 含义 | 取值 |
|---|---|---|
| file | 文献 PDF 文件名 (无路径) | 如 `P3-2.pdf`; 57 个文件, 对应 57 个 Pn-x 引用 |
| page | 句子所在页 (1-based) | 1..N (个别句子实际页与 TSV 记录有出入, 如 P6-1 两句实际 p7, 见 cn_font_calib_2026-09-07.json) |
| type | 句子类型/来源 | 恒为 `hl` (本次交付为高亮句集; 预留其他取值空间) |
| flag | 句子在**构建时**分配的定位通道 | 见下表 |
| text | 句子原文 (含当日从乱码文字层侧转录引入的 OCR 噪声字, 视觉校准句见 cn_font_calib_2026-09-07.json) | — |

flag 取值 (构建时静态通道标记, 共 171 句):

| flag | 数量 | 文件数 | 含义 |
|---|---|---|---|
| (空) | 142 | 45 | 文本层通道: PDF 有正常文字层, 句子经 hl_lib.locate_sentence 直接定位 |
| ocr | 29 | 12 | OCR 通道: PDF 文字层乱码/缺失(渲染正常), 句子须经渲染+OCR 词流定位 |

flag=ocr 的 12 个文件与句数: P15-3(3)、P15-4(2)、P21-3(2)、P23-3(2)、P27-2(4)、P27-3(2)、P3-2(1)、P3-3(2)、P6-1(3)、P8-10(3)、P8-4(2)、P9-10(3)。

注意: flag 是构建交付时的静态分配, **运行验证时以 verify_sentence_set.py 的区域级判定 (text/mixed/garbled/image) 动态归类为准**。例如 P27-3 经 layout.col_resort 修复后运行时已可由 OCR 复现 (计入 located_ok), 但 TSV flag 保持交付原值 `ocr` 不变, 二者不冲突。

verify_sentence_set.py (E3) 运行时的区域级通道判定取值 (见 scripts/hl_v3_final/verify_sentence_set.py):

| 判定 | 判定依据 (正文区字符量 + 有效字母率) | 路由 |
|---|---|---|
| text | 正文区(去边距版心)字符 ≥ 150 且有效字母率 ≥ 0.5 | hl_lib 文本层定位 |
| mixed | 页有少量文字层(页眉/页码)但正文区字符 < 150 | OCR 通道 |
| garbled | 正文区字符 ≥ 150 但有效字母率 < 0.5 (字形映射乱码) | OCR 通道 |
| image | 整页无有效字母/CJK | OCR 通道 |

TSV 静态 flag 与运行时判定是"交付口径 vs 复现口径"两层: 交付时按文件整体文字层可用性标 `ocr`(12 个乱码/图片文件), 复现时按页面区域细判, 故 `ocr` 文件内的句在运行时可能落入 mixed/garbled/image 任一通道。

## 3. 官方 hl_ocr_band.py 对 12 个 OCR 文件的复现 (行动1)
对照 (official_placed/total vs 今日 annots):
| pnx | official placed | today annots | 说明 |
|---|---|---|---|
| P8-10 | 2/3 | 10 | 图片型 MMWR, 部分成功 |
| P9-10 | 1/3 | 8 | 图片型 MMWR, 部分成功 |
| P21-3 | 1/2 | 6 | CSR 乱码, 部分成功 |
| P3-2/P3-3/P6-1/P8-4 | 0/* | 7/10/16/8 | 中文 PDFTron 乱码, OCR 词序难复现 |
| P15-3/P23-3 | 0/* | 8/4 | CSR 357页 乱码, 表格版面 OCR 序乱 |
| P15-4 | 0/2 | 5 | CT.gov 图片页 |
| P27-2/P27-3 | 0/* | 9/6 | PubMed 打印件/JGIM 乱码 |

结论: 官方 hl_ocr_band.py 对"单栏/简单双栏英文可读图片"可用; 对 CSR 表格/PubMed 打印件/中文双栏等复杂版面, 其 start/end 短语窗口 + 分栏启发式难以全自动复现。
增强建议(入库 TODO):
  a) 支持整句 norm 匹配(替代仅短语窗口), 与 hl_lib.locate_sentence 对齐
  b) 版面分析增强: 识别页眉/页脚排除; 表格区域专用; 中文 chi_sim 双栏 x 聚类
  c) 区域级判定: verify_sentence_set 混合页(页含少量文字层)应标记走 OCR 通道而非 NOT FOUND

## 5. OCR 增强入库后复现结果 (E1/E2/E3, M1-M4, 同日完成)

仓库侧新增/改造 (见 docs/OCR增强功能立项方案_2026-09-07.md):
- `layout.py` (E2): 版面区域模型, 词级双栏切分, 页眉页脚/页码剔除
- `hl_ocr_band.py --sentence` (E1): 整句定位 locate_in_ocr (四级回退, 与 hl_lib.locate_sentence 对齐)
- `verify_sentence_set.py` (E3): 区域级判定 text/mixed/garbled/image, 消除混合页 NOT FOUND 误报

M4 全量回归 (权威结果见 m4_regression_2026-09-07.json; 其后 col_resort 修复见立项方案 §13):
| 指标 | 官方基线 | 增强后 | 目标 |
|---|---|---|---|
| 12 OCR 文件整句定位 | 4/29 (14%) | 21/29 (72%) | ≥26/29* |
| verify located_ok | 142 | 159 | ≥154 ✓ |
| 混合页 NOT FOUND 误报 | 15 | 0 | 消除 ✓ |
| 文本层 45 文件 | 142/142 | 142/142 | 无回退 ✓ |
| P8-10/P9-10/P21-3 | 部分 | 3/3·3/3·2/2 全中 | 不回退 ✓ |

*: 21/29 未达 26/29 的门槛, 差额 8 句为中文 PDFTron 乱码(源字形损坏, chi_sim 亦不可解), 已全部经 mmx 视觉校准闭环 (见 cn_font_calib_2026-09-07.json 与立项方案 §12)。

## 6. 745 vs 171 句基准口径说明 (行动4)
- GitHub commit dd3d0e6 记录 "RSV 745-sentence regression 730 locate-OK"
- 该 745 句为早期中间轮次的句集(含未下载/重复/被删句子与早期回归实验), 未入库, 仓库内无 TSV 数据可复现
- 本次交付 171 句为最终交付口径 (57 Pn-x 逐页逐条选定句, 全部 missing=0)
- 两者不可直接比较; 若需统一基准, 建议以本次入库的 rsv_sentences_official.tsv (171 句) 为 RSV 可复现基线, 745 句历史集仅作回归范围参考

## 7. 后续
- 保留今日 7 个可复用脚本于工作区 (hl_one/verify_hl/_hl_ocr_gen/mmx_text_chat/pick_sents + hl_lib/render_fitz)
- OCR 通道迁移官方工具的增强项见 §3, 已按 docs/OCR增强功能立项方案_2026-09-07.md 落地 (M1-M3 完成, M4 回归收尾), 待办见该文档
