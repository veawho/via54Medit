// Chrome auto-detection and debug-instance launch.
//
// Cross-platform deployment (2026-08-21): every CDP-dependent feature
// (antfu, fulltext Tier 2) used to require a manually launched Chrome
// with --remote-debugging-port=9223. This file finds the browser on the
// current OS, starts a dedicated debug instance with an isolated profile,
// and lets callers ensure CDP is reachable with one call.
package source

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"
)

// ChromeCandidates returns browser executables to try, most specific
// first, for the current OS. Edge/Chromium included as fallbacks.
func ChromeCandidates() []string {
	switch runtime.GOOS {
	case "darwin":
		return []string{
			"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
			"/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
			"/Applications/Chromium.app/Contents/MacOS/Chromium",
			"/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
		}
	case "windows":
		prog := os.Getenv("ProgramFiles")
		prog86 := os.Getenv("ProgramFiles(x86)")
		local := os.Getenv("LOCALAPPDATA")
		var out []string
		for _, base := range []string{prog86, prog} {
			if base == "" {
				continue
			}
			out = append(out,
				filepath.Join(base, "Google", "Chrome", "Application", "chrome.exe"),
				filepath.Join(base, "Microsoft", "Edge", "Application", "msedge.exe"))
		}
		if local != "" {
			out = append(out, filepath.Join(local, "Google", "Chrome", "Application", "chrome.exe"))
		}
		return out
	default: // linux and friends
		return []string{"google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"}
	}
}

// DetectChrome returns the first existing browser executable, or an
// error listing what was tried. Respects $CHROME_PATH override.
func DetectChrome() (string, error) {
	if v := os.Getenv("CHROME_PATH"); v != "" {
		if _, err := os.Stat(v); err == nil {
			return v, nil
		}
		return "", fmt.Errorf("chrome: $CHROME_PATH %q not found", v)
	}
	for _, c := range ChromeCandidates() {
		if strings.ContainsRune(c, filepath.Separator) || (runtime.GOOS == "windows" && strings.Contains(c, "\\")) {
			if _, err := os.Stat(c); err == nil {
				return c, nil
			}
			continue
		}
		if p, err := exec.LookPath(c); err == nil {
			return p, nil
		}
	}
	return "", fmt.Errorf("chrome: no Chrome/Edge/Chromium found (tried %v; set $CHROME_PATH)", ChromeCandidates())
}

// DebugProfileDir returns the isolated profile dir used for the debug
// instance (kept separate so the user's daily browser is untouched).
func DebugProfileDir(port int) string {
	home, err := os.UserHomeDir()
	if err != nil {
		home = "."
	}
	return filepath.Join(home, ".medit", fmt.Sprintf("chrome-debug-%d", port))
}

// LaunchChromeDebug starts a headless-capable Chrome with the remote
// debugging port on an isolated profile. Returns the running command.
// The caller is responsible for keeping the *exec.Cmd referenced (it
// runs detached; Process will be released by the OS when done).
func LaunchChromeDebug(port int) (*exec.Cmd, error) {
	chrome, err := DetectChrome()
	if err != nil {
		return nil, err
	}
	profile := DebugProfileDir(port)
	if err := os.MkdirAll(profile, 0o755); err != nil {
		return nil, fmt.Errorf("chrome: mkdir profile: %w", err)
	}
	args := []string{
		fmt.Sprintf("--remote-debugging-port=%d", port),
		"--remote-debugging-address=127.0.0.1",
		"--user-data-dir=" + profile,
		"--no-first-run",
		"--no-default-browser-check",
		"--disable-background-networking",
	}
	cmd := exec.Command(chrome, args...)
	// Detach: never block the CLI waiting on the browser process.
	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("chrome: start: %w", err)
	}
	_ = cmd.Process.Release()
	return cmd, nil
}

// EnsureChromeCDP makes sure a Chrome debug instance answers on cdpURL:
// health check → if unreachable, detect+launch → poll until healthy.
// Returns the browser path used (or "" if CDP was already up).
func EnsureChromeCDP(ctx context.Context, cdpURL string, port int) (string, error) {
	if err := chromeHealthOnce(cdpURL); err == nil {
		return "", nil // already reachable
	}
	chrome, err := DetectChrome()
	if err != nil {
		return "", fmt.Errorf("chrome CDP unreachable and %w", err)
	}
	if _, err := LaunchChromeDebug(port); err != nil {
		return "", err
	}
	// Poll health for up to ~15s (Chrome can take a moment to open the port).
	deadline := time.Now().Add(15 * time.Second)
	for time.Now().Before(deadline) {
		if err := chromeHealthOnce(cdpURL); err == nil {
			return chrome, nil
		}
		select {
		case <-ctx.Done():
			return "", ctx.Err()
		case <-time.After(500 * time.Millisecond):
		}
	}
	return "", fmt.Errorf("chrome CDP not reachable at %s after launch (see `medit browser health`)", cdpURL)
}

// chromeHealthOnce is the single lightweight health probe.
func chromeHealthOnce(baseURL string) error {
	req, err := http.NewRequest("GET", strings.TrimRight(baseURL, "/")+"/json/version", nil)
	if err != nil {
		return err
	}
	resp, err := (&http.Client{Timeout: 2 * time.Second}).Do(req)
	if err != nil {
		return fmt.Errorf("chrome CDP: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode/100 != 2 {
		return fmt.Errorf("chrome CDP: HTTP %d", resp.StatusCode)
	}
	return nil
}
