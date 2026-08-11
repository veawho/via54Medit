package docproc

import (
	"context"
	"encoding/json"
	"fmt"
	"github.com/veawho/via54Medit/internal/foundation"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// ---------------------------------------------------------------------------
// mockLLMProvider — test-only LLM provider returning pre-set JSON
// ---------------------------------------------------------------------------

type mockLLMProvider struct {
	name        string
	entities    string
	soap        string
	completeErr error
}

func (m *mockLLMProvider) Name() string {
	return m.name
}

func (m *mockLLMProvider) Complete(context.Context, string, string) (string, error) {
	if m.completeErr != nil {
		return "", m.completeErr
	}
	// Default to entities response
	return m.entities, nil
}

func (m *mockLLMProvider) CompleteWithOptions(context.Context, foundation.CompleteOptions) (string, error) {
	// Dispatch: entity extraction mentions "Extract entities" / "SOAP" dispatch
	if m.completeErr != nil {
		return "", m.completeErr
	}
	// We use separate providers per stage to control responses precisely.
	// Default to entities response.
	return m.entities, nil
}

type mockEntityProvider struct {
	response string
	err      error
}

func (m *mockEntityProvider) Name() string {
	return "mock-entity"
}
func (m *mockEntityProvider) Complete(context.Context, string, string) (string, error) {
	return m.response, m.err
}
func (m *mockEntityProvider) CompleteWithOptions(context.Context, foundation.CompleteOptions) (string, error) {
	return m.response, m.err
}

type mockSoapProvider struct {
	response string
	err      error
}

func (m *mockSoapProvider) Name() string {
	return "mock-soap"
}
func (m *mockSoapProvider) Complete(context.Context, string, string) (string, error) {
	return m.response, m.err
}
func (m *mockSoapProvider) CompleteWithOptions(context.Context, foundation.CompleteOptions) (string, error) {
	return m.response, m.err
}

// ---------------------------------------------------------------------------
// mock completeOptions (shallow copy of foundation.CompleteOptions)
// ---------------------------------------------------------------------------

type _unusedCompleteOptions struct {
	System      string
	User        string
	Model       string
	MaxTokens   int
	Temperature float64
}

// ---------------------------------------------------------------------------
// response helpers
// ---------------------------------------------------------------------------

func entityOnlyResponse() string {
	return `{
		"symptoms": [],
		"medications": [
			{"name": "Metformin", "dosage": "500mg", "frequency": "twice daily", "route": "oral", "context": "existing"}
		],
		"lab_values": [
			{"type": "blood_pressure", "value": "145/92", "unit": "mmHg", "timestamp": "this morning", "normal_range": "120/80", "abnormal": true}
		],
		"diagnoses": [
			{"name": "type 2 diabetes mellitus", "context": "confirmed"},
			{"name": "hypertension", "context": "confirmed"}
		],
		"vital_signs": [],
		"procedures": [],
		"action_items": [
			{"type": "medication_review", "details": "review dizziness", "urgency": "medium", "reason": "possible side effect"}
		],
		"contradictions": [],
		"missing_info": ["no recent HbA1c provided"],
		"phi_flags": []
	}`
}

func soapResponse() string {
	return `{
		"subjective": "Patient reports dizziness since starting new medication three days ago.",
		"objective": "Blood pressure 145/92 mmHg this morning.",
		"assessment": "Possible medication side effect from Lisinopril. Hypertension not fully controlled.",
		"plan": "Review dizziness at next visit. Consider BP medication adjustment if persistent.",
		"alerts": ["Elevated BP reading"],
		"missing_info": ["No recent HbA1c provided"],
		"confidence": 0.9
	}`
}

func soapErrorResponse() string {
	return "not valid json at all"
}

// ---------------------------------------------------------------------------
// TextExtractor tests
// ---------------------------------------------------------------------------

func TestTextExtractor_Text(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "test.txt")
	os.WriteFile(path, []byte("Hello world\nThis is a test"), 0o644)

	ext := NewTextExtractor()
	text, err := ext.Extract(context.Background(), path)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if !strings.Contains(text, "Hello world") {
		t.Fatalf("expected text to contain 'Hello world', got %q", text)
	}
}

func TestTextExtractor_MaxChars(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "long.txt")
	os.WriteFile(path, []byte(strings.Repeat("x", 1000)), 0o644)

	ext := NewTextExtractor()
	ext.MaxChars = 100
	text, err := ext.Extract(context.Background(), path)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if len(text) != 100 {
		t.Fatalf("expected 100 chars, got %d", len(text))
	}
}

func TestTextExtractor_HTML(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "test.html")
	html := `<html><body><p>Clinical note: patient has diabetes</p><p>BP 145/92</p><script>alert('xss')</script></body></html>`
	os.WriteFile(path, []byte(html), 0o644)

	ext := NewTextExtractor()
	text, err := ext.Extract(context.Background(), path)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if !strings.Contains(text, "diabetes") {
		t.Fatalf("expected text to contain 'diabetes', got %q", text)
	}
	if strings.Contains(text, "alert") {
		t.Fatalf("expected scripts to be stripped, got %q", text)
	}
}

func TestTextExtractor_PDF_NotAvailable(t *testing.T) {
	ext := NewTextExtractor()
	_, err := ext.Extract(context.Background(), "nonexistent.pdf")
	if err == nil {
		t.Fatalf("expected error for missing PDF")
	}
}

// ---------------------------------------------------------------------------
// EntityExtractor tests
// ---------------------------------------------------------------------------

func TestEntityExtractor_ExtractsEntities(t *testing.T) {
	provider := &mockEntityProvider{response: entityOnlyResponse()}

	ext := NewEntityExtractor(provider)
	text := "Patient reports dizziness since starting Lisinopril 10mg three days ago. BP this morning 145/92."

	entities, err := ext.Extract(context.Background(), text)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if entities == nil {
		t.Fatalf("expected non-null entities")
	}
	if len(entities.Medications) != 1 {
		t.Fatalf("expected 1 medication, got %d", len(entities.Medications))
	}
	if entities.Medications[0].Name != "Metformin" {
		t.Fatalf("expected medication 'Metformin', got %q", entities.Medications[0].Name)
	}
	if len(entities.Diagnoses) != 2 {
		t.Fatalf("expected 2 diagnoses, got %d", len(entities.Diagnoses))
	}
	if len(entities.MissingInfo) != 1 {
		t.Fatalf("expected 1 missing info, got %d", len(entities.MissingInfo))
	}
	if len(entities.LabValues) != 1 {
		t.Fatalf("expected 1 lab value, got %d", len(entities.LabValues))
	}
}

func TestEntityExtractor_EmptyInput(t *testing.T) {
	provider := &mockEntityProvider{}
	ext := NewEntityExtractor(provider)
	entities, err := ext.Extract(context.Background(), "")
	if err != nil {
		t.Fatalf("expected no error for empty input, got %v", err)
	}
	if entities == nil {
		t.Fatalf("expected non-null entities for empty input")
	}
}

func TestEntityExtractor_LLMErrors(t *testing.T) {
	provider := &mockEntityProvider{err: fmt.Errorf("LLM timeout")}
	ext := NewEntityExtractor(provider)
	_, err := ext.Extract(context.Background(), "patient text")
	if err == nil {
		t.Fatalf("expected error for LLM failure")
	}
}

func TestEntityExtractor_RecoverJSON(t *testing.T) {
	provider := &mockEntityProvider{}
	ext := NewEntityExtractor(provider)

	// Test recoverJSON with trailing garbage
	raw := `{"diagnoses":[{"name":"test"}]} some extra text`
	result := ext.recoverJSON(raw)
	if !strings.HasPrefix(result, `{"diagnoses"`) {
		t.Fatalf("expected valid JSON prefix, got %q", result)
	}
}

// ---------------------------------------------------------------------------
// SoapSummarizer tests
// ---------------------------------------------------------------------------

func TestSoapSummarizer_Summarizes(t *testing.T) {
	provider := &mockSoapProvider{response: soapResponse()}

	sum := NewSoapSummarizer(provider)
	text := "Patient reports dizziness. BP 145/92 this morning."

	soap, err := sum.Summarize(context.Background(), text)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if soap == nil {
		t.Fatalf("expected non-null SOAP summary")
	}
	if !strings.Contains(soap.Subjective, "dizziness") {
		t.Fatalf("expected subjective to contain 'dizziness', got %q", soap.Subjective)
	}
	if soap.Confidence != 0.9 {
		t.Fatalf("expected confidence 0.9, got %.2f", soap.Confidence)
	}
}

func TestSoapSummarizer_EmptyInput(t *testing.T) {
	provider := &mockSoapProvider{}
	sum := NewSoapSummarizer(provider)
	_, err := sum.Summarize(context.Background(), "")
	if err == nil {
		t.Fatalf("expected error for empty input")
	}
}

func TestSoapSummarizer_LLMErrors(t *testing.T) {
	provider := &mockSoapProvider{err: fmt.Errorf("LLM timeout")}
	sum := NewSoapSummarizer(provider)
	_, err := sum.Summarize(context.Background(), "patient text")
	if err == nil {
		t.Fatalf("expected error for LLM failure")
	}
}

func TestSoapSummarizer_InvalidJSON(t *testing.T) {
	provider := &mockSoapProvider{response: soapErrorResponse()}
	sum := NewSoapSummarizer(provider)
	_, err := sum.Summarize(context.Background(), "patient text")
	if err == nil {
		t.Fatalf("expected error for invalid JSON")
	}
}

// ---------------------------------------------------------------------------
// Pipeline tests
// ---------------------------------------------------------------------------

func TestPipeline_Process(t *testing.T) {
	entityProvider := &mockEntityProvider{response: entityOnlyResponse()}

	pipeline := NewPipelineWithEntityOnly(entityProvider)

	dir := t.TempDir()
	path := filepath.Join(dir, "clinical.txt")
	os.WriteFile(path, []byte("Patient reports dizziness since starting Lisinopril. BP 145/92."), 0o644)

	result, err := pipeline.Process(context.Background(), path)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if result == nil {
		t.Fatalf("expected non-null result")
	}
	if result.RawText == "" {
		t.Fatalf("expected non-empty raw text")
	}
	if result.Entities == nil {
		t.Fatalf("expected non-null entities")
	}
	if len(result.Errors) != 0 {
		t.Fatalf("expected no errors, got %v", result.Errors)
	}
}

func TestPipeline_EntityErrorIsNonFatal(t *testing.T) {
	// Entity extraction fails but pipeline still returns result
	entityProvider := &mockEntityProvider{err: fmt.Errorf("LLM failure")}

	pipeline := NewPipelineWithEntityOnly(entityProvider)

	dir := t.TempDir()
	path := filepath.Join(dir, "clinical.txt")
	os.WriteFile(path, []byte("Patient reports dizziness."), 0o644)

	result, err := pipeline.Process(context.Background(), path)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if result == nil {
		t.Fatalf("expected non-null result even with entity error")
	}
	if len(result.Errors) != 1 {
		t.Fatalf("expected 1 error, got %d", len(result.Errors))
	}
	if result.RawText == "" {
		t.Fatalf("expected raw text even with entity error")
	}
}

func TestPipeline_FileNotFound(t *testing.T) {
	provider := &mockEntityProvider{}
	pipeline := NewPipelineWithEntityOnly(provider)

	_, err := pipeline.Process(context.Background(), "/tmp/does-not-exist.txt")
	if err == nil {
		t.Fatalf("expected error for missing file")
	}
}

// ---------------------------------------------------------------------------
// FHIR output tests
// ---------------------------------------------------------------------------

func TestExtractedEntities_FHIRCompatible(t *testing.T) {
	entities := &ExtractedEntities{
		Diagnoses: []Diagnosis{
			{Name: "type 2 diabetes mellitus", Context: "confirmed"},
		},
		Medications: []Medication{
			{Name: "Metformin", Dosage: "500mg", Frequency: "twice daily"},
		},
	}

	data, err := json.Marshal(entities)
	if err != nil {
		t.Fatalf("expected valid JSON, got %v", err)
	}

	var m map[string]any
	if err := json.Unmarshal(data, &m); err != nil {
		t.Fatalf("expected valid JSON, got %v", err)
	}

	if _, ok := m["diagnoses"]; !ok {
		t.Fatalf("expected 'diagnoses' field for FHIR compatibility")
	}
	if _, ok := m["medications"]; !ok {
		t.Fatalf("expected 'medications' field for FHIR compatibility")
	}
}

// ---------------------------------------------------------------------------
// Duration tracking
// ---------------------------------------------------------------------------

func TestPipeline_DurationTracking(t *testing.T) {
	provider := &mockEntityProvider{response: entityOnlyResponse()}
	pipeline := NewPipelineWithEntityOnly(provider)

	dir := t.TempDir()
	path := filepath.Join(dir, "clinical.txt")
	os.WriteFile(path, []byte("Patient reports dizziness."), 0o644)

	result, err := pipeline.Process(context.Background(), path)
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if result.Duration <= 0 {
		t.Fatalf("expected positive duration")
	}
	if result.Duration > time.Second {
		t.Fatalf("expected duration under 1 second, got %v", result.Duration)
	}
}
