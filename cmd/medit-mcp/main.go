// Command medit-mcp is the via54Medit MCP Server entry point.
//
// It exposes 8 tools to MCP clients (Claude Desktop, Cursor, VS Code
// Copilot, etc.):
//
//   - medit_ask        : 一句话循证检索 (4 源并发 + LLM 摘要)
//   - medit_pico       : PICO 抽取 (Phase 3 实装, Phase 4.0 先做 placeholder)
//   - medit_grade      : GRADE 评级 (Phase 3 实装, Phase 4.0 先做 placeholder)
//   - medit_anno2ppt   : 证据包 → PPT (Phase 3 实装, Phase 4.0 先做 placeholder)
//
// HLO (Hermes Literature Orchestrator) 集成 (2026-07-28, Phase 5):
//   - medit_hlo_ask    : HLO NLU 入口 (1 句自然语言 = 1 次执行, 14 意图路由)
//   - medit_hlo_truth  : 160 Row 字段真值表查询 (medit_grade 升级数据源)
//   - medit_hlo_audit  : 32 Producer 白名单 PDF 真伪鉴定
//   - medit_hlo_corr   : NL 修正自升级 (corrections → MEMORY → skill patch)
//
// Transport: stdio (per MCP spec). The client (e.g. Claude Desktop)
// spawns `medit-mcp` as a subprocess and speaks JSON-RPC over stdin/stdout.
//
// Phase 4.0 milestones:
//
//	✅ stdio transport
//	✅ 4 tool registration
//	✅ medit_ask fully wired to the router
//	🔜 medit_pico / medit_grade / medit_anno2ppt (Phase 3.0 next)
//
// Phase 5.0 (HLO 集成):
//	✅ HLO Source adapter (hlo_orchestrator.go)
//	✅ 4 HLO MCP tools (medit_hlo_ask / medit_hlo_truth / medit_hlo_audit / medit_hlo_corr)
//	✅ 0 浏览器注册, 0 密钥, 0 成本 (复用 HLO 现有 SQLite + 4 源 API)
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"os/exec"
	"sort"
	"strings"
	"time"

	"github.com/modelcontextprotocol/go-sdk/mcp"

	"github.com/veawho/via54Medit/internal/foundation"
	"github.com/veawho/via54Medit/internal/router"
	"github.com/veawho/via54Medit/internal/source"
	"github.com/veawho/via54Medit/pkg/types"
)

const serverName = "via54Medit"
const serverVersion = "0.1.0-phase4"

func main() {
	// MCP server talks JSON-RPC over stdio. Anything we log goes to
	// stderr (per the MCP convention) so it doesn't pollute the wire.
	log.SetOutput(os.Stderr)
	log.SetPrefix("medit-mcp: ")

	ctx := context.Background()

	server := mcp.NewServer(&mcp.Implementation{
		Name:    serverName,
		Version: serverVersion,
	}, &mcp.ServerOptions{
		Instructions: "via54Medit MCP server — 4 tools for evidence-based medical literature retrieval. Use medit_ask for any clinical question; medit_pico / medit_grade / medit_anno2ppt are Phase 3 placeholders.",
	})

	// Register the 4 tools.
	mcp.AddTool(server, &mcp.Tool{
		Name:        "medit_ask",
		Description: "Run a clinical question through 4 literature sources (PubMed, OpenAlex, S2, antfu), fuse results, and optionally produce an LLM summary. Returns an EvidencePackage (JSON).",
	}, askTool)

	mcp.AddTool(server, &mcp.Tool{
		Name:        "medit_pico",
		Description: "Extract PICO (Population/Intervention/Comparator/Outcome) from a clinical question. Phase 3 placeholder — returns the question back with PICO=null.",
	}, picoTool)

	mcp.AddTool(server, &mcp.Tool{
		Name:        "medit_grade",
		Description: "Apply GRADE evidence rating to a citation package. Phase 3 placeholder — returns grade='B' (default) with reasoning='Phase 3 not yet implemented'.",
	}, gradeTool)

	mcp.AddTool(server, &mcp.Tool{
		Name:        "medit_anno2ppt",
		Description: "Render an evidence package as antfu-style PPT cards. Phase 3 placeholder — returns the path to a future PPTX file (does not exist yet).",
	}, anno2pptTool)

	// HLO 集成 (Phase 5, 2026-07-28)
	mcp.AddTool(server, &mcp.Tool{
		Name:        "medit_hlo_ask",
		Description: "HLO NLU-First 入口: 1 句自然语言 = 1 次执行, 14 意图路由 (process_row / search_papers / audit / cron_upgrade / normalize / daily_push / record_correction / eval_skills / refresh_truth / help / test / free_query). 调 Python hlo_nlu_v2.py, 0 浏览器注册, 0 密钥, 0 LLM 费用.",
	}, hloAskTool)

	mcp.AddTool(server, &mcp.Tool{
		Name:        "medit_hlo_truth",
		Description: "查询 HLO 字段真值表 (160 Row DOI + Author ground truth). 数据源 ~/.hermes/cache/lit_truth.json. 用于 medit_grade 升级 + CrossRef 二次验证.",
	}, hloTruthTool)

	mcp.AddTool(server, &mcp.Tool{
		Name:        "medit_hlo_audit",
		Description: "32 Producer 白名单 PDF 真伪鉴定: 调 hlo_nlu_v2.py '审计' → 179 PDF 分类 (真/假/未知). 用于 _downloads/ 验收.",
	}, hloAuditTool)

	mcp.AddTool(server, &mcp.Tool{
		Name:        "medit_hlo_corr",
		Description: "NL 修正自升级: 'P5-7 d Qin S 改成 Meyer T' → 存 SQLite + 写 MEMORY.md. 下次 cron_upgrade 自动 patch skill. 14+ 意图 NLU 路由.",
	}, hloCorrTool)

	// Run with stdio transport; logs go to stderr to keep stdout clean.
	t := &mcp.LoggingTransport{Transport: &mcp.StdioTransport{}, Writer: os.Stderr}
	if err := server.Run(ctx, t); err != nil {
		log.Printf("Server failed: %v", err)
		os.Exit(1)
	}
}

// --- Tool 1: medit_ask ---

type AskInput struct {
	Query      string `json:"query" jsonschema:"the clinical question to ask"`
	MaxResults int    `json:"max_results,omitempty" jsonschema:"max citations per source (default 20)"`
	NoAntfu    bool   `json:"no_antfu,omitempty" jsonschema:"skip antfu (default false)"`
	NoLLM      bool   `json:"no_llm,omitempty" jsonschema:"skip LLM summary (default false)"`
	LLMKey     string `json:"llm_api_key,omitempty" jsonschema:"OpenAI API key (only for openai provider)"`
}

type AskOutput struct {
	ConvID      string           `json:"conv_id"`
	Question    string           `json:"question"`
	Summary     string           `json:"summary"`
	Citations   []types.Citation `json:"citations"`
	Duration    string           `json:"duration"`
	SourcesUsed map[string]int   `json:"sources_used"`
}

func askTool(ctx context.Context, _ *mcp.CallToolRequest, input AskInput) (*mcp.CallToolResult, AskOutput, error) {
	if input.Query == "" {
		return nil, AskOutput{}, fmt.Errorf("query is required")
	}
	max := input.MaxResults
	if max <= 0 {
		max = 20
	}
	r := router.NewRouter()
	r.Concurrency = 4
	r.TimeoutPerSource = 30 * time.Second
	r.MaxRetries = 1

	for _, name := range []string{"pubmed", "openalex", "s2"} {
		s, err := defaultSource(name)
		if err != nil {
			log.Printf("source %s init: %v", name, err)
			continue
		}
		r.AddSource(s)
	}
	if !input.NoAntfu {
		s, err := source.NewAntfuSource(map[string]any{
			"cdp_url": "http://localhost:9223",
			"timeout": "60s",
		})
		if err == nil {
			r.AddSource(s)
		} else {
			log.Printf("antfu init: %v", err)
		}
	}
	if !input.NoLLM {
		// Try hermes (local), fall back to no-LLM.
		llm, err := foundation.NewLLM("hermes", map[string]any{
			"endpoint": "http://localhost:8765",
			"model":    "MiniMax-M3",
		})
		if err == nil {
			r.LLM = llm
		}
	}

	ep, err := r.Ask(ctx, types.EBMQuestion{
		Query:      input.Query,
		Intent:     types.IntentSearch,
		MaxResults: max,
	})
	if err != nil {
		return nil, AskOutput{}, fmt.Errorf("ask: %w", err)
	}

	out := AskOutput{
		ConvID:      ep.ConvID,
		Question:    ep.Question.Query,
		Summary:     ep.Summary,
		Citations:   ep.Citations,
		Duration:    ep.Duration.String(),
		SourcesUsed: ep.SourcesUsed,
	}
	// Also include a human-readable text version of the summary.
	textSummary := ep.Summary
	if textSummary == "" {
		textSummary = "(no summary)"
	}
	return &mcp.CallToolResult{
		Content: []mcp.Content{&mcp.TextContent{Text: textSummary}},
	}, out, nil
}

func defaultSource(name string) (source.SourceAdapter, error) {
	switch name {
	case "pubmed":
		return source.NewPubMedSource(nil)
	case "openalex":
		return source.NewOpenAlexSource(nil)
	case "s2":
		return source.NewS2Source(nil)
	}
	return nil, fmt.Errorf("unknown source: %s", name)
}

// --- Tool 2: medit_pico (Phase 3 placeholder) ---

type PicoInput struct {
	Query string `json:"query" jsonschema:"natural language clinical question"`
}

type PicoOutput struct {
	Query string      `json:"query"`
	PICO  *types.PICO `json:"pico"`
	Note  string      `json:"note"`
}

func picoTool(_ context.Context, _ *mcp.CallToolRequest, input PicoInput) (*mcp.CallToolResult, PicoOutput, error) {
	if input.Query == "" {
		return nil, PicoOutput{}, fmt.Errorf("query is required")
	}
	out := PicoOutput{
		Query: input.Query,
		PICO:  nil, // Phase 3 will use LLM to populate
		Note:  "Phase 3 placeholder: PICO extraction is not yet implemented. The query is echoed back unchanged.",
	}
	raw, _ := json.Marshal(out)
	return &mcp.CallToolResult{
		Content: []mcp.Content{&mcp.TextContent{Text: string(raw)}},
	}, out, nil
}

// --- Tool 3: medit_grade (Phase 3 placeholder) ---

type GradeInput struct {
	EvidencePackageJSON string `json:"evidence_package" jsonschema:"JSON-serialized EvidencePackage"`
}

type GradeOutput struct {
	GRADE       string `json:"grade"`
	GRADEReason string `json:"grade_reasoning"`
	Note        string `json:"note"`
}

func gradeTool(_ context.Context, _ *mcp.CallToolRequest, input GradeInput) (*mcp.CallToolResult, GradeOutput, error) {
	if input.EvidencePackageJSON == "" {
		return nil, GradeOutput{}, fmt.Errorf("evidence_package is required")
	}
	out := GradeOutput{
		GRADE:       "B",
		GRADEReason: "Phase 3 placeholder — simplified GRADE not yet implemented. Returning B as a sensible default.",
		Note:        "Once Phase 3 lands, this will use: score = n_citations + multi_source + RCT_ratio + recency.",
	}
	raw, _ := json.Marshal(out)
	return &mcp.CallToolResult{
		Content: []mcp.Content{&mcp.TextContent{Text: string(raw)}},
	}, out, nil
}

// --- Tool 4: medit_anno2ppt (Phase 3 placeholder) ---

type Anno2PPTInput struct {
	EvidencePackageJSON string `json:"evidence_package" jsonschema:"JSON-serialized EvidencePackage"`
	OutputDir           string `json:"output_dir,omitempty" jsonschema:"where to write the PPTX (default cwd)"`
}

type Anno2PPTOutput struct {
	OutputPath string `json:"output_path"`
	Note       string `json:"note"`
}

func anno2pptTool(_ context.Context, _ *mcp.CallToolRequest, input Anno2PPTInput) (*mcp.CallToolResult, Anno2PPTOutput, error) {
	if input.EvidencePackageJSON == "" {
		return nil, Anno2PPTOutput{}, fmt.Errorf("evidence_package is required")
	}
	dir := input.OutputDir
	if dir == "" {
		dir = "."
	}
	out := Anno2PPTOutput{
		OutputPath: dir + "/medit-evidence.pptx",
		Note:       "Phase 3 placeholder — PPTX not yet rendered. Path returned for future use.",
	}
	raw, _ := json.Marshal(out)
	return &mcp.CallToolResult{
		Content: []mcp.Content{&mcp.TextContent{Text: string(raw)}},
	}, out, nil
}

// =============================================================================
// HLO 集成 (Phase 5, 2026-07-28) - 4 个 HLO MCP 工具
// =============================================================================
//
// 设计原则:
//   - 0 浏览器注册 (无 Langfuse / 无 Dashboard)
//   - 0 密钥 (4 源 API 0 key + CrossRef polite pool + OpenAlex mailto)
//   - 0 LLM 费用 (CrossRef + OpenAlex 替代 Claude 验证)
//   - 0 记忆 (1 句 NL = 1 次执行, 14 意图路由)
//   - 复用 HLO 现有 14KB SQLite + 4 源 API 缓存 + 飞书 8 section
//
// 用法示例 (Claude Desktop / Cursor / Copilot):
//   User: "处理 P5-7"        → medit_hlo_ask(query="处理 P5-7")
//   User: "Qin S 2025 HCC"   → medit_hlo_ask(query="找 Qin S 2025 HCC")
//   User: "P5-7 d 改成 Meyer"  → medit_hlo_corr(row="5-7", field="d", ...)
//
// HLO Python 路径: /Users/david/Desktop/HLO_design/hlo_nlu_v2.py
// =============================================================================

// hloRunPython 执行 hlo_nlu_v2.py 并返回 stdout
func hloRunPython(args ...string) (string, error) {
	cmd := exec.Command("python3.11", append([]string{"/Users/david/Desktop/HLO_design/hlo_nlu_v2.py"}, args...)...)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return "", fmt.Errorf("hlo exec: %w (stderr: %s)", err, stderr.String())
	}
	return stdout.String(), nil
}

// --- HLO Tool 1: medit_hlo_ask (NLU 入口) ---

type HloAskInput struct {
	Query string `json:"query" jsonschema:"natural language query (e.g. '处理 P5-7', '找 Qin S 2025 HCC', '审计')"`
}

type HloAskOutput struct {
	Intent     string `json:"intent"`
	DurationMs int    `json:"duration_ms"`
	Output     string `json:"output"`
	Source     string `json:"source"`
}

func hloAskTool(_ context.Context, _ *mcp.CallToolRequest, input HloAskInput) (*mcp.CallToolResult, HloAskOutput, error) {
	if input.Query == "" {
		return nil, HloAskOutput{}, fmt.Errorf("query is required")
	}
	out, err := hloRunPython(input.Query)
	if err != nil {
		return nil, HloAskOutput{}, err
	}

	// 解析 HLO 输出 (提取意图和耗时)
	intent := "unknown"
	duration := 0
	for _, line := range strings.Split(out, "\n") {
		if strings.HasPrefix(line, "🎯") {
			intent = strings.TrimSpace(strings.TrimPrefix(line, "🎯 意图:"))
		}
		if strings.HasPrefix(line, "⏱️") {
			fmt.Sscanf(strings.TrimSpace(strings.TrimPrefix(line, "⏱️  耗时:")), "%dms", &duration)
		}
	}

	result := HloAskOutput{
		Intent:     intent,
		DurationMs: duration,
		Output:     out,
		Source:     "hlo_nlu_v2.py",
	}
	raw, _ := json.Marshal(result)
	return &mcp.CallToolResult{
		Content: []mcp.Content{&mcp.TextContent{Text: string(raw)}},
	}, result, nil
}

// --- HLO Tool 2: medit_hlo_truth (160 Row 字段真值表) ---

type HloTruthInput struct {
	RowPref string `json:"row_pref,omitempty" jsonschema:"Row 编号 e.g. P5-7 (空=查全部 160 Row)"`
}

type HloTruthOutput struct {
	Count     int            `json:"count"`
	RowPref   string         `json:"row_pref,omitempty"`
	Truth     map[string]any `json:"truth,omitempty"`
	AllKeys   []string       `json:"all_keys,omitempty"`
	Source    string         `json:"source"`
}

func hloTruthTool(_ context.Context, _ *mcp.CallToolRequest, input HloTruthInput) (*mcp.CallToolResult, HloTruthOutput, error) {
	// 调 hlo_nlu_v2.py 刷新
	_, err := hloRunPython("刷新 truth")
	if err != nil {
		return nil, HloTruthOutput{}, err
	}
	// 读真值表
	truthPath := os.Getenv("HOME") + "/.hermes/cache/lit_truth.json"
	data, err := os.ReadFile(truthPath)
	if err != nil {
		return nil, HloTruthOutput{}, fmt.Errorf("read truth: %w", err)
	}
	var all map[string]map[string]any
	if err := json.Unmarshal(data, &all); err != nil {
		return nil, HloTruthOutput{}, fmt.Errorf("parse truth: %w", err)
	}

	result := HloTruthOutput{
		Count:  len(all),
		Source: truthPath,
	}
	if input.RowPref != "" {
		key := input.RowPref
		if !strings.HasPrefix(key, "P") {
			key = "P" + key
		}
		result.RowPref = key
		result.Truth = all[key]
	} else {
		// 返回所有 key
		for k := range all {
			result.AllKeys = append(result.AllKeys, k)
		}
		sort.Strings(result.AllKeys)
	}
	raw, _ := json.Marshal(result)
	return &mcp.CallToolResult{
		Content: []mcp.Content{&mcp.TextContent{Text: string(raw)}},
	}, result, nil
}

// --- HLO Tool 3: medit_hlo_audit (32 Producer 白名单审计) ---

type HloAuditInput struct {
	// 空 = 全表审计 (179 PDF)
	Directory string `json:"directory,omitempty" jsonschema:"PDF 目录 (默认 ~/Desktop/雷管方案_文献整理/_downloads)"`
}

type HloAuditOutput struct {
	Real   int      `json:"real"`
	Fake   int      `json:"fake"`
	Unknown int     `json:"unknown"`
	FakeList []string `json:"fake_list,omitempty"`
	Output  string  `json:"output"`
	Source  string  `json:"source"`
}

func hloAuditTool(_ context.Context, _ *mcp.CallToolRequest, input HloAuditInput) (*mcp.CallToolResult, HloAuditOutput, error) {
	out, err := hloRunPython("审计")
	if err != nil {
		return nil, HloAuditOutput{}, err
	}

	// 解析输出
	result := HloAuditOutput{Output: out, Source: "hlo_nlu_v2.py audit"}
	for _, line := range strings.Split(out, "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "✅ 真 PDF:") {
			fmt.Sscanf(strings.TrimPrefix(line, "✅ 真 PDF:"), "%d", &result.Real)
		} else if strings.HasPrefix(line, "❌ 假 (Chrome printToPDF):") {
			fmt.Sscanf(strings.TrimPrefix(line, "❌ 假 (Chrome printToPDF):"), "%d", &result.Fake)
		} else if strings.HasPrefix(line, "⚠️ 未知 Producer:") {
			fmt.Sscanf(strings.TrimPrefix(line, "⚠️ 未知 Producer:"), "%d", &result.Unknown)
		}
	}
	raw, _ := json.Marshal(result)
	return &mcp.CallToolResult{
		Content: []mcp.Content{&mcp.TextContent{Text: string(raw)}},
	}, result, nil
}

// --- HLO Tool 4: medit_hlo_corr (NL 修正自升级) ---

type HloCorrInput struct {
	RowPref   string `json:"row_pref" jsonschema:"Row 编号 e.g. 5-7 或 P5-7"`
	Field     string `json:"field" jsonschema:"字段 e.g. d / e / g / h"`
	Predicted string `json:"predicted" jsonschema:"LLM 预测值 e.g. Qin S"`
	Corrected string `json:"corrected" jsonschema:"用户真值 e.g. Meyer T"`
}

type HloCorrOutput struct {
	RowPref   string `json:"row_pref"`
	Field     string `json:"field"`
	Predicted string `json:"predicted"`
	Corrected string `json:"corrected"`
	Status    string `json:"status"`
	Output    string `json:"output"`
	Source    string `json:"source"`
}

func hloCorrTool(_ context.Context, _ *mcp.CallToolRequest, input HloCorrInput) (*mcp.CallToolResult, HloCorrOutput, error) {
	if input.RowPref == "" || input.Predicted == "" || input.Corrected == "" {
		return nil, HloCorrOutput{}, fmt.Errorf("row_pref, predicted, corrected are required")
	}
	// 构造 NL: "P5-7 d Qin S 改成 Meyer T"
	nl := fmt.Sprintf("P%s %s %s 改成 %s", input.RowPref, input.Field, input.Predicted, input.Corrected)
	out, err := hloRunPython(nl)
	if err != nil {
		return nil, HloCorrOutput{}, err
	}

	result := HloCorrOutput{
		RowPref:   "P" + input.RowPref,
		Field:     input.Field,
		Predicted: input.Predicted,
		Corrected: input.Corrected,
		Status:    "ok",
		Output:    out,
		Source:    "hlo_nlu_v2.py record_correction_nl",
	}
	if strings.Contains(out, "error") || strings.Contains(out, "❌") {
		result.Status = "error"
	}
	raw, _ := json.Marshal(result)
	return &mcp.CallToolResult{
		Content: []mcp.Content{&mcp.TextContent{Text: string(raw)}},
	}, result, nil
}
