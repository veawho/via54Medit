// Package source — Bayesian state 序列化 (Phase 5.1 算法驱动, 2026-07-29)
//
// 跨设备 deterministic 保证: Bayesian update 状态序列化到 ~/.medit/cache/bayesian_state.json
// 之前每次跑重算 → 现在 commit + load, 同输入同输出

package source

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
)

// BayesianState 是 cron scheduler 的 Beta(α, β) 状态
// 算法: Beta(α + ok, β + err) 决定下次跑概率
type BayesianState struct {
	mu sync.Mutex

	// Per-job Beta distribution
	Jobs map[string]*BetaParams `json:"jobs"`
}

// BetaParams 是 Beta 分布的 α + β 参数
type BetaParams struct {
	Alpha float64 `json:"alpha"` // 成功先验 + 成功次数
	Beta  float64 `json:"beta"`  // 失败先验 + 失败次数
}

// DefaultAlpha/Beta 是 Beta(1, 1) prior (uniform)
const (
	DefaultAlpha = 1.0
	DefaultBeta  = 1.0
)

// NewBayesianState 创建一个空状态
func NewBayesianState() *BayesianState {
	return &BayesianState{
		Jobs: make(map[string]*BetaParams),
	}
}

// GetOrCreate 算法: 拿 job 的 BetaParams (lazy init)
func (bs *BayesianState) GetOrCreate(jobName string) *BetaParams {
	bs.mu.Lock()
	defer bs.mu.Unlock()
	if bs.Jobs[jobName] == nil {
		bs.Jobs[jobName] = &BetaParams{
			Alpha: DefaultAlpha,
			Beta:  DefaultBeta,
		}
	}
	return bs.Jobs[jobName]
}

// RecordSuccess 算法: 成功 +1 (Beta α +1)
func (bs *BayesianState) RecordSuccess(jobName string) {
	p := bs.GetOrCreate(jobName)
	p.Alpha++
}

// RecordFail 算法: 失败 +1 (Beta β +1)
func (bs *BayesianState) RecordFail(jobName string) {
	p := bs.GetOrCreate(jobName)
	p.Beta++
}

// ExpectedSuccess 算法: Beta 期望 = α / (α + β)
func (bs *BayesianState) ExpectedSuccess(jobName string) float64 {
	p := bs.GetOrCreate(jobName)
	return p.Alpha / (p.Alpha + p.Beta)
}

// ShouldRun 算法: Beta 期望 >= threshold 决定是否跑
func (bs *BayesianState) ShouldRun(jobName string, minProb float64) bool {
	return bs.ExpectedSuccess(jobName) >= minProb
}

// ══════════════════════════════════════════════════════════════════════
// 持久化算法 (跨设备 deterministic)
// ══════════════════════════════════════════════════════════════════════

// statePath 是 Bayesian state 默认存储位置
func statePath() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".medit/cache/bayesian_state.json")
}

// LoadBayesianState 算法: 从 JSON 加载 Bayesian state
// 跨设备: 同一 JSON → 同一状态
func LoadBayesianState() (*BayesianState, error) {
	data, err := os.ReadFile(statePath())
	if err != nil {
		if os.IsNotExist(err) {
			// 文件不存在 → 新建空状态
			return NewBayesianState(), nil
		}
		return nil, fmt.Errorf("load bayesian state: %w", err)
	}
	var bs BayesianState
	if err := json.Unmarshal(data, &bs); err != nil {
		return nil, fmt.Errorf("unmarshal bayesian state: %w", err)
	}
	if bs.Jobs == nil {
		bs.Jobs = make(map[string]*BetaParams)
	}
	return &bs, nil
}

// Save 算法: 序列化到 JSON (commit 模式)
func (bs *BayesianState) Save() error {
	bs.mu.Lock()
	defer bs.mu.Unlock()
	// 算法: atomic write (temp file + rename)
	tmp := statePath() + ".tmp"
	data, err := json.MarshalIndent(bs, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal bayesian state: %w", err)
	}
	if err := os.WriteFile(tmp, data, 0o644); err != nil {
		return fmt.Errorf("write tmp: %w", err)
	}
	if err := os.Rename(tmp, statePath()); err != nil {
		return fmt.Errorf("rename: %w", err)
	}
	return nil
}

// SaveBayesianState 是便捷包装
func SaveBayesianState(bs *BayesianState) error {
	return bs.Save()
}

// ══════════════════════════════════════════════════════════════════════
// MirrorStats 序列化 (sci_hub 跨设备)
// ══════════════════════════════════════════════════════════════════════

// MirrorStatsSnapshot 是 mirror 健康度的快照 (跨设备 deterministic)
type MirrorStatsSnapshot struct {
	Timestamp int64                            `json:"timestamp"`
	Mirrors   map[string]*MirrorHealthSnapshot `json:"mirrors"`
}

// MirrorHealthSnapshot 是单个 mirror 健康度快照
type MirrorHealthSnapshot struct {
	SuccessCount int     `json:"success_count"`
	FailCount    int     `json:"fail_count"`
	LatencyMS    int64   `json:"latency_ms"`
	HealthScore  float64 `json:"health_score"`
}

// snapshotPath 是 mirror stats 默认存储位置
func snapshotPath() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".medit/cache/mirror_stats.json")
}

// LoadMirrorStatsSnapshot 算法: 从 JSON 加载 mirror 健康度
func LoadMirrorStatsSnapshot() (*MirrorStatsSnapshot, error) {
	data, err := os.ReadFile(snapshotPath())
	if err != nil {
		if os.IsNotExist(err) {
			return &MirrorStatsSnapshot{
				Timestamp: 0,
				Mirrors:   make(map[string]*MirrorHealthSnapshot),
			}, nil
		}
		return nil, fmt.Errorf("load mirror stats: %w", err)
	}
	var snap MirrorStatsSnapshot
	if err := json.Unmarshal(data, &snap); err != nil {
		return nil, fmt.Errorf("unmarshal mirror stats: %w", err)
	}
	if snap.Mirrors == nil {
		snap.Mirrors = make(map[string]*MirrorHealthSnapshot)
	}
	return &snap, nil
}

// Save 算法: 序列化到 JSON (atomic write)
func (s *MirrorStatsSnapshot) Save() error {
	tmp := snapshotPath() + ".tmp"
	data, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal mirror stats: %w", err)
	}
	if err := os.WriteFile(tmp, data, 0o644); err != nil {
		return fmt.Errorf("write tmp: %w", err)
	}
	return os.Rename(tmp, snapshotPath())
}

// Update 算法: 更新单个 mirror 的健康度
func (s *MirrorStatsSnapshot) Update(mirror string, success bool, latencyMS int64) {
	if s.Mirrors == nil {
		s.Mirrors = make(map[string]*MirrorHealthSnapshot)
	}
	if s.Mirrors[mirror] == nil {
		s.Mirrors[mirror] = &MirrorHealthSnapshot{}
	}
	m := s.Mirrors[mirror]
	if success {
		m.SuccessCount++
	} else {
		m.FailCount++
	}
	// 算法: EWMA alpha=0.3
	if m.LatencyMS == 0 {
		m.LatencyMS = latencyMS
	} else {
		m.LatencyMS = int64(0.7*float64(m.LatencyMS) + 0.3*float64(latencyMS))
	}
	// 算法: health score = 命中率 × latency penalty
	total := m.SuccessCount + m.FailCount
	if total > 0 {
		hits := float64(m.SuccessCount) / float64(total)
		penalty := 1.0 / (1.0 + float64(m.LatencyMS)/1000.0)
		m.HealthScore = hits * penalty
	}
}
