package source

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/veawho/via54Medit/pkg/types"
)

func newTestPubMed(t *testing.T) (*PubMedSource, func()) {
	t.Helper()
	s, err := NewPubMedSource(map[string]any{
		"email":      "test@example.com",
		"rate_limit": 100, // high limit so tests are fast
	})
	if err != nil {
		t.Fatal(err)
	}
	return s, func() {}
}

func TestPubMedSourceDefaults(t *testing.T) {
	s, err := NewPubMedSource(nil)
	if err != nil {
		t.Fatal(err)
	}
	if s.Name() != "pubmed" {
		t.Errorf("Name = %q, want pubmed", s.Name())
	}
	if !s.Enabled() {
		t.Error("default enabled should be true")
	}
	if s.rps != 3 {
		t.Errorf("default rps = %d, want 3", s.rps)
	}
}

func TestPubMedSourceAPIKeyUpgradesRPS(t *testing.T) {
	s, _ := NewPubMedSource(map[string]any{"api_key": "test-key"})
	if s.rps != 10 {
		t.Errorf("with api_key rps = %d, want 10", s.rps)
	}
}

func TestPubMedSourceDisabled(t *testing.T) {
	s, _ := NewPubMedSource(map[string]any{"enabled": false})
	if s.Enabled() {
		t.Error("enabled=false should yield Enabled()=false")
	}
	_, err := s.Search(context.Background(), types.EBMQuestion{Query: "x"}, 10)
	if err == nil {
		t.Error("Search on disabled source should fail")
	}
}

func TestParseYear(t *testing.T) {
	cases := []struct {
		in   string
		want int
	}{
		{"2019 Sep", 2019},
		{"2020 Mar 15", 2020},
		{"2021", 2021},
		{"Published 2018-01-01", 2018},
		{"no year here", 0},
		{"99", 0},   // too short
		{"1899", 0}, // below 1900 threshold
	}
	for _, c := range cases {
		if got := parseYear(c.in); got != c.want {
			t.Errorf("parseYear(%q) = %d, want %d", c.in, got, c.want)
		}
	}
}

func TestPubMedEsearchDecoding(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Verify required params are present.
		if r.URL.Query().Get("db") != "pubmed" {
			t.Error("missing db=pubmed")
		}
		if r.URL.Query().Get("email") != "test@example.com" {
			t.Error("missing email param")
		}
		_, _ = w.Write([]byte(`{
			"esearchresult": {
				"idlist": ["31535829", "31535830", "31535831"]
			}
		}`))
	}))
	defer srv.Close()

	// Test the decoder shape by hitting the test server.
	got := struct {
		ESearchResult struct {
			IDList []string `json:"idlist"`
		} `json:"esearchresult"`
	}{}
	resp, err := http.Get(srv.URL + "/esearch.fcgi?db=pubmed&email=test@example.com")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	if err := jsonDecoder(resp.Body, &got); err != nil {
		t.Fatal(err)
	}
	if len(got.ESearchResult.IDList) != 3 {
		t.Errorf("got %d PMIDs, want 3", len(got.ESearchResult.IDList))
	}
}

func TestPubMedEsummaryXMLDecoding(t *testing.T) {
	// Real-ish eSummary response shape.
	xmlData := `<?xml version="1.0"?>
<!DOCTYPE eSummaryResult>
<eSummaryResult>
  <DocSum>
    <Id>31535829</Id>
    <Item Name="Title" Type="String">DAPA-HF Trial: Dapagliflozin in Heart Failure</Item>
    <Item Name="FullJournalName" Type="String">New England Journal of Medicine</Item>
    <Item Name="PubDate" Type="String">2019 Sep 19</Item>
    <Item Name="DOI" Type="String">10.1056/NEJMoa1911303</Item>
  </DocSum>
  <DocSum>
    <Id>31535830</Id>
    <Item Name="Title" Type="String">Another Trial</Item>
    <Item Name="FullJournalName" Type="String">Lancet</Item>
    <Item Name="PubDate" Type="String">2020</Item>
  </DocSum>
</eSummaryResult>`

	var got PubmedESummary
	if err := xmlDecode(strings.NewReader(xmlData), &got); err != nil {
		t.Fatal(err)
	}
	if len(got.DocSums) != 2 {
		t.Fatalf("got %d DocSums, want 2", len(got.DocSums))
	}
	if got.DocSums[0].ID != "31535829" {
		t.Errorf("DocSum[0].ID = %q, want 31535829", got.DocSums[0].ID)
	}
	if got.DocSums[0].Items[0].Value != "DAPA-HF Trial: Dapagliflozin in Heart Failure" {
		t.Errorf("title = %q", got.DocSums[0].Items[0].Value)
	}
}

func TestPubMedRateLimiter(t *testing.T) {
	// With rate_limit=2, 5 sequential calls should take ~2s (5/2 - 1 tokens
	// already available ≈ 1.5s of wait time). This is a smoke test — we
	// just verify the limiter doesn't deadlock or panic, not exact timing.
	s, _ := NewPubMedSource(map[string]any{"rate_limit": 2})
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	var wg sync.WaitGroup
	for i := 0; i < 5; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			if err := s.takeToken(ctx); err != nil {
				t.Errorf("takeToken: %v", err)
			}
		}()
	}
	wg.Wait()
}
