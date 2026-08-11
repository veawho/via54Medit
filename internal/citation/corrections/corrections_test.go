package corrections

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestLoadLog_NewFile(t *testing.T) {
	tmpDir := t.TempDir()
	logPath := filepath.Join(tmpDir, "corrections.json")

	log, err := LoadLog(logPath)
	if err != nil {
		t.Fatalf("LoadLog: %v", err)
	}
	if log == nil {
		t.Fatal("log is nil")
	}
	if len(log.Corrections) != 0 {
		t.Errorf("expected 0 corrections, got %d", len(log.Corrections))
	}
}

func TestRecordCorrection(t *testing.T) {
	tmpDir := t.TempDir()
	logPath := filepath.Join(tmpDir, "corrections.json")

	log, err := LoadLog(logPath)
	if err != nil {
		t.Fatalf("LoadLog: %v", err)
	}

	c := CorrectionEntry{
		Type:          TypeAuthorCorrection,
		Context:       "Abou-Alfa should be detected as author",
		Before:        "empty",
		After:         "Abou-Alfa GK, et al.",
		SourceProject: "雷管方案_文献整理",
	}

	if err := log.Record(c); err != nil {
		t.Fatalf("Record: %v", err)
	}
	if len(log.Corrections) != 1 {
		t.Errorf("expected 1 correction, got %d", len(log.Corrections))
	}
	if log.Corrections[0].ID == "" {
		t.Errorf("ID should be auto-generated")
	}
	if log.Corrections[0].Status != "pending" {
		t.Errorf("Status = %q, want 'pending'", log.Corrections[0].Status)
	}

	// Reload and verify persistence
	log2, err := LoadLog(logPath)
	if err != nil {
		t.Fatalf("reload: %v", err)
	}
	if len(log2.Corrections) != 1 {
		t.Errorf("expected 1 after reload, got %d", len(log2.Corrections))
	}
}

func TestPendingCorrections(t *testing.T) {
	log := &Log{Corrections: []CorrectionEntry{
		{ID: "1", Status: "pending"},
		{ID: "2", Status: "fixed"},
		{ID: "3", Status: "verified"},
		{ID: "4", Status: "pending"},
	}}

	pending := log.PendingCorrections()
	if len(pending) != 2 {
		t.Errorf("expected 2 pending, got %d", len(pending))
	}
}

func TestMarkFixed(t *testing.T) {
	tmpDir := t.TempDir()
	logPath := filepath.Join(tmpDir, "corrections.json")
	log, _ := LoadLog(logPath)

	log.Record(CorrectionEntry{ID: "test-1", Type: TypeAuthorCorrection})
	log.Record(CorrectionEntry{ID: "test-2", Type: TypeJournalCorrection})

	if err := log.MarkFixed("test-1"); err != nil {
		t.Fatalf("MarkFixed: %v", err)
	}

	if log.Corrections[0].Status != "fixed" {
		t.Errorf("Status = %q, want 'fixed'", log.Corrections[0].Status)
	}
	if log.Corrections[1].Status != "pending" {
		t.Errorf("Status = %q, want 'pending'", log.Corrections[1].Status)
	}
}

func TestSanitizeFn(t *testing.T) {
	tests := []struct {
		input string
		want  string
	}{
		{"corr-2026-07-31-001", "corr_2026_07_31_001"},
		{"test.abc", "test_abc"},
		{"normal_name", "normal_name"},
	}
	for _, tt := range tests {
		t.Run(tt.input, func(t *testing.T) {
			got := sanitizeFn(tt.input)
			if got != tt.want {
				t.Errorf("sanitizeFn(%q) = %q, want %q", tt.input, got, tt.want)
			}
		})
	}
}

func TestGenerateTestCase_Author(t *testing.T) {
	c := CorrectionEntry{
		ID:          "test-author-1",
		Type:        TypeAuthorCorrection,
		Context:     "Abou-Alfa should be detected",
		After:       "Abou-Alfa GK, et al.",
		DOIAfter:    "10.1056/EVIDoa2100070",
	}

	tc := GenerateTestCase(c)
	if tc.FunctionName == "" {
		t.Error("FunctionName should be set")
	}
	if tc.SourceCorrection != "test-author-1" {
		t.Errorf("SourceCorrection = %q, want test-author-1", tc.SourceCorrection)
	}
	if tc.GoTestBody == "" {
		t.Error("GoTestBody should not be empty")
	}
}

func TestGenerateAllFromLog(t *testing.T) {
	log := &Log{
		Corrections: []CorrectionEntry{
			{ID: "1", Type: TypeAuthorCorrection, Status: "pending", After: "Abou-Alfa"},
			{ID: "2", Type: TypeJournalCorrection, Status: "fixed"},
			{ID: "3", Type: TypeDOICorrection, Status: "pending", DOIBefore: "10.1234/test", DOIAfter: "test"},
		},
	}

	cases := log.GenerateAll()
	if len(cases) != 2 {
		t.Errorf("expected 2 test cases (pending only), got %d", len(cases))
	}
}

func TestGenerateGoTestFile(t *testing.T) {
	log := &Log{
		Corrections: []CorrectionEntry{
			{ID: "test-1", Type: TypeAuthorCorrection, Status: "pending", After: "Abou-Alfa", DOIAfter: "10.1234/test"},
			{ID: "test-2", Type: TypeJournalCorrection, Status: "pending", After: "NEJM Evid"},
		},
	}

	code := log.GenerateGoTestFile("citation")
	if code == "" {
		t.Error("generated code should not be empty")
	}
	if !contains(code, "package citation") {
		t.Error("should contain package declaration")
	}
	if !contains(code, "import \"testing\"") {
		t.Error("should import testing")
	}
	if !contains(code, "Abou-Alfa") {
		t.Error("should include Abou-Alfa from correction")
	}
	if !contains(code, "NEJM") {
		t.Error("should include NEJM from correction")
	}
}

// TestSeedFromLeiguanProject simulates seeding the corrections log with
// real corrections from the 雷管方案_文献整理 project (Phase 6 retrospective).
func TestSeedFromLeiguanProject(t *testing.T) {
	tmpDir := t.TempDir()
	logPath := filepath.Join(tmpDir, "corrections.json")

	log, _ := LoadLog(logPath)

	// 12 historical corrections from 雷管方案_文献整理 project
	historical := []CorrectionEntry{
		{
			Type:                     TypeAuthorCorrection,
			Context:                  "v1 regex missed hyphenated author Abou-Alfa",
			After:                    "Abou-Alfa GK, et al.",
			DOIAfter:                 "10.1056/EVIDoa2100070",
			SourceProject:            "雷管方案_文献整理",
			ExpectedAlgorithmChange:  "regex should support hyphenated surnames",
			Status:                   "fixed",
		},
		{
			Type:                     TypeAuthorCorrection,
			Context:                  "v1 missed multi-author 'Peter Robert Galle, Thomas Decaens'",
			After:                    "Peter Robert Galle, Thomas Decaens, Masatoshi Kudo",
			SourceProject:            "雷管方案_文献整理",
			ExpectedAlgorithmChange:  "extract multi-author lists before stopping at journal",
			Status:                   "fixed",
		},
		{
			Type:                     TypeDOICorrection,
			Context:                  "v1 extracted wrong DOI tail for multi-segment DOIs",
			DOIBefore:                "10.1158/1078-0432.CCR-24-0006",
			DOIAfter:                 "1078-0432.CCR-24-0006",
			SourceProject:            "雷管方案_文献整理",
			ExpectedAlgorithmChange:  "extract full DOI suffix including journal code",
			Status:                   "fixed",
		},
		{
			Type:                     TypeRichTextConversion,
			Context:                  "v1 used type='url' but Feishu requires type='link'",
			After:                    "{type: 'link', link: url, text: url}",
			SourceProject:            "雷管方案_文献整理",
			ExpectedAlgorithmChange:  "use 'link' (not 'url') for Feishu rich text",
			Status:                   "fixed",
		},
		{
			Type:                     TypeRichTextConversion,
			Context:                  "v1 sent [{text, type}] directly, but Feishu needs {rich_text: [...]} envelope",
			After:                    "{rich_text: [{text, type}, ...]}",
			SourceProject:            "雷管方案_文献整理",
			ExpectedAlgorithmChange:  "wrap in {rich_text: [...]} envelope",
			Status:                   "fixed",
		},
		{
			Type:                     TypeSyncDirection,
			Context:                  "sync_all.py reverse-writes CSV, clobbering manual edits",
			After:                    "use citation package directly, never sync_all.py Step 1",
			SourceProject:            "雷管方案_文献整理",
			ExpectedAlgorithmChange:  "add hard rule: never call sync_all.py",
			Status:                   "fixed",
		},
		{
			Type:                     TypeFileMapping,
			Context:                  "Row 47 G column pointed to wrong PDF (swap with Row 48)",
			RowIndex:                 47,
			SlidePage:                "19-1",
			After:                    "P19-1_P20-1_P24-8_P24-9/P19-1_P20-1_P24-8_P24-9_main_Qin_S_Liver_Cancer_2021_Lenvatinib.pdf",
			SourceProject:            "雷管方案_文献整理",
			ExpectedAlgorithmChange:  "improve Pn-x shared PDF resolver",
			Status:                   "fixed",
		},
		{
			Type:                     TypeRichTextConversion,
			Context:                  "H column had 152 row drift (not pushed)",
			SourceProject:            "雷管方案_文献整理",
			ExpectedAlgorithmChange:  "ensure all 5 columns (D/E/F/G/H) are pushed",
			Status:                   "fixed",
		},
		{
			Type:                     TypeGeneral,
			Context:                  "UTF-8 BOM in CSV header broke Go encoding/csv",
			SourceProject:            "雷管方案_文献整理",
			ExpectedAlgorithmChange:  "strip UTF-8 BOM in readCSV",
			Status:                   "fixed",
		},
		{
			Type:                     TypeGeneral,
			Context:                  "CSV trailing \\r\\n caused 1-char mismatch with Feishu",
			SourceProject:            "雷管方案_文献整理",
			ExpectedAlgorithmChange:  "TrimRight every column on read",
			Status:                   "fixed",
		},
		{
			Type:                     TypeFileMapping,
			Context:                  "Row 156 P43-4 D column was Abou-Alfa but G pointed to Qin APASL (wrong)",
			RowIndex:                 156,
			SlidePage:                "43-5",
			After:                    "P11-1_P26-4_P27-4_P29-2_P33-2_P33-6_P43-5/P11-1_HIMALAYA_Primary_AbouAlfa_NEJMEvid2022_Main.pdf",
			SourceProject:            "雷管方案_文献整理",
			ExpectedAlgorithmChange:  "cross-validate D column author vs G PDF content",
			Status:                   "fixed",
		},
		{
			Type:                     TypeGeneral,
			Context:                  "Cron 30-min interval wasted resources (95% idle)",
			SourceProject:            "雷管方案_文献整理",
			ExpectedAlgorithmChange:  "embed in hlo_daily_normalize (daily 22:00)",
			Status:                   "fixed",
		},
	}

	for _, c := range historical {
		c.Timestamp = time.Now()
		if err := log.Record(c); err != nil {
			t.Fatalf("Record: %v", err)
		}
	}

	if len(log.Corrections) != 12 {
		t.Errorf("expected 12 corrections, got %d", len(log.Corrections))
	}

	// Verify pending = 0 (all marked fixed)
	pending := log.PendingCorrections()
	if len(pending) != 0 {
		t.Errorf("expected 0 pending (all fixed), got %d", len(pending))
	}
}

// Helper
func contains(s, substr string) bool {
	return len(s) > 0 && len(substr) > 0 && (s == substr || containsSubstring(s, substr))
}

func containsSubstring(s, substr string) bool {
	for i := 0; i+len(substr) <= len(s); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

// Ensure file is used
var _ = json.Marshal
var _ = os.Create
// TestSeedFromLeiguanProject_Part2 covers the Phase 4 batch 1 fixes
// (user uploaded STRIDE/TREMENDOUS PDF on 2026-07-31, triggering 6 row fixes).
func TestSeedFromLeiguanProject_Part2(t *testing.T) {
	tmpDir := t.TempDir()
	logPath := filepath.Join(tmpDir, "corrections.json")
	log, _ := LoadLog(logPath)

	batch1Fixes := []CorrectionEntry{
		{
			ID:                       "corr-2026-07-31-001",
			Type:                     TypeFileMapping,
			Context:                  "Row 39/56/73/99/155 G列指向 P14-1_main_related.pdf 但内容是中文垃圾页 (单机游戏大全)",
			Before:                   "P14-1_P22-3_P24-1_P26-6_P33-4_P43-4/P14-1_main_related.pdf",
			After:                    "P14-1_P22-3_P24-1_P26-6_P33-4_P43-4/Qin_S_APASL_2025_TREMENDOUS_STRIDE_China_Cohort_FanJia_QinSK_Interview.pdf",
			ExpectedAlgorithmChange:  "verify 必须做 PDF content match, 不只检查 file existence",
			Status:                   "fixed",
			SourceProject:            "雷管方案_文献整理",
			RowIndex:                 39,
			SlidePage:                "14-1",
		},
		{
			ID:                       "corr-2026-07-31-002",
			Type:                     TypeFileMapping,
			Context:                  "Row 57 D=Lau G J Hepatol 2025, G=P14-1_main_related.pdf (中文垃圾页)",
			Before:                   "P14-1_P22-3_P24-1_P26-6_P33-4_P43-4/P14-1_main_related.pdf",
			After:                    "_downloads/Lau___2024_Cell_10_1097_HEP_0000000000001385_Immune.pdf",
			Status:                   "fixed",
			SourceProject:            "雷管方案_文献整理",
			RowIndex:                 57,
			SlidePage:                "24-2",
		},
		{
			ID:                       "corr-2026-07-31-003",
			Type:                     TypeGeneral,
			Context:                  "用户上传 STRIDE/TREMENDOUS 2025 APASL 访谈 PDF, 用于修复 5 row Qin S 2025 APASL OP0102 G 列错配",
			ExpectedAlgorithmChange:  "via54Medit citation.match 应该支持 会议摘要 + 中文媒体访谈 模式",
			Status:                   "fixed",
			SourceProject:            "雷管方案_文献整理",
		},
		{
			ID:                       "corr-2026-07-31-004",
			Type:                     TypeSyncDirection,
			Context:                  "修复 6 row G 列后, 立即 verify + push 飞书, 100% 一致 (0 mismatch)",
			Status:                   "fixed",
			SourceProject:            "雷管方案_文献整理",
		},
		{
			ID:                       "corr-2026-07-31-005",
			Type:                     TypeGeneral,
			Context:                  "Verify (D vs G) 必须做 content match, 不只 file existence (P0 priority)",
			ExpectedAlgorithmChange:  "verify_consistency.go 应当新增 PDF text content match",
			Status:                   "pending",
			SourceProject:            "雷管方案_文献整理",
		},
		{
			ID:                       "corr-2026-07-31-006",
			Type:                     TypeGeneral,
			Context:                  "Row 39/56/57/73/99/155 G 列文件存在但是内容是中文垃圾页 (不是真文献), 必须做内容 verify (P0 priority)",
			Status:                   "pending",
			SourceProject:            "雷管方案_文献整理",
		},
	}

	for _, c := range batch1Fixes {
		c.Timestamp = time.Now()
		if err := log.Record(c); err != nil {
			t.Fatalf("Record: %v", err)
		}
	}

	if len(log.Corrections) != 6 {
		t.Errorf("expected 6 corrections, got %d", len(log.Corrections))
	}

	pending := log.PendingCorrections()
	if len(pending) != 2 {
		t.Errorf("expected 2 pending (corr-005/006), got %d", len(pending))
	}
}

// TestSeedFromLeiguanProject_Part3 covers Phase 4 batch 2 fixes
// (Sangro 2025 ESMO + CheckMate 9DW + Thyroid guideline + Stewart 2015)
// Total: 11 rows G path fixes + 4 row Song/CARES-310 fixes.
func TestSeedFromLeiguanProject_Part3(t *testing.T) {
	tmpDir := t.TempDir()
	logPath := filepath.Join(tmpDir, "corrections.json")
	log, _ := LoadLog(logPath)

	batch2 := []CorrectionEntry{
		{
			ID:                       "corr-2026-07-31-007",
			Type:                     TypeFileMapping,
			Context:                  "Row 26/32/51/58/76/152 D=Bruno Sangro ESMO 1494P, G=liangyihui_fig2 (图片, 不是文献)",
			After:                    "_downloads/Shukui___2025_ESMO_NoID_Sangro.pdf",
			ExpectedAlgorithmChange:  "D vs G content match should also detect 'fig2.png' as NOT a real paper",
			Status:                   "fixed",
			SourceProject:            "雷管方案_文献整理",
		},
		{
			ID:                       "corr-2026-07-31-008",
			Type:                     TypeFileMapping,
			Context:                  "Row 40/61/93 D=Galle/Llovet 2024 ASCO LBA4008 CheckMate 9DW, G=错配 (中文摘要/CheckMate9DW CSCO)",
			After:                    "_downloads/Rapid___2026_Cell_NCT04039607_Nivolumab.pdf",
			Status:                   "fixed",
			SourceProject:            "雷管方案_文献整理",
		},
		{
			ID:                       "corr-2026-07-31-009",
			Type:                     TypeFileMapping,
			Context:                  "Row 91 D=甲状腺癌指南 2023, G=PubMed printout 错配",
			After:                    "_downloads/Thyroid_Cancer_TKI_AE___2023_Source_10_19401_j_cnki_1007-3639_2023_09_009_Vol.pdf",
			Status:                   "fixed",
			SourceProject:            "雷管方案_文献整理",
		},
		{
			ID:                       "corr-2026-07-31-010",
			Type:                     TypeFileMapping,
			Context:                  "Row 134 D=Stewart 2015 Cancer Immunol Res, G=错配",
			After:                    "_downloads/Stewart___2026_Source_NoID_Identification_Characterization.pdf",
			Status:                   "fixed",
			SourceProject:            "雷管方案_文献整理",
		},
		{
			ID:                       "corr-2026-07-31-011",
			Type:                     TypeFileMapping,
			Context:                  "Row 106/145 D=Song YG Liver Cancer 2024 13(6):590-600, G=P33-1_main_related (wrong)",
			After:                    "_downloads/Yoo_J_2024_LiverCancer_10_1159_000539423_Young_Song_Kyeong.pdf",
			Status:                   "fixed",
			SourceProject:            "雷管方案_文献整理",
		},
		{
			ID:                       "corr-2026-07-31-012",
			Type:                     TypeGeneral,
			Context:                  "Row 19/66 D=Qin S Lancet Oncol 2025 26(12):1598-1611 (CARES-310), G 是 trial protocol 不是 published paper",
			ExpectedAlgorithmChange:  "Trial protocol vs published paper 应该区分 (不同 row 用同一份 protocol)",
			Status:                   "fixed",
			SourceProject:            "雷管方案_文献整理",
		},
	}

	for _, c := range batch2 {
		c.Timestamp = time.Now()
		if err := log.Record(c); err != nil {
			t.Fatalf("Record: %v", err)
		}
	}

	if len(log.Corrections) != 6 {
		t.Errorf("expected 6 corrections, got %d", len(log.Corrections))
	}
}
