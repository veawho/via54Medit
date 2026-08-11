package anno2ppt

import (
	"strings"
)

// PDFType PDF 类型分类 (用户 2026-08-01 教训)
//
// v3.9算法把 Chrome 截图和 ReportLab 截图混淆, 同一套 fallback 策略可能不适用.
// 必须先分类, 再选不同修复策略.
type PDFType string

const (
	PDFTypeRealPDF          PDFType = "real_pdf"            // Veeva Vault / Adobe InDesign / Arbortext
	PDFTypeReportLabWrap    PDFType = "reportlab_screenshot" // liangyihui.net 截图包壳
	PDFTypeChromeScreenshot PDFType = "chrome_screenshot"    // Skia/PDF mXXX
	PDFTypeMeetingAbstract  PDFType = "meeting_abstract"    // pdfmake
	PDFTypeOAAMAvailable    PDFType = "oa_am_available"      // UCL Discovery / PubMed Central
	PDFTypeUnknown          PDFType = "unknown"
)

// ProducerBlacklist 黑名单 (判定为截图包壳)
var ProducerBlacklist = []string{
	"ReportLab PDF Library",  // ReportLab 截图包壳
	"WeasyPrint",             // HTML→PDF 包装
	"Skia/PDF",               // Chrome 截屏 (with Mozilla creator)
}

// ProducerWhitelist 白名单 (判定为真 PDF)
var ProducerWhitelist = []string{
	"Veeva Vault",            // ASCO/JCO 会议摘要标准
	"Adobe InDesign",         // 期刊标准排版
	"Adobe PDF Library",      // 期刊标准
	"Arbortext",              // 期刊生成工具
	"Acrobat Distiller",      // 期刊生成工具
	"XPP",                    // Elsevier 工具
	"pdfmake",                // GI Cancer Symp 摘要
}

// ClassifyPDF 根据 producer + creator + 文字层分类 PDF 类型
//
// 算法 (3 步):
//  1. producer 关键词匹配 (blacklist / whitelist)
//  2. creator 关键词匹配 (Mozilla + Skia = Chrome 截图)
//  3. 文字层内容判断 ("Image: fig2.png" = ReportLab, "An official website" = Chrome)
//
// 设计原则: 单维度太弱, 必须 3 步串联验证 (避免占位符假阳性)
func ClassifyPDF(producer, creator, firstPageText string) PDFType {
	// Step 1: Producer 黑名单
	producerLower := strings.ToLower(producer)
	for _, kw := range ProducerBlacklist {
		if strings.Contains(producerLower, strings.ToLower(kw)) {
			if kw == "Skia/PDF" && !strings.Contains(creator, "Mozilla") {
				continue // Skia alone may not be Chrome
			}
			if kw == "ReportLab PDF Library" {
				return PDFTypeReportLabWrap
			}
			if kw == "Skia/PDF" {
				return PDFTypeChromeScreenshot
			}
			return PDFTypeUnknown
		}
	}

	// Step 2: Producer 白名单
	for _, kw := range ProducerWhitelist {
		if strings.Contains(producerLower, strings.ToLower(kw)) {
			if kw == "pdfmake" {
				return PDFTypeMeetingAbstract
			}
			return PDFTypeRealPDF
		}
	}

	// Step 3: 文字层内容判断
	if strings.Contains(firstPageText, "Image: fig2.png") {
		return PDFTypeReportLabWrap
	}
	if strings.Contains(firstPageText, "An official website") {
		return PDFTypeChromeScreenshot
	}
	if strings.Contains(firstPageText, "Page 1 of") && strings.Contains(firstPageText, "ASCO") {
		return PDFTypeMeetingAbstract
	}

	return PDFTypeUnknown
}

// RepairStrategy 修复策略
type RepairStrategy string

const (
	StrategyReplaceWithRealPDF  RepairStrategy = "replace_with_real_pdf"   // 找真原文 PDF (ReportLab)
	StrategyFindOAAm           RepairStrategy = "find_oa_am"              // 找 OA 仓库 (Chrome)
	StrategyUseAbstractAsMain   RepairStrategy = "abstract_as_main"       // 用 abstract (双源架构)
	StrategyKeepAsIs            RepairStrategy = "keep_as_is"             // 真 PDF 无需修
	StrategyInspectManually     RepairStrategy = "inspect_manually"        // 人工判断
)

// RecommendStrategy 根据 PDF 类型推荐修复策略
//
// 用户 2026-08-01 设计:
//   - ReportLab 截图 → 必须找真原文 (与同 DOI 其他 Pn-x 复用)
//   - Chrome 截图 → UCL Discovery / PubMed Central / OA 仓库
//   - 期刊付费墙 → 双源架构 (ScienceDirect abstract + NCT)
//   - 真 PDF → 保持
func RecommendStrategy(pdfType PDFType, doi string) RepairStrategy {
	switch pdfType {
	case PDFTypeReportLabWrap:
		return StrategyReplaceWithRealPDF
	case PDFTypeChromeScreenshot:
		return StrategyFindOAAm
	case PDFTypeUnknown:
		// 兜底: 期刊付费墙 → 双源架构
		if isPaywallDOI(doi) {
			return StrategyUseAbstractAsMain
		}
		return StrategyInspectManually
	default:
		return StrategyKeepAsIs
	}
}

// isPaywallDOI 判断 DOI 是否需要付费墙 (Elsevier/Wiley/Karger)
//
// 简化版: PII 编码识别
//   - S2468-1253 → Lancet Gastroenterol Hepatol (Elsevier)
//   - S1470-2045 → Lancet Oncology (Elsevier)
//   - S0140-6736 → Lancet (Elsevier)
func isPaywallDOI(doi string) bool {
	if doi == "" {
		return false
	}
	lower := strings.ToLower(doi)
	paywallPrefixes := []string{
		"10.1016/",  // Elsevier 通用
		"10.1056/",  // NEJM
		"10.1002/",  // Wiley
		"10.1159/",  // Karger
	}
	for _, p := range paywallPrefixes {
		if strings.HasPrefix(lower, p) {
			return true
		}
	}
	return false
}

// L0ProducerCheck producer 黑白名单快速验证
//
// 返回: (是否可信, 原因)
func L0ProducerCheck(producer, creator string) (bool, string) {
	producerLower := strings.ToLower(producer)
	creatorLower := strings.ToLower(creator)

	// Chrome 截图特殊组合 (Skia/PDF + Mozilla) — 优先于黑名单
	if strings.Contains(producerLower, "skia/pdf") && strings.Contains(creatorLower, "mozilla") {
		return false, "chrome_screenshot_combined"
	}

	// 黑名单 (截图包壳)
	for _, kw := range ProducerBlacklist {
		if strings.Contains(producerLower, strings.ToLower(kw)) {
			return false, "producer_blacklist: " + kw
		}
	}

	// 白名单
	for _, kw := range ProducerWhitelist {
		if strings.Contains(producerLower, strings.ToLower(kw)) {
			return true, "producer_whitelist: " + kw
		}
	}

	// 未知: 需要 L0 score 验证
	return false, "unknown_producer"
}
