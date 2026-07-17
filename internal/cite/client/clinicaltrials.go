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
	ClinTrialsBaseURL = "https://clinicaltrials.gov/api/v2"
	ClinTrialsDelay   = 100 * time.Millisecond
)

// ClinTrialsClient queries the ClinicalTrials.gov API v2.
type ClinTrialsClient struct {
	baseURL string
	client  *http.Client
}

// NewClinTrialsClient creates a ClinicalTrials client.
func NewClinTrialsClient() *ClinTrialsClient {
	return &ClinTrialsClient{
		baseURL: ClinTrialsBaseURL,
		client:  NewDefaultHTTPClient(),
	}
}

func (c *ClinTrialsClient) Name() string { return "clinicaltrials" }

// Search returns the top trial for a query.
func (c *ClinTrialsClient) Search(ctx context.Context, query string) (*SearchResult, error) {
	results, err := c.List(ctx, query, 1)
	if err != nil {
		return nil, err
	}
	if len(results) == 0 {
		return nil, nil
	}
	return results[0], nil
}

// List returns up to limit trials for a query.
func (c *ClinTrialsClient) List(ctx context.Context, query string, limit int) ([]*SearchResult, error) {
	params := url.Values{}
	params.Set("query.term", query)
	params.Set("pageSize", strconv.Itoa(minInt(limit, 50)))
	params.Set("format", "json")
	params.Set("countTotal", "true")
	time.Sleep(ClinTrialsDelay)
	reqURL := c.baseURL + "/studies?" + params.Encode()
	req, err := http.NewRequestWithContext(ctx, "GET", reqURL, nil)
	if err != nil {
		return nil, fmt.Errorf("clinicaltrials: new request: %w", err)
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", "via54Medit/1.0")
	resp, err := c.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("clinicaltrials: request: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return nil, fmt.Errorf("clinicaltrials: HTTP %d", resp.StatusCode)
	}
	var ctResp struct {
		Studies []map[string]interface{} `json:"studies"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&ctResp); err != nil {
		return nil, fmt.Errorf("clinicaltrials: decode: %w", err)
	}
	results := make([]*SearchResult, 0, len(ctResp.Studies))
	for _, study := range ctResp.Studies {
		r := &SearchResult{Source: c.Name()}
		if protocol, ok := study["protocolSection"]; ok {
			protocolMap := protocol.(map[string]interface{})
			if id, ok := protocolMap["identificationModule"]; ok {
				idMap := id.(map[string]interface{})
				if nct, ok := idMap["nctId"]; ok {
					r.DOI = nct.(string)
				}
				if title, ok := idMap["briefTitle"]; ok {
					r.Title = title.(string)
				}
				if status, ok := idMap["overallStatus"]; ok {
					r.Authors = status.(string)
				}
			}
			if design, ok := protocolMap["designModule"]; ok {
				designMap := design.(map[string]interface{})
				if phases, ok := designMap["phases"]; ok {
					if pArr, ok := phases.([]interface{}); ok && len(pArr) > 0 {
						r.Journal = fmt.Sprintf("%v", pArr[0])
					}
				}
			}
		}
		conditions := []string{}
		if rm, ok := study["conditions"]; ok {
			if rmSlice, ok := rm.([]interface{}); ok {
				for _, c := range rmSlice {
					conditions = append(conditions, c.(string))
				}
			}
		}
		r.Journal = r.Journal + " | " + strings.Join(conditions, ", ")
		results = append(results, r)
	}
	return results, nil
}

// GetByNCT gets full study by NCT ID.
func (c *ClinTrialsClient) GetByNCT(ctx context.Context, nctID string) (*SearchResult, error) {
	params := url.Values{}
	params.Set("filter.overallStatus", "*")
	params.Set("pageSize", "1")
	reqURL := c.baseURL + "/studies/" + nctID + "?" + params.Encode()
	req, err := http.NewRequestWithContext(ctx, "GET", reqURL, nil)
	if err != nil {
		return nil, fmt.Errorf("clinicaltrials: new request: %w", err)
	}
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", "via54Medit/1.0")
	resp, err := c.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("clinicaltrials: request: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return nil, fmt.Errorf("clinicaltrials: HTTP %d", resp.StatusCode)
	}
	var r struct {
		Study map[string]interface{} `json:"study"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&r); err != nil {
		return nil, fmt.Errorf("clinicaltrials: decode: %w", err)
	}
	return &SearchResult{DOI: nctID, Title: "ClinicalTrials.gov study", Source: c.Name()}, nil
}

// minInt returns the smaller of two ints.
func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}
