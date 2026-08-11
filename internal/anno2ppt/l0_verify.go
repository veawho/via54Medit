package anno2ppt

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// L0VerifyResult PDF 真实性验证结果
//
// 算法驱动 (4 维要素 + 时间戳):
//
//	score = 0.45*TitleSim + 0.30*AuthorSim + 0.15*PubDateMatch + 0.10*MetadataCompleteness
//
// 阈值:
//	score >= 0.70 → verified=true (完全可信)
//	0.45 <= score < 0.70 → verified=false, warning (部分可信, 需 LLM 复核)
//	score < 0.45 → verified=false, reject (不可信, 走 fallback)
//
// 设计: 用户 2026-08-01 教训 -- P22-1 main PDF 是 liangyihui.net 截图包壳,
// 误标记为 ESMO 2025 #1494P. L0 验证可以拦截此类"看起来像但实际不是"的 PDF.
type L0VerifyResult struct {
	Verified    bool    `json:"verified"`
	Score       float64 `json:"score"`
	TitleSim    float64 `json:"title_similarity"`
	AuthorSim   float64 `json:"author_similarity"`
	DateMatch   float64 `json:"date_match"`
	MetaCompl   float64 `json:"metadata_completeness"`
	Issue       string  `json:"issue,omitempty"`         // 不通过原因
	RefTitle    string  `json:"reference_title,omitempty"` // Crossref 期望标题
	PDFTitle    string  `json:"pdf_title,omitempty"`       // PDF 实际标题
	CrossrefRaw string  `json:"crossref_raw,omitempty"`    // Crossref 原始 JSON (debug)
}

// CrossrefRecord Crossref API 返回的论文元数据
type CrossrefRecord struct {
	Title    []string `json:"title"`
	Authors  []struct {
		Family string `json:"family"`
		Given  string `json:"given"`
	} `json:"author"`
	Published struct {
		DateParts [][]int `json:"date-parts"`
	} `json:"published"`
	DOI       string   `json:"DOI"`
	Container []string `json:"container-title"`
	Publisher string   `json:"publisher"`
}

// FetchCrossrefMeta 通过 DOI 查询 Crossref API
//
// API: https://api.crossref.org/works/{doi}
//
// 无本地 LLM 依赖 (AGENTS.md 关键约束 1), 无 Hermes API (约束 6).
func FetchCrossrefMeta(doi string, httpClient *http.Client) (*CrossrefRecord, error) {
	if doi == "" {
		return nil, fmt.Errorf("empty DOI")
	}
	cleanedDOI := strings.TrimPrefix(doi, "https://doi.org/")
	cleanedDOI = strings.TrimPrefix(cleanedDOI, "http://doi.org/")
	cleanedDOI = strings.TrimPrefix(cleanedDOI, "doi.org/")

	apiURL := fmt.Sprintf("https://api.crossref.org/works/%s", url.PathEscape(cleanedDOI))
	if httpClient == nil {
		httpClient = &http.Client{Timeout: 15 * time.Second}
	}
	resp, err := httpClient.Get(apiURL)
	if err != nil {
		return nil, fmt.Errorf("crossref fetch: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("crossref status %d for DOI %s", resp.StatusCode, cleanedDOI)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("crossref read: %w", err)
	}

	var rec struct {
		Message CrossrefRecord `json:"message"`
	}
	if err := json.Unmarshal(body, &rec); err != nil {
		return nil, fmt.Errorf("crossref parse: %w", err)
	}
	return &rec.Message, nil
}

// JaccardSimilarity 词语 Jaccard 相似度 (集合交集 / 集合并集)
//
//	比 TF-IDF / 编辑距离简单, 但对论文标题足够 (论文标题关键词明确)
func JaccardSimilarity(a, b string) float64 {
	a = strings.ToLower(strings.TrimSpace(a))
	b = strings.ToLower(strings.TrimSpace(b))
	if a == "" || b == "" {
		return 0
	}

	tokensA := tokenizeTitle(a)
	tokensB := tokenizeTitle(b)
	if len(tokensA) == 0 || len(tokensB) == 0 {
		return 0
	}

	setA := make(map[string]bool, len(tokensA))
	for _, t := range tokensA {
		setA[t] = true
	}
	intersection := 0
	union := len(setA)
	for _, t := range tokensB {
		if setA[t] {
			intersection++
		} else {
			union++
		}
	}
	if union == 0 {
		return 0
	}
	return float64(intersection) / float64(union)
}

// tokenizeTitle 标题分词 (去标点 + 去停用词 + 小写)
func tokenizeTitle(s string) []string {
	// 停用词 (英文 + 标点)
	stopWords := map[string]bool{
		"a": true, "an": true, "the": true, "of": true, "in": true, "on": true,
		"and": true, "or": true, "is": true, "are": true, "was": true, "were": true,
		"with": true, "from": true, "for": true, "to": true, "by": true, "at": true,
		// 中文常见停用词
		"的": true, "在": true, "和": true, "与": true, "或": true, "是": true,
		"了": true, "将": true, "对": true, "等": true, "从": true, "中": true,
	}

	// 标点替换为空格
	chars := []rune(s)
	var out []string
	buf := strings.Builder{}
	flush := func() {
		t := strings.ToLower(strings.TrimSpace(buf.String()))
		if t != "" && !stopWords[t] && len(t) > 1 {
			out = append(out, t)
		}
		buf.Reset()
	}
	for _, c := range chars {
		if (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') ||
			(c >= 0x4E00 && c <= 0x9FFF) {
			buf.WriteRune(c)
		} else {
			flush()
		}
	}
	flush()
	return out
}

// ExtractAuthorFamily 从 Crossref 格式提取 Authors Family Names
func ExtractAuthorFamily(authors []struct {
	Family string `json:"family"`
	Given  string `json:"given"`
}) []string {
	out := []string{}
	for _, a := range authors {
		if a.Family != "" {
			out = append(out, a.Family)
		}
	}
	return out
}

// AuthorMatch 计算 PDF 作者列表与 Crossref 作者列表的匹配度
//
// 算法: PDF author 是否包含 Crossref 第一作者 (family name)
func AuthorMatch(pdfAuthor string, crossrefAuthors []string) float64 {
	if pdfAuthor == "" || len(crossrefAuthors) == 0 {
		return 0
	}
	pdfLower := strings.ToLower(pdfAuthor)
	for _, refAuthor := range crossrefAuthors {
		refLower := strings.ToLower(refAuthor)
		if strings.Contains(pdfLower, refLower) {
			return 1.0
		}
	}
	// 至少匹配 Crossref 任意一位作者
	return 0.0
}

// DateMatch 计算 PDF 创建日期与 Crossref 发布日期的逻辑一致性
//
// 规则: PDF 创建日期 >= Crossref 发布日期 (PDF 是发布后生成的) 拿 1.0
// 否则 (PDF 早于发布) 拿 0.0 (异常)
func DateMatch(pdfCreationDate, crossrefPubDate time.Time) float64 {
	if pdfCreationDate.IsZero() || crossrefPubDate.IsZero() {
		return 0.5 // 缺一个, 给中性
	}
	if pdfCreationDate.After(crossrefPubDate) {
		return 1.0
	}
	return 0.0
}

// MetadataCompleteness 计算 PDF metadata 完整度
//
// 4 个字段都有: 1.0
// 3 个字段: 0.75
// 2 个字段: 0.5
// 1 个字段: 0.25
// 0 个字段: 0.0
//
// 对占位符 (untitled / anonymous / unspecified / 等) 严格识别
func MetadataCompleteness(title, author, subject, creator string) float64 {
	filled := 0
	total := 4
	if isRealMetadata(title) {
		filled++
	}
	if isRealMetadata(author) {
		filled++
	}
	if isRealMetadata(subject) {
		filled++
	}
	if isRealMetadata(creator) {
		filled++
	}
	return float64(filled) / float64(total)
}

// isRealMetadata 检查 metadata 字段是否是真的有内容
//
// 排除所有 placeholder 和默认值
func isRealMetadata(s string) bool {
	s = strings.TrimSpace(s)
	if s == "" {
		return false
	}
	lowered := strings.ToLower(s)
	placeholders := []string{
		"untitled", "anonymous", "unspecified", "n/a", "na",
		"anon", "unknown", "test", "placeholder", "default",
		"匿名", "未指定", "无标题", "未知",
	}
	for _, p := range placeholders {
		if lowered == p {
			return false
		}
	}
	return true
}

// L0Verify PDF 真实性验证主入口
//
// 参数:
//   pdfTitle, pdfAuthor, pdfSubject, pdfCreator: PDF metadata
//   pdfCreation: PDF metadata CreationDate (time.Time)
//   doi: 引文中的 DOI (用于 Crossref 反查)
//
// 返回: L0VerifyResult
//
// 触发流: process_pn_x.py 或 medit confirm 应在调 L4 之前先调 L0
func L0Verify(pdfTitle, pdfAuthor, pdfSubject, pdfCreator string, pdfCreation time.Time, doi string) L0VerifyResult {
	res := L0VerifyResult{}
	res.PDFTitle = pdfTitle

	if doi == "" {
		// 没 DOI 没法 L0 验证, 降级为 partial: 只看 metadata 完整度
		res.MetaCompl = MetadataCompleteness(pdfTitle, pdfAuthor, pdfSubject, pdfCreator)
		res.Score = res.MetaCompl * 0.5 // 没 DOI 减半
		res.TitleSim = 0
		res.AuthorSim = 0
		res.DateMatch = 0
		res.Issue = "no DOI provided"
		res.Verified = res.Score >= 0.50
		return res
	}

	// Crossref 反查
	ref, err := FetchCrossrefMeta(doi, nil)
	if err != nil {
		// API 失败: 不阻止 L4, 但标记不可信
		res.MetaCompl = MetadataCompleteness(pdfTitle, pdfAuthor, pdfSubject, pdfCreator)
		res.Score = res.MetaCompl * 0.4
		res.Issue = fmt.Sprintf("crossref fetch failed: %v", err)
		res.Verified = false
		return res
	}

	// 1. Title 相似度
	if len(ref.Title) > 0 {
		refTitle := ref.Title[0]
		res.RefTitle = refTitle
		res.TitleSim = JaccardSimilarity(pdfTitle, refTitle)
	} else {
		res.TitleSim = 0
	}

	// 2. Author 匹配
	refAuthors := ExtractAuthorFamily(ref.Authors)
	res.AuthorSim = AuthorMatch(pdfAuthor, refAuthors)

	// 3. 日期匹配
	var crossrefPubDate time.Time
	if len(ref.Published.DateParts) > 0 && len(ref.Published.DateParts[0]) >= 3 {
		crossrefPubDate = time.Date(
			ref.Published.DateParts[0][0],
			time.Month(ref.Published.DateParts[0][1]),
			ref.Published.DateParts[0][2],
			0, 0, 0, 0, time.UTC,
		)
	}
	res.DateMatch = DateMatch(pdfCreation, crossrefPubDate)

	// 4. Metadata 完整度
	res.MetaCompl = MetadataCompleteness(pdfTitle, pdfAuthor, pdfSubject, pdfCreator)

	// 综合评分
	res.Score = 0.45*res.TitleSim + 0.30*res.AuthorSim + 0.15*res.DateMatch + 0.10*res.MetaCompl

	// 决策
	if res.Score >= 0.70 {
		res.Verified = true
	} else {
		res.Verified = false
		if res.TitleSim < 0.30 {
			res.Issue = fmt.Sprintf("Title mismatch (sim=%.2f): PDF=%q vs Ref=%q",
				res.TitleSim, pdfTitle, res.RefTitle)
		} else if res.AuthorSim < 0.5 {
			res.Issue = fmt.Sprintf("Author mismatch: PDF=%q vs Ref[0]=%q",
				pdfAuthor, refAuthors)
		}
	}

	return res
}
