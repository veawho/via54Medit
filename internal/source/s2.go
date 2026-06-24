// Package source - Semantic Scholar (S2) adapter.
//
// API docs: https://api.semanticscholar.org/api-docs/
//
// Endpoints used:
//   - GET /paper/search?query=...&limit=20&fields=...   search
//   - GET /paper/{paper_id}                              fetch by ID
//
// Rate limits:
//   - 1 req/s without API key
//   - 100 req/s with API key (registered users)
//
// We use a token bucket with the configured rate. Auth via x-api-key
// header when api_key is set.
package source

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/veawho/via54Medit/pkg/types"
)

// S2Source talks to the Semantic Scholar Graph API.
type S2Source struct {
	apiKey  string
	rps     int
	enabled bool
	client  *http.Client

	mu       sync.Mutex
	tokens   float64
	lastFill time.Time
}

// NewS2Source builds an S2 adapter.
func NewS2Source(cfg map[string]any) (*S2Source, error) {
	s := &S2Source{
		rps:     1, // 1 req/s without api_key is S2's default
		enabled: true,
		client:  &http.Client{Timeout: 30 * time.Second},
	}
	if cfg != nil {
		if v, ok := cfg["enabled"].(bool); ok {
			s.enabled = v
		}
		if v, ok := cfg["api_key"].(string); ok && v != "" {
			s.apiKey = v
			s.rps = 100 // authenticated tier
		}
		if v, ok := cfg["rate_limit"].(int); ok && v > 0 {
			s.rps = v
		}
	}
	s.tokens = float64(s.rps)
	s.lastFill = time.Now()
	return s, nil
}

func (s *S2Source) Name() string  { return "s2" }
func (s *S2Source) Enabled() bool { return s.enabled }

func (s *S2Source) takeToken(ctx context.Context) error {
	interval := time.Second / time.Duration(s.rps)
	for {
		s.mu.Lock()
		now := time.Now()
		elapsed := now.Sub(s.lastFill).Seconds()
		s.tokens += elapsed * float64(s.rps)
		if s.tokens > float64(s.rps) {
			s.tokens = float64(s.rps)
		}
		s.lastFill = now
		if s.tokens >= 1 {
			s.tokens--
			s.mu.Unlock()
			return nil
		}
		wait := time.Duration((1 - s.tokens) / float64(s.rps) * float64(time.Second))
		s.mu.Unlock()
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(wait):
		}
		if interval > 0 {
			time.Sleep(interval / 4)
		}
	}
}

// fields to request — minimum useful set for downstream dedup + ranking.
const s2Fields = "title,abstract,authors,year,venue,externalIds,citationCount,influentialCitationCount,tldr"

// Search queries S2 and returns up to `limit` citations.
func (s *S2Source) Search(ctx context.Context, q types.EBMQuestion, limit int) ([]types.Citation, error) {
	if !s.enabled {
		return nil, fmt.Errorf("s2: source is disabled")
	}
	if limit <= 0 {
		limit = 20
	}
	if err := s.takeToken(ctx); err != nil {
		return nil, fmt.Errorf("s2: rate limit: %w", err)
	}

	v := url.Values{
		"query":  {q.Query},
		"limit":  {strconv.Itoa(limit)},
		"fields": {s2Fields},
	}
	u := "https://api.semanticscholar.org/graph/v1/paper/search?" + v.Encode()
	req, err := http.NewRequestWithContext(ctx, "GET", u, nil)
	if err != nil {
		return nil, fmt.Errorf("s2: new request: %w", err)
	}
	if s.apiKey != "" {
		req.Header.Set("x-api-key", s.apiKey)
	}

	resp, err := s.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("s2: do: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return nil, fmt.Errorf("s2: search %d", resp.StatusCode)
	}

	var got struct {
		Data []s2Paper `json:"data"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&got); err != nil {
		return nil, fmt.Errorf("s2: decode: %w", err)
	}

	cites := make([]types.Citation, 0, len(got.Data))
	now := time.Now()
	for _, p := range got.Data {
		c := p.toCitation()
		c.SourceOrigin = []string{"s2"}
		c.FetchedAt = now
		cites = append(cites, c)
	}
	return cites, nil
}

// Health checks S2 is reachable.
func (s *S2Source) Health(ctx context.Context) error {
	if err := s.takeToken(ctx); err != nil {
		return fmt.Errorf("s2: health: rate limit: %w", err)
	}
	u := "https://api.semanticscholar.org/graph/v1/paper/search?query=test&limit=1&fields=title"
	req, err := http.NewRequestWithContext(ctx, "GET", u, nil)
	if err != nil {
		return err
	}
	if s.apiKey != "" {
		req.Header.Set("x-api-key", s.apiKey)
	}
	resp, err := s.client.Do(req)
	if err != nil {
		return fmt.Errorf("s2: health: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return fmt.Errorf("s2: health returned %d", resp.StatusCode)
	}
	return nil
}

// --- response shape ---

type s2Paper struct {
	PaperID                  string            `json:"paperId"`
	Title                    string            `json:"title"`
	Abstract                 string            `json:"abstract"`
	Year                     int               `json:"year"`
	Venue                    string            `json:"venue"`
	ExternalIDs              map[string]string `json:"externalIds"`
	CitationCount            int               `json:"citationCount"`
	InfluentialCitationCount int               `json:"influentialCitationCount"`
	TLDR                     *struct {
		Text string `json:"text"`
	} `json:"tldr,omitempty"`
	Authors []struct {
		Name string `json:"name"`
	} `json:"authors"`
}

func (p s2Paper) toCitation() types.Citation {
	c := types.Citation{
		ID:      "s2:" + p.PaperID,
		Title:   strings.TrimSpace(p.Title),
		Year:    p.Year,
		Journal: p.Venue,
		CitedBy: p.CitationCount,
		PMID:    p.ExternalIDs["PubMed"],
		DOI:     p.ExternalIDs["DOI"],
	}
	if p.TLDR != nil {
		c.TLDR = p.TLDR.Text
		// Use TLDR as abstract proxy if no abstract.
		if c.Abstract == "" {
			c.Abstract = p.TLDR.Text
		}
	}
	if c.Abstract == "" {
		c.Abstract = p.Abstract
	}
	if len(p.Authors) > 0 {
		c.Authors = make([]string, 0, len(p.Authors))
		for _, a := range p.Authors {
			if a.Name != "" {
				c.Authors = append(c.Authors, a.Name)
			}
		}
	}
	return c
}
