// Package authority — PageRank 跨 P 目录 (Phase 7 算法驱动, 2026-07-29)
//
// Aider Repo Map 风格:
//   1. 用 universal-ctags 抽 P 目录函数名 / 类名
//   2. 构 graph (节点 = 函数, 边 = 调用关系)
//   3. PageRank 迭代排序, 选 top N 进 context
//
// via54Medit 适配:
//   - 节点 = 论文 (DOI / PMID / Row)
//   - 边 = 引用关系 (paper A 引用 paper B)
//   - PageRank = 该 Row 在医学领域的权威度
//
// 跨设备 deterministic: 固定 damping + 固定迭代次数 → 同输入同输出

package authority

import (
	"math"
	"sort"
	"sync"
)

// PageRank 是论文引用图 PageRank 算法
type PageRank struct {
	mu sync.Mutex

	// 配置
	Damping    float64 // 阻尼系数 (典型 0.85)
	Iterations int     // 迭代次数 (典型 50)
	Tolerance  float64 // 收敛阈值

	// 数据
	nodes []string         // 节点 ID → 名字
	idx   map[string]int   // 名字 → 索引
	edges [][]int          // 出边邻接表
	score []float64        // PageRank 分数
}

// NewPageRank 创建 PageRank (默认 damping=0.85, iter=50, tol=1e-6)
func NewPageRank() *PageRank {
	return &PageRank{
		Damping:    0.85,
		Iterations: 50,
		Tolerance:  1e-6,
		idx:        make(map[string]int),
		edges:      make([][]int, 0),
		score:      make([]float64, 0),
	}
}

// AddNode 算法: 加节点 (幂等)
func (pr *PageRank) AddNode(name string) int {
	pr.mu.Lock()
	defer pr.mu.Unlock()
	if id, ok := pr.idx[name]; ok {
		return id
	}
	id := len(pr.nodes)
	pr.idx[name] = id
	pr.nodes = append(pr.nodes, name)
	pr.edges = append(pr.edges, []int{})
	pr.score = append(pr.score, 0.0)
	return id
}

// AddEdge 算法: 加有向边 from → to (论文 A 引用 B, 表示 A→B)
func (pr *PageRank) AddEdge(from, to string) {
	fromID := pr.AddNode(from)
	toID := pr.AddNode(to)
	pr.mu.Lock()
	defer pr.mu.Unlock()
	pr.edges[fromID] = append(pr.edges[fromID], toID)
}

// Compute 算法: 跑 PageRank 迭代
// 公式: PR(p) = (1-d)/N + d * Σ(PR(q)/L(q) for q→p)
//   - d = Damping (0.85)
//   - N = 总节点数
//   - L(q) = q 的出度
// O(Iterations × Edges)
func (pr *PageRank) Compute() {
	pr.mu.Lock()
	defer pr.mu.Unlock()

	n := len(pr.nodes)
	if n == 0 {
		return
	}

	// 算法: 初始化 PR = 1/N (均匀)
	newScore := make([]float64, n)
	for i := range newScore {
		newScore[i] = 1.0 / float64(n)
	}

	for iter := 0; iter < pr.Iterations; iter++ {
		// 算法: 算出度总和 (处理 dangling nodes)
		var sumDangling float64
		for i, e := range pr.edges {
			if len(e) == 0 {
				// dangling: 只贡献 (1-d)/N
				continue
			}
			_ = i
		}
		_ = sumDangling // 简化版不用 dangling 处理

		// 算法: PageRank 核心公式
		for i := 0; i < n; i++ {
			newScore[i] = (1.0 - pr.Damping) / float64(n)
			// 求所有指向 i 的节点 q 的贡献
			for q, qEdges := range pr.edges {
				if len(qEdges) == 0 {
					continue
				}
				// 算法: q 的 PR 分摊给所有 L(q) 个 out-edges
				contribution := pr.score[q] / float64(len(qEdges))
				for _, target := range qEdges {
					if target == i {
						newScore[i] += pr.Damping * contribution
						break
					}
				}
			}
		}

		// 算法: 检查收敛 (max diff < Tolerance → 提前终止)
		maxDiff := 0.0
		for i := 0; i < n; i++ {
			diff := math.Abs(newScore[i] - pr.score[i])
			if diff > maxDiff {
				maxDiff = diff
			}
		}
		copy(pr.score, newScore)
		if maxDiff < pr.Tolerance {
			break
		}
	}
	_ = newScore
}

// TopK 算法: 返回 top K 节点按 PR 降序
// 结果: [(node_id, name, score), ...]
type Ranked struct {
	ID    int
	Name  string
	Score float64
}

func (pr *PageRank) TopK(k int) []Ranked {
	pr.mu.Lock()
	defer pr.mu.Unlock()

	n := len(pr.nodes)
	if k > n {
		k = n
	}

	results := make([]Ranked, n)
	for i := 0; i < n; i++ {
		results[i] = Ranked{ID: i, Name: pr.nodes[i], Score: pr.score[i]}
	}

	sort.Slice(results, func(i, j int) bool {
		return results[i].Score > results[j].Score
	})

	return results[:k]
}

// Scores 算法: 返回所有节点 score
func (pr *PageRank) Scores() map[string]float64 {
	pr.mu.Lock()
	defer pr.mu.Unlock()
	out := make(map[string]float64, len(pr.nodes))
	for i, name := range pr.nodes {
		out[name] = pr.score[i]
	}
	return out
}

// Stats 是 PageRank 状态
type Stats struct {
	Nodes int `json:"nodes"`
	Edges int `json:"edges"`
}

// Stats 算法: 返回状态
func (pr *PageRank) Stats() Stats {
	pr.mu.Lock()
	defer pr.mu.Unlock()
	edges := 0
	for _, e := range pr.edges {
		edges += len(e)
	}
	return Stats{
		Nodes: len(pr.nodes),
		Edges: edges,
	}
}
