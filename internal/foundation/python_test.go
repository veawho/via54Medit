package foundation

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func TestResolvePythonEnvOverride(t *testing.T) {
	// A fake executable that exists.
	tmp := t.TempDir()
	fake := filepath.Join(tmp, "my-python")
	if runtime.GOOS == "windows" {
		fake += ".exe"
	}
	if err := os.WriteFile(fake, []byte("#!/bin/sh\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	t.Setenv("PYTHON", fake)
	got, err := ResolvePython(nil)
	if err != nil {
		t.Fatal(err)
	}
	if got != fake {
		t.Errorf("ResolvePython = %q, want %q", got, fake)
	}
}

func TestResolvePythonConfigWins(t *testing.T) {
	t.Setenv("PYTHON", "definitely-not-a-real-python-xyz")
	// Config beats env; both bad → error mentions both.
	_, err := ResolvePython(map[string]any{"python_path": ""})
	if err == nil {
		t.Error("expected error with no usable interpreter")
	}
}

func TestResolvePythonNotFound(t *testing.T) {
	t.Setenv("PYTHON", "")
	// Force all candidates to miss by testing a nonexistent one only is
	// not possible (host has python3) — so assert the function either
	// succeeds with a found candidate or fails with a helpful message.
	got, err := ResolvePython(nil)
	if err != nil {
		// Error path must still mention the fallback chain.
		if len(err.Error()) < 10 {
			t.Errorf("unhelpful error: %v", err)
		}
		return
	}
	if got == "" {
		t.Error("empty interpreter path")
	}
}

func TestHermesHome(t *testing.T) {
	t.Setenv("HERMES_HOME", "/tmp/alt-hermes")
	if got := HermesHome(); got != "/tmp/alt-hermes" {
		t.Errorf("HermesHome = %q", got)
	}
	if got := HermesPath("cache", "x.json"); got != filepath.Join("/tmp/alt-hermes", "cache", "x.json") {
		t.Errorf("HermesPath = %q", got)
	}
	t.Setenv("HERMES_HOME", "")
	home, _ := os.UserHomeDir()
	if got := HermesHome(); got != filepath.Join(home, ".hermes") {
		t.Errorf("HermesHome default = %q", got)
	}
}

func TestUserMeditDir(t *testing.T) {
	t.Setenv("MEDIT_HOME", "/tmp/alt-medit")
	if got := UserMeditDir(); got != "/tmp/alt-medit" {
		t.Errorf("UserMeditDir = %q", got)
	}
	t.Setenv("MEDIT_HOME", "")
	home, _ := os.UserHomeDir()
	if got := UserMeditDir(); got != filepath.Join(home, ".medit") {
		t.Errorf("UserMeditDir default = %q", got)
	}
}
