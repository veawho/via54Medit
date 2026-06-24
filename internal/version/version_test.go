// Package version_test covers the build-time version metadata.
//
// Phase 0 baseline: 4 cases. Phase 1 will extend when -ldflags wiring lands.
package version_test

import (
	"strings"
	"testing"

	"github.com/veawho/via54Medit/internal/version"
)

// TestVersionNotEmpty guards against an empty semver string reaching
// the JSON output that downstream automation parses.
func TestVersionNotEmpty(t *testing.T) {
	if version.Version == "" {
		t.Fatal("Version must not be empty (default in source: 0.1.0-phase0)")
	}
	if !strings.HasPrefix(version.Version, "0.") {
		t.Errorf("Version %q: expected 0.x semver pre-1.0", version.Version)
	}
}

// TestCommitPlaceholder pins the "unknown" default behavior.
// Real builds inject via -ldflags "-X .../version.Commit=$(git rev-parse HEAD)".
func TestCommitPlaceholder(t *testing.T) {
	// Phase 0 default is "unknown"; Phase 1+ must override at build time.
	if version.Commit == "" {
		t.Fatal("Commit must not be empty (default in source: \"unknown\")")
	}
}

// TestFullContainsKeyFields ensures the `medit version` multi-line
// output includes every value a user / auditor might grep for.
func TestFullContainsKeyFields(t *testing.T) {
	full := version.Full()
	want := []string{
		"via54Medit",
		"commit:",
		"built:",
		"go:",
		"license:",
		"AGPL-3.0",
		"MIT",
		"github.com/veawho/via54Medit",
	}
	for _, w := range want {
		if !strings.Contains(full, w) {
			t.Errorf("Full() missing %q\n--- full output ---\n%s", w, full)
		}
	}
}

// TestShortFormat pins the `medit --version` one-line shape.
// cobra's rootCmd.Version field uses Short(); changing format breaks
// any tooling that greps for "via54Medit X.Y.Z".
func TestShortFormat(t *testing.T) {
	short := version.Short()
	if !strings.HasPrefix(short, "via54Medit ") {
		t.Errorf("Short() = %q: must start with \"via54Medit \"", short)
	}
	if !strings.Contains(short, "(") || !strings.Contains(short, ")") {
		t.Errorf("Short() = %q: must include commit in parens", short)
	}
}
