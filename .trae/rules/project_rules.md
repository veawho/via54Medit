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
