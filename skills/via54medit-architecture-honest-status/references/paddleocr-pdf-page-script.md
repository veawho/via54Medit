# PaddleOCR PDF 页解析脚本

## 位置
`/Users/david/Desktop/developments/via54Medit/scripts/paddleocr_pdf_page.py`

## 调用方式
```bash
# 首选: 走 CLI —— 它会自动挑"装了 paddleocr 的那个解释器", 并锚定脚本位置
medit anno2ppt ocr <pdf_path> <page_num>

# 直接跑脚本也行, 但**必须**用装了 paddleocr 的解释器(见下方"解释器")
python3 /path/to/paddleocr_pdf_page.py <pdf_path> <page_num>
python3 /path/to/paddleocr_pdf_page.py --smoke     # 真识别自检(部署/复检)
```

## 输出
- stdout: 完整 JSON struct（ocr_blocks, rows, table_rows, all_text, bbox）
- stderr: 进度日志

## 依赖
- Python 3.10+，**且必须装了 paddleocr/paddle**（见下方说明）
- PaddleOCR 3.x（安装带约束 `paddleocr>=3.0,<4`；实测 3.7.0 可用）
- PaddlePaddle 3.x（实测 3.3.1）
- PyMuPDF

### 解释器（2026-09-12 更正，务必看）
**不要照名字挑解释器。** 本机实测：`~/.local/bin/python3.11` 有 pymupdf 却**没有**
paddleocr，而仓库用的 `python3` 两个都有 —— 旧文档让人用 `python3.11` 调用，命令必然
`ModuleNotFoundError`；同时部署报告用另一个解释器探测，仍显示"PaddleOCR 已就绪"。

正确做法：让 `medit anno2ppt ocr` 自己挑（它按"能不能 import"选），或显式指定：

```bash
export VIA54_OCR_PYTHON=/path/to/python   # 该解释器必须已装 paddleocr
```

判断某个解释器行不行：

```bash
<python> -c "import importlib.util as u; print([m for m in ('paddleocr','paddle','pymupdf') if u.find_spec(m) is None])"
```

## 已知问题
- 模型首次加载较慢（~10s 下载 4 个模型, ~180MB）
- 缓存路径: `/Users/david/.paddlex/official_models/`
- 输出坐标是 200 DPI 渲染图坐标, 不是 PDF 原生坐标, 需要缩放

## 通过 medit CLI 调用
```bash
medit anno2ppt ocr <pdf_path> <page_num>
```