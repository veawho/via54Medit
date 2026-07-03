package foundation

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestNewDefaultConfigHasAllSections(t *testing.T) {
	cfg := NewDefaultConfig()

	wantSections := []string{"sources", "embedder", "vectorstore", "llm", "router", "storage", "output"}
	got := cfg.SectionNames()
	if len(got) != len(wantSections) {
		t.Errorf("SectionNames() = %v, want %d sections", got, len(wantSections))
	}
	for _, w := range wantSections {
		if !contains(got, w) {
			t.Errorf("SectionNames() missing %q (got %v)", w, got)
		}
	}
}

func TestConfigGetStringExpandsHome(t *testing.T) {
	cfg := NewDefaultConfig()

	// Set HOME to a known value, then verify expansion.
	t.Setenv("HOME", "/home/testuser")
	t.Setenv("USERPROFILE", "") // ensure Windows USERPROFILE doesn't override
	got, ok := cfg.GetString("storage", "qa_dir")
	if !ok {
		t.Fatal("GetString(storage.qa_dir) not found")
	}
	// expandHome uses filepath.Join, so the result depends on the OS.
	// On Windows it becomes \home	estuser\.medit\qa, on POSIX it stays
	// /home/testuser/.medit/qa. Build the expected value the same way.
	want := filepath.Join("/home/testuser", ".medit", "qa")
	if got != want {
		t.Errorf("GetString(storage.qa_dir) = %q, want %q", got, want)
	}
}

func TestConfigGetIntHandlesFloat64(t *testing.T) {
	// YAML decoders commonly return numbers as float64. Our GetInt
	// must accept that. Inject via Sections since we hand-roll here.
	cfg := NewDefaultConfig()
	cfg.Sections["router"] = map[string]any{"concurrency": float64(8)}

	got, ok := cfg.GetInt("router", "concurrency")
	if !ok {
		t.Fatal("GetInt(router.concurrency) not found")
	}
	if got != 8 {
		t.Errorf("GetInt = %d, want 8", got)
	}
}

func TestConfigGetMissing(t *testing.T) {
	cfg := NewDefaultConfig()
	if _, ok := cfg.GetString("nonexistent", "key"); ok {
		t.Error("GetString on missing section should return ok=false")
	}
	if _, ok := cfg.GetInt("nonexistent", "key"); ok {
		t.Error("GetInt on missing section should return ok=false")
	}
	if _, ok := cfg.GetBool("nonexistent", "key"); ok {
		t.Error("GetBool on missing section should return ok=false")
	}
}

func TestConfigGetReturnsCopy(t *testing.T) {
	// Critical: callers must not be able to mutate the internal map.
	cfg := NewDefaultConfig()
	m := cfg.Get("router")
	m["concurrency"] = "WRONG" // string instead of int

	// Re-fetch: must be unchanged.
	m2 := cfg.Get("router")
	if m2["concurrency"] == "WRONG" {
		t.Error("Get() returned a reference, not a copy — caller mutation leaked")
	}
}

func TestExpandHomeWindows(t *testing.T) {
	// Phase 1: ~user/... is NOT expanded (no user lookup).
	// Phase 1: ~ and ~/... ARE expanded using HOME or USERPROFILE.
	t.Setenv("HOME", "")
	t.Setenv("USERPROFILE", `C:\Users\wizard`)

	cases := []struct {
		in, want string
	}{
		{"~/medit/qa", `C:\Users\wizard\medit\qa`},
		{"~", `C:\Users\wizard`},
		{"/abs/path", "/abs/path"},
		{"relative/path", "relative/path"},
		{"~other/foo", "~other/foo"}, // unsupported
	}
	for _, c := range cases {
		got := expandHome(c.in)
		// Windows path joining uses \ ; on MSYS bash it's /
		// Normalize for comparison.
		if normalize(got) != normalize(c.want) {
			t.Errorf("expandHome(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

func TestLoadFileNotFound(t *testing.T) {
	_, err := LoadFile(filepath.Join(t.TempDir(), "nope.yaml"))
	if err == nil {
		t.Error("LoadFile on missing file should return error")
	}
}

func TestLoadFileExists(t *testing.T) {
	dir := t.TempDir()
	p := filepath.Join(dir, "config.yaml")
	if err := writeFile(p, "version: 1\n"); err != nil {
		t.Fatal(err)
	}
	cfg, err := LoadFile(p)
	if err != nil {
		t.Fatalf("LoadFile: %v", err)
	}
	if cfg.Path != p {
		t.Errorf("Path = %q, want %q", cfg.Path, p)
	}
	if cfg.Version != 1 {
		t.Errorf("Version = %d, want 1", cfg.Version)
	}
}

// --- helpers ---

func contains(ss []string, s string) bool {
	for _, x := range ss {
		if x == s {
			return true
		}
	}
	return false
}

func normalize(p string) string {
	return strings.ReplaceAll(filepath.ToSlash(p), "\\", "/")
}

func writeFile(path, content string) error {
	return writeFileImpl(path, []byte(content))
}
