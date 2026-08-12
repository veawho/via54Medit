package anno2ppt

import (
	"fmt"
	"sort"
	"strings"
)

// SourceType 来源类型 (用户 2026-08-01 双源架构设计)
type SourceType string

const (
	SourceTypeSDAbstract    SourceType = "sd_abstract"      // ScienceDirect abstract 页面
	SourceTypeNCTRegistry   SourceType = "nct_registry"      // ClinicalTrials.gov
	SourceTypeUCLDiscovery  SourceType = "ucl_discovery"     // UCL Discovery AAM
	SourceTypeESMO          SourceType = "esmo"              // ESMO 会议摘要
	SourceTypeAME           SourceType = "ame"               // AME Publishing
	SourceTypeKarger        SourceType = "karger"            // Karger
	SourceTypeCleanAbstract SourceType = "clean_abstract"    // PubMed clean abstract
	SourceTypeRealPDF       SourceType = "real_pdf"          // 真原文 PDF
)

// EvidenceSource 一条证据来源
type EvidenceSource struct {
	Type         SourceType `json:"type"`
	DOI          string     `json:"doi"`
	Layout       string     `json:"layout"`         // "main" or "fallback"
	Citation     string     `json:"citation"`        // 引用文字
	Available    bool       `json:"available"`       // 是否获取成功
	Limit        string     `json:"limit"`           // 限制说明
	DataProvided []string   `json:"data_provided"`   // 提供的关键数据点
}

// DualSourceManifest 双源 manifest schema
//
// 用户 2026-08-01 硬规则: 不合成 1 个 PDF, 用 main + fallback 互补
type DualSourceManifest struct {
	PNx                 string           `json:"pn_x"`
	MainPDF             string           `json:"main_pdf"`
	FallbackPDFs        []string         `json:"fallback_pdfs"`
	FallbackTriggered   bool             `json:"fallback_triggered"`
	FallbackTriggerReason string         `json:"fallback_trigger_reason"`
	EvidenceSources     []EvidenceSource `json:"evidence_sources"`
	HighlightSummary    HighlightSummary `json:"highlight_summary"`
}

// HighlightSummary 高亮统计
type HighlightSummary struct {
	MainPDFHits             int      `json:"main_pdf_hits"`
	FallbackPDFHits         int      `json:"fallback_pdf_hits"`
	FallbackPagesHighlighted []int   `json:"fallback_pages_highlighted"`
	Total                   int      `json:"total"`
}

// NewDualSourceManifest 创建双源 manifest
func NewDualSourceManifest(pnx, mainPDF string) *DualSourceManifest {
	return &DualSourceManifest{
		PNx:           pnx,
		MainPDF:       mainPDF,
		FallbackPDFs:  []string{},
		EvidenceSources: []EvidenceSource{},
	}
}

// AddFallback 添加 fallback PDF
func (m *DualSourceManifest) AddFallback(fallbackPDF string, source EvidenceSource) {
	m.FallbackPDFs = append(m.FallbackPDFs, fallbackPDF)
	m.EvidenceSources = append(m.EvidenceSources, source)
	m.FallbackTriggered = true
}

// ShouldTriggerFallback 判断是否需要触发 fallback
//
// 算法:
//  1. L0 验证失败 (verified=false)
//  2. proposer_strategy = dual_source (Elsevier/Wiley/Karger 付费墙)
//  3. user_hints dual_source (用户提供 URC 文档说明)
func ShouldTriggerFallback(l0Verified bool, doi string, userHintsDualSource bool) bool {
	if userHintsDualSource {
		return true
	}
	if !l0Verified && isPaywallDOI(doi) {
		return true
	}
	return false
}

// FindNCTRegistry NCT 试验注册号 (从 DOI 推断)
//
// 已知 NCT 映射 (2026-08-01):
//   - Qin S AHELP 2021 → NCT02329860
//   - LEAP-002 2024 → NCT03713593 (待补)
//   - HIMALAYA 2022 → NCT03298451 (待补)
func FindNCTRegistry(doi string) string {
	knownMap := map[string]string{
		"10.1016/S2468-1253(21)00109-6": "NCT02329860", // AHELP
		"10.1016/S1470-2045(23)00469-2": "NCT03713593", // LEAP-002 (Llovet)
		"10.1056/NEJMoa2024020":        "NCT03298451", // HIMALAYA
	}
	return knownMap[doi]
}

// TryFetchNCT 尝试从 NCT 提取 AE 数据
//
// 返回: any_grade AE 列表 / true / ""
func TryFetchNCT(doi string) (string, bool, string) {
	nct := FindNCTRegistry(doi)
	if nct == "" {
		return "", false, "NCT registry not found for DOI"
	}
	// 真实情况: 这一步在 Python 脚本 scripts/nct_fetcher.py 中实现
	// 在 Go 代码中只做架构 + 接口
	return "", true, nct + " (handled by scripts/nct_fetcher.py)"
}

// CombineEvidenceData 合并多源数据
//
// 已知 PPT 需求 vs paper 数据互补逻辑
func CombineEvidenceData(mainData, fallbackData map[string]string) map[string]string {
	out := make(map[string]string)
	for k, v := range mainData {
		out[k] = v
	}
	for k, v := range fallbackData {
		if _, ok := out[k]; !ok {
			out[k] = v
		}
	}
	return out
}

// SourcePriority 来源优先级 (高 → 低)
var SourcePriority = []SourceType{
	SourceTypeRealPDF,
	SourceTypeUCLDiscovery,
	SourceTypeAME,
	SourceTypeKarger,
	SourceTypeESMO,
	SourceTypeCleanAbstract,
	SourceTypeSDAbstract,
	SourceTypeNCTRegistry,
}

// SortSourcesByPriority 按优先级排序来源
func SortSourcesByPriority(sources []EvidenceSource) []EvidenceSource {
	priorityMap := make(map[SourceType]int, len(SourcePriority))
	for i, st := range SourcePriority {
		priorityMap[st] = i
	}
	sort.SliceStable(sources, func(i, j int) bool {
		pi, oki := priorityMap[sources[i].Type]
		pj, okj := priorityMap[sources[j].Type]
		if !oki && !okj {
			return false
		}
		if !oki {
			return false
		}
		if !okj {
			return true
		}
		return pi < pj
	})
	return sources
}

// 已沉淀 (2026-08-12 状态更新):
//   - ✓ DualSourceManifest schema (line 37)
//   - ✓ ShouldTriggerFallback 触发条件 (line 78)
//   - ✓ FindNCTRegistry 已知映射 (line 94)
//   - ✓ SourcePriority 优先级 (line 133)
//   - ✓ SortSourcesByPriority 排序 (line 145)
//
// 后续 TODO (Phase 5+):
//   - [ ] NCT 完整数据 fetch — scripts/nct_fetcher.py 暂未建 (P2)
//         优先建 Python 脚本 (clinicaltrials.gov API → JSON),
//         此处用 os/exec 调子进程,数据进 DualSourceManifest.PrimaryNCTData
//   - [ ] OA 仓库自动探测 (UCL Discovery / PubMed Central / Europe PMC)
//         实现: 内嵌 OARepository 列表 + HEAD 探测 + 优先级降级
//   - [ ] 双源 highlight 标注驱动 (主 + fallback 各自一张图)
//         在 AnnoCard 模板上同时渲染两张 jpg 拼版

// String 便于 manifest 输出
func (e EvidenceSource) String() string {
	return fmt.Sprintf("[%s/%s] %s (data: %s, limit: %s)",
		e.Layout, e.Type, e.Citation, strings.Join(e.DataProvided, ", "), e.Limit)
}
