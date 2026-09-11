// LLM token usage spool.
//
// 每次真实 LLM 调用都把服务商返回的 usage 追加到一行 JSONL；`medit-telemetry`
// 负责把这批记录**幂等地**摄入 telemetry.db 的 llm_token_logs 表。
//
// 为什么是落盘 spool，而不是 Go 直接写 SQLite：
//  1. Go 侧目前没有 SQLite 驱动，为一个记账功能引入 cgo/driver 会让构建显著变重；
//  2. LLM 调用可能来自 `medit ask` / `medplan` / docproc / medit-mcp 等多个进程，
//     并发写同一个 SQLite 文件反而更容易撞锁；
//  3. 落盘是 O_APPEND 追加，代价极低，且记账失败绝不会影响调用本身。
//
// 幂等性靠 req_id：服务商返回的 id 优先，没有就自造一个唯一值，摄入端按
// req_id 去重，所以"写了一半崩溃再重跑"不会重复计费。
package foundation

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"
)

// LLMUsageSpoolEnv 可覆盖 spool 落盘路径（测试用）。
const LLMUsageSpoolEnv = "VIA54_LLM_USAGE_SPOOL"

// usageInfo 只保留计费需要的三个字段。字段名与 telemetry 的列名保持一致，
// 免得摄入端再做一次名字映射。
type usageInfo struct {
	PromptTokens     int `json:"prompt_tokens"`
	CompletionTokens int `json:"completion_tokens"`
	TotalTokens      int `json:"total_tokens"`
}

var spoolMu sync.Mutex

// guessSource 在调用方没有显式给 Source 时，从调用栈推断调用源。
//
// 目的是让"这笔 token 是谁花的"可追溯（如 medplan/research.go），
// 而不是把所有 Go 侧调用都笼统记成 "go"。它**只是标签**：
// 推断不出来就退回 "go"，永远不会影响调用本身。
func guessSource() string {
	pcs := make([]uintptr, 24)
	n := runtime.Callers(2, pcs)
	if n == 0 {
		return "go"
	}
	frames := runtime.CallersFrames(pcs[:n])
	for {
		fr, more := frames.Next()
		fn := fr.Function
		// 跳过记账链路自身（都在 internal/foundation 里）与 runtime
		if !strings.Contains(fn, "/internal/foundation.") && !strings.HasPrefix(fn, "runtime.") {
			if i := strings.LastIndex(fn, "/"); i >= 0 {
				fn = fn[i+1:]
			}
			if fn != "" {
				return "go:" + fn
			}
		}
		if !more {
			break
		}
	}
	return "go"
}

// spoolPath 解析 spool 路径，默认 ~/.medit/llm_usage_spool.jsonl。
func spoolPath() string {
	if v := strings.TrimSpace(os.Getenv(LLMUsageSpoolEnv)); v != "" {
		return v
	}
	home, err := os.UserHomeDir()
	if err != nil || strings.TrimSpace(home) == "" {
		return ""
	}
	return filepath.Join(home, ".medit", "llm_usage_spool.jsonl")
}

// recordLLMUsage 追加一条用量记录。**永不返回错误** —— 记账是旁路，
// 绝不能因为它失败而让 LLM 调用本身失败。
func recordLLMUsage(provider, model, reqID, source, project string, u *usageInfo) {
	if u == nil {
		return
	}
	if u.TotalTokens <= 0 {
		u.TotalTokens = u.PromptTokens + u.CompletionTokens
	}
	if u.TotalTokens <= 0 && u.PromptTokens <= 0 && u.CompletionTokens <= 0 {
		// 服务商没返回 usage（或全 0）：宁可不记，也不要凭猜写一个假数字
		return
	}

	path := spoolPath()
	if path == "" {
		return
	}
	if strings.TrimSpace(provider) == "" {
		provider = "unknown"
	}
	if strings.TrimSpace(model) == "" {
		model = "unknown"
	}
	if strings.TrimSpace(source) == "" {
		source = guessSource()
	}
	if strings.TrimSpace(reqID) == "" {
		reqID = fmt.Sprintf("go-%s-%d", provider, time.Now().UnixNano())
	}

	line, err := json.Marshal(map[string]any{
		"ts":                time.Now().UTC().Format(time.RFC3339),
		"provider":          provider,
		"model":             model,
		"prompt_tokens":     u.PromptTokens,
		"completion_tokens": u.CompletionTokens,
		"total_tokens":      u.TotalTokens,
		"req_id":            reqID,
		"source":            source,
		"project_name":      project,
	})
	if err != nil {
		return
	}

	spoolMu.Lock()
	defer spoolMu.Unlock()
	if dir := filepath.Dir(path); dir != "" && dir != "." {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return
		}
	}
	f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644)
	if err != nil {
		return
	}
	defer f.Close()
	_, _ = f.Write(append(line, '\n'))
}

// llmResponseEnvelope 是所有 OpenAI 兼容响应里我们真正关心的部分：
// 正文 + 计费 usage + 服务商 request id。
type llmResponseEnvelope struct {
	ID      string `json:"id"`
	Model   string `json:"model"`
	Choices []struct {
		Message struct {
			Content string `json:"content"`
		} `json:"message"`
	} `json:"choices"`
	Usage *usageInfo `json:"usage"`
}

// content 返回第一条 choice 的正文（保持与原实现一致的行为）。
func (e *llmResponseEnvelope) content() string {
	if len(e.Choices) == 0 {
		return ""
	}
	return e.Choices[0].Message.Content
}
