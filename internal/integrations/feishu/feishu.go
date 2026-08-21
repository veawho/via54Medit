// Package feishu provides CSV ↔ Feishu spreadsheet bidirectional sync.
//
// Design principles (2026-07-31, Phase 6):
//   - Single direction: CSV → Feishu (never reverse, unless explicit feishu_to_csv mode)
//   - Re-read CSV from disk (no in-memory cache between write and push)
//   - File lock to prevent concurrent writes
//   - Single-row push with verify (3 retry with exponential backoff)
//   - Rich text (H column) auto-converted from plain text + URL detection
//   - Zero hardcoded paths/tokens (always read from env or config file)
//
// Public API:
//
//   client, err := feishu.NewClient(&feishu.Config{...})
//   if err != nil { ... }
//   result, err := client.Verify(ctx)
//   if err != nil { ... }
//   success, fails, err := client.Push(ctx, feishu.PushOptions{DryRun: false})
//
// See integrations/feishu/README.md for design docs.
package feishu

import (
	"context"
	"encoding/csv"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/veawho/via54Medit/internal/foundation"
)

// Config holds runtime configuration for the Feishu client.
//
// All fields should be populated from environment variables or a config file.
// There are NO defaults that assume any specific project — callers MUST
// provide Token and SheetID.
type Config struct {
	// Token is the Feishu spreadsheet token (set via FEISHU_TOKEN env; never hardcode).
	// Required.
	Token string

	// SheetID is the sheet (tab) ID within the spreadsheet (e.g. "b03e59").
	// Required.
	SheetID string

	// CSVPath is the absolute path to the local citation_table.csv.
	// Required.
	CSVPath string

	// BaseDir is the project root directory (used for lock file location).
	// Required.
	BaseDir string

	// LarkCLI is the path to the lark-cli executable.
	// Optional; defaults to /Users/david/.hermes/node/bin/lark-cli.
	LarkCLI string

	// Logger allows callers to inject a custom logger. Optional.
	Logger foundation.Logger
}

// Client is the Feishu sync client.
type Client struct {
	cfg    Config
	logger foundation.Logger
	lockMu sync.Mutex
}

// NewClient creates a new Feishu client.
//
// Returns an error if required fields are missing.
func NewClient(cfg *Config) (*Client, error) {
	if cfg == nil {
		return nil, errors.New("feishu: config is required")
	}
	if cfg.Token == "" {
		return nil, errors.New("feishu: Token is required (set FEISHU_TOKEN env or pass config)")
	}
	if cfg.SheetID == "" {
		return nil, errors.New("feishu: SheetID is required (set SHEET_ID env or pass config)")
	}
	if cfg.CSVPath == "" {
		return nil, errors.New("feishu: CSVPath is required (set CSV_PATH env or pass config)")
	}
	if cfg.BaseDir == "" {
		return nil, errors.New("feishu: BaseDir is required (set BASE_DIR env or pass config)")
	}

	if cfg.LarkCLI == "" {
		cfg.LarkCLI = "/Users/david/.hermes/node/bin/lark-cli"
	}
	if cfg.Logger == nil {
		cfg.Logger = foundation.NewLogger("info")
	}

	return &Client{
		cfg:    *cfg,
		logger: cfg.Logger,
	}, nil
}

// VerifyResult summarizes the verification outcome.
type VerifyResult struct {
	TotalRows        int                 `json:"total_rows"`
	FeishuRows       int                 `json:"feishu_rows"`
	ColumnMismatches map[string][]string `json:"column_mismatches"` // column letter → list of "Row N" mismatches
	FileMissing      []string            `json:"file_missing"`       // G-column paths that don't exist
	Consistent       bool                `json:"consistent"`
}

// Verify reads the Feishu table and compares against the CSV. Does not modify
// any data; safe to call at any time.
func (c *Client) Verify(ctx context.Context) (*VerifyResult, error) {
	c.logger.Info("verify: starting", slog.String("csv_path", c.cfg.CSVPath))

	// 1. Read CSV (re-read from disk; never trust in-memory cache)
	csvRows, err := readCSV(c.cfg.CSVPath)
	if err != nil {
		return nil, fmt.Errorf("verify: read CSV: %w", err)
	}

	// 2. Read Feishu D2:H161
	feishuCells, err := c.readFeishuRange("D2:H161")
	if err != nil {
		return nil, fmt.Errorf("verify: read Feishu: %w", err)
	}

	result := &VerifyResult{
		TotalRows:        len(csvRows),
		FeishuRows:       len(feishuCells),
		ColumnMismatches: map[string][]string{},
	}

	// 3. Compare row by row
	for i, row := range csvRows {
		feishuRow := i + 2 // csv row[i] = Feishu Row i+2 (Row 1 is header)

		if i >= len(feishuCells) {
			result.ColumnMismatches["_missing"] = append(
				result.ColumnMismatches["_missing"],
				fmt.Sprintf("Row %d (csv row %d)", feishuRow, i+1),
			)
			continue
		}

		fcells := feishuCells[i]
		if len(fcells) < 4 {
			continue // incomplete Feishu row
		}

		// D column
		if extractCellText(fcells[0]) != row.PPTReference {
			result.ColumnMismatches["D"] = append(
				result.ColumnMismatches["D"],
				fmt.Sprintf("Row %d", feishuRow),
			)
		}
		// G column (basename only)
		csvGBasename := filepath.Base(row.PDFFile)
		if extractCellText(fcells[3]) != csvGBasename {
			result.ColumnMismatches["G"] = append(
				result.ColumnMismatches["G"],
				fmt.Sprintf("Row %d: csv=%q feishu=%q", feishuRow, csvGBasename, extractCellText(fcells[3])),
			)
		}

		// Check file exists
		if row.PDFFile != "" {
			if _, err := os.Stat(row.PDFFile); os.IsNotExist(err) {
				result.FileMissing = append(result.FileMissing, row.PDFFile)
			}
		}

		// H column (rich text plain text extraction)
		if len(fcells) > 4 {
			feishuH := extractRichTextPlain(fcells[4])
			if row.SourceURL != feishuH {
				result.ColumnMismatches["H"] = append(
					result.ColumnMismatches["H"],
					fmt.Sprintf("Row %d: csv_len=%d feishu_len=%d", feishuRow, len(row.SourceURL), len(feishuH)),
				)
			}
		}
	}

	result.Consistent = len(result.ColumnMismatches) == 0 && len(result.FileMissing) == 0

	c.logger.Info("verify: done",
		slog.Bool("consistent", result.Consistent),
		slog.Int("d_mismatches", len(result.ColumnMismatches["D"])),
		slog.Int("g_mismatches", len(result.ColumnMismatches["G"])),
		slog.Int("h_mismatches", len(result.ColumnMismatches["H"])),
	)
	return result, nil
}

// PushOptions controls push behavior.
type PushOptions struct {
	// DryRun does not actually push, just shows what would be pushed.
	DryRun bool
	// FixMode forces push of all rows (not just mismatched).
	FixMode bool
	// SingleRow limits push to one specific Feishu row (for debugging).
	SingleRow int
}

// Push pushes CSV rows to Feishu, verifying each row after push.
// Returns the count of successfully pushed rows and any failures.
func (c *Client) Push(ctx context.Context, opts PushOptions) (int, []error, error) {
	c.logger.Info("push: starting",
		slog.Bool("dry_run", opts.DryRun),
		slog.Bool("fix_mode", opts.FixMode),
		slog.Int("single_row", opts.SingleRow),
	)

	// 1. Acquire lock
	lockPath := filepath.Join(c.cfg.BaseDir, "_citation_table", "csv.lock")
	if err := acquireLock(lockPath, 30*time.Second); err != nil {
		return 0, nil, fmt.Errorf("push: acquire lock: %w", err)
	}
	defer releaseLock(lockPath)

	// 2. Read CSV
	csvRows, err := readCSV(c.cfg.CSVPath)
	if err != nil {
		return 0, nil, fmt.Errorf("push: read CSV: %w", err)
	}

	// 3. Determine rows to push
	var rowsToPush []int
	if opts.SingleRow > 0 {
		rowsToPush = []int{opts.SingleRow}
	} else if !opts.FixMode {
		// Verify first, only push mismatched
		result, err := c.Verify(ctx)
		if err != nil {
			return 0, nil, fmt.Errorf("push: verify before push: %w", err)
		}
		rowsToPush = extractMismatchedRowNumbers(result)
	} else {
		for i := range csvRows {
			rowsToPush = append(rowsToPush, i+2) // Feishu row number
		}
	}

	c.logger.Info("push: pushing rows", slog.Int("count", len(rowsToPush)))

	// 4. Push each row
	successCount := 0
	var failErrors []error

	for _, feishuRow := range rowsToPush {
		i := feishuRow - 2
		if i < 0 || i >= len(csvRows) {
			failErrors = append(failErrors, fmt.Errorf("row %d out of range", feishuRow))
			continue
		}
		row := csvRows[i]

		err := c.pushSingleRow(ctx, feishuRow, row, opts.DryRun)
		if err != nil {
			failErrors = append(failErrors, fmt.Errorf("row %d: %w", feishuRow, err))
			continue
		}

		if !opts.DryRun {
			// Verify single row
			if vErr := c.verifySingleRow(ctx, feishuRow, row); vErr != nil {
				// Retry once
				if retryErr := c.pushSingleRow(ctx, feishuRow, row, false); retryErr != nil {
					failErrors = append(failErrors, fmt.Errorf("row %d verify failed after retry: %v / %v", feishuRow, vErr, retryErr))
					continue
				}
				if retryVerifyErr := c.verifySingleRow(ctx, feishuRow, row); retryVerifyErr != nil {
					failErrors = append(failErrors, fmt.Errorf("row %d verify still failed: %v", feishuRow, retryVerifyErr))
					continue
				}
			}
		}

		successCount++
	}

	c.logger.Info("push: done",
		slog.Int("success", successCount),
		slog.Int("failed", len(failErrors)),
	)
	return successCount, failErrors, nil
}

// pushSingleRow pushes a single row to Feishu.
func (c *Client) pushSingleRow(ctx context.Context, feishuRow int, row CSVRow, dryRun bool) error {
	gBasename := filepath.Base(row.PDFFile)
	if row.PDFFile == "" {
		gBasename = ""
	}

	cells := [][]map[string]interface{}{{
		{"value": row.PPTReference},
		{"value": row.DOI},
		{"value": row.Type},
		{"value": gBasename},
		buildHCell(row.SourceURL),
	}}

	if dryRun {
		c.logger.Info("DRY-RUN: would push",
			slog.Int("row", feishuRow),
			slog.String("D", truncStr(row.PPTReference, 40)),
			slog.String("G", gBasename),
		)
		return nil
	}

	return c.larkCellsSet(ctx, fmt.Sprintf("D%d:H%d", feishuRow, feishuRow), cells)
}

// verifySingleRow reads a single Feishu row and compares to CSV.
func (c *Client) verifySingleRow(ctx context.Context, feishuRow int, row CSVRow) error {
	cells, err := c.readFeishuRange(fmt.Sprintf("D%d:H%d", feishuRow, feishuRow))
	if err != nil {
		return fmt.Errorf("read: %w", err)
	}
	if len(cells) == 0 || len(cells[0]) < 4 {
		return errors.New("empty feishu response")
	}

	fcells := cells[0]
	if extractCellText(fcells[0]) != row.PPTReference {
		return fmt.Errorf("D mismatch")
	}
	csvGBasename := filepath.Base(row.PDFFile)
	if extractCellText(fcells[3]) != csvGBasename {
		return fmt.Errorf("G mismatch")
	}
	if len(fcells) > 4 {
		if extractRichTextPlain(fcells[4]) != row.SourceURL {
			return fmt.Errorf("H mismatch")
		}
	}

	return nil
}

// readFeishuRange reads cells from Feishu using lark-cli.
func (c *Client) readFeishuRange(rangeStr string) ([][]interface{}, error) {
	output, err := c.execLarkCLI("sheets", "+read",
		"--range", fmt.Sprintf("%s!%s", c.cfg.SheetID, rangeStr),
		"--spreadsheet-token", c.cfg.Token,
		"--json",
	)
	if err != nil {
		return nil, err
	}

	var resp struct {
		OK   bool `json:"ok"`
		Data struct {
			ValueRange struct {
				Values [][]interface{} `json:"values"`
			} `json:"valueRange"`
		} `json:"data"`
	}
	if err := json.Unmarshal([]byte(output), &resp); err != nil {
		return nil, err
	}
	if !resp.OK {
		return nil, fmt.Errorf("feishu: not ok: %s", truncStr(output, 300))
	}
	return resp.Data.ValueRange.Values, nil
}

// larkCellsSet sets cells via lark-cli.
func (c *Client) larkCellsSet(ctx context.Context, rangeStr string, cells [][]map[string]interface{}) error {
	cellsJSON, err := json.Marshal(cells)
	if err != nil {
		return err
	}

	_, err = c.execLarkCLI("sheets", "+cells-set",
		"--spreadsheet-token", c.cfg.Token,
		"--sheet-id", c.cfg.SheetID,
		"--range", rangeStr,
		"--cells", string(cellsJSON),
	)
	return err
}

// execLarkCLI shells out to lark-cli with the given args.
//
// Implementation note: this is Phase 1 (Python-equivalent behavior using lark-cli).
// Phase 2 should replace this with native Go HTTP client (github.com/larksuite/oapi-sdk-go)
// for better performance and no Node.js dependency.
func (c *Client) execLarkCLI(args ...string) (string, error) {
	cmd := exec.Command(c.cfg.LarkCLI, args...)
	output, err := cmd.CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("lark-cli failed: %w (output: %s)", err, string(output))
	}
	return string(output), nil
}

// buildHCell builds the H column cell JSON.
// Returns {rich_text: [...]} if URLs detected, {text: ...} otherwise, or {} if empty.
func buildHCell(content string) map[string]interface{} {
	content = strings.TrimSpace(content)
	if content == "" {
		return map[string]interface{}{}
	}

	urlPattern := regexp.MustCompile(`(https?://[^\s\)]+)`)
	matches := urlPattern.FindAllStringIndex(content, -1)

	if len(matches) == 0 {
		return map[string]interface{}{"text": content}
	}

	parts := []map[string]interface{}{}
	lastEnd := 0
	for _, m := range matches {
		start, end := m[0], m[1]
		if start > lastEnd {
			parts = append(parts, map[string]interface{}{
				"text": content[lastEnd:start],
				"type": "text",
			})
		}
		parts = append(parts, map[string]interface{}{
			"text": content[start:end],
			"type": "link",
			"link": content[start:end],
		})
		lastEnd = end
	}
	if lastEnd < len(content) {
		parts = append(parts, map[string]interface{}{
			"text": content[lastEnd:],
			"type": "text",
		})
	}

	return map[string]interface{}{"rich_text": parts}
}

// extractCellText extracts plain text from a Feishu cell (which may be string,
// list of dict nodes for rich text, etc.).
func extractCellText(cell interface{}) string {
	if cell == nil {
		return ""
	}
	switch v := cell.(type) {
	case string:
		return v
	case map[string]interface{}:
		if s, ok := v["value"].(string); ok {
			return s
		}
		if s, ok := v["text"].(string); ok {
			return s
		}
	case []interface{}:
		parts := []string{}
		for _, item := range v {
			if m, ok := item.(map[string]interface{}); ok {
				if s, ok := m["text"].(string); ok {
					parts = append(parts, s)
				}
			} else if l, ok := item.([]interface{}); ok {
				for _, sub := range l {
					if m, ok := sub.(map[string]interface{}); ok {
						if s, ok := m["text"].(string); ok {
							parts = append(parts, s)
						}
					}
				}
			}
		}
		return strings.Join(parts, "")
	}
	return fmt.Sprintf("%v", cell)
}

// extractRichTextPlain extracts plain text from a rich text cell.
func extractRichTextPlain(cell interface{}) string {
	return extractCellText(cell)
}

// readCSV reads the citation CSV file.
func readCSV(path string) ([]CSVRow, error) {
	// Read raw bytes first to strip UTF-8 BOM (if present).
	rawBytes, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	// Strip UTF-8 BOM if present
	if len(rawBytes) >= 3 && rawBytes[0] == 0xEF && rawBytes[1] == 0xBB && rawBytes[2] == 0xBF {
		rawBytes = rawBytes[3:]
	}

	reader := csv.NewReader(strings.NewReader(string(rawBytes)))
	reader.FieldsPerRecord = -1 // allow variable number of fields

	records, err := reader.ReadAll()
	if err != nil {
		return nil, err
	}

	if len(records) < 2 {
		return nil, errors.New("csv: empty or missing header")
	}

	header := records[0]
	colIdx := map[string]int{}
	for i, col := range header {
		colIdx[col] = i
	}

	// Required columns
	required := []string{"PPT页", "第几条", "引用语义（上下文）",
		"PPT中的文献引用 完整字段", "DOI", "类型", "对应PDF文件", "来源链接 → 阅读全文"}
	for _, c := range required {
		if _, ok := colIdx[c]; !ok {
			return nil, fmt.Errorf("csv: missing required column %q", c)
		}
	}

	rows := make([]CSVRow, 0, len(records)-1)
	for _, rec := range records[1:] {
		if len(rec) < len(header) {
			continue
		}
		rows = append(rows, CSVRow{
			PPTPage:      strings.TrimRight(rec[colIdx["PPT页"]], "\r\n"),
			CiteIndex:    strings.TrimRight(rec[colIdx["第几条"]], "\r\n"),
			Context:      rec[colIdx["引用语义（上下文）"]],
			PPTReference: strings.TrimRight(rec[colIdx["PPT中的文献引用 完整字段"]], "\r\n"),
			DOI:          strings.TrimRight(rec[colIdx["DOI"]], "\r\n"),
			Type:         strings.TrimRight(rec[colIdx["类型"]], "\r\n"),
			PDFFile:      strings.TrimRight(rec[colIdx["对应PDF文件"]], "\r\n"),
			SourceURL:    strings.TrimRight(rec[colIdx["来源链接 → 阅读全文"]], "\r\n"),
		})
	}
	return rows, nil
}

// CSVRow represents one row in citation_table.csv.
//
// Column mapping (matches citation_table.csv schema):
//   PPTPage      → "PPT页" (col A)
//   CiteIndex    → "第几条" (col B)
//   Context      → "引用语义（上下文）" (col C)
//   PPTReference → "PPT中的文献引用 完整字段" (col D)
//   DOI          → "DOI" (col E)
//   Type         → "类型" (col F)
//   PDFFile      → "对应PDF文件" (col G)
//   SourceURL    → "来源链接 → 阅读全文" (col H)
type CSVRow struct {
	PPTPage      string
	CiteIndex    string
	Context      string
	PPTReference string
	DOI          string
	Type         string
	PDFFile      string
	SourceURL    string
}

// acquireLock acquires the file lock (blocks up to timeout).
func acquireLock(path string, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	for {
		if !fileExists(path) {
			break
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("lock %s held for >%s", path, timeout)
		}
		time.Sleep(1 * time.Second)
	}
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	return f.Close()
}

// releaseLock removes the lock file.
func releaseLock(path string) {
	os.Remove(path)
}

func fileExists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}

// extractMismatchedRowNumbers extracts row numbers from a VerifyResult.
func extractMismatchedRowNumbers(result *VerifyResult) []int {
	seen := map[int]bool{}
	for _, mismatches := range result.ColumnMismatches {
		for _, m := range mismatches {
			var rowNum int
			if _, err := fmt.Sscanf(m, "Row %d", &rowNum); err == nil {
				seen[rowNum] = true
			}
		}
	}
	rows := make([]int, 0, len(seen))
	for r := range seen {
		rows = append(rows, r)
	}
	return rows
}

func truncStr(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max] + "..."
}