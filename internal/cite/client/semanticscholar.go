package client

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

const (
	SemSchBaseURL = "https://api.semanticscholar.org/graph/v1"
	SemSchDelay   = 150 * time.Millisecond
)

// SemSchClient queries the Semantic Scholar API for citation metadata.
type SemSchClient struct {
	baseURL string
	apiKey  string
	client  *http.Client
}

// NewSemSchClient creates a Semantic Scholar client.
func NewSemSchClient() *SemSchClient {
	apiKey := os.Getenv("SEMANTIC_SCHOLAR_API_KEY")
	return &SemSchClient{
		baseURL: SemSchBaseURL,
		apiKey:  apiKey,
		client:  NewDefaultHTTPClient(),
	}
}

func (c *SemSchClient) Name() string { return "semanticscholar" }

// Search returns the top result for a query.
func (c *SemSchClient) Search(ctx context.Context, query string) (*SearchResult, error) {
	results, err := c.List(ctx, query, 1)
	if err != nil {
		return nil, err
	}
	if len(results) == 0 {
		return nil, nil
	}
	return results[0], nil
}

// List returns up to limit results for a query.
func (c *SemSchClient) List(ctx context.Context, query string, limit int) ([]*SearchResult, error) {
	params := url.Values{}
	params.Set("query", query)
	params.Set("limit", strconv.Itoa(limit))
	params.Set("fields", "title,authors,venue,year,externalIds,citationCount")
	url := c.baseURL + "/paper/search?" + params.Encode()
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return nil, fmt.Errorf("semanticscholar req: %w", err)
	}
	if c.apiKey != "" {
		req.Header.Set("x-api-key", c.apiKey)
	}
	resp, err := c.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("semanticscholar GET: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("semanticscholar HTTP %d", resp.StatusCode)
	}
	var r SemSchResponse
	if err := json.NewDecoder(resp.Body).Decode(&r); err != nil {
		return nil, fmt.Errorf("semanticscholar decode: %w", err)
	}
	var out []*SearchResult
	for _, p := range r.Data {
		out = append(out, p.toResult(c.Name()))
	}
	return out, nil
}

// --- internal types ---

type SemSchResponse struct {
	Data  []SemSchPaper `json:"data"`
	Total int           `json:"total"`
}

type SemSchPaper struct {
	Title         string            `json:"title"`
	Authors       []SemSchAuthor    `json:"authors"`
	Venue         string            `json:"venue"`
	Year          int               `json:"year"`
	ExternalIds   map[string]string `json:"externalIds"`
	CitationCount int               `json:"citationCount"`
}

type SemSchAuthor struct {
	Name string `json:"name"`
}

func (p *SemSchPaper) toResult(source string) *SearchResult {
	authors := make([]string, 0, len(p.Authors))
	for _, a := range p.Authors {
		authors = append(authors, a.Name)
	}
	pmid := ""
	if v, ok := p.ExternalIds["PMID"]; ok {
		pmid = v
	}
	doi := ""
	if v, ok := p.ExternalIds["DOI"]; ok {
		doi = v
	}
	return &SearchResult{
		Title:   p.Title,
		Authors: strings.Join(authors, ", "),
		Journal: p.Venue,
		Year:    p.Year,
		PMID:    pmid,
		DOI:     doi,
		Score:   float64(p.CitationCount),
		Source:  source,
	}
}
