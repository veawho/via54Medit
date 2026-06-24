// Command medit-mcp is the via54Medit MCP Server entry point.
//
// It exposes 4 tools to MCP clients (Claude Desktop, Cursor, VS Code
// Copilot, etc.):
//
//   - medit_ask      : 一句话循证检索 (4 源并发 + LLM 摘要)
//   - medit_pico     : PICO 抽取 (Phase 3 实装, Phase 4.0 先做 placeholder)
//   - medit_grade    : GRADE 评级 (Phase 3 实装, Phase 4.0 先做 placeholder)
//   - medit_anno2ppt : 证据包 → PPT (Phase 3 实装, Phase 4.0 先做 placeholder)
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
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"os"
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
			"endpoint": "http://localhost:8642",
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
