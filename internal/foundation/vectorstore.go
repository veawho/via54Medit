// Vector store abstraction for via54Medit.
//
// Phase 1: hand-rolled HTTP client for Qdrant (gRPC-free REST API) plus
// a tiny in-memory fallback for tests and small datasets (<10K docs).
// Phase 1.5: add meilisearch + sqlite-vec.
//
// The interface favors simplicity over completeness — Phase 2 router
// only needs Upsert + Search + Delete. Filter, payload index, snapshot
// etc. land in Phase 2 once the router asks for them.
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

// VectorStore holds dense vectors and supports nearest-neighbor search.
type VectorStore interface {
	// Name returns the store identifier (e.g., "qdrant", "in-memory").
	Name() string

	// Dimension returns the vector size the store expects.
	// Mismatched Dim() vs Embedder().Dimension() is a config bug.
	Dimension() int

	// Upsert inserts or replaces vectors. IDs are caller-provided strings.
	// Vectors must match Dimension() length.
	Upsert(ctx context.Context, items []VectorItem) error

	// Search returns the top-k most similar items to query.
	// Score is cosine similarity (1.0 = identical, 0 = orthogonal, -1 = opposite).
	// Phase 1 only: filter is ignored.
	Search(ctx context.Context, query []float32, k int) ([]ScoredItem, error)

	// Delete removes items by ID. Missing IDs are silently ignored.
	Delete(ctx context.Context, ids []string) error

	// Health checks the store is reachable.
	Health(ctx context.Context) error
}

// VectorItem is what Upsert consumes.
type VectorItem struct {
	ID      string         // caller-chosen stable ID (PMID, DOI, UUID, etc.)
	Vector  []float32      // must match Dimension()
	Payload map[string]any // arbitrary metadata: title, source, year, etc.
}

// ScoredItem is what Search returns.
type ScoredItem struct {
	ID      string
	Score   float32
	Payload map[string]any
}

// --- registry ---

type vsFactory func(cfg map[string]any) (VectorStore, error)

var (
	vsMu       sync.RWMutex
	vsRegistry = map[string]vsFactory{}
)

func RegisterVectorStore(name string, factory vsFactory) {
	vsMu.Lock()
	defer vsMu.Unlock()
	vsRegistry[name] = factory
}

func NewVectorStore(name string, cfg map[string]any) (VectorStore, error) {
	vsMu.RLock()
	f, ok := vsRegistry[name]
	vsMu.RUnlock()
	if !ok {
		return nil, fmt.Errorf("vectorstore: unknown name %q (registered: %v)", name, registeredVS())
	}
	return f(cfg)
}

func registeredVS() []string {
	vsMu.RLock()
	defer vsMu.RUnlock()
	out := make([]string, 0, len(vsRegistry))
	for k := range vsRegistry {
		out = append(out, k)
	}
	return out
}

// --- Qdrant backend (REST API) ---

// QdrantStore talks to a Qdrant instance via its HTTP REST API (no gRPC).
// Default: localhost:6333, collection "medlit".
//
// Phase 1 limitation: assumes collection already exists (created out-of-band
// by setup.sh). Phase 1.5 adds CreateCollection / DeleteCollection.
type QdrantStore struct {
	baseURL    string
	collection string
	dim        int
	apiKey     string
	client     *http.Client
}

func init() {
	RegisterVectorStore("qdrant", newQdrant)
}

func newQdrant(cfg map[string]any) (VectorStore, error) {
	q := &QdrantStore{
		baseURL:    "http://localhost:6333",
		collection: "medlit",
		dim:        1024,
		client:     &http.Client{Timeout: 30 * time.Second},
	}
	if v, ok := cfg["url"].(string); ok && v != "" {
		q.baseURL = v
	}
	if v, ok := cfg["collection"].(string); ok && v != "" {
		q.collection = v
	}
	if v, ok := cfg["vector_size"].(int); ok && v > 0 {
		q.dim = v
	}
	if v, ok := cfg["api_key"].(string); ok {
		q.apiKey = v
	}
	return q, nil
}

func (q *QdrantStore) Name() string   { return "qdrant" }
func (q *QdrantStore) Dimension() int { return q.dim }

func (q *QdrantStore) Health(ctx context.Context) error {
	req, err := http.NewRequestWithContext(ctx, "GET", q.baseURL+"/healthz", nil)
	if err != nil {
		return err
	}
	resp, err := q.client.Do(req)
	if err != nil {
		return fmt.Errorf("qdrant: health: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return fmt.Errorf("qdrant: health returned %d", resp.StatusCode)
	}
	return nil
}

func (q *QdrantStore) Upsert(ctx context.Context, items []VectorItem) error {
	if len(items) == 0 {
		return nil
	}
	// Validate dimensions.
	for _, it := range items {
		if len(it.Vector) != q.dim {
			return fmt.Errorf("qdrant: item %s has dim %d, expected %d", it.ID, len(it.Vector), q.dim)
		}
	}

	points := make([]map[string]any, len(items))
	for i, it := range items {
		points[i] = map[string]any{
			"id":      it.ID,
			"vector":  it.Vector,
			"payload": it.Payload,
		}
	}
	reqBody := map[string]any{"points": points}
	body, err := json.Marshal(reqBody)
	if err != nil {
		return fmt.Errorf("qdrant: marshal: %w", err)
	}

	url := q.baseURL + "/collections/" + q.collection + "/points?wait=true"
	req, err := http.NewRequestWithContext(ctx, "PUT", url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("qdrant: new request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	if q.apiKey != "" {
		req.Header.Set("Api-Key", q.apiKey)
	}

	resp, err := q.client.Do(req)
	if err != nil {
		return fmt.Errorf("qdrant: upsert: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		raw, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("qdrant: upsert %d: %s", resp.StatusCode, truncate(string(raw), 200))
	}
	return nil
}

func (q *QdrantStore) Search(ctx context.Context, query []float32, k int) ([]ScoredItem, error) {
	if len(query) != q.dim {
		return nil, fmt.Errorf("qdrant: query dim %d, expected %d", len(query), q.dim)
	}
	if k <= 0 {
		k = 10
	}
	reqBody := map[string]any{
		"vector":       query,
		"limit":        k,
		"with_payload": true,
	}
	body, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("qdrant: marshal: %w", err)
	}

	url := q.baseURL + "/collections/" + q.collection + "/points/search"
	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("qdrant: new request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	if q.apiKey != "" {
		req.Header.Set("Api-Key", q.apiKey)
	}

	resp, err := q.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("qdrant: search: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		raw, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("qdrant: search %d: %s", resp.StatusCode, truncate(string(raw), 200))
	}

	var got struct {
		Result []struct {
			ID      any            `json:"id"` // Qdrant returns id as string OR number
			Score   float32        `json:"score"`
			Payload map[string]any `json:"payload"`
		} `json:"result"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&got); err != nil {
		return nil, fmt.Errorf("qdrant: decode: %w", err)
	}

	out := make([]ScoredItem, len(got.Result))
	for i, r := range got.Result {
		switch v := r.ID.(type) {
		case string:
			out[i].ID = v
		case float64:
			out[i].ID = fmt.Sprintf("%d", int(v))
		}
		out[i].Score = r.Score
		out[i].Payload = r.Payload
	}
	return out, nil
}

func (q *QdrantStore) Delete(ctx context.Context, ids []string) error {
	if len(ids) == 0 {
		return nil
	}
	reqBody := map[string]any{
		"points": ids,
	}
	body, err := json.Marshal(reqBody)
	if err != nil {
		return fmt.Errorf("qdrant: marshal: %w", err)
	}

	url := q.baseURL + "/collections/" + q.collection + "/points/delete?wait=true"
	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("qdrant: new request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	if q.apiKey != "" {
		req.Header.Set("Api-Key", q.apiKey)
	}

	resp, err := q.client.Do(req)
	if err != nil {
		return fmt.Errorf("qdrant: delete: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		raw, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("qdrant: delete %d: %s", resp.StatusCode, truncate(string(raw), 200))
	}
	return nil
}

// --- in-memory backend (for tests + small datasets) ---

// MemoryStore is a brute-force cosine-similarity store. O(n) per query.
// Use for <10K docs, unit tests, and air-gapped environments where
// Qdrant isn't available.
type MemoryStore struct {
	mu   sync.RWMutex
	dim  int
	data map[string]VectorItem // id -> item
}

func init() {
	RegisterVectorStore("memory", newMemory)
}

func newMemory(cfg map[string]any) (VectorStore, error) {
	dim := 1024
	if v, ok := cfg["vector_size"].(int); ok && v > 0 {
		dim = v
	}
	return &MemoryStore{
		dim:  dim,
		data: make(map[string]VectorItem),
	}, nil
}

func (m *MemoryStore) Name() string   { return "memory" }
func (m *MemoryStore) Dimension() int { return m.dim }

func (m *MemoryStore) Health(ctx context.Context) error { return nil }

func (m *MemoryStore) Upsert(ctx context.Context, items []VectorItem) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, it := range items {
		if len(it.Vector) != m.dim {
			return fmt.Errorf("memory: item %s has dim %d, expected %d", it.ID, len(it.Vector), m.dim)
		}
		m.data[it.ID] = it
	}
	return nil
}

func (m *MemoryStore) Search(ctx context.Context, query []float32, k int) ([]ScoredItem, error) {
	if len(query) != m.dim {
		return nil, fmt.Errorf("memory: query dim %d, expected %d", len(query), m.dim)
	}
	if k <= 0 {
		k = 10
	}
	m.mu.RLock()
	defer m.mu.RUnlock()

	type scored struct {
		id    string
		score float32
		item  VectorItem
	}
	all := make([]scored, 0, len(m.data))
	for id, item := range m.data {
		all = append(all, scored{
			id:    id,
			score: cosineSimilarity(query, item.Vector),
			item:  item,
		})
	}
	// Partial sort: top-k via simple selection (n is small).
	if k > len(all) {
		k = len(all)
	}
	for i := 0; i < k; i++ {
		maxIdx := i
		for j := i + 1; j < len(all); j++ {
			if all[j].score > all[maxIdx].score {
				maxIdx = j
			}
		}
		all[i], all[maxIdx] = all[maxIdx], all[i]
	}

	out := make([]ScoredItem, k)
	for i := 0; i < k; i++ {
		out[i] = ScoredItem{
			ID:      all[i].id,
			Score:   all[i].score,
			Payload: all[i].item.Payload,
		}
	}
	return out, nil
}

func (m *MemoryStore) Delete(ctx context.Context, ids []string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	for _, id := range ids {
		delete(m.data, id)
	}
	return nil
}

// --- helpers ---

func cosineSimilarity(a, b []float32) float32 {
	if len(a) != len(b) {
		return 0
	}
	var dot, na, nb float64
	for i := range a {
		dot += float64(a[i]) * float64(b[i])
		na += float64(a[i]) * float64(a[i])
		nb += float64(b[i]) * float64(b[i])
	}
	if na == 0 || nb == 0 {
		return 0
	}
	return float32(dot / (sqrt(na) * sqrt(nb)))
}

// silence unused import in case strings ever becomes unused
var _ = strings.TrimRight
