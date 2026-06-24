package foundation

import "os"

// writeFileImpl is a thin shim so tests don't import os directly
// (keeps the test file's import list minimal).
func writeFileImpl(path string, data []byte) error {
	return os.WriteFile(path, data, 0o600)
}

// sortedKeys returns a sorted copy of a map's keys (test helper).
// Used by tests that need a stable iteration order.
func sortedKeys[V any](m map[string]V) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	// import sort in tests is fine; this is a test helper only
	sortStrings(keys)
	return keys
}

func sortStrings(ss []string) {
	for i := 1; i < len(ss); i++ {
		for j := i; j > 0 && ss[j-1] > ss[j]; j-- {
			ss[j-1], ss[j] = ss[j], ss[j-1]
		}
	}
}
