// Package source provides adapters for medical literature sources.
//
// HLO (Hermes Literature Orchestrator) integration (2026-07-28):
//   - hlo_orchestrator.go : 🔥 HLO NLU-First adapter (calls Python hlo_nlu_v2.py)
//   - pubmed.go           : NCBI E-utilities
//   - openalex.go         : OpenAlex API
//   - s2.go               : Semantic Scholar
//   - antfu.go            : 蚂蚁阿福 RAG (Chrome CDP)
//
// HLO 提供:
//   1. NLU 自然语言入口 (1 句 NL = 1 次执行, 14 意图路由)
//   2. 32 Producer 白名单 PDF 真伪鉴定
//   3. 5 模式 BibTeX Author 简写
//   4. 17 DOI 前缀期刊映射
//   5. 飞书 H 字段 v2.0 8 section (anno2ppt 完美对应)
//   6. _downloads/ 命名规范化
//   7. 160 Row 字段真值表
//   8. 自升级: NL 修正 → MEMORY → skill patch
package source

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"strings"
	"time"

	"github.com/veawho/via54Medit/pkg/types"
)

// --- HLO Adapter (调 Python hlo_nlu_v2.py) ---

// HLOSource bridges Go via54Medit with Python hlo_nlu_v2.py.
//
// 集成方式 (零重写):
//   - 接收自然语言查询
//   - 调 hlo_nlu_v2.py "<NL>" → JSON 输出
//   - 解析 14 意图 (process_row / search_papers / audit / ...)
//   - 返回 Citation 列表 (用于 medit_ask 融合)
//
// 设计原则:
//   - 零浏览器 (无 Langfuse 依赖)
//   - 零密钥 (4 源 API 0 key 起步)
//   - 零记忆 (用户不需要记命令名)
//   - 零成本 (复用 HLO 现有 14KB SQLite + 4 源 API 缓存)
type HLOSource struct {
	scriptPath string
	pythonPath string
	enabled    bool
	timeout    time.Duration
}

// NewHLOSource builds a HLO adapter from config.
//
// Recognized keys: enabled, script_path, python_path, timeout.
// Defaults: enabled=true, script_path=auto-detect, python_path=python3.11, timeout=60s.
func NewHLOSource(cfg map[string]any) (*HLOSource, error) {
	s := &HLOSource{
		scriptPath: autoDetectScript(),
		pythonPath: "python3.11",
		enabled:    true,
		timeout:    60 * time.Second,
	}
	if cfg != nil {
		if v, ok := cfg["script_path"].(string); ok {
			s.scriptPath = v
		}
		if v, ok := cfg["python_path"].(string); ok {
			s.pythonPath = v
		}
		if v, ok := cfg["timeout"].(string); ok {
			if d, err := time.ParseDuration(v); err == nil {
				s.timeout = d
			}
		}
		if v, ok := cfg["enabled"].(bool); ok {
			s.enabled = v
		}
	}
	// 验证脚本存在
	if _, err := exec.LookPath(s.scriptPath); err != nil && !fileExists(s.scriptPath) {
		return nil, fmt.Errorf("hlo script not found: %s", s.scriptPath)
	}
	return s, nil
}

// autoDetectScript 自动找 hlo_nlu_v2.py (按可能性优先级)
func autoDetectScript() string {
	candidates := []string{
		"/Users/david/Desktop/HLO_design/hlo_nlu_v2.py",
		"./hlo_nlu_v2.py",
		"$HOME/HLO_design/hlo_nlu_v2.py",
	}
	for _, c := range candidates {
		if fileExists(c) {
			return c
		}
	}
	return candidates[0] // fallback, will error out
}

func fileExists(p string) bool {
	_, err := osStat(p)
	return err == nil
}

// osStat is a thin wrapper to allow testability.
func osStat(p string) (struct{}, error) {
	if _, err := exec.LookPath(p); err == nil {
		return struct{}{}, nil
	}
	// 也检查 file://
	if _, err := exec.Command("test", "-f", p).Output(); err == nil {
		return struct{}{}, nil
	}
	return struct{}{}, fmt.Errorf("not found: %s", p)
}

// Name returns the source identifier.
func (h *HLOSource) Name() string { return "hlo" }

// Enabled reports whether the source is active.
func (h *HLOSource) Enabled() bool { return h.enabled }

// Health checks whether hlo_nlu_v2.py is reachable.
func (h *HLOSource) Health(ctx context.Context) error {
	cmd := exec.CommandContext(ctx, h.pythonPath, h.scriptPath, "test")
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("hlo health: %w (out: %s)", err, string(out))
	}
	return nil
}

// Search performs a natural language query through HLO.
//
// HLO 返回的 search_papers 意图: Europe PMC 实时拉取
// 其他 13 意图不直接返回 citations, 而是返回结构化结果
func (h *HLOSource) Search(ctx context.Context, q types.EBMQuestion, limit int) ([]types.Citation, error) {
	if !h.enabled {
		return nil, nil
	}
	if limit <= 0 {
		limit = 20
	}

	// 调 hlo_nlu_v2.py
	// 默认用 "找 <query>" 触发 search_papers 意图
	nlQuery := fmt.Sprintf("找 %s", q.Query)
	if q.TimeRange.From > 0 || q.TimeRange.To > 0 {
		nlQuery = fmt.Sprintf("%s (%d-%d)", nlQuery, q.TimeRange.From, q.TimeRange.To)
	}

	ctx, cancel := context.WithTimeout(ctx, h.timeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, h.pythonPath, h.scriptPath, nlQuery)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("hlo search: %w (stderr: %s)", err, stderr.String())
	}

	// 解析 HLO 输出
	return h.parseSearchOutput(stdout.String(), limit), nil
}

// parseSearchOutput 解析 hlo_nlu_v2.py 输出为 Citation 列表.
//
// HLO search_papers 格式:
//   🎯 意图: search_papers
//   ⏱️  耗时: 1380ms
//
//   🔍 关键词: Qin S 2025 HCC (最近 7 天)
//   📚 找到 5 篇
//
//   1. 🔓 Title here
//      Author A, Author B | Journal (Year)
//      DOI: 10.xxxx | PMID: xxxxx
func (h *HLOSource) parseSearchOutput(output string, limit int) []types.Citation {
	cites := make([]types.Citation, 0, limit)
	lines := strings.Split(output, "\n")

	var current *types.Citation
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			current = nil
			continue
		}
		// 1. Title 行: "1. 🔓 Title here" 或 "1. Title here"
		if strings.HasPrefix(line, "📚") || strings.HasPrefix(line, "🎯") ||
			strings.HasPrefix(line, "⏱️") || strings.HasPrefix(line, "🔍") {
			continue
		}
		// 解析 "1. Title"
		if strings.Contains(line, ".") && len(cites) < limit {
			parts := strings.SplitN(line, ".", 2)
			if len(parts) == 2 {
				title := strings.TrimSpace(parts[1])
				// 去掉 emoji 前缀 (🔓/🔒)
				title = strings.TrimLeft(title, "🔓🔒 \t")
				if title != "" {
					current = &types.Citation{
						ID:    fmt.Sprintf("hlo-%d", len(cites)),
						Title: title,
					}
					cites = append(cites, *current)
				}
			}
			continue
		}
		// 2. 作者/期刊行: "Author A, Author B | Journal (Year)"
		if current != nil && strings.Contains(line, "|") {
			parts := strings.SplitN(line, "|", 2)
			if len(parts) == 2 {
				current.Authors = parseAuthors(strings.TrimSpace(parts[0]))
				journalYear := strings.TrimSpace(parts[1])
				if idx := strings.LastIndex(journalYear, "("); idx > 0 {
					current.Journal = strings.TrimSpace(journalYear[:idx])
					yearStr := strings.TrimRight(strings.TrimSpace(journalYear[idx+1:]), ")")
					fmt.Sscanf(yearStr, "%d", &current.Year)
				}
			}
			continue
		}
		// 3. DOI/PMID 行: "DOI: 10.xxxx | PMID: xxxxx"
		if current != nil && (strings.Contains(line, "DOI:") || strings.Contains(line, "PMID:")) {
			if idx := strings.Index(line, "DOI:"); idx >= 0 {
				doiPart := line[idx+4:]
				if pipeIdx := strings.Index(doiPart, "|"); pipeIdx > 0 {
					doiPart = doiPart[:pipeIdx]
				}
				current.DOI = strings.TrimSpace(doiPart)
			}
			if idx := strings.Index(line, "PMID:"); idx >= 0 {
				pmidPart := line[idx+5:]
				current.PMID = strings.TrimSpace(pmidPart)
			}
		}
	}
	return cites
}

// parseAuthors splits "Author A, Author B" into []string.
func parseAuthors(s string) []string {
	parts := strings.Split(s, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		if t := strings.TrimSpace(p); t != "" {
			out = append(out, t)
		}
	}
	return out
}

// --- HLO Truth Query (字段真值表) ---

// HLOTruthQuery 返回 160 Row 字段真值表 (medit_grade 升级数据源).
//
// 数据源: ~/.hermes/cache/lit_truth.json (160 Row DOI + Author 真值)
func HLOTruthQuery(rowPref string) (map[string]any, error) {
	truthPath := osHomeDir() + "/.hermes/cache/lit_truth.json"
	if !fileExists(truthPath) {
		// 自动生成
		cmd := exec.Command("python3.11", "/Users/david/Desktop/HLO_design/hlo_nlu_v2.py", "刷新 truth")
		if err := cmd.Run(); err != nil {
			return nil, fmt.Errorf("truth refresh failed: %w", err)
		}
	}
	// 读 JSON
	cmd := exec.Command("python3.11", "-c",
		fmt.Sprintf("import json; t=json.load(open('%s')); print(json.dumps(t.get('%s', {})))", truthPath, rowPref))
	out, err := cmd.Output()
	if err != nil {
		return nil, err
	}
	var result map[string]any
	if err := json.Unmarshal(out, &result); err != nil {
		return nil, err
	}
	return result, nil
}

func osHomeDir() string {
	out, _ := exec.Command("sh", "-c", "echo $HOME").Output()
	return strings.TrimSpace(string(out))
}
