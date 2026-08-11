package citation

import (
	"strings"
	"testing"
)

// Test data is derived from the 雷管方案_文献整理 project, which is the
// primary consumer of this library. The corrections are continuously
// integrated into via54Medit (see internal/citation/corrections/).
//
// Golden cases:
//
//	1. Simple format:  "Qin S, et al. Lancet Oncol. 2025..."
//	2. Hyphenated author: "Abou-Alfa GK, et al. 2022. NEJM Evid..."
//	3. Multi-author:    "Peter Robert Galle, Thomas Decaens, Masatoshi Kudo..."
//	4. DOI tail:        "10.1056/EVIDoa2100070" → "EVIDoa2100070"
//	5. Trial acronym:   "HIMALAYA", "IMbrave150", "CheckMate 9DW"
//	6. Drug name:       "Tremelimumab", "Atezolizumab"
//	7. Edge case:       empty input → empty KeyFields

func TestExtractKeyFields_SimpleFormat(t *testing.T) {
	c := Citation{
		Reference: "Qin S, et al. Lancet Oncol. 2025 Dec;26(12):1598-1611.",
	}
	kf := c.ExtractKeyFields()

	if len(kf.Authors) == 0 || kf.Authors[0] != "Qin" {
		t.Errorf("Authors = %v, want [Qin ...]", kf.Authors)
	}
	if kf.Journal != "Lancet Oncol" && kf.Journal != "Lancet" {
		t.Errorf("Journal = %q, want Lancet Oncol", kf.Journal)
	}
	if kf.Year != "2025" {
		t.Errorf("Year = %q, want 2025", kf.Year)
	}
}

func TestExtractKeyFields_HyphenatedAuthor(t *testing.T) {
	// v1 algorithm missed "Abou-Alfa" — fixed in v2.
	// DOI in this case is in DOI metadata field, not in Reference text.
	c := Citation{
		Reference: "Abou-Alfa GK, et al. 2022. NEJM Evid. 1(8): EVIDoa2100070",
		DOI:       "10.1056/EVIDoa2100070",
	}
	kf := c.ExtractKeyFields()

	found := false
	for _, a := range kf.Authors {
		if a == "Abou-Alfa" {
			found = true
		}
	}
	if !found {
		t.Errorf("Abou-Alfa should be detected as author, got: %v", kf.Authors)
	}
	if kf.Year != "2022" {
		t.Errorf("Year = %q, want 2022", kf.Year)
	}
	if kf.DOITail != "EVIDoa2100070" {
		t.Errorf("DOITail = %q, want EVIDoa2100070", kf.DOITail)
	}
}

func TestExtractKeyFields_MultiAuthor(t *testing.T) {
	c := Citation{
		Reference: "Peter Robert Galle, Thomas Decaens, Masatoshi Kudo, et al. 2024 ASCO LBA4008.",
	}
	kf := c.ExtractKeyFields()

	if len(kf.Authors) < 2 || kf.Authors[0] != "Peter" || kf.Authors[1] != "Robert" {
		t.Errorf("Authors = %v, want first 2 to be [Peter, Robert]", kf.Authors)
	}
	if kf.Year != "2024" {
		t.Errorf("Year = %q, want 2024", kf.Year)
	}
}

func TestExtractKeyFields_TrialAndDrug(t *testing.T) {
	c := Citation{
		Reference: "Tremelimumab plus Durvalumab in Unresectable HCC (HIMALAYA). NEJMEvid 2022.",
	}
	kf := c.ExtractKeyFields()

	if kf.Trial != "HIMALAYA" {
		t.Errorf("Trial = %q, want HIMALAYA", kf.Trial)
	}
	if kf.Drug != "Tremelimumab" {
		t.Errorf("Drug = %q, want Tremelimumab", kf.Drug)
	}
}

func TestExtractKeyFields_EmptyInput(t *testing.T) {
	kf := ExtractKeyFieldsFromText("")
	if len(kf.Authors) > 0 || kf.Journal != "" || kf.Year != "" {
		t.Errorf("empty input should give empty KeyFields, got: %+v", kf)
	}
}

func TestExtractKeyFields_CrossrefDOIFormat(t *testing.T) {
	// DOIs in different formats should all extract tail correctly.
	tests := []struct {
		input string
		want  string
	}{
		{"10.1056/EVIDoa2100070", "EVIDoa2100070"},
		{"10.1159/000518619", "000518619"},
		{"10.1158/1078-0432.CCR-24-0006", "1078-0432.CCR-24-0006"},
		{"10.3322/caac.21834", "caac.21834"},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			got := extractDOITail(tt.input)
			if got != tt.want {
				t.Errorf("extractDOITail(%q) = %q, want %q", tt.input, got, tt.want)
			}
		})
	}
}

// TestKeyFieldsMatch_PerfectMatch verifies the match algorithm scores 1.0
// when all fields are present.
func TestKeyFieldsMatch_PerfectMatch(t *testing.T) {
	kf := KeyFields{
		Authors: []string{"Qin"},
		Journal: "Lancet",
		Year:    "2025",
		Trial:   "IMbrave150",
		Drug:    "Atezolizumab",
		DOITail: "EVIDoa2100070",
	}

	pdfText := "This is the IMbrave150 study by Qin S et al. Published in Lancet " +
		"in 2025. Treatment: Atezolizumab + Bevacizumab. DOI: 10.1056/EVIDoa2100070"

	result := kf.Match(pdfText)

	if result.Score != 1.0 {
		t.Errorf("Score = %f, want 1.0 (matched: %v, missing: %v)",
			result.Score, result.MatchedFields, result.MissingFields)
	}
	if result.Reason != "perfect match" {
		t.Errorf("Reason = %q, want 'perfect match'", result.Reason)
	}
}

// TestKeyFieldsMatch_PartialMatch verifies partial match scoring.
func TestKeyFieldsMatch_PartialMatch(t *testing.T) {
	kf := KeyFields{
		Authors: []string{"Abou-Alfa"},
		Journal: "NEJMEvid",
		Year:    "2022",
		Trial:   "HIMALAYA",
	}

	// PDF text only has 2 out of 4 fields
	pdfText := "By Abou-Alfa et al. Published in 2022. doi:10.1056/EVID..."

	result := kf.Match(pdfText)

	if result.Score < 0.4 || result.Score > 0.6 {
		t.Errorf("Score = %f, want ~0.5 (matched: %v, missing: %v)",
			result.Score, result.MatchedFields, result.MissingFields)
	}
	if !strings.Contains(result.Reason, "match") {
		t.Errorf("Reason = %q, want 'partial match'", result.Reason)
	}
}

// TestKeyFieldsMatch_NoMatch verifies complete mismatch scoring.
func TestKeyFieldsMatch_NoMatch(t *testing.T) {
	kf := KeyFields{
		Authors: []string{"Qin"},
		Journal: "Lancet",
		Year:    "2025",
	}

	pdfText := "This is about unrelated topic. No citations match."

	result := kf.Match(pdfText)

	if result.Score != 0.0 {
		t.Errorf("Score = %f, want 0.0", result.Score)
	}
	if result.Reason != "no match" {
		t.Errorf("Reason = %q, want 'no match'", result.Reason)
	}
}

// TestNormalizeForMatching verifies the normalization function.
func TestNormalizeForMatching(t *testing.T) {
	tests := []struct {
		input string
		want  string
	}{
		{"Hello World", "hello world"},
		{"  Multiple   Spaces  ", "multiple spaces"},
		{"Tab\tSeparated", "tab separated"},
		{"Newline\nTest", "newline test"},
		{"Mixed   Whitespace", "mixed whitespace"},
	}

	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			got := normalizeForMatching(tt.input)
			if got != tt.want {
				t.Errorf("normalizeForMatching(%q) = %q, want %q", tt.input, got, tt.want)
			}
		})
	}
}

// TestCitationString verifies the String() method.
func TestCitationString(t *testing.T) {
	c := Citation{
		SlidePage: "3",
		CiteIndex: "1",
		Reference: "Qin S, et al. Lancet Oncol. 2025.",
		DOI:       "10.1056/test",
		PDFFile:   "P3-1/P3-1_main.pdf",
	}

	s := c.String()
	if !strings.Contains(s, "3-1") {
		t.Errorf("String should contain slide reference, got: %s", s)
	}
	if !strings.Contains(s, "Qin") {
		t.Errorf("String should contain reference author, got: %s", s)
	}
}