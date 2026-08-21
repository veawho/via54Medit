# TMA 文献整理 2026-08-10 完整审计报告

## 目录状态

```
TMA_文献整理/
├── _1_ppt/                          ❌ _2_expanded/ 空, _3_images/ 空
│   ├── _1_original/
│   ├── _2_expanded/                 ❌ 需要重建扩充尺寸PPT
│   └── _3_images/                   ❌ 需要重建导出图片
├── _2_pdfs/                         ❌ 空（PDF实际在 _pnx/）
├── _3_highlight/                    ❌ 空（highlight实际在 _pnx/*/）
├── _pnx/                            ✅ 111个目录，106个有highlight
├── _ppt_renders/                    ✅ 33张 slide_pp_NNN.jpg
└── TMA临床路径的诊断与鉴别.pptx     ✅ 原版PPT
```

## 飞书表最终状态（2026-08-10）

- **URL**: https://hackhealth.feishu.cn/sheets/P41bsK7t8hMJHntV936cggbxnve
- **Token**: P41bsK7t8hMJHntV936cggbxnve
- **行数**: 107行（含表头），数据106行
- **F列**: 106✅ / 106总

## 关键教训

### 1. CNKI 假文件识别（2026-08-10 实测）

P25-2/P30-2/P9-5 三个目录的 PDF 都是"高级检索"搜索页（3MB），不是目标论文。

**识别代码**：
```python
text = doc[0].get_text()
if '检索' in text or '想找什么' in text or 'Advanced Search' in text:
    # 假文件
```

**解决**：用户提供真实文件 `/Users/david/.hermes/cache/documents/doc_*/共识_2025版_...pdf` → 复制到 P25-2/P30-2/P9-5。

### 2. CHEST Cloudflare 阻断（2026-08-10 实测）

- browser_navigate → Cloudflare 安全验证
- curl → 同一页面
- cua-driver → 0 accessibility 元素

**结论**：订阅期刊无法自动绕过，必须用户手动下载。

**P11-2 和 P25-8 是同一篇 Azoulay 2017 Chest 论文**，只下载一次即可。

### 3. fitz ExtGState 错误

`fitz.open()` 对损坏 PDF 报 `ExtGState resource 'KSPE196'`。

**解决**：加 `garbage=4` 参数：
```python
doc = fitz.open(path, garbage=4)
```

### 4. UpToDate 占位 PDF

P12-3 是 UpToDate 订阅内容，无法获取全文。

**处理**：用 D 列内容生成 2KB 占位 PDF，verify.json 注明 `note: UpToDate subscription`。

## 剩余问题（2026-08-10）

| 问题 | 状态 | 说明 |
|------|------|------|
| `_1_ppt/_2_expanded/` | ❌ 待重建 | 扩充尺寸PPT |
| `_1_ppt/_3_images/` | ❌ 待重建 | 导出图片 |
| D列内容 | ⚠️ 暂定 | 需要逐页视觉核对PPT重新确认 |
| Step 5 三方对齐 | ❌ 未完成 | PPT ↔ 表格 ↔ PDF 三方验证 |
| Step 6 目录整合 | ❌ 未完成 | P23-24-P24-1 等合并目录待处理 |
