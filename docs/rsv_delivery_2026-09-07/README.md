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

## 4. 745 vs 171 句基准口径说明 (行动4)
- GitHub commit dd3d0e6 记录 "RSV 745-sentence regression 730 locate-OK"
- 该 745 句为早期中间轮次的句集(含未下载/重复/被删句子与早期回归实验), 未入库, 仓库内无 TSV 数据可复现
- 本次交付 171 句为最终交付口径 (57 Pn-x 逐页逐条选定句, 全部 missing=0)
- 两者不可直接比较; 若需统一基准, 建议以本次入库的 rsv_sentences_official.tsv (171 句) 为 RSV 可复现基线, 745 句历史集仅作回归范围参考

## 5. 后续
- 保留今日 7 个可复用脚本于工作区 (hl_one/verify_hl/_hl_ocr_gen/mmx_text_chat/pick_sents + hl_lib/render_fitz)
- OCR 通道迁移官方工具的增强项见 §3, 可在 via54Medit repo 立项
