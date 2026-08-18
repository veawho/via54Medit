# TMA Highlight 工具链 — 复现指南(REPRODUCE)

> 本目录 `_highlight_toolkit/` 是**自包含**工具链,可独立复现全部 Pn-x 的 highlight。
> 详细规范见 `../HIGHLIGHT机制与算法规范_v3_FINAL.md`。

## 工具链文件

| 文件 | 作用 |
|---|---|
| `hl_lib.py` | 核心算法:canon 规范化 / locate_sentence / sentence_rects / highlight_sentences |
| `render_fitz.py` | fitz 渲染 PDF 全部页面为 PNG(100dpi,`page_NNN.png`) |
| `rerun_all.py` | 批量重跑全部句子脚本(优先 `scripts/`,回退 `/tmp`;逐个执行+渲染+失败收集) |
| `scripts/` | 105 个 Pn-x 的句子定义脚本(hl_p{Pn-x}.py,已沉淀) |
| `test_hl_lib.py` | 单元测试(25 用例,`python3 test_hl_lib.py` 应全部通过) |
| `copy_hl_images.py` | 把**有高亮的页面**图片复制到 Pn-x 根目录(命名 `{Pn-x}_highlight_pNNN.png`) |
| `vision_check.py` | 视觉验证统一入口(SenseNova → M3 → GLM 降级) |

## 复现步骤

```bash
TOOLKIT="/Users/david/Desktop/TMA_文献整理/_highlight_toolkit"
HL="/Users/david/Desktop/TMA_文献整理/step4_highlight_106目录_合并DOI"

# 1) 重跑全部 Pn-x(先清旧 annots 再生成, 逐个执行; 句子脚本在 scripts/)
python3 "$TOOLKIT/rerun_all.py"
#   —— 若批量后有个别 annots 报 "not bound to any page"(PyMuPDF list()假象或竞态):
#      再跑一遍 rerun_all.py; 验证时务必直接迭代 page.annots()

# 2) 渲染(rerun_all 已自动调用 render_fitz.py; 也可单独跑)
python3 "$TOOLKIT/render_fitz.py" "$HL/P23-8/P23-8_highlight.pdf" "$HL/P23-8/P23-8_highlight_pages" 100

# 3) 根目录图片(只复制高亮页)
python3 "$TOOLKIT/copy_hl_images.py"            # 全部
python3 "$TOOLKIT/copy_hl_images.py" P23-8      # 单个

# 4) 验证(像素: 每个 annot rect 内黄色 > 0; 页号一致)
python3 - <<'EOF'
import fitz, glob, os
from PIL import Image
import numpy as np
scale = 100/72.0
for d in ['P23-8']:
    doc = fitz.open(f'{d}/{d}_highlight.pdf')
    hl = sorted(pi+1 for pi in range(len(doc)) if len(list(doc[pi].annots() or [])) > 0)
    nok = sum(1 for pi in range(len(doc)) for a in doc[pi].annots()
              if ((np.array(Image.open(f'{d}/{d}_highlight_pages/page_{pi+1:03d}.png').convert('RGB'))
                   [int(a.rect.y0*scale):int(a.rect.y1*scale), int(a.rect.x0*scale):int(a.rect.x1*scale)][:,:,0]>180)
                  &(np.array(Image.open(f'{d}/{d}_highlight_pages/page_{pi+1:03d}.png').convert('RGB'))
                   [int(a.rect.y0*scale):int(a.rect.y1*scale), int(a.rect.x0*scale):int(a.rect.x1*scale)][:,:,1]>160)
                  &(np.array(Image.open(f'{d}/{d}_highlight_pages/page_{pi+1:03d}.png').convert('RGB'))
                   [int(a.rect.y0*scale):int(a.rect.y1*scale), int(a.rect.x0*scale):int(a.rect.x1*scale)][:,:,2]<170)).sum()>0)
    root = sorted(int(os.path.basename(f).rsplit('_p',1)[1][:3]) for f in glob.glob(f'{d}/{d}_highlight_p*.png'))
    print(d, 'hl_pages', hl, 'root_imgs', root, 'yellow_rects', nok)
EOF

# 5) 视觉抽查
python3 -c "
import sys; sys.path.insert(0, '$TOOLKIT')
from vision_check import vision
print(vision(['$HL/P23-8/P23-8_highlight_pages/page_002.png'],
             '高亮是否整句覆盖? 是否覆盖标题/作者/引用? 文字可读?'))
"
```

## 新 Pn-x 接入

1. 按对应 slide 的视觉内容选**整句**(禁止复制其他 Pn-x 的 highlight)
2. 写 `_highlight_toolkit/scripts/hl_p{Pn-x}.py`(模板见规范第五节; 页面重复文本时句子可用 `(text, occurrence)` 元组消歧)
3. `python3 rerun_all.py` 重跑全部(幂等,重复执行安全)
4. `copy_hl_images.py` 更新根目录图片
5. 视觉验证 + 更新 `{Pn-x}_verify.json`

## 环境要求

- Python 3.9+、PyMuPDF(fitz)、Pillow、numpy
- API 密钥(在 vision_check.py 顶部,SenseNova/M3/GLM)
- 目录:step3_pdf下载_106目录 / step4_highlight_106目录_合并DOI(路径硬编码在脚本内,迁移时全局替换)
