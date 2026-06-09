// Package version exposes build-time version information.
package version

import "fmt"

// These variables are set via -ldflags at build time.
var (
	// Version is the semver (e.g., "0.1.0").
	Version = "0.1.0-phase0"

	// Commit is the git SHA.
	Commit = "unknown"

	// BuildDate is the ISO 8601 timestamp.
	BuildDate = "unknown"

	// GoVersion is the Go compiler version.
	GoVersion = "unknown"
)

// Full returns a multi-line version string for `medit version`.
func Full() string {
	return fmt.Sprintf(
		"via54Medit %s\n  commit:    %s\n  built:     %s\n  go:        %s\n  license:   AGPL-3.0 (source) + MIT (templates)\n  repo:      github.com/veawho/via54Medit",
		Version, Commit, BuildDate, GoVersion,
	)
}

// Short returns a one-line version (for `medit --version`).
func Short() string {
	return fmt.Sprintf("via54Medit %s (%s)", Version, Commit)
}
