# Copilot & Codex Instructions for via54Medit

## Project Scope
`via54Medit` is an evidence-based medicine literature engine and high-precision document annotation tool.

## Key Instructions
1. **Primary Interface**: Designed for Trae / Traework Agent, Hermes Agent, OpenClaw, Codex, and DeepSeek.
2. **Go Code**:
   - Follow standard Go idioms, wrap errors with context (`fmt.Errorf("...: %w", err)`).
   - Use `internal/foundation` for provider adapters (`hermes`, `openai`, `deepseek`).
   - Run `go test ./...` to verify all components.
3. **Python Scripts**:
   - Use `scripts/hl_v3_final/hl_lib.py` for all sentence locating, bounding rect generation, and tri-modal PDF annotations.
   - Use `scripts/provider_llm.py` and `scripts/provider_vision.py` for model provider abstraction.
   - Verify tests with `python3 scripts/hl_v3_final/test_hl_lib.py`.
