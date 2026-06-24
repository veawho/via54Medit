// Package foundation provides the core building blocks of via54Medit.
//
// All five foundation components (Log / Config / LLM / Embedder / VectorStore)
// live in this single package, following the same pattern:
//
//  1. An interface (Embedder / VectorStore / LLMProvider / Config / Logger)
//  2. A New(name string, ...) constructor that dispatches on name
//  3. A Register(name, factory) extension point for third-party backends
//
// The interfaces are designed to be similar to via54Design (so future swap
// is easy) but the implementations are hand-rolled in this package —
// see ARCHITECTURE 21 "独立运行原则" for the rationale.
//
// All public APIs accept a context.Context as their first argument and
// return errors with wrapped context (fmt.Errorf("...: %w", err)).
//
// Phase 1 milestone (2026-06-24): all 5 components compile + have unit
// tests. Real HTTP calls to bge-m3 / Qdrant / OpenAI land in Phase 1.5
// (foundation v0.2) once server URLs are stable.
package foundation
