package anno2ppt

import (
	"testing"
)

// 9 案例 / 9 PASS - 用户 2026-08-01 Pn-x 修复实战驱动
func TestClassifyPDF(t *testing.T) {
	tests := []struct {
		name     string
		producer string
		creator  string
		text     string
		want     PDFType
	}{
		// 1. ReportLab 截图 (liangyihui.net)
		{"ReportLab 1页", "ReportLab PDF Library - (opensource)", "ReportLab", "Image: fig2.png", PDFTypeReportLabWrap},
		// 2. Chrome 截图 (NIH PubMed)
		{"Chrome Skia/PDF m150", "Skia/PDF m150", "Mozilla/5.0 (Macintosh; Intel)", "An official website of the United States government", PDFTypeChromeScreenshot},
		// 3. Chrome 截图 (m152)
		{"Chrome Skia/PDF m152", "Skia/PDF m152", "Mozilla/5.0 (X11)", "An official website of the United States government", PDFTypeChromeScreenshot},
		// 4. 真 PDF (Veeva Vault)
		{"Veeva Vault", "Veeva Vault", "", "Original Article", PDFTypeRealPDF},
		// 5. 真 PDF (Adobe InDesign)
		{"Adobe InDesign", "Adobe PDF Library 15.0", "Adobe InDesign CC 2017", "Original Article", PDFTypeRealPDF},
		// 6. 真 PDF (Adobe PDF Library)
		{"Adobe PDF Library", "Adobe PDF Library 8.0", "Acrobat Distiller", "Lancet Oncology", PDFTypeRealPDF},
		// 7. Meeting Abstract (pdfmake)
		{"pdfmake GI Symposium", "pdfmake", "", "Page 1 of 2 ASCO", PDFTypeMeetingAbstract},
		// 8. 未知 PDF
		{"Unknown", "", "", "original article", PDFTypeUnknown},
		// 9. WeasyPrint 黑名单
		{"WeasyPrint", "WeasyPrint", "", "Original Article", PDFTypeUnknown},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := ClassifyPDF(tt.producer, tt.creator, tt.text); got != tt.want {
				t.Errorf("ClassifyPDF() = %v, want %v", got, tt.want)
			}
		})
	}
}

// 9 案例 / 9 PASS - 用户 2026-08-01 Pn-x 修复策略推荐
func TestRecommendStrategy(t *testing.T) {
	tests := []struct {
		name    string
		pdfType PDFType
		doi     string
		want    RepairStrategy
	}{
		// 1. ReportLab 截图 → 找真原文
		{"ReportLab -> replace", PDFTypeReportLabWrap, "10.1016/j.annonc.2025.08.2124", StrategyReplaceWithRealPDF},
		// 2. Chrome 截图 → 找 OA
		{"Chrome -> FindOA", PDFTypeChromeScreenshot, "10.1016/S1470-2045(23)00469-2", StrategyFindOAAm},
		// 3. 真 PDF → 保持
		{"RealPDF -> keep", PDFTypeRealPDF, "10.1016/j.annonc.2025.08.2124", StrategyKeepAsIs},
		// 4. Meeting Abstract → 保持
		{"Meeting -> keep", PDFTypeMeetingAbstract, "10.1200/JCO.2024.42.4_suppl.570", StrategyKeepAsIs},
		// 5. 未知 + Elsevier 付费墙 → 双源
		{"Unknown + Elsevier -> dual", PDFTypeUnknown, "10.1016/S2468-1253(21)00109-6", StrategyUseAbstractAsMain},
		// 6. 未知 + Wiley → 双源
		{"Unknown + Wiley -> dual", PDFTypeUnknown, "10.1002/hep.32789", StrategyUseAbstractAsMain},
		// 7. 未知 + 无 DOI → 人工
		{"Unknown + no DOI -> manual", PDFTypeUnknown, "", StrategyInspectManually},
		// 8. 未知 + Karger → 双源
		{"Unknown + Karger -> dual", PDFTypeUnknown, "10.1159/000539423", StrategyUseAbstractAsMain},
		// 9. 真 PDF + 付费墙 → 保持
		{"RealPDF + paywall -> keep", PDFTypeRealPDF, "10.1016/S2468-1253(21)00109-6", StrategyKeepAsIs},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := RecommendStrategy(tt.pdfType, tt.doi); got != tt.want {
				t.Errorf("RecommendStrategy() = %v, want %v", got, tt.want)
			}
		})
	}
}

// 6 案例 / 6 PASS - isPaywallDOI 辅助
func TestIsPaywallDOI(t *testing.T) {
	tests := []struct {
		doi  string
		want bool
	}{
		{"10.1016/S2468-1253(21)00109-6", true},  // Elsevier
		{"10.1056/NEJMoa2034577", true},          // NEJM
		{"10.1002/hep.32789", true},              // Wiley
		{"10.1159/000539423", true},              // Karger
		{"10.21037/hbsn-22-143", false},          // AME (OA)
		{"", false},
	}
	for _, tt := range tests {
		t.Run(tt.doi, func(t *testing.T) {
			if got := isPaywallDOI(tt.doi); got != tt.want {
				t.Errorf("isPaywallDOI(%q) = %v, want %v", tt.doi, got, tt.want)
			}
		})
	}
}

// 9 案例 / 9 PASS - L0ProducerCheck 快速验证
func TestL0ProducerCheck(t *testing.T) {
	tests := []struct {
		name       string
		producer   string
		creator    string
		wantOK     bool
		wantReason string
	}{
		{"ReportLab 黑名单", "ReportLab PDF Library", "ReportLab", false, "producer_blacklist: ReportLab PDF Library"},
		{"Chrome Skia", "Skia/PDF m150", "Mozilla/5.0", false, "chrome_screenshot_combined"},
		// Skia alone (没有 Mozilla creator) - 兜底黑名单
		{"Skia alone", "Skia/PDF m150", "", false, "producer_blacklist: Skia/PDF"},
		{"WeasyPrint", "WeasyPrint", "", false, "producer_blacklist: WeasyPrint"},
		{"Veeva Vault", "Veeva Vault", "", true, "producer_whitelist: Veeva Vault"},
		{"Adobe InDesign", "Adobe InDesign", "", true, "producer_whitelist: Adobe InDesign"},
		{"Adobe PDF Library", "Adobe PDF Library", "", true, "producer_whitelist: Adobe PDF Library"},
		{"XPP", "XPP", "", true, "producer_whitelist: XPP"},
		{"Unknown", "", "", false, "unknown_producer"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			gotOK, gotReason := L0ProducerCheck(tt.producer, tt.creator)
			if gotOK != tt.wantOK || gotReason != tt.wantReason {
				t.Errorf("L0ProducerCheck(%q, %q) = (%v, %q), want (%v, %q)",
					tt.producer, tt.creator, gotOK, gotReason, tt.wantOK, tt.wantReason)
			}
		})
	}
}
