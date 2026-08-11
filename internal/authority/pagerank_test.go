package authority

import (
	"math"
	"testing"
)

// TestPageRank_Empty 算法测试: 空图
func TestPageRank_Empty(t *testing.T) {
	pr := NewPageRank()
	pr.Compute()
	if len(pr.TopK(5)) != 0 {
		t.Errorf("空图 TopK 应该返回空")
	}
}

// TestPageRank_SingleNode 算法测试: 单节点
func TestPageRank_SingleNode(t *testing.T) {
	pr := NewPageRank()
	pr.AddNode("A")
	pr.Compute()

	results := pr.TopK(1)
	if len(results) != 1 {
		t.Fatalf("应该返回 1 结果, got %d", len(results))
	}
	if results[0].Name != "A" {
		t.Errorf("Top-1 = %s, want A", results[0].Name)
	}
	if results[0].Score <= 0 {
		t.Errorf("Score = %f, 应该 > 0", results[0].Score)
	}
}

// TestPageRank_TwoNodes 算法测试: A → B
// 期望: B 的 PR > A (因为 B 被 A 引)
func TestPageRank_TwoNodes(t *testing.T) {
	pr := NewPageRank()
	pr.AddEdge("A", "B")
	pr.Compute()

	scores := pr.Scores()
	a, b := scores["A"], scores["B"]

	if b <= a {
		t.Errorf("B (被 A 引) PR=%f 应该 > A=%f", b, a)
	}
	if math.Abs(b-a) < 0.01 {
		t.Errorf("B 比 A 应该明显高, got A=%f B=%f", a, b)
	}
}

// TestPageRank_Cycle 算法测试: A→B→A 环
func TestPageRank_Cycle(t *testing.T) {
	pr := NewPageRank()
	pr.AddEdge("A", "B")
	pr.AddEdge("B", "A")
	pr.Compute()

	scores := pr.Scores()
	if math.Abs(scores["A"]-scores["B"]) > 1e-6 {
		t.Errorf("环上 PR 应该相等 (对称), got A=%f B=%f", scores["A"], scores["B"])
	}
}

// TestPageRank_HubAuthority 算法测试: Hub 和 Authority (经典 PageRank 用例)
//
// 拓扑:
//   T1 (权威) ← T2 ← T3 ← T4 (4 个 hub 都引 T1)
//   T1 ← T5
// 期望: T1 是顶, T2-T5 在中 (high in-degree)
func TestPageRank_HubAuthority(t *testing.T) {
	pr := NewPageRank()
	// 4 个 hub 都引 T1 (T1 是核心权威)
	pr.AddEdge("T2", "T1")
	pr.AddEdge("T3", "T1")
	pr.AddEdge("T4", "T1")
	pr.AddEdge("T5", "T1")
	// T1 不引任何 (pure authority)
	pr.Compute()

	scores := pr.Scores()
	if math.IsNaN(scores["T1"]) {
		t.Fatalf("T1 score = NaN, 算法有误")
	}
	for _, h := range []string{"T2", "T3", "T4", "T5"} {
		if scores[h] >= scores["T1"] {
			t.Errorf("Hub %s PR=%f 应该 < Authority T1 PR=%f (T1 被 4 引)",
				h, scores[h], scores["T1"])
		}
	}
}

// TestPageRank_DanglingNode 算法测试: 出度为 0 的节点 (dangling)
func TestPageRank_DanglingNode(t *testing.T) {
	pr := NewPageRank()
	pr.AddEdge("A", "B") // A 引 B
	pr.AddEdge("B", "C") // B 引 C
	// C 是 dangling (不出边)
	pr.Compute()

	scores := pr.Scores()
	if scores["C"] <= 0 {
		t.Errorf("C (dangling) 应该仍有非零 PR (从 dangling 漂移), got %f", scores["C"])
	}
}

// TestPageRank_TopK 算法测试: TopK 排序正确
func TestPageRank_TopK(t *testing.T) {
	pr := NewPageRank()
	// T1 被 5 个节点引
	for _, node := range []string{"A", "B", "C", "D", "E"} {
		pr.AddEdge(node, "T1")
	}
	// T2 被 2 个引
	pr.AddEdge("A", "T2")
	pr.AddEdge("B", "T2")
	// T3 = 普通
	pr.Compute()

	results := pr.TopK(3)
	if len(results) != 3 {
		t.Fatalf("TopK(3) 应该返回 3, got %d", len(results))
	}

	// Top-1 应该是 T1 (5 个引用)
	if results[0].Name != "T1" {
		t.Errorf("Top-1 = %s, want T1", results[0].Name)
	}

	// 算法: TopK 应该按 PR 降序
	for i := 1; i < len(results); i++ {
		if results[i].Score > results[i-1].Score {
			t.Errorf("TopK 排序错: [%d].Score=%f > [%d].Score=%f",
				i, results[i].Score, i-1, results[i-1].Score)
		}
	}
}

// TestPageRank_Convergence 算法测试: 收敛
func TestPageRank_Convergence(t *testing.T) {
	pr := NewPageRank()
	pr.AddEdge("A", "B")
	pr.AddEdge("B", "C")
	pr.AddEdge("C", "A")
	pr.Compute()

	pr2 := NewPageRank()
	pr2.Iterations = 1000 // 极端大
	pr2.AddEdge("A", "B")
	pr2.AddEdge("B", "C")
	pr2.AddEdge("C", "A")
	pr2.Compute()

	// 算法: 收敛后, 不同 iter 数应该产出相似分数
	s1 := pr.Scores()
	s2 := pr2.Scores()
	for name := range s1 {
		diff := math.Abs(s1[name] - s2[name])
		if diff > 0.05 {
			t.Errorf("Convergence 失败: %s 50 iter=%f vs 1000 iter=%f (diff=%f)",
				name, s1[name], s2[name], diff)
		}
	}
}

// TestPageRank_Stats 算法测试: 状态输出
func TestPageRank_Stats(t *testing.T) {
	pr := NewPageRank()
	pr.AddEdge("A", "B")
	pr.AddEdge("A", "C")
	pr.AddEdge("B", "D")
	pr.Compute()

	s := pr.Stats()
	if s.Nodes != 4 {
		t.Errorf("Nodes = %d, want 4", s.Nodes)
	}
	if s.Edges != 3 {
		t.Errorf("Edges = %d, want 3", s.Edges)
	}
}
