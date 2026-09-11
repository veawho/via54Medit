# PPT 渲染保真度：判定标准与可选通道

> 目的：把"只用 PowerPoint 渲染"这条规则的**判定标准**写清楚，避免以后要么禁得过死、要么放得过松。
> 起因：2026-09-11 用户澄清了标准不是"某个可执行文件"，而是**保真度**。

---

## 1. 用户原话与判定标准

用户原话（2026-09-11）：

> "事实上，我是认为 PowerPoint 渲染出来的图片更符合原版，如果有其他渲染图片并不会改变 PowerPoint 排版与文字的方式也可以集成"

据此，规则的正确表述是：

| | 内容 |
| --- | --- |
| **版式与文字** | 必须由 **PowerPoint 自己的排版引擎**产出 —— 这是不可替代的一步 |
| **下游栅格化** | 把 PowerPoint 导出的**固定版式**产物（PDF / EMF / 位图）转成图片，**不算换通道** |
| **判定标准** | 看它**会不会重新排版**，而不是看它是什么程序 |

为什么这条线要划在"是否重新排版"上：PPTX 只是**描述性**格式（形状、字体名、字号、位置、继承关系），
把它变成画面必须有排版引擎；第三方实现各自实现一遍 OOXML 布局与字体匹配，必然在字体回退、断行、
autofit、SmartArt、图表、效果等处与原版分叉。而 PDF 是**固定版式**格式，栅格化器只解释绘制指令、
**不存在重排/回流机制**。

---

## 2. 各方案结论表

### 2.1 PPTX → 画面（**会重新排版，必须用 PowerPoint**）

| 方案 | 是否与 PowerPoint 一致 | 依据 |
| --- | --- | --- |
| **Microsoft PowerPoint**（Windows COM / macOS 原生 AppleScript） | ✅ 一致（它就是原版） | 桌面版真实排版引擎 |
| Microsoft PowerPoint for the web / **Microsoft Graph `?format=jpg`** | ✅ 微软自家引擎（服务端） | Graph 官方支持 pptx→jpg（须指定 width/height）与 pptx→pdf；免装桌面版，但需 OAuth + 网络 |
| LibreOffice / soffice | ❌ 不一致 | 官方社区实测：即使替代字体"度量相同"（Carlito ↔ Calibri），文字显示仍不同；中日文字体映射还会丢信息 |
| WPS Office | ❌ 不一致 | 自研排版引擎 + 私有字体映射；中文被强制替换后行高/版式漂移，厂商未承诺一致 |
| Apple Keynote | ❌ 不一致 | 用自己的排版引擎重新排布导入的 pptx，缺字体即替换 |
| Google Slides | ❌ 不一致 | 多方资料明确指出导入后 layout / fonts 会偏移 |
| python-pptx | ❌ **根本无法渲染** | 只读写 OOXML，不含排版引擎（"Slide Rendering & Export" 至今是未实现的 issue） |
| Aspose.Slides | ❌ 不一致 | **官方文档自述**：渲染精度相对 PowerPoint 会有差异，尤其是自定义或缺失字体时 |
| Spire.Presentation / GroupDocs / Syncfusion | ❌ 未证实（仅厂商宣称） | 自称 "pixel-perfect" / "high-fidelity"，但同页承认缺字体即出错，且无独立像素级对照证据 |

**2024–2026 也没有出现合格的"免装 PowerPoint 本地高保真"引擎。** 新项目（`pptx-viewer`、
`deck-ir`、`SlideGlance`、`pptx-wasm` 等）都自称高保真但**未提供与 PowerPoint 的逐像素对照证明**，
且都不是微软引擎 —— 按定义无法保证一致。

### 2.2 PowerPoint 产物 → 图片（**只光栅化，不重排，可以换**）

| 方案 | 是否改变版式/文字位置 | 备注 |
| --- | --- | --- |
| PowerPoint 直接出位图（COM `Slide.Export`） | ❌ 不改变 | **保真上限最高**，且绕开"字体未内嵌"风险 —— 能直出就别走 PDF |
| **PyMuPDF / fitz `get_pixmap()`** | ❌ 不改变 | 本仓库默认。按 CropBox 渲染，无偏移 |
| **pdftoppm（poppler）** | ❌ 不改变 | 参考文档原实现用的就是它。**必须加 `-cropbox`**，否则默认按 MediaBox 渲染会带出白边/偏移 |
| Ghostscript | ❌ 不重排，但**外观有已知缺陷** | 无内嵌字体时会用自带回退字体替代；曾有 SMask 污染图形状态、multiply 混合暗带等 bug |
| ImageMagick | ❌ 不重排，但继承 Ghostscript 的问题 | 其 PDF 读取实际委托 Ghostscript；且多数发行版默认在 `policy.xml` 里禁用 PDF |

> 注意：栅格化器之间**仍可能有肉眼可见差异**，来源是字体回退与透明/混合处理，而不是重排版。
> 所以本仓库固定用 PyMuPDF，并提供 pdftoppm 作为第二选择（强制 `-cropbox`）。

### 2.3 一个容易忽略的坑：字体是否内嵌

PowerPoint 导出 PDF 时若**没有内嵌字体**，栅格化器（poppler / MuPDF / Ghostscript）就会做**字体回退**，
字形因此改变 —— 那就是"改变了文字"。文字**位置与字距**来自 PDF 本身、不会漂移，但字形会变。

本仓库因此在 PowerPoint 导出 PDF 之后做一次检查：**发现未内嵌字体就打印保真警告**（见
`ppt_render_engine._non_embedded_fonts()`）。另外 PowerPoint 导出选项里的
"Bitmap text when fonts may not be embedded" 会把文字在**导出阶段**就位图化，导致放大后模糊 ——
这是导出环节的问题，栅格化器救不回来。

---

## 3. 本仓库的落地约定

| 环节 | 约定 |
| --- | --- |
| 版式来源 | **只允许 PowerPoint**：Windows COM `PowerPoint.Application`；macOS 原生 AppleScript |
| 首选出图方式 | PowerPoint 直接出位图（Windows `Slide.Export(PNG)`）> PowerPoint 导出 PDF → 固定版式栅格化（macOS） |
| 栅格化器 | `RENDER_RASTERIZER` = `pymupdf`（默认）/ `pdftoppm`（强制 `-cropbox`）；其它取值直接报错 |
| 禁止 | 任何**重新排版**的引擎：LibreOffice / soffice、Keynote、WPS、python-pptx、Aspose.Slides、Spire.Presentation、GroupDocs、Syncfusion |
| 不采用 | Ghostscript / ImageMagick（虽不重排，但有已知外观缺陷） |
| 未落地但合格 | Microsoft Graph `pptx→jpg`（微软自家引擎、免装桌面版；需 OAuth 与网络，等有需要再接） |
| 不变量 | `tests/test_repo_hygiene.py::TestRenderFidelity` 看守"禁止重排引擎"这条线 |

PowerPoint 不可用时**直接报错**，不降级 —— 因为降级就等于换一个排版引擎，正是要避免的事。

---

## 4. 来源

- LibreOffice 文字不一致实测（度量相同的替代字体仍不同）：<https://ask.libreoffice.org/t/powerpoint-compatibility-text-not-displayed-identically-even-when-substitute-fonts-have-same-metrics/55932>
- LibreOffice 中日文字体映射丢失：<https://ask.libreoffice.org/t/in-impress-chinese-fonts-convert-to-confusing-fonts-viewing-in-ms/84689>
- WPS / Impress / Slides 兼容性（明确 layout / fonts 会偏移）：<https://www.wps.ai/blog/best-ppt-alternative-for-businesses-2026/>
- PowerPoint vs Google Slides vs Keynote（2026 对比）：<https://presentersarena.com/tools/powerpoint-vs-google-slides-vs-keynote-the-ultimate-2026-showdown>
- python-pptx 渲染长期未实现：<https://github.com/MHoroszowski/python-pptx/issues/28>
- Aspose 官方文档（渲染精度可能与 PowerPoint 有差异）：<https://docs.aspose.com/slides/net/convert-powerpoint-to-jpg/>
- GroupDocs "pixel-perfect" 宣称与字体缺失报错同页：<https://tutorials.groupdocs.com/editor/java/presentation-documents/generate-svg-slide-previews-groupdocs-editor-java/>
- Syncfusion PowerPoint→Image 官方文档：<https://help.syncfusion.com/document-processing/powerpoint/conversions/powerpoint-to-image/overview>
- Microsoft Graph 格式转换（pptx→jpg / pptx→pdf）：<https://learn.microsoft.com/en-us/graph/api/driveitem-get-content-format>
- PowerPoint 导出分辨率与 DPI 上限：<https://learn.microsoft.com/en-us/office/troubleshoot/powerpoint/change-export-slide-resolution>
- pdftoppm(1) man page（默认 150 DPI、默认 MediaBox、`-cropbox`）：<https://manpages.debian.org/bookworm/poppler-utils/pdftoppm.1.en.html>
- PyMuPDF FAQ（`get_pixmap()` 渲染语义、CropBox 与 MediaBox）：<https://pymupdf.readthedocs.io/en/latest/faq/index.html>
- Ghostscript 使用文档（字体回退）：<https://ghostscript.readthedocs.io/en/gs10.01.1/Use.html>
- Ghostscript Bug 705284（SMask 污染图形状态）：<https://bugs.ghostscript.com/show_bug.cgi?id=705284>
- Ghostscript Bug 688601（multiply 混合暗带）：<https://bugs.ghostscript.com/show_bug.cgi?id=688601>
- ImageMagick 安全策略（PDF coder 默认禁用）：<https://imagemagick.org/security-policy/>
