package source

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/veawho/via54Medit/pkg/types"
)

func TestAntfuSourceDefaults(t *testing.T) {
	s, err := NewAntfuSource(nil)
	if err != nil {
		t.Fatal(err)
	}
	if s.Name() != "antfu" {
		t.Errorf("Name = %q, want antfu", s.Name())
	}
	if !s.Enabled() {
		t.Error("default enabled should be true")
	}
	if s.cdpURL != "http://localhost:9223" {
		t.Errorf("default cdp_url = %q", s.cdpURL)
	}
}

func TestAntfuSourceCustomConfig(t *testing.T) {
	s, _ := NewAntfuSource(map[string]any{
		"cdp_url":     "http://my-chrome:9999",
		"deep_search": false,
		"timeout":     "30s",
	})
	if s.cdpURL != "http://my-chrome:9999" {
		t.Errorf("cdp_url = %q, want custom", s.cdpURL)
	}
	if s.deepSearch {
		t.Error("deep_search should be false")
	}
	if s.timeout != 30*time.Second {
		t.Errorf("timeout = %v, want 30s", s.timeout)
	}
}

func TestAntfuSourceDisabled(t *testing.T) {
	s, _ := NewAntfuSource(map[string]any{"enabled": false})
	if s.Enabled() {
		t.Error("enabled=false should yield Enabled()=false")
	}
}

func TestAntfuSourceSearchReturnsNotImplemented(t *testing.T) {
	// Phase 1.5: this test should change to a real assertion.
	// For now, it pins the Phase 1 contract: error must be clear + actionable.
	s, _ := NewAntfuSource(map[string]any{})
	_, err := s.Search(context.Background(), types.EBMQuestion{Query: "SGLT2"}, 10)
	if err == nil {
		t.Fatal("Phase 1 antfu Search should return error (not yet implemented)")
	}
	if !strings.Contains(err.Error(), "Phase 1.5") {
		t.Errorf("error should mention Phase 1.5, got: %v", err)
	}
	if !strings.Contains(err.Error(), "Chrome") {
		t.Errorf("error should mention Chrome 9223, got: %v", err)
	}
}

func TestAntfuSourceHealthReturnsNotImplemented(t *testing.T) {
	s, _ := NewAntfuSource(map[string]any{})
	err := s.Health(context.Background())
	if err == nil {
		t.Fatal("Phase 1 antfu Health should return error")
	}
	if !strings.Contains(err.Error(), "localhost:9223") {
		t.Errorf("error should include cdp_url, got: %v", err)
	}
}

func TestAntfuSourceSearchWhenDisabled(t *testing.T) {
	s, _ := NewAntfuSource(map[string]any{"enabled": false})
	_, err := s.Search(context.Background(), types.EBMQuestion{}, 10)
	if err == nil {
		t.Fatal("Search on disabled source should fail")
	}
	if !strings.Contains(err.Error(), "disabled") {
		t.Errorf("error should say disabled, got: %v", err)
	}
}
