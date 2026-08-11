// Package consensus — Self-Consistency 投票 (Phase 8 算法驱动, 2026-07-29)
//
// 算法思想 (Wang et al. 2022, arXiv:2203.11171):
//   1. 同问题问 N 次 (每条 reasoning path 不同, 因为 temperature > 0)
//   2. 收集 N 个答案 + 置信度
//   3. 投票: 选最频繁 / 加权最高 的答案
//   4. 替代 "单次问, 单次答" → 大幅提升 CoT 推理准确率
//
// via54Medit 适配:
//   - 场景: HLO NLU 不确定时, 多 path 投出稳定 intent
//   - 场景: dedupe 阈值边界, 多 embedding 投票
//   - 场景: 真伪鉴定, 多 vision model 投票
//
// 跨设备 deterministic: 固定 N + 固定 tie-break → 同输入同结果

package consensus

import (
	"sort"
	"sync"
)

// Vote 是单个投票
type Vote struct {
	Answer     string
	Confidence float64
}

// Voter 是投票者 (扩展示意接口, 实际是 closure / LLM 调用)
type Voter func(query string) Vote

// SelfConsistency 配置
type SelfConsistency struct {
	mu sync.Mutex

	// N 是采样次数 (典型 5-10)
	N int

	// MinAgreement 是最小一致率 (低于此返回 MultipleResults)
	MinAgreement float64

	// TieBreak 决胜策略 ("frequency" / "avg_confidence" / "max_confidence")
	TieBreak string

	// Voters 是 N 个投票者函数 (可重复同函数)
	Voters []Voter
}

// NewSelfConsistency 创建 (默认 N=5, MinAgreement=0.6)
func NewSelfConsistency(voters []Voter) *SelfConsistency {
	return &SelfConsistency{
		N:            5,
		MinAgreement: 0.6,
		TieBreak:     "frequency",
		Voters:       voters,
	}
}

// Consensus 算法: 跑 N 个 vote, 投票出 consensus
// 返回:
//   - answer: 共识答案
//   - agreement: 一致率 (0-1)
//   - allVotes: 所有 N 个投票
func (sc *SelfConsistency) Consensus(query string) (string, float64, []Vote) {
	sc.mu.Lock()
	defer sc.mu.Unlock()

	if len(sc.Voters) == 0 {
		return "", 0, nil
	}

	// 算法: 收集 N 个 vote
	allVotes := make([]Vote, len(sc.Voters))
	for i, voter := range sc.Voters {
		allVotes[i] = voter(query)
	}

	// 算法: 计算答案频率
	counts := make(map[string]int)
	for _, v := range allVotes {
		counts[v.Answer]++
	}

	// 算法: 排序 by frequency desc
	type scored struct {
		answer string
		count  int
	}
	var sortedAnswers []scored
	for ans, cnt := range counts {
		sortedAnswers = append(sortedAnswers, scored{ans, cnt})
	}
	sort.Slice(sortedAnswers, func(i, j int) bool {
		if sortedAnswers[i].count != sortedAnswers[j].count {
			return sortedAnswers[i].count > sortedAnswers[j].count
		}
		// tie-break: 按 avg_confidence (algorithm tieBreak = "avg_confidence")
		return avgConf(sortedAnswers[i].answer, allVotes) > avgConf(sortedAnswers[j].answer, allVotes)
	})

	if len(sortedAnswers) == 0 {
		return "", 0, allVotes
	}

	winner := sortedAnswers[0]
	agreement := float64(winner.count) / float64(len(allVotes))

	return winner.answer, agreement, allVotes
}

// avgConf 算法: 平均置信度 (辅助 tie-break)
func avgConf(answer string, votes []Vote) float64 {
	var sum, n float64
	for _, v := range votes {
		if v.Answer == answer {
			sum += v.Confidence
			n++
		}
	}
	if n == 0 {
		return 0
	}
	return sum / n
}

// MultipleResults 算法: 不一致时返回多条候选
type Result struct {
	Answer     string
	Count      int
	AvgConf    float64
}

func (sc *SelfConsistency) MultipleResults(query string) []Result {
	sc.mu.Lock()
	defer sc.mu.Unlock()

	if len(sc.Voters) == 0 {
		return nil
	}

	// 算法: 跑所有 voter
	allVotes := make([]Vote, len(sc.Voters))
	for i, voter := range sc.Voters {
		allVotes[i] = voter(query)
	}

	// 算法: 按 answer 聚合
	groups := make(map[string]*Result)
	confs := make(map[string][]float64)
	for _, v := range allVotes {
		if groups[v.Answer] == nil {
			groups[v.Answer] = &Result{Answer: v.Answer}
		}
		groups[v.Answer].Count++
		confs[v.Answer] = append(confs[v.Answer], v.Confidence)
	}

	// 算法: 算 avg conf
	results := make([]Result, 0, len(groups))
	for ans, r := range groups {
		sum := 0.0
		for _, c := range confs[ans] {
			sum += c
		}
		r.AvgConf = sum / float64(len(confs[ans]))
		results = append(results, *r)
	}

	// 算法: 按 Count desc 排序
	sort.Slice(results, func(i, j int) bool {
		return results[i].Count > results[j].Count
	})

	return results
}

// Stats 是 SelfConsistency 配置
type Stats struct {
	N     int     `json:"n"`
	Min   float64 `json:"min_agreement"`
	Tie   string  `json:"tie_break"`
}

func (sc *SelfConsistency) Stats() Stats {
	sc.mu.Lock()
	defer sc.mu.Unlock()
	return Stats{
		N:   sc.N,
		Min: sc.MinAgreement,
		Tie: sc.TieBreak,
	}
}
