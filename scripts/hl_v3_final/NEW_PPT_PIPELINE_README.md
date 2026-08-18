# 新 PPT 处理流程(PIPELINE)

> 从「新 PPT」到「Pn-x highlight 交付」的完整可复现流程。
> 位置:_highlight_toolkit/pipeline/

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
  │  (后续) hl_lib + rerun_all.py  按 slide 选句高亮
  ▼
Pn-x 交付(雷管方案 5 要素)
```

## Step 1: 导出 PPT 图片

```bash
python3 step1_export_slides.py <ppt.pptx> <out_dir> [dpi=100]
# 输出: <out_dir>/<name>_expanded.pdf + <out_dir>/images/slide_pp_NNN.jpg
```
- 依赖:LibreOffice(soffice)→ PDF,PyMuPDF → 每页 JPG
- 测试:33 页 PPT 全部导出 ✓

## Step 2: 提取 Pn-x 文献引用字段

```bash
python3 step2_extract_refs.py <ppt.pptx> <refs.json>
# 输出: [{slide, num, text}] 与 _citation_table/tma_citation_table.json 同构
```
提取规则(经 106 条全量回归验证):
- 引用片段 = `N. 文本`,文本须含年份(19xx/20xx)或 `et al`/`等` 或中文≥10字(期刊/指南)
- 支持同行多引用(slide23 整行 1..26)、跨段落续行(`6.2. Zheng` 递归拆分)
- 同 (slide,num) 互相包含取最长;不同文本(如 slide31 的 Laurence/Jiang 编号重复)全部保留
- 与旧表对比:106/106 键全覆盖,15 完全一致 + 89 子串一致(旧表截断处新表更完整)

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
每步下载后校验:`%PDF` 魔数 + 页数>0 + 首页标题含引用特征

实测(2026-08-14):
- Frontiers(P20-1)/PLoS(P28-2)/中华期刊 OA 镜像:自动下载成功 ✓
- Wiley/Nature/MDPI(Cloudflare 深度封锁):自动失败,但**准确定位 DOI 与 OA 候选 URL**写入报告 `manual_download_candidates`,供浏览器人工下载

已知环境限制:无头环境无法绕过 Cloudflare(Wiley/Nature/MDPI 403),这是网络环境限制而非流程缺陷。

## 校验与报告

- 下载报告 `_download_report.json`:每条记录 source/pages/head/doi_err/manual_download_candidates
- 校验失败(下载到 HTML/0 页/标题不符)自动重试下一源,最终 FAILED 附人工候选

## 表同步(本地表 / 在线表)

```bash
python3 sync_table.py <refs.json> _citation_table/tma_citation_table.csv --feishu-out feishu_sync.csv
# 本地表: 引用列更新(取更长更完整), 保留 MD5/页数/Highlight 列
# 在线表: 生成 A_slide/B_mark/C_citation 格式 CSV 供回传飞书
```
- 对齐基线:雷管方案 106 个 Pn-x;P31-8/P31-9 不存在(已删除)
- 同键多值(如 slide31 的 Laurence/Jiang 编号重复):sync 保留首个,与 Pn-x 体系一致

## 后续衔接

- 下载的 PDF 放入 `step3_pdf下载_106目录/{Pn-x}_main.pdf`
- 按对应 slide 写句子脚本 `_highlight_toolkit/scripts/hl_p{Pn-x}.py`(禁止复制其他 Pn-x)
- `rerun_all.py` 重跑 → `copy_hl_images.py` 对齐根目录 → 视觉/像素验证
- 详见 `HIGHLIGHT机制与算法规范_v3_FINAL.md` 与 `REPRODUCE.md`
