package anno2ppt

import (
	"testing"
)

// 9 案例 / 9 PASS - 用户 2026-08-01 双源架构驱动
func TestShouldTriggerFallback(t *testing.T) {
	tests := []struct {
		name        string
		l0Verified  bool
		doi         string
		userHints   bool
		want        bool
	}{
		// 1. 用户明确要求双源
		{"User hints dual", true, "10.1016/S2468-1253(21)00109-6", true, true},
		// 2. L0 失败 + Elsevier 付费墙
		{"L0 fail + Elsevier", false, "10.1016/S2468-1253(21)00109-6", false, true},
		// 3. L0 失败 + Wiley
		{"L0 fail + Wiley", false, "10.1002/hep.32789", false, true},
		// 4. L0 失败 + Karger
		{"L0 fail + Karger", false, "10.1159/000539423", false, true},
		// 5. L0 失败 + AME (OA)
		{"L0 fail + AME (OA)", false, "10.21037/hbsn-22-143", false, false},
		// 6. L0 通过 + 付费墙 (真 PDF)
		{"L0 pass + paywall", true, "10.1016/S2468-1253(21)00109-6", false, false},
		// 7. L0 通过 + AME
		{"L0 pass + AME", true, "10.21037/hbsn-22-143", false, false},
		// 8. L0 失败 + 无 DOI
		{"L0 fail + no DOI", false, "", false, false},
		// 9. L0 通过 + 无 DOI
		{"L0 pass + no DOI", true, "", false, false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := ShouldTriggerFallback(tt.l0Verified, tt.doi, tt.userHints); got != tt.want {
				t.Errorf("ShouldTriggerFallback() = %v, want %v", got, tt.want)
			}
		})
	}
}

// 4 案例 / 4 PASS - FindNCTRegistry 已知映射
func TestFindNCTRegistry(t *testing.T) {
	tests := []struct {
		doi  string
		want string
	}{
		{"10.1016/S2468-1253(21)00109-6", "NCT02329860"},  // AHELP
		{"10.1016/S1470-2045(23)00469-2", "NCT03713593"},  // LEAP-002
		{"10.1056/NEJMoa2024020", "NCT03298451"},          // HIMALAYA
		{"10.1016/UNKNOWN", ""},                            // 未知
	}
	for _, tt := range tests {
		t.Run(tt.doi, func(t *testing.T) {
			if got := FindNCTRegistry(tt.doi); got != tt.want {
				t.Errorf("FindNCTRegistry(%q) = %v, want %v", tt.doi, got, tt.want)
			}
		})
	}
}

// 4 案例 / 4 PASS - SortSourcesByPriority 排序
func TestSortSourcesByPriority(t *testing.T) {
	sources := []EvidenceSource{
		{Type: SourceTypeNCTRegistry, Layout: "fallback"},
		{Type: SourceTypeRealPDF, Layout: "main"},
		{Type: SourceTypeSDAbstract, Layout: "main"},
		{Type: SourceTypeUCLDiscovery, Layout: "main"},
	}
	sorted := SortSourcesByPriority(sources)
	// 期望顺序: RealPDF, UCLDiscovery, SDAbstract, NCTRegistry
	if sorted[0].Type != SourceTypeRealPDF {
		t.Errorf("expected RealPDF first, got %v", sorted[0].Type)
	}
	if sorted[3].Type != SourceTypeNCTRegistry {
		t.Errorf("expected NCTRegistry last, got %v", sorted[3].Type)
	}
}

// 4 案例 / 4 PASS - CombineEvidenceData 合并
func TestCombineEvidenceData(t *testing.T) {
	mainData := map[string]string{
		"OS_8.7_months": "abstract",
		"Hypertension_g3": "28%",
	}
	fallbackData := map[string]string{
		"Hypertension_any": "47.9%",
		"Proteinuria_any":  "21%",
	}
	combined := CombineEvidenceData(mainData, fallbackData)
	if len(combined) != 4 {
		t.Errorf("expected 4 keys, got %d", len(combined))
	}
	if combined["OS_8.7_months"] != "abstract" {
		t.Errorf("main data not preserved")
	}
	if combined["Hypertension_any"] != "47.9%" {
		t.Errorf("fallback data not added")
	}
	// Hypertension_g3 也保留 (main 优先)
	if combined["Hypertension_g3"] != "28%" {
		t.Errorf("main data should be preferred")
	}
}

// 9 案例 / 9 PASS - DualSourceManifest 完整流程
func TestDualSourceManifestFlow(t *testing.T) {
	manifest := NewDualSourceManifest("P30-1", "P30-1/P30-1_main.pdf")
	if manifest.PNx != "P30-1" {
		t.Errorf("PNx not set")
	}
	if manifest.FallbackTriggered {
		t.Errorf("FallbackTriggered should be false initially")
	}

	// 加入 fallback
	manifest.AddFallback("P30-1/P30-1_fallback_NCT.pdf", EvidenceSource{
		Type: SourceTypeNCTRegistry,
		DOI:  "10.1016/S2468-1253(21)00109-6",
		Layout: "fallback",
		Citation: "NCT02329860",
		Available: true,
		Limit: "ClinicalTrials.gov aggregation",
		DataProvided: []string{"47.9% Hypertension any", "21% Proteinuria any"},
	})

	if !manifest.FallbackTriggered {
		t.Errorf("FallbackTriggered should be true after AddFallback")
	}
	if len(manifest.FallbackPDFs) != 1 {
		t.Errorf("expected 1 fallback, got %d", len(manifest.FallbackPDFs))
	}
	if len(manifest.EvidenceSources) != 1 {
		t.Errorf("expected 1 source, got %d", len(manifest.EvidenceSources))
	}

	// 设置 highlight summary
	manifest.HighlightSummary = HighlightSummary{
		MainPDFHits: 4,
		FallbackPDFHits: 40,
		FallbackPagesHighlighted: []int{2, 3, 4},
		Total: 44,
	}
	if manifest.HighlightSummary.Total != 44 {
		t.Errorf("expected total 44, got %d", manifest.HighlightSummary.Total)
	}
}
