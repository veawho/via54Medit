// Package download provides layered full-text acquisition.
//
// batch.go — batch download with checkpoint/resume, DOI-aware tier selection,
// worker pool, and HTML report generation.
package download

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/veawho/via54Medit/internal/source"
	"github.com/veawho/via54Medit/pkg/types"
)

// BatchConfig controls how batch download behaves.
type BatchConfig struct {
	// WorkerCount is the number of concurrent downloads (0 = serial).
	WorkerCount int

	// CheckpointPath enables checkpoint/resume when non-empty.
	// Every processed item is recorded; interrupt-safe.
	CheckpointPath string

	// OutputDir for downloaded files. If empty, uses FullTextFinder.OutDir.
	OutputDir string

	// CDPURL overrides FullTextFinder.ChromeCDP. If empty, uses existing value.
	CDPURL string

	// GenerateHTML generates citation_access.html after batch completes.
	GenerateHTML bool

	// SkipDoneCheck skips the checkpoint IsDone check (force re-download).
	SkipDoneCheck bool
}

// BatchResult holds the aggregate outcome of a batch download.
type BatchResult struct {
	Total     int
	Successes int
	Failures  int
	Skipped   int
	Duration  time.Duration
	Items     []BatchItem
}

// BatchItem is the outcome of one citation in a batch.
type BatchItem struct {
	DOI     string
	Title   string
	Path    string
	Tier    int
	Size    int64
	Err     error
	Skipped bool
}

// ----------------------------------------------------------------
// BatchDownload
// ----------------------------------------------------------------

// BatchDownload runs the full tiered download pipeline for every
// citation in the slice.  It respects checkpoint state so an
// interrupted run can be resumed.
func (f *FullTextFinder) BatchDownload(ctx context.Context, citations []types.Citation, cfg BatchConfig) (*BatchResult, error) {
	start := time.Now()
	res := &BatchResult{
		Total: len(citations),
	}

	if cfg.OutputDir != "" {
		f.OutDir = cfg.OutputDir
	}
	if cfg.CDPURL != "" {
		f.ChromeCDP = cfg.CDPURL
	}

	_ = os.MkdirAll(f.OutDir, 0o700)

	// Set up checkpoint
	var cp *Checkpoint
	if cfg.CheckpointPath != "" {
		var err error
		cp, err = NewCheckpoint(cfg.CheckpointPath, len(citations))
		if err != nil {
			return nil, fmt.Errorf("batch: checkpoint: %w", err)
		}
	}

	// Worker pool
	work := make(chan int, len(citations))
	results := make(chan BatchItem, len(citations))
	var wg sync.WaitGroup

	workers := cfg.WorkerCount
	if workers < 1 {
		workers = 1
	}

	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for idx := range work {
				itemCtx, itemCancel := context.WithTimeout(ctx, 180*time.Second)
				bi := f.processOne(itemCtx, &citations[idx], cp, cfg.SkipDoneCheck)
				itemCancel()
				results <- bi
			}
		}()
	}

	// Feed work
	go func() {
		for i := 0; i < len(citations); i++ {
			work <- i
		}
		close(work)
		wg.Wait()
		close(results)
	}()

	// Collect results
	for bi := range results {
		res.Items = append(res.Items, bi)
		switch {
		case bi.Skipped:
			res.Skipped++
		case bi.Err != nil || bi.Path == "":
			res.Failures++
		default:
			res.Successes++
		}
	}

	res.Duration = time.Since(start)

	// Generate HTML report
	if cfg.GenerateHTML {
		reportPath := filepath.Join(f.OutDir, "citation_access.html")
		if err := generateReport(res, reportPath); err != nil {
			// non-fatal
			_ = err
		}
	}

	return res, nil
}

// processOne handles a single citation through DOI-aware tier selection.
func (f *FullTextFinder) processOne(ctx context.Context, c *types.Citation, cp *Checkpoint, force bool) BatchItem {
	bi := BatchItem{
		DOI:   c.DOI,
		Title: c.Title,
	}

	// Checkpoint skip
	if cp != nil && !force && cp.IsDone(c.DOI) {
		bi.Skipped = true
		return bi
	}

	// DOI classification → strategy hint
	contentType := ClassifyDOI(c.DOI)

	// For charts/figures/replies: skip OA metadata lookup, go straight to CDP print
	// For research papers: use full tiered pipeline
	var result *FullTextResult
	var err error

	switch contentType {
	case ContentChartFigure, ContentAuthorReply, ContentSupplementary:
		if f.ChromeCDP != "" {
			cdr := f.tier2CDP(ctx, c, &tier1Meta{})
			if cdr.path != "" {
				result = &FullTextResult{
					Citation: c,
					Path:     cdr.path,
					Tier:     2,
					Format:   cdr.format,
					Size:     cdr.size,
					Used:     cdr.used,
				}
			}
		}
	default:
		result, err = f.Get(ctx, c)
	}

	if result != nil && result.Path != "" {
		bi.Path = result.Path
		bi.Tier = result.Tier
		bi.Size = result.Size

		if cp != nil {
			cp.RecordSuccess(CheckpointItem{
				DOI:    c.DOI,
				PMID:   c.PMID,
				Title:  c.Title,
				Status: "ok",
				Path:   result.Path,
				Tier:   result.Tier,
				Size:   result.Size,
			})
		}
	} else {
		bi.Err = err
		if err == nil {
			bi.Err = fmt.Errorf("all tiers failed")
		}

		if cp != nil {
			cp.RecordFailure(CheckpointItem{
				DOI:    c.DOI,
				PMID:   c.PMID,
				Title:  c.Title,
				Status: "fail",
			})
		}
	}

	return bi
}

// ----------------------------------------------------------------
// HTML report generator
// ----------------------------------------------------------------

func generateReport(res *BatchResult, path string) error {
	var b strings.Builder

	summary := fmt.Sprintf(`<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8">
<title>PDF Access Report</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:1200px;margin:auto;padding:20px;background:#fff}
h1{color:#111;font-size:1.5rem}
.summary{display:flex;gap:20px;margin:15px 0;padding:12px;background:#f6f9fc;border-radius:8px}
.summary span{font-size:1rem}
.ok{color:#0a7} .fail{color:#e43} .skip{color:#888}
table{width:100%%;border-collapse:collapse;margin:10px 0}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid #eee;font-size:0.85rem}
th{background:#f6f9fc;font-weight:600}
tr.ok td{background:#f0faf4}
tr.fail td{background:#fef6f5}
tr.skip td{color:#999}
a{color:#2563eb;text-decoration:none}
a:hover{text-decoration:underline}
.badge{display:inline-block;padding:1px 6px;border-radius:3px;font-size:0.75rem;font-weight:600}
.badge-ok{background:#dcfce7;color:#166534}
.badge-fail{background:#fee2e2;color:#991b1b}
.badge-skip{background:#f5f5f4;color:#78716c}
</style></head><body>
<h1>📄 PDF Access Report</h1>
<div class="summary">
<span>✅ <b>%d</b> success</span>
<span>❌ <b>%d</b> failed</span>
<span>⏭️ <b>%d</b> skipped</span>
<span>📊 <b>%d</b> total</span>
<span>⏱️ %s</span>
</div>
<table><thead><tr><th>#</th><th>DOI</th><th>Title</th><th>Size</th><th>Status</th><th>Path</th></tr></thead><tbody>
`, res.Successes, res.Failures, res.Skipped, res.Total,
		time.Duration(res.Duration).Round(time.Second).String())

	b.WriteString(summary)

	sort.Slice(res.Items, func(i, j int) bool {
		return res.Items[i].DOI < res.Items[j].DOI
	})

	for i, item := range res.Items {
		cls := "ok"
		badgeCls := "badge-ok"
		badgeText := "✅"
		pathStr := ""
		switch {
		case item.Skipped:
			cls = "skip"
			badgeCls = "badge-skip"
			badgeText = "⏭️"
		case item.Err != nil || item.Path == "":
			cls = "fail"
			badgeCls = "badge-fail"
			badgeText = "❌"
		default:
			pathStr = fmt.Sprintf("<a href='%s'>view</a>", item.Path)
		}

		sizeStr := ""
		if item.Size > 0 {
			sizeStr = formatBytes(item.Size)
		}

		title := item.Title
		if len(title) > 80 {
			title = title[:80] + "…"
		}

		doiLink := ""
		if item.DOI != "" {
			doiLink = fmt.Sprintf("<a href='https://doi.org/%s' target='_blank'>%s</a>",
				item.DOI, truncateDOI(item.DOI))
		}

		b.WriteString(fmt.Sprintf("<tr class='%s'><td>%d</td><td>%s</td><td>%s</td><td>%s</td><td><span class='%s'>%s</span></td><td>%s</td></tr>\n",
			cls, i+1, doiLink, title, sizeStr, badgeCls, badgeText, pathStr))
	}

	b.WriteString("</tbody></table></body></html>")

	return os.WriteFile(path, []byte(b.String()), 0o644)
}

func truncateDOI(doi string) string {
	if len(doi) <= 40 {
		return doi
	}
	return doi[:37] + "…"
}

func formatBytes(n int64) string {
	switch {
	case n >= 1024*1024:
		return fmt.Sprintf("%.1f MB", float64(n)/(1024*1024))
	case n >= 1024:
		return fmt.Sprintf("%.0f KB", float64(n)/1024)
	default:
		return fmt.Sprintf("%d B", n)
	}
}

// Close releases the long-lived CDP connection, if any.
func (f *FullTextFinder) Close() {
	if f.cdpClient != nil {
		f.cdpClient.Close()
		f.cdpClient = nil
	}
}

// SetCDPClient injects a pre-configured CDP client for reuse across calls.
// The caller retains ownership and must call Close on it when done.
func (f *FullTextFinder) SetCDPClient(client *source.CDPClient) {
	f.cdpClient = client
}
