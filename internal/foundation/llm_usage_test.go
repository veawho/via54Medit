package foundation

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// 记账是本仓库最容易被"以为做了其实没做"的地方：usage 被解析出来后
// 一路丢了，报表里就是永久 0。所以这里做端到端断言 —— 真的发一次请求，
// 真的读回落盘文件，而不是只测内部函数。
func readSpool(t *testing.T, path string) []map[string]any {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("spool 未落盘: %v", err)
	}
	var out []map[string]any
	for _, ln := range strings.Split(strings.TrimSpace(string(raw)), "\n") {
		var rec map[string]any
		if err := json.Unmarshal([]byte(ln), &rec); err != nil {
			t.Fatalf("spool 行不是合法 JSON: %v (%s)", err, ln)
		}
		out = append(out, rec)
	}
	return out
}

func TestDeepSeekCallRecordsUsage(t *testing.T) {
	spool := filepath.Join(t.TempDir(), "spool.jsonl")
	t.Setenv(LLMUsageSpoolEnv, spool)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"id":"chatcmpl-ds-1","model":"deepseek-chat",` +
			`"choices":[{"message":{"content":"ok"}}],` +
			`"usage":{"prompt_tokens":120,"completion_tokens":30,"total_tokens":150}}`))
	}))
	defer srv.Close()

	p, err := newDeepSeek(map[string]any{"endpoint": srv.URL, "api_key": "k"})
	if err != nil {
		t.Fatal(err)
	}
	out, err := p.Complete(context.Background(), "", "hi")
	if err != nil {
		t.Fatal(err)
	}
	if out != "ok" {
		t.Fatalf("out = %q", out)
	}

	recs := readSpool(t, spool)
	if len(recs) != 1 {
		t.Fatalf("spool 记录数 = %d, want 1", len(recs))
	}
	r := recs[0]
	// provider 必须是 deepseek，而不是复用了实现的 hermes —— 否则账会串。
	if r["provider"] != "deepseek" {
		t.Errorf("provider = %v, want deepseek", r["provider"])
	}
	if r["model"] != "deepseek-chat" {
		t.Errorf("model = %v", r["model"])
	}
	if r["prompt_tokens"].(float64) != 120 || r["completion_tokens"].(float64) != 30 {
		t.Errorf("usage 未落盘: %v", r)
	}
	if r["total_tokens"].(float64) != 150 {
		t.Errorf("total = %v, want 150", r["total_tokens"])
	}
	if r["req_id"] != "chatcmpl-ds-1" {
		t.Errorf("req_id = %v (幂等去重依赖它)", r["req_id"])
	}
	if r["ts"] == "" || r["source"] == "" {
		t.Errorf("ts/source 不应为空: %v", r)
	}
}

func TestOpenAIProjectsUsageToOpenAINotHermes(t *testing.T) {
	spool := filepath.Join(t.TempDir(), "spool.jsonl")
	t.Setenv(LLMUsageSpoolEnv, spool)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"id":"chatcmpl-oa-1","model":"gpt-4o-mini",` +
			`"choices":[{"message":{"content":"ok"}}],` +
			`"usage":{"prompt_tokens":80,"completion_tokens":20}}`))
	}))
	defer srv.Close()

	p, err := newOpenAI(map[string]any{"endpoint": srv.URL, "api_key": "k"})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := p.Complete(context.Background(), "", "hi"); err != nil {
		t.Fatal(err)
	}
	recs := readSpool(t, spool)
	if len(recs) != 1 || recs[0]["provider"] != "openai" {
		t.Fatalf("provider = %v, want openai", recs)
	}
	// 服务商没给 total_tokens 时应自行补齐
	if recs[0]["total_tokens"].(float64) != 100 {
		t.Errorf("total = %v, want 100", recs[0]["total_tokens"])
	}
}

func TestGLMRecordsAsZhipu(t *testing.T) {
	spool := filepath.Join(t.TempDir(), "spool.jsonl")
	t.Setenv(LLMUsageSpoolEnv, spool)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"id":"glm-req-1","model":"glm-4.6v-flash",` +
			`"choices":[{"message":{"content":"好"}}],` +
			`"usage":{"prompt_tokens":300,"completion_tokens":40,"total_tokens":340}}`))
	}))
	defer srv.Close()

	p, err := NewLLM("glm", map[string]any{"endpoint": srv.URL, "api_key": "k"})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := p.Complete(context.Background(), "", "hi"); err != nil {
		t.Fatal(err)
	}
	recs := readSpool(t, spool)
	// Go 侧叫 glm，Python 侧叫 zhipu：落库必须统一，否则报表里会分成两家
	if len(recs) != 1 || recs[0]["provider"] != "zhipu" {
		t.Fatalf("provider = %v, want zhipu", recs)
	}
}

func TestNoUsageMeansNoSpoolLine(t *testing.T) {
	spool := filepath.Join(t.TempDir(), "spool.jsonl")
	t.Setenv(LLMUsageSpoolEnv, spool)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		// 服务商不返回 usage：宁可不记，也不能凭猜写一个假数字
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}]}`))
	}))
	defer srv.Close()

	p, err := newHermes(map[string]any{"endpoint": srv.URL})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := p.Complete(context.Background(), "", "hi"); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(spool); err == nil {
		t.Error("没有 usage 时不应产生 spool 记录")
	}
}

func TestExplicitSourceWins(t *testing.T) {
	spool := filepath.Join(t.TempDir(), "spool.jsonl")
	t.Setenv(LLMUsageSpoolEnv, spool)

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"ok"}}],` +
			`"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}`))
	}))
	defer srv.Close()

	p, err := newHermes(map[string]any{"endpoint": srv.URL})
	if err != nil {
		t.Fatal(err)
	}
	if _, err := p.CompleteWithOptions(context.Background(), CompleteOptions{
		User: "hi", Source: "docproc/entity",
	}); err != nil {
		t.Fatal(err)
	}
	recs := readSpool(t, spool)
	if len(recs) != 1 || recs[0]["source"] != "docproc/entity" {
		t.Fatalf("source = %v, want docproc/entity", recs)
	}
}
