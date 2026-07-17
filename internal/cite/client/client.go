package client

import (
	"context"
	"net/http"
	"time"
)

// SearchResult is the common output type across all citation search backends.
type SearchResult struct {
	Title   string  `json:"title"`
	Authors string  `json:"authors"`
	Journal string  `json:"journal"`
	Year    int     `json:"year"`
	PMID    string  `json:"pmid"`
	DOI     string  `json:"doi"`
	Score   float64 `json:"score"`
	Source  string  `json:"source"`
}

// SourceName is a constant source identifier.
type SourceName string

const (
	SourcePubMed     SourceName = "pubmed"
	SourceCrossref   SourceName = "crossref"
	SourceSemScholar SourceName = "semanticscholar"
	SourceClinTrials SourceName = "clinicaltrials"
	SourceAntafu     SourceName = "antafu"
)

// Searcher is the unified interface for all citation search backends.
type Searcher interface {
	Name() string
	Search(ctx context.Context, query string) (*SearchResult, error)
	List(ctx context.Context, query string, limit int) ([]*SearchResult, error)
}

// NewDefaultHTTPClient returns an http.Client with a 30-second timeout.
func NewDefaultHTTPClient() *http.Client {
	return &http.Client{Timeout: 30 * time.Second}
}
