package client

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"regexp"
	"strings"
	"sync"
	"time"
)

// AntafuClient queries chat.antafu.com via its real API endpoint.
// Real API: POST https://medigw.alipay.com/medigw/aqpc/chat/streamChat
// Requires live browser session for jShield consultData payload.
// Set $ANTAFU_TOKEN_FILE to JSON: {Authorization, did-token, consultData}

const (
	AntafuBaseURL = "https://medigw.alipay.com/medigw/aqpc/chat/streamChat"
	AntafuReferer = "https://chat.antafu.com/"
)

// SessionTokens holds auth credentials extracted from a live browser.
type SessionTokens struct {
	Authorization string `json:"Authorization"`
	DidToken      string `json:"did-token"`
	ConsultData   string `json:"consultData"` // jShield consult payload
	AccessToken   string `json:"accessToken"`
}

// LoadSessionTokens reads tokens from a file.
func LoadSessionTokens(path string) (*SessionTokens, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read token file: %w", err)
	}
	var t SessionTokens
	if err := json.Unmarshal(b, &t); err != nil {
		return nil, fmt.Errorf("parse token file: %w", err)
	}
	return &t, nil
}

// StreamRequestBody is the body for the streamChat API call.
type StreamRequestBody struct {
	ChatId      string            `json:"chatId"`
	SessionId   string            `json:"sessionId"`
	ItemId      string            `json:"itemId"`
	QueryType   string            `json:"queryType"`
	QueryFrom   string            `json:"queryFrom"`
	Query       string            `json:"query"`
	ExtParams   map[string]string `json:"extParams"`
	Scene       string            `json:"scene"`
	ConsultData string            `json:"consultData"`
}

// ChatResponse is the parsed data field from an SSE chunk.
type ChatResponse struct {
	TraceId     string        `json:"traceId"`
	IsRobot     bool          `json:"isRobot"`
	Des         string        `json:"des"`
	Success     bool          `json:"success"`
	ContentList []ContentItem `json:"contentList"`
}

type ContentItem struct {
	TemplateData map[string]interface{} `json:"templateData"`
	TemplateId   string                 `json:"templateId"`
}

var idCounter int64
var idMu sync.Mutex

func newIDs(prefix string) (chatId, sessionId, itemId string) {
	idMu.Lock()
		idCounter++
		id := idCounter
		idMu.Unlock()
	return fmt.Sprintf("%s_%d", prefix, id),
		fmt.Sprintf("%s_%d", prefix, id+1),
		fmt.Sprintf("%s_%d_query", prefix, id)
}

// AntafuClient sends queries to the Antafu streamChat API.
// Requires a live browser session to provide valid consultData.
type AntafuClient struct {
	httpClient *http.Client
	tokens     *SessionTokens
	mu         sync.Mutex
}

// NewAntafuClient creates an Antafu client from session tokens.
// If tokens is nil, client is created in disabled state.
// TokenFile can be set via $ANTAFU_TOKEN_FILE env var.
func NewAntafuClient(tokens *SessionTokens) *AntafuClient {
	if tokens == nil {
		if p := os.Getenv("ANTAFU_TOKEN_FILE"); p != "" {
			t, err := LoadSessionTokens(p)
			if err != nil {
				fmt.Fprintf(os.Stderr, "[antafu] failed to load tokens: %v\n", err)
			} else {
				tokens = t
			}
		}
	}
	return &AntafuClient{
		httpClient: &http.Client{Timeout: 60 * time.Second},
		tokens:     tokens,
	}
}

// IsEnabled returns true if valid tokens are loaded.
func (c *AntafuClient) IsEnabled() bool {
	return c != nil && c.tokens != nil && c.tokens.Authorization != ""
}

// Query sends a text query to the Antafu API and returns response text.
// Returns "", err if no valid session or jShield captcha rejection.
func (c *AntafuClient) Query(ctx context.Context, query string) (string, error) {
	if !c.IsEnabled() {
		return "", fmt.Errorf("antafu client not enabled: set ANTAFU_TOKEN_FILE")
	}

	c.mu.Lock()
		defer c.mu.Unlock()

		chatId, sessionId, itemId := newIDs("chat")

		body := &StreamRequestBody{
			ChatId:      chatId,
			SessionId:   sessionId,
			ItemId:      itemId,
			QueryType:   "text_input",
			QueryFrom:   "edit_text",
			Query:       query,
			ExtParams: map[string]string{
				"pcSource":        "",
				"pcQuestionModel": "DeepSearch",
				"customChatMode":  "normal",
				"modeType":        "fastMode",
				"curAgentId":      "arec2_med_deep_search",
			},
			Scene:       "CONSULT",
			ConsultData: c.tokens.ConsultData,
		}

		js, err := json.Marshal(body)
		if err != nil {
			return "", fmt.Errorf("marshal: %w", err)
		}

		req, err := http.NewRequestWithContext(ctx, "POST", AntafuBaseURL,
			strings.NewReader(string(js)))
		if err != nil {
			return "", fmt.Errorf("request: %w", err)
		}
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Accept", "text/event-stream")
		req.Header.Set("Authorization", c.tokens.Authorization)
		req.Header.Set("did-token", c.tokens.DidToken)
		req.Header.Set("Referer", AntafuReferer)
		req.Header.Set("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36")

		resp, err := c.httpClient.Do(req)
		if err != nil {
			return "", fmt.Errorf("http: %w", err)
		}
		defer resp.Body.Close()

		if resp.StatusCode != 200 {
			return "", fmt.Errorf("HTTP %d", resp.StatusCode)
		}

		return c.parseSSE(resp.Body)
}

// parseSSE reads SSE chunks and returns concatenated text response.
// Detects captcha errors and extracts text from templateData.
func (c *AntafuClient) parseSSE(body io.ReadCloser) (string, error) {
	var parts []string
	scanner := bufio.NewScanner(body)
	scanner.Buffer(make([]byte, 0, 1024*1024), 10*1024*1024)

	for scanner.Scan() {
		line := scanner.Text()
		if strings.HasPrefix(line, "data:") {
			data := strings.TrimPrefix(line, "data:")
			var resp ChatResponse
			if err := json.Unmarshal([]byte(data), &resp); err != nil {
				continue
			}
			if strings.Contains(resp.Des, "系统错误") {
				for _, ci := range resp.ContentList {
					if strings.Contains(ci.TemplateId, "Captcha") {
						return "", fmt.Errorf("jShield captcha: consultData expired")
					}
				}
			}

			// Extract text from templateData
			for _, ci := range resp.ContentList {
				if text, ok := ci.TemplateData["text"]; ok {
					if s, ok2 := text.(string); ok2 && s != "" {
						parts = append(parts, s)
					}
				}
			}
		}
	}

	if len(parts) == 0 {
		return "", fmt.Errorf("no text content returned")
	}
	return strings.Join(parts, "\n"), nil
}

// ExtractCitations finds citation-like patterns in Antafu responses.
// Antafu returns natural language, so we extract DOI/PMID patterns.
func (c *AntafuClient) ExtractCitations(ctx context.Context, query string) ([]string, error) {
	text, err := c.Query(ctx, query)
	if err != nil {
		return nil, err
	}

	var citations []string
	pmidRe := regexp.MustCompile(`PMID\s*[:\-]?\s*(\d{6,9})`)
	doiRe := regexp.MustCompile(`(10\.\d{4,9}/\S+)`)

	for _, m := range pmidRe.FindAllStringSubmatch(text, -1) {
		citations = append(citations, "PMID:"+m[1])
	}
	for _, m := range doiRe.FindAllStringSubmatch(text, -1) {
		citations = append(citations, m[1])
	}

	return citations, nil
}