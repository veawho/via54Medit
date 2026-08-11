// replayer.go — converts correction entries into regression tests.
//
// This is the core of the experience loop. Every user correction becomes
// a permanent test case in via54Medit.
package corrections

import (
	"fmt"
	"strings"
)

// TestCase represents a single regression test generated from a correction.
type TestCase struct {
	// FunctionName is the Go test function name (e.g. "TestKeywordMatch_AbouAlfa_v2").
	FunctionName string
	// SourceCorrection is the ID of the correction this test came from.
	SourceCorrection string
	// Description is a human-readable description.
	Description string
	// GoTestBody is the generated Go test code.
	GoTestBody string
}

// GenerateTestCase creates a Go test function from a CorrectionEntry.
//
// Algorithm:
//  1. If Type = author → generate test for ExtractKeyFields (author detection)
//  2. If Type = journal → generate test for journal pattern
//  3. If Type = doi → generate test for DOI tail extraction
//  4. If Type = file_mapping → generate test for Pn-x resolver
//  5. Else → general test
func GenerateTestCase(c CorrectionEntry) TestCase {
	switch c.Type {
	case TypeAuthorCorrection:
		return generateAuthorTest(c)
	case TypeJournalCorrection:
		return generateJournalTest(c)
	case TypeDOICorrection:
		return generateDOITest(c)
	case TypeFileMapping:
		return generateFileMappingTest(c)
	case TypeRichTextConversion:
		return generateRichTextTest(c)
	default:
		return generateGeneralTest(c)
	}
}

func generateAuthorTest(c CorrectionEntry) TestCase {
	fn := fmt.Sprintf("TestKeywordMatch_Author_%s", sanitizeFn(c.ID))
	body := fmt.Sprintf(`func %s(t *testing.T) {
	// Correction: %s
	// Context: %s
	// Before: %s
	// After: %s
	citation := Citation{Reference: %q, DOI: %q}
	kf := citation.ExtractKeyFields()
	// Verify the author is now correctly detected
	if len(kf.Authors) == 0 {
		t.Fatal("expected author to be detected")
	}
}`,
		fn, c.ID, c.Context, c.Before, c.After,
		c.After, c.DOIAfter)
	return TestCase{
		FunctionName:     fn,
		SourceCorrection: c.ID,
		Description:      c.Context,
		GoTestBody:       body,
	}
}

func generateJournalTest(c CorrectionEntry) TestCase {
	fn := fmt.Sprintf("TestJournalPattern_%s", sanitizeFn(c.ID))
	body := fmt.Sprintf(`func %s(t *testing.T) {
	// Correction: %s
	// Context: %s
	citation := Citation{Reference: %q}
	kf := citation.ExtractKeyFields()
	if kf.Journal == "" {
		t.Fatal("expected journal to be detected")
	}
}`, fn, c.ID, c.Context, c.After)
	return TestCase{
		FunctionName:     fn,
		SourceCorrection: c.ID,
		Description:      c.Context,
		GoTestBody:       body,
	}
}

func generateDOITest(c CorrectionEntry) TestCase {
	fn := fmt.Sprintf("TestDOIExtraction_%s", sanitizeFn(c.ID))
	body := fmt.Sprintf(`func %s(t *testing.T) {
	// Correction: %s
	// Context: %s
	doi := %q
	expected := %q
	got := extractDOITail(doi)
	if got != expected {
		t.Errorf("DOI tail mismatch")
	}
}`, fn, c.ID, c.Context, c.DOIBefore, c.DOIAfter)
	return TestCase{
		FunctionName:     fn,
		SourceCorrection: c.ID,
		Description:      c.Context,
		GoTestBody:       body,
	}
}

func generateFileMappingTest(c CorrectionEntry) TestCase {
	fn := fmt.Sprintf("TestFileMapping_%s", sanitizeFn(c.ID))
	body := fmt.Sprintf(`func %s(t *testing.T) {
	// Correction: %s
	// Context: %s
	// Before: %s
	// After: %s
	// Test verifies that the Pn-x resolver returns the correct file
	// for row %d (slide %s).
	t.Skip("manual implementation required - see comment")
	// TODO: Generate actual Pn-x resolver test based on row %d
	//       and the corrected file path
}`, fn, c.ID, c.Context, c.Before, c.After, c.RowIndex, c.SlidePage, c.RowIndex)
	return TestCase{
		FunctionName:     fn,
		SourceCorrection: c.ID,
		Description:      c.Context,
		GoTestBody:       body,
	}
}

func generateRichTextTest(c CorrectionEntry) TestCase {
	fn := fmt.Sprintf("TestRichText_%s", sanitizeFn(c.ID))
	body := fmt.Sprintf(`func %s(t *testing.T) {
	// Correction: %s
	// Context: %s
	content := %q
	got := BuildRichCell(content)
	rt, ok := got["rich_text"].([]map[string]interface{})
	if !ok {
		t.Fatalf("expected rich_text array, got %%v", got)
	}
	if len(rt) == 0 {
		t.Fatal("expected non-empty rich_text array")
	}
}`, fn, c.ID, c.Context, c.After)
	return TestCase{
		FunctionName:     fn,
		SourceCorrection: c.ID,
		Description:      c.Context,
		GoTestBody:       body,
	}
}

func generateGeneralTest(c CorrectionEntry) TestCase {
	fn := fmt.Sprintf("TestRegression_%s", sanitizeFn(c.ID))
	body := fmt.Sprintf(`func %s(t *testing.T) {
	// Correction: %s
	// Context: %s
	// Before: %s
	// After: %s
	t.Skip("TODO: implement specific regression test")
}`, fn, c.ID, c.Context, c.Before, c.After)
	return TestCase{
		FunctionName:     fn,
		SourceCorrection: c.ID,
		Description:      c.Context,
		GoTestBody:       body,
	}
}

// sanitizeFn converts a correction ID to a valid Go function name.
func sanitizeFn(id string) string {
	// Replace non-alphanumeric chars with underscore
	b := strings.Builder{}
	for _, r := range id {
		if (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9') {
			b.WriteRune(r)
		} else {
			b.WriteRune('_')
		}
	}
	return b.String()
}

// GenerateAll replays all pending corrections and returns test cases.
func (l *Log) GenerateAll() []TestCase {
	var cases []TestCase
	for _, c := range l.Corrections {
		if c.Status != "pending" {
			continue
		}
		cases = append(cases, GenerateTestCase(c))
	}
	return cases
}

// GenerateGoTestFile concatenates all test cases into a single _test.go file.
func (l *Log) GenerateGoTestFile(packageName string) string {
	var b strings.Builder
	b.WriteString("// Code generated by corrections/replayer. DO NOT EDIT.\n")
	b.WriteString("//\n")
	b.WriteString("// This file contains regression tests generated from user corrections.\n")
	b.WriteString("// To regenerate: medit citation replayer --generate\n\n")
	b.WriteString("package ")
	b.WriteString(packageName)
	b.WriteString("\n\n")
	b.WriteString("import \"testing\"\n\n")
	cases := l.GenerateAll()
	for _, tc := range cases {
		b.WriteString("// ")
		b.WriteString(tc.Description)
		b.WriteString("\n")
		b.WriteString(tc.GoTestBody)
		b.WriteString("\n\n")
	}
	return b.String()
}