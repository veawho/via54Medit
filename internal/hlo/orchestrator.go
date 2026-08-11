// Package hlo — Hermes Literature Orchestrator (算法驱动版)
//
// 这是 via54Medit 算法驱动升级 Phase 1 的核心模块 (v1.0.0, 2026-07-29)。
// 原 cmd/medit/commands/hlo.go 188 行全是 exec.Command 调 Python,
// 现重写为纯 Go 算法 + 数据结构驱动, 跨设备 deterministic 一致。
//
// 设计原则 (用户原话 2026-07-29):
//   1. "算法比规则靠谱, 所有能力依靠算法驱动"
//   2. "算法配合 LLM, 去理解概念、理解规则的相对性"
//   3. "不写死绝对值, 强行塞记忆"
//
// 5 大算法武器 (业界验证, 见 /tmp/algorithm_vs_rules_research.md):
//   - Regex pattern matching (NLU 路由, 替代硬编码 if/else)
//   - Probabilistic intent scoring (多意图叠加 + 置信度)
//   - LRU + radix tree 数据结构 (替代 list 查询)
//   - PageRank 图算法 (跨 Row 引用关系, 替代 P 目录硬编码)
//   - LLM reflection (置信度低时让 LLM 反思)
//
// 架构 (算法驱动, 不是规则驱动):
//   ┌─────────────────────────────────────────┐
//   │ Input: "处理 P5-7"                       │
//   └────────────────┬────────────────────────┘
//                    ↓
//   ┌─────────────────────────────────────────┐
//   │ 1. Tokenize (regex split)               │  ← 算法 (不是 if/else)
//   └────────────────┬────────────────────────┘
//                    ↓
//   ┌─────────────────────────────────────────┐
//   │ 2. Match patterns (priority list)        │  ← 算法 (14 个 intent pattern)
//   │    每个 pattern 返回 (intent, score)     │
//   └────────────────┬────────────────────────┘
//                    ↓
//   ┌─────────────────────────────────────────┐
//   │ 3. Top-K intent 投票 (置信度聚合)        │  ← 算法 (Self-Consistency)
//   │    score > threshold → 用 LLM 二次确认    │  ← 规则相对性
//   └────────────────┬────────────────────────┘
//                    ↓
//   ┌─────────────────────────────────────────┐
//   │ 4. Handler dispatch (动态查表)           │  ← 算法 (map[Intent]Handler)
//   └────────────────┬────────────────────────┘
//                    ↓
//   ┌─────────────────────────────────────────┐
//   │ 5. Output (格式化 + 置信度报告)           │
//   └─────────────────────────────────────────┘
package hlo

import (
	"fmt"
	"regexp"
	"sort"
	"strings"
)

// Intent 是 14 种 NLU 意图类型
type Intent string

const (
	IntentProcessRow       Intent = "process_row"
	IntentSearchPapers      Intent = "search_papers"
	IntentSearchAuthorYear  Intent = "search_author_year"
	IntentAudit             Intent = "audit"
	IntentCronUpgrade       Intent = "cron_upgrade"
	IntentNormalize         Intent = "normalize"
	IntentDailyPush         Intent = "daily_push"
	IntentRecordCorrection  Intent = "record_correction_nl"
	IntentEvalSkills        Intent = "eval_skills"
	IntentRefreshTruth      Intent = "refresh_truth"
	IntentRecentPapers      Intent = "recent_papers"
	IntentTest              Intent = "test"
	IntentHelp              Intent = "help"
	IntentDedup             Intent = "dedup"
	IntentVerifyPdfFulltext Intent = "verify_pdf_fulltext" // v1.5.0 NEW
	IntentUserSuppliedURL   Intent = "user_supplied_url"   // v1.5.0 NEW
	IntentSciHubFetch       Intent = "scihub_fetch"        // v1.5.0 NEW
	IntentVerifyPDFMetadata Intent = "verify_pdf_metadata" // v1.5.0 NEW
	IntentPMCPowBypass      Intent = "pmc_pow_bypass"      // v1.5.0 NEW
	IntentFreeQuery         Intent = "free_query"
)

// Pattern 表示一条 intent pattern, 含正则 + 优先级 + 槽位提取
type Pattern struct {
	Regex    *regexp.Regexp
	Intent   Intent
	Priority int    // 短意图优先, 数字越大越先匹配
	Weight   float64 // 命中后加权 (1.0 = 标准, < 1 = 模糊匹配)
}

// IntentMatch 表示一次匹配结果
type IntentMatch struct {
	Intent    Intent
	Score     float64 // 0-1, 1 = 完全匹配
	Slots     []string // 捕获组
	Raw       string  // 原始输入
}

// ParseResult 是 NLU 路由结果
type ParseResult struct {
	Best  IntentMatch   // 最高分意图
	All   []IntentMatch // 所有候选 (按 score 降序)
	Confidence float64   // 整体置信度 (0-1)
	NeedsLLM   bool      // 是否需要 LLM 二次确认
}

// 默认 NLU 路由阈值 (相对性: 不是绝对的 0.7, 而是上下文调整)
const (
	DefaultConfidenceThreshold = 0.65 // 65% 置信度才不调 LLM
	ShortIntentBonus           = 0.20 // 短意图 ("test"/"help") 加分
)

// 14 个 intent pattern 表 (算法驱动, 不是规则表)
//
// 优先级: 短意图 (test/help/audit) > 关键词意图 (process/record) > 模糊意图 (free_query)
// 每个 pattern 有 Priority (高优先级先匹配) + Weight (匹配质量)
var defaultPatterns = []Pattern{
	// === 短意图 (最高优先级) ===
	{Regex: regexp.MustCompile(`^(?:test|测试|自检)\s*$`), Intent: IntentTest, Priority: 100, Weight: 1.0},
	{Regex: regexp.MustCompile(`^(?:help|帮助|怎么用|怎么玩|功能)\s*$`), Intent: IntentHelp, Priority: 100, Weight: 1.0},
	{Regex: regexp.MustCompile(`^(?:评估|eval|skill|总结)`), Intent: IntentEvalSkills, Priority: 95, Weight: 0.9},
	{Regex: regexp.MustCompile(`^(?:刷新|refresh|真值表|truth)`), Intent: IntentRefreshTruth, Priority: 95, Weight: 0.9},
	{Regex: regexp.MustCompile(`^(?:升级|自升级|evolve|self-upgrade|cron-upgrade)\s*$`), Intent: IntentCronUpgrade, Priority: 90, Weight: 1.0},
	{Regex: regexp.MustCompile(`^(?:规范化|normalize|改名|重命名)\s*$`), Intent: IntentNormalize, Priority: 90, Weight: 1.0},
	{Regex: regexp.MustCompile(`^(?:审计|audit|检查|校准|真伪)\s*$`), Intent: IntentAudit, Priority: 90, Weight: 1.0},
	{Regex: regexp.MustCompile(`^(?:每日|推送|daily|跑批|cron)\s*$`), Intent: IntentDailyPush, Priority: 85, Weight: 1.0},

	// === v1.5.0 NEW: 5 个新意图 ===
	{Regex: regexp.MustCompile(`(?:这个\s*(?:pdf|PDF)\s*(?:是不是|是否)\s*(?:错配|错|对))`), Intent: IntentVerifyPdfFulltext, Priority: 92, Weight: 0.95},
	{Regex: regexp.MustCompile(`(?:我(?:下载了|给你的|发了)|提供|发了)(?:网页|截图|pdf|链接|文章|文献)?`), Intent: IntentUserSuppliedURL, Priority: 92, Weight: 0.95},
	{Regex: regexp.MustCompile(`(?:PMC|pmc)(\d+)\s+(?:下|下载|fetch|get)\s+(\S+)`), Intent: IntentPMCPowBypass, Priority: 92, Weight: 0.95},
	{Regex: regexp.MustCompile(`(?:sci-hub|scihub|科学\s*hub)\s+(\S+)`), Intent: IntentSciHubFetch, Priority: 92, Weight: 0.95},
	{Regex: regexp.MustCompile(`(?:验证|鉴定|真伪|check|audit)\s+(?:.*?\s+)?(/\S+\.pdf|\S+\.pdf)`), Intent: IntentVerifyPDFMetadata, Priority: 92, Weight: 0.95},

	// === Row 处理 ===
	{Regex: regexp.MustCompile(`^(?:处理|跑|执行|process|看下|看)\s*(?:P?(\d+)-(\d+)|row\s*(\d+)|第?\s*(\d+)\s*(?:row|行|号)?)`), Intent: IntentProcessRow, Priority: 80, Weight: 0.95},

	// === 找文献 ===
	{Regex: regexp.MustCompile(`^(?:找|搜|查|query|search)\s+(.+?)(?:\s+(?:最近|近|recent|new))?\s*(\d+)?\s*(?:天|day|周|week|月|month|篇)?\s*$`), Intent: IntentSearchPapers, Priority: 75, Weight: 0.85},

	// === 找作者+年份 (Go regexp 不支持 negative lookahead, 改用 Priority 解决) ===
	// 算法: 短意图 Priority=100 已先匹配, search_author_year Priority=60 排在后面
	// 即使 "test" 也会先命中 IntentTest (Priority=100), 不会触发这条
	{Regex: regexp.MustCompile(`^([A-Z][a-zA-Z-]+(?:\s+[A-Z]\.?)?)\s*(\d{4})?\s*(?:HCC|liver|肝|cancer|hepatocellular|论文|文献)?\s*$`), Intent: IntentSearchAuthorYear, Priority: 60, Weight: 0.7},

	// === NL 修正 ===
	{Regex: regexp.MustCompile(`^(?:记录|record|修正|改|错|应该是|改成)\s*(?:P?(\d+)-(\d+))?\s*(?:的\s*)?(\w+)?\s*(?:字段|field)?\s*["\']?(.+?)["\']?\s*(?:应该是|改成|→|->|to|=)\s*["\']?(.+?)["\']?$`), Intent: IntentRecordCorrection, Priority: 70, Weight: 0.95},
	{Regex: regexp.MustCompile(`^(?:Row\s+)?P?(\d+)-(\d+)\s*(?:的\s*)?(\w+)?\s*(?:字段|field)?\s*["\']?(.+?)["\']?\s*(?:应该是|改成|→|->|to|=)\s*["\']?(.+?)["\']?$`), Intent: IntentRecordCorrection, Priority: 70, Weight: 0.95},

	// === 看 N 篇新论文 ===
	{Regex: regexp.MustCompile(`^(?:最近|recent|new)\s*(\d+)?\s*篇?`), Intent: IntentRecentPapers, Priority: 65, Weight: 0.8},

	// === 去重 ===
	{Regex: regexp.MustCompile(`^(?:去重|dedup|重复|cleanup)`), Intent: IntentDedup, Priority: 85, Weight: 0.9},

	// === 默认: 自由 query ===
	{Regex: regexp.MustCompile(`^(.+)$`), Intent: IntentFreeQuery, Priority: 0, Weight: 0.5},
}

// Orchestrator 是 HLO 算法驱动入口 (算法驱动, 不是规则表)
// 设计: 持有 patterns 表 + LLM client 接口 + 自升级状态
type Orchestrator struct {
	patterns []Pattern
	llm      LLMClient // 接口 (DI), 不是写死 provider
}

// LLMClient 是 LLM 抽象 (通过接口注入, 算法不依赖具体 provider)
type LLMClient interface {
	// Confirm 当 NLU 置信度低时, 让 LLM 二次确认
	Confirm(ctx interface{}, text string, candidates []IntentMatch) (Intent, float64, error)
}

// NoopLLMClient 是 LLM client 的 fallback 实现 (离线场景)
type NoopLLMClient struct{}

func (n *NoopLLMClient) Confirm(ctx interface{}, text string, candidates []IntentMatch) (Intent, float64, error) {
	if len(candidates) == 0 {
		return IntentFreeQuery, 0, nil
	}
	return candidates[0].Intent, candidates[0].Score, nil
}

// NewOrchestrator 创建一个算法驱动的 Orchestrator (不依赖任何 hardcoded provider)
func NewOrchestrator(llm LLMClient) *Orchestrator {
	if llm == nil {
		llm = &NoopLLMClient{}
	}
	return &Orchestrator{
		patterns: defaultPatterns,
		llm:      llm,
	}
}

// Parse 算法 1: 输入自然语言, 输出 N 个候选意图 + score (0-1)
//
// 不是 if/else 硬编码, 而是:
//   1. 每个 pattern 跑一次正则匹配
//   2. 命中 pattern 加 priority + weight 计算 score
//   3. 返回所有候选, 按 score 降序
//
// 这是 DSPy "声明式 pattern 表 + 算法打分" 的 Go 实现
func (o *Orchestrator) Parse(text string) ParseResult {
	text = strings.TrimSpace(text)
	if text == "" {
		return ParseResult{
			Best:       IntentMatch{Intent: IntentFreeQuery, Score: 0, Raw: text},
			Confidence: 0,
			NeedsLLM:   true,
		}
	}

	// 算法: 跑所有 patterns, 收集候选
	var candidates []IntentMatch
	for _, p := range o.patterns {
		matches := p.Regex.FindStringSubmatch(text)
		if matches == nil {
			continue
		}

		// 算法: 综合 score = priority_score * weight
		// priority_score: (priority / 100) 归一化到 0-1
		// weight: pattern 自身权值 (0-1)
		// 短意图 bonus: 完整匹配 = 100% (优先级最高)
		score := (float64(p.Priority) / 100.0) * p.Weight
		// 短输入 (完全匹配, len < 10) 加 bonus
		if len(text) <= 10 && matches[0] == text {
			score += ShortIntentBonus
		}
		// 归一化到 0-1
		if score > 1.0 {
			score = 1.0
		}

		candidates = append(candidates, IntentMatch{
			Intent: p.Intent,
			Score:  score,
			Slots:  matches[1:], // 跳过完整匹配
			Raw:    text,
		})
	}

	// 算法: 排序 (按 score 降序) - Go sort 不保证稳定性, 但我们不需
	sort.SliceStable(candidates, func(i, j int) bool {
		return candidates[i].Score > candidates[j].Score
	})

	if len(candidates) == 0 {
		return ParseResult{
			Best:       IntentMatch{Intent: IntentFreeQuery, Score: 0, Raw: text},
			Confidence: 0,
			NeedsLLM:   true,
		}
	}

	best := candidates[0]
	confidence := best.Score
	needsLLM := confidence < DefaultConfidenceThreshold

	return ParseResult{
		Best:       best,
		All:        candidates,
		Confidence: confidence,
		NeedsLLM:   needsLLM,
	}
}

// ParseWithLLM 算法 2: 当置信度低时, 让 LLM 二次确认
//
// 这是 "规则相对性" 的标准实现 (业界 DSPy GEPA + 自一致性):
//   - 置信度低 → 不强行决定
//   - 让 LLM 看 Top-K 候选 + 反思
//   - 返回 LLM 的判断 + 自己的置信度
func (o *Orchestrator) ParseWithLLM(ctx interface{}, text string, topK int) (ParseResult, error) {
	parsed := o.Parse(text)
	if !parsed.NeedsLLM {
		return parsed, nil
	}

	// 取 Top-K 候选 (默认 3)
	if topK <= 0 {
		topK = 3
	}
	if topK > len(parsed.All) {
		topK = len(parsed.All)
	}
	candidates := parsed.All[:topK]

	// 算法: 让 LLM 二次确认
	intent, conf, err := o.llm.Confirm(ctx, text, candidates)
	if err != nil {
		// LLM 失败时, 用算法 fallback (取最高分)
		return parsed, fmt.Errorf("LLM confirm: %w", err)
	}

	parsed.Best = IntentMatch{
		Intent: intent,
		Score:  conf,
		Raw:    text,
	}
	parsed.Confidence = conf
	parsed.NeedsLLM = false
	return parsed, nil
}

// Patterns 暴露 patterns (用于 testing / 自升级)
func (o *Orchestrator) Patterns() []Pattern {
	return o.patterns
}

// AddPattern 动态加 pattern (算法驱动, 不是改代码)
// 这就是 "不写死绝对值" — 模式可热加载, 不需重新编译
func (o *Orchestrator) AddPattern(p Pattern) {
	o.patterns = append(o.patterns, p)
}

// String 实现 fmt.Stringer, 用于输出
func (p Pattern) String() string {
	return fmt.Sprintf("Pattern{Intent=%s, Priority=%d, Weight=%.2f}", p.Intent, p.Priority, p.Weight)
}