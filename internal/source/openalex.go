// Package source - OpenAlex adapter.
//
// OpenAlex is a free, open catalog of 200M+ scholarly works.
// API docs: https://docs.openalex.org/
//
// Endpoints used:
//   - GET /works?search=...&per_page=20&mailto=...   search by free text
//   - GET /works/{openalex_id}                       fetch by ID
//
// Rate limits: 10 req/s with a polite email in `mailto=`; otherwise
// throttled. We use a token-bucket rate limiter similar to PubMed.
//
// Identity model: OpenAlex IDs look like "W2741809807" (prefix W).
// They also surface DOI, PMID, and MAG IDs for cross-source dedup.
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

// OpenAlexSource talks to the OpenAlex REST API.
type OpenAlexSource struct {
	email   string
	rps     int
	enabled bool
	client  *http.Client

	// rate limiter (same pattern as PubMed)
	mu       sync.Mutex
	tokens   float64
	lastFill time.Time
}

// NewOpenAlexSource builds an OpenAlex adapter from a config map.
//
// Recognized keys: enabled, email, rate_limit.
// Defaults: enabled=true, rate_limit=10, email="".
func NewOpenAlexSource(cfg map[string]any) (*OpenAlexSource, error) {
	s := &OpenAlexSource{
		rps:     10,
		enabled: true,
		client:  &http.Client{Timeout: 30 * time.Second},
	}
	if cfg != nil {
		if v, ok := cfg["enabled"].(bool); ok {
			s.enabled = v
		}
		if v, ok := cfg["email"].(string); ok {
			s.email = v
		}
		if v, ok := cfg["rate_limit"].(int); ok && v > 0 {
			s.rps = v
		}
	}
	s.tokens = float64(s.rps)
	s.lastFill = time.Now()
	return s, nil
}

func (s *OpenAlexSource) Name() string  { return "openalex" }
func (s *OpenAlexSource) Enabled() bool { return s.enabled }

// takeToken mirrors PubMed's token-bucket rate limiter.
func (s *OpenAlexSource) takeToken(ctx context.Context) error {
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

// Health checks OpenAlex is reachable.
func (s *OpenAlexSource) Health(ctx context.Context) error {
	req, err := s.newRequest(ctx, "/works?per_page=1&search=test")
	if err != nil {
		return err
	}
	resp, err := s.client.Do(req)
	if err != nil {
		return fmt.Errorf("openalex: health: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return fmt.Errorf("openalex: health returned %d", resp.StatusCode)
	}
	return nil
}

// Search queries OpenAlex and returns up to `limit` citations.
func (s *OpenAlexSource) Search(ctx context.Context, q types.EBMQuestion, limit int) ([]types.Citation, error) {
	if !s.enabled {
		return nil, fmt.Errorf("openalex: source is disabled")
	}
	if limit <= 0 {
		limit = 20
	}
	if err := s.takeToken(ctx); err != nil {
		return nil, fmt.Errorf("openalex: rate limit: %w", err)
	}

	v := url.Values{
		"search":   {q.Query},
		"per_page": {strconv.Itoa(limit)},
	}
	path := "/works?" + v.Encode()
	req, err := s.newRequest(ctx, path)
	if err != nil {
		return nil, err
	}
	resp, err := s.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("openalex: search: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return nil, fmt.Errorf("openalex: search %d", resp.StatusCode)
	}

	var got struct {
		Results []openAlexWork `json:"results"`
		Meta    struct {
			Count int `json:"count"`
		} `json:"meta"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&got); err != nil {
		return nil, fmt.Errorf("openalex: decode: %w", err)
	}

	cites := make([]types.Citation, 0, len(got.Results))
	now := time.Now()
	for _, w := range got.Results {
		c := w.toCitation()
		c.SourceOrigin = []string{"openalex"}
		c.FetchedAt = now
		cites = append(cites, c)
	}
	return cites, nil
}

func (s *OpenAlexSource) newRequest(ctx context.Context, path string) (*http.Request, error) {
	u := "https://api.openalex.org" + path
	if s.email != "" {
		sep := "?"
		if strings.Contains(path, "?") {
			sep = "&"
		}
		u += sep + "mailto=" + url.QueryEscape(s.email)
	}
	return http.NewRequestWithContext(ctx, "GET", u, nil)
}

// --- OpenAlex response shape (subset) ---

type openAlexWork struct {
	ID              string         `json:"id"`  // full URL like "https://openalex.org/W2741809807"
	DOI             string         `json:"doi"` // "https://doi.org/10.1056/NEJMoa1911303" or null
	Title           string         `json:"title"`
	DisplayName     string         `json:"display_name"`
	PublicationYear int            `json:"publication_year"`
	PublicationDate string         `json:"publication_date"`
	Authorships     []openAlexAuth `json:"authorships"`
	PrimaryLocation struct {
		Source struct {
			DisplayName string `json:"display_name"`
		} `json:"source"`
	} `json:"primary_location"`
	PMID         string  `json:"pmid"` // "https://pubmed.ncbi.nlm.nih.gov/31535829" or null
	CitedByCount int     `json:"cited_by_count"`
	FWCI         float64 `json:"fwci"`
	Abstract     *struct {
		InvertedIndex map[string][]int `json:"inverted_index"`
	} `json:"abstract_inverted_index,omitempty"`
}

type openAlexAuth struct {
	Author struct {
		DisplayName string `json:"display_name"`
	} `json:"author"`
}

// toCitation converts an openAlexWork to a types.Citation.
func (w openAlexWork) toCitation() types.Citation {
	c := types.Citation{
		ID:      "openalex:" + extractOpenAlexID(w.ID),
		Title:   strings.TrimSpace(w.Title),
		Year:    w.PublicationYear,
		DOI:     stripDOIPrefix(w.DOI),
		PMID:    extractPMIDFromURL(w.PMID),
		FWCI:    w.FWCI,
		CitedBy: w.CitedByCount,
	}
	if w.PrimaryLocation.Source.DisplayName != "" {
		c.Journal = w.PrimaryLocation.Source.DisplayName
	}
	if w.Authorships != nil {
		c.Authors = make([]string, 0, len(w.Authorships))
		for _, a := range w.Authorships {
			if a.Author.DisplayName != "" {
				c.Authors = append(c.Authors, a.Author.DisplayName)
			}
		}
	}
	if w.Abstract != nil && w.Abstract.InvertedIndex != nil {
		c.Abstract = reconstructAbstract(w.Abstract.InvertedIndex)
	}
	return c
}

// extractOpenAlexID pulls the "W..." part from a full ID URL.
func extractOpenAlexID(id string) string {
	if idx := strings.LastIndex(id, "/"); idx >= 0 {
		return id[idx+1:]
	}
	return id
}

// stripDOIPrefix returns "10.1056/NEJMoa..." from "https://doi.org/10.1056/NEJMoa..."
func stripDOIPrefix(doi string) string {
	if doi == "" {
		return ""
	}
	if idx := strings.Index(doi, "doi.org/"); idx >= 0 {
		return doi[idx+len("doi.org/"):]
	}
	return doi
}

// extractPMIDFromURL returns "31535829" from "https://pubmed.ncbi.nlm.nih.gov/31535829"
func extractPMIDFromURL(pmidURL string) string {
	if pmidURL == "" {
		return ""
	}
	if idx := strings.LastIndex(pmidURL, "/"); idx >= 0 {
		return pmidURL[idx+1:]
	}
	return pmidURL
}

// reconstructAbstract reverses OpenAlex's inverted index format.
// Input: {"heart": [0, 5], "failure": [3]} → "heart failure heart"
// (approximate; OpenAlex's format is a token → positions map).
// We join unique tokens in position order to get a readable string.
func reconstructAbstract(idx map[string][]int) string {
	if len(idx) == 0 {
		return ""
	}
	// Position → token
	pos := make(map[int]string, len(idx))
	for word, positions := range idx {
		for _, p := range positions {
			pos[p] = word
		}
	}
	// Build ordered list of positions
	positions := make([]int, 0, len(pos))
	for p := range pos {
		positions = append(positions, p)
	}
	sortInts(positions)
	// Join
	parts := make([]string, 0, len(positions))
	for _, p := range positions {
		parts = append(parts, pos[p])
	}
	return strings.Join(parts, " ")
}

// sortInts is a small insertion sort to avoid importing "sort" in this file.
func sortInts(s []int) {
	for i := 1; i < len(s); i++ {
		for j := i; j > 0 && s[j-1] > s[j]; j-- {
			s[j-1], s[j] = s[j], s[j-1]
		}
	}
}
