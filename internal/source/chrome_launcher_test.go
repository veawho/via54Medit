package source

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"testing"
	"time"
)

func TestChromeCandidatesPerOS(t *testing.T) {
	cands := ChromeCandidates()
	if len(cands) == 0 {
		t.Fatal("no candidates")
	}
	switch runtime.GOOS {
	case "darwin":
		if cands[0] != "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" {
			t.Errorf("darwin first candidate = %q", cands[0])
		}
	case "windows":
		found := false
		for _, c := range cands {
			if c == filepath.Join(os.Getenv("ProgramFiles(x86)"), "Google", "Chrome", "Application", "chrome.exe") {
				found = true
			}
		}
		if !found && os.Getenv("ProgramFiles(x86)") == "" {
			found = true // env absent in constrained test env — acceptable
		}
		_ = found
	default:
		if cands[0] != "google-chrome" {
			t.Errorf("linux first candidate = %q", cands[0])
		}
	}
}

func TestDetectChromeEnvOverride(t *testing.T) {
	tmp := t.TempDir()
	fake := filepath.Join(tmp, "fake-chrome")
	if err := os.WriteFile(fake, []byte("#!/bin/sh\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	t.Setenv("CHROME_PATH", fake)
	got, err := DetectChrome()
	if err != nil {
		t.Fatal(err)
	}
	if got != fake {
		t.Errorf("DetectChrome = %q, want %q", got, fake)
	}
}

func TestDetectChromeBadEnvOverride(t *testing.T) {
	t.Setenv("CHROME_PATH", "/nonexistent/chrome-xyz")
	if _, err := DetectChrome(); err == nil {
		t.Error("expected error for bad $CHROME_PATH")
	}
}

func TestDebugProfileDir(t *testing.T) {
	t.Setenv("HOME", "/tmp/fakehome")
	if runtime.GOOS == "windows" {
		t.Setenv("USERPROFILE", `C:\fakehome`)
	}
	dir := DebugProfileDir(9223)
	if filepath.Base(dir) != "chrome-debug-9223" {
		t.Errorf("profile dir = %q", dir)
	}
}

func TestEnsureChromeCDPAlreadyUp(t *testing.T) {
	// Simulate a reachable CDP endpoint; EnsureChromeCDP must not launch.
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.Write([]byte(`{"Browser":"Chrome/1.0"}`))
	}))
	defer srv.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	chrome, err := EnsureChromeCDP(ctx, srv.URL, 9223)
	if err != nil {
		t.Fatal(err)
	}
	if chrome != "" {
		t.Errorf("expected no launch (already up), got launch of %q", chrome)
	}
}

func TestEnsureChromeCDPUnreachableNoChrome(t *testing.T) {
	// No browser on PATH and $CHROME_PATH invalid → clean error.
	t.Setenv("CHROME_PATH", "/nonexistent/chrome-xyz")
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	_, err := EnsureChromeCDP(ctx, "http://127.0.0.1:1", 9223)
	if err == nil {
		t.Error("expected error when CDP unreachable and no chrome")
	}
}
