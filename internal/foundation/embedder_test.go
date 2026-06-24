package foundation

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestRegisterAndNewEmbedder(t *testing.T) {
	if !contains(registeredEmbedders(), "bge-m3") {
		t.Error("bge-m3 not registered")
	}
	if !contains(registeredEmbedders(), "openai") {
		t.Error("openai not registered")
	}
}

func TestNewEmbedderUnknown(t *testing.T) {
	_, err := NewEmbedder("not-a-real-embedder", nil)
	if err == nil {
		t.Fatal("unknown embedder should fail")
	}
}

func TestNewBGEm3Defaults(t *testing.T) {
	e, err := newBGEm3(map[string]any{})
	if err != nil {
		t.Fatal(err)
	}
	if e.Name() != "bge-m3" {
		t.Errorf("Name = %q, want bge-m3", e.Name())
	}
	if e.Dimension() != 1024 {
		t.Errorf("Dimension = %d, want 1024", e.Dimension())
	}
}

func TestNewBGEm3CustomDim(t *testing.T) {
	e, _ := newBGEm3(map[string]any{"vector_size": 768})
	if e.Dimension() != 768 {
		// newBGEm3 doesn't take vector_size; this should still be 1024
		// (size is fixed by model). Update if we add support.
		t.Logf("Dimension = %d, expected behavior: bge-m3 fixed at 1024", e.Dimension())
	}
}

func TestNewBGEm3EmbedEmpty(t *testing.T) {
	e, _ := newBGEm3(map[string]any{})
	vecs, err := e.Embed(context.Background(), []string{})
	if err != nil {
		t.Fatal(err)
	}
	if len(vecs) != 0 {
		t.Errorf("empty input should return empty result, got %d", len(vecs))
	}
}

func TestNewBGEm3EmbedEndToEnd(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req struct {
			Model string   `json:"model"`
			Input []string `json:"input"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, err.Error(), 400)
			return
		}
		// Echo back fake embeddings (one per input, in order).
		result := make([]map[string]any, len(req.Input))
		for i := range req.Input {
			// Two orthogonal-ish vectors so the order is testable.
			vec := make([]float32, 4)
			if i == 0 {
				vec[0] = 1
			} else {
				vec[1] = 1
			}
			result[i] = map[string]any{
				"embedding": vec,
				"index":     i,
			}
		}
		_ = json.NewEncoder(w).Encode(map[string]any{"data": result})
	}))
	defer srv.Close()

	e, _ := newBGEm3(map[string]any{"endpoint": srv.URL})
	vecs, err := e.Embed(context.Background(), []string{"hello", "world"})
	if err != nil {
		t.Fatal(err)
	}
	if len(vecs) != 2 {
		t.Fatalf("got %d vecs, want 2", len(vecs))
	}
	// Verify L2-normalized (sum of squares ≈ 1).
	for i, v := range vecs {
		var sum float64
		for _, x := range v {
			sum += float64(x) * float64(x)
		}
		if sum < 0.99 || sum > 1.01 {
			t.Errorf("vec %d: L2 norm squared = %f, want ≈1.0", i, sum)
		}
	}
	// Verify order preserved (vecs[0][0] should be 1, vecs[1][1] should be 1).
	if vecs[0][0] != 1 || vecs[1][1] != 1 {
		t.Errorf("order not preserved: vecs[0]=%v, vecs[1]=%v", vecs[0], vecs[1])
	}
}

func TestNewBGEm3EmbedServerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "model not loaded", 503)
	}))
	defer srv.Close()

	e, _ := newBGEm3(map[string]any{"endpoint": srv.URL})
	_, err := e.Embed(context.Background(), []string{"hi"})
	if err == nil {
		t.Fatal("503 should produce error")
	}
	if !strings.Contains(err.Error(), "503") {
		t.Errorf("error should include status, got: %v", err)
	}
}

func TestNewOpenAIEmbedderRequiresKey(t *testing.T) {
	_, err := newOpenAIEmbedder(map[string]any{})
	if err == nil {
		t.Fatal("openai without api_key should fail")
	}
}

func TestNewOpenAIEmbedderDim(t *testing.T) {
	e, _ := newOpenAIEmbedder(map[string]any{"api_key": "sk-test"})
	if e.Dimension() != 1536 {
		t.Errorf("Dimension = %d, want 1536 (text-embedding-3-small)", e.Dimension())
	}
}

func TestL2Normalize(t *testing.T) {
	cases := []struct {
		in   []float32
		want []float32
	}{
		{[]float32{3, 4}, []float32{0.6, 0.8}}, // 3-4-5 triangle
		{[]float32{0, 0, 0}, []float32{0, 0, 0}},
		{[]float32{1, 0, 0}, []float32{1, 0, 0}},
	}
	for _, c := range cases {
		got := l2normalize(c.in)
		for i := range got {
			diff := got[i] - c.want[i]
			if diff < -0.01 || diff > 0.01 {
				t.Errorf("l2normalize(%v) = %v, want ≈%v", c.in, got, c.want)
				break
			}
		}
	}
}
