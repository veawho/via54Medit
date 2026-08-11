// Package commands - fulltext subcommand.
//
// fulltext searches publication metadata and downloads open-access full text
// using the tiered FullTextFinder pipeline.
//
// Usage:
//
//	medit fulltext search 10.1038/s41586-021-03621-9
//	medit fulltext download 10.1038/s41586-021-03621-9 --cdp-url ws://localhost:9223
package commands

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/spf13/cobra"
	"github.com/veawho/via54Medit/internal/download"
	"github.com/veawho/via54Medit/internal/foundation"
	"github.com/veawho/via54Medit/pkg/types"
)

var (
	fullTextCDP        string
	fullTextCookies    string
	fullTextOutDir     string
	fullTextWorkers    int
	fullTextCheckpoint string
	fullTextHTML       bool
	fullTextInput      string
)

var fullTextCmd = &cobra.Command{
	Use:   "fulltext",
	Short: "Search and download open-access full text",
	Long: `Search publication metadata and download open-access full text.

The fulltext command has two subcommands:
  - search  <doi|pmid>      query OpenAlex and print metadata/PDF URLs
  - download <doi|pmid>    fetch full text using the tiered FullTextFinder

Examples:
  medit fulltext search "10.1038/s41586-021-03621-9"
  medit fulltext search 31535829
  medit fulltext download "10.1038/s41586-021-03621-9"
  medit fulltext download 31535829 --cdp-url ws://localhost:9223 --cookie-file ~/.medit/scihub_cookies.txt --output-dir ~/.medit/pdfs`,
}

var fullTextSearchCmd = &cobra.Command{
	Use:   "search <doi|pmid>",
	Short: "Query OpenAlex and print metadata plus PDF URLs",
	Args:  cobra.ExactArgs(1),
	RunE:  runFullTextSearch,
}

var fullTextDownloadCmd = &cobra.Command{
	Use:   "download <doi|pmid>",
	Short: "Fetch full text using the tiered FullTextFinder",
	Args:  cobra.ExactArgs(1),
	RunE:  runFullTextDownload,
}

var fullTextBatchCmd = &cobra.Command{
	Use:   "batch <citations.json>",
	Short: "Batch-download full text for a list of citations",
	Long: `Batch-download full text for citations listed in a JSON file.
	
The input file must be a JSON array of objects with at least 'doi' fields.
Example:
  medit fulltext batch citations.json --cdp-url http://localhost:9223 --workers 4 --html`,
	Args: cobra.ExactArgs(1),
	RunE: runFullTextBatch,
}

func init() {
	fullTextSearchCmd.Flags().StringVar(&fullTextCDP, "cdp-url", "", "Chrome CDP websocket (search ignores this)")
	fullTextSearchCmd.Flags().StringVar(&fullTextCookies, "cookie-file", "", "Sci-Hub cookie file (search ignores this)")
	fullTextSearchCmd.Flags().StringVar(&fullTextOutDir, "output-dir", "", "Output directory (search ignores this)")

	fullTextDownloadCmd.Flags().StringVar(&fullTextCDP, "cdp-url", "", "Chrome CDP websocket")
	fullTextDownloadCmd.Flags().StringVar(&fullTextCookies, "cookie-file", "", "Path to sci-hub cookies")
	fullTextDownloadCmd.Flags().StringVar(&fullTextOutDir, "output-dir", "", "Output directory")

	fullTextBatchCmd.Flags().StringVar(&fullTextCDP, "cdp-url", "http://localhost:9223", "Chrome CDP URL")
	fullTextBatchCmd.Flags().StringVar(&fullTextOutDir, "output-dir", "", "Output directory for PDFs")
	fullTextBatchCmd.Flags().StringVar(&fullTextCookies, "cookie-file", "", "Path to sci-hub cookies")
	fullTextBatchCmd.Flags().IntVar(&fullTextWorkers, "workers", 3, "Concurrent download workers")
	fullTextBatchCmd.Flags().StringVar(&fullTextCheckpoint, "checkpoint", "", "Checkpoint file path for resume")
	fullTextBatchCmd.Flags().BoolVar(&fullTextHTML, "html", true, "Generate HTML access report")

	fullTextCmd.AddCommand(fullTextSearchCmd, fullTextDownloadCmd, fullTextBatchCmd)
}

func runFullTextSearch(cmd *cobra.Command, args []string) error {
	identifier := args[0]
	c, err := resolveIdentifierToCitation(cmd.Context(), identifier)
	if err != nil {
		return fmt.Errorf("fulltext search: %w", err)
	}
	if c.Title == "" {
		return fmt.Errorf("fulltext search: no results for %q", identifier)
	}

	out := cmd.OutOrStdout()
	fmt.Fprintf(out, "Title: %s\n", c.Title)
	if len(c.Authors) > 0 {
		fmt.Fprintf(out, "Authors: %s\n", strings.Join(c.Authors, ", "))
	}
	if c.Journal != "" {
		fmt.Fprintf(out, "Journal: %s\n", c.Journal)
	}
	if c.Year > 0 {
		fmt.Fprintf(out, "Year: %d\n", c.Year)
	}
	if c.DOI != "" {
		fmt.Fprintf(out, "DOI: %s\n", c.DOI)
	}
	if c.PMID != "" {
		fmt.Fprintf(out, "PMID: %s\n", c.PMID)
	}
	fmt.Fprintln(out, "PDF URLs:")
	pdfs := deduplicateStrings(nonEmptyStrings(citePDFURLs(c)))
	if len(pdfs) == 0 {
		fmt.Fprintln(out, "  (none)")
	}
	for i, u := range pdfs {
		fmt.Fprintf(out, "  %d. %s\n", i+1, u)
	}
	return nil
}

func runFullTextDownload(cmd *cobra.Command, args []string) error {
	identifier := args[0]
	cfg := loadFullTextConfig()
	c, err := resolveIdentifierToCitation(cmd.Context(), identifier)
	if err != nil {
		return fmt.Errorf("fulltext download: %w", err)
	}
	if c.Title == "" && c.DOI == "" {
		return fmt.Errorf("fulltext download: could not resolve %q", identifier)
	}

	ctx, cancel := context.WithTimeout(cmd.Context(), 180*time.Second)
	defer cancel()

	finder := &download.FullTextFinder{
		ChromeCDP:   cfg.ChromeCDP,
		CookieFile:  cfg.CookieFile,
		OutDir:      cfg.OutputDir,
		SpringerRPS: cfg.SpringerRPS,
		ApiRPS:      cfg.ApiRPS,
	}

	result, err := finder.Get(ctx, c)
	if result == nil {
		return fmt.Errorf("fulltext download: no result (nil) for %q", identifier)
	}
	out := cmd.OutOrStdout()
	fmt.Fprintf(out, "Fetched full text for: %s\n", c.Title)
	fmt.Fprintf(out, "Tier: %d\n", result.Tier)
	fmt.Fprintf(out, "Duration: %s\n", result.Duration)
	fmt.Fprintf(out, "Used: %s\n", strings.Join(result.Used, ", "))
	if result.Format != "" {
		fmt.Fprintf(out, "Format: %s\n", result.Format)
	}
	if result.Size > 0 {
		fmt.Fprintf(out, "Size: %d bytes\n", result.Size)
	}
	fmt.Fprintln(out, "Status:")
	if err == nil && result.Path != "" {
		fmt.Fprintf(out, "  success: %s\n", result.Path)
	} else if result.Path != "" {
		fmt.Fprintf(out, "  partial success: %s (first error: %v)\n", result.Path, err)
	} else {
		fmt.Fprintf(out, "  failed: %v\n", err)
	}
	return nil
}

func runFullTextBatch(cmd *cobra.Command, args []string) error {
	inputFile := args[0]

	// Read input JSON
	raw, err := os.ReadFile(inputFile)
	if err != nil {
		return fmt.Errorf("batch: read %s: %w", inputFile, err)
	}

	var input []struct {
		DOI   string `json:"doi"`
		PMID  string `json:"pmid,omitempty"`
		Title string `json:"title,omitempty"`
	}
	if err := json.Unmarshal(raw, &input); err != nil {
		return fmt.Errorf("batch: parse %s: %w", inputFile, err)
	}

	if len(input) == 0 {
		return fmt.Errorf("batch: no citations in %s", inputFile)
	}

	// Convert to types.Citation slice
	citations := make([]types.Citation, len(input))
	for i, v := range input {
		citations[i] = types.Citation{
			DOI:   v.DOI,
			PMID:  v.PMID,
			Title: v.Title,
		}
	}

	out := cmd.OutOrStdout()
	fmt.Fprintf(out, "📄 Batch download: %d citations, %d workers\n", len(citations), fullTextWorkers)

	// Resolve output directory
	outDir := fullTextOutDir
	if outDir == "" {
		home, _ := os.UserHomeDir()
		if home == "" {
			home = "/tmp"
		}
		outDir = filepath.Join(home, ".medit", "pdfs")
	}
	_ = os.MkdirAll(outDir, 0o700)

	// Set up FullTextFinder
	finder := download.NewFullTextFinder(fullTextCDP)
	if fullTextCookies != "" {
		finder.CookieFile = fullTextCookies
	}
	if outDir != "" {
		finder.OutDir = outDir
	}
	defer finder.Close()

	// Run batch
	ctx, cancel := context.WithTimeout(cmd.Context(), 30*time.Minute)
	defer cancel()

	cfg := download.BatchConfig{
		WorkerCount:    fullTextWorkers,
		CheckpointPath: fullTextCheckpoint,
		GenerateHTML:   fullTextHTML,
		SkipDoneCheck:  false,
	}

	// Set HTML report path inside output dir
	if fullTextHTML {
		_ = os.MkdirAll(outDir, 0o700)
	}

	result, err := finder.BatchDownload(ctx, citations, cfg)
	if err != nil {
		return fmt.Errorf("batch: %w", err)
	}

	// Print report
	fmt.Fprintf(out, "\n📊 Results:\n")
	fmt.Fprintf(out, "  ✅ %d success\n", result.Successes)
	fmt.Fprintf(out, "  ❌ %d failed\n", result.Failures)
	fmt.Fprintf(out, "  ⏭️ %d skipped\n", result.Skipped)
	fmt.Fprintf(out, "  ⏱️ %s\n", time.Duration(result.Duration).Round(time.Second).String())

	if fullTextHTML {
		reportPath := filepath.Join(outDir, "citation_access.html")
		fmt.Fprintf(out, "  📁 Report: %s\n", reportPath)
	}

	// Show validations for failed items
	var failures int
	for _, item := range result.Items {
		if item.Err != nil {
			failures++
			if failures <= 5 {
				fmt.Fprintf(out, "  ❌ %s: %v\n", item.DOI, item.Err)
			}
		}
	}
	if failures > 5 {
		fmt.Fprintf(out, "  ... and %d more failures\n", failures-5)
	}

	return nil
}

func loadFullTextConfig() fullTextConfig {
	cfg := foundation.NewDefaultConfig()
	d := fullTextConfig{
		ChromeCDP:   "ws://localhost:9223",
		CookieFile:  "~/.medit/scihub_cookies.txt",
		OutputDir:   "~/.medit/pdfs",
		SpringerRPS: 0.5,
		ApiRPS:      1.0,
	}
	if section := cfg.Get("download"); section != nil {
		if b, exists := section["enabled"]; exists {
			d.Enabled = b.(bool)
		}
		if s, exists := section["chrome_cdp"]; exists {
			if ss, ok := s.(string); ok {
				d.ChromeCDP = ss
			}
		}
		if s, exists := section["cookie_file"]; exists {
			if ss, ok := s.(string); ok {
				d.CookieFile = ss
			}
		}
		if s, exists := section["output_dir"]; exists {
			if ss, ok := s.(string); ok {
				d.OutputDir = ss
			}
		}
		if s, exists := section["springer_rps"]; exists {
			switch v := s.(type) {
			case float64:
				d.SpringerRPS = v
			case int:
				d.SpringerRPS = float64(v)
			}
		}
		if s, exists := section["api_rps"]; exists {
			switch v := s.(type) {
			case float64:
				d.ApiRPS = v
			case int:
				d.ApiRPS = float64(v)
			}
		}
	}
	d.CookieFile = expandPath(d.CookieFile)
	d.OutputDir = expandPath(d.OutputDir)
	return d
}

type fullTextConfig struct {
	Enabled     bool
	ChromeCDP   string
	CookieFile  string
	OutputDir   string
	SpringerRPS float64
	ApiRPS      float64
}

func resolveIdentifierToCitation(ctx context.Context, identifier string) (*types.Citation, error) {
	if isDOI(identifier) {
		httpCite, err := openAlexWorkByDOI(ctx, identifier)
		if err == nil && httpCite != nil {
			return httpCite, nil
		}
	}

	httpCite, err := openAlexWorkByPMID(ctx, identifier)
	if err == nil && httpCite != nil {
		return httpCite, nil
	}

	return nil, fmt.Errorf("no publication found")
}

func isDOI(identifier string) bool {
	return strings.HasPrefix(identifier, "10.")
}

func openAlexWorkByDOI(ctx context.Context, doi string) (*types.Citation, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", fmt.Sprintf("https://api.openalex.org/works/https://doi.org/%s", url.PathEscape(doi)), nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "via54Medit/1.0")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("openalex HTTP %d", resp.StatusCode)
	}
	var work httpWork
	if err := json.NewDecoder(resp.Body).Decode(&work); err != nil {
		return nil, err
	}
	return httpWorkToCitation(&work), nil
}

func openAlexWorkByPMID(ctx context.Context, pmid string) (*types.Citation, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", fmt.Sprintf("https://api.openalex.org/works?filter=pmid:%s&per-page=1", url.PathEscape(pmid)), nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "via54Medit/1.0")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("openalex HTTP %d", resp.StatusCode)
	}
	var body httpWorkList
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return nil, err
	}
	if len(body.Results) == 0 {
		return nil, fmt.Errorf("no results")
	}
	return httpWorkToCitation(&body.Results[0]), nil
}

func citePDFURLs(c *types.Citation) []string {
	var urls []string
	if c.OAPDFURL != "" {
		urls = append(urls, c.OAPDFURL)
	}
	if c.SciHubURL != "" {
		urls = append(urls, c.SciHubURL)
	}
	return urls
}

func nonEmptyStrings(ss []string) []string {
	var out []string
	for _, s := range ss {
		if strings.TrimSpace(s) != "" {
			out = append(out, s)
		}
	}
	return out
}

func deduplicateStrings(ss []string) []string {
	seen := make(map[string]struct{}, len(ss))
	var out []string
	for _, s := range ss {
		if _, ok := seen[s]; !ok {
			seen[s] = struct{}{}
			out = append(out, s)
		}
	}
	return out
}

func expandPath(p string) string {
	if strings.HasPrefix(p, "~/") {
		home := os.Getenv("HOME")
		if home == "" {
			home = os.Getenv("USERPROFILE")
		}
		if home != "" {
			return filepath.Join(home, p[2:])
		}
	}
	return p
}

type httpWork struct {
	Id          string `json:"id"`
	Title       string `json:"title"`
	Authorships []struct {
		Author struct {
			Name string `json:"name"`
		} `json:"author"`
	} `json:"authorships"`
	PrimaryLocation struct {
		Source struct {
			Name string `json:"name"`
		} `json:"source"`
		IsOa   bool    `json:"is_oa"`
		PdfUrl *string `json:"pdf_url"`
	} `json:"primary_location"`
	Locations []struct {
		Source struct {
			Name string `json:"name"`
		} `json:"source"`
		IsOa   bool    `json:"is_oa"`
		PdfUrl *string `json:"pdf_url"`
		PMCID  string  `json:"pmcid"`
	} `json:"locations"`
	PublicationYear int    `json:"publication_year"`
	DOI             string `json:"doi"`
}

type httpWorkList struct {
	Results []httpWork `json:"results"`
}

func httpWorkToCitation(w *httpWork) *types.Citation {
	c := &types.Citation{
		Title:   w.Title,
		DOI:     w.DOI,
		Year:    w.PublicationYear,
		Journal: w.PrimaryLocation.Source.Name,
	}
	for _, a := range w.Authorships {
		if a.Author.Name != "" {
			c.Authors = append(c.Authors, a.Author.Name)
		}
	}
	if w.PrimaryLocation.PdfUrl != nil {
		c.OAPDFURL = *w.PrimaryLocation.PdfUrl
	}
	for _, loc := range w.Locations {
		if loc.PdfUrl != nil {
			c.OAPDFURL = *loc.PdfUrl
		}
		if loc.PMCID != "" {
			c.PMID = loc.PMCID
		}
		if loc.Source.Name != "" {
			c.Journal = loc.Source.Name
		}
	}
	return c
}
