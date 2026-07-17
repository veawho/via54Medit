// trialNames.go maps clinical trial names to PubMed search terms.
// This is the trial-name fallback layer: when PMID/DOI extraction fails,
// we search PubMed by trial name + drug + journal context.

package cite

import (
	"fmt"
	"strings"
)

// TrialName defines a trial and its metadata for search/enrichment.
type TrialName struct {
	Name      string   // canonical name: "HIMALAYA", "CheckMate 9L"
	Drugs     []string // drug names to anchor search: ["durvalumab", "tremelimumab"]
	Disease   string   // "hepatocellular carcinoma"
	Journal   string   // journal name
	Year      int      // publication year
	PMID      string   // expected PMID
	Title     string   // expected title fragment
}

// trialNameMap is the authoritative list of trial → PubMed search anchors.
var trialNameMap = map[string]TrialName{
	"HIMALAYA": {
		Name:    "HIMALAYA",
		Drugs:   []string{"tremelimumab", "durvalumab"},
		Disease: "hepatocellular carcinoma",
		Journal: "Hepatobiliary Surgery and Nutrition", // main paper
		Year:    2022,
		PMID:    "36016731",
		Title:   "Durvalumab plus tremelimumab in unresectable hepatocellular carcinoma",
	},
	"HIMALAYA-Asian": {
		Name:    "HIMALAYA",
		Drugs:   []string{"tremelimumab", "durvalumab"},
		Disease: "hepatocellular carcinoma",
		Journal: "J Hepatol",
		Year:    2025,
		PMID:    "39089633",
		Title:   "Asian subgroup",
	},
	"HIMALAYA-PRO": {
		Name:    "HIMALAYA",
		Drugs:   []string{"tremelimumab", "durvalumab"},
		Disease: "hepatocellular carcinoma",
		Journal: "J Clin Oncol",
		Year:    2024,
		PMID:    "38805668",
		Title:   "Patient-Reported Outcomes",
	},
	"IMbrave150": {
		Name:    "IMbrave150",
		Drugs:   []string{"atezolizumab", "bevacizumab"},
		Disease: "hepatocellular carcinoma",
		Journal: "N Engl J Med",
		Year:    2020,
		PMID:    "32402160",
		Title:   "Atezolizumab plus Bevacizumab",
	},
	"ORIENT-32": {
		Name:    "ORIENT-32",
		Drugs:   []string{"sintilimab", "IBI305"},
		Disease: "hepatocellular carcinoma",
		Journal: "Lancet Oncol",
		Year:    2021,
		PMID:    "34143971",
		Title:   "Sintilimab plus a bevacizumab biosimilar",
	},
	"CheckMate 9L": {
		Name:    "CheckMate 9L",
		Drugs:   []string{"tislelizumab", "sorafenib"},
		Disease: "hepatocellular carcinoma",
		Journal: "JAMA Oncol",
		Year:    2023,
		PMID:    "37796513",
		Title:   "Tislelizumab vs Sorafenib",
	},
	"CheckMate 459": {
		Name:    "CheckMate 459",
		Drugs:   []string{"nivolumab", "ipilimumab"},
		Disease: "hepatocellular carcinoma",
		Journal: "Lancet Oncol",
		Year:    2022,
		PMID:    "34914889",
		Title:   "Nivolumab versus sorafenib",
	},
	"CheckMate 9DW": {
		Name:    "CheckMate 9DW",
		Drugs:   []string{"nivolumab", "ipilimumab"},
		Disease: "hepatocellular carcinoma",
		Journal: "Lancet",
		Year:    2025,
		PMID:    "40349714",
		Title:   "Nivolumab plus ipilimumab versus lenvatinib or sorafenib",
	},
	"REACH-2": {
		Name:    "REACH-2",
		Drugs:   []string{"lenvatinib"},
		Disease: "hepatocellular carcinoma",
		Journal: "Lancet",
		Year:    2018,
		PMID:    "29433850",
		Title:   "Lenvatinib versus sorafenib",
	},
	"RESOLUTE-HEP": {
		Name:    "RESOLUTE-HEP",
		Drugs:   []string{"camrelizumab", "rivoceranib"},
		Disease: "hepatocellular carcinoma",
		Journal: "Lancet",
		Year:    2023,
		PMID:    "37499670",
		Title:   "Camrelizumab plus rivoceranib versus sorafenib as first-line therapy",
	},
	"CARES-310": {
		Name:    "CARES-310",
		Drugs:   []string{"camrelizumab", "rivoceranib"},
		Disease: "hepatocellular carcinoma",
		Journal: "Lancet Oncol",
		Year:    2025,
		PMID:    "41308676",
		Title:   "Camrelizumab plus rivoceranib versus sorafenib",
	},
	"REFine": {
		Name:    "REFine",
		Drugs:   []string{"donafenib"},
		Disease: "hepatocellular carcinoma",
		Journal: "J Clin Oncol",
		Year:    2021,
		PMID:    "34185551",
		Title:   "Donafenib Versus Sorafenib in First-Line Treatment",
	},
}

// LookupTrial searches trialNameMap for a given trial name (case-insensitive).
func LookupTrial(name string) (*TrialName, bool) {
	n := strings.ToUpper(strings.TrimSpace(name))
	for k, v := range trialNameMap {
		if strings.ToUpper(k) == n {
			return &v, true
		}
	}
	return nil, false
}

// AllTrials returns all trial names.
func AllTrials() []TrialName {
	out := make([]TrialName, 0, len(trialNameMap))
	for _, v := range trialNameMap {
		out = append(out, v)
	}
	return out
}

// BuildPubMedQuery constructs a PubMed-compatible search query for a trial.
// Returns a string like: "tremelimumab"[tiab] AND "durvalumab"[tiab] AND "hepatocellular carcinoma"[tiab]
func BuildPubMedQuery(t TrialName) string {
	var parts []string
	for _, drug := range t.Drugs {
		parts = append(parts, fmt.Sprintf("\"%s\"[tiab]", drug))
	}
	parts = append(parts, fmt.Sprintf("\"%s\"[tiab]", t.Disease))
	return strings.Join(parts, " AND ")
}
