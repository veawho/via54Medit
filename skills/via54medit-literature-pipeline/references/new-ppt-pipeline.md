# 新 PPT 处理流程(pipeline v1, 2026-08-14 测试通过)

> 从「新 PPT」到「Pn-x highlight 交付」完整可复现流程。
> 脚本: `scripts/step1_export_slides.py` / `step2_extract_refs.py` / `step3_download.py`(详细 README: `scripts/NEW_PPT_PIPELINE_README.md`)。

## 流程总览

```
新 PPT (.pptx)
  │  step1_export_slides.py   导出 PPT 图片
  ▼
全页 PDF + slide_pp_NNN.jpg
  │  step2_extract_refs.py    提取 Pn-x 文献引用字段
  ▼
[{slide, num, text}] 引用表
  │  step3_download.py        查找正确 PDF 链接并下载
  ▼
PDF + 下载报告(含人工候选)
  │  hl_p{Pn-x}.py + rerun_all.py  按 slide 选句高亮
  ▼
Pn-x 交付(雷管方案 5 要素)
```

## Step 1: 导出 PPT 图片

```bash
python3 step1_export_slides.py <ppt.pptx> <out_dir> [dpi=100]
# 输出: <out_dir>/<name>_expanded.pdf + <out_dir>/images/slide_pp_NNN.jpg
```
- 依赖: LibreOffice(soffice) → PDF, PyMuPDF → 每页 JPG
- 实测: 33 页 PPT 全部导出 ✓

## Step 2: 提取 Pn-x 文献引用字段

```bash
python3 step2_extract_refs.py <ppt.pptx> <refs.json>
# 输出: [{slide, num, text}]
```
提取规则(106 条全量回归验证):
- 引用片段 = `N. 文本`, 文本须含年份(19xx/20xx)或 `et al`/`等` 或中文 ≥10 字(期刊/指南)
- 支持同行多引用(slide23 整行 1..26)、跨段落续行(`6.2. Zheng` 递归拆分)
- 同 (slide,num) 互相包含取最长; 不同文本(如 slide31 的 Laurence/Jiang 编号重复)全部保留
- 回归: 106/106 键全覆盖, 15 完全一致 + 89 子串一致

## Step 3: 查找正确 PDF 链接并下载

```bash
python3 step3_download.py <refs.json> <out_dir> [--pn P23-8] [--limit N]
# 输出: <out_dir>/{Pn-x}.pdf + _download_report.json
```
下载链(逐级降级):
1. 引用文本直接 DOI → `https://doi.org/{doi}`(浏览器 UA)
2. CrossRef 定位 DOI(`query.bibliographic`)
3. OpenAlex / Unpaywall / Semantic Scholar 定位 OA PDF 直链
4. Europe PMC OA

每步下载后校验: `%PDF` 魔数 + 页数>0 + 首页标题含引用特征, 失败自动重试下一源。

实测(2026-08-14): Frontiers(P20-1)/PLoS(P28-2)/中华期刊 OA 镜像自动成功;
Wiley/Nature/MDPI(Cloudflare 深度封锁)自动失败但**准确定位 DOI 与 OA 候选 URL** 写入
`manual_download_candidates` 供浏览器人工下载 —— 这是网络环境限制而非流程缺陷。

## 下载后强制校验(历史教训)

- **下载后立即 title+authors 校验**(不要批量下完才查): P29-2/P23-24/P24-1/P28-1 曾全部错位
- DOI/PMID 不 100% 正确: 下载前 PubMed esummary 验证 title+authors 匹配
- CNKI 单页长 PDF 首页含"高级检索"导航是正常现象, 别误判为搜索页(37K 字符单页含全文可直接用)
- 订阅期刊(UpToDate/CHEST 等)Cloudflare+订阅墙无法自动绕过 → 用户手动下载, 占位必须标注

## 后续衔接

- 下载 PDF 放入 `step3_pdf下载_106目录/{Pn-x}_main.pdf`
- 按对应 slide 写句子脚本 `scripts/hl_pnx_examples/hl_p{Pn-x}.py`(**禁止复制其他 Pn-x 的句子**)
- `rerun_all.py` 重跑 → `copy_hl_images.py` 对齐根目录 → 像素/视觉验证
- 表同步: `sync_table.py` → `align_tables.py` → `leiguan_table.py --write`(见 leiguan-8col-table-standard.md)
