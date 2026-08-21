// Python interpreter resolution and portable home-dir helpers.
//
// Cross-platform deployment (2026-08-21): every place that shells out to
// Python must go through ResolvePython instead of hardcoding a
// interpreter name, so a fresh machine (Windows/macOS/Linux) works with
// whatever Python it has. Order: explicit config > $PYTHON > python3.11
// > python3 > python.
package foundation

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
)

// PythonCandidates is the interpreter fallback chain (most specific first).
var PythonCandidates = []string{"python3.11", "python3", "python"}

// ResolvePython finds a usable Python interpreter.
//
// cfg["python_path"] (if non-empty) wins, then $PYTHON, then the
// candidate chain. Each candidate is verified to exist (and, on Windows,
// has a .exe variant tried as well).
func ResolvePython(cfg map[string]any) (string, error) {
	if v, ok := cfg["python_path"].(string); ok && v != "" {
		if isExecutable(v) {
			return v, nil
		}
		return "", fmt.Errorf("python_path %q not found", v)
	}
	if v := os.Getenv("PYTHON"); v != "" {
		if isExecutable(v) {
			return v, nil
		}
		return "", fmt.Errorf("$PYTHON %q not found", v)
	}
	for _, c := range PythonCandidates {
		if p, err := exec.LookPath(c); err == nil {
			return p, nil
		}
		if runtime.GOOS == "windows" {
			if p, err := exec.LookPath(c + ".exe"); err == nil {
				return p, nil
			}
		}
	}
	return "", fmt.Errorf("no python interpreter found (tried %v; set $PYTHON or config python_path)", PythonCandidates)
}

// ResolvePythonSimple is ResolvePython without a config map.
func ResolvePythonSimple() (string, error) {
	return ResolvePython(nil)
}

// isExecutable checks a path exists and is executable (or a .bat/.cmd on
// Windows, where LookPath-compatible resolution is looser).
func isExecutable(p string) bool {
	info, err := os.Stat(p)
	if err != nil {
		return false
	}
	if info.IsDir() {
		return false
	}
	if runtime.GOOS == "windows" {
		switch filepath.Ext(p) {
		case ".exe", ".bat", ".cmd", ".ps1", "":
			return true
		}
		return false
	}
	return info.Mode()&0o111 != 0
}

// HermesHome returns the hermes data root: $HERMES_HOME > ~/.hermes.
// Everything that used to hardcode ~/.hermes must route through this so
// a fresh machine can point at an alternate layout.
func HermesHome() string {
	if v := os.Getenv("HERMES_HOME"); v != "" {
		return v
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return ".hermes"
	}
	return filepath.Join(home, ".hermes")
}

// HermesPath joins a relative path under HermesHome.
func HermesPath(rel ...string) string {
	parts := append([]string{HermesHome()}, rel...)
	return filepath.Join(parts...)
}

// UserMeditDir returns the via54Medit data root (~/.medit, overridable
// via MEDIT_HOME for portable installs).
func UserMeditDir() string {
	if v := os.Getenv("MEDIT_HOME"); v != "" {
		return v
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return ".medit"
	}
	return filepath.Join(home, ".medit")
}

// LookPathWithHint tries exec.LookPath and wraps the error with an
// install hint that names the tool and the current OS package manager.
func LookPathWithHint(name string) error {
	if _, err := exec.LookPath(name); err == nil {
		return nil
	}
	hint := "install it and put it on PATH"
	switch runtime.GOOS {
	case "darwin":
		hint = "brew install " + name
	case "linux":
		hint = "apt install " + name + " (or your distro equivalent)"
	case "windows":
		hint = "download the installer and add it to PATH"
	}
	return fmt.Errorf("%s not found on PATH (%s)", name, hint)
}
