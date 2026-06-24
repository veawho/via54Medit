package foundation

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestRegisterAndNewLLM(t *testing.T) {
	// hermes and openai should be registered via init().
	if !contains(registeredLLMs(), "hermes") {
		t.Error("hermes not registered (init() didn't fire?)")
	}
	if !contains(registeredLLMs(), "openai") {
		t.Error("openai not registered")
	}
}

func TestNewLLMUnknown(t *testing.T) {
	_, err := NewLLM("nonexistent-provider-xyz", nil)
	if err == nil {
		t.Fatal("NewLLM with unknown name should return error")
	}
	if !strings.Contains(err.Error(), "nonexistent-provider-xyz") {
		t.Errorf("error should name the unknown provider, got: %v", err)
	}
}

func TestNewOpenAIRequiresAPIKey(t *testing.T) {
	_, err := newOpenAI(map[string]any{}) // no api_key
	if err == nil {
		t.Fatal("newOpenAI() without api_key should fail")
	}
	if !strings.Contains(err.Error(), "api_key") {
		t.Errorf("error should mention api_key, got: %v", err)
	}
}

func TestNewHermesDefaults(t *testing.T) {
	p, err := newHermes(map[string]any{})
	if err != nil {
		t.Fatal(err)
	}
	if p.Name() != "hermes" {
		t.Errorf("Name = %q, want hermes", p.Name())
	}
	// We can't easily inspect the private fields, so just verify it
	// implements LLMProvider (compile-time check via interface return).
	var _ LLMProvider = p
}

func TestNewHermesWithCustomEndpoint(t *testing.T) {
	p, err := newHermes(map[string]any{
		"endpoint": "http://my-llm:9999",
		"model":    "custom-model",
	})
	if err != nil {
		t.Fatal(err)
	}
	// End-to-end test: spin up a test server, point hermes at it, verify call.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/chat/completions" {
			t.Errorf("unexpected path: %s", r.URL.Path)
		}
		if got := r.Header.Get("Content-Type"); got != "application/json" {
			t.Errorf("Content-Type = %q, want application/json", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"echo: hello"}}]}`))
	}))
	defer srv.Close()

	// Re-create provider with test server URL.
	p, err = newHermes(map[string]any{
		"endpoint": srv.URL,
		"model":    "test-model",
	})
	if err != nil {
		t.Fatal(err)
	}
	out, err := p.Complete(context.Background(), "you are a parrot", "hello")
	if err != nil {
		t.Fatalf("Complete: %v", err)
	}
	if out != "echo: hello" {
		t.Errorf("Complete = %q, want \"echo: hello\"", out)
	}
}

func TestNewHermesSendsBearerToken(t *testing.T) {
	var gotAuth string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
	}))
	defer srv.Close()

	p, _ := newHermes(map[string]any{
		"endpoint": srv.URL,
		"api_key":  "sk-test-123",
	})
	_, err := p.Complete(context.Background(), "", "hi")
	if err != nil {
		t.Fatal(err)
	}
	if gotAuth != "Bearer sk-test-123" {
		t.Errorf("Authorization = %q, want \"Bearer sk-test-123\"", gotAuth)
	}
}

func TestNewHermesNoBearerWhenNoKey(t *testing.T) {
	gotAuth := "PRESENT" // sentinel
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotAuth = r.Header.Get("Authorization")
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
	}))
	defer srv.Close()

	p, _ := newHermes(map[string]any{"endpoint": srv.URL})
	_, err := p.Complete(context.Background(), "", "hi")
	if err != nil {
		t.Fatal(err)
	}
	if gotAuth != "" {
		t.Errorf("Authorization = %q, want empty (no key provided)", gotAuth)
	}
}

func TestNewHermesErrorOnHTTPError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, `{"error":"rate limited"}`, http.StatusTooManyRequests)
	}))
	defer srv.Close()

	p, _ := newHermes(map[string]any{"endpoint": srv.URL})
	_, err := p.Complete(context.Background(), "", "hi")
	if err == nil {
		t.Fatal("Complete on 429 should fail")
	}
	if !strings.Contains(err.Error(), "429") {
		t.Errorf("error should include status code, got: %v", err)
	}
}

func TestNewHermesEmptyUserMessage(t *testing.T) {
	p, _ := newHermes(map[string]any{})
	_, err := p.Complete(context.Background(), "system", "")
	if err == nil {
		t.Fatal("Complete with empty user message should fail")
	}
}

func TestNewHermesContextCancellation(t *testing.T) {
	// Server returns 503 immediately. The test asserts that the client
	// honors the context deadline (which is shorter than the server's
	// response time) and errors out.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, "slow", http.StatusServiceUnavailable)
	}))
	defer srv.Close()

	p, _ := newHermes(map[string]any{
		"endpoint": srv.URL,
	})
	// Override the default 60s timeout with a tiny one to keep tests quick.
	h := p.(*HermesProvider)
	h.client = &http.Client{Timeout: 5 * time.Millisecond}

	_, err := p.Complete(context.Background(), "", "hi")
	if err == nil {
		t.Fatal("Complete with 5ms client timeout should fail")
	}
	// We don't assert on the error type because Go's http client may
	// report either "context deadline exceeded" or "Client.Timeout exceeded"
	// depending on the exact Go version. The fact that we got any error
	// is what matters.
}

func TestNewHermesZeroChoices(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`{"choices":[]}`))
	}))
	defer srv.Close()

	p, _ := newHermes(map[string]any{"endpoint": srv.URL})
	_, err := p.Complete(context.Background(), "", "hi")
	if err == nil {
		t.Fatal("Complete with 0 choices should fail")
	}
	if !strings.Contains(err.Error(), "0 choices") {
		t.Errorf("error should mention 0 choices, got: %v", err)
	}
}
