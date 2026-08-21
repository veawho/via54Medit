// GLM backend (智谱 BigModel OpenAI-compatible API).
//
// Registered as "glm". Endpoint defaults to the official
// https://open.bigmodel.cn/api/paas/v4 with model glm-4-flash (free
// tier); any OpenAI-compatible gateway works via cfg["endpoint"].
// API key resolution: cfg["api_key"] → $GLM_API_KEY → $ZHIPU_API_KEY.
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
	"time"
)

// GLMProvider calls a BigModel OpenAI-compatible /chat/completions.
type GLMProvider struct {
	endpoint string
	model    string
	apiKey   string
	client   *http.Client
}

func init() {
	RegisterLLM("glm", newGLM)
}

func newGLM(cfg map[string]any) (LLMProvider, error) {
	g := &GLMProvider{
		endpoint: "https://open.bigmodel.cn/api/paas/v4",
		model:    "glm-4-flash",
		client:   &http.Client{Timeout: 120 * time.Second},
	}
	if v, ok := cfg["endpoint"].(string); ok && v != "" {
		g.endpoint = v
	}
	if v, ok := cfg["model"].(string); ok && v != "" {
		g.model = v
	}
	if v, ok := cfg["api_key"].(string); ok && v != "" {
		g.apiKey = v
	}
	if g.apiKey == "" {
		g.apiKey = firstNonEmptyEnv("GLM_API_KEY", "ZHIPU_API_KEY")
	}
	if g.apiKey == "" {
		return nil, fmt.Errorf("llm: glm requires api_key in config or $GLM_API_KEY")
	}
	return g, nil
}

func firstNonEmptyEnv(names ...string) string {
	for _, n := range names {
		if v := strings.TrimSpace(os.Getenv(n)); v != "" {
			return v
		}
	}
	return ""
}

func (g *GLMProvider) Name() string { return "glm" }

func (g *GLMProvider) Complete(ctx context.Context, system, user string) (string, error) {
	return g.CompleteWithOptions(ctx, CompleteOptions{System: system, User: user})
}

func (g *GLMProvider) CompleteWithOptions(ctx context.Context, opts CompleteOptions) (string, error) {
	if opts.User == "" {
		return "", fmt.Errorf("llm: user message is required")
	}
	model := opts.Model
	if model == "" {
		model = g.model
	}
	messages := make([]map[string]string, 0, 2)
	if opts.System != "" {
		messages = append(messages, map[string]string{"role": "system", "content": opts.System})
	}
	messages = append(messages, map[string]string{"role": "user", "content": opts.User})

	reqBody := map[string]any{
		"model":    model,
		"messages": messages,
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

	// BigModel path is /api/paas/v4/chat/completions (no /v1 prefix),
	// so the endpoint default carries the base and we append directly.
	url := strings.TrimRight(g.endpoint, "/") + "/chat/completions"
	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewReader(body))
	if err != nil {
		return "", fmt.Errorf("llm: new request: %w", err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+g.apiKey)

	resp, err := g.client.Do(req)
	if err != nil {
		return "", fmt.Errorf("llm: do request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode/100 != 2 {
		raw, _ := io.ReadAll(resp.Body)
		return "", fmt.Errorf("llm: %s returned %d: %s", g.Name(), resp.StatusCode, truncate(string(raw), 200))
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
		return "", fmt.Errorf("llm: %s returned 0 choices", g.Name())
	}
	return got.Choices[0].Message.Content, nil
}
