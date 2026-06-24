// Package persist handles on-disk persistence for via54Medit.
//
// Phase 1.5 (per ROADMAP §1.1 internal/persist/qa.go) ships a
// minimal "save and retrieve past questions" feature, inspired by
// the original persist_qa.py from antfu-evidence-search v1.11.
//
// Storage layout (Phase 1.5):
//
//	~/.medit/qa/<conv_id>.json     # per-question JSON snapshot
//	~/.medit/qa/<conv_id>.md       # human-readable Markdown
//
// Both files are written atomically (write-temp-then-rename) so a crash
// mid-write doesn't leave a half-baked file on disk.
//
// SQLite FTS5 indexing is Phase 2 (per ROADMAP). For Phase 1.5 we
// have a simple directory-based store — enough for ~10K conversations.
package persist

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/veawho/via54Medit/pkg/types"
)

// QAStore is the file-backed store for past questions and answers.
type QAStore struct {
	dir string // base directory (e.g. ~/.medit/qa)
}

// NewQAStore creates a store rooted at dir. The directory is created
// if it doesn't exist.
func NewQAStore(dir string) (*QAStore, error) {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, fmt.Errorf("persist: mkdir %s: %w", dir, err)
	}
	return &QAStore{dir: dir}, nil
}

// Save writes an EvidencePackage to disk in both JSON and Markdown
// formats. The conv_id is used as the filename (sanitized).
func (s *QAStore) Save(ep *types.EvidencePackage) error {
	if ep == nil {
		return fmt.Errorf("persist: nil EvidencePackage")
	}
	if ep.ConvID == "" {
		return fmt.Errorf("persist: empty ConvID")
	}
	safe := safeFilename(ep.ConvID)

	jsonPath := filepath.Join(s.dir, safe+".json")
	mdPath := filepath.Join(s.dir, safe+".md")

	// JSON: indented for human inspection.
	jsonData, err := json.MarshalIndent(ep, "", "  ")
	if err != nil {
		return fmt.Errorf("persist: marshal JSON: %w", err)
	}
	if err := atomicWrite(jsonPath, jsonData); err != nil {
		return fmt.Errorf("persist: write JSON: %w", err)
	}

	// Markdown: human-readable summary.
	mdData := renderMarkdown(ep)
	if err := atomicWrite(mdPath, []byte(mdData)); err != nil {
		return fmt.Errorf("persist: write MD: %w", err)
	}
	return nil
}

// Load reads a saved EvidencePackage by conv_id.
func (s *QAStore) Load(convID string) (*types.EvidencePackage, error) {
	safe := safeFilename(convID)
	data, err := os.ReadFile(filepath.Join(s.dir, safe+".json"))
	if err != nil {
		return nil, fmt.Errorf("persist: load %s: %w", convID, err)
	}
	var ep types.EvidencePackage
	if err := json.Unmarshal(data, &ep); err != nil {
		return nil, fmt.Errorf("persist: unmarshal: %w", err)
	}
	return &ep, nil
}

// List returns all saved conv_ids, sorted by modification time (newest first).
func (s *QAStore) List() ([]string, error) {
	entries, err := os.ReadDir(s.dir)
	if err != nil {
		return nil, fmt.Errorf("persist: list: %w", err)
	}
	type fileWithMod struct {
		name    string
		modTime time.Time
	}
	var files []fileWithMod
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".json") {
			continue
		}
		info, err := e.Info()
		if err != nil {
			continue
		}
		name := strings.TrimSuffix(e.Name(), ".json")
		files = append(files, fileWithMod{name: name, modTime: info.ModTime()})
	}
	// Sort newest first.
	for i := 0; i < len(files); i++ {
		for j := i + 1; j < len(files); j++ {
			if files[j].modTime.After(files[i].modTime) {
				files[i], files[j] = files[j], files[i]
			}
		}
	}
	out := make([]string, len(files))
	for i, f := range files {
		out[i] = f.name
	}
	return out, nil
}

// Delete removes a saved package (both .json and .md).
func (s *QAStore) Delete(convID string) error {
	safe := safeFilename(convID)
	jsonPath := filepath.Join(s.dir, safe+".json")
	mdPath := filepath.Join(s.dir, safe+".md")
	// os.Remove returns nil if file doesn't exist; that's fine.
	if err := os.Remove(jsonPath); err != nil && !os.IsNotExist(err) {
		return err
	}
	if err := os.Remove(mdPath); err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}

// --- helpers ---

// safeFilename returns a filesystem-safe version of s.
// Replaces any non-alphanumeric chars with '_'.
func safeFilename(s string) string {
	cleaned := strings.Map(func(r rune) rune {
		if (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9') || r == '-' || r == '_' {
			return r
		}
		return '_'
	}, s)
	if cleaned == "" {
		return "unnamed"
	}
	return cleaned
}

// atomicWrite writes data to a temp file then renames it onto path.
// This ensures the file at path is either the old content or the new
// content, never a partial write.
func atomicWrite(path string, data []byte) error {
	dir := filepath.Dir(path)
	tmp, err := os.CreateTemp(dir, ".tmp-*")
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	// Clean up on failure.
	defer func() {
		if tmpName != "" {
			os.Remove(tmpName)
		}
	}()

	if _, err := tmp.Write(data); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	if err := os.Rename(tmpName, path); err != nil {
		return err
	}
	tmpName = "" // prevent the deferred cleanup
	return nil
}

// renderMarkdown formats an EvidencePackage as a human-readable
// Markdown document.
func renderMarkdown(ep *types.EvidencePackage) string {
	var b strings.Builder
	b.WriteString("# via54Medit Evidence Package\n\n")
	b.WriteString(fmt.Sprintf("**ConvID**: %s  \n", ep.ConvID))
	b.WriteString(fmt.Sprintf("**Date**: %s  \n", ep.CreatedAt.Format("2006-01-02 15:04:05 MST")))
	b.WriteString(fmt.Sprintf("**Duration**: %s  \n", ep.Duration))
	b.WriteString(fmt.Sprintf("**Question**: %s  \n\n", ep.Question.Query))

	if len(ep.SourcesUsed) > 0 {
		b.WriteString("**Sources**:\n")
		// Sort source names for stable output.
		names := make([]string, 0, len(ep.SourcesUsed))
		for k := range ep.SourcesUsed {
			names = append(names, k)
		}
		for i := 1; i < len(names); i++ {
			for j := i; j > 0 && names[j-1] > names[j]; j-- {
				names[j-1], names[j] = names[j], names[j-1]
			}
		}
		for _, name := range names {
			b.WriteString(fmt.Sprintf("- %s: %d citations\n", name, ep.SourcesUsed[name]))
		}
		b.WriteString("\n")
	}

	if ep.Summary != "" {
		b.WriteString("## Summary\n\n")
		b.WriteString(ep.Summary)
		b.WriteString("\n\n")
	}

	if len(ep.Citations) > 0 {
		b.WriteString("## Citations\n\n")
		for i, c := range ep.Citations {
			b.WriteString(fmt.Sprintf("%d. %s\n", i+1, c.Title))
			if c.Journal != "" {
				j := c.Journal
				if c.Year > 0 {
					j = fmt.Sprintf("%s (%d)", j, c.Year)
				}
				b.WriteString(fmt.Sprintf("   - %s\n", j))
			}
			if c.PMID != "" {
				b.WriteString(fmt.Sprintf("   - PMID: %s\n", c.PMID))
			}
			if c.DOI != "" {
				b.WriteString(fmt.Sprintf("   - DOI: %s\n", c.DOI))
			}
			if len(c.SourceOrigin) > 0 {
				b.WriteString(fmt.Sprintf("   - Sources: %s\n", strings.Join(c.SourceOrigin, ", ")))
			}
		}
	}
	return b.String()
}
