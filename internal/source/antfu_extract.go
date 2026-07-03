// Antfu (蚂蚁阿福) HTML extraction.
//
// Given the rendered HTML of an antfu chat page, this file extracts:
//  1. The assistant's answer text
//  2. The list of cited references (with title + URL + snippet)
//
// The real antfu DOM is observed empirically — Phase 1.5 ships with
// conservative selectors that match common patterns, plus a config
// struct so users can override them for their own antfu build/version.
//
// Reference: the original antfu-evidence-search used a similar goquery
// pipeline (extract_antfu_refs.py in v1.11.0). This file is a Go port
// of that logic, simplified for our use case.
package source

import (
	"io"
	"regexp"
	"strconv"
	"strings"

	"github.com/PuerkitoBio/goquery"
)

// ExtractConfig holds the CSS selectors used to find the answer and
// reference blocks. Defaults are conservative and match common patterns
// across antfu versions.
type ExtractConfig struct {
	// AnswerSelector: where the assistant's reply text lives.
	// Comma-separated list (matches first found).
	AnswerSelector string

	// QuoteContainerSelector: where the references panel lives.
	QuoteContainerSelector string

	// QuoteItemSelector: each individual reference card inside the panel.
	QuoteItemSelector string

	// TitleSelector: title element inside a quote item.
	TitleSelector string

	// URLAttr: which attribute holds the link URL (usually "href").
	URLAttr string

	// SnippetSelector: optional snippet/excerpt text inside a quote item.
	SnippetSelector string
}

// DefaultExtractConfig returns the conservative defaults.
func DefaultExtractConfig() ExtractConfig {
	return ExtractConfig{
		AnswerSelector:         ".markdown-body, .answer-content, [class*=answer-body], [class*=markdown]",
		QuoteContainerSelector: ".quotedMaterials, .reference-list, [class*=quotedMaterialsBox], [class*=quotedMaterials]",
		QuoteItemSelector:      ".reference-item, .ref-item, [class*=ReferenceItem], li[class*=reference], [class*=quotedMaterialsItem]",
		TitleSelector:          "a, .title, h3, h4, [class*=quotedMaterialsItemTitle]",
		URLAttr:                "href",
		SnippetSelector:        ".snippet, p, .abstract, [class*=snippet], [class*=quotedMaterialsJournalText]",
	}
}

// ExtractedResult is the output of Extract().
type ExtractedResult struct {
	// Answer is the assistant's reply text (joined paragraphs, trimmed).
	Answer string

	// References is the list of cited papers/articles. Each has at least
	// a title; URL and snippet are best-effort (may be empty if missing).
	References []AntfuRef
}

// AntfuRef is a single cited reference from an antfu page.
type AntfuRef struct {
	Title   string
	URL     string
	Snippet string
	// Year, extracted from snippet or title when present.
	Year int
}

// Extract parses the given HTML and returns the answer + references.
// Pure function — no I/O, no network — so tests can run on synthetic HTML.
func Extract(html io.Reader, cfg ExtractConfig) (ExtractedResult, error) {
	if cfg.AnswerSelector == "" {
		cfg = DefaultExtractConfig()
	}
	doc, err := goquery.NewDocumentFromReader(html)
	if err != nil {
		return ExtractedResult{}, err
	}

	result := ExtractedResult{
		Answer:     extractAnswer(doc, cfg.AnswerSelector),
		References: extractReferences(doc, cfg),
	}
	return result, nil
}

// extractAnswer returns the joined text of the first matching element.
// If multiple selectors are given (comma-separated), the first selector
// that matches wins; subsequent selectors are NOT tried (consistent with
// goquery's First behavior).
func extractAnswer(doc *goquery.Document, selector string) string {
	selectors := splitSelectors(selector)
	for _, sel := range selectors {
		sel = strings.TrimSpace(sel)
		if sel == "" {
			continue
		}
		// Find all matching elements and join their text.
		var parts []string
		doc.Find(sel).Each(func(_ int, s *goquery.Selection) {
			text := strings.TrimSpace(s.Text())
			if text != "" {
				parts = append(parts, text)
			}
		})
		if len(parts) > 0 {
			return strings.Join(parts, "\n\n")
		}
	}
	return ""
}

func extractReferences(doc *goquery.Document, cfg ExtractConfig) []AntfuRef {
	containerSelectors := splitSelectors(cfg.QuoteContainerSelector)
	for _, sel := range containerSelectors {
		sel = strings.TrimSpace(sel)
		if sel == "" {
			continue
		}
		container := doc.Find(sel).First()
		if container.Length() == 0 {
			continue
		}
		itemSelectors := splitSelectors(cfg.QuoteItemSelector)
		var refs []AntfuRef
		for _, itemSel := range itemSelectors {
			itemSel = strings.TrimSpace(itemSel)
			if itemSel == "" {
				continue
			}
			container.Find(itemSel).Each(func(_ int, s *goquery.Selection) {
				ref := AntfuRef{
					Title:   extractFirstText(s, cfg.TitleSelector),
					URL:     extractFirstAttr(s, cfg.TitleSelector, cfg.URLAttr),
					Snippet: extractFirstText(s, cfg.SnippetSelector),
					Year:    extractYear(s.Text()),
				}
				if ref.Title != "" || ref.URL != "" {
					refs = append(refs, ref)
				}
			})
			if len(refs) > 0 {
				return refs
			}
		}
	}
	return nil
}

func extractFirstText(s *goquery.Selection, selector string) string {
	selectors := splitSelectors(selector)
	for _, sel := range selectors {
		sel = strings.TrimSpace(sel)
		if sel == "" {
			continue
		}
		first := s.Find(sel).First()
		if first.Length() > 0 {
			return strings.TrimSpace(first.Text())
		}
	}
	return ""
}

func extractFirstAttr(s *goquery.Selection, selector, attr string) string {
	selectors := splitSelectors(selector)
	for _, sel := range selectors {
		sel = strings.TrimSpace(sel)
		if sel == "" {
			continue
		}
		first := s.Find(sel).First()
		if first.Length() > 0 {
			if v, ok := first.Attr(attr); ok {
				return strings.TrimSpace(v)
			}
		}
	}
	return ""
}

// splitSelectors splits a comma-separated selector list, respecting
// simple cases (no nested commas inside attribute brackets).
func splitSelectors(s string) []string {
	if s == "" {
		return nil
	}
	parts := strings.Split(s, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		out = append(out, strings.TrimSpace(p))
	}
	return out
}

var yearRe = regexp.MustCompile(`\b(19|20)\d{2}\b`)

// extractYear finds the first plausible 4-digit year (1900-2099) in text.
// Returns 0 if none found.
func extractYear(s string) int {
	m := yearRe.FindString(s)
	if m == "" {
		return 0
	}
	y, err := strconv.Atoi(m)
	if err != nil {
		return 0
	}
	return y
}
