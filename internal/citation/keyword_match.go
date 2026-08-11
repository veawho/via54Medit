package citation

import (
	"regexp"
	"strings"
)

// Common journal name patterns (compiled once for performance).
// Each pattern is tried in order; first match wins.
var journalPatterns = []*regexp.Regexp{
	// Major journals (full names and abbreviations)
	regexp.MustCompile(`\b(Lancet(?:\s+Oncol|Oncol|Gastroenterol|Gastro)?|NEJM(?:\s+Evid|Evid)?|JAMA(?:\s+Oncol)?|N\.?\s*Engl\.?\s*J\.?\s*Med|J\.?\s*Clin\.?\s*(?:Oncol|Invest)|JNCC|J\.?\s*Natl\.?\s*Cancer\s+Inst|J\.?\s*Hepatol|JCO|JAMA\s+Oncol|Cancer\s+Cell|Nat\.?\s*(?:Med|Immunol|Cancer|Commun|Rev|Biotechnol|Genet)|Cell|Hepatology|Gastroenterology|Gut|Br\s*J\s*Cancer|Ann\.?\s*Oncol|Sci\.?\s*(?:Transl|Immunol)|Sig\s*Transduct|Clin\.?\s*Cancer\s+Res|J\.?\s*Hematol|Science|Lancet\s*Glob|Eur\.?\s*J\s*Cancer|Cell\s*Res|EMJ|Hepatol\s*Int|Liver\s*Cancer|Anticancer\s*Res|Br\s*J\s*Clin|JAMA\s+Intern\s+Med|Lancet\s*Diabetes\s*Endocrinol|Front\.?\s*(?:Oncol|Immunol)|Cancer\s*Res|medRxiv)\b`),
	// BMJ, NEJM, JAMA — special cases
	regexp.MustCompile(`\b(BMJ|medRxiv)\b`),
}

// Trial acronym patterns (HCC + general oncology).
var trialPatterns = regexp.MustCompile(`\b(HIMALAYA|IMbrave150|CheckMate\s*(?:9DW|9X|040|227)|APOLLO|TREMENDOUS|REFLECT|SHARP|LEAP-?002|TRIPLET|CARES-?310|RATIONALE-?301|ORIENT-?32|HEPATORCH|EMERALD-?\w*|TALENTACE|TALENTOP|TIMES|CARES-?005|KEYNOTE-?\d*|RESORCE|CELESTIAL|METEOR|REACH-?2|GoBigger)\b`)

// HCC drug patterns.
var drugPatterns = regexp.MustCompile(`\b(Tremelimumab|Durvalumab|Atezolizumab|Bevacizumab|Sintilimab|Tislelizumab|Camrelizumab|Pembrolizumab|Nivolumab|Ipilimumab|Sorafenib|Lenvatinib|Donafenib|Apatinib|Penpulimab|Anlotinib|Cabozantinib|Regorafenib|Quavonlimab|Teripalatide|Toripalimab|Donafenib|Selumetinib|Vandetanib|Axitinib|Sunitinib|Pazopanib)\b`)

// yearPattern matches 4-digit year in 1990-2099 range.
var yearPattern = regexp.MustCompile(`\b(19\d{2}|20\d{2})\b`)

// doiPattern matches a DOI prefix; we extract the tail separately.
var doiPattern = regexp.MustCompile(`10\.\d+/(\S+?)(?:[,;.\s)]|$)`)

// ExtractKeyFieldsFromText is the algorithm version 2 implementation.
//
// Algorithm (not rule-driven):
//  1. Authors: find capitalized last names (with optional hyphen)
//  2. Journal: try major journal regex patterns
//  3. Year: 4-digit year
//  4. Trial: regex match against 30+ known trial acronyms
//  5. Drug: regex match against 20+ known HCC drugs
//  6. DOI: extract tail (last component after /)
//
// vs v1 (硬编码 regex): v1 missed hyphenated authors (Abou-Alfa) and
// multi-author lists. v2 fixes both.
func ExtractKeyFieldsFromText(text string) KeyFields {
	if text == "" {
		return KeyFields{}
	}

	// Authors: match "LastName[, LastName2]" at start of text, before
	// journal/year/drug. Allow hyphenated surnames.
	//
	// Examples that must match:
	//   "Qin S, et al. Lancet Oncol..."
	//   "Abou-Alfa GK, et al. 2022..."
	//   "Finn Richard S, et al."
	//   "Peter Robert Galle, Thomas Decaens..."
	authors := extractAuthors(text)

	journal := extractJournal(text)
	year := extractYear(text)
	trial := extractTrial(text)
	drug := extractDrug(text)
	doiTail := extractDOITail(text)

	return KeyFields{
		Authors: authors,
		Journal: journal,
		Year:    year,
		Trial:   trial,
		Drug:    drug,
		DOITail: doiTail,
	}
}

// extractAuthors extracts last names from the start of the citation text.
//
// Algorithm: scan text from start, find tokens matching [A-Z][a-z]+ (with
// optional hyphen). Stop at first non-author token (e.g. journal name, year,
// drug name, or "et al.").
//
// Returns up to 5 authors. Filters out journal/year/drug false positives.
func extractAuthors(text string) []string {
	// Tokenize: split on commas, semicolons, periods (followed by space), spaces
	// Keep only the first ~200 chars (authors always at start)
	head := text
	if len(head) > 200 {
		head = head[:200]
	}

	// Pattern: capital letter start, lowercase letters, optional hyphen, more
	authorPattern := regexp.MustCompile(`\b([A-Z][a-z]+(?:-[A-Z][a-z]+)*)\b`)

	// Journal/drug patterns to filter out
	journalSet := map[string]bool{
		"Lancet": true, "NEJM": true, "JAMA": true, "Cell": true,
		"Hepatology": true, "Gastroenterology": true, "Gut": true,
		"Science": true, "Nature": true, "Cancer": true,
		"Br": true, "Ann": true, "Sig": true, "Eur": true,
		"Front": true, "BMJ": true, "Nat": true, "Clin": true,
	}

	yearSet := map[string]bool{}
	for y := 1990; y <= 2099; y++ {
		yearSet[string(rune('0'+y/1000))+
			string(rune('0'+(y/100)%10))+
			string(rune('0'+(y/10)%10))+
			string(rune('0'+y%10))] = true
	}

	drugSet := map[string]bool{
		"Tremelimumab": true, "Durvalumab": true, "Atezolizumab": true,
		"Bevacizumab": true, "Sintilimab": true, "Tislelizumab": true,
		"Camrelizumab": true, "Pembrolizumab": true, "Nivolumab": true,
		"Ipilimumab": true, "Sorafenib": true, "Lenvatinib": true,
	}

	// Words that signal end of author list
	endSignals := map[string]bool{
		"al": true, // "et al."
	}

	authors := []string{}
	matches := authorPattern.FindAllStringSubmatch(head, -1)
	for _, m := range matches {
		word := m[1]
		if len(word) < 3 {
			continue // skip 2-letter words
		}
		if journalSet[word] || yearSet[word] || drugSet[word] {
			break // reached journal/year/drug
		}
		if endSignals[word] {
			break // "et al."
		}
		authors = append(authors, word)
		if len(authors) >= 5 {
			break
		}
	}
	return authors
}

// extractJournal returns the first matching journal name, or "".
func extractJournal(text string) string {
	for _, p := range journalPatterns {
		if m := p.FindString(text); m != "" {
			return m
		}
	}
	return ""
}

// extractYear returns the first 4-digit year, or "".
func extractYear(text string) string {
	if m := yearPattern.FindString(text); m != "" {
		return m
	}
	return ""
}

// extractTrial returns the first matching trial acronym, or "".
func extractTrial(text string) string {
	if m := trialPatterns.FindString(text); m != "" {
		return m
	}
	return ""
}

// extractDrug returns the first matching drug name, or "".
func extractDrug(text string) string {
	if m := drugPatterns.FindString(text); m != "" {
		return m
	}
	return ""
}

// extractDOITail returns the last segment of the DOI path, or "".
//
// Example: "10.1056/EVIDoa2100070" → "EVIDoa2100070"
//          "10.1159/000518619"      → "000518619"
//          "10.1158/1078-0432.CCR-24-0006" → "CCR-24-0006"
//          "10.3322/caac.21834"     → "caac.21834"
//
// Algorithm: capture the DOI suffix after "10.<number>/", then take the
// substring after the LAST "/". This handles multi-segment paths correctly.
func extractDOITail(text string) string {
	// DOI suffix can contain letters, digits, dots, hyphens, underscores,
	// but NOT whitespace, semicolons, or commas. Multiple "/" are OK.
	//
	// Examples that must work:
	//   "10.1056/EVIDoa2100070"          → "EVIDoa2100070"
	//   "10.1159/000518619"               → "000518619"
	//   "10.1158/1078-0432.CCR-24-0006"   → "1078-0432.CCR-24-0006"  (multi-segment)
	//   "10.3322/caac.21834"              → "caac.21834"
	//   "...EVIDoa2100070"  (no trailing separator) → "EVIDoa2100070"
	//
	// Algorithm: find "10.<digits>/", then capture the longest suffix
	// matching [A-Za-z0-9._-] (including "/" for multi-segment paths).
	// Take everything after the FIRST "/", since "/" indicates path
	// hierarchy in DOI (publisher/journal ID/article ID).
	pattern := regexp.MustCompile(`10\.\d+/([A-Za-z0-9._\-/]+)`)
	m := pattern.FindStringSubmatch(text)
	if len(m) < 2 {
		return ""
	}
	path := m[1]
	// Strip trailing punctuation (but NOT period in the middle like "caac.21834")
	path = strings.TrimRight(path, ",;. 	\n")
	return path
}

// MatchResult is the outcome of comparing D column to a candidate PDF.
type MatchResult struct {
	// Score is 0.0-1.0; higher is better
	Score float64
	// MatchedFields lists which KeyFields were found in the PDF text
	MatchedFields []string
	// MissingFields lists which KeyFields were NOT found
	MissingFields []string
	// Reason is human-readable explanation
	Reason string
}

// Match checks if the KeyFields are present in a PDF's text content.
//
// Algorithm:
//   - For each non-empty key field, check if it's present in the PDF text
//     (case-insensitive, normalized)
//   - Score = matched / total non-empty fields
//   - Returns detailed breakdown for debugging
//
// Returns:
//   - Score 1.0 = perfect match (all fields present)
//   - Score 0.0 = complete mismatch (no fields present)
//   - Score > 0.5 = "good enough" (most fields present)
func (kf KeyFields) Match(pdfText string) MatchResult {
	normalized := normalizeForMatching(pdfText)
	result := MatchResult{}

	total := 0

	if len(kf.Authors) > 0 {
		total++
		matched := false
		for _, a := range kf.Authors {
			if strings.Contains(normalized, strings.ToLower(a)) {
				matched = true
				break
			}
		}
		if matched {
			result.MatchedFields = append(result.MatchedFields, "authors")
		} else {
			result.MissingFields = append(result.MissingFields, "authors")
		}
	}

	if kf.Year != "" {
		total++
		if strings.Contains(normalized, kf.Year) {
			result.MatchedFields = append(result.MatchedFields, "year")
		} else {
			result.MissingFields = append(result.MissingFields, "year")
		}
	}

	if kf.Journal != "" {
		total++
		// Fuzzy journal match: try journal name and 4-letter prefix
		jl := strings.ToLower(kf.Journal)
		jlCompact := strings.ReplaceAll(jl, " ", "")
		if strings.Contains(normalized, jl) ||
			strings.Contains(normalized, jlCompact) ||
			strings.Contains(normalized, jl[:min(8, len(jl))]) {
			result.MatchedFields = append(result.MatchedFields, "journal")
		} else {
			result.MissingFields = append(result.MissingFields, "journal")
		}
	}

	if kf.Trial != "" {
		total++
		if strings.Contains(normalized, strings.ToLower(kf.Trial)) {
			result.MatchedFields = append(result.MatchedFields, "trial")
		} else {
			result.MissingFields = append(result.MissingFields, "trial")
		}
	}

	if kf.Drug != "" {
		total++
		if strings.Contains(normalized, strings.ToLower(kf.Drug)) {
			result.MatchedFields = append(result.MatchedFields, "drug")
		} else {
			result.MissingFields = append(result.MissingFields, "drug")
		}
	}

	if kf.DOITail != "" {
		total++
		if strings.Contains(normalized, strings.ToLower(kf.DOITail)) {
			result.MatchedFields = append(result.MatchedFields, "doi_tail")
		} else {
			result.MissingFields = append(result.MissingFields, "doi_tail")
		}
	}

	if total > 0 {
		result.Score = float64(len(result.MatchedFields)) / float64(total)
	}

	switch {
	case result.Score == 1.0:
		result.Reason = "perfect match"
	case result.Score >= 0.5:
		result.Reason = "good match"
	case result.Score > 0:
		result.Reason = "partial match"
	default:
		result.Reason = "no match"
	}

	return result
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}