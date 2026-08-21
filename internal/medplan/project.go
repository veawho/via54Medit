// Project persistence: each planning project lives in its own
// directory under ~/.medit/medplan/<project>/ with one JSON file per
// stage plus a rendered Markdown deliverable. Writes are atomic
// (temp-then-rename), mirroring internal/persist.
package medplan

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"unicode"
)

// ProjectStore manages on-disk medplan projects.
type ProjectStore struct {
	base string
}

// DefaultProjectDir is the standard storage root.
const DefaultProjectDir = ".medit/medplan"

// NewProjectStore creates the default store at ~/.medit/medplan.
func NewProjectStore() (*ProjectStore, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return nil, fmt.Errorf("medplan: home dir: %w", err)
	}
	return NewProjectStoreAt(filepath.Join(home, DefaultProjectDir))
}

// NewProjectStoreAt creates a store rooted at dir (created if needed).
func NewProjectStoreAt(dir string) (*ProjectStore, error) {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return nil, fmt.Errorf("medplan: mkdir %s: %w", dir, err)
	}
	return &ProjectStore{base: dir}, nil
}

// Base returns the storage root.
func (s *ProjectStore) Base() string { return s.base }

// Dir returns the project directory (no existence guarantee).
func (s *ProjectStore) Dir(name string) string {
	return filepath.Join(s.base, sanitizeProjectName(name))
}

func (s *ProjectStore) ensureProject(name string) error {
	if err := os.MkdirAll(s.Dir(name), 0o755); err != nil {
		return fmt.Errorf("medplan: mkdir project %s: %w", name, err)
	}
	return nil
}

func writeAtomic(path string, data []byte) error {
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, data, 0o644); err != nil {
		return fmt.Errorf("medplan: write %s: %w", tmp, err)
	}
	if err := os.Rename(tmp, path); err != nil {
		return fmt.Errorf("medplan: rename %s: %w", path, err)
	}
	return nil
}

func writeJSON(path string, v any) error {
	data, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return fmt.Errorf("medplan: marshal %s: %w", path, err)
	}
	return writeAtomic(path, data)
}

func readJSON(path string, v any) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("medplan: read %s: %w", path, err)
	}
	if err := json.Unmarshal(data, v); err != nil {
		return fmt.Errorf("medplan: unmarshal %s: %w", path, err)
	}
	return nil
}

// --- Brief ---

// SaveBrief persists brief.json.
func (s *ProjectStore) SaveBrief(b *Brief) error {
	if b == nil || b.Project == "" {
		return fmt.Errorf("medplan: brief needs a project name")
	}
	if err := s.ensureProject(b.Project); err != nil {
		return err
	}
	return writeJSON(filepath.Join(s.Dir(b.Project), "brief.json"), b)
}

// LoadBrief reads brief.json for a project.
func (s *ProjectStore) LoadBrief(name string) (*Brief, error) {
	var b Brief
	if err := readJSON(filepath.Join(s.Dir(name), "brief.json"), &b); err != nil {
		return nil, err
	}
	return &b, nil
}

// --- Research / Insights ---

// SaveResearch persists research.json.
func (s *ProjectStore) SaveResearch(d *ResearchDossier) error {
	return writeJSON(filepath.Join(s.Dir(d.Project), "research.json"), d)
}

// LoadResearch reads research.json.
func (s *ProjectStore) LoadResearch(name string) (*ResearchDossier, error) {
	var d ResearchDossier
	if err := readJSON(filepath.Join(s.Dir(name), "research.json"), &d); err != nil {
		return nil, err
	}
	return &d, nil
}

// SaveInsights persists insights.json.
func (s *ProjectStore) SaveInsights(ins *Insights) error {
	return writeJSON(filepath.Join(s.Dir(ins.Project), "insights.json"), ins)
}

// LoadInsights reads insights.json.
func (s *ProjectStore) LoadInsights(name string) (*Insights, error) {
	var ins Insights
	if err := readJSON(filepath.Join(s.Dir(name), "insights.json"), &ins); err != nil {
		return nil, err
	}
	return &ins, nil
}

// --- Outline / Compliance (per audience) ---

// OutlinePath returns the outline file path for an audience.
func (s *ProjectStore) OutlinePath(name string, a Audience) string {
	return filepath.Join(s.Dir(name), fmt.Sprintf("outline_%s.json", a))
}

// SaveOutline persists outline_<audience>.json.
func (s *ProjectStore) SaveOutline(o *StrategyOutline) error {
	return writeJSON(s.OutlinePath(o.Project, o.Audience), o)
}

// LoadOutline reads the latest outline for an audience.
func (s *ProjectStore) LoadOutline(name string, a Audience) (*StrategyOutline, error) {
	var o StrategyOutline
	if err := readJSON(s.OutlinePath(name, a), &o); err != nil {
		return nil, err
	}
	return &o, nil
}

// CompliancePath returns the compliance report path for an audience.
func (s *ProjectStore) CompliancePath(name string, a Audience) string {
	return filepath.Join(s.Dir(name), fmt.Sprintf("compliance_%s.json", a))
}

// SaveCompliance persists compliance_<audience>.json.
func (s *ProjectStore) SaveCompliance(r *ComplianceReport) error {
	return writeJSON(s.CompliancePath(r.Project, r.Audience), r)
}

// LoadCompliance reads the compliance report for an audience.
func (s *ProjectStore) LoadCompliance(name string, a Audience) (*ComplianceReport, error) {
	var r ComplianceReport
	if err := readJSON(s.CompliancePath(name, a), &r); err != nil {
		return nil, err
	}
	return &r, nil
}

// --- Listing / rendering ---

// List returns project names, sorted. A project is any directory
// containing brief.json.
func (s *ProjectStore) List() ([]string, error) {
	entries, err := os.ReadDir(s.base)
	if err != nil {
		return nil, fmt.Errorf("medplan: list %s: %w", s.base, err)
	}
	var out []string
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		if _, err := os.Stat(filepath.Join(s.base, e.Name(), "brief.json")); err == nil {
			out = append(out, e.Name())
		}
	}
	sort.Strings(out)
	return out, nil
}

// WriteMarkdown renders a deliverable Markdown file into the project
// directory (outline_<audience>.md).
func (s *ProjectStore) WriteMarkdown(name string, a Audience, md string) error {
	if err := s.ensureProject(name); err != nil {
		return err
	}
	path := filepath.Join(s.Dir(name), fmt.Sprintf("outline_%s.md", a))
	return writeAtomic(path, []byte(md))
}

// sanitizeProjectName keeps letters/digits/dash/underscore/dot and
// collapses everything else to "-" (same spirit as persist.safeFilename
// but unicode-friendly so Chinese project names survive).
func sanitizeProjectName(name string) string {
	var b strings.Builder
	lastDash := false
	for _, r := range name {
		switch {
		case unicode.IsLetter(r) || unicode.IsDigit(r) || r == '-' || r == '_' || r == '.':
			b.WriteRune(r)
			lastDash = false
		default:
			if !lastDash {
				b.WriteRune('-')
				lastDash = true
			}
		}
	}
	out := strings.Trim(b.String(), "-")
	if out == "" {
		out = "project"
	}
	return out
}

// Slugify exposes the project-name sanitizer for callers that derive
// a project slug from a product name.
func Slugify(name string) string { return sanitizeProjectName(name) }
