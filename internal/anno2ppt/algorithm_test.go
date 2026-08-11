package anno2ppt

import (
	"strings"
	"testing"
)

// 9 案例 / 31 单元测试 - P3-2 真实场景驱动
// 注: 所有 Errorf 字符串必须 ASCII, go vet 把中文误判为 format verb.

// === Test 1: ParseAllegation 4 维要素抽取 ===

func TestParseAllegation_P3_2(t *testing.T) {
	text := "China HCC 5-year survival rate only 14.4%, far below other cancers"
	a := ParseAllegation(text)

	if !strings.Contains(a.Elements[0].Geography, "China") &&
		!strings.Contains(a.Elements[0].Geography, "中国") {
		t.Errorf("Geography should be China or 中国, got %q", a.Elements[0].Geography)
	}
	if !strings.Contains(strings.ToLower(a.Elements[0].Disease), "hcc") &&
		!strings.Contains(a.Elements[0].Disease, "肝癌") {
		t.Errorf("Disease should be HCC or 肝癌, got %q", a.Elements[0].Disease)
	}
	if !strings.Contains(a.Elements[2].Value, "14.4") {
		t.Errorf("Value should contain 14.4, got %q", a.Elements[2].Value)
	}
	if a.Elements[2].Unit != "%" {
		t.Errorf("Unit should be %%, got %q", a.Elements[2].Unit)
	}
	if a.Elements[2].ValueNum != 14.4 {
		t.Errorf("ValueNum should be 14.4, got %v", a.Elements[2].ValueNum)
	}
	if a.Elements[3].Conclusion != "below_all" {
		t.Errorf("Conclusion should be below_all (far below others), got %q", a.Elements[3].Conclusion)
	}
}

// === Test 2: SetConclusionScore P3-2 真实场景 (27 行, 25 > 14.4 + 1 < 14.4) ===

func TestSetConclusionScore_P3_2_Real(t *testing.T) {
	rows := makeTableRows_P3_2()

	score, nHigh, nLow, nExc := SetConclusionScore(14.4, "below_all", rows)

	if nHigh != 25 {
		t.Errorf("nHigh should be 25, got %d", nHigh)
	}
	if nLow != 1 {
		t.Errorf("nLow should = 1 (pancreas 8.5), got %d", nLow)
	}
	if nExc != 1 {
		t.Errorf("nExc should = 1, got %d", nExc)
	}
	if score < 0.90 {
		t.Errorf("Confirm score should >= 0.90 (1 exception allowed), got %.2f", score)
	}
}

// === Test 3: 完美应证 (20 行全部 > subject) ===

func TestSetConclusionScore_PerfectAllAbove(t *testing.T) {
	rows := makeRows_AllAbove(14.4, 20)
	score, _, _, _ := SetConclusionScore(14.4, "below_all", rows)
	if score < 0.99 {
		t.Errorf("20/20 all > should = 1.0, got %.2f", score)
	}
}

// === Test 4: 失败应证 (大部分 < subject) ===

func TestSetConclusionScore_Fail(t *testing.T) {
	rows := []TableRow{
		{Disease: "lung cancer", Value: 10.0},
		{Disease: "stomach cancer", Value: 12.0},
		{Disease: "HCC", Value: 14.4},
		{Disease: "colorectal", Value: 20.0},
	}
	score, nHigh, nLow, _ := SetConclusionScore(14.4, "below_all", rows)
	if score >= 0.70 {
		t.Errorf("Confirm failed (1 high 2 low), score should < 0.70, got %.2f", score)
	}
	if nLow != 2 {
		t.Errorf("nLow should be 2 (lung 10 + stomach 12), got %d", nLow)
	}
	if nHigh != 1 {
		t.Errorf("nHigh should be 1 (colorectal 20), got %d", nHigh)
	}
}

// === Test 5: ConfirmAllegation 集合结论 端到端 ===

func TestConfirmAllegation_SetConclusion(t *testing.T) {
	text := "China HCC 5-year survival rate only 14.4%, far below other cancers"
	a := ParseAllegation(text)
	rows := makeTableRows_P3_2()

	m := ConfirmAllegation(a, nil, rows)

	if !m.Decision.ShouldHighlight {
		t.Errorf("Confirm success should highlight, reason: %s", m.Decision.Reason)
	}
	if m.ConfirmScore < 0.90 {
		t.Errorf("ConfirmScore should >= 0.90, got %.2f", m.ConfirmScore)
	}
	if len(m.Decision.BBoxes) != 27 {
		t.Errorf("Should highlight 27 rows (incl. subject), got %d bboxes", len(m.Decision.BBoxes))
	}
	if !strings.Contains(m.Decision.Notes, "25") {
		t.Errorf("Notes should mention 25 (25 cancers above 14.4), got %q", m.Decision.Notes)
	}
}

// === Test 6: ConfirmAllegation 单点结论 (HIMALAYA OS) ===

func TestConfirmAllegation_SinglePoint(t *testing.T) {
	// 加 geography 让 4 维全匹配
	text := "Global HCC OS 24.0 months in HIMALAYA trial"
	a := ParseAllegation(text)

	ev := EvidenceEvidence{
		Page:    5,
		RawText: "Tremelimumab plus durvalumab in unresectable HCC, median OS 24.0 months (95% CI 18.7-30.8)",
		Element: InformationElement{
			Geography: "global",
			Disease:   "HCC",
			Indicator: "OS",
			Value:     "24.0",
			ValueNum:  24.0,
			Unit:      "months",
		},
		Confidence: 0.0,
	}

	m := ConfirmAllegation(a, []EvidenceEvidence{ev}, nil)

	if !m.Decision.ShouldHighlight {
		t.Errorf("Single-point confirm should highlight, reason: %s", m.Decision.Reason)
	}
	if m.ConfirmScore < 0.70 {
		t.Errorf("ConfirmScore should >= 0.70, got %.2f", m.ConfirmScore)
	}
}

// === Test 7: OCR 错字 / 无空格 / 全角标点 容错 ===

func TestParseAllegation_OCR_Typo(t *testing.T) {
	texts := []string{
		"中国肝癌5年生存率仅14.4%,远低于其他癌种",
		"中国肝癌 5 年生存率仅 14.4 % ， 远低于其他癌种",
		"China HCC 5-year survival only 14.4%, far below other cancers",
	}

	for _, txt := range texts {
		a := ParseAllegation(txt)
		if a.Elements[2].ValueNum != 14.4 {
			t.Errorf("text=%q should extract 14.4, got %v", txt, a.Elements[2].ValueNum)
		}
		if a.Elements[3].Conclusion == "" {
			t.Errorf("text=%q should extract conclusion", txt)
		}
	}
}

// === Test 8: 评分算法 - 4 维 fuzzy ===

func TestScoreElement_Fuzzy(t *testing.T) {
	a := InformationElement{Geography: "中国"}
	b := InformationElement{Geography: "China"}
	score := ScoreElement(a, b, "geography")
	if score < 0.5 {
		t.Errorf("China vs 中国 should fuzzy match, got %.2f", score)
	}

	a = InformationElement{Disease: "HCC"}
	b = InformationElement{Disease: "肝癌"}
	score = ScoreElement(a, b, "disease")
	if score < 0.9 {
		t.Errorf("HCC vs 肝癌 should 0.9+, got %.2f", score)
	}

	a = InformationElement{ValueNum: 14.4}
	b = InformationElement{ValueNum: 14.5}
	score = ScoreElement(a, b, "value")
	if score < 0.9 {
		t.Errorf("14.4 vs 14.5 should fuzzy (5%% tolerance), got %.2f", score)
	}

	a = InformationElement{ValueNum: 14.4}
	b = InformationElement{ValueNum: 100}
	score = ScoreElement(a, b, "value")
	if score > 0.3 {
		t.Errorf("14.4 vs 100 should low score, got %.2f", score)
	}
}

// === Test 9: 跨语言 - 英文癌肿 ===

func TestParseAllegation_English(t *testing.T) {
	text := "In China, the 5-year survival rate of HCC is only 14.4%, far below other cancers"
	a := ParseAllegation(text)

	if !strings.Contains(a.Elements[0].Geography, "China") {
		t.Errorf("Geography should be China, got %q", a.Elements[0].Geography)
	}
	if !strings.Contains(strings.ToLower(a.Elements[0].Disease), "hcc") {
		t.Errorf("Disease should HCC, got %q", a.Elements[0].Disease)
	}
	if a.Elements[2].ValueNum != 14.4 {
		t.Errorf("ValueNum should be 14.4, got %v", a.Elements[2].ValueNum)
	}
}

// ====== Helpers: 真实场景测试数据 ======

func makeTableRows_P3_2() []TableRow {
	rows := []TableRow{
		{Disease: "肝癌", Value: 14.4, Unit: "%", Geography: "中国"},
		{Disease: "甲状腺癌", Value: 84.3, Unit: "%", Geography: "中国"},
		{Disease: "乳腺癌", Value: 83.2, Unit: "%", Geography: "中国"},
		{Disease: "膀胱癌", Value: 72.9, Unit: "%", Geography: "中国"},
		{Disease: "肾癌", Value: 69.8, Unit: "%", Geography: "中国"},
		{Disease: "前列腺癌", Value: 69.2, Unit: "%", Geography: "中国"},
		{Disease: "淋巴瘤", Value: 65.4, Unit: "%", Geography: "中国"},
		{Disease: "子宫癌", Value: 65.1, Unit: "%", Geography: "中国"},
		{Disease: "宫颈癌", Value: 63.4, Unit: "%", Geography: "中国"},
		{Disease: "卵巢癌", Value: 54.9, Unit: "%", Geography: "中国"},
		{Disease: "结直肠癌", Value: 57.6, Unit: "%", Geography: "中国"},
		{Disease: "皮肤癌", Value: 56.9, Unit: "%", Geography: "中国"},
		{Disease: "口腔癌", Value: 50.1, Unit: "%", Geography: "中国"},
		{Disease: "喉癌", Value: 48.7, Unit: "%", Geography: "中国"},
		{Disease: "胃癌", Value: 45.5, Unit: "%", Geography: "中国"},
		{Disease: "食管癌", Value: 40.4, Unit: "%", Geography: "中国"},
		{Disease: "胆囊癌", Value: 36.3, Unit: "%", Geography: "中国"},
		{Disease: "白血病", Value: 35.4, Unit: "%", Geography: "中国"},
		{Disease: "骨癌", Value: 35.0, Unit: "%", Geography: "中国"},
		{Disease: "脑癌", Value: 32.6, Unit: "%", Geography: "中国"},
		{Disease: "肺癌", Value: 32.5, Unit: "%", Geography: "中国"},
		{Disease: "胆管癌", Value: 29.8, Unit: "%", Geography: "中国"},
		{Disease: "睾丸癌", Value: 28.9, Unit: "%", Geography: "中国"},
		{Disease: "鼻咽癌", Value: 23.8, Unit: "%", Geography: "中国"},
		{Disease: "胸膜癌", Value: 18.4, Unit: "%", Geography: "中国"},
		{Disease: "小肠癌", Value: 16.8, Unit: "%", Geography: "中国"},
		{Disease: "胰腺癌", Value: 8.5, Unit: "%", Geography: "中国"},
	}
	return rows
}

func makeRows_AllAbove(threshold float64, n int) []TableRow {
	rows := make([]TableRow, 0, n+1)
	rows = append(rows, TableRow{Disease: "肝癌", Value: threshold, Unit: "%", Geography: "中国"})
	for i := 0; i < n; i++ {
		rows = append(rows, TableRow{Disease: "CancerX", Value: threshold + float64(i+1)*5, Unit: "%", Geography: "中国"})
	}
	return rows
}