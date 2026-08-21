# AGENTS.md — via54Medit 跨工具协作规约

> 适用于 **Claude Code / Cursor / GitHub Copilot / Hermes Agent / OpenCode / Codex** 等所有 AI 工具。
> 本文件等价于 `CLAUDE.md` / `.cursorrules` / `.github/copilot-instructions.md`，各工具自动识别同名约定。

---

## 项目身份

- **名称**: via54Medit
- **副标题**: Multi-Source Medical Literature Router for Evidence-Based Medicine
- **作者**: 巫师叔叔 (via54) + Hermes Agent
- **GitHub**: github.com/veawho/via54Medit (private)
- **本地路径**: `G:\agent\developments\via54Medit\`
- **许可**: MIT (templates/configs/docs) + AGPL-3.0 (source code)
- **依赖**: github.com/veawho/via54Design（**可选借鉴**,非强制 — 2026-06-24 修订,见 ARCHITECTURE §21）

## 技术栈

| 层 | 技术 |
|---|---|
| 主语言 | Go 1.22+ (CLI + MCP Server) |
| 热路径 | Rust 1.75+ (PDF 解析 / 分块) |
| 胶水 | Bash (scripts/) |
| 数据库 | SQLite (FTS5) + Qdrant (vector) + bge-m3 (embedder) |
| 协议 | MCP (Model Context Protocol) |
| 测试 | go test + VHS (e2e) + cargo test |
| 文档 | Markdown + Go doc + cargo doc |
| L0 PDF 真实性 | PyMuPDF + Crossref API (median/i2sco) |
| L1 文字加速 | PyMuPDF (Rust 备选) |
| L2 OCR 中文 | PaddleOCR 3.7+ (86k★) |
| L3 视觉理解 | sensenova-6.7-flash-lite → MiniMax-M3 → PyMuPDF local (3级 Cascade) |
| L4 应证推理 | Go `internal/anno2ppt` (4 维要素 + 集合结论) |
| L5 双源架构 | Go `internal/anno2ppt/dual_source.go` (main + fallback) |
| L6 经验沉淀 | Python `process_pn_x_learnings.py` (自动 callback) |
| **CSV 同步铁律** | `internal/citation/sync/csv_sync.go` (8 列表头冻结) + `scripts/csv_feishu_sync.py` |

## 用户偏好 (巫师叔叔 4A 风格)

1. **第一性铁律验证**: 不接受"理论可行"，必须有可运行示例
2. **批量全修**: 一次给完整修复方案，不分步询问
3. **AGPL-3.0 + MIT 双许可**: 源码 AGPL, 模板/配置 MIT
4. **全平台思维**: 主动考虑 macOS / Linux / Windows
5. **结构化输出**: 表格、清单、决策树；少用 bullet soup
6. **拒绝试错式**: 先穷尽诊断再行动
7. **黄金比例 + 黄金测试**: 关键功能必有 9 案例 / 31 单元测试
8. **确定性优于随机**: map 遍历必排序，CSS 变量生成必 deterministic
9. **质量门禁 8 项**: 编译通过 / 单元测试 / 集成测试 / lint / format / vet / race / coverage≥80%
11. **文档先行**: ARCHITECTURE.md 在 Phase 0 完成, ROADMAP.md 跟 Phase 同步
12. **🔥 CSV 必有表头 (2026-08-01 铁律)**: 任何 citation_table.csv 第 1 行 = 8 列标准表头 (PPT页/第几条/引用语义/PPT引文完整字段/DOI/类型/对应PDF文件/来源链接). 飞书 row 1 = 表头, row N+1 = CSV data row N. 用 `internal/citation/sync/csv_sync.go` (Go) 或 `scripts/csv_feishu_sync.py` (Python) 验证. 不带表头 = 数据错位 1 行 (P3-1 2026-08-01 踩坑).
13. **🔥 PPT 引文是真理 (2026-08-01 铁律)**: main PDF 必须是 PPT 引文直接对应的文献. main 找不到数据才用 fallback, 但 fallback 也必须与 PPT 语义对齐, **严禁换文献** (P3-1 2026-08-01 错位: 本地 main=Kudo HBSN 2022 HIMALAYA Editorial, 但 PPT 标号 1 想引用 GLOBOCAN 2022 China 36.8万, 完全无关 → 移到 _v39_deprecated). "找不到" = main PDF 实际**不含** PPT 数据, 不仅是路径不存在.
14. **🔥 GLOBOCAN 数据时序差异必须标注 (2026-08-02 铁律)**: IARC 网站 (gco.iarc.who.int) 已下线 2022 数据, 只显示 2024. 当 PPT 引 GLOBOCAN 2022 但本地只有 2024 PDF 时, 必须在**飞书表 H 列 + 本地 CSV H 列 + manifest** 三处加【⚠️ 数据时序差异】段: PPT 引 36.8万 / 现 GLOBOCAN 2024 是 35.4万 (差 1.4万, 趋势一致). 不影响 PPT 应证结论, 但用户必须知情.
15. **🔥 飞书 H 列必须用 rich_text + 真实下载链接 (2026-08-02 铁律)**: 飞书表 H 列必须用 rich_text 格式 (lark-cli --cells + rich_text array), 不能用 markdown 文本. 链接必须指向**互联网下载链接** (DOI / PMC / Frontiers / MDPI / IARC 等), 不是本地 file://. 本地路径用 file:// 让人打开看, 但**下载链接是网上链接**. 本地 CSV H 列用 markdown 格式 (飞书是真理, CSV 从飞书同步).
16. **🔥 飞书是唯一真理源 (2026-08-02 根因级铁律)**: 飞书表 = 真理 (single source of truth), 本地 CSV = 镜像. 任何写入飞书前必跑 `citation_sync.py lock_row_anchors(N-5, N+5)` 拉 A+B 真值, 然后 `assert_no_collision(N, expected_pnx)`. 任何写入后必跑 `re_read_verify` 确认 rich_text 元素数一致. 用 `citation_sync.py sync` 单向同步飞书→CSV, CSV 不允许反向覆盖飞书.
17. **🔥 链接必须分类 + 时效体检 (2026-08-02 根因级铁律)**: H 列链接分 5 类 — A 官方PDF开放 / A_PDF付费墙 / B_PMC主页 / C_DOI / D_LOCAL / E_WAYBACK. 跑 `link_health.py check_table` 全表体检, 自动识别失效链接 (403/404) + 时效差异 (URL含2022但当前数据是2024). 失效或时效有问题的链接必须加【⚠️ 时效差异】段标注 + 推荐 Type E Wayback 备用. 用 `PNX_EXPIRY_WHITELIST` 硬编码已知时效问题 (P3-1 GLOBOCAN 2022→2024).
18. **🔥 写飞书前必对账, 写后必验证 (2026-08-02 根因级铁律)**: 任何写入飞书的代码必走 `write_h_atomic(row_n, expected_pnx, rich_text)`. 流程: lock → assert_no_collision → dry_run → write → re_read_verify. 不允许直接用 ad-hoc Python 写飞书 H 列.
19. **🔥 H 列必须含 4 必填段 (2026-08-02 根因级铁律)**: 飞书 H 列 rich_text 必含 4 段: ① 主文件 (本地路径 + 互联网下载链接), ② Fallback 补充材料 (本地路径 + 下载链接), ③ PPT 真实内容位置 (标号 + 引文 + PPT 数据), ④ Highlight 图 (本地 file://). main 和 fallback **都必须有**对应下载链接, 不能只有本地.
20. **🔥 错位永不妥协 (2026-08-02 根因级铁律)**: `assert_no_collision` 是最后防线, 任何"想当然"的 Row 索引 (CSV Row N=飞书 Row N+1 之类) 必报错. 飞书 token+sheet id 唯一, 不允许假设. 错位历史 (P3-1 2026-08-01 飞书错位, P4-1 2026-08-02 Row 3~7 串内容) 必查 + 必改 + 必测, 不允许"看起来对了"就放过.
21. **🔥 PDF 多模态深度理解 (2026-08-02 根因级铁律)**: 用 Docling (IBM 64k stars) 解析 PDF, 提取结构化数据 (texts/tables/pictures/bbox). 表格用 Table-Transformer (微软, docling 内置, 3k+ stars), 公式用 Pix2Text (中文 OCR + LaTeX, breezedeus). PyMuPDF 抽文字作为 fallback. 不允许只靠 PyMuPDF get_text() (丢表格结构).
22. **🔥 信息要素推理: PPT 引文 → PDF 应证位置 (2026-08-02 根因级铁律)**: 不允许简单关键词匹配. 用 `pdf_understand.py semantic_match_ppt_to_pdf()`: ① extract_ppt_data_points 智能抽百分比 (36.7% 同时生成 36.7 变体) + 医学术语 (BCLC B/C/HBV/HCC/AFP/ALBI); ② find_data_point_in_doc 在 docling tables/texts 中搜, 返回 page_no + bbox + type; ③ 应证得分 = found/total, 必须精确到 cell + bbox.
23. **🔥 高亮必须 bbox 精确 (2026-08-02 根因级铁律)**: 不允许"全页黄色"覆盖 (太大, 丢精度). 用 docling 输出的 cell bbox, 用 `render_highlight_bbox()` 画精确单元格高亮. 旧 v3.x 高亮图作废, 重生成时必须用 bbox.
24. **🔥 错字 OCR 修正 + 图表错行 (2026-08-02 根因级铁律)**: Pix2Text (中文 OCR) + Docling Table-Transformer 表格结构识别. docling 已内置 RapidOCR (PP-OCRv6 中英文混排) + Table-Transformer. 错行问题: docling 返回 table_cells 含 start_row_offset_idx, 找错行直接读 idx 即可. 错字问题: RapidOCR 自动纠错.
25. **🔥 所有问题必查 GitHub 高 star 项目 (2026-08-02 用户硬规则 #2)**: 任何新问题先搜 GitHub (Docling/MinerU/Marker/PyMuPDF/Nougat/Surya/GOT-OCR/Pix2Text/Qwen2-VL), 找最佳路径, 不允许用 ad-hoc Python patch. via54Medit 是产品化的算法驱动的生产级项目, 每个能力都基于成熟开源方案.
26. **🔥 PPT 视觉理解: Step 1 是流程起点 (2026-08-02 根因级铁律)**: 任何 Pn-x 标注前先做 `ppt_understand.py find_citation_marks_v2()`, 从 PPT 第 N 页表格的方案名称/药物列 + 标题横幅语义提取引文标号. 只提取"中文词+数字"(如 仑伐替尼5)、"方案+数字"(如 T+A方案8,9)、"O+Y+数字"(如 O+Y15,16) — **禁止**泛化正则, 会把期刊年份/ISSN/疗效数据 (mOS 12.1月) 误当标号. P5 验证: 18/18 标号全匹配.
27. **🔥 3 步执行顺序不可逆 (2026-08-02 根因级铁律)**: ① PPT 视觉理解 (标号位置+表格行/列+文本内容) → ② PDF highlight 对齐验证 (`verify_highlight_alignment` 返回 aligned/score/issues) → ③ 五方校验 (① PPT理解 + ② D列引文 + ③ PDF全文 + ④ Highlight区域 + ⑤ H列). 旧流程 (先体检→推H→再回头修) 作废.
28. **🔥 信息要素推理取代关键词匹配 (2026-08-02 根因级铁律)**: 不允许只用关键词在 PDF 中 grep 然后高亮. 必须走: ① extract_ppt_data_points 抽数据点 (百分比双变体 + 医学术语) → ② find_data_point_in_doc 在 Docling tables/texts 中搜 → ③ verify_highlight_alignment 验证对齐 → ④ semantic_match_ppt_to_pdf 应证推理.
29. **🔥 H 列写 rich_text 的 4 个根因 (2026-08-02 用户硬规则)**: H 列写入飞书必须同时满足 4 个条件:
    (a) **排版保留**: rich_text 文本段必须含 `\n` 换行符, 不能按行拆分多段 (飞书多段内联渲染无换行). 全部文本作为 1 个 text 段 (含 `\n`), 只在链接位置插入 link 段.
    (b) **裸 URL 也转链接**: 不仅 `[text](url)` 格式, `https://doi.org/xxx` 等裸 URL 也必须转成 `{type:"link", text, link}` 段. 用 `markdown_to_rich_text()` v3 同时检测两种格式.
    (c) **每个本地文件对应下载链接**: 4-tier 链接中 🥇 一级 (本地 PDF) 必须有对应互联网下载链接 (DOI/PubMed/Europe PMC). 仅靠 DOI 链接不够, 还需加 PubMed 搜索链接 (`https://pubmed.ncbi.nlm.nih.gov/?term=<DOI>`) 和 Europe PMC 链接 (`https://europepmc.org/search?query=<DOI>`).
    (d) **H 列 v5.0 结构 (2026-08-02 用户硬规则)**: 用户最新要求, H 列内容必须:
        - 仅保留本地**文件名** (不保留路径), `P5-X_main_xxx.pdf`
        - 主文件部分必含: 标题 / 作者 / 期刊 / 年/卷/期/页 / 出版 / DOI
        - 不重复 C 列的"多引用结构" (C 列已有)
        - 应证推理合并为: 视觉对齐 PPT / 数据对齐 PPT / 视觉·语义推理
    修复: `h_column_builder.py` 新模块 (parse_d_field + parse_c_field + build_h_md + markdown_to_rich_text) + `citation_sync.py` 集成. P3 + P4 + P5 H2-H28 全部 27 行验证通过 (17 行有 3 links + 1 行 P3-2 政府文件 2 links + 1 行 P5-1 卫健委 2 links).

30. **🔥 H 列 v6.0 文件清单 + 应证评分 + 时效性 (2026-08-02 用户硬规则)**: H 列必须严格与 `_literature_citation_index/Pn-x/` 目录一致:
    (a) **文件清单 = Pn-x 目录**: 扫描 main / fallback / supplementary 三类 PDF. main 不够时显示 `【🔄 Fallback 补充材料】`. main 足够但有 fb/supp 时显示 `【🔄 附加材料】`. P5-13 有 2 main + 5 supp 时全部列出.
    (b) **应证评分**: 每个 PDF 都显示 `应证评分: 0.XX (step2 hits N/M)`. 评分从 manifest.step2_score 读取 (P5 Step 2 算法: docling 搜 PPT 数据点, found/total). P3-1=0.06 (GLOBOCAN 截图与中文 PPT 数据点不匹配, 是真实情况, 标注低分), P5-2=0.78 (main 应证 FOLFOX mOS 6.47月), P5-8 main=0.73 / fallback=0.70-0.50 (多 PDF 都评分).
    (c) **时效性**: 4 类永久/时效/临时/政府文件. DOI 一般永久. GLOBOCAN 标【⚠️ 时效差异: 2022→2024】+ Wayback 备用 URL. NHC 政府文件标【🏛️ 政府文件 (永久)】. ESMO/ASCO 标【⏰ 会议摘要 (1-2 年有效期)】+ 失效后备 URL.
    修复: `h_column_builder.py` 新增 `scan_pn_x_dir` + `calculate_main_score` + `calculate_fallback_score` + `identify_link_eternality` + `build_h_md_v6`. 每个 manifest 加 step2_score/step2_found/step2_total 字段. P3+P4+P5 H2-H28 全部 27 行验证通过.

31. **🔥 H 列 v6.x Fallback 完整显示 (2026-08-02 用户硬规则)**: H 列必须严格处理 main 评分低 + fallback 的情况:
    (a) **3 个 fallback 触发条件** (任一触发即显示 `【🔄/⚠️ Fallback 补充材料】`):
        1. manifest.fallback_triggered = True (main 不够)
        2. main_score < 0.7 (评分低, 即使 fb_triggered=False 也要补强)
        3. 有跨标号引用 (fb_cross_refs 非空, 如 P4-3 引 P4-1/P4-2)
    (b) **跨标号引用**: manifest.fallback_pdfs 含 `P4-1/file.pdf` (跨 Pn-x) 时, scan_pn_x_dir 解析路径, 提取 target_pn_x + target_file + 目标 Pn-x 的 step2_score 作为 fallback 应证评分.
    (c) **本目录 fb vs 跨标号**: fb_local (本目录 _fallback_/_fb_ PDF) + fb_cross_refs (跨 Pn-x 引用) 合并显示. 本目录 fb 优先 (有 size 信息), 跨标号 fb 补充.
    (d) **应证评分低警告**: 当 main_score < 0.7 且无 fb/cross_ref 时, 加 `【⚠️ 应证评分低】` 段, 显示 found/missing_data_points, 解释 main PDF 仍是真理 (docling 文本匹配未必完整).
    (e) **嵌套括号 URL parser**: markdown_to_rich_text 必须用手写 parser 处理 URL 含 `(25)` 等嵌套括号 (DOI like `10.1016/S0140-6736(25)00403-9`), 旧 regex `[^)]+` 会在第一个 `)` 截断.
  修复: `h_column_builder.py` 升级 scan_pn_x_dir (加 fb_local/fb_cross_refs/fb_info) + build_h_md_v6 (3 触发 fallback) + calculate_fallback_score (跨标号 score 借用目标 Pn-x) + markdown_to_rich_text (嵌套括号 parser). P3+P4+P5 H2-H28 全部 27 行验证通过.
32. **🔥 H 列 v7 语义等同性推理 (2026-08-02 用户硬规则)**: 当 PDF 数据点与 PPT 数据点字符不一致时, 必须用语义等同性推理, 不能简单标 missing:
    (a) **数值精度等价**: 14.4 ≈ 14.40 ≈ 14.400 (浮点相等). PDF Table 2 写 "14.4", PPT 写 "14.4%" 或 "14.40" → 等价推理命中.
    (b) **单位等价**: PDF 上下文 (表格 caption / 周围 text) 说明数据是 percentage → 裸数字等价于带 % 变体.
    (c) **算法**: `numerical_equivalence_variants()` 生成所有变体, `find_data_point_with_equivalence()` 用所有变体搜, `compute_semantic_alignment_score()` 计算最终评分.
    (d) **H 列展示**: 主文件应证评分后加 `, 含 N 个等价推理`. 加【🧠 语义等同性推理】段显示每个等价变体 (例 `'14.4%' 在 PDF 中以变体 '14.4' 出现 → 应证等价`).
    (e) **效果**: P3-3 0.44 → 1.00 (21 个等价), P5-17 0.58 → 0.77 (19 个等价), P5-18 0.64 → 0.95 (24 个等价).
  修复: `pdf_understand.py` 新增 `numerical_equivalence_variants` + `find_data_point_with_equivalence` + `find_all_ppt_data_points_with_equivalence` + `compute_semantic_alignment_score`. 每个 manifest 加 `equivalent_matches_count` + `equivalent_found_data_points` 字段. `h_column_builder.py` build_h_md_v6 加【🧠 语义等同性推理】段. P3+P4+P5 H2-H28 全部 27 行验证通过.
33. **🔥 H 列 v7.2 main 完整应证 + PDF 应证位置 (2026-08-02 用户硬规则)**: 当 main PDF 找到 PPT 引文标号的核心数据时, 必须显式展示:
    (a) **满分标注**: 当 main_score ≥ 1.0 时, 应证评分后加 `⭐满分`. H 列块【✅ main 完整应证 PPT 内容】也加 `⭐满分`.
    (b) **PDF 应证位置**: manifest.found_data_point_locations 存每个 found_data_point 的 `{page_no, text_snippet}`. H 列显示核心数据点的具体 PDF 位置, 例 `✓ '46.6' → page 3: （二）主要目标。到2030年...总体癌症5年生存率达到46.6%`.
    (c) **推理链**: 显示 PPT 引文 (推理源) → PPT 语义 (推理目标) → main PDF 应证位置 (页 + 上下文). 让用户看到完整的视觉+语义推理过程.
    (d) **fallback 触发逻辑修正**: 之前用 `manifest.fallback_triggered` (基于高亮图数量) 是错的. 改用 `main_score < 0.7`. 6 个 manifest 旧标记触发修正 (P3-4, P4-4, P5-1, P5-16, P3-2).
    (e) **计算 fallback 应证评分**: `calculate_fallback_score` 加政府文件分支 (卫健委/令汇编/nhc/gov/regulation → 0.75).
  修复: `pdf_understand.compute_semantic_alignment_score` 返回 matches, `h_column_builder.build_h_md_v6` 加满分标注 + PDF 应证位置段 + 推理链. P3-2 案例: 应证评分 1.00 ⭐满分, 核心数据 '46.6' → page 3, 上文"总体癌症5年生存率达到46.6%". P3 + P4 + P5 H2-H28 全部 27 行验证通过.
35. **🔥 H 列 v7.6 多层级 PDF 下载链接 (2026-08-02 用户硬规则)**: H 列下载链接段必须分层级, 不是只有 DOI 主链接:
    (a) **3 个分类, 互不重复**:
        📥 出版商 PDF 直链 (基于 DOI 模式): ScienceDirect (10.1016/*) / NEJM (10.1056/NEJM*) / Nature (10.1038/*) / Wiley (10.1002/*, 10.1111/*) / JCO ASCO (10.1200/JCO*) / AACR (10.1158/*) / Gastroenterology (10.1053/j.gastro*) / BMC (10.1186/*) / PLOS (10.1371/*) / Oxford (10.1093/*) / CA Cancer J Clin (10.3322/caac*) / LWW (10.1097/*) / SAGE (10.1177/*) / Oncotarget (10.18632/*) / Frontiers (10.3389/*) / The Lancet 官网 (10.1016/S0140-6736*)
        🔍 数据库搜索 (PubMed + Europe PMC): `https://pubmed.ncbi.nlm.nih.gov/?term=<DOI>` + `https://europepmc.org/search?query=<DOI>`
        🌐 DOI 通用链接 + OpenAccess: DOI 主链接 `https://doi.org/<DOI>` + OpenAccess Button `https://api.openaccessbutton.org/find?id=<DOI>` (查找 OA 全文)
    (b) **每个 Pn-x 4-8 个链接** (按 DOI 模式分别对应): P3-3 (Zeng JNCC 10.1016) 6 links; P5-15 (Yau Lancet 10.1016) 7 links (含 The Lancet 官网); P5-2 (Qin JCO 10.1200) 6 links (ASCO 全文+PDF); P3-1 GLOBOCAN 6 links; P5-1 NHC 政府文件 2 links; P3-2 政府文件 2 links.
    (c) **链接标签**: 出版商直链显示 "[ScienceDirect](url)" 而不是 "[ScienceDirect 全文](url)", 飞书 link text 用短标签.
  修复: `h_column_builder.get_publisher_pdf_urls()` 新增, 按 DOI 模式返回出版商特定 PDF 直链. `build_h_md_v6` 下载链接段重写为 3 段互不重复结构. P3 + P4 + P5 H2-H28 全部 27 行验证通过.
36. **🔥 H 列 v8.0 完整 Slide 3-43 全覆盖 (2026-08-02 用户硬规则)**: H 列必须覆盖 PPT 所有 slide 的所有引用标号, 不只是 slide 3-5:
    (a) **slide 6+ 简化模式**: 133 个 Pn-x 缺 manifest 和主文件, 算法先 (1) 复制主目录 PDF 到 `_literature_citation_index/Pn-x/`, (2) 生成简化 manifest (step2_score=None + D 列元数据 + 主文件元数据), (3) `calculate_main_score()` 返回 None 表示"未运行 docling, 用 D 列元数据默认 1.00 满分".
    (b) **会议摘要 v9.0**: `parse_d_field()` 升级识别 APASL/ASCO/ASCO-GI/ESMO/CSCO/EASL/AASLD 会议名 + 摘要号. 当 `info_d["type"]="conference_abstract"` 时, 下载链接段显示会议官网 + PubMed 会议搜索 + OpenAccess 查找. 会议摘要时效: 1-2 年有效期.
    (c) **政府文件 v9.0**: P3-2/P5-1 显示 NHC 官网 + 中国实用外科杂志 (永久).
    (d) **GLOBOCAN 特殊**: P3-1 显示 IARC 官方 + GLOBOCAN Liver PDF + Wayback 失效后备 (时效差异 2022→2024).
    (e) **下载链接 v7.6 三层结构**: 📥 出版商直链 (基于 DOI 模式) / 🔍 数据库搜索 (PubMed + Europe PMC) / 🌐 DOI 通用 + OpenAccess.
    (f) **数据点应证 v7.7**: 当 `main_score` 是 None, H 列显示 "1.00 ⭐满分 (CSV 元数据应证, 未运行 docling step2)". 5 步推理链 ⑤ 显示 "⚠️ 未运行 docling, 评分基于 D 列元数据对齐 (CSV 应证, 待 docling 验证)" + main PDF 文件信息.
  修复: `h_column_builder.parse_d_field` v9 升级 (识别 8 种会议), `calculate_main_score` 改返回 None, `build_h_md_v6` 下载链接段加会议分支 (会议官网 + PubMed + OpenAccess), 加 `main_score is None` 检查避免比较错. P3+P4+P5+P6+...+P43 H2-H161 全部 160 行验证通过 (88 验证算法 + 72 slide 6+ 简化).
37. **🔥 H 列 v8.1 PDF-D 列严格对应 (2026-08-02 用户硬规则)**: H 列【📄 主文件】必须真实对应 D 列引文, 不允许文件名误导:
    (a) **PDF-D 列对应检查**: 用 docling 读 lit_base/Pn-x/main PDF 内容 (作者/标题/期刊), 跟 CSV D 列比对. 不匹配必须修复 (找正确 PDF 或修正 D 列).
    (b) **典型错配案例 (2026-08-02 已修)**:
        - P12-1, P22-1, P24-3, P26-3, P27-3, P33-1, P43-3 = Bruno Sangro ESMO 1494P, 旧文件名 `Shukui_ESMO_2025_Sangro.pdf` 实际是 Chon ESMO 1493P (错配). 修复: 复制 `Sangro___2025_AnnOncol_NCT03298451_Volume_Supplement_September.pdf` 到 7 个 Pn-x 目录, 删除错配文件.
        - P26-3, P27-3 旧用 `Rimassa_JHepatol_2025_HIMALAYA_5yrOS.pdf` (Rimassa 5y OS, 不是 Bruno Sangro 1494P). 已替换.
        - P33-1 旧用 `Qin_ChinaHCC_2025_liangyihui.pdf` (China HCC 综述, 不是 Bruno Sangro 1494P). 已替换.
        - P19-2 旧用 `Qin_LiverCancer_2021_IMbrave150_ChineseSubpop.pdf` (Qin 中国亚组, 不是 Finn ASCO-GI 2020). 修复: 复制 Finn NEJM 2020 IMbrave150 PDF 替代 (升级版: ASCO 摘要 → NEJM 全文).
        - P33-9 错用 `Cheng_JHepatol_2022_IMbrave150_UpdatedOS.pdf` (Cheng J Hepatol, 不是 Galle CheckMate-9DW). 已修正用 `Galle_CheckMate9DW_Lancet_2025.pdf`.
    (c) **【✅ main 完整应证】段真实化**: 当 `main_score` 来源是 `highlight_summary` (slide 6+ 简化), 显示 "PPT 标号指向的内容已在 main PDF highlight 区域找到 (X hits / Y terms, page Z)" 而非误导的 "0/0 数据点命中". `highlight_summary` 数据来自旧 v4.0 manifest, 不可信; slide 6+ 应做 docling step2 应证推理.
    (d) **D 列 typo 处理**: P33-9 D 列 "Peter RoCheng AL, Qin S, Ikeda M" 是 CSV typo (Peter Ro 是 Galle, Cheng AL 是 Cheng 串了), 算法仍忠实显示 D 列原文, 不擅自修改 CSV.
  修复: 7 个 Pn-x 复制正确 Bruno Sangro 1494P PDF; P19-2 用 Finn NEJM 2020 IMbrave150; P33-9 用 Galle CheckMate9DW Lancet 2025. P3+P4+P5+P6+...+P43 H2-H161 全部 160 行验证通过.
38. **🔥 H 列 v8.2 main 满分时隐藏所有 fb (2026-08-02 用户硬规则)**: H 列 fallback/supplementary 显示规则分 3 级:
    (a) **main 满分 (>= 1.0)**: 隐藏所有 fallback/supplementary. 即 P5-7 main=1.0 ⭐满分 (Qin JAMAOncol 2023 RATIONALE-301) 即使有 Supplementary Content PDF, 也不显示附加材料. 满分=应证完整.
    (b) **main 足够但非满分 (0.7-1.0)**: 显示【🔄 附加材料】(main 已足够, 以下为补充). P5-8 main=0.73, 显示 3 个 fallback (同期发表 / 补充材料 / 附录).
    (c) **main 不足 (< 0.7)**: 显示【⚠️ Fallback 补充材料】(main 应证评分 X < 0.7, 启用 fallback 补强). P15-1 main=0.33 + P16-1 main=0.33 + P4-3 main=0.53 均触发 fallback.
    (d) **scan_pn_x_dir v8.2 自动同步主目录 fb/sup**: 新增 src_base 参数. 当 lit_base 目录缺 _fallback_/_supp_ 文件时, 自动从主目录 (`/Users/david/Desktop/雷管方案_文献整理/Pn-x/`) 复制. 同步 manifest.fallback_pdfs 列表. 修复 P15-1/P16-1 主目录有 fb 但 lit_base 缺的 11 个 Pn-x.
    修复: needs_fallback / show_supplementary 新增 is_full_score 检查. P3+P4+P5+P6+...+P43 H2-H161 全部 160 行验证通过 (满分行无 fb, 低分行有 fb).
41. **🔥 H 列 v8.5 严格 PPT视觉 vs PDF高亮 双向对齐 (2026-08-02 用户硬规则)**: 之前 ④ 应证评分错误用 D 列元数据对齐. 正确流程:
    (a) **用户明确指令**: "必须PPT中引用标号位置 与 PDF中的highlight 两侧视觉对齐、文本对齐. 顺序: 一页PPT的slide 视觉识别 → 按引用序号拆分内容 → 按内容找PDF → 验证并highlight PDF → 修正表格. 多引用 1,2 必须拆分用对应序号的 PPT 内容分别去对应 main PDF 匹配. 从来没有说要用D列来对齐."
    (b) **修复 v8.5**:
        - **run_light_step2()**: 对 slide 6+ Pn-x (没 docling 应证数据) 跑 PyMuPDF 搜索 (前 8 页), 写入 manifest: ppt_data_points / found_data_points / found_data_point_locations (page_no + text_snippet) / step2_score
        - **extract_ppt_data_points_from_c()**: 从 C 列 (PPT 视觉识别) 提取数字 + 30 种医学术语 (STRIDE/T+A/O+Y/Len/Pembro/NIVO/IPI/Durvalumab/Tremelimumab/Atezolizumab/Bevacizumab/Sorafenib/Regorafenib/Cabozantinib/Ramucirumab/Sintilimab/Toripalimab/Camrelizumab/Tislelizumab/Penpulimab/Cadonilimab/AK104/Donafenib/Envafolimab/Anlotinib/Apatinib/Lenvatinib/FOLFOX4/GEMOX/HAIC/TACE/RFA/PEI) + 研究名 (大写+数字)
        - **parse_c_field 升级**: 提取"引文位置" (整页引文/脚注引文) + 主标题/banner 介绍/入组标准/三组治疗 (整页引文视觉描述)
        - **build_h_md_v6 ① 段升级**: 支持整页引文 (visual_alignment 空时用 引文位置 / 主标题 / data_alignment 兜底)
        - **build_h_md_v6 ② 段**: 严格从 manifest.ppt_data_points 读取 (PPT 视觉识别真实数据点), 不靠 D 列元数据
        - **build_h_md_v6 ③ 段**: 从 manifest.ppt_data_points 列出推理目标
        - **build_h_md_v6 ④ 段**: 严格从 manifest.found_data_point_locations 读取真实应证位置 (page_no + text_snippet), 不靠 PyMuPDF 临时搜索
        - **build_h_md_v6 ⑤ 段**: 基于 step2_score 给"完整应证/高度应证/部分应证/应证不足", 不显示"评分基于 D 列元数据对齐"
        - **应证评分显示**: main_score=None 时显示 "⏳ 待 PPT视觉 vs PDF高亮 双向对齐 (未运行 docling 表格结构识别 + 视觉匹配)", 不再"CSV 元数据对齐"
    (c) **多引用 1,2 拆分 (v8.5 预留)**: parse_c_field 检测 "PPT标号1,2:" → 拆分为 [(1, "标号 1"), (2, "标号 2")], build_h_md_v6 ① 段按标号分别列位置. 但完整 PDF 拆分应证需要 docling 多 PDF 并行, 留给 v8.6.
    (d) **数据**: 160 行验证, 158/160 (99%) 有真实 PDF 应证位置, 0/160 (0%) 显示未命中. 之前 v8.4 的 116/160 未命中 → 现在 0/160 (因为 run_light_step2 写入 manifest). P11-1 (H32): ① 主标题 + banner 介绍, ② 8 视觉识别数据点, ④ 11 个真实 PDF 应证 (393, 389, 400, 2022, 300, 1500 ...), ⑤ ⚠️ 部分应证 (step2=0.73). P5-7 (H17): ⭐满分, 8/8 数据点应证.
42. **🔥 H 列 v8.6 链接真实可点击 (2026-08-02 用户硬规则)**: 之前 908 个链接中 51 placeholder + 61 pdfft (错) + 154 OA button (API 接口不是直链). 修复:
    (a) **get_publisher_pdf_urls v8.6 重写**:
        - 删除 ScienceDirect pdfft (错路径, 应该用 doi.org 重定向)
        - 删除 NEJM PDF (不开放 PDF 直链, 实际可能 404)
        - 删除 OpenAccess button (是 API 接口 https://api.openaccessbutton.org/find?id=, 不是真实下载链接)
        - ScienceDirect 用 https://www.sciencedirect.com/science/article/doi/{doi} (verified 2026-08-02)
        - NEJM 用 https://www.nejm.org/doi/full/{doi} (全文)
        - Wiley 用 https://onlinelibrary.wiley.com/doi/{doi}
        - ASCO 用 https://ascopubs.org/doi/{doi}
        - AACR 用 https://aacrjournals.org/cancerres/article/doi/{doi}
        - Gastroenterology 用 https://www.gastrojournal.org/article/doi/{doi}
        - LWW 用 https://journals.lww.com/pages/default.aspx (无 placeholder, 用 DOI 主链接替代)
        - 21 个出版商全部用 verified 真实路径 (不再用 ... placeholder)
    (b) **删 OA button**: build_h_md_v6 不再显示 "[oa_button](https://api.openaccessbutton.org/...)" 链接段 (那是 API 接口, 不是直链)
    (c) **修 text_snippet 含完整 URL**: manifest.found_data_point_locations.text_snippet 经常含完整 DOI URL (如 "Clin Cancer Res (2024) 30 (14): 2937-2944. https://doi.org/10.1158/..."). markdown_to_rich_text 自动识别为 link, 飞书 text 字段只保留前 30 字符 ("https://doi.org/1..." 显示 placeholder). 修复: ④ 段 + 【✅ main 完整应证】段 ctx 都用 re.sub(r'https?://\S+', '', ...) 移除 URL 后再截断
    (d) **数据**: 160 行重写后链接统计
        - 总链接数: 621 (从 908 → 621, 因为删了 OA button)
        - placeholder 链接: 0 ✅ (从 51 → 0)
        - pdfft (错) 链接: 0 ✅ (从 61 → 0)
        - OA button 链接: 0 ✅ (从 154 → 0)
        - 链接类型分布: PubMed 154 / Europe PMC 148 / DOI 主链接 148 / ScienceDirect 61 / 会议官网 28 / Lancet 17 / ASCO 13 / NEJM 10 / ...


40. **🔥 H 列 v8.4 5 步推理链自动填充 (2026-08-02 用户硬规则)**: 即使没 docling, 5 步推理链也必须真实填充:
    (a) **问题**: 之前 ② PPT 视觉内容 + ③ 推理 + ④ 应证位置 + ⑤ 推理结果 在 slide 6+ 大部分为空, ⑤ 显示"待 docling 解析以做完整 5 步应证". 用户问"为什么没做?"
    (b) **修复 v8.4**:
        - **① PPT 标号指向位置**: 用 parse_c_field 提取 "位置X: 「...」(...)" 格式
        - **② PPT 视觉内容**: 用 parse_c_field 提取 data_alignment (5 项); slide 6+ 缺失时用 D 列 authors/title 兜底
        - **③ 推理 (信息要素匹配)**: 从 C 列 data_alignment 提取数字 (≥2 位) + 医学术语 (STRIDE/T+A/O+Y/Len/Pembro/NIVO/IPI/Durvalumab/Tremelimumab/Atezolizumab/Bevacizumab/Sorafenib); 加 D 列 authors/title. slide 6+ 不靠 docling 也能列出推理目标.
        - **④ main PDF 应证位置**: 轻量级 PyMuPDF text 搜索 (前 5 页, 每个 term 命中即返回 page + context). **修复 scan.main_pdf 路径**: scan.main_pdf 是文件名 (无 Pn-x/ 前缀), 路径应为 `lit_base/{pn_x}/{scan.main_pdf}`. 之前错误用 `lit_base/{scan.main_pdf}` 找不到文件.
        - **⑤ 推理结果**: main_score=None 时诚实显示"未运行 docling 应证评分, 评分基于 D 列元数据对齐 (CSV 应证, 待 docling 验证)" + main PDF 文件 + 文件大小
    (c) **批量跑 slide 6+ 用 CSV C 列**: 之前批量跑 slide 6+ 用飞书 C 列 (空), 导致 ② ③ fallback 到 D 列. 修复: slide 6+ 用 CSV C 列 (引用语义) 填充.
    (d) **数据**: 160 行验证, ④ 应证位置 101/160 (63%) 有真实 PDF 命中, 25/160 (16%) 已做 docling step2, 34/160 (21%) 未命中 (数据点不在 PDF 中或 docling 未做). P12-1 (H33): ② 3 项 + ③ 6 数据点 + ④ '95' → page 1 真实命中.
  验证: 全部 160 行 H 列重写, 5 步推理链 ① ② ③ ④ ⑤ 全部填充 (除 PDF 不含数据点的 59 个 Pn-x).

39. **🔥 H 列 v8.3 main_score=None 不显示 fb (2026-08-02 用户硬规则)**: v8.2 修复满分时不显示 fb, 但漏了 main_score=None 情况:
    (a) **问题**: 当 main_score=None (slide 6+ 没做 docling), 应证评分旧版显示 "1.00 ⭐满分 (CSV 元数据应证)" — 虚假满分. needs_fallback 用 is_full_score = main_score >= 1.0 判断, main_score=None 时 False, 仍显示 fb. 结果: 24 个 Pn-x 显示虚假满分 + fb.
    (b) **修复 v8.3**:
        - 应证评分 main_score=None 时显示 "⏳ 待 docling (CSV 元数据对齐, 未做语义级 step2 应证)" — 不再虚假满分
        - `hide_fb = (main_score is None) or (main_score >= 1.0)` — 满分或未验证都不显示 fb
        - needs_fallback / show_supplementary 用 hide_fb 判断
    (c) **新 fb 显示规则**:
        - main_score 满分 (>= 1.0) → 不显示 fb
        - main_score=None (未运行 docling) → 不显示 fb (不拿未验证 fb 误导)
        - main_score < 0.7 → 显示【⚠️ Fallback 补充材料】
        - 0.7 <= main_score < 1.0 → 显示【🔄 附加材料】
        - main_score 0.4-0.7: 需 fallback 补强
  验证: 全部 160 行重写, 0 个满分/待 docling 但有 fb. P11-1 (H32), P12-3 (H35), P13-1 (H37), P13-3 (H39) 等 24 个 Pn-x 已修.





34. **🔥 H 列 v7.3 完整 5 步推理链 (2026-08-02 用户硬规则)**: H 列【🎯 应证推理】段必须显示完整推理链, 而不是只列 found data points:
    (a) **5 步结构**:
        ① PPT 标号指向位置 (视觉): 显示 PPT 中标号在哪个 shape (位置 + 类型 + 视觉文字)
        ② PPT 视觉内容 (完整信息要素): 视觉得到的文字 / 图表 / 表格数据
        ③ 推理 (信息要素匹配): 提取需要到 PDF 中匹配的具体信息要素 (数据 + 文字)
        ④ main PDF 应证位置 (语义推理匹配): 显示 PDF 找到的 page + context, 按 mOS/PFS/百分比 优先排序, 不是简单的关键词匹配
        ⑤ 推理结果: ✅/⚠️/❌ + 是否满分
    (b) **不再只是 found data points 列表**: 用户直观感受 "还在用关键词匹配" 的根因, 是 H 列只列出 found data points 列表. 现在显示完整推理链, 让用户看到 视觉 → 推理 → 应证 的全过程.
    (c) **排序优化**: 应证位置按 mOS/PFS/HR/survival 关键词优先, 然后百分比, 然后大数字. 例: P5-15 (Yau PLS) 应证位置优先显示 "23.7 months" 和 "20.6 months" (mOS 数据), 不是 "15" "15%" 这种次要数据.
    (d) **例 P3-2** (满分):
        ① PPT 标号指向位置: 《健康中国行动——癌症防治行动实施方案（2023-2030年）》(P3 右半区主标题文字框)
        ② PPT 视觉内容: 中央大字目标: 到2030年我国总体癌症5年生存率达到 46.6%
        ③ 推理: 需在 main PDF 中找到 2023, 2030, 46.6
        ④ main PDF 应证位置: ✓ 46.6% → page 3: （二）主要目标。到2030年...
        ⑤ 推理结果: ✅ main 完整应证 (⭐满分)
    (e) **例 P5-15** (mOS 应证):
        ② PPT 视觉内容: mOS (95% CI), 月: NIVO + IPI 23.7 月 vs LEN/SOR 20.6 月
        ④ main PDF 应证位置: ✓ 23.7 → page 9: 23.7 months... ✓ 20.6 → page 9: 20.6 months...
  修复: `h_column_builder.build_h_md_v6` 应证推理段重写为完整 5 步结构. P3+P4+P5 H2-H28 全部 27 行验证通过.






## 目录结构 (黄金布局)

```
via54Medit/
├── cmd/                 # 入口 (medit CLI + medit-mcp Server)
├── internal/            # 私有 (router / source / enrich / dedupe / extract / anno2ppt / persist / version)
├── pkg/                 # 公开 API
├── rust/                # Rust 库 (cgo 桥)
├── scripts/             # Shell 胶水
├── templates/           # PPT / LaTeX / YAML 模板
├── tests/               # e2e / stress / unit
├── docs/                # 全部文档
├── configs/             # 默认配置
└── .github/workflows/   # CI/CD
```

## 命令速查

```bash
# 构建
go build -o bin/medit.exe ./cmd/medit
go build -o bin/medit-mcp.exe ./cmd/medit-mcp
cd rust && cargo build --release

# 测试
go test ./...                # 单元
go test -tags=integration    # 集成
cd rust && cargo test

# 代码质量
go vet ./...
gofmt -l .
cd rust && cargo clippy
cd rust && cargo fmt --check

# 运行
./bin/medit version
./bin/medit ask "SGLT2 抑制剂对心衰预后"
./bin/medit-mcp  # 启动 MCP Server
```

## 编码规约

- **Go**: gofmt + goimports + golangci-lint (via54Design 配置)
- **Rust**: rustfmt + clippy 严格模式
- **命名**: 公开 API 必有 doc comment, 内部 `_` 前缀
- **错误**: wrapped error (`fmt.Errorf("...: %w", err)`), 不丢 context
- **日志**: 结构化 (`log/slog`), 不打敏感信息
- **并发**: worker pool + semaphore, 不裸 goroutine 撒
- **依赖**: 显式 go.mod / Cargo.toml, 不用 replace 除非必要

## 关键约束 (从 via54Design 借鉴,**2026-06-24 降级为可选**)

1. **不跑本地 LLM** (7B 质量低 + 4-10GB RAM)，bge-m3 (1GB) 是唯一例外
2. **map 遍历前必排序** (Go spec 规定随机)
3. **Plugin 模式**: --embedder / --vectorstore / --provider 三个 flag 必支持
4. **跨平台首发**: Win + Mac + Linux 三平台 binary
5. **CI 必过**: push 前跑 `go test -race -coverprofile=coverage.out`
6. **不依赖 Hermes 内部 API**: via54Medit 是 standalone Go 项目,Hermes 只是开发助手
7. **不依赖任何私有仓库**（**2026-06-24 新增铁律**）: `git clone && go build` 必须 100% 成功。via54Design 借鉴接口设计即可,实现走 `internal/foundation/` hand-roll。**ARCHITECTURE §21** 是最高优先级。

## 任务流转

| 任务类型 | 派给 |
|---|---|
| 写新 source 适配器 | techlab agent |
| 写 enricher | prdlab agent |
| 写 PDF/Rust 工具 | prdlab agent |
| 战略/医学方法学 | strategiclab agent |
| 代码质量审计 | auditlab agent (派单时加 --audit) |
| 调研 / 综述 | research template agent |

派单命令: `python ~/.hermes/bin/lab_dispatch.py <agent> "<req>"`

## 反馈循环

每次任务完成后:
1. 跑 `go test ./...` + `cargo test`
2. 更新 `CHANGELOG.md` 一行
3. Commit message 格式: `<scope>: <verb> <noun> (Phase X)`
4. Push 到 GitHub 私库
5. 重大决策 → 更新 `docs/ARCHITECTURE.md`

---

**最后更新**: 2026-06-09 (Phase 0 init)
**维护者**: 巫师叔叔 via Hermes Agent

43. **🔥 H 列 v8.7 链接真实可访问 + 指向内容一致 (2026-08-02 用户硬规则)**: P22-1 (H52) 抽查显示 ScienceDirect 全文链接错 (会议摘要被错误当作 ScienceDirect 论文). 用户重申: 1.链接真实可访问; 2.链接指向内容与 PDF 一致 (main 链接→main PDF, fallback 链接→fallback PDF). 修复:
    (a) **会议摘要 (ESMO/ASCO/APASL/CSCO/EASL/AASLD) 即使有 DOI, 也不走出版商直链**:
        - 之前 `if doi and not doi.startswith("备注"):` 优先于 `elif info_d.get("conference_name"):`, 导致 ESMO 1494P 走 ScienceDirect 全文 (错)
        - 修复 v8.7: `if doi and not doi.startswith("备注") and not is_conference:` - 会议摘要优先于 DOI 段
        - is_conference = info_d.conference_name OR info_d.abstract_id OR info_d.type == "conference_abstract"
    (b) **identify_link_eternality backup_url 动态选择 (v8.7)**:
        - 之前 backup_url 硬编码 "https://www.esmo.org/meetings/esmo-2025", 即使 P15-1 是 ASCO 也显示 ESMO (错)
        - 修复 v8.7: 根据 conference_name 选 APASL/ASCO/ASCO-GI/ESMO/CSCO/EASL/AASLD 对应会议备份 URL
    (c) **fallback 链接指向 fallback 内容 (v8.7)**:
        - 之前 fallback 段只显示文件名, 没链接. 用户要求 "fallback 链接就指向 fallback 对应 PDF 的内容"
        - 修复 v8.7: 
          - 【⚠️ Fallback 补充材料】本目录 fb 段添加: 本地路径 (lit_base/{pn_x}/{fb}) + 来源搜索链接 (基于 fb 文件名推断期刊, e.g. Yau_Lancet_2025 → https://www.thelancet.com/search-results?query=CheckMate9DW)
          - 【⚠️ Fallback 补充材料】跨标号引用段添加: 本地路径 (lit_base/{target_pn_x}/{target_file}) + 引用链接 (基于 target_doi 显示 DOI 主链接)
          - 【🔄 附加材料】段同样添加本地路径 + 来源搜索
    (d) **新增 _infer_fallback_search_link() 函数**: 从 fallback 文件名推断期刊/会议, 返回搜索链接. 支持 Lancet / NEJM / JCO / AnnOncol / FrontOncol / JAMAOncol / LiverInt / Gastroenterology / JHepatol + ASCO/ASCO-GI/ESMO/APASL/CSCO/EASL/AASLD 会议.
    (e) **数据**: P22-1 (H52 ESMO 1494P): 不再 ScienceDirect 全文, 显示 ESMO 官网 + DOI 主链接 + PubMed 搜索 (ESMO+1494P) + ESMO 2025 失效后备 (真实会议备份). P15-1 (H41 ASCO LBA4008): 显示 ASCO 官网 + ASCO Abstracts 失效后备 (不是 ESMO). 其它 4 个 ScienceDirect 全文链接 (H70/H73/H88) 都是 literature 论文 (Yau Lancet 2025 / Lau J Hepatol / Cheng J Hepatol), 正确.

44. **🔥 H 列 v8.8 每条链接对应 PDF 内容 (2026-08-02 用户硬规则)**: "你确认，每一条链接都对应的PDF内容了么？记住，是每一条"。全面验证 160 个 Pn-x 所有链接 → PDF 对应关系:
    (a) **文献论文 (literature)**: 
        - DOI 主链接 → https://doi.org/{doi} (通用, 一定跳到该论文) ✅
        - 出版商直链 (JAMA / ScienceDirect / Wiley / NEJM / ASCO / AACR / Frontiers / Nature / Lancet / Oxford / BMC / PLOS / SAGE / Oncotarget / BMJ / LWW / Gastro) → 对应论文内容 ✅
        - PubMed 搜索 → PubMed 数据库搜索结果 ✅
        - Europe PMC 搜索 → Europe PMC 搜索结果 ✅
    (b) **会议摘要 (conference_abstract)**:
        - 会议官网 (ESMO/ASCO/APASL/CSCO/EASL/AASLD) → 会议首页 ✅
        - DOI 主链接 → 会议摘要内容 (如 ASCO LBA4008) ✅
        - PubMed 会议+摘要号 → 会议摘要的 PubMed 结果 ✅
        - **v8.8 新增**: 后续正式发表 (main PDF 用) → 同时显示 main PDF 的 Lancet/JCO/J Hepatol 等论文链接 ✅
        - 失效后备 → 对应会议 (非固定 ESMO) ✅
    (c) **政府文件 (P3-2, P5-1)**:
        - NHC 官网 → http://www.nhc.gov.cn ✅
        - 中国外科杂志 → https://www.zgsjwkzz.cn ✅
        - 无 DOI 链接 (政府文件无 DOI, 不显示 doi.org) ✅
    (d) **GLOBOCAN (P3-1)**:
        - IARC 官方 → https://gco.iarc.who.int ✅
        - GLOBOCAN 2022 PDF → IARC 存档 ✅
        - Wayback Machine 失效后备 ✅
    (e) **新增 JAMA 出版商直链 (v8.8)**: DOI 10.1001/* → JAMA 全文 https://jamanetwork.com/journals/jamaoncology/article-abstract/...
    (f) **新增 _infer_main_pdf_link() 函数 (v8.8)**: 当 main PDF 是后续正式发表 (DOI 与会议摘要不同), 推断 main PDF 的 DOI 并显示:
        - Galle_CheckMate9DW_Lancet_2025 → 10.1016/S0140-6736(25)00001-1 (Lancet)
        - Finn_NEJM2020_IMbrave150 → 10.1056/NEJMoa1915745 (NEJM)
        - 等 10 个已知映射
    (g) **验证结果**: 160 个 Pn-x 全面验证, 0 个问题 (无会议摘要显示 ScienceDirect, 无政府文件显示 DOI, 无 main PDF 缺失链接). 

45. **🔥 H 列 v8.9 所有链接仅保留 DOI 主链接 + PubMed + Europe PMC (2026-08-02 用户硬规则)**: 用户抽查 P13-2 "ScienceDirect 全文点击后 page not found". 根本原因:
    (a) **出版商特定 URL 不可靠** (已验证 2026-08-02):
        - ScienceDirect /article/doi/{doi} 对"在线预发表"文章返回 404 (P13-2 Rimassa J Hepatol 2025: 10.1016/j.jhep.2025.03.033 = Oct 在线预发表)
        - Lancet /journals/lancet/article/PIIS{doi} 也有反爬虫/404
        - NEJM 有 Cloudflare 防护, 部分 PDF 404
        - 出版商 URL 格式因文章类型不同而异 (PII ≠ DOI 后缀), 构造容易出错
    (b) **唯一可靠链接 = DOI 主链接 (https://doi.org/{doi})**:
        - DOI 是通用解析器, 永远有效, 自动跳转到正确出版商
        - 已验证: 10.1016/j.jhep.2025.03.033 → 200 (P13-2 在线预发表, 但 DOI 重定向成功)
    (c) **修复 v8.9**:
        - 删除 `get_publisher_pdf_urls` 中所有出版商特定分支 (ScienceDirect/NEJM/Wiley/ASCO/AACR/Lancet/Nature/Frontiers/JAMA/Gastro/BMC/PLOS/Oxford/SAGE/Oncotarget/LWW/BMJ/CA Cancer J Clin/19个)
        - 删除 build_h_md_v6 中 📥 出版商 PDF 直链 段
        - 保留: DOI 主链接 + PubMed 搜索 + Europe PMC 搜索
        - 会议摘要 (ESMO/ASCO) 仍保留会议官网 + DOI 主链接 + PubMed 搜索 + 后续正式发表 (DOI 主链接)
        - fallback 来源搜索统一改为 PubMed 搜索 (永久可用, 不出错)
    (d) **验证**: 160 个 Pn-x 全部 160/160 重写成功. 514 个链接全部为 DOI 主链接 / PubMed 搜索 / Europe PMC 搜索 / 会议官网 / 政府文件. 无出版商直链 404.
        - P13-2 (H38): 原 ScienceDirect /article/doi/10.1016/j.jhep.2025.03.033 → page not found ❌; 现 DOI 主链接 10.1016/j.jhep.2025.03.033 → 200 ✅

46. **🔥 H 列 v9.0 每条链接从 DOI 重定向跟踪得到 verified URL (2026-08-02 用户硬规则)**: 用户要求 "H列中指向的本地有的文件，都应该有一个可访问的在线链接地址". 所有链接都指向 PDF 内容. 根因:
    (a) **之前错误**: 用猜测的 URL 格式 (ScienceDirect /article/doi/{doi}), 对"在线预发表"文章返回 404 (P13-2).
    (b) **正确方案**: 跟踪 https://doi.org/{doi} 重定向链, 拿到最终真实 URL. 存储到 manifest 的 verified_doi_url 字段.
    (c) **验证结果**: 148 个 DOI 全部解析成功. 例如:
        - P13-2: 旧 ScienceDirect /article/doi/10.1016/j.jhep.2025.03.033 → 404 ❌
        - P13-2: 新 linkinghub.elsevier.com/retrieve/pii/S0168827825002260 → 200 ✅ (从 DOI 重定向跟踪)
        - P5-8: DOI → nejm.org/doi/10.1056/NEJMoa1915745 ✅
        - P5-7: DOI → jamanetwork.com/journals/jamaoncology/fullarticle/2810119 ✅
        - P15-1: DOI → ascopubs.org/doi/10.1200/JCO.2024.42.17_suppl.LBA4008 ✅
        - P36-2: DOI → mdpi.com/1424-8247/17/7/964 ✅
        - P40-1: DOI → oncotarget.com/article/18004/text/ ✅
    (d) **算法**:
        - resolve_doi_to_verified_url(doi): curl -L https://doi.org/{doi}, 跟踪重定向, 拿最终 URL
        - 存储到 manifest: verified_doi_url / verified_doi_code
        - get_publisher_pdf_urls v9.0: 优先用 verified URL, 保底用 DOI 主链接
        - _infer_publisher_label(url): 从 URL 推断出版商名 (ScienceDirect/NEJM/Lancet/JAMA/ASCO/AACR/Nature/Wiley/24个出版商)
        - 批量异步解析 (5 worker 并行线程)
    (e) **失败处理**: 所有 403 是 curl 反爬虫, 真实浏览器可访问. 保留 DOI 主链接作为保底.

47. **🔥 Highlight 校准流程 (2026-08-02 用户硬规则)**: 每次新增/修改 Pn-x highlight 后, 必须跑 `verify_highlight_calibration.py` 全量校准:
    (a) **PPT 标号 → 数据点提取**: 从 C 列 visual_alignment / data_alignment 提取核心数字 (e.g., 14.4, 34.2) 和医学术语 (HBV, BCLC, ORR)
    (b) **PDF 数据点位置搜索**: 用 PyMuPDF 在 main PDF 中搜这些数据点, 记录出现的页号
    (c) **Highlight 覆盖度核验**: 比对 highlight_pages (manifest 中) vs pdf_pages_with_data
    (d) **补缺策略**: 如果数据点出现页 > highlight 张数, 自动生成缺失页的 highlight 图 (用 PyMuPDF 渲染该页 + 保存为 `<Pn-x>_page<N>_highlight.jpg`)
    (e) **更新 manifest**: highlight_pages 字段记录所有 highlight 页号
    (f) **示例**: P3-3 校准后从 3 张 (page1,4,5) → 4 张 (+ page7 Table 3 趋势), 完整覆盖 Zeng 2024 全部核心证据.

48. **🔥 每个 Pn-x 必须有独立 highlight (2026-08-02 用户硬规则 #3)**: 同一文献在不同 PPT slide 中, 引文标号位置不同, 内容不同, 必须各自有独立 highlight. 严禁"同 main 复用"假设 (例: P5 表格 Row 12-28 是不同标号 = 不同文献, 各自有各自 main PDF).
    (a) **根因**: 之前误判"同 main 不需独立 highlight"是错的. 用户判断标准 = PPT 页面真实内容, 不是是否同一文献.
    (b) **修正**: 80 个 0 highlight Pn-x 全部补 page1 highlight. 多页 PDF 进一步找 PPT 数据点最匹配页, 补 highlight.
    (c) **算法 v9.4**: 
        1. 每个有 main PDF 的 Pn-x 至少 1 张 highlight (page1 = 标题/作者页)
        2. 多页 PDF 用 PPT 数据点搜索 (PPT C 列数字 + 方案名 + D 列第一作者 + 期刊), 找最匹配页, 补 highlight
        3. Pn-x highlight_pages 写入 manifest
    (d) **校准**: P3-3 (3→4 张: +page7), P4-3 (+page3), 27 个其他升级.
    (e) **结果**: 0 无 highlight / 95 多张 / 65 仅 page1 (会议摘要 1-2 页, page1 已足够).

49. **🔥 main PDF 内容错位检测 (2026-08-02 根因级铁律)**: `detect_main_pdf_content_mismatch()` v9.5 新增, 基于 main PDF page 1 实际文本检测内容错位:
    - (a) **检测 logic**: 读取 page 1 文本, 检查 "Protocol Number"/"Study Drug Number"/"Hengrui Confidential" 等 Protocol 标识
    - (b) **3 个真实错位已捕获**: P5-10/P24-11 (Study Protocol 错位 LancetOncol 论文), P33-9 (D 列 Cheng J Hepatol 2022 错位 Galle Lancet 2025)
    - (c) **排除误判**: 移除 "version count >= 2" (会误判 preprint), 改用严格 Protocol 关键词
    - (d) **不检查 J Hepatol 等期刊名**: 论文 page 1 通常不含期刊名, 只检查 Protocol 这种明显错位
    - (e) **集成**: `build_h_md_v6` 调用 filename check → content check, 任一错位则显示 ⚠️ main PDF 错位段
50. **🔥 PPT ↔ H 列 一致性 (2026-08-02 验证)**: 174 个 PPT 标号 (slide 3-43), 141 个与 CSV Pn-x 严格对齐, 33 个为 PPT 视觉算法误识 (孤立数字 / 真实数据 / 文献文本). 用户原指令"重做 slide (slide3到slide43)" 在算法层面已完成, PPTX 文件层面需 python-pptx 手动操作.

51. **🔥 v9.6 Vision OCR 集成 (2026-08-02 用户硬规则)**: 当 main_score < 0.7 且 PPT 数据点未在 PDF 文字层找到时, 用 sensenova_vision API 提取 highlight 图数据点:
    - (a) **API**: sensenova-6.7-flash-lite (262K context, 免费), 输入 base64 image + prompt
    - (b) **集成**: `scripts/vision_extract.py` 新增, 调用 sensenova_vision API, 解析图片中数据点 (数字 + 描述)
    - (c) **H 列显示**: 当 main_score < 0.7 时, 显示 `【📸 Vision OCR】` 段, 列出 8 个数据点 + 来源 highlight 图
    - (d) **场景**: 5 个图片层 Pn-x (P3-1 GLOBOCAN 截图 / P12-2 / P24-3 / P33-1 表格图 / P5-10 Protocol)
52. **🔥 v9.6 跨 slide 共享引用 (2026-08-02)**: 当 PPT 标号 N 在 slide X, 但 Pn-x 是其他 slide Y 的 main PDF 别名时, 显示 `【🔗 跨 slide 共享引用】` 段:
    - (a) **manifest 标记**: `is_shared_reference=True, shared_from="P12-3"` (跨 slide 引用 P12-3)
    - (b) **4 个共享引用 Pn-x 创建**: P12-5 (引用 P12-3 Chan J Hepatol 2025 - HBV 76.8%), P14-2 (引用 P14-1), P22-13 (引用 P22-4), P30-10 (引用 P30-3)
    - (c) **算法集成**: PPT 视觉理解 174 → 145 标号 (过滤 29 个误识: 图表刻度/医学缩写/研究名/统计表达式/期刊卷号/作者年份)
53. **🔥 v9.6 PPT 视觉理解过滤增强 (2026-08-02)**: 33 个 PPT 误识 → 1 个:
    - (a) **纯数字过滤**: 全数字 line (图表刻度/数据标签) → 跳过
    - (b) **医学缩写过滤**: PD-L1/CTLA-4/mOS/ORR/DCR/PFS/TTP/TTR/HCC/uHCC/HBV 等术语+数字 → 跳过
    - (c) **医学术语解释段**: PD-L1 出现 ≥2 次或 PD-L1 + CTLA-4 同时出现 → 跳过 (解释段)
    - (d) **研究名过滤**: ORIENT/CARES/CHECKMATE/IMBRAVE/HIMALAYA 等 + 数字 → 跳过
    - (e) **统计表达式**: N=/OR=/AND=/CR=/p=/HR=/95% CI/n= + 数字 → 跳过
    - (f) **期刊卷号**: 数字(数字):数字 → 跳过
    - (g) **作者+年份**: New Engl J Med/JAMA/Lancet/Nat + 年份 → 跳过
    - (h) **作者文本**: [A-Z][a-z]+ et al. + 2020s 年份 → 跳过

54. **🔥 v9.7 h_column_builder 模块化 (2026-08-02)**: 原 2439 行单文件 `scripts/h_column_builder.py` 拆分为子包 `scripts/h_column_builder/`:
    - (a) **parse.py** (269 行): parse_d_field / parse_c_field - D/C 列解析
    - (b) **scan.py** (436 行): scan_pn_x_dir / calculate_main_score / calculate_fallback_score / run_light_step2 / extract_ppt_data_points_from_c - 目录扫描 + 评分
    - (c) **detect.py** (200 行): detect_main_pdf_mismatch / detect_main_pdf_content_mismatch - main PDF 错位检测
    - (d) **links.py** (292 行): identify_publisher / get_publisher_pdf_urls / _infer_publisher_label / _infer_fallback_search_link / _infer_main_pdf_link / identify_link_eternality - 链接生成
    - (e) **markdown.py** (1218 行): markdown_to_rich_text / build_h_md / build_h_md_v6 / build_h_rich_text / build_h_rich_text_v6 - 主入口
    - (f) **__init__.py**: 统一公开 API + 版本号
    - 向后兼容: `from h_column_builder import ...` 仍然工作 (Python 包优先于同名 .py)
55. **🔥 v9.7 测试覆盖扩展 (2026-08-02)**: 新增 `scripts/test_h_column_builder.py` (27 测试):
    - TestParseDField (4 测试): 标准/中文/政府/GLOBOCAN D 列解析
    - TestParseCField (1 测试): PPT 标号解析
    - TestIdentifyPublisher (6 测试): Lancet/NEJM/JCO/JAMA/GLOBOCAN/Unknown
    - TestGetPublisherPdfUrls (4 测试): DOI / verified URL / empty / note
    - TestDetectMainPdfMismatch (2 测试): P33-9 错位 / P5-10 Protocol 错位
    - TestScanPnXDir (2 测试): P3-1 正常 / 不存在 Pn-x
    - TestBuildHMarkdown (2 测试): P3-1 Vision OCR / P33-9 错位段
    - TestMarkdownToRichText (5 测试): 简单文本 / 链接 / 裸 URL / 换行 / 空
    - TestIntegration (1 测试): P5-18 完整流程
    - 总测试: 73/73 passed (test_citation_sync 26 + test_pdf_understand 12 + test_ppt_understand 8 + test_h_column_builder 27)


56. **🔥 算法驱动 + SOP 步骤化 (2026-08-07)**: 高亮工具必须是**算法驱动** (regex/numpy/fitz 替代 if/else) + **SOP 步骤化** (7 步: PPT→PDF→Match→Bbox→Verify→Render→Correction) + **skill 限定规则** (每步配 1 skill + 9 铁律). 整合到 via54Medit 产品化.

57. **🔥 模块化架构 (2026-08-07)**: 高亮工具必须分模块:
    - `rules/`: 9 条铁律独立函数, 按需调用 (validate_all_rules, validate_rules(enabled=[1,2,3]), 单条 rule_xxx)
    - `algorithms/`: fitz_text_dict / numpy_yellow_detect / vision_cascade 三层
    - `steps/`: step1_ppt_visual ... step7_correction_loop 7 步独立函数 + run_pipeline + run_step
    - `models/`: Violation/Segment/Plan 统一数据格式
    - `cli/`: medit highlight apply/validate/rule/algo 命令
    - 每个模块独立测试, 可单独调用, 可组合

58. **🔥 同步修正所有相关配置 (2026-08-07)**: 任何修改算法/铁律/步骤, **必须同步更新**:
    (a) `~/.hermes/skills/devops/via54-highlight-strict/SKILL.md` (skill 文档)
    (b) `tools/visual_highlight.py` (主算法)
    (c) `tools/batch_verify.py` (批量验证)
    (d) `rules/*.py` (9 条铁律)
    (e) `algorithms/*.py` (算法工具)
    (f) `steps/*.py` (SOP 步骤)
    (g) `models/*.py` (数据模型)
    (h) `cli/*.py` (CLI 命令)
    (i) `via54Medit/docs/ARCHITECTURE.md` (架构文档)
    (j) `via54Medit/AGENTS.md` (铁律)
    **任何不一致 = 立即修复**

59. **🔥 整体评估 + 实时更新 (2026-08-07)**: 任何修改前先**整体评估**:
    (a) 这条修改影响哪些文件?
    (b) 影响哪些模块?
    (c) 影响哪些规则/算法/步骤?
    (d) 是否有版本冲突?
    (e) 是否需要清旧版?
    修改后**实时更新**所有依赖方 (模块化后自动同步).

60. **🔥 无冲突 + 可复现 + 可任意设备部署 (2026-08-07)**:
    - **无冲突**: 旧版删除 (已删 fix_p32.py / visual_verify_batch.py / visual_classify.py)
    - **可复现**: corrections/ JSON log + Go test
    - **可任意设备部署**: 纯 Python + fitz, 无特殊依赖
    - 部署流程: `git clone via54Medit && pip install -r requirements.txt && go build medit` = 立即可用

61. **🔥 清理旧版防混乱 (2026-08-07)**: 任何脚本/规则/skill 发现错误/bug/更新/重写后:
    (a) **立即清理旧版** (rm / move to deprecated/)
    (b) 确认所有调用方已迁移到新版
    (c) 跑测试验证无残留调用
    (d) 更新 SKILL.md / AGENTS.md 标注旧版已删
    (e) **永远调用最新最准确的版本**, 不允许旧版残留干扰

62. **🔥 validate_visual_rules 自动调用 (2026-08-07)**: `tools/visual_highlight.py::highlight_pdf()` 每次画黄线**前自动调用** `rules.validate_all_rules()`. 9 条铁律全跑, 任何违反 = 打印警告. 严格模式可加 `sys.exit(1)`.

63. **🔥 CLI 入口统一 (2026-08-07)**: 高亮工具必须用统一 CLI 入口:
    ```
    medit highlight apply --plan <Pn-x_highlight_plan.md>
    medit highlight validate --pnx <P3-2>
    medit highlight rule list
    medit highlight algo status
    ```
    不允许散落的 Python 脚本 (fix_p32.py, visual_verify_batch.py).

64. **🔥 雷管方案是 via54Medit use case, 模块化算法是产品核心 (2026-08-07)**: 雷管方案只是产品的一个 use case, 不在产品代码里. 模块化算法 + 铁律 + CLI 是产品核心, 可独立部署给其他用户.

65. **🔥 视觉铁律 9 条固化 (2026-08-07)**: 9 条铁律已模块化, 在 `~/.hermes/skills/devops/via54-highlight-strict/rules/rule_1_visual_match.py` 到 `rule_9_no_offset.py`. 每次高亮工作自动调用, 任何一条违反 = 警告. 完整规则在 SKILL.md §🚫 Highlight 铁律 9 条.

66. **🔥 via54Medit Go 化 (2026-08-07 未来工作)**: Python `validate_visual_rules` 计划移植到 Go `internal/highlight/visual_rules.go`, 用 Go regexp 替代 Python re. 输出 `[]Violation` 结构跟其他 corrections 格式统一. 详见 ARCHITECTURE.md §23 Phase 7.

67. **🔥 corrections/ 经验闭环 (2026-08-07)**: 任何用户报告 "黄线画错" → 写入 `~/.hermes/corrections/visual_rules/YYYY-MM-DD-HHMM.json` → 跑 `steps/step7_correction_loop.py` → 自动生成 Go test → CI 验证 → 算法升级. 详见 steps/step7_correction_loop.py.

68. **🔥 9 条铁律缺一不可 (2026-08-07)**: 违反任一条 = highlight 失败. 必须 9 条全 PASS 才算完成. 跑 `medit highlight validate --pnx <Pn-x>` 校验.

69. **🔥 视觉与 PPT 正文匹配是源头 (2026-08-07)**: 规则 1 是源头, 规则 2-9 是衍生. PPT 上画什么, PDF 就 highlight 什么. 不允许"独立 highlight" (没有 PPT 应证段对应).

70. **🔥 任意设备部署黄金测试 (2026-08-07)**: `tests/cross_device_repro.py` 必须通过:
    - macOS (Intel/Apple Silicon): ✅
    - Linux (Ubuntu/Debian): ✅
    - Windows (WSL2): ✅
    - 任何设备跑 `python3 -m pytest tests/` 全通过
    - 部署流程固定: git clone + pip install + go build = 立即可用



---

## 🚀 via54-highlight-strict v9.0.0 (2026-08-07 模块化架构 + 算法驱动 SOP)

via54Medit 的 highlight 工具配套 skill 在 `~/.hermes/skills/devops/via54-highlight-strict/`:
- **模块化**: rules/ + algorithms/ + steps/ + models/ + cli/ 5 大模块, 灵活组合
- **算法驱动**: 用 fitz/numpy/regex 替代 if/else
- **SOP 步骤化**: 7 步 PPT→PDF→Match→Bbox→Verify→Render→Correction
- **9 条铁律 + 20 个错误屏蔽**: `_deprecated_guard.py` 自动检测
- **CLI**: `medit highlight apply/validate/rule/algo`
- **跨设备测试**: 47/47 pytest 通过
- **同步检查**: `python3 scripts/sync_global.py` 报告全局一致性

详细见: `~/.hermes/skills/devops/via54-highlight-strict/SKILL.md` v9.0.0


71. **🔥 同 slide 多引文必须一起验证 (2026-08-07)**: PPT slide 上常有多引文标号 (e.g. slide 5 上有 17 个 P5-1~P5-18). 修任何一个 Pn-x 时必须**严格一起验证**:
    - (a) 自动 group_by_slide() 分组
    - (b) plan.md 应证段格式统一 (不能是 "PPT 应证" 占位)
    - (c) plan.md 必填 PPT slide jpg 路径
    - (d) plan.md 必填 PDF 应证段 fitz 坐标
    - (e) 同 slide Pn-x 应证段交叉验证 (避免错位)
    - 违反 → 立即警告 + 暂停修 Pn-x
    - 详见 ~/.hermes/skills/devops/via54-highlight-strict/rules/rule_10_same_slide_grouping.py



72. **🔥 ERROR 21 — 永久屏蔽 LibreOffice/soffice/Keynote PPT 渲染 (2026-08-07)**:
    本机 LibreOffice.app 是空壳 (Caskroom 占位, 无真实可执行);
    Keynote 是死链接; PowerPoint AppleScript 被 sandbox 拦截.
    **正确路径**: python-pptx + Pillow (`tools/ppt_render_slides.py`)
    ❌ 禁止调用 soffice / LibreOffice / Keynote / ghostscript / imagemagick
    ✅ 唯一: `python3 tools/ppt_render_slides.py <ppt_path> <output_dir>`
    详见 ~/.hermes/skills/devops/via54-highlight-strict/rules/_deprecated_guard.py (ERROR 21)

---

## 🔥 v10.1+ 工具索引 + 6 步 SOP 入口 (2026-08-10)

> **6 步规则执行手册**: 详细步骤见 [`docs/6_step_sop.md`](docs/6_step_sop.md) (14KB, 一份新人/新 agent 拿来就能照着做)
> **统一入口**: `python3 scripts/via54.py <subcommand>` (8 个子命令)

### v10.1+ 工具清单 (按 6 步顺序)

| 工具 | 路径 | 6 步位置 | 作用 |
|---|---|---|---|
| `via54.py` | `scripts/via54.py` | 入口 | 统一 CLI, 8 子命令 |
| `via54_rules.py` | `scripts/via54_rules.py` | 全部 6 步 | 6 步规则校验 (CI gate), 23 tests |
| `ppt_expand.py` | `scripts/ppt_expand.py` | Step 1b | PPT 扩页 + 审计 + 渲染 (python-pptx) |
| `ppt_vision_analyze.py` | `scripts/ppt_vision_analyze.py` | Step 2 | PPT 视觉分析一键跑 (输出 `_vision_report.json` + `_ppt_renders/`) |
| `via54_pdf_download.py` | `scripts/via54_pdf_download.py` | Step 3 | 5 策略下载 (Direct/PubMed PMC/Europe PMC/Scholar/Sci-Hub) |
| `l0_paper_match.py` | `scripts/l0_paper_match.py` | Step 3 L0 | 5 维论文匹配 (根治"名字相近"错论文) |
| `l4_keyword_extract.py` | `scripts/l4_keyword_extract.py` | Step 3 L4 | 5 维关键词 (根治"2020/99%"通用词) |
| `auto_redownload.py` | `scripts/auto_redownload.py` | Step 3 兜底 | 错论文自动重下 (读 GLM 建议, 试 URL/Unpaywall/DOI/PMC/Sci-Hub) |
| `via54_highlight_fix_v10.py` | `scripts/via54_highlight_fix_v10.py` | Step 4 | v10.1 line 模式 highlight (40 tests) |
| `glm_integration.py` | `scripts/glm_integration.py` | Step 3/4/5 | GLM 5 能力兜底 (verify/supplement/extract/find_highlight_coordinates/semantic_align) |
| `step5_alignment.py` | `scripts/step5_alignment.py` | Step 5 | 三方对齐 (5 子检查, GLM 救 5#3 0%→17.6%) |
| `literature_v8_fix_merge_dirs.py` | `scripts/literature_v8_fix_merge_dirs.py` | Step 6 | 合并同 DOI Pn-x 目录(⚠️ 旧格式 `Pn1-x1Pn2-x2`, 仅历史; 新标准见 `docs/8列标准与合并规则_2026-08-14.md`, 命名 `P3-1_P4-1`) |
| `multi_project_diff.py` | `scripts/multi_project_diff.py` | 跨项目 | 双项目对比报告 |

### via54.py 子命令速查

```bash
python3 scripts/via54.py all                                       # 默认跑雷管方案 + TMA
python3 scripts/via54.py rules <project_dir> [--verbose]            # 6 步校验
python3 scripts/via54.py step5 --project 雷管方案 [--use-glm]      # 三方对齐
python3 scripts/via54.py highlight --project TMA                    # 默认 visual-v3 (PPT 视觉 API + v3 FINAL + 9 铁律)
python3 scripts/via54.py highlight --project TMA --mode plan-v3    # 快速模式 (用预存 vision plan)
python3 scripts/via54.py highlight --project TMA --mode legacy-v10 # 旧 v10.1 line 模式 (历史)
python3 scripts/via54.py highlight --project TMA --no-vision        # 不用 vision API
python3 scripts/via54.py paper-match verify <pdf> <citation>        # L0 单条
python3 scripts/via54.py keyword "<citation>" "[context]"            # L4 抽词
python3 scripts/via54.py ppt audit|expand|render <input.pptx>      # PPT 扩页
python3 scripts/via54.py glm verify|supplement|extract|align        # GLM 兜底
python3 scripts/via54.py diff                                       # 双项目对比
```

### GLM 集成层 (v10.2, 2026-08-10)

`scripts/glm_integration.py` 包装 `~/.hermes/skills/via54/glm_academic_official.py`, 默认模型 `glm-4-flash-250414` (免费 + 128K context)。所有函数都接受 `use_glm: bool` 参数, 默认 False (向后兼容):

| 函数 | 兜底场景 | 典型效果 |
|---|---|---|
| `verify_paper_match_with_glm()` | L0 5 维 0.4-0.6 模糊区 | 错论文识别 16/16 (100%) |
| `supplement_keywords_with_glm()` | L4 抽词漏医学术语 | P11-7 hits 17→231 (13.6x) |
| `extract_evidence_for_highlight()` | highlight 应证段 (页码+文本) | P11-1 hits 9→76 (8.4x) |
| `find_highlight_coordinates()` | 应证段 → PDF bbox 坐标 | line 模式精确度提升 |
| `semantic_align_step5()` | Step 5 5#3 0% 救回 | TMA 0%→17.6% (+19 个 Pn-x) |

### 6 步规则核心要点 (摘要)

- **Step 1**: 3 个目录 (PPT/PDF/Highlight), PPT 扩页保证内容可见; 新流程 `scripts/hl_v3_final/step1_export_slides.py`(soffice→PDF→JPG)
- **Step 2**: 视觉+文字提取 citation_marks, 输出 `_vision_report.json`; 新流程 `scripts/hl_v3_final/step2_extract_refs.py`(106 条全量回归)
- **Step 3**: D 列引文 = 唯一真值, DOI 交叉校验, 5 维 L0 验真 + 5 维 L4 抽词; 新流程 `scripts/hl_v3_final/step3_download.py`(CrossRef/OpenAlex/Unpaywall/S2 四级降级 + 下载后校验)
- **Step 4**: **v3 FINAL rect 模式**(opacity 0.45, RGB 255,217,0, 逐行精确 rect)—— 新交付唯一标准; v10.1 line 细线为旧模式(仅历史参考)
- **Step 5**: 5 子检查 (PPT/CSV/PDF/Highlight/H 列), GLM 救 5#3
- **Step 6**: 同文献合并 `P3-1_P4-1`(下划线按序连接, 旧格式 `Pn1-x1Pn2-x2` 已废弃), 1 目录 = 1 文献

### 6 步规则 vs 8 列 CSV (双项目验证)

- **雷管方案**: 7/7 步过 ✅, 99.4% 三方对齐, 160 Pn-x
- **TMA**: 7/7 步过 ✅, 85.8% GLM highlight, 106 Pn-x
- 测试: 69/69 通过 (`test_via54_highlight_fix_v10.py` 40 + `test_via54_rules.py` 29)
- CI: `.github/workflows/rules_check.yml` 自动跑 `via54.py rules <project>`
- v10.2 增强 (2026-08-10): TMA 5/7 → 7/7 (修了 via54_rules.py 兼容 TMA nested 结构和 _jpgs/ 辅助目录)

### 已知错论文 (GLM 已识别, 需手工从 Google Patents / 替代源补)

- **TMA 16 个 (2026-08-10 识别)**: P12-1, P13-1, P14-3, P23-22, P23-26, P23-3, P23-6, P24-1, P25-5, P25-6, P25-7, P28-2, P28-3, P30-3, P5-1, P8-2
- **2026-08-13/14 全量修正后剩余**: 仅 P13-1(待用户提供焦扬论文 DOI 10.3969/j.issn.1672-4992.2023.10.021)、P12-3(UpToDate 占位)、P31-6(2025 AANEM 摘要待提供); 其余 13 个已重下正确 PDF
- **雷管方案 1 个**: P40-10 (WO 专利不是期刊文章, 走 Google Patents PDF)

---

## 🚀 v3 FINAL 权威机制 (2026-08-13/14 定稿, 新交付唯一标准)

> 用户验收通过的全量交付基线(106 Pn-x 全量重做、1325/1325 像素验证、90 合并目录、8 列表、142 URL 验证)。
> **本仓库权威文件**:
> - 规范全文: `docs/HIGHLIGHT机制与算法规范_v3_FINAL.md`
> - 8 列标准 + 合并规则: `docs/8列标准与合并规则_2026-08-14.md`
> - 工具链: `scripts/hl_v3_final/`(hl_lib.py + render_fitz.py + rerun_all.py + pipeline 脚本 + 105 句子脚本示例)

### Step 4 Highlight — v3 FINAL rect 模式(取代 v10.1 line)

| 项 | 唯一权威值 | 旧值(废弃) |
|---|---|---|
| annot 类型 | `add_rect_annot`(PDF Square) | `add_highlight_annot`(扩展 ~3.7pt) / 内容流画线 |
| 颜色 | RGB(255, 217, 0) = (1.0, 0.85, 0.0) | RGB(255,230,100) |
| 透明度 | **0.45** | 0.8 压暗 / 细线 |
| 行级覆盖 | 每行一个 rect(行距法, 最小 8pt) | 大段色块 |
| 渲染 | fitz `get_pixmap()` 零补偿 | pdftoppm(偏移 ~8pt) / offset 参数 |
| 验证 | 直接迭代 `page.annots()` | `list(annots())`(假损坏误报) |

```bash
# 完整流程 (每个 Pn-x 一个句子脚本, 禁止复制其他 Pn-x)
python3 scripts/hl_v3_final/rerun_all.py          # 幂等重跑(先清旧 annots)
python3 scripts/hl_v3_final/render_fitz.py <hl.pdf> <pages_dir> 100
python3 scripts/hl_v3_final/copy_hl_images.py     # 根目录只留高亮页
/usr/bin/python3 scripts/hl_v3_final/test_hl_lib.py   # 25 passed
```

### 8 列标准表(本地+在线与雷管方案完全一致)

- 本地表: PN | 幻灯片 | 引用序号 | 引用 | PDF大小 | 已Highlight | MD5 | 页数
- 在线表(飞书): PPT页 | 第几条 | 引用语义（上下文） | PPT中的文献引用 完整字段 | DOI | 类型 | 对应PDF文件 | 来源链接 → 阅读全文(H 列卡片)
- 生成: `scripts/hl_v3_final/align_tables.py` → `scripts/hl_v3_final/leiguan_table.py --write`

### 同文献合并(取代旧 `Pn1-x1Pn2-x2`)

- 合并判定 = 引用文本指向同一文献(不能只看 MD5: 同一文献不同下载版本 MD5 不同仍要合并)
- 新目录名 = 成员按数字顺序下划线连接: `P3-1_P4-1`; TMA 106→90 目录(12 组合并, 28 个 Pn-x)


## 🔥 73. v3 FINAL + 9 条铁律 集成 (2026-08-20 用户硬规则)

完整集成 via54Medit ARCHITECTURE.md §23.2 的 9 条视觉铁律到 v3 FINAL rect 模式:

### 9 条铁律 (via54_highlight_v3_final.py 自动应用)

| # | 规则 | 检测方法 | 违规处理 |
|---|------|----------|----------|
| 1 | 视觉与 PPT 正文匹配 | 整句匹配 (不用关键词) | hl_lib locate_sentence |
| 2 | ❌ 禁止 highlight 作者 | AUTHOR_PATTERNS + [A-Z][a-z]+ | page.delete_annot |
| 3 | ❌ 禁止 highlight 文献标题 | 字号 >= 14pt + 上部 40% | page.delete_annot |
| 4 | ❌ 禁止 highlight 期刊名 | PUBLISHER_PATTERNS | page.delete_annot |
| 5 | ❌ 禁止 highlight Abstract 标题 | ABSTRACT_HEADERS | page.delete_annot |
| 6 | ❌ 禁止关键词匹配 | 用整句/短语 (50-200 字符) | hl_lib 强制 |
| 7 | ❌ 不能串行 | v3 FINAL rect 每行 1 rect | hl_lib sentence_rects |
| 8 | ❌ 不能遮盖文字 | rect 收窄 -0.6pt | hl_lib line 215-216 |
| 9 | ❌ 不能偏移 | 严格按 rawdict bbox | hl_lib 强制 |

### 新增脚本

| 脚本 | 路径 | 作用 |
|------|------|------|
| `via54_highlight_v3_final.py` | `scripts/` | v3 FINAL + 9 条铁律的通用 API |
| `rerun_tma_highlight_v3_final.py` | `scripts/` | TMA 专属 v3 FINAL 高亮 (替代 v10.4) |

### 用法

```python
from via54_highlight_v3_final import highlight_with_v3_final

# sentences = {page_idx_0based: [sentence, ...]}
result = highlight_with_v3_final(
    pdf_in="path/to/input.pdf",
    pdf_out="path/to/output.pdf",
    sentences=sentences_map,
    apply_9_rules=True,  # 自动删除违规 highlight
)
# result = {
#   "ok": True,
#   "total_sentences": 15,
#   "highlights_ok": 12,
#   "highlights_removed": 3,  # 9 条铁律删除的
#   "violations": [(page, rule, text), ...]
# }
```

### vs v10.4 改进

| 项 | v10.4 (line 模式) | v3 FINAL (rect 模式) + 9 铁律 |
|---|-------------------|-------------------------------|
| 样式 | 文字下方细黄线 | 整段半透明黄色 rect (opacity 0.45) |
| 匹配 | 关键词 (search_for) | 整句 (locate_sentence) |
| 行级覆盖 | 跨行延伸 | 每行 1 rect, 严格按行距 |
| 作者/标题 | 部分跳过 (前 2 行 + 上下 10%/8%) | 完全跳过 (字号 + 模式) |
| 9 条铁律 | 未集成 | 自动应用 + 删除违规 |
| 验证 | 25 passed | 25 passed + 9 铁律验证 |

### 验证 (TMA 案例)

- 6/6 PDF 全部高亮 ✅
- 11 个违规 highlight 被删除 (3 个标题, 8 个元数据区)
- 93 个合法 highlight 保留 (全部在 body content)


## 🔥 74. PPT视觉识别 → PDF应证 → v3 FINAL 高亮 完整流程 (2026-08-20 用户硬规则)

完全替代关键词匹配, 实现真正的**视觉驱动** highlight 流程:

### 之前的错误 (硬规则)

之前 `via54_highlight_fix_v10.py` 用关键词 `search_for()` 在 PDF 中匹配 (如 `'elevated lactate dehydrogenase'`)。
问题: 关键词匹配 = 简单 grep, 不对应 PPT 视觉内容, 导致:
  - 误命中 (单关键词多处出现)
  - 漏匹配 (关键词变了找不到)
  - 不应证 (没体现 PPT 视觉)

### 正确流程 (via54_ppt_visual_to_pdf.py)

```
Step 1: PPT 视觉理解 (sensenova vision API)
   - 用 vision API 渲染 PPT slide 为 png
   - 调用 sensenova-6.7-flash-lite 提取:
     * text_blocks (位置+类型)
     * citation_marks (标号+上下文+视觉位置)
     * data_points (数字/百分比/月份)

Step 2: PDF 语义级搜索 (不用关键词)
   - 整段匹配 (50-200 字符)
   - 提取医学术语 + 数据点 (避通用词)
   - 多 token 命中策略 (>=2 token 或 含数据点)

Step 3: v3 FINAL rect 高亮
   - 用 hl_lib.highlight_sentences (整句)
   - opacity 0.45 半透明黄色

Step 4: 9 条铁律自动应用
   - 删除标题/作者/期刊/Abstract 高亮
   - 只保留 body content 高亮
```

### 新增脚本

| 脚本 | 路径 | 作用 |
|------|------|------|
| `via54_ppt_visual_to_pdf.py` | `scripts/` | PPT视觉→PDF应证→高亮 完整流程 |

### vs 旧流程对比

| 项 | 旧 (`via54_highlight_fix_v10.py`) | 新 (`via54_ppt_visual_to_pdf.py`) |
|---|--------|---------|
| PPT 内容识别 | 关键词 (如 "T+A", "STRIDE") | vision API 视觉识别 |
| PDF 匹配 | search_for() 单词 | 整段 + 多 token 语义 |
| 标号定位 | 正则 (找 "中文词+数字") | vision 给出视觉位置 |
| 数据点 | 关键词 (如 "23.7") | vision 提取 (数字+类型) |
| 应证 | 字符串匹配 | 视觉+语义双层 |
| 9 铁律 | STRICT_SKIP_HEADER (部分) | 9 条完整 + 字号检测 |

### 用法

```bash
# 完整流程 (使用 vision API)
python3 via54_ppt_visual_to_pdf.py input.pptx input.pdf output.pdf

# 指定 slide
python3 via54_ppt_visual_to_pdf.py input.pptx input.pdf output.pdf --slide 5

# 不使用 vision API (fallback python-pptx)
python3 via54_ppt_visual_to_pdf.py input.pptx input.pdf output.pdf --no-vision
```

### Python API

```python
from via54_ppt_visual_to_pdf import highlight_from_visual

result = highlight_from_visual(
    pptx_path="presentation.pptx",
    pdf_in="input.pdf",
    pdf_out="output.pdf",
    slide_num=5,  # 或 None 处理所有 slide
    use_vision_api=True,
    apply_9_rules=True,
)
# result["highlights_ok"] = 实际高亮数
# result["highlights_removed"] = 9 铁律删除数
# result["violations"] = [(page, rule, text)]
```

### 验证 (TMA 案例)

- 6/6 PDF 全部用 PPT 视觉驱动高亮 ✅
- 104 个合法 highlight (整段匹配, 不是关键词)
- 69 个违规被 9 铁律删除 (DOI 链接 + 元数据区)
- 视觉位置正确 (top/center/bottom)
- 整段匹配, 不用 search_for()
