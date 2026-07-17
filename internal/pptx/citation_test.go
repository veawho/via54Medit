package pptx

import (
	"strings"
	"testing"
)

func TestIsCitationLine_Basic(t *testing.T) {
	tests := []struct {
		name  string
		tline string
		want  bool
	}{
		{
			name:  "standard citation with journal and year",
			tline: "Finn RS, IMbrave150, N Engl J Med 2020; 382(18):1894-1905",
			want:  true,
		},
		{
			name:  "citation with DOI",
			tline: "Ren Z, ORIENT-32, Lancet Oncol 2021; 22(8):1112-1123, doi:10.1016/S1470-2045(21)00252-7",
			want:  true,
		},
		{
			name:  "citation with PMID",
			tline: "Song YG, Bleeding Meta, Liver Cancer 2024; 15(4):345-356, PMID:39687040",
			want:  true,
		},
		{
			name:  "citation with et al",
			tline: "Yau T, et al., Lancet 2025; 406(10408):1001-1010",
			want:  true,
		},
		{
			name:  "not a citation - plain text",
			tline: "三重获益，引领uHCC一线治疗新标准",
			want:  false,
		},
		{
			name:  "not a citation - short line",
			tline: "HIMALAYA",
			want:  false,
		},
		{
			name:  "OA journal citation",
			tline: "Lin J, Front Oncol 2022; 12:906778",
			want:  true,
		},
		{
			name:  "numbered reference",
			tline: "1. Kudo M, Lenvatinib vs Sorafenib, Lancet 2018; 391:1141-1151",
			want:  true,
		},
		{
			name:  "Chinese reference label",
			tline: "参考文献 免疫检查点抑制剂联合治疗一线肝细胞癌",
			want:  true,
		},
	}

	for _, tt := range tests {
		tt := tt
		t.Run(tt.name, func(t *testing.T) {
			got := isCitationLine(tt.tline)
			if got != tt.want {
				t.Errorf("isCitationLine(%q) = %v, want %v", tt.tline, got, tt.want)
			}
		})
	}
}

func TestExtractSlideNum(t *testing.T) {
	tests := []struct {
		filename string
		want     int
	}{
		{"ppt/slides/slide1.xml", 1},
		{"ppt/slides/slide23.xml", 23},
		{"ppt/notesSlides/notesSlide5.xml", 5},
		{"ppt/slides/notes.xml", 0},
		{"ppt/slides/slide.xml", 0},
	}
	for _, tt := range tests {
		got := extractSlideNum(tt.filename)
		if got != tt.want {
			t.Errorf("extractSlideNum(%q) = %d, want %d", tt.filename, got, tt.want)
		}
	}
}

func TestParseCitationLine_ExtractFields(t *testing.T) {
	raw := "Qin S, Tislelizumab vs Sorafenib, JAMA Oncol 2023; 9(2):189-199, doi:10.1001/jamaoncol.2022.7654"
	e := ParseCitationLine(raw)
	if e.DOI != "10.1001/jamaoncol.2022.7654" {
		t.Errorf("DOI = %q, want 10.1001/jamaoncol.2022.7654", e.DOI)
	}
	if e.Year != 2023 {
		t.Errorf("Year = %d, want 2023", e.Year)
	}
	if e.Journal != "JAMA Oncol" {
		t.Errorf("Journal = %q, want JAMA Oncol", e.Journal)
	}
}

func TestParseCitationLine_PMID(t *testing.T) {
	raw := "Song YG, Bleeding Meta, Liver Cancer 2024; 15(4):345-356, PMID:39687040"
	e := ParseCitationLine(raw)
	if e.PMID != "39687040" {
		t.Errorf("PMID = %q, want 39687040", e.PMID)
	}
	if e.Year != 2024 {
		t.Errorf("Year = %d, want 2024", e.Year)
	}
}

func TestParseCitationLine_VolumeIssue(t *testing.T) {
	raw := "Ren Z, ORIENT-32, Lancet Oncol 2021; 22(8):1112-1123"
	e := ParseCitationLine(raw)
	if e.Volume != "22(8)" {
		t.Errorf("Volume = %q, want 22(8)", e.Volume)
	}
	if e.Issue != "8" {
		t.Errorf("Issue = %q, want 8", e.Issue)
	}
	if e.Pages != "1112-1123" {
		t.Errorf("Pages = %q, want 1112-1123", e.Pages)
	}
}

func TestExtractCitationLines(t *testing.T) {
	slideTexts := map[int]string{
		1: "HIMALAYA trial results: overall survival benefit was demonstrated",
		2: "1. Finn RS, IMbrave150, N Engl J Med 2020; 382(18):1894-1905",
		3: "2. Yau T, CheckMate 459, Lancet Oncol 2022; 23(2):156-168",
		4: "References: 检查点抑制剂联合治疗一线肝细胞癌",
	}
	lines := ExtractCitationLines(slideTexts)
	if len(lines) == 0 {
		t.Fatal("expected citation lines, got 0")
	}
	found := false
	for _, l := range lines {
		if l.SlideIndex == 2 && strings.Contains(l.RawText, "Finn RS") {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected to find Finn RS citation on slide 2")
	}
}

func TestFindCitationLines_JournalWindow(t *testing.T) {
	text := "Lau G, et al. 2025. J Hepatol. 82(2): 258-267 HIMALAYA"
	cites := findCitationLines(text)
	if len(cites) == 0 {
		t.Errorf("expected to find a citation with J Hepatol, got %d results", len(cites))
	}
}

func TestBatchResult_Structure(t *testing.T) {
	r := &BatchResult{
		Total:          5,
		Exact:          3,
		Downloadable:   4,
	}
	if r.Total != 5 {
		t.Fatal("BatchResult fields not accessible")
	}
}

func TestExtractSlideText_Empty(t *testing.T) {
	data := []byte(`<root><title>test</title></root>`)
	result := extractSlideText(data)
	if result != "" {
		t.Errorf("extractSlideText returned %q, want empty", result)
	}
}

func TestExtractSlideText_WithText(t *testing.T) {
	data := []byte(`<root><a:t>Hello</a:t><a:t>World</a:t></root>`)
	result := extractSlideText(data)
	if result != "Hello World" {
		t.Errorf("extractSlideText returned %q, want Hello World", result)
	}
}
