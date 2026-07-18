// Package download provides tiered full-text acquisition.
//
// checkpoint.go — checkpoint/resume support for interrupted batch operations.
package download

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
)

// Checkpoint records which citations have been processed and their results.
// It enables resuming an interrupted batch download without re-processing.
type Checkpoint struct {
	path string
	mu   sync.Mutex
	data CheckpointData
}

// CheckpointData is the serialisable checkpoint state.
type CheckpointData struct {
	Total      int                 `json:"total"`
	Processed  int                 `json:"processed"`
	Successes  int                 `json:"successes"`
	Failures   int                 `json:"failures"`
	Skipped    int                 `json:"skipped"`
	Items      []CheckpointItem    `json:"items"`
	Results    map[string]string   `json:"results"` // doi → path
}

// CheckpointItem records the status of one citation.
type CheckpointItem struct {
	DOI    string `json:"doi,omitempty"`
	PMID   string `json:"pmid,omitempty"`
	Title  string `json:"title,omitempty"`
	Status string `json:"status"` // "ok", "fail", "skip"
	Path   string `json:"path,omitempty"`
	Tier   int    `json:"tier,omitempty"`
	Size   int64  `json:"size,omitempty"`
}

// NewCheckpoint creates or loads a checkpoint file.
func NewCheckpoint(path string, total int) (*Checkpoint, error) {
	cp := &Checkpoint{
		path: path,
		data: CheckpointData{
			Total:   total,
			Results: make(map[string]string),
		},
	}

	// Try to load existing checkpoint
	raw, err := os.ReadFile(path)
	if err == nil {
		if err := json.Unmarshal(raw, &cp.data); err == nil {
			// Count processed items from loaded data
			cp.data.Processed = 0
			cp.data.Successes = 0
			cp.data.Failures = 0
			cp.data.Skipped = 0
			cp.data.Results = make(map[string]string)
			for _, item := range cp.data.Items {
				cp.data.Processed++
				if item.Path != "" {
					cp.data.Results[item.DOI] = item.Path
				}
				switch item.Status {
				case "ok":
					cp.data.Successes++
				case "fail":
					cp.data.Failures++
				case "skip":
					cp.data.Skipped++
				}
			}
		}
	}

	return cp, nil
}

// IsDone returns true if the given DOI has already been successfully processed.
func (cp *Checkpoint) IsDone(doi string) bool {
	cp.mu.Lock()
	defer cp.mu.Unlock()
	_, done := cp.data.Results[doi]
	return done
}

// RecordSuccess marks a citation as successfully processed.
func (cp *Checkpoint) RecordSuccess(item CheckpointItem) {
	cp.mu.Lock()
	defer cp.mu.Unlock()
	item.Status = "ok"
	cp.data.Items = append(cp.data.Items, item)
	cp.data.Processed++
	cp.data.Successes++
	if item.DOI != "" {
		cp.data.Results[item.DOI] = item.Path
	}
	cp.save()
}

// RecordFailure marks a citation as failed.
func (cp *Checkpoint) RecordFailure(item CheckpointItem) {
	cp.mu.Lock()
	defer cp.mu.Unlock()
	item.Status = "fail"
	cp.data.Items = append(cp.data.Items, item)
	cp.data.Processed++
	cp.data.Failures++
	cp.save()
}

// RecordSkip marks a citation as skipped (already processed or no-op).
func (cp *Checkpoint) RecordSkip(item CheckpointItem) {
	cp.mu.Lock()
	defer cp.mu.Unlock()
	item.Status = "skip"
	cp.data.Items = append(cp.data.Items, item)
	cp.data.Processed++
	cp.data.Skipped++
	cp.save()
}

// Summary returns a human-readable checkpoint summary.
func (cp *Checkpoint) Summary() string {
	cp.mu.Lock()
	defer cp.mu.Unlock()
	d := cp.data
	return fmt.Sprintf("processed=%d ok=%d fail=%d skip=%d total=%d",
		d.Processed, d.Successes, d.Failures, d.Skipped, d.Total)
}

// Progress returns the number of items processed so far.
func (cp *Checkpoint) Progress() int {
	cp.mu.Lock()
	defer cp.mu.Unlock()
	return cp.data.Processed
}

// save writes checkpoint to disk (caller must hold mu).
func (cp *Checkpoint) save() {
	dir := filepath.Dir(cp.path)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return
	}
	b, err := json.MarshalIndent(cp.data, "", "  ")
	if err != nil {
		return
	}
	_ = os.WriteFile(cp.path, b, 0o644)
}
