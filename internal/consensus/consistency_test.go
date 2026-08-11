package consensus

import (
	"strings"
	"testing"
)

// VoteX 是 X 票的 voter
func VoteX(answer string, conf float64, n int) []Voter {
	return make([]Voter, n)
}

func mkVoter(answer string, conf float64) Voter {
	return func(q string) Vote {
		return Vote{Answer: answer, Confidence: conf}
	}
}

// TestConsensus_AllAgree 算法测试: 5 票全一致 → agreement=1.0
func TestConsensus_AllAgree(t *testing.T) {
	voters := []Voter{
		mkVoter("process_row", 0.9),
		mkVoter("process_row", 0.85),
		mkVoter("process_row", 0.95),
		mkVoter("process_row", 0.88),
		mkVoter("process_row", 0.92),
	}
	sc := NewSelfConsistency(voters)
	ans, agree, votes := sc.Consensus("处理 P5-7")
	if ans != "process_row" {
		t.Errorf("Consensus = %s, want process_row", ans)
	}
	if agree != 1.0 {
		t.Errorf("Agreement = %f, want 1.0 (all same)", agree)
	}
	if len(votes) != 5 {
		t.Errorf("Votes = %d, want 5", len(votes))
	}
}

// TestConsensus_Majority 算法测试: 3 票 A + 2 票 B → A 胜
func TestConsensus_Majority(t *testing.T) {
	voters := []Voter{
		mkVoter("process_row", 0.9),
		mkVoter("process_row", 0.85),
		mkVoter("process_row", 0.95),
		mkVoter("audit", 0.8),
		mkVoter("audit", 0.7),
	}
	sc := NewSelfConsistency(voters)
	ans, agree, _ := sc.Consensus("处理")
	if ans != "process_row" {
		t.Errorf("Consensus = %s, want process_row (3 votes vs 2)", ans)
	}
	if agree != 0.6 {
		t.Errorf("Agreement = %f, want 0.6 (3/5)", agree)
	}
}

// TestConsensus_TieBreakAvg 算法测试: 2 票 A + 2 票 B → tie, 高 avg_conf 胜
func TestConsensus_TieBreakAvg(t *testing.T) {
	voters := []Voter{
		mkVoter("A", 0.6), // avg 0.7
		mkVoter("A", 0.8),
		mkVoter("B", 0.9), // avg 0.9 (higher)
		mkVoter("B", 0.9),
	}
	sc := NewSelfConsistency(voters)
	sc.TieBreak = "avg_confidence"
	ans, _, _ := sc.Consensus("test")
	if ans != "B" {
		t.Errorf("Tie-break by avg_conf 应该 B 胜 (avg 0.9 vs 0.7), got %s", ans)
	}
}

// TestConsensus_AllDifferent 算法测试: 5 票都不同 → agreement=0.2
func TestConsensus_AllDifferent(t *testing.T) {
	voters := []Voter{
		mkVoter("A", 0.5),
		mkVoter("B", 0.5),
		mkVoter("C", 0.5),
		mkVoter("D", 0.5),
		mkVoter("E", 0.5),
	}
	sc := NewSelfConsistency(voters)
	ans, agree, _ := sc.Consensus("test")
	if agree != 0.2 {
		t.Errorf("Agreement = %f, want 0.2 (1/5)", agree)
	}
	// 算法: 任何 ans 都 OK (5 票都不同)
	if ans == "" {
		t.Errorf("ans 不应该是空")
	}
}

// TestConsensus_EmptyVoters 算法测试: 空 voters 不崩溃
func TestConsensus_EmptyVoters(t *testing.T) {
	sc := NewSelfConsistency(nil)
	ans, agree, _ := sc.Consensus("test")
	if ans != "" || agree != 0 {
		t.Errorf("空 voters 应该返回 (\"\", 0), got (%q, %f)", ans, agree)
	}
}

// TestConsensus_QueryPassedThrough 算法测试: query 真的传给 voter
func TestConsensus_QueryPassedThrough(t *testing.T) {
	var capturedQuery string
	voters := []Voter{
		func(q string) Vote { capturedQuery = q; return Vote{Answer: "A", Confidence: 0.9} },
		mkVoter("A", 0.9),
		mkVoter("A", 0.9),
		mkVoter("A", 0.9),
		mkVoter("A", 0.9),
	}
	sc := NewSelfConsistency(voters)
	sc.Consensus("hello world")
	if capturedQuery != "hello world" {
		t.Errorf("capturedQuery = %q, want 'hello world'", capturedQuery)
	}
}

// TestMultipleResults 算法测试: 不一致时返回多条候选
func TestMultipleResults(t *testing.T) {
	voters := []Voter{
		mkVoter("A", 0.9),
		mkVoter("A", 0.9),
		mkVoter("A", 0.9),
		mkVoter("B", 0.7),
		mkVoter("C", 0.5),
	}
	sc := NewSelfConsistency(voters)
	results := sc.MultipleResults("test")

	if len(results) != 3 {
		t.Errorf("MultipleResults 应该返回 3 个候选, got %d", len(results))
	}
	// 按 Count desc 排序
	if results[0].Answer != "A" || results[0].Count != 3 {
		t.Errorf("Top-1 应该 A (3 votes), got %s (%d)", results[0].Answer, results[0].Count)
	}
	// avg_conf 应该正确
	if results[0].AvgConf != 0.9 {
		t.Errorf("A avg conf = %f, want 0.9", results[0].AvgConf)
	}
}

// TestConsensus_MultiRound 算法测试: 多轮投票 (一致性在 5 票 70%)
func TestConsensus_MultiRound(t *testing.T) {
	// 模拟: 5 次问, 4 次 process_row, 1 次 audit → process_row 胜 (80%)
	voters := []Voter{
		mkVoter("process_row", 0.9),
		mkVoter("process_row", 0.85),
		mkVoter("process_row", 0.92),
		mkVoter("process_row", 0.88),
		mkVoter("audit", 0.7),
	}
	sc := NewSelfConsistency(voters)
	ans, agree, _ := sc.Consensus("处理 P5-7")
	if ans != "process_row" {
		t.Errorf("80%% 应该 process_row, got %s", ans)
	}
	if agree != 0.8 {
		t.Errorf("Agreement = %f, want 0.8", agree)
	}
}

// TestConsensus_Stats 算法测试: Stats 输出
func TestConsensus_Stats(t *testing.T) {
	voters := []Voter{mkVoter("A", 0.9), mkVoter("A", 0.9)}
	sc := NewSelfConsistency(voters)
	sc.N = 7
	s := sc.Stats()
	if s.N != 7 {
		t.Errorf("Stats.N = %d, want 7", s.N)
	}
	if !strings.Contains(s.Tie, "freq") {
		t.Errorf("Stats.Tie 应该含 'freq', got %s", s.Tie)
	}
}
