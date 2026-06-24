package foundation

import (
	"bytes"
	"context"
	"encoding/json"
	"strings"
	"sync"
	"testing"
)

// safeBuffer is a concurrency-safe bytes.Buffer for capturing parallel
// log output in tests.
type safeBuffer struct {
	mu  sync.Mutex
	buf bytes.Buffer
}

func (b *safeBuffer) Write(p []byte) (int, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.buf.Write(p)
}

func (b *safeBuffer) String() string {
	b.mu.Lock()
	defer b.mu.Unlock()
	return b.buf.String()
}

// TestParseLevel pins the level string → slog.Level mapping. Touching
// this requires also updating the package doc.
func TestParseLevel(t *testing.T) {
	cases := []struct {
		in   string
		want string
	}{
		{"debug", "DEBUG"},
		{"DEBUG", "DEBUG"},
		{"info", "INFO"},
		{"", "INFO"},
		{"garbage", "INFO"},
		{"warn", "WARN"},
		{"warning", "WARN"},
		{"error", "ERROR"},
	}
	for _, c := range cases {
		got := parseLevel(c.in).String()
		if got != c.want {
			t.Errorf("parseLevel(%q) = %s, want %s", c.in, got, c.want)
		}
	}
}

// TestNewWithJSONOutput confirms the JSON handler emits a parseable
// line with the expected fields. Locks the wire format that downstream
// log shippers (Loki / Datadog) parse.
func TestNewWithJSONOutput(t *testing.T) {
	buf := &safeBuffer{}
	lg := NewLoggerWith(buf, "info")
	lg.Info("hello", "conv_id", "abc-123", "n", 42)

	var got map[string]any
	if err := json.Unmarshal([]byte(strings.TrimSpace(buf.String())), &got); err != nil {
		t.Fatalf("JSON parse: %v\noutput: %s", err, buf.String())
	}
	if got["msg"] != "hello" {
		t.Errorf("msg = %v, want \"hello\"", got["msg"])
	}
	if got["conv_id"] != "abc-123" {
		t.Errorf("conv_id = %v, want \"abc-123\"", got["conv_id"])
	}
	if got["level"] != "INFO" {
		t.Errorf("level = %v, want \"INFO\"", got["level"])
	}
	if _, ok := got["time"]; !ok {
		t.Error("time field missing (audit log requires it)")
	}
}

// TestWithPrependsFields ensures With() copies fields to every subsequent line.
func TestWithPrependsFields(t *testing.T) {
	buf := &safeBuffer{}
	lg := NewLoggerWith(buf, "info").With("source", "pubmed")
	lg.Info("first")
	lg.Info("second", "extra", "x")

	lines := strings.Split(strings.TrimSpace(buf.String()), "\n")
	if len(lines) != 2 {
		t.Fatalf("expected 2 lines, got %d: %s", len(lines), buf.String())
	}
	for i, line := range lines {
		var got map[string]any
		if err := json.Unmarshal([]byte(line), &got); err != nil {
			t.Fatalf("line %d parse: %v", i, err)
		}
		if got["source"] != "pubmed" {
			t.Errorf("line %d: source = %v, want pubmed (With field missing)", i, got["source"])
		}
	}
}

// TestNoopDiscards guards against accidental stdout writes in library mode.
func TestNoopDiscards(t *testing.T) {
	lg := NoopLogger()
	// All four levels must compile + return without panic.
	lg.Debug("d", "k", "v")
	lg.Info("i", "k", "v")
	lg.Warn("w", "k", "v")
	lg.Error("e", "k", "v")
	// Noop.With must return another Noop (not nil — that would NPE callers).
	if lg.With("a", 1) == nil {
		t.Error("NoopLogger().With(...) must not return nil")
	}
}

// TestConvIDContext verifies the context plumbing used by router
// to tag every log line from a single ask() call.
func TestConvIDContext(t *testing.T) {
	ctx := WithConvID(context.Background(), "ask-42")
	if got := ConvIDFrom(ctx); got != "ask-42" {
		t.Errorf("ConvIDFrom = %q, want ask-42", got)
	}
	// Empty context yields "" (not nil-panic).
	if got := ConvIDFrom(context.Background()); got != "" {
		t.Errorf("ConvIDFrom(empty) = %q, want \"\"", got)
	}
}

// TestSetDefaultRoundTrip makes sure SetDefault returns the old default
// and that Default() reflects the swap.
func TestSetDefaultRoundTrip(t *testing.T) {
	old := DefaultLogger()
	defer SetDefaultLogger(old) // restore for other tests

	new1 := NoopLogger()
	returned := SetDefaultLogger(new1)
	if returned != old {
		t.Errorf("SetDefault returned %v, want original default %v", returned, old)
	}
	if DefaultLogger() != new1 {
		t.Error("Default() did not reflect SetDefault() change")
	}
}
