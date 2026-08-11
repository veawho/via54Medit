package hlo

import (
	"regexp"
	"strings"
	"testing"
)

// TestOrchestrator_ShortIntents 算法测试: 短意图优先 (Priority=100)
func TestOrchestrator_ShortIntents(t *testing.T) {
	orch := NewOrchestrator(nil)

	tests := []struct {
		input    string
		expected Intent
	}{
		{"test", IntentTest},
		{"测试", IntentTest},
		{"help", IntentHelp},
		{"帮助", IntentHelp},
		{"audit", IntentAudit},
		{"审计", IntentAudit},
		{"normalize", IntentNormalize},
		{"规范化", IntentNormalize},
	}

	for _, tt := range tests {
		parsed := orch.Parse(tt.input)
		if parsed.Best.Intent != tt.expected {
			t.Errorf("Parse(%q).Intent = %q, want %q", tt.input, parsed.Best.Intent, tt.expected)
		}
		if parsed.Confidence < 0.65 {
			t.Errorf("Parse(%q).Confidence = %f, want ≥0.65", tt.input, parsed.Confidence)
		}
	}
}

// TestOrchestrator_ProcessRow 算法测试: 处理 Row 命令
func TestOrchestrator_ProcessRow(t *testing.T) {
	orch := NewOrchestrator(nil)

	parsed := orch.Parse("处理 P5-7")
	if parsed.Best.Intent != IntentProcessRow {
		t.Errorf("Parse(处理 P5-7).Intent = %q, want %q", parsed.Best.Intent, IntentProcessRow)
	}
	// 检查 slots: ["5", "7", "", ""]
	if len(parsed.Best.Slots) < 2 || parsed.Best.Slots[0] != "5" || parsed.Best.Slots[1] != "7" {
		t.Errorf("Parse(处理 P5-7).Slots = %v, want ['5', '7', ...]", parsed.Best.Slots)
	}
}

// TestOrchestrator_V15Intents 算法测试: v1.5.0 5 个新意图
func TestOrchestrator_V15Intents(t *testing.T) {
	orch := NewOrchestrator(nil)

	tests := []struct {
		input    string
		expected Intent
		minConf  float64
	}{
		{"PMC13367031 下 POH2-5-65", IntentPMCPowBypass, 0.6},
		{"sci-hub 10.1200/JCO.2012.44.5643", IntentSciHubFetch, 0.6},
		{"这个 PDF 是不是错配", IntentVerifyPdfFulltext, 0.6},
	}

	for _, tt := range tests {
		parsed := orch.Parse(tt.input)
		if parsed.Best.Intent != tt.expected {
			t.Errorf("Parse(%q).Intent = %q, want %q", tt.input, parsed.Best.Intent, tt.expected)
		}
		if parsed.Confidence < tt.minConf {
			t.Errorf("Parse(%q).Confidence = %f, want ≥%f", tt.input, parsed.Confidence, tt.minConf)
		}
	}
}

// TestOrchestrator_SearchPapers 算法测试: 找文献意图
func TestOrchestrator_SearchPapers(t *testing.T) {
	orch := NewOrchestrator(nil)

	parsed := orch.Parse("找 Qin S 2025 HCC")
	if parsed.Best.Intent != IntentSearchPapers {
		t.Errorf("Parse(找 Qin S 2025 HCC).Intent = %q, want %q", parsed.Best.Intent, IntentSearchPapers)
	}
}

// TestOrchestrator_AddPattern 算法测试: 热加载 pattern
func TestOrchestrator_AddPattern(t *testing.T) {
	orch := NewOrchestrator(nil)

	// 添加自定义 pattern
		orch.AddPattern(Pattern{
			Regex:    regexp.MustCompile(`^测试自定义意图\s+(\S+)$`),
			Intent:   "custom_intent",
			Priority: 80,
			Weight:   0.9,
		})

	parsed := orch.Parse("测试自定义意图 hello")
	// 注意: Intent 类型是 enum, "custom_intent" 是字符串, 需要 cast
	if string(parsed.Best.Intent) != "custom_intent" {
		t.Errorf("Parse(测试自定义意图 hello).Intent = %q, want %q", parsed.Best.Intent, "custom_intent")
	}
}
func TestOrchestrator_Priority(t *testing.T) {
	orch := NewOrchestrator(nil)

	// "audit" 应该是 IntentAudit (Priority=90), 不是 IntentTest (Priority=100)
	parsed := orch.Parse("audit")
	if parsed.Best.Intent != IntentAudit {
		t.Errorf("Parse(audit).Intent = %q, want %q (Priority=90)", parsed.Best.Intent, IntentAudit)
	}

	// 完全匹配短输入应该加分
	parsed2 := orch.Parse("test")
	if parsed2.Confidence < 0.85 {
		t.Errorf("Parse(test) 短输入完全匹配应该 ≥0.85, got %f", parsed2.Confidence)
	}
}

// TestOrchestrator_NeedsLLM 算法测试: 置信度低时 NeedsLLM=true
func TestOrchestrator_NeedsLLM(t *testing.T) {
	orch := NewOrchestrator(nil)

	parsed := orch.Parse("这是一段非常长的输入没有任何明确的关键词应该会触发自由查询路径")
	if !parsed.NeedsLLM {
		t.Errorf("Parse 长输入应该有 NeedsLLM=true")
	}
}

// TestPatterns_String 算法测试: Pattern 字符串表示
func TestPatterns_String(t *testing.T) {
	p := Pattern{
		Regex:    regexp.MustCompile(`^test$`),
		Intent:   IntentTest,
		Priority: 100,
		Weight:   1.0,
	}
	s := p.String()
	if s == "" {
		t.Errorf("Pattern.String() 返回空")
	}
	if !strings.Contains(s, "Intent=test") {
		t.Errorf("Pattern.String() 应包含 Intent=test, got %q", s)
	}
}
