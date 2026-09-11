# Trae / Traework Project Rules for via54Medit

## 1. Project Overview & Role
You are the EBM & Medical Literature AI Specialist operating within Trae (Traework).
`via54Medit` is a high-precision medical literature search, evidence extraction, citation alignment, and PDF annotation system for Evidence-Based Medicine (EBM).

- **Core Binary**: `bin/medit` (CLI) and `bin/medit-mcp` (Model Context Protocol stdio server).
- **Core Languages**: Go 1.22+ (CLI/MCP Server/Routers), Python 3.10+ (PDF/Vision/Annotation processing), Rust (High-perf PDF).
- **Supported Providers**: DeepSeek (V3/R1), Hermes Agent, MiniMax (M3), SenseNova, OpenAI/Codex.

---

## 2. Traework Execution SOP & Tool Calling

### A. Literature Search & Retrieval
1. **Via MCP Tool**: Call `medit_ask(query=...)` or `medit_hlo_ask(query=...)`.
2. **Via CLI**: Run `./bin/medit ask "<clinical question>"` or `go run ./cmd/medit ask "<query>"`.
3. Sources queried: PubMed (NCBI E-utilities), OpenAlex, Semantic Scholar (S2), Crossref, and ClinicalTrials.gov.

### B. Highlighting & Tri-Modal PDF Annotation (Zero-Touch Policy)
1. **Core Library**: Use `scripts/hl_v3_final/hl_lib.py`.
2. **Tri-Modal Annotation**:
   - `Highlight` (Rect yellow highlights for exact evidence sentences).
   - `Square` (Red context bounding boxes for tables/figures/paragraphs via `add_context_box`).
   - `FreeText` (Red index badges `A`, `B`, `C` mapping PPT/Word arguments via `add_freetext_badge`).
3. **Slide-Scoped Context Filtering**: Always use `filter_sentences_by_slide_context()` to prevent shared document annotation flooding.
4. **Hyphenation Resilience**: Handled automatically via `locate_sentence()`.

### C. Visual & Semantic Inspection
- Vision script: `python3 scripts/provider_vision.py <image_path> "<prompt>" [--json]`
- LLM reasoning: `python3 scripts/provider_llm.py "<prompt>" --model deepseek-reasoner`
- Supports `VISION_PROVIDER` (`mmx`, `sensenova`, `glm`) and `LLM_PROVIDER` (`deepseek`, `hermes`, `openai`, `codex`).

---

## 3. Strict Coding & Engineering Guardrails
1. **Never alter or overwrite target PDF files** unless explicitly instructed by the user.
2. **All Go packages must pass tests**: Always verify with `go test ./...`.
3. **All Python scripts must pass tests**: Verify with `python3 scripts/hl_v3_final/test_hl_lib.py`.
4. **Environment Fallbacks**:
   - Python: use `/Users/david/.hermes/hermes-agent/venv/bin/python3` or system `python3`.
   - Go: use standard Go 1.22+.
   - DeepSeek API: use `DEEPSEEK_API_KEY`.
5. **PPT 渲染保真: 版式与文字必须来自 Microsoft PowerPoint (2026-08-05 用户硬规则; 2026-09-11 澄清判定标准)**:
   - 用户原话 (2026-08-05): "powerpoint 渲染作为默认... 并默认必须用 PowerPoint 渲染"。
   - 用户澄清 (2026-09-11): "我是认为 PowerPoint 渲染出来的图片更符合原版, **如果有其他渲染图片并不会改变 PowerPoint 排版与文字的方式也可以集成**"。
   - 所以判定标准是**会不会重新排版**, 不是"是不是 PowerPoint 这个程序":
     - **不可替代**: PPTX→画面这一步 (版式/文字)。只允许 PowerPoint —— Windows COM / macOS 原生 AppleScript。
     - **可以换**: 把 PowerPoint 导出的**固定版式**产物 (PDF/EMF/位图) 再栅格化成图片这一步 —— PDF 只解释绘制指令、不重排, 所以不算换通道。栅格化器见 `RENDER_RASTERIZER` (`pymupdf` 默认 / `pdftoppm` 强制 `-cropbox`)。
     - **禁止**: 任何会重新排版的引擎 —— LibreOffice / Keynote / WPS / python-pptx / Aspose.Slides / Spire.Presentation / GroupDocs / Syncfusion。拿不到 PowerPoint 就**报错**, 不降级。
   - 首选 PowerPoint **直接出位图** (Windows `Slide.Export`), 因为还绕开"PDF 字体未内嵌 → 栅格化替换字形"的风险; 走 PDF 时会打印未内嵌字体的保真警告。
   - 实现位置: `scripts/hl_v3_final/ppt_to_pdf.py` (PPT→PDF, 技能包自包含) 与 `scripts/ppt_render_engine.py` (PPT→图片)。PPT→PDF/图片的入口都必须委托给它们。
   - 不变量由 `tests/test_repo_hygiene.py::TestRenderFidelity` 看守; 判定标准与各方案结论表见 `docs/ppt-render-fidelity.md`, 规则出处见 `skills/via54medit-algorithm-driven-upgrade-v2/references/v2.12.0-powerpoint-render-mandatory.md`。
