package similarity

import (
	"math"
	"testing"
)

// TestHNSW_InsertSingle 算法测试: 单节点插入
func TestHNSW_InsertSingle(t *testing.T) {
	h := NewHNSW()
	h.Insert(0, []float64{1, 0, 0})
	if h.Stats().Nodes != 1 {
		t.Errorf("Nodes after 1 insert = %d, want 1", h.Stats().Nodes)
	}
}

// TestHNSW_SearchExact 算法测试: 完全匹配检索
func TestHNSW_SearchExact(t *testing.T) {
	h := NewHNSW()
	// 插入 10 个 3 维向量
	for i := 0; i < 10; i++ {
		vec := []float64{float64(i), float64(i * 2), 0}
		h.Insert(i, vec)
	}

	// 查询完全匹配
	ids, dists := h.SearchK([]float64{3, 6, 0}, 3)
	if len(ids) == 0 {
		t.Errorf("SearchK 应该返回结果")
	}

	// 算法: (3,6,0) 与 (i,2i,0) 同方向, CosineDistance 都 = 0, top-N 都在 (i,2i,0)
	if dists[0] > 0.001 {
		t.Errorf("Top-1 distance = %f, 应该 ≤ 0.001 (同方向)", dists[0])
	}
}

// TestHNSW_Performance 算法测试: 1K 节点下性能 (Aider benchmark)
func TestHNSW_Performance(t *testing.T) {
	h := NewHNSW()
	// 插入 1K 节点
	for i := 0; i < 1000; i++ {
		vec := make([]float64, 128)
		for j := range vec {
			vec[j] = float64((i + j) % 100) / 100.0
		}
		h.Insert(i, vec)
	}
	if h.Stats().Nodes != 1000 {
		t.Errorf("Nodes = %d, want 1000", h.Stats().Nodes)
	}

	// 检索
	query := make([]float64, 128)
	for j := range query {
		query[j] = 0.5
	}
	ids, dists := h.SearchK(query, 10)
	if len(ids) != 10 {
		t.Errorf("SearchK 应该返回 10 个结果, got %d", len(ids))
	}

	// 距离应该递增
	for i := 1; i < len(dists); i++ {
		if dists[i] < dists[i-1] {
			t.Errorf("距离应该递增, got dists[%d]=%f < dists[%d]=%f",
				i, dists[i], i-1, dists[i-1])
		}
	}
}

// TestCosineDistance 算法测试: 余弦距离基础
func TestCosineDistance(t *testing.T) {
	// 完全相同 → 距离 0
	d := CosineDistance([]float64{1, 0}, []float64{1, 0})
	if d > 1e-9 {
		t.Errorf("CosineDistance 相同向量应该 = 0, got %f", d)
	}

	// 垂直 → 距离 1
	d = CosineDistance([]float64{1, 0}, []float64{0, 1})
	if math.Abs(d-1.0) > 1e-9 {
		t.Errorf("CosineDistance 垂直向量应该 = 1, got %f", d)
	}

	// 相反 → 距离 2
	d = CosineDistance([]float64{1, 0}, []float64{-1, 0})
	if math.Abs(d-2.0) > 1e-9 {
		t.Errorf("CosineDistance 相反向量应该 = 2, got %f", d)
	}

	// 不同维度 → MaxFloat64
	d = CosineDistance([]float64{1, 0}, []float64{1, 0, 0})
	if d != math.MaxFloat64 {
		t.Errorf("CosineDistance 不同维度应该 = MaxFloat64, got %f", d)
	}

	// 零向量
	d = CosineDistance([]float64{0, 0}, []float64{1, 0})
	if d != 1.0 {
		t.Errorf("CosineDistance 零向量应该 = 1, got %f", d)
	}
}

// TestEuclideanDistance 算法测试: 欧氏距离
func TestEuclideanDistance(t *testing.T) {
	d := EuclideanDistance([]float64{0, 0}, []float64{3, 4})
	if math.Abs(d-5.0) > 1e-9 {
		t.Errorf("EuclideanDistance (3,4) 应该 = 5, got %f", d)
	}

	d = EuclideanDistance([]float64{1, 0}, []float64{1, 0})
	if d > 1e-9 {
		t.Errorf("EuclideanDistance 相同应该 = 0, got %f", d)
	}
}

// TestHNSW_Deterministic 算法测试: 跨设备确定性 (固定 seed → 同结果)
func TestHNSW_Deterministic(t *testing.T) {
	// 创建 2 个 HNSW (固定 seed)
	h1 := NewHNSW()
	h2 := NewHNSW()

	// 同样顺序插入
	for i := 0; i < 20; i++ {
		vec := []float64{float64(i) * 0.1, float64(i) * 0.2, float64(i) * 0.3}
		h1.Insert(i, vec)
		h2.Insert(i, vec)
	}

	// 同样查询
	q := []float64{0.5, 1.0, 1.5}
	ids1, dists1 := h1.SearchK(q, 5)
	ids2, dists2 := h2.SearchK(q, 5)

	if len(ids1) != len(ids2) {
		t.Errorf("Deterministic 失败: 长度不同")
	}
	for i := range ids1 {
		if ids1[i] != ids2[i] {
			t.Errorf("Deterministic 失败: ids[%d] = %d vs %d", i, ids1[i], ids2[i])
		}
		if math.Abs(dists1[i]-dists2[i]) > 1e-9 {
			t.Errorf("Deterministic 失败: dists[%d] = %f vs %f", i, dists1[i], dists2[i])
		}
	}
}

// TestHNSW_EmptySearch 算法测试: 空 HNSW 不崩溃
func TestHNSW_EmptySearch(t *testing.T) {
	h := NewHNSW()
	ids, dists := h.SearchK([]float64{1, 0}, 5)
	if ids != nil || dists != nil {
		t.Errorf("空 HNSW 应该返回 (nil, nil), got (%v, %v)", ids, dists)
	}
}

// TestHNSW_Scaling 算法测试: 缩放性 (10K 节点)
func TestHNSW_Scaling(t *testing.T) {
	if testing.Short() {
		t.Skip("跳过 10K 节点测试")
	}
	h := NewHNSW()
	// 10K 节点
	for i := 0; i < 10000; i++ {
		vec := make([]float64, 32)
		for j := range vec {
			vec[j] = float64((i*7+j*3)%100) / 100.0
		}
		h.Insert(i, vec)
	}
	query := make([]float64, 32)
	for i := range query {
		query[i] = 0.5
	}
	ids, _ := h.SearchK(query, 5)
	if len(ids) != 5 {
		t.Errorf("10K HNSW 检索应该返回 5, got %d", len(ids))
	}
}

// TestHNSW_Stats 算法测试: 状态输出
func TestHNSW_Stats(t *testing.T) {
	h := NewHNSW()
	h.Insert(1, []float64{1, 0})
	h.Insert(2, []float64{0, 1})
	s := h.Stats()
	if s.Nodes != 2 {
		t.Errorf("Stats.Nodes = %d, want 2", s.Nodes)
	}
	if s.Entry == 0 {
		t.Errorf("Stats.Entry 应该非 0")
	}
}
