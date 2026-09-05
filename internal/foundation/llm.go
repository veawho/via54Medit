// LLM Provider abstraction for via54Medit.
//
// Phase 1: hand-rolled HTTP clients for hermes (the local MiniMax-M3
// gateway) and openai-compatible endpoints. Anthropic / Ollama land in
// Phase 1.5 once we have a real need — the interface is stable.
//
// All implementations honor context.Context for cancellation and timeout.
// Rate limits are NOT enforced at the LLM layer — that's the source
// adapter's job (each source has its own budget).
package foundation

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
)

// LLMProvider is the contract every backend (hermes / openai / anthropic / ollama) implements.
//
// All methods are safe for concurrent use. Providers are configured once
// at startup and shared across all goroutines.
type LLMProvider interface {
	// Name returns the provider identifier (e.g., "hermes", "openai").
	Name() string

	// Complete sends a chat-style prompt and returns the assistant's reply.
	//
	// system: optional system prompt ("" = none)
	// user: the actual user message
	// Returns the assistant's text response.
	Complete(ctx context.Context, system, user string) (string, error)

	// CompleteWithOptions is like Complete but with model parameters.
	// Use when callers need to override temperature / max_tokens / model.
	CompleteWithOptions(ctx context.Context, opts CompleteOptions) (string, error)
}

// CompleteOptions is the parameter struct for CompleteWithOptions.
type CompleteOptions struct {
	System      string  // system prompt ("" = none)
	User        string  // user message (required)
	Model       string  // model override ("" = use provider default)
	MaxTokens   int     // 0 = use provider default
	Temperature float64 // 0 = use provider default
	// Phase 1.5: TopP, StopSequences, ResponseFormat
}

// --- registry (plugin pattern) ---

type llmFactory func(cfg map[string]any) (LLMProvider, error)

var (
	llmMu       sync.RWMutex
	llmRegistry = map[string]llmFactory{}
)

// RegisterLLM registers a backend factory. Call from init() in a
// separate file (e.g., llm_anthropic.go) to add a new backend.
func RegisterLLM(name string, factory llmFactory) {
	llmMu.Lock()
	defer llmMu.Unlock()
	llmRegistry[name] = factory
}

// NewLLM dispatches by name. Returns error if name is unknown.
func NewLLM(name string, cfg map[string]any) (LLMProvider, error) {
	llmMu.RLock()
	f, ok := llmRegistry[name]
	llmMu.RUnlock()
	if !ok {
		return nil, fmt.Errorf("llm: unknown provider %q (registered: %v)", name, registeredLLMs())
	}
	return f(cfg)
}

func registeredLLMs() []string {
	llmMu.RLock()
	defer llmMu.RUnlock()
	out := make([]string, 0, len(llmRegistry))
	for k := range llmRegistry {
		out = append(out, k)
	}
	return out
}

// --- hermes backend (local MiniMax-M3 gateway) ---

// HermesProvider calls an OpenAI-compatible /v1/chat/completions endpoint.
// Hermes runs locally on :8642 by default but any OpenAI-compatible
// server (vLLM / ollama / llama.cpp) works.
type HermesProvider struct {
	endpoint string
	model    string
	apiKey   string
	client   *http.Client
}

func init() {
	RegisterLLM("hermes", newHermes)
}

func newHermes(cfg map[string]any) (LLMProvider, error) {
	h := &HermesProvider{
		endpoint: "http://localhost:8765",
		model:    "MiniMax-M3",
		client:   &http.Client{Timeout: 60 * time.Second},
	}
	if v, ok := cfg["endpoint"].(string); ok && v != "" {
		h.endpoint = v
	}
	if v, ok := cfg["model"].(string); ok && v != "" {
		h.model = v
	}
	if v, ok := cfg["api_key"].(string); ok {
		h.apiKey = v
	}
	return h, nil
}

func (h *HermesProvider) Name() string { return "hermes" }

func (h *HermesProvider) Complete(ctx context.Context, system, user string) (string, error) {
	return h.CompleteWithOptions(ctx, CompleteOptions{System: system, User: user})
}

func (h *HermesProvider) CompleteWithOptions(ctx context.Context, opts CompleteOptions) (string, error) {
	if opts.User == "" {
		return "", fmt.Errorf("llm: user message is required")
	}
	model := opts.Model
	if model == "" {
		model = h.model
	}
	// Build OpenAI-compatible request.
	reqBody := map[string]any{
		"model": model,
		"messages": []map[string]string{
			{"role": "system", "content": opts.System},
			{"role": "user", "content": opts.User},
		},
	}
	if opts.MaxTokens > 0 {
		reqBody["max_tokens"] = opts.MaxTokens
	}
	if opts.Temperature > 0 {
		reqBody["temperature"] = opts.Temperature
	}
	body, err := json.Marshal(reqBody)
	if err != nil {
		return "", fmt.Errorf("llm: marshal: %w", err)
	}

	url := strings.TrimRight(h.endpoint, "/") + "/v1/chat/completions"
	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(body))
	if err != nil {
		return "", fmt.Errorf("llm: new request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	if h.apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+h.apiKey)
	}

	resp, err := h.client.Do(req)
	if err != nil {
		return "", fmt.Errorf("llm: do request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode/100 != 2 {
		raw, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("llm: %s returned %d: %s", h.Name(), resp.StatusCode, truncate(string(raw), 200))
	}

	var got struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&got); err != nil {
		return "", fmt.Errorf("llm: decode response: %w", err)
	}
	if len(got.Choices) == 0 {
		return "", fmt.Errorf("llm: %s returned 0 choices", h.Name())
	}
	return got.Choices[0].Message.Content, nil
}

// --- openai backend (also OpenAI-compatible) ---

// OpenAIProvider is the same as Hermes but with openai.com endpoint default.
// Exists as a separate type so providers can have different defaults.
type OpenAIProvider struct {
	endpoint string
	model    string
	apiKey   string
	client   *http.Client
}

func init() {
	RegisterLLM("openai", newOpenAI)
}

func newOpenAI(cfg map[string]any) (LLMProvider, error) {
	o := &OpenAIProvider{
		endpoint: "https://api.openai.com",
		model:    "gpt-4o-mini",
		client:   &http.Client{Timeout: 60 * time.Second},
	}
	if v, ok := cfg["endpoint"].(string); ok && v != "" {
		o.endpoint = v
	}
	if v, ok := cfg["model"].(string); ok && v != "" {
		o.model = v
	}
	if v, ok := cfg["api_key"].(string); ok && v != "" {
		o.apiKey = v
	}
	if o.apiKey == "" {
		return nil, fmt.Errorf("llm: openai requires api_key in config")
	}
	return o, nil
}

func (o *OpenAIProvider) Name() string { return "openai" }

func (o *OpenAIProvider) Complete(ctx context.Context, system, user string) (string, error) {
	return o.CompleteWithOptions(ctx, CompleteOptions{System: system, User: user})
}

// --- deepseek backend (OpenAI-compatible DeepSeek V3 / R1) ---

type DeepSeekProvider struct {
	endpoint string
	model    string
	apiKey   string
	client   *http.Client
}

func init() {
	RegisterLLM("deepseek", newDeepSeek)
}

func newDeepSeek(cfg map[string]any) (LLMProvider, error) {
	d := &DeepSeekProvider{
		endpoint: "https://api.deepseek.com",
		model:    "deepseek-chat",
		client:   &http.Client{Timeout: 90 * time.Second},
	}
	if v, ok := cfg["endpoint"].(string); ok && v != "" {
		d.endpoint = v
	}
	if v, ok := cfg["model"].(string); ok && v != "" {
		d.model = v
	}
	if v, ok := cfg["api_key"].(string); ok && v != "" {
		d.apiKey = v
	}
	if d.apiKey == "" {
		// Fallback to environment variable
		d.apiKey = os.Getenv("DEEPSEEK_API_KEY")
	}
	return d, nil
}

func (d *DeepSeekProvider) Name() string { return "deepseek" }

func (d *DeepSeekProvider) Complete(ctx context.Context, system, user string) (string, error) {
	return d.CompleteWithOptions(ctx, CompleteOptions{System: system, User: user})
}

func (d *DeepSeekProvider) CompleteWithOptions(ctx context.Context, opts CompleteOptions) (string, error) {
	h := &HermesProvider{
		endpoint: d.endpoint,
		model:    d.model,
		apiKey:   d.apiKey,
		client:   d.client,
	}
	return h.CompleteWithOptions(ctx, opts)
}

func (o *OpenAIProvider) CompleteWithOptions(ctx context.Context, opts CompleteOptions) (string, error) {
	// Implementation is identical to Hermes — we just swap the endpoint/model.
	// To avoid duplication, build a HermesProvider with OpenAI's config.
	h := &HermesProvider{
		endpoint: o.endpoint,
		model:    o.model,
		apiKey:   o.apiKey,
		client:   o.client,
	}
	return h.CompleteWithOptions(ctx, opts)
}

// --- helpers ---

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}
