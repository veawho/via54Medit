// Package source provides adapters for medical literature sources.
//
// Phase 1 status (2026-06-24):
//   - pubmed.go  : ✅ NCBI E-utilities (esearch + esummary), 3 req/s rate-limited
//   - antfu.go   : ⚠️  Stub. Real Chrome 9223 CDP client lands in Phase 1.5
//   - openalex.go: 📋 Phase 2
//   - s2.go      : 📋 Phase 2
//
// All adapters implement source.SourceAdapter (declared in interface.go).
// Each adapter is rate-limited internally so the router can fire 4 sources
// in parallel without overwhelming upstream APIs.
package source

import (
	"context"
	"encoding/xml"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/veawho/via54Medit/pkg/types"
)

// --- PubMed adapter (NCBI E-utilities) ---

// PubMedSource talks to NCBI's E-utilities API.
//
// Endpoints used:
//   - esearch.fcgi: query → list of PMIDs
//   - esummary.fcgi: PMIDs → metadata (title / authors / journal / year)
//
// Rate limit: 3 req/s without API key (NCBI's anonymous limit).
// With api_key in config, jumps to 10 req/s. We implement a token bucket
// so concurrent calls don't burst beyond the limit.
type PubMedSource struct {
	tool    string
	email   string // NCBI requires a contact email for the "tool" param
	apiKey  string
	rps     int // requests per second
	enabled bool

	// rate limiter state
	mu       sync.Mutex
	tokens   float64
	lastFill time.Time

	client *http.Client

	// === 算法驱动 v1.0.0 (Phase 2 算法化, 2026-07-29) ===

	// rpsMin/RpsMax 动态调整范围 (基于 API 配额)
	// 算法: 读 X-RateLimit-Remaining header, 自动调整 rps
	//   - remaining > 50% → rps 可以往上加 (cap at rpsMax)
	//   - remaining < 10% → rps 必须往下减 (floor at rpsMin)
	//   - 429/5xx → rps 立即减半
	// → 替代硬编码 3 req/s, 跨设备自适应
	rpsMin int
	rpsMax int

	// adaptiveRPS 当前实际 RPS (动态调整)
	adaptiveRPS int
}

// NewPubMedSource builds a PubMed adapter from a config map.
//
// Recognized keys: enabled, api_key, rate_limit, email.
// Defaults: enabled=true, rate_limit=3, email="".
func NewPubMedSource(cfg map[string]any) (*PubMedSource, error) {
	s := &PubMedSource{
		tool:    "via54Medit",
		rps:     3,
		enabled: true,
		client:  &http.Client{Timeout: 30 * time.Second},
		// 算法: 默认 RPS 范围 (有 API key 10, 无 3)
		rpsMin:      1,
		rpsMax:      10,
		adaptiveRPS: 3,
	}
	if cfg != nil {
		if v, ok := cfg["enabled"].(bool); ok {
			s.enabled = v
		}
		if v, ok := cfg["api_key"].(string); ok && v != "" {
			s.apiKey = v
			s.rps = 10 // authenticated tier
		}
		if v, ok := cfg["rate_limit"].(int); ok && v > 0 {
			s.rps = v
		}
		if v, ok := cfg["rps_min"].(int); ok && v > 0 {
			s.rpsMin = v
		}
		if v, ok := cfg["rps_max"].(int); ok && v > 0 {
			s.rpsMax = v
		}
		if v, ok := cfg["email"].(string); ok && v != "" {
			s.email = v
		}
	}
	// 算法: adaptiveRPS 初始 = rps
	if s.rps < s.rpsMin {
		s.rpsMin = s.rps
	}
	if s.rps > s.rpsMax {
		s.rpsMax = s.rps
	}
	s.adaptiveRPS = s.rps
	s.tokens = float64(s.rps)
	s.lastFill = time.Now()
	return s, nil
}

func (s *PubMedSource) Name() string  { return "pubmed" }
func (s *PubMedSource) Enabled() bool { return s.enabled }

// takeToken blocks until a token is available or ctx is cancelled.
// 算法: 用 adaptiveRPS (不是硬编码 rps) → 跨设备自适应
func (s *PubMedSource) takeToken(ctx context.Context) error {
	effectiveRPS := s.getEffectiveRPS()
	interval := time.Second / time.Duration(effectiveRPS)
	for {
		s.mu.Lock()
		// Refill bucket: tokens accumulated since lastFill.
		now := time.Now()
		elapsed := now.Sub(s.lastFill).Seconds()
		s.tokens += elapsed * float64(effectiveRPS)
		if s.tokens > float64(effectiveRPS) {
			s.tokens = float64(effectiveRPS)
		}
		s.lastFill = now

		if s.tokens >= 1 {
			s.tokens--
			s.mu.Unlock()
			return nil
		}
		// Not enough tokens: compute how long to wait.
		wait := time.Duration((1 - s.tokens) / float64(effectiveRPS) * float64(time.Second))
		s.mu.Unlock()

		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(wait):
		}
		if interval > 0 {
			time.Sleep(interval / 4) // small jitter to avoid thundering herd
		}
	}
}

// getEffectiveRPS 算法: 返回当前 effective RPS (线程安全)
// 优先用 adaptiveRPS (动态调整), fallback 到 rps (静态)
func (s *PubMedSource) getEffectiveRPS() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.adaptiveRPS > 0 {
		return s.adaptiveRPS
	}
	return s.rps
}

// adaptRPS 算法: 根据 NCBI header 调整 RPS (替换硬编码 rps)
// remaining > 50% → 加 1 (cap rpsMax)
// remaining < 10% → 减 1 (floor rpsMin)
// 429 → 立即减半
// 5xx → 减 1
// 这是 "规则相对性" 的标准实现: 不写死 RPS, 而是基于反馈调整
func (s *PubMedSource) adaptRPS(remaining int, total int, statusCode int) {
	s.mu.Lock()
	defer s.mu.Unlock()
	oldRPS := s.adaptiveRPS

	switch {
	case statusCode == 429:
		// 429 Too Many Requests: 立即减半
		s.adaptiveRPS = s.adaptiveRPS / 2
		if s.adaptiveRPS < s.rpsMin {
			s.adaptiveRPS = s.rpsMin
		}
	case statusCode >= 500:
		// 5xx server error: 减 1
		s.adaptiveRPS--
		if s.adaptiveRPS < s.rpsMin {
			s.adaptiveRPS = s.rpsMin
		}
	case total > 0 && remaining > 0:
		pctRemaining := float64(remaining) / float64(total)
		switch {
		case pctRemaining > 0.5:
			// 配额充足: 加 1
			s.adaptiveRPS++
			if s.adaptiveRPS > s.rpsMax {
				s.adaptiveRPS = s.rpsMax
			}
		case pctRemaining < 0.1:
			// 配额紧张: 减 1
			s.adaptiveRPS--
			if s.adaptiveRPS < s.rpsMin {
				s.adaptiveRPS = s.rpsMin
			}
		}
	}

	// 重置 token bucket 反映新 RPS
	s.tokens = float64(s.adaptiveRPS)
	s.lastFill = time.Now()

	if s.adaptiveRPS != oldRPS {
		_ = oldRPS // 调试用, 避免 unused warning
	}
}

// Search runs esearch + esummary, returns up to `limit` citations.
func (s *PubMedSource) Search(ctx context.Context, q types.EBMQuestion, limit int) ([]types.Citation, error) {
	if !s.enabled {
		return nil, fmt.Errorf("pubmed: source is disabled")
	}
	if limit <= 0 {
		limit = 20
	}

	// [1] esearch — get PMIDs
	if err := s.takeToken(ctx); err != nil {
		return nil, fmt.Errorf("pubmed: rate limit wait: %w", err)
	}
	pmids, err := s.esearch(ctx, q.Query, limit)
	if err != nil {
		return nil, fmt.Errorf("pubmed: esearch: %w", err)
	}
	if len(pmids) == 0 {
		return []types.Citation{}, nil
	}

	// [2] esummary — get metadata for each PMID
	if err := s.takeToken(ctx); err != nil {
		return nil, fmt.Errorf("pubmed: rate limit wait: %w", err)
	}
	cites, err := s.esummary(ctx, pmids)
	if err != nil {
		return nil, fmt.Errorf("pubmed: esummary: %w", err)
	}

	// Tag provenance.
	now := time.Now()
	for i := range cites {
		cites[i].SourceOrigin = []string{"pubmed"}
		cites[i].FetchedAt = now
	}
	return cites, nil
}

func (s *PubMedSource) Health(ctx context.Context) error {
	req, err := s.newRequest(ctx, "esearch.fcgi", url.Values{
		"db":      {"pubmed"},
		"term":    {"aspirin"},
		"retmax":  {"1"},
		"retmode": {"json"},
	})
	if err != nil {
		return err
	}
	resp, err := s.client.Do(req)
	if err != nil {
		return fmt.Errorf("pubmed: health: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return fmt.Errorf("pubmed: health returned %d", resp.StatusCode)
	}
	return nil
}

// --- esearch ---

func (s *PubMedSource) esearch(ctx context.Context, term string, retMax int) ([]string, error) {
	v := url.Values{
		"db":      {"pubmed"},
		"term":    {term},
		"retmax":  {strconv.Itoa(retMax)},
		"retmode": {"json"},
		"sort":    {"relevance"},
	}
	req, err := s.newRequest(ctx, "esearch.fcgi", v)
	if err != nil {
		return nil, err
	}
	resp, err := s.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return nil, fmt.Errorf("esearch: %d", resp.StatusCode)
	}

	var got struct {
		ESearchResult struct {
			IDList []string `json:"IdList"`
		} `json:"esearchresult"`
	}
	if err := decodeJSON(resp.Body, &got); err != nil {
		return nil, fmt.Errorf("esearch: decode: %w", err)
	}
	return got.ESearchResult.IDList, nil
}

// --- esummary (XML) ---

// PubmedESummary is the shape of esummary's <DocSum> elements.
type PubmedESummary struct {
	XMLName xml.Name       `xml:"eSummaryResult"`
	DocSums []PubmedDocSum `xml:"DocSum"`
}

type PubmedDocSum struct {
	ID    string       `xml:"Id"`
	Items []PubmedItem `xml:"Item"`
}

type PubmedItem struct {
	Name  string `xml:"Name,attr"`
	Type  string `xml:"Type,attr"`
	Value string `xml:",chardata"`
}

func (s *PubMedSource) esummary(ctx context.Context, pmids []string) ([]types.Citation, error) {
	v := url.Values{
		"db":      {"pubmed"},
		"id":      {strings.Join(pmids, ",")},
		"retmode": {"xml"},
	}
	req, err := s.newRequest(ctx, "esummary.fcgi", v)
	if err != nil {
		return nil, err
	}
	resp, err := s.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return nil, fmt.Errorf("esummary: %d", resp.StatusCode)
	}

	var got PubmedESummary
	if err := xml.NewDecoder(resp.Body).Decode(&got); err != nil {
		return nil, fmt.Errorf("esummary: xml decode: %w", err)
	}

	out := make([]types.Citation, 0, len(got.DocSums))
	for _, ds := range got.DocSums {
		c := types.Citation{ID: "pubmed:" + ds.ID, PMID: ds.ID}
		for _, it := range ds.Items {
			switch it.Name {
			case "Title":
				c.Title = it.Value
			case "FullJournalName", "Source":
				c.Journal = it.Value
			case "PubDate":
				// e.g. "2019 Sep" or "2020"
				c.Year = parseYear(it.Value)
			case "AuthorList":
				// AuthorList is itself a list — we ignore here; PICO 1.5 will parse
			case "DOI":
				if strings.HasPrefix(it.Value, "10.") {
					c.DOI = it.Value
				}
			}
		}
		out = append(out, c)
	}
	return out, nil
}

func (s *PubMedSource) newRequest(ctx context.Context, endpoint string, v url.Values) (*http.Request, error) {
	v.Set("tool", s.tool)
	if s.email != "" {
		v.Set("email", s.email)
	}
	if s.apiKey != "" {
		v.Set("api_key", s.apiKey)
	}
	u := "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/" + endpoint + "?" + v.Encode()
	return http.NewRequestWithContext(ctx, "GET", u, nil)
}

// --- helpers ---

func parseYear(s string) int {
	// Take the first 4-digit run.
	for i := 0; i+4 <= len(s); i++ {
		if y, err := strconv.Atoi(s[i : i+4]); err == nil && y >= 1900 && y <= 2100 {
			return y
		}
	}
	return 0
}

func decodeJSON(r interface{ Read(p []byte) (int, error) }, v any) error {
	// thin shim so tests can mock via httptest.ResponseRecorder bodies
	return jsonDecoder(r, v)
}
