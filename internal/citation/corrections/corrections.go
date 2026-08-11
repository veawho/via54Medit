// Package corrections implements the experience loop for via54Medit.
//
// Philosophy (2026-07-31, user-taught):
//
//	"所有修改修正经验都会持续集成到via54Medit"
//
// Every time a user corrects a citation (or any algorithm output) in their
// local project (e.g. 雷管方案_文献整理), the correction is:
//
//  1. Recorded in a CorrectionEntry (JSON format)
//  2. Replayed against the algorithm to generate test cases
//  3. Committed to via54Medit as a regression test
//  4. Verified by CI before merge
//
// Loop:
//
//	User makes correction
//	  → corrections.Record(c)  (saves to corrections.json)
//	  → corrections.ReplayAll() generates TestCase entries
//	  → corrections.GenerateGoTest() writes *_test.go additions
//	  → go test ./...  (verifies fix)
//	  → git commit + push  (continuous integration)
package corrections

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

// CorrectionType is the category of correction.
type CorrectionType string

const (
	TypeAuthorCorrection    CorrectionType = "author"        // e.g. Abou-Alfa missed
	TypeJournalCorrection   CorrectionType = "journal"       // e.g. NEJM Evid not detected
	TypeDOICorrection       CorrectionType = "doi"           // e.g. DOI tail wrong
	TypeTrialCorrection     CorrectionType = "trial"         // e.g. HIMALAYA missed
	TypeDrugCorrection      CorrectionType = "drug"          // e.g. Tremelimumab missed
	TypeFileMapping         CorrectionType = "file_mapping"  // e.g. row 47 G wrong
	TypeRichTextConversion  CorrectionType = "rich_text"     // e.g. H column rich text bug
	TypeSyncDirection       CorrectionType = "sync_direction" // e.g. sync_all reverse
	TypeGeneral             CorrectionType = "general"
)

// CorrectionEntry represents one user correction.
//
// Example (from 雷管方案_文献整理 history, 2026-07-31):
//
//	{
//	  "id": "corr-2026-07-31-001",
//	  "timestamp": "2026-07-31T01:30:00+08:00",
//	  "type": "file_mapping",
//	  "context": "Row 47 P19-1 G column pointed to wrong file",
//	  "before": "P19-2_Finn_RS_ASCOGI2021_Abstract267...",
//	  "after": "P19-1_P20-1_P24-8_P24-9_main_Qin_S_Liver_Cancer_2021_Lenvatinib.pdf",
//	  "expected_algorithm_change": "improve Pn-x shared PDF resolver",
//	  "test_case": "TestPnxResolver_Row47",
//	  "status": "pending"
//	}
type CorrectionEntry struct {
	ID                       string         `json:"id"`
	Timestamp                time.Time      `json:"timestamp"`
	Type                     CorrectionType `json:"type"`
	Context                  string         `json:"context"`
	Before                   string         `json:"before"`
	After                    string         `json:"after"`
	ExpectedAlgorithmChange  string         `json:"expected_algorithm_change,omitempty"`
	TestCase                 string         `json:"test_case,omitempty"`
	Status                   string         `json:"status"` // "pending" | "fixed" | "verified"
	SourceProject            string         `json:"source_project"` // e.g. "雷管方案_文献整理"
	RowIndex                 int            `json:"row_index,omitempty"`
	SlidePage                string         `json:"slide_page,omitempty"`
	DOIBefore                string         `json:"doi_before,omitempty"`
	DOIAfter                 string         `json:"doi_after,omitempty"`
}

// CorrectionLog is the on-disk JSON file that accumulates corrections.
const DefaultLogPath = "~/.via54medit/corrections.json"

// Log is the corrections log, persisted to disk.
type Log struct {
	Path       string             `json:"path"`
	Corrections []CorrectionEntry `json:"corrections"`
}

// LoadLog reads the corrections log from disk.
func LoadLog(path string) (*Log, error) {
	if path == "" {
		path = DefaultLogPath
	}
	expanded, err := filepath.Abs(os.ExpandEnv(path))
	if err != nil {
		return nil, err
	}
	if _, err := os.Stat(expanded); os.IsNotExist(err) {
		return &Log{Path: expanded, Corrections: []CorrectionEntry{}}, nil
	}
	data, err := os.ReadFile(expanded)
	if err != nil {
		return nil, err
	}
	var l Log
	if err := json.Unmarshal(data, &l); err != nil {
		return nil, fmt.Errorf("parse corrections log: %w", err)
	}
	if l.Path == "" {
		l.Path = expanded
	}
	return &l, nil
}

// Save writes the log back to disk atomically.
func (l *Log) Save() error {
	if err := os.MkdirAll(filepath.Dir(l.Path), 0755); err != nil {
		return err
	}
	data, err := json.MarshalIndent(l, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(l.Path, data, 0644)
}

// Record adds a new correction entry to the log.
func (l *Log) Record(c CorrectionEntry) error {
	if c.ID == "" {
		c.ID = fmt.Sprintf("corr-%s", time.Now().Format("20060102-150405"))
	}
	if c.Timestamp.IsZero() {
		c.Timestamp = time.Now()
	}
	if c.Status == "" {
		c.Status = "pending"
	}
	l.Corrections = append(l.Corrections, c)
	return l.Save()
}

// PendingCorrections returns corrections with status "pending".
func (l *Log) PendingCorrections() []CorrectionEntry {
	var pending []CorrectionEntry
	for _, c := range l.Corrections {
		if c.Status == "pending" {
			pending = append(pending, c)
		}
	}
	return pending
}

// MarkFixed marks a correction as fixed (algorithm updated).
func (l *Log) MarkFixed(id string) error {
	for i := range l.Corrections {
		if l.Corrections[i].ID == id {
			l.Corrections[i].Status = "fixed"
			return l.Save()
		}
	}
	return fmt.Errorf("correction not found: %s", id)
}

// MarkVerified marks a correction as verified (CI passed).
func (l *Log) MarkVerified(id string) error {
	for i := range l.Corrections {
		if l.Corrections[i].ID == id {
			l.Corrections[i].Status = "verified"
			return l.Save()
		}
	}
	return fmt.Errorf("correction not found: %s", id)
}