// Embedder abstraction for via54Medit.
//
// Phase 1: hand-rolled HTTP clients for bge-m3 (via a sentence-transformers
// OpenAI-compatible server) and openai's text-embedding-3-small. Both
// expose the same /v1/embeddings shape, so the implementations share code.
//
// Phase 1.5: add sense-nova + a native onnxruntime-go bge-m3 client
// (no Python server needed). The interface stays the same.
//
// The Embed() contract returns L2-normalized vectors so cosine similarity
// reduces to a dot product — saves a sqrt per query in the router.
package foundation

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"
)

// Embedder turns text into dense vectors for semantic search.
type Embedder interface {
	// Name returns the embedder identifier (e.g., "bge-m3", "openai").
	Name() string

	// Dimension returns the fixed vector size. Callers use this to
	// configure the vector store collection on first run.
	Dimension() int

	// Embed returns L2-normalized vectors for the given inputs.
	// One vector per input, in the same order. Empty input list → empty result.
	Embed(ctx context.Context, inputs []string) ([][]float32, error)

	// Health checks the embedder is reachable. Used by the router's
	// pre-flight check.
	Health(ctx context.Context) error
}

// --- registry ---

type embedderFactory func(cfg map[string]any) (Embedder, error)

var (
	embedMu       sync.RWMutex
	embedRegistry = map[string]embedderFactory{}
)

func RegisterEmbedder(name string, factory embedderFactory) {
	embedMu.Lock()
	defer embedMu.Unlock()
	embedRegistry[name] = factory
}

func NewEmbedder(name string, cfg map[string]any) (Embedder, error) {
	embedMu.RLock()
	f, ok := embedRegistry[name]
	embedMu.RUnlock()
	if !ok {
		return nil, fmt.Errorf("embedder: unknown name %q (registered: %v)", name, registeredEmbedders())
	}
	return f(cfg)
}

func registeredEmbedders() []string {
	embedMu.RLock()
	defer embedMu.RUnlock()
	out := make([]string, 0, len(embedRegistry))
	for k := range embedRegistry {
		out = append(out, k)
	}
	return out
}

// --- bge-m3 backend (sentence-transformers OpenAI-compatible server) ---

// BGEm3Provider calls a sentence-transformers server that exposes
// /v1/embeddings (most llama.cpp / vllm / text-embeddings-inference
// servers do this out of the box).
//
// Default: localhost:8080, model "BAAI/bge-m3", dim 1024.
type BGEm3Provider struct {
	endpoint string
	model    string
	dim      int
	apiKey   string
	client   *http.Client
}

func init() {
	RegisterEmbedder("bge-m3", newBGEm3)
}

func newBGEm3(cfg map[string]any) (Embedder, error) {
	b := &BGEm3Provider{
		endpoint: "http://localhost:8080",
		model:    "BAAI/bge-m3",
		dim:      1024,
		client:   &http.Client{Timeout: 30 * time.Second},
	}
	if v, ok := cfg["endpoint"].(string); ok && v != "" {
		b.endpoint = v
	}
	if v, ok := cfg["model"].(string); ok && v != "" {
		b.model = v
	}
	if v, ok := cfg["model_path"].(string); ok && v != "" {
		// model_path is the on-disk path; server picks it up via env or arg.
		// We don't load it client-side.
		_ = v
	}
	if v, ok := cfg["api_key"].(string); ok {
		b.apiKey = v
	}
	return b, nil
}

func (b *BGEm3Provider) Name() string   { return "bge-m3" }
func (b *BGEm3Provider) Dimension() int { return b.dim }

func (b *BGEm3Provider) Health(ctx context.Context) error {
	req, err := http.NewRequestWithContext(ctx, "GET", b.endpoint+"/health", nil)
	if err != nil {
		return err
	}
	resp, err := b.client.Do(req)
	if err != nil {
		return fmt.Errorf("bge-m3: health check: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return fmt.Errorf("bge-m3: health check returned %d", resp.StatusCode)
	}
	return nil
}

func (b *BGEm3Provider) Embed(ctx context.Context, inputs []string) ([][]float32, error) {
	if len(inputs) == 0 {
		return [][]float32{}, nil
	}
	reqBody := map[string]any{
		"model": b.model,
		"input": inputs,
	}
	body, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("bge-m3: marshal: %w", err)
	}
	url := strings.TrimRight(b.endpoint, "/") + "/v1/embeddings"
	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("bge-m3: new request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	if b.apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+b.apiKey)
	}

	resp, err := b.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("bge-m3: do request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode/100 != 2 {
		raw, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("bge-m3: %d: %s", resp.StatusCode, truncate(string(raw), 200))
	}

	var got struct {
		Data []struct {
			Embedding []float32 `json:"embedding"`
			Index     int       `json:"index"`
		} `json:"data"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&got); err != nil {
		return nil, fmt.Errorf("bge-m3: decode: %w", err)
	}
	if len(got.Data) != len(inputs) {
		return nil, fmt.Errorf("bge-m3: got %d embeddings for %d inputs", len(got.Data), len(inputs))
	}

	// Reorder by index and L2-normalize.
	out := make([][]float32, len(inputs))
	for _, d := range got.Data {
		if d.Index < 0 || d.Index >= len(inputs) {
			return nil, fmt.Errorf("bge-m3: out-of-range index %d", d.Index)
		}
		out[d.Index] = l2normalize(d.Embedding)
	}
	return out, nil
}

// --- openai backend ---

type OpenAIEmbedder struct {
	endpoint string
	model    string
	dim      int
	apiKey   string
	client   *http.Client
}

func init() {
	RegisterEmbedder("openai", newOpenAIEmbedder)
}

func newOpenAIEmbedder(cfg map[string]any) (Embedder, error) {
	o := &OpenAIEmbedder{
		endpoint: "https://api.openai.com",
		model:    "text-embedding-3-small",
		dim:      1536,
		client:   &http.Client{Timeout: 30 * time.Second},
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
		return nil, fmt.Errorf("embedder: openai requires api_key")
	}
	return o, nil
}

func (o *OpenAIEmbedder) Name() string   { return "openai" }
func (o *OpenAIEmbedder) Dimension() int { return o.dim }

func (o *OpenAIEmbedder) Health(ctx context.Context) error {
	// OpenAI doesn't have a /health endpoint; we just check DNS via a
	// cheap embeddings call with empty input (which OpenAI rejects, but
	// a 4xx response means the server is up).
	req, err := http.NewRequestWithContext(ctx, "POST",
		strings.TrimRight(o.endpoint, "/")+"/v1/embeddings",
		bytes.NewReader([]byte(`{"model":"`+o.model+`","input":[]}`)))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+o.apiKey)
	resp, err := o.client.Do(req)
	if err != nil {
		return fmt.Errorf("openai: health check: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode == 401 {
		return fmt.Errorf("openai: invalid api_key")
	}
	if resp.StatusCode/100 == 5 {
		return fmt.Errorf("openai: server error %d", resp.StatusCode)
	}
	return nil
}

func (o *OpenAIEmbedder) Embed(ctx context.Context, inputs []string) ([][]float32, error) {
	// Identical wire format to bge-m3 — delegate to a BGEm3Provider
	// configured with OpenAI's endpoint.
	b := &BGEm3Provider{
		endpoint: o.endpoint,
		model:    o.model,
		dim:      o.dim,
		apiKey:   o.apiKey,
		client:   o.client,
	}
	return b.Embed(ctx, inputs)
}

// --- helpers ---

// l2normalize returns a unit-length copy of v.
// Vectors of all zeros stay as zeros (no NaN propagation).
func l2normalize(v []float32) []float32 {
	var sum float64
	for _, x := range v {
		sum += float64(x) * float64(x)
	}
	if sum == 0 {
		out := make([]float32, len(v))
		copy(out, v)
		return out
	}
	inv := 1.0 / sqrt(sum)
	out := make([]float32, len(v))
	for i, x := range v {
		out[i] = float32(float64(x) * inv)
	}
	return out
}

func sqrt(x float64) float64 {
	// Newton's method, 4 iterations is enough for float32 precision
	z := x / 2
	for i := 0; i < 8; i++ {
		z = (z + x/z) / 2
	}
	return z
}
