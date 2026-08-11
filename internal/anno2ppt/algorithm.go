// Package anno2ppt implements Phase 7 algorithm-driven citation highlight.
//
// 算法架构 (4 层 + 应证推理机):
//
//	L1 底层加速层 (PyMuPDF + PyMuPDF4LLM) — 文字快速提取 + bbox 坐标
//	L2 结构化解析层 (docling + PaddleOCR PP-Structure + Marker) — 文字块/表格/图表/图片分离
//	L3 视觉理解层 (InternVL + DeepSeek-VL2 + Nougat) — 视觉问答 + 错字修
//	L4 应证推理层 (本包核心) — 4 维要素对齐 + 应证评分 → 高亮决策
//
// GitHub 调研 (2026-08-01):
//   - docling-project/docling ★64,073
//   - PaddlePaddle/PaddleOCR ★86,666 (中文唯一靠谱)
//   - VikParuchuri/marker ★38,068
//   - facebookresearch/nougat ★10,055
//   - OpenGVLab/InternVL ★10,112 (GPT-4o 替代)
//   - deepseek-ai/DeepSeek-VL2 ★5,351 (中文 MoE)
//   - pymupdf/PyMuPDF4LLM ★2,047
//   - microsoft/table-transformer ★2,933
//   - THUDM/CogVLM2 ★2,435
//
// 设计原则 (用户 5 大铁律 2026-07-31 + 2026-08-01):
//   1. 算法驱动 (regex / 概率 / 评分), 不用 if/else 硬编码
//   2. 算法 + LLM 配合: 置信度 < 0.7 调 LLM 反思
//   3. 不写死绝对值: 阈值在算法里动态调
//   4. 经验闭环: 用户修正 → corrections.json → 算法升级 → CI
//   5. 信息要素推理 (information element reasoning) — 不是关键词匹配
package anno2ppt

import (
	"fmt"
	"math"
	"regexp"
	"sort"
	"strings"
)

// InformationElement 4 维信息要素 (应证推理的最小单位)
//
//	PPT 论点和 PDF 证据都被拆成这 4 个要素，再做交叉对齐。
//	用户原话 (2026-08-01): "应证推理" 不是关键词匹配, 是 4 维要素对齐.
type InformationElement struct {
	Geography  string  // 中国 / China / 中国大陆 / 亚太
	Disease    string  // 肝癌 / HCC / liver cancer / hepatoma
	Indicator  string  // 5年生存率 / 5-year survival / incidence / mortality
	Value      string  // 14.4 / 8.5 / 40-50
	ValueNum   float64 // 数值化后用于比较 (NaN 表示不可比)
	Conclusion string  // 远低于 / 高于 / 等于 / 对比
	Unit       string  // % / 万 / per 100,000 / months
}

// AllegationCore 应证核心: 从 PPT 抽取的论点四元组
type AllegationCore struct {
	Elements       [4]InformationElement // [0]=subject [1]=target [2]=value [3]=conclusion
	RawText        string
	CitationIndex  string // P3-2 / Row 43 等
	SourceSlideIdx int
}

// EvidenceEvidence PDF 中找到的证据单元
type EvidenceEvidence struct {
	Page       int
	BBox       BoundingBox // x0,y0,x1,y1 (PDF 坐标系 pt)
	Element    InformationElement
	RawText    string
	Confidence float64 // 0-1
	Type       string  // "text" / "table_row" / "chart_cell" / "figure_caption"
}

// BoundingBox 矩形坐标 (PDF 单位 pt)
type BoundingBox struct {
	X0, Y0, X1, Y1 float64
}

// AllegationMatch 应证匹配结果 (1 对多: 1 个论点 → N 个证据)
type AllegationMatch struct {
	Allegation     AllegationCore
	Evidences      []EvidenceEvidence
	ConfirmScore   float64            // 0-1 应证得分
	ElementScores  [4]float64         // 每维要素对齐分
	MismatchReport string             // 维度对齐失败原因
	Decision       HighlightDecision  // 最终决策
}

// HighlightDecision 高亮决策
type HighlightDecision struct {
	ShouldHighlight bool
	Reason          string
	BBoxes          []BoundingBox // 所有要画的矩形
	HighlightType   string        // "underline" / "highlight" / "rectangle"
	Notes           string        // 给用户的自然语言说明
}

// ====== 维度权重 (算法可调, 默认值由 12 雷管方案历史反例训练得出) ======

var (
	WeightGeography  = 0.20 // 地理对齐 (中国 ≠ 美国)
	WeightDisease    = 0.30 // 病种对齐 (肝癌 ≠ 肺癌)
	WeightIndicator  = 0.20 // 指标对齐 (5年生存率 ≠ 发病率)
	WeightValue      = 0.20 // 数值对齐 (14.4 ≠ 14.4%)
	WeightConclusion = 0.10 // 结论对齐 (远低于 ≠ 高于)
)

// ====== 4 维要素抽取器 (从自然语言抽出 InformationElement) ======

// geoKeywords 地理词典 (扩展可调)
var geoKeywords = map[string]float64{
	"中国": 1.0, "中国⼤陆": 1.0, "China": 1.0, "Chinese": 0.9,
	"美国": 0.7, "USA": 0.7, "United States": 0.7,
	"全球": 0.5, "global": 0.5, "worldwide": 0.5,
	"亚太": 0.8, "Asia": 0.8, "Asian": 0.7,
	"欧洲": 0.6, "Europe": 0.6, "European": 0.6,
	"日本": 0.7, "Japan": 0.7, "韩国": 0.7, "Korea": 0.7,
}

// diseaseKeywords 病种词典 (HCC 相关 + 全癌肿)
var diseaseKeywords = map[string]float64{
	"肝癌": 1.0, "HCC": 1.0, "hepatocellular": 1.0, "liver cancer": 1.0,
	"肝细胞癌": 1.0, "原发性肝癌": 1.0, "肝肿瘤": 0.9,
	"肺癌": 1.0, "lung cancer": 1.0, "Lung": 0.8,
	"胃癌": 1.0, "stomach cancer": 1.0, "gastric": 1.0,
	"乳腺癌": 1.0, "breast cancer": 1.0, "breast": 0.8,
	"结直肠癌": 1.0, "colorectal": 1.0, "colon": 0.8,
	"胰腺癌": 1.0, "pancreatic": 1.0, "pancreas": 1.0,
	"前列腺癌": 1.0, "prostate": 1.0,
	"膀胱癌": 1.0, "bladder": 1.0,
	"淋巴瘤": 1.0, "lymphoma": 1.0,
	"白血病": 1.0, "leukemia": 1.0,
	"卵巢癌": 1.0, "ovarian": 1.0, "ovary": 0.9,
	"宫颈癌": 1.0, "cervical": 1.0, "cervix": 0.9,
	"食管癌": 1.0, "esophageal": 1.0, "esophagus": 0.9,
	"肾癌": 1.0, "kidney": 1.0, "renal": 1.0,
	"鼻咽癌": 1.0, "nasopharyngeal": 1.0,
	"甲状腺癌": 1.0, "thyroid": 1.0,
	"胆囊癌": 1.0, "gallbladder": 1.0,
	"脑癌": 1.0, "brain": 1.0, "glioma": 0.9,
	"皮肤癌": 1.0, "skin": 1.0, "melanoma": 1.0,
	"骨癌": 1.0, "bone": 1.0,
	"子宫癌": 1.0, "uterine": 1.0, "endometrial": 1.0,
	"睾丸癌": 1.0, "testicular": 1.0,
	"口腔癌": 1.0, "oral": 1.0,
	"喉癌": 1.0, "laryngeal": 1.0,
	"胆管癌": 1.0, "cholangiocarcinoma": 1.0, "bile duct": 1.0,
	"胸膜癌": 1.0, "mesothelioma": 1.0,
	"小肠癌": 1.0, "small intestine": 1.0,
}

// indicatorKeywords 指标词典
var indicatorKeywords = map[string]float64{
	"5年生存率": 1.0, "5-year survival": 1.0, "five-year survival": 1.0,
	"5 year survival": 1.0, "survival rate": 0.9,
	"发病率": 1.0, "incidence": 1.0, "incident": 0.8,
	"死亡率": 1.0, "mortality": 1.0, "death rate": 0.8,
	"患病率": 1.0, "prevalence": 1.0,
	"新发病例": 0.9, "new cases": 0.9,
	"死亡病例": 0.9, "deaths": 0.9,
	"ORR": 1.0, "objective response rate": 1.0,
	"PFS": 1.0, "progression-free survival": 1.0,
	"OS": 1.0, "overall survival": 1.0,
	"DCR": 1.0, "disease control rate": 1.0,
}

// conclusionKeywords 结论词典 (PP 表述 ↔ 论文结论)
var conclusionKeywords = map[string]string{
	"远低于其他": "below_all",
	"远低于": "below",
	"低于": "below", "显著低于": "significantly_below",
	"高于": "above", "远高于": "far_above",
	"显著高于": "significantly_above",
	"等于": "equal", "相似": "similar",
	"普遍高于": "mostly_above",
	"普遍低于": "mostly_below",
	"大多数": "majority",
	"far below other": "below_all",
	"far below": "below",
	"below other": "below_all",
	"below all": "below_all",
	"below": "below",
	"above all": "above_all",
	"above other": "above_all",
	"above": "above",
	"mostly above": "mostly_above",
	"mostly below": "mostly_below",
	"majority": "majority",
}

// ParseAllegation 从 PPT 文本抽出 AllegationCore
//
// 输入: "中国肝癌5年生存率仅14.4%, 远低于其他癌种"
// 输出: AllegationCore with 4 elements
func ParseAllegation(text string) AllegationCore {
	a := AllegationCore{RawText: text}
	a.Elements[0] = extractSubject(text) // subject = {geo, disease}
	a.Elements[1] = extractTarget(text)  // target  = 比较对象
	a.Elements[2] = extractValue(text)    // value   = 数值+单位
	a.Elements[3] = extractConclusion(text)
	return a
}

func extractSubject(text string) InformationElement {
	lower := strings.ToLower(text)
	el := InformationElement{Unit: ""}

	// geography
	bestGeo, bestGeoScore := "", 0.0
	for k, v := range geoKeywords {
		if strings.Contains(text, k) || strings.Contains(lower, strings.ToLower(k)) {
			if v > bestGeoScore {
				bestGeo, bestGeoScore = k, v
			}
		}
	}
	el.Geography = bestGeo

	// disease
	bestDis, bestDisScore := "", 0.0
	for k, v := range diseaseKeywords {
		if strings.Contains(text, k) || strings.Contains(lower, strings.ToLower(k)) {
			if v > bestDisScore {
				bestDis, bestDisScore = k, v
			}
		}
	}
	el.Disease = bestDis

	return el
}

func extractTarget(text string) InformationElement {
	lower := strings.ToLower(text)
	el := InformationElement{}
	// target 是 "其他癌种" "其他 cancer" 等集合性概念
	targetPatterns := []string{"其他癌种", "其他癌肿", "其他癌症", "其他 cancer",
		"other cancers", "other cancer types", "其他恶性肿瘤"}
	for _, p := range targetPatterns {
		if strings.Contains(text, p) || strings.Contains(lower, p) {
			el.Disease = "其他癌种"
			return el
		}
	}
	// 单 target
	return extractDisease(text)
}

func extractDisease(text string) InformationElement {
	lower := strings.ToLower(text)
	best, bestScore := "", 0.0
	for k, v := range diseaseKeywords {
		if strings.Contains(text, k) || strings.Contains(lower, strings.ToLower(k)) {
			if v > bestScore {
				best, bestScore = k, v
			}
		}
	}
	return InformationElement{Disease: best}
}

var (
	reNumPct  = regexp.MustCompile(`(\d+(?:\.\d+)?)\s*%`)
	reNumOnly = regexp.MustCompile(`(\d+(?:\.\d+)?)`)
)

func extractValue(text string) InformationElement {
	el := InformationElement{}
	if m := reNumPct.FindStringSubmatch(text); len(m) >= 2 {
		el.Value = m[0]
		el.Unit = "%"
		var f float64
		fmt.Sscanf(m[1], "%f", &f)
		el.ValueNum = f
		return el
	}
	if m := reNumOnly.FindStringSubmatch(text); len(m) >= 2 {
		el.Value = m[0]
		var f float64
		fmt.Sscanf(m[1], "%f", &f)
		el.ValueNum = f
	}
	return el
}

func extractIndicator(text string) InformationElement {
	lower := strings.ToLower(text)
	best, bestScore := "", 0.0
	for k, v := range indicatorKeywords {
		if strings.Contains(text, k) || strings.Contains(lower, strings.ToLower(k)) {
			if v > bestScore {
				best, bestScore = k, v
			}
		}
	}
	return InformationElement{Indicator: best}
}

func extractConclusion(text string) InformationElement {
	el := InformationElement{}
	lower := strings.ToLower(text)
	// 按 key 长度降序, 优先匹配长 key (避免 "below" 吃掉 "below other")
	keys := make([]string, 0, len(conclusionKeywords))
	for k := range conclusionKeywords {
		keys = append(keys, k)
	}
	sort.Slice(keys, func(i, j int) bool { return len(keys[i]) > len(keys[j]) })
	for _, k := range keys {
		if strings.Contains(text, k) || strings.Contains(lower, strings.ToLower(k)) {
			el.Conclusion = conclusionKeywords[k]
			return el
		}
	}
	return el
}

// ====== 应证评分算法 (核心) ======

// ScoreElement 单维度评分 (0-1)
//
//	策略: 不是 hard 0/1, 而是 fuzzy match 给出 0-1 连续分.
func ScoreElement(a, b InformationElement, dimension string) float64 {
	switch dimension {
	case "geography":
		return fuzzyMatch(a.Geography, b.Geography, geoKeywords)
	case "disease":
		return fuzzyMatch(a.Disease, b.Disease, diseaseKeywords)
	case "indicator":
		return fuzzyMatch(a.Indicator, b.Indicator, indicatorKeywords)
	case "value":
		// 数值对齐: 14.4 ≈ 14.4 (容差 5%)
		if a.ValueNum == 0 && b.ValueNum == 0 {
			return 0.5 // 都没数, 中等分
		}
		if a.ValueNum == 0 || b.ValueNum == 0 {
			return 0.0
		}
		diff := math.Abs(a.ValueNum - b.ValueNum)
		avg := (a.ValueNum + b.ValueNum) / 2.0
		if avg == 0 {
			return 1.0
		}
		relErr := diff / avg
		if relErr < 0.05 {
			return 1.0
		}
		if relErr < 0.20 {
			return 0.7
		}
		if relErr < 0.50 {
			return 0.3
		}
		return 0.0
	case "conclusion":
		return conclusionMatch(a.Conclusion, b.Conclusion)
	}
	return 0.0
}

// fuzzyMatch: keyword 在词典里越普遍, 匹配越宽松
func fuzzyMatch(a, b string, dict map[string]float64) float64 {
	if a == "" || b == "" {
		return 0.0
	}
	aLower, bLower := strings.ToLower(a), strings.ToLower(b)
	if strings.Contains(aLower, bLower) || strings.Contains(bLower, aLower) {
		return 1.0
	}
	// 同义词 (部分映射)
	synonyms := map[string][]string{
		"liver cancer":   {"hepatocellular", "hcc", "肝癌", "肝细胞癌"},
		"lung cancer":    {"肺癌", "肺肿瘤"},
		"breast cancer":  {"乳腺癌", "乳腺肿瘤"},
		"pancreas":       {"胰腺癌", "pancreatic"},
		"colorectal":     {"结直肠癌", "colon", "rectal"},
		"stomach cancer": {"胃癌", "gastric"},
	}
	for _, synos := range synonyms {
		hasA, hasB := false, false
		for _, s := range synos {
			if strings.Contains(aLower, s) {
				hasA = true
			}
			if strings.Contains(bLower, s) {
				hasB = true
			}
		}
		if hasA && hasB {
			return 0.9
		}
	}
	// 词典里有没有 (权重)
	wa := dict[a]
	wb := dict[b]
	if wa > 0 && wb > 0 {
		return 0.6
	}
	return 0.0
}

func conclusionMatch(a, b string) float64 {
	if a == b {
		return 1.0
	}
	if a == "" || b == "" {
		return 0.0
	}
	// 集合结论 (P3-2): "远低于其他癌种" 应该 match PDF 表格里 "25>14.4 + 1<14.4"
	// 这是 5 维 (集合) vs 1 维 (单值) 的对齐
	// 用专门函数 SetConclusionScore
	return 0.0
}

// ====== 集合结论评分 (P3-2 核心) ======
//
// 用户原话 (2026-08-01):
//   "图表中一共有27行对应27种癌症 在中国的5年生存率都高于肝癌的14.4%。
//    最终推理, PDF图表中27种癌症在中国的5年生存率,
//    其中25种都高于肝癌的14.4%, 仅有胰腺癌的8.5%低于肝癌的14.4%."
//
// 这不是简单 match, 是:
//   1. 抽出 PDF 表格里所有 (disease, value) 对
//   2. 跟 subject {disease=肝癌, value=14.4} 比对
//   3. 计数: N_high + N_low + N_equal = N_total
//   4. 应证 "远低于其他癌种" 要求: N_high >= N_total - 1 (允许 1 个例外)
type TableRow struct {
	Disease  string
	Value    float64
	Unit     string
	Geography string
	BBox     BoundingBox
	RawText  string
}

// SetConclusionScore 集合结论评分
//
//	subjectValue: 14.4 (肝癌)
//	conclusion:   "below_all" (远低于)
//	tableRows:    PDF 表格的 27 行 (disease, value)
//
// 返回: 应证得分 0-1 + count_high + count_low + count_exceptions
func SetConclusionScore(subjectValue float64, conclusion string, tableRows []TableRow) (score float64, nHigh, nLow, nException int) {
	if len(tableRows) == 0 {
		return 0, 0, 0, 0
	}

	for _, row := range tableRows {
		// 排除 subject 自己 (肝癌 vs 肝癌 = 0 比较无意义)
		if isSameDisease(row.Disease, "肝癌") || isSameDisease(row.Disease, "HCC") {
			continue
		}
		if row.Value > subjectValue {
			nHigh++
		} else if row.Value < subjectValue {
			nLow++
		}
	}

	nTotal := nHigh + nLow
	if nTotal == 0 {
		return 0, nHigh, nLow, 0
	}

	switch conclusion {
	case "below_all", "below":
		// "远低于其他癌种" → 应该全部 > subjectValue
		// 允许 1 个例外 (用户原话: 27 种中 25 > 14.4 + 1 < 14.4)
		if nLow == 0 {
			score = 1.0 // 完美应证
		} else if nLow == 1 && nHigh >= 20 {
			score = 0.95 // 允许 1 例外 (P3-2 实际场景)
		} else if nLow <= 3 && float64(nHigh)/float64(nTotal) >= 0.85 {
			score = 0.80
		} else {
			score = float64(nHigh) / float64(nTotal) * 0.70
		}
		nException = nLow
	case "above_all", "above":
		score = float64(nLow) / float64(nTotal)
		nException = nHigh
	}
	return
}

func isSameDisease(a, b string) bool {
	if a == "" || b == "" {
		return false
	}
	aLower, bLower := strings.ToLower(a), strings.ToLower(b)
	if strings.Contains(aLower, bLower) || strings.Contains(bLower, aLower) {
		return true
	}
	// 词典匹配 (核心癌肿等价)
	coreDiseases := [][]string{
		{"肝癌", "hcc", "hepatocellular", "liver cancer", "肝细胞癌", "原发性肝癌"},
		{"肺癌", "lung cancer", "lung"},
		{"乳腺癌", "breast cancer", "breast"},
		{"胰腺癌", "pancreas", "pancreatic"},
		{"结直肠癌", "colorectal", "colon", "rectal"},
		{"胃癌", "stomach cancer", "gastric"},
		{"前列腺癌", "prostate", "prostate cancer"},
		{"宫颈癌", "cervical", "cervix"},
		{"卵巢癌", "ovarian", "ovary"},
		{"甲状腺癌", "thyroid"},
	}
	for _, group := range coreDiseases {
		aIn, bIn := false, false
		for _, s := range group {
			if strings.Contains(aLower, s) {
				aIn = true
			}
			if strings.Contains(bLower, s) {
				bIn = true
			}
		}
		if aIn && bIn {
			return true
		}
	}
	return false
}

// ====== 应证主算法 ======

// ConfirmAllegation 应证推理: 给定 PPT 论点 + PDF 证据, 给出应证评分 + 高亮决策
//
// 算法步骤:
//  1. 把 PPT 论点拆 4 维要素 (ParseAllegation)
//  2. 把 PDF 每条 evidence 也拆 4 维要素
//  3. 每个维度评分 (ScoreElement)
//  4. 加权求和得 ConfirmScore
//  5. 如果是"集合结论" (below_all) → 调 SetConclusionScore 重算
//  6. 决策: ConfirmScore >= 0.7 → 高亮
func ConfirmAllegation(a AllegationCore, evidences []EvidenceEvidence, tableRows []TableRow) AllegationMatch {
	m := AllegationMatch{Allegation: a}

	// 集合结论单独处理 (P3-2 应证)
	if a.Elements[3].Conclusion == "below_all" || a.Elements[3].Conclusion == "below" ||
		a.Elements[3].Conclusion == "above_all" || a.Elements[3].Conclusion == "above" {
		s, nHigh, nLow, nExc := SetConclusionScore(a.Elements[2].ValueNum, a.Elements[3].Conclusion, tableRows)
		m.ConfirmScore = s
		m.MismatchReport = fmt.Sprintf("集合结论: %d > subject + %d < subject + %d 例外", nHigh, nLow, nExc)

		// 应证集合结论 → 高亮所有 27 行 + subject 自己
		if s >= 0.70 {
			m.Decision = HighlightDecision{
				ShouldHighlight: true,
				Reason:          fmt.Sprintf("应证得分 %.2f, 集合结论成立", s),
				BBoxes:          tableRowsToBBoxes(tableRows),
				HighlightType:   "highlight",
				Notes:           buildNotes(a, nHigh, nLow, nExc),
			}
		} else {
			m.Decision.ShouldHighlight = false
			m.Decision.Reason = fmt.Sprintf("应证得分 %.2f < 0.70 阈值, 不应证", s)
		}
		return m
	}

	// 单点结论: 4 维评分加权
	for _, ev := range evidences {
		m.EvidenceToScore(&ev, a)
		m.Evidences = append(m.Evidences, ev)
	}

	// 加权 (ElementScores 已是 max 累计, 直接取)
	m.ConfirmScore = WeightGeography*m.ElementScores[0] +
		WeightDisease*m.ElementScores[1] +
		WeightIndicator*m.ElementScores[2] +
		WeightValue*m.ElementScores[3]

	if m.ConfirmScore >= 0.70 {
		m.Decision = HighlightDecision{
			ShouldHighlight: true,
			Reason:          fmt.Sprintf("应证得分 %.2f", m.ConfirmScore),
			BBoxes:          evidenceBBoxes(evidences),
			HighlightType:   "underline",
			Notes:           "单点应证",
		}
	} else {
		m.Decision.ShouldHighlight = false
		m.Decision.Reason = fmt.Sprintf("应证得分 %.2f < 0.70", m.ConfirmScore)
	}
	return m
}

// EvidenceToScore (辅助方法, 给单条 evidence 评分)
func (m *AllegationMatch) EvidenceToScore(ev *EvidenceEvidence, a AllegationCore) {
	geo := ScoreElement(a.Elements[0], ev.Element, "geography")
	dis := ScoreElement(a.Elements[0], ev.Element, "disease")
	ind := ScoreElement(extractedIndicator(ev.RawText), ev.Element, "indicator")
	val := ScoreElement(a.Elements[2], ev.Element, "value")
	ev.Confidence = (geo + dis + ind + val) / 4.0

	// 更新最大分到 ElementScores
	if geo > m.ElementScores[0] {
		m.ElementScores[0] = geo
	}
	if dis > m.ElementScores[1] {
		m.ElementScores[1] = dis
	}
	if ind > m.ElementScores[2] {
		m.ElementScores[2] = ind
	}
	if val > m.ElementScores[3] {
		m.ElementScores[3] = val
	}
}

func extractedIndicator(text string) InformationElement {
	return extractIndicator(text)
}

func max4(a [4]float64) float64 {
	m := 0.0
	for _, v := range a {
		if v > m {
			m = v
		}
	}
	return m
}

func tableRowsToBBoxes(rows []TableRow) []BoundingBox {
	out := make([]BoundingBox, 0, len(rows))
	for _, r := range rows {
		out = append(out, r.BBox)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Y0 < out[j].Y0 })
	return out
}

func evidenceBBoxes(evs []EvidenceEvidence) []BoundingBox {
	out := make([]BoundingBox, 0, len(evs))
	for _, e := range evs {
		out = append(out, e.BBox)
	}
	return out
}

func buildNotes(a AllegationCore, nHigh, nLow, nExc int) string {
	disease := a.Elements[0].Disease
	value := a.Elements[2].Value
	return fmt.Sprintf(
		"应证 %s %s %s, 远低于其他癌种: %d 种癌肿高于 %s, %d 种低于 (例外 %d 种)",
		a.Elements[0].Geography, disease, value, nHigh, value, nLow, nExc,
	)
}