# PaddleOCR PDF 页解析脚本

## 位置
`/Users/david/Desktop/developments/via54Medit/scripts/paddleocr_pdf_page.py`

## 调用方式
```bash
python3.11 /path/to/paddleocr_pdf_page.py <pdf_path> <page_num>
```

## 输出
- stdout: 完整 JSON struct（ocr_blocks, rows, table_rows, all_text, bbox）
- stderr: 进度日志

## 依赖
- Python 3.11 (hermes-agent venv: `/Users/david/.hermes/hermes-agent/venv/bin/python3.11`)
- PaddleOCR 3.7.0
- PaddlePaddle 3.3.1
- PyMuPDF 1.28.0

## 已知问题
- 模型首次加载较慢（~10s 下载 4 个模型, ~180MB）
- 缓存路径: `/Users/david/.paddlex/official_models/`
- 输出坐标是 200 DPI 渲染图坐标, 不是 PDF 原生坐标, 需要缩放

## 通过 medit CLI 调用
```bash
medit anno2ppt ocr <pdf_path> <page_num>
```