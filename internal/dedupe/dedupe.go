// Package dedupe merges duplicate citations returned by the 4 sources.
//
// The router (Phase 2) collects citations from PubMed, OpenAlex, S2, and
// antfu. The same paper can appear multiple times:
//   - PubMed and OpenAlex both return it (different IDs, same PMID/DOI)
//   - antfu extracts a reference whose URL happens to match OpenAlex
//   - OpenAlex and S2 both surface it (different IDs, same DOI)
//
// dedupe.go provides a single function Dedupe() that:
//  1. Groups citations by PMID/DOI where available
//  2. Falls back to title-similarity (simhash, hamming distance < 3)
//     for citations with no identifiers
//  3. Picks the "best" representative from each group (max CitedBy+FWCI)
//  4. Merges SourceOrigin so we know which sources confirmed the paper
//
// Output is sorted by score descending. Caller decides the limit.
package dedupe

import (
	"crypto/sha1"
	"encoding/binary"
	"sort"
	"strings"

	"github.com/veawho/via54Medit/pkg/types"
)

// Dedupe returns the merged list of citations, with duplicates removed.
// Within each duplicate group, the citation with the highest "richness"
// score is kept (CitedBy + FWCI*10), and SourceOrigin is merged.
func Dedupe(in []types.Citation) []types.Citation {
	if len(in) == 0 {
		return nil
	}

	// Phase 1: group by PMID or DOI
	idGroups := make(map[string][]*types.Citation) // group key → citations
	idIndex := make(map[string]string)             // each c.ID → group key
	noID := make([]*types.Citation, 0, len(in))

	for i := range in {
		c := &in[i]
		key := groupKey(c)
		if key == "" {
			noID = append(noID, c)
			continue
		}
		idGroups[key] = append(idGroups[key], c)
		idIndex[c.ID] = key
	}

	// Phase 2: for citations without PMID/DOI, try simhash match
	// against already-grouped items.
	for _, c := range noID {
		hash := simhash(c.Title)
		merged := false
		for _, group := range idGroups {
			if len(group) == 0 {
				continue
			}
			if hammingDistance(hash, simhash(group[0].Title)) < 3 {
				group = append(group, c)
				merged = true
				break
			}
		}
		if !merged {
			// New group keyed by simhash.
			idGroups[hash] = append(idGroups[hash], c)
		}
	}

	// Phase 3: pick best from each group + merge SourceOrigin
	out := make([]types.Citation, 0, len(idGroups))
	for _, group := range idGroups {
		if len(group) == 0 {
			continue
		}
		best := *group[0]
		mergedOrigins := map[string]bool{}
		if best.SourceOrigin != nil {
			for _, s := range best.SourceOrigin {
				mergedOrigins[s] = true
			}
		}
		for _, c := range group[1:] {
			if richness(c) > richness(&best) {
				best = *c
			}
			for _, s := range c.SourceOrigin {
				mergedOrigins[s] = true
			}
		}
		best.SourceOrigin = sortedKeys(mergedOrigins)
		out = append(out, best)
	}

	// Phase 4: sort by richness desc (stable for equal scores)
	sort.SliceStable(out, func(i, j int) bool {
		return richness(&out[i]) > richness(&out[j])
	})
	return out
}

// groupKey returns a normalized key for PMID/DOI matching.
// Empty string means the citation has no usable identifier.
func groupKey(c *types.Citation) string {
	if c.PMID != "" {
		return "pmid:" + c.PMID
	}
	if c.DOI != "" {
		// Normalize: lowercase, strip whitespace
		return "doi:" + strings.ToLower(strings.TrimSpace(c.DOI))
	}
	return ""
}

// richness scores a citation for ranking.
// Weight choices (Phase 1 heuristic, may revisit in Phase 2.5):
//   - CitedBy: 1 point per cite
//   - FWCI: 10× multiplier (FWCI 1.0 = field average; >1 = above average)
//   - source_diversity: 5 points per unique source
//   - recency: 0 (not yet — Phase 2.5 will add Year weighting)
func richness(c *types.Citation) float64 {
	score := float64(c.CitedBy)
	score += c.FWCI * 10
	score += float64(len(c.SourceOrigin)) * 5
	return score
}

// sortedKeys returns the map keys in sorted order.
func sortedKeys(m map[string]bool) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

// simhash computes a 64-bit fingerprint of a string for near-duplicate
// detection. We tokenize on whitespace + lowercase, hash each token
// with SHA-1, and combine via bit-counting (the standard simhash
// algorithm).
//
// Citations with hamming distance < 3 are considered the same paper.
// This is intentionally simple — Phase 2.5 may add n-gram tokens.
func simhash(s string) string {
	s = strings.ToLower(strings.TrimSpace(s))
	if s == "" {
		return ""
	}
	tokens := strings.FieldsFunc(s, func(r rune) bool {
		return r == ' ' || r == '\t' || r == '\n' || r == '\r' || r == '.' || r == ',' || r == ';' || r == ':' || r == '!' || r == '?'
	})
	if len(tokens) == 0 {
		return ""
	}
	var counts [64]int
	for _, tok := range tokens {
		sum := sha1.Sum([]byte(tok))
		// Use first 8 bytes of SHA-1 as our 64-bit hash.
		h := binary.BigEndian.Uint64(sum[:8])
		for i := 0; i < 64; i++ {
			if h&(1<<uint(i)) != 0 {
				counts[i]++
			} else {
				counts[i]--
			}
		}
	}
	// Build the fingerprint.
	var fp uint64
	for i := 0; i < 64; i++ {
		if counts[i] > 0 {
			fp |= 1 << uint(i)
		}
	}
	// Encode as 8-byte string for storage in a map.
	out := make([]byte, 8)
	binary.BigEndian.PutUint64(out, fp)
	return string(out)
}

// hammingDistance counts the number of differing bits between two
// simhash fingerprints. < 3 means "probably the same paper".
func hammingDistance(a, b string) int {
	if len(a) != 8 || len(b) != 8 {
		return 64 // treat as completely different
	}
	va := binary.BigEndian.Uint64([]byte(a))
	vb := binary.BigEndian.Uint64([]byte(b))
	xor := va ^ vb
	// Brian Kernighan's bit counting
	count := 0
	for xor != 0 {
		xor &= xor - 1
		count++
	}
	return count
}
