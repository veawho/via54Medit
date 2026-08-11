// Package cite extracts academic citations from PPTX/PDF/DOCX documents,
// enriches them via PubMed/Crossref, and resolves against known trial names.
//
// Design:
//
//	Extractor interface  -- each format implements it
//	Factory             -- auto-detects by file extension
//	CitationVerifier    -- PMID → PubMed, DOI → Crossref,
//	                       fallback: trial-name → PubMed search
package cite

// Citation is the unified citation model.
type Citation struct {
	// Source
	DocumentType string `json:"document_type"`    // "pptx" | "pdf" | "docx"
	Number       int    `json:"number,omitempty"` // reference number if numbered style
	PageIndex    int    `json:"page_index"`       // 1-based page/slide number
	PageTitle    string `json:"page_title,omitempty"`

	// Raw
	RawText string `json:"raw_text"`

	// Parsed fields
	Authors string `json:"authors,omitempty"`
	Title   string `json:"title,omitempty"`
	Journal string `json:"journal,omitempty"`
	Year    int    `json:"year"`
	Volume  string `json:"volume,omitempty"`
	Issue   string `json:"issue,omitempty"`
	Pages   string `json:"pages,omitempty"`
	PMID    string `json:"pmid,omitempty"`
	DOI     string `json:"doi,omitempty"`

	// Verified metadata (enriched)
	VerifiedPMID    string `json:"verified_pmid,omitempty"`
	VerifiedDOI     string `json:"verified_doi,omitempty"`
	VerifiedTitle   string `json:"verified_title,omitempty"`
	VerifiedJournal string `json:"verified_journal,omitempty"`
	VerifiedYear    int    `json:"verified_year"`

	// Trial identification
	TrialName    string `json:"trial_name,omitempty"` // e.g. "HIMALAYA", "CheckMate 9L"
	IsTrialPaper bool   `json:"is_trial_paper"`

	// Verification
	Status  string `json:"status"` // "verified" | "partial" | "unverified" | "error"
	Message string `json:"message,omitempty"`
}

// Extractor extracts text pages and raw citation lines from a document.
type Extractor interface {
	// Type returns the document type: "pptx" | "pdf" | "docx"
	Type() string
	// ExtractPages returns (page_index_1based, full_page_text)
	ExtractPages() (map[int]string, error)
}
