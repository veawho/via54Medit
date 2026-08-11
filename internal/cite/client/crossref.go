package client

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

const (
	CrossrefBaseURL = "https://api.crossref.org"
	CrossrefDelay   = 200 * time.Millisecond
)

// CrossrefClient searches the Crossref REST API for bibliographic metadata.
type CrossrefClient struct {
	baseURL string
	client  *http.Client
	mailto  string
}

// NewCrossrefClient creates a Crossref client.
func NewCrossrefClient(mailto string) *CrossrefClient {
	if mailto == "" {
		mailto = "via54medit@example.com"
	}
	return &CrossrefClient{
		baseURL: CrossrefBaseURL,
		client:  NewDefaultHTTPClient(),
		mailto:  mailto,
	}
}

func (c *CrossrefClient) Name() string { return "crossref" }

// Search returns the top result for a query.
func (c *CrossrefClient) Search(ctx context.Context, query string) (*SearchResult, error) {
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
func (c *CrossrefClient) List(ctx context.Context, query string, limit int) ([]*SearchResult, error) {
	params := url.Values{}
	params.Set("query", query)
	params.Set("rows", strconv.Itoa(limit))
	params.Set("select", "title,author,container-title,published,DOI,type")
	resp, err := c.client.Get(c.baseURL + "/works?" + params.Encode())
	if err != nil {
		return nil, fmt.Errorf("crossref GET: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("crossref HTTP %d", resp.StatusCode)
	}
	var r CrossrefResponse
	if err := json.NewDecoder(resp.Body).Decode(&r); err != nil {
		return nil, fmt.Errorf("crossref decode: %w", err)
	}
	var out []*SearchResult
	for _, item := range r.Message.Items {
		out = append(out, item.toResult(c.Name()))
	}
	return out, nil
}

// --- internal types ---

type CrossrefResponse struct {
	Status  string          `json:"status"`
	Message CrossrefMessage `json:"message"`
}

type CrossrefMessage struct {
	Items []CrossrefItem `json:"items"`
}

type CrossrefItem struct {
	Type           string           `json:"type"`
	Title          []string         `json:"title"`
	Author         []CrossrefAuthor `json:"author"`
	ContainerTitle []string         `json:"container-title"`
	Published      CrossrefDate     `json:"published"`
	DOI            string           `json:"DOI"`
	Score          float64          `json:"score"`
}

type CrossrefAuthor struct {
	Given  string `json:"given"`
	Family string `json:"family"`
}

type CrossrefDate struct {
	DateParts [][]int `json:"date-parts"`
}

func (i *CrossrefItem) toResult(source string) *SearchResult {
	title := ""
	if len(i.Title) > 0 {
		title = i.Title[0]
	}
	authors := make([]string, 0, len(i.Author))
	for _, a := range i.Author {
		if a.Family != "" {
			authors = append(authors, a.Family)
		}
	}
	year := 0
	if len(i.Published.DateParts) > 0 && len(i.Published.DateParts[0]) > 0 {
		year = i.Published.DateParts[0][0]
	}
	journal := ""
	if len(i.ContainerTitle) > 0 {
		journal = i.ContainerTitle[0]
	}
	return &SearchResult{
		Title:   title,
		Authors: strings.Join(authors, ", "),
		Journal: journal,
		Year:    year,
		DOI:     i.DOI,
		Score:   i.Score,
		Source:  source,
	}
}
