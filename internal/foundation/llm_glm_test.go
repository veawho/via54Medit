package foundation

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestGLMProviderChatCompletions(t *testing.T) {
	var gotPath, gotAuth string
	var gotBody map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotAuth = r.Header.Get("Authorization")
		json.NewDecoder(r.Body).Decode(&gotBody)
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"choices":[{"message":{"content":"你好，策划助手"}}]}`))
	}))
	defer srv.Close()

	p, err := NewLLM("glm", map[string]any{
		"endpoint": srv.URL,
		"api_key":  "test-key",
		"model":    "glm-4-flash",
	})
	if err != nil {
		t.Fatal(err)
	}
	out, err := p.Complete(context.Background(), "系统提示", "用户消息")
	if err != nil {
		t.Fatal(err)
	}
	if out != "你好，策划助手" {
		t.Errorf("out = %q", out)
	}
	// BigModel path: no /v1 prefix.
	if gotPath != "/chat/completions" {
		t.Errorf("path = %s, want /chat/completions", gotPath)
	}
	if gotAuth != "Bearer test-key" {
		t.Errorf("auth = %q", gotAuth)
	}
	if gotBody["model"] != "glm-4-flash" {
		t.Errorf("model = %v", gotBody["model"])
	}
	msgs := gotBody["messages"].([]any)
	if len(msgs) != 2 {
		t.Errorf("messages = %v (system+user expected)", msgs)
	}
}

func TestGLMProviderEnvKey(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
	}))
	defer srv.Close()

	t.Setenv("GLM_API_KEY", "env-key")
	p, err := NewLLM("glm", map[string]any{"endpoint": srv.URL})
	if err != nil {
		t.Fatal(err)
	}
	if g := p.(*GLMProvider); g.apiKey != "env-key" {
		t.Errorf("apiKey = %q, want env-key", g.apiKey)
	}
	// ZHIPU_API_KEY fallback.
	t.Setenv("GLM_API_KEY", "")
	t.Setenv("ZHIPU_API_KEY", "zhipu-key")
	p2, err := NewLLM("glm", map[string]any{"endpoint": srv.URL})
	if err != nil {
		t.Fatal(err)
	}
	if g := p2.(*GLMProvider); g.apiKey != "zhipu-key" {
		t.Errorf("apiKey = %q, want zhipu-key", g.apiKey)
	}
}

func TestGLMProviderRequiresKey(t *testing.T) {
	t.Setenv("GLM_API_KEY", "")
	t.Setenv("ZHIPU_API_KEY", "")
	if _, err := NewLLM("glm", map[string]any{}); err == nil {
		t.Error("glm without key should error")
	}
}

func TestGLMProviderErrorStatus(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusUnauthorized)
		w.Write([]byte(`{"error":{"message":"bad key"}}`))
	}))
	defer srv.Close()
	p, err := NewLLM("glm", map[string]any{"endpoint": srv.URL, "api_key": "k"})
	if err != nil {
		t.Fatal(err)
	}
	_, err = p.Complete(context.Background(), "", "hi")
	if err == nil || !strings.Contains(err.Error(), "401") {
		t.Errorf("expected 401 error, got %v", err)
	}
}
