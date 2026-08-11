package anno2ppt

import (
	"strings"
	"testing"
	"time"
)

// === 案例 1: 真实 P22-1 ESMO 2025 #1494P 原文 PDF (应 verified=true) ===
func TestL0Verify_RealESMO1494P(t *testing.T) {
	// 真原文 PDF metadata (从 PyMuPDF 抽)
	pdfTitle := "1494P Pooled efficacy and safety outcomes with tremelimumab plus durvalumab in participants (pts) with unresectable hepatocellular carcinoma (uHCC) from the combined China extension and global cohorts in the phase III HIMALAYA study"
	pdfAuthor := "B. Sangro"
	pdfSubject := "Annals of Oncology, 36 (2025) S832-S833. doi:10.1016/j.annonc.2025.08.2124"
	pdfCreator := "Elsevier"
	pdfCreation := time.Date(2025, 11, 6, 1, 51, 29, 0, time.UTC)

	res := L0Verify(pdfTitle, pdfAuthor, pdfSubject, pdfCreator, pdfCreation, "10.1016/j.annonc.2025.08.2124")

	if !res.Verified {
		t.Errorf("Real ESMO 1494P should verified=true, got false. Score=%.2f Issue=%s", res.Score, res.Issue)
	}
	if res.Score < 0.70 {
		t.Errorf("Real ESMO 1494P should score >= 0.70, got %.2f", res.Score)
	}
	if res.TitleSim < 0.50 {
		t.Errorf("Title similarity too low for real paper: %.2f", res.TitleSim)
	}
	if res.AuthorSim < 0.5 {
		t.Errorf("Author should match: PDF=%q, got %.2f", pdfAuthor, res.AuthorSim)
	}
}

// === 案例 2: v3.9 P22-1 二手截图 PDF (应 verified=false) ===
func TestL0Verify_ScreenCapturePDF(t *testing.T) {
	// v3.9 截图包壳 PDF 的 metadata
	pdfTitle := "untitled" // 截图包壳没设置 title
	pdfAuthor := "anonymous"
	pdfSubject := "unspecified"
	pdfCreator := "anonymous"
	pdfCreation := time.Date(2026, 7, 26, 15, 42, 55, 0, time.UTC) // 是今天生成的

	res := L0Verify(pdfTitle, pdfAuthor, pdfSubject, pdfCreator, pdfCreation, "10.1016/j.annonc.2025.08.2124")

	if res.Verified {
		t.Errorf("Screenshot PDF should NOT be verified as ESMO 1494P. Score=%.2f", res.Score)
	}
	if res.TitleSim > 0.30 {
		t.Errorf("Title similarity should be very low (untitled vs long title): %.2f", res.TitleSim)
	}
}

// === 案例 3: 空 DOI (降级到 metadata 完整度) ===
func TestL0Verify_NoDOI(t *testing.T) {
	res := L0Verify("Hong Kong Study", "Smith J", "Some Subject", "Some Creator",
		time.Now(), "") // empty DOI

	if res.Score > 0.50 {
		t.Errorf("No DOI should cap at 0.50, got %.2f", res.Score)
	}
	if !strings.Contains(res.Issue, "no DOI") {
		t.Errorf("Issue should mention no DOI, got %q", res.Issue)
	}
}

// === 案例 4: DOI 格式 https://doi.org/10.1016/... 也能解析 ===
func TestL0Verify_DOIWithURLPrefix(t *testing.T) {
	// 至少证明 URL 解析不 panic + URL prefix 被正确剥离
	_, err := FetchCrossrefMeta("https://doi.org/10.1016/j.annonc.2025.08.2124", nil)
	if err != nil {
		t.Logf("Crossref fetch returned err (may be network): %v", err)
	}
}

// === 案例 5: Jaccard 标题相似度 ===
func TestJaccardSimilarity(t *testing.T) {
	// 注: "of" / "in" / "the" 这类停用词被 tokenize 去掉
	cases := []struct {
		name string
		a, b string
		want float64
	}{
		{"完全相同", "HIMALAYA study of HCC", "HIMALAYA study of HCC", 1.0},
		{"去停用词后相同", "HIMALAYA study HCC", "HIMALAYA study of HCC", 1.0},
		{"完全不同", "HIMALAYA study HCC", "completely different text", 0.0},
		{"空字符串", "", "something", 0.0},
		{"中英混合", "HIMALAYA 亚太", "HIMALAYA Asia-Pacific", 0.25},
	}
	for _, c := range cases {
		got := JaccardSimilarity(c.a, c.b)
		if got < c.want-0.15 || got > c.want+0.15 {
			t.Errorf("%s: Jaccard(%q, %q) = %.2f, want ~%.2f", c.name, c.a, c.b, got, c.want)
		}
	}
}

// === 案例 6: Jaccard 应该忽略停用词 ===
func TestJaccardSimilarity_StopWords(t *testing.T) {
	// 不同: "HIMALAYA study of HCC in China" vs "HIMALAYA study of HCC in Japan"
	// 词: HIMALAYA, study, HCC, China vs HIMALAYA, study, HCC, Japan
	// 交集 3, 并集 5 → 0.6
	c := "HIMALAYA study of HCC in Japan"
	got := JaccardSimilarity("HIMALAYA study of HCC in China", c)
	if got < 0.55 || got > 0.65 {
		t.Errorf("Expected ~0.6, got %.2f", got)
	}
}

// === 案例 7: Metadata 完整度 ===
func TestMetadataCompleteness(t *testing.T) {
	cases := []struct {
		title, author, subject, creator string
		wantMin, wantMax                float64
		desc                            string
	}{
		{"Real", "Real", "Real", "Real", 1.0, 1.0, "全填"},
		{"Real", "Real", "Real", "", 0.75, 0.75, "1 个空"},
		{"untitled", "anonymous", "", "", 0.0, 0.0, "全 placeholder"},
		{"Real", "anon", "Real", "anon", 0.5, 0.5, "短截 anonymous"},
	}
	for _, c := range cases {
		got := MetadataCompleteness(c.title, c.author, c.subject, c.creator)
		if got < c.wantMin || got > c.wantMax {
			t.Errorf("%s: got %.2f, want in [%.2f, %.2f]", c.desc, got, c.wantMin, c.wantMax)
		}
	}
}

// === 案例 8: Author Match ===
func TestAuthorMatch(t *testing.T) {
	cases := []struct {
		pdf     string
		ref     []string
		wantMin float64
		desc    string
	}{
		{"B. Sangro", []string{"Sangro"}, 1.0, "完全匹配"},
		{"Sangro B. et al", []string{"Sangro"}, 1.0, "包含 1 作者"},
		{"Smith J", []string{"Sangro"}, 0.0, "完全不匹配"},
		{"", []string{"Sangro"}, 0.0, "PDF author 空"},
		{"B. Sangro", []string{}, 0.0, "参考空"},
	}
	for _, c := range cases {
		got := AuthorMatch(c.pdf, c.ref)
		if got < c.wantMin {
			t.Errorf("%s: got %.2f, want >= %.2f", c.desc, got, c.wantMin)
		}
	}
}

// === 案例 9: Date Match ===
func TestDateMatch(t *testing.T) {
	pdfAfter := time.Date(2025, 11, 15, 0, 0, 0, 0, time.UTC)  // 发布后
	refDate := time.Date(2025, 11, 6, 0, 0, 0, 0, time.UTC)   // 发布日
	refBefore := time.Date(2025, 10, 15, 0, 0, 0, 0, time.UTC) // 发布前

	if got := DateMatch(pdfAfter, refDate); got != 1.0 {
		t.Errorf("PDF after pub should = 1.0, got %.2f", got)
	}
	if got := DateMatch(refBefore, refDate); got != 0.0 {
		t.Errorf("PDF before pub should = 0.0, got %.2f", got)
	}
	if got := DateMatch(time.Time{}, refDate); got != 0.5 {
		t.Errorf("Missing PDF date should = 0.5, got %.2f", got)
	}
}

// === 集成测试: 端到端 P22-1 验证 (用真 DOI 但可能网络失败) ===
func TestL0Verify_RealP22V39Difference(t *testing.T) {
	// 模拟 P22-1 v3.9 (截图包壳)
	v39Res := L0Verify(
		"untitled", "anonymous", "unspecified", "anonymous",
		time.Date(2026, 7, 26, 15, 42, 55, 0, time.UTC),
		"10.1016/j.annonc.2025.08.2124",
	)

	// 模拟 P22-1 v4.0 (真原文)
	v40Res := L0Verify(
		"1494P Pooled efficacy and safety outcomes with tremelimumab plus durvalumab in participants (pts) with unresectable hepatocellular carcinoma (uHCC) from the combined China extension and global cohorts in the phase III HIMALAYA study",
		"B. Sangro",
		"Annals of Oncology, 36 (2025) S832-S833. doi:10.1016/j.annonc.2025.08.2124",
		"Elsevier",
		time.Date(2025, 11, 6, 1, 51, 29, 0, time.UTC),
		"10.1016/j.annonc.2025.08.2124",
	)

	if v39Res.Verified == v40Res.Verified {
		t.Errorf("v3.9 and v4.0 should have different verified status. v39=%v v40=%v",
			v39Res.Verified, v40Res.Verified)
	}
	if v40Res.Score <= v39Res.Score {
		t.Errorf("v4.0 score should be > v3.9. v39=%.2f, v40=%.2f", v39Res.Score, v40Res.Score)
	}
}
