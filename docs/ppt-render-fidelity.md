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
| Microsoft PowerPoint for the web / **Microsoft Graph `?format=` 转换** | ✅ 微软自家引擎（服务端）—— 但与**桌面版**有已知差异 | Graph 官方支持 pptx→jpg（须指定 width/height，且**只给第一页**）与 pptx→pdf（**整份**）；免装桌面版，但需 OAuth + 网络。已在 `RENDER_ENGINE=graph` 下接入，见 §3 |
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
| 版式来源 | **只允许微软自家引擎**，两个取值二选一（`RENDER_ENGINE`）：`powerpoint`（默认，桌面版）/ `graph`（Microsoft Graph 在线转换） |
| 首选出图方式 | PowerPoint 直接出位图（Windows `Slide.Export`）> PowerPoint/Graph 导出 PDF → 固定版式栅格化（macOS / 无桌面版时） |
| 栅格化器 | `RENDER_RASTERIZER` = `pymupdf`（默认）/ `pdftoppm`（强制 `-cropbox`）；其它取值直接报错 |
| 禁止 | 任何**重新排版**的引擎：LibreOffice / soffice、Keynote、WPS、python-pptx、Aspose.Slides、Spire.Presentation、GroupDocs、Syncfusion |
| 不采用 | Ghostscript / ImageMagick（虽不重排，但有已知外观缺陷） |
| **Word（DOC/DOCX）** | **同一条标准**：版式只由 **Microsoft Word** 产出（Windows COM / macOS 原生 AppleScript）。原先那两条会**改版式**的兜底已删除 —— LibreOffice headless 转 PDF、以及用 python-docx 抽段落拼"简易 PDF"。拿不到 Word 就直接失败 |
| 不变量 | `tests/test_repo_hygiene.py::TestRenderFidelity` 看守"禁止重排引擎"这条线（**豁免清单已为空**） |

选定的引擎拿不到时**直接报错**，**不自动切换**到另一个 —— 连"桌面版失败就自动切 Graph"也不行，
必须由使用者显式指定。（当年 darwin 上自动降级到 soffice 的教训。）
**Word 源文件同理**：没有 Word 就不渲染，不拿 LibreOffice 或 python-docx 拼一个"看起来像"的版本。

### 3.1 Microsoft Graph 通道（`RENDER_ENGINE=graph`）

实现：`scripts/hl_v3_final/graph_render.py`。流程：

```
本地 pptx --PUT--> OneDrive/SharePoint (_via54medit_render_tmp/)
         --GET .../content?format=pdf--> 302 → 预认证 URL → 下载整份 PDF
         --> 本地栅格化 (pymupdf/pdftoppm) --> slide_NNN.png
         --DELETE--> 清理临时上传 (GRAPH_KEEP_UPLOAD=1 可保留)
```

几个**踩过的坑 / 官方限制**（都已按此实现）：

| 事项 | 结论 |
| --- | --- |
| 为什么不用 `format=jpg` | 官方 API 页未说明，社区实测**只返回第一张幻灯片**；整份只有 `format=pdf` 走得通 |
| 必须先在云上 | 该 API 只作用于 `driveItem`，所以**必须先上传**本地文件 |
| 响应形态 | 是 **302 Found**（不是 202 异步）；**跟随 `Location` 时不能带 `Authorization`** |
| 权限 | 应用权限（app-only）最低 `Files.ReadWrite.All` 且需管理员同意；委派最低 `Files.Read` |
| 认证 | 客户端凭据：`login.microsoftonline.com/{tenant}/oauth2/v2.0/token`，`scope=https://graph.microsoft.com/.default`；也支持直接给现成令牌 |
| 个人版 OneDrive | 只支持委派；**app-only 需要工作/学校租户**（Entra） |
| 单次上传上限 | 250 MB，超过需 upload session（本模块未实现，会明确报错） |
| 保真度 | 走 **Office 在线**引擎，与桌面版有差异：字体替换、符号占位、部分对象行为。所以它是**显式选项**，桌面版可用时优先桌面版 |

自检：`python3 scripts/hl_v3_final/graph_render.py --check`（验证凭据 → 取令牌 → drive 可达）。

---

## 5. 可用性: "通道通" ≠ "能出图"

本机实测过一个很容易踩的坑:

| 探针 | 结果 |
| --- | --- |
| `launch` + `get version`（PowerPoint / Word） | ✓ 秒回（0.004s，能报出版本号） |
| 真的 `open` 一份 PPTX 再导出 PDF | ✗ AppleEvent **-1712**（超时），一张图都没有 |
| 真的 `open` 一份 DOCX 再导出 PDF | ✗ `save as` 报 **-1708**；更糟的是有时 **rc=0 却什么都不产出** |

所以**依赖探测给出的"就绪"是假 OK** —— 一条跑半小时的管线会在渲染那一步才炸。为此:

- `scripts/render_doctor.py` 默认做**真出图探针**: 现场造一份最小文档, 用**生产函数**真的渲染一遍,
  数产出的图片; 它在只查依赖时**明确拒绝**说"就绪"（`--quick` 的结语是"不能据此认为能渲染"）。
- 每个通道先**快速预检**（launch + get version）, 不通就**立刻**返回并给出可操作建议, 不去白等。
- 等待都有上界: `PPT_RENDER_TIMEOUT` / `WORD_RENDER_TIMEOUT`（默认 60s）、
  `PPT_RENDER_PREFLIGHT_TIMEOUT` / `WORD_RENDER_PREFLIGHT_TIMEOUT`（默认 20s）;
  子进程上界 = 配置值 + 15。
- 渲染产物**必须校验存在且非空** —— 桌面 Office 自动化确实存在"报成功但没产出"的行为。

**高可用在这里的含义**是: 早发现、快失败、原因准、建议可执行、**绝不产出错误结果**。
**不是**"总能渲染" —— 那需要换引擎, 而换引擎等于放弃保真, 正是本规则不允许的。

## 6. 来源

- LibreOffice 文字不一致实测（度量相同的替代字体仍不同）：<https://ask.libreoffice.org/t/powerpoint-compatibility-text-not-displayed-identically-even-when-substitute-fonts-have-same-metrics/55932>
- LibreOffice 中日文字体映射丢失：<https://ask.libreoffice.org/t/in-impress-chinese-fonts-convert-to-confusing-fonts-viewing-in-ms/84689>
- WPS / Impress / Slides 兼容性（明确 layout / fonts 会偏移）：<https://www.wps.ai/blog/best-ppt-alternative-for-businesses-2026/>
- PowerPoint vs Google Slides vs Keynote（2026 对比）：<https://presentersarena.com/tools/powerpoint-vs-google-slides-vs-keynote-the-ultimate-2026-showdown>
- python-pptx 渲染长期未实现：<https://github.com/MHoroszowski/python-pptx/issues/28>
- Aspose 官方文档（渲染精度可能与 PowerPoint 有差异）：<https://docs.aspose.com/slides/net/convert-powerpoint-to-jpg/>
- GroupDocs "pixel-perfect" 宣称与字体缺失报错同页：<https://tutorials.groupdocs.com/editor/java/presentation-documents/generate-svg-slide-previews-groupdocs-editor-java/>
- Syncfusion PowerPoint→Image 官方文档：<https://help.syncfusion.com/document-processing/powerpoint/conversions/powerpoint-to-image/overview>
- Microsoft Graph 格式转换（pptx→jpg / pptx→pdf；含权限表与 302 响应）：<https://learn.microsoft.com/en-us/graph/api/driveitem-get-content-format>
- Microsoft Graph 上传文件内容（`PUT .../content`，单次 250 MB 上限）：<https://learn.microsoft.com/en-us/graph/api/driveitem-put-content>
- Microsoft Graph 创建上传会话（>250 MB 时必须；分片须为 320 KiB 整数倍）：<https://learn.microsoft.com/en-us/graph/api/driveitem-createuploadsession>
- 客户端凭据流（app-only 取令牌形态与 `/.default` scope）：<https://learn.microsoft.com/en-us/graph/auth-v2-service>
- Web 版 PowerPoint 的功能行为差异（保真度差异的官方依据）：<https://support.microsoft.com/en-US/PowerPoint/how-certain-features-behave-in-web-based-powerpoint>
- pptx→jpg 只返回第一页（官方 API 页未记载，社区实测）：<https://learn.microsoft.com/en-au/answers/questions/2073843/conversion-of-pptx-to-jpg-via-graph-api-only-retur>
- PowerPoint 导出分辨率与 DPI 上限：<https://learn.microsoft.com/en-us/office/troubleshoot/powerpoint/change-export-slide-resolution>
- pdftoppm(1) man page（默认 150 DPI、默认 MediaBox、`-cropbox`）：<https://manpages.debian.org/bookworm/poppler-utils/pdftoppm.1.en.html>
- PyMuPDF FAQ（`get_pixmap()` 渲染语义、CropBox 与 MediaBox）：<https://pymupdf.readthedocs.io/en/latest/faq/index.html>
- Ghostscript 使用文档（字体回退）：<https://ghostscript.readthedocs.io/en/gs10.01.1/Use.html>
- Ghostscript Bug 705284（SMask 污染图形状态）：<https://bugs.ghostscript.com/show_bug.cgi?id=705284>
- Ghostscript Bug 688601（multiply 混合暗带）：<https://bugs.ghostscript.com/show_bug.cgi?id=688601>
- ImageMagick 安全策略（PDF coder 默认禁用）：<https://imagemagick.org/security-policy/>
