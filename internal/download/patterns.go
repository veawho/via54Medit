// Package download provides tiered full-text acquisition.
//
// patterns.go — DOI and URL pattern detection for non-standard content types.
package download

import "regexp"

// DOI patterns that indicate non-standard content types:
//   - chart/figures: peerj figures, elife figures
//   - author responses: RSC journals, Springer
//   - supplementary data: elife supplements
var (
	// chartFigPattern matches DOIs pointing to figures, tables, or charts
	chartFigPattern = regexp.MustCompile(`(?i)(/fig-\d+|/table-\d+|/suppl|/figure\b|\.fig-\d+)`)
	// responsePattern matches DOIs pointing to author responses/replies
	responsePattern = regexp.MustCompile(`(?i)(/response\d*$|/v\d+/response\d*$|-c\d+$|\.reply|/v\d+/response1$)`)
	// suppDataPattern matches supplementary content DOIs (e.g. eLife .026 suffix, /suppl)
	suppDataPattern = regexp.MustCompile(`(?i)(/supplementary|/suppl_material|\.\d{3,4}$|/suppl/)`)
)

// ContentType describes the type of content a DOI/URL points to.
type ContentType int

const (
	ContentResearchPaper ContentType = iota // Standard research article
	ContentChartFigure                      // Figure, table, chart (e.g. PeerJ fig)
	ContentAuthorReply                      // Author reply / commentary
	ContentRetraction                       // Retraction notice
	ContentSupplementary                    // Supplementary data
	ContentUnknown                          // Unknown / mixed
)

// ClassifyDOI returns the content type based on DOI pattern analysis.
func ClassifyDOI(doi string) ContentType {
	if doi == "" {
		return ContentUnknown
	}
	switch {
	case chartFigPattern.MatchString(doi):
		return ContentChartFigure
	case responsePattern.MatchString(doi):
		return ContentAuthorReply
	case suppDataPattern.MatchString(doi):
		return ContentSupplementary
	default:
		return ContentResearchPaper
	}
}

// IsDownloadableContent returns true if the content type should trigger a download attempt.
// All content types are downloadable — some may just produce smaller files.
func IsDownloadableContent(ct ContentType) bool {
	return true
}

// ContentTypeLabel returns a human-readable label for a content type.
func ContentTypeLabel(ct ContentType) string {
	switch ct {
	case ContentResearchPaper:
		return "research-paper"
	case ContentChartFigure:
		return "chart-figure"
	case ContentAuthorReply:
		return "author-reply"
	case ContentRetraction:
		return "retraction"
	case ContentSupplementary:
		return "supplementary"
	default:
		return "unknown"
	}
}
