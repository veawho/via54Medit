package foundation

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestRegisterAndNewVectorStore(t *testing.T) {
	if !contains(registeredVS(), "qdrant") {
		t.Error("qdrant not registered")
	}
	if !contains(registeredVS(), "memory") {
		t.Error("memory not registered")
	}
}

func TestNewVectorStoreUnknown(t *testing.T) {
	_, err := NewVectorStore("redis", nil)
	if err == nil {
		t.Fatal("unknown vector store should fail")
	}
}

func TestNewQdrantDefaults(t *testing.T) {
	v, err := newQdrant(map[string]any{})
	if err != nil {
		t.Fatal(err)
	}
	if v.Name() != "qdrant" {
		t.Errorf("Name = %q, want qdrant", v.Name())
	}
	if v.Dimension() != 1024 {
		t.Errorf("Dimension = %d, want 1024", v.Dimension())
	}
}

// --- MemoryStore (the most testable) ---

func TestMemoryStoreRoundTrip(t *testing.T) {
	v, _ := newMemory(map[string]any{"vector_size": 3})
	ctx := context.Background()

	// Upsert 3 items, then search for one of them exactly.
	items := []VectorItem{
		{ID: "a", Vector: []float32{1, 0, 0}, Payload: map[string]any{"title": "first"}},
		{ID: "b", Vector: []float32{0, 1, 0}, Payload: map[string]any{"title": "second"}},
		{ID: "c", Vector: []float32{0, 0, 1}, Payload: map[string]any{"title": "third"}},
	}
	if err := v.Upsert(ctx, items); err != nil {
		t.Fatal(err)
	}

	// Query = (1,0,0) should rank "a" first with score 1.0.
	res, err := v.Search(ctx, []float32{1, 0, 0}, 2)
	if err != nil {
		t.Fatal(err)
	}
	if len(res) != 2 {
		t.Fatalf("got %d results, want 2", len(res))
	}
	if res[0].ID != "a" {
		t.Errorf("top-1 = %q, want a (exact match)", res[0].ID)
	}
	if res[0].Score < 0.99 {
		t.Errorf("top-1 score = %f, want ≈1.0", res[0].Score)
	}
	if res[0].Payload["title"] != "first" {
		t.Errorf("payload lost: %v", res[0].Payload)
	}
}

func TestMemoryStoreEmptySearch(t *testing.T) {
	v, _ := newMemory(map[string]any{"vector_size": 3})
	res, err := v.Search(context.Background(), []float32{1, 0, 0}, 5)
	if err != nil {
		t.Fatal(err)
	}
	if len(res) != 0 {
		t.Errorf("empty store should return 0 results, got %d", len(res))
	}
}

func TestMemoryStoreDimensionMismatch(t *testing.T) {
	v, _ := newMemory(map[string]any{"vector_size": 3})
	err := v.Upsert(context.Background(), []VectorItem{
		{ID: "a", Vector: []float32{1, 0}}, // wrong size
	})
	if err == nil {
		t.Fatal("Upsert with wrong dim should fail")
	}
}

func TestMemoryStoreSearchDimensionMismatch(t *testing.T) {
	v, _ := newMemory(map[string]any{"vector_size": 3})
	_, err := v.Search(context.Background(), []float32{1, 0}, 5)
	if err == nil {
		t.Fatal("Search with wrong dim should fail")
	}
}

func TestMemoryStoreDelete(t *testing.T) {
	v, _ := newMemory(map[string]any{"vector_size": 3})
	ctx := context.Background()
	_ = v.Upsert(ctx, []VectorItem{
		{ID: "a", Vector: []float32{1, 0, 0}},
		{ID: "b", Vector: []float32{0, 1, 0}},
	})
	if err := v.Delete(ctx, []string{"a"}); err != nil {
		t.Fatal(err)
	}
	res, _ := v.Search(ctx, []float32{1, 0, 0}, 10)
	for _, r := range res {
		if r.ID == "a" {
			t.Error("deleted item 'a' still searchable")
		}
	}
}

func TestMemoryStoreDeleteMissingIsOK(t *testing.T) {
	v, _ := newMemory(map[string]any{"vector_size": 3})
	// Deleting IDs that don't exist must not error.
	if err := v.Delete(context.Background(), []string{"nope", "nada"}); err != nil {
		t.Errorf("Delete missing IDs should be no-op, got: %v", err)
	}
}

func TestMemoryStoreConcurrentAccess(t *testing.T) {
	// Smoke test: concurrent Upsert + Search + Delete must not race.
	v, _ := newMemory(map[string]any{"vector_size": 3})
	ctx := context.Background()

	done := make(chan struct{})
	go func() {
		for i := 0; i < 50; i++ {
			_ = v.Upsert(ctx, []VectorItem{{ID: "x", Vector: []float32{1, 0, 0}}})
			_, _ = v.Search(ctx, []float32{1, 0, 0}, 5)
			_ = v.Delete(ctx, []string{"x"})
		}
		close(done)
	}()
	<-done
}

// --- QdrantStore end-to-end with httptest ---

func TestQdrantStoreHealth(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/healthz" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	}))
	defer srv.Close()

	v, _ := newQdrant(map[string]any{"url": srv.URL})
	if err := v.Health(context.Background()); err != nil {
		t.Fatal(err)
	}
}

func TestQdrantStoreHealthDown(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "down", 500)
	}))
	defer srv.Close()

	v, _ := newQdrant(map[string]any{"url": srv.URL})
	if err := v.Health(context.Background()); err == nil {
		t.Error("500 health should fail")
	}
}

func TestQdrantStoreUpsert(t *testing.T) {
	gotReq := map[string]any{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if err := json.NewDecoder(r.Body).Decode(&gotReq); err != nil {
			t.Fatal(err)
		}
		_, _ = w.Write([]byte(`{"result":{"status":"completed"}}`))
	}))
	defer srv.Close()

	v, _ := newQdrant(map[string]any{"url": srv.URL, "vector_size": 3})
	err := v.Upsert(context.Background(), []VectorItem{
		{ID: "abc", Vector: []float32{1, 0, 0}, Payload: map[string]any{"k": "v"}},
	})
	if err != nil {
		t.Fatal(err)
	}
	points, _ := gotReq["points"].([]any)
	if len(points) != 1 {
		t.Errorf("got %d points, want 1", len(points))
	}
}

func TestQdrantStoreSearch(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"result": []map[string]any{
				{"id": "doc-1", "score": 0.95, "payload": map[string]any{"title": "match"}},
				{"id": "doc-2", "score": 0.42, "payload": map[string]any{"title": "weak"}},
			},
		})
	}))
	defer srv.Close()

	v, _ := newQdrant(map[string]any{"url": srv.URL, "vector_size": 3})
	res, err := v.Search(context.Background(), []float32{1, 0, 0}, 2)
	if err != nil {
		t.Fatal(err)
	}
	if len(res) != 2 {
		t.Fatalf("got %d results, want 2", len(res))
	}
	if res[0].ID != "doc-1" || res[0].Score != 0.95 {
		t.Errorf("top-1 = %+v, want doc-1 score 0.95", res[0])
	}
	if res[0].Payload["title"] != "match" {
		t.Errorf("payload lost: %v", res[0].Payload)
	}
}

func TestQdrantStoreSearchNumericID(t *testing.T) {
	// Qdrant can return IDs as numbers; we must convert to string.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{
			"result": []map[string]any{
				{"id": 42, "score": 0.99, "payload": map[string]any{}},
			},
		})
	}))
	defer srv.Close()

	v, _ := newQdrant(map[string]any{"url": srv.URL, "vector_size": 3})
	res, err := v.Search(context.Background(), []float32{1, 0, 0}, 1)
	if err != nil {
		t.Fatal(err)
	}
	if res[0].ID != "42" {
		t.Errorf("numeric id conversion: got %q, want \"42\"", res[0].ID)
	}
}
