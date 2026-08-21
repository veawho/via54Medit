package commands

import (
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"github.com/spf13/cobra"
	"github.com/veawho/via54Medit/internal/anno2ppt"
	"github.com/veawho/via54Medit/internal/foundation"
)

// resolvePython finds a usable python interpreter (env/config aware).
// Every Python subprocess in this file goes through it so the CLI works
// on any machine without a hardcoded venv layout.
func resolvePython() string {
	py, err := foundation.ResolvePython(nil)
	if err != nil {
		fmt.Fprintf(os.Stderr, "warning: %v (using literal 'python3')\n", err)
		return "python3"
	}
	return py
}

// anno2pptCmd Phase 7: 应证推理机 CLI 入口
// 集成: L0 PDF 真实性验证 + L1 PyMuPDF4LLM + L2 PaddleOCR + L4 应证推理机
//
// 用法:
//
//	medit anno2ppt parse "..."                    # 4 维要素抽取
//	medit anno2ppt confirm <text> <rows.json>     # 应证推理
//	medit anno2ppt ocr <pdf> <page-num>           # PaddleOCR 解析 PDF 页
//	medit anno2ppt l0verify <pdf> <doi>           # L0 PDF 真实性验证
//	medit anno2ppt pipeline <pdf> <text>           # 全流程: L0 → OCR → 表格 → 应证
var anno2pptCmd = &cobra.Command{
	Use:   "anno2ppt",
	Short: "Phase 7 algorithm-driven citation highlight (L0+L4 应证推理机)",
	Long:  `anno2ppt is the Phase 7 algorithm-driven highlight engine with L0 PDF authenticity verification.`,
}

var anno2pptParseCmd = &cobra.Command{
	Use:   "parse <text>",
	Short: "Parse PPT allegation text into 4-dim information elements",
	Args:  cobra.MinimumNArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		text := args[0]
		a := anno2ppt.ParseAllegation(text)
		return json.NewEncoder(os.Stdout).Encode(map[string]interface{}{
			"raw_text": a.RawText,
			"elements": a.Elements,
		})
	},
}

var anno2pptConfirmCmd = &cobra.Command{
	Use:   "confirm <text> <table_rows.json>",
	Short: "Confirm allegation against PDF table rows",
	Args:  cobra.MinimumNArgs(2),
	RunE: func(cmd *cobra.Command, args []string) error {
		text := args[0]
		rowsFile := args[1]

		raw, err := os.ReadFile(rowsFile)
		if err != nil {
			return fmt.Errorf("read rows: %w", err)
		}
		var rows []anno2ppt.TableRow
		if err := json.Unmarshal(raw, &rows); err != nil {
			return fmt.Errorf("parse rows JSON: %w", err)
		}

		a := anno2ppt.ParseAllegation(text)
		m := anno2ppt.ConfirmAllegation(a, nil, rows)

		return json.NewEncoder(os.Stdout).Encode(map[string]interface{}{
			"allegation":      a,
			"confirm_score":   m.ConfirmScore,
			"mismatch_report": m.MismatchReport,
			"decision":        m.Decision,
			"bbox_count":      len(m.Decision.BBoxes),
		})
	},
}

var anno2pptOcrCmd = &cobra.Command{
	Use:   "ocr <pdf_path> <page_num>",
	Short: "Run PaddleOCR on a PDF page, output structured table rows",
	Args:  cobra.MinimumNArgs(2),
	RunE: func(cmd *cobra.Command, args []string) error {
		pdfPath := args[0]
		pageNum := args[1]

		// 调用 Python 脚本做 OCR (PaddleOCR + PP-Structure)
		scriptPath := foundation.HermesPath("skills", "via54medit", "via54medit-anno2ppt-phase7", "scripts", "paddleocr_pdf_page.py")
		// 如果没安装到 skill, fallback 到仓库 scripts/ (git clone 部署形态)
		if _, err := os.Stat(scriptPath); os.IsNotExist(err) {
			scriptPath = filepath.Join("scripts", "paddleocr_pdf_page.py")
		}

		pyExe := resolvePython()
		cmdP := exec.Command(pyExe, scriptPath, pdfPath, pageNum)
		cmdP.Stdout = os.Stdout
		cmdP.Stderr = os.Stderr
		return cmdP.Run()
	},
}

// anno2pptL0VerifyCmd L0 PDF 真实性验证 (用户 2026-08-01 教训)
//
// 用法: medit anno2ppt l0verify <pdf_path> <doi>
//
// 输出: L0 验证结果 (verified=true/false, score, title_similarity, author_similarity, ...)
// 决策:
//
//	verified=true (score >= 0.70) → PDF 真实可信, 继续 L4
//	0.45 <= score < 0.70 → warning, 需 LLM 复核
//	score < 0.45 → reject, 走 fallback
//
// 触发流: 任何新 Pn-x 抓 PDF 时, 必须先做 L0 验证.
// 设计: 用户 2026-08-01 批评 v3.9 P22-1 main PDF 是 liangyihui.net 截图包壳,
//
//	误标记为 ESMO 2025 #1494P. L0 拦截此类"看起来像但实际不是"的 PDF.
var anno2pptL0VerifyCmd = &cobra.Command{
	Use:   "l0verify <pdf_path> <doi>",
	Short: "L0 PDF authenticity verification via Crossref + metadata",
	Long: `L0 verification: validates if the PDF actually represents the cited DOI.

Algorithm:
  score = 0.45*TitleSim + 0.30*AuthorSim + 0.15*DateMatch + 0.10*MetadataCompleteness
  TitleSim: Jaccard similarity between PDF metadata.Title and Crossref title
  AuthorSim: PDF metadata.Author contains Crossref first author family name
  DateMatch: PDF CreationDate >= Crossref published date
  MetadataCompleteness: 4-field completeness (title/author/subject/creator)

Usage:
  medit anno2ppt l0verify paper.pdf 10.1016/j.annonc.2025.08.2124`,
	Args: cobra.MinimumNArgs(2),
	RunE: func(cmd *cobra.Command, args []string) error {
		pdfPath := args[0]
		doi := args[1]

		// 读 PDF metadata (用 PyMuPDF)
		title, author, subject, creator, creationStr, err := extractPDFMetadata(pdfPath)
		if err != nil {
			return fmt.Errorf("extract PDF metadata: %w", err)
		}

		creationTime, _ := time.Parse(time.RFC3339, creationStr)

		// L0 验证
		res := anno2ppt.L0Verify(title, author, subject, creator, creationTime, doi)

		// 输出 JSON
		out := map[string]interface{}{
			"pdf_path":              pdfPath,
			"doi":                   doi,
			"verified":              res.Verified,
			"score":                 res.Score,
			"title_similarity":      res.TitleSim,
			"author_similarity":     res.AuthorSim,
			"date_match":            res.DateMatch,
			"metadata_completeness": res.MetaCompl,
			"pdf_title":             res.PDFTitle,
			"reference_title":       res.RefTitle,
			"issue":                 res.Issue,
		}
		if res.Verified {
			out["decision"] = "PASS: PDF is authentic, proceed to L4"
		} else if res.Score >= 0.45 {
			out["decision"] = "WARNING: partial match, recommend LLM review"
		} else {
			out["decision"] = "REJECT: PDF not authentic to cited DOI, use fallback"
		}
		return json.NewEncoder(os.Stdout).Encode(out)
	},
}

// extractPDFMetadata 用 PyMuPDF 抽取 PDF metadata
//
// 通过 Python 子进程调用, 避免 Go 端引入 PyMuPDF 依赖
func extractPDFMetadata(pdfPath string) (title, author, subject, creator, creationStr string, err error) {
	pyExe := resolvePython()
	scriptPath := filepath.Join(os.Getenv("HOME"), "Desktop", "developments", "via54Medit", "scripts", "l0_extract_pdf_meta.py")
	// 如果本地脚本不存在, 用 inline one-liner
	if _, statErr := os.Stat(scriptPath); os.IsNotExist(statErr) {
		// inline PyMuPDF (用 here-string 避免 Go % verb 冲突)
		oneLiner := `import sys, json
import fitz
doc = fitz.open(sys.argv[1])
m = doc.metadata
print(json.dumps({
    "title": m.get("title", "") or "",
    "author": m.get("author", "") or "",
    "subject": m.get("subject", "") or "",
    "creator": m.get("creator", "") or "",
    "creation": m.get("creationDate", "") or "",
}))
`
		out, err := exec.Command(pyExe, "-c", oneLiner, pdfPath).Output()
		if err != nil {
			return "", "", "", "", "", fmt.Errorf("inline fitz: %w", err)
		}
		var m map[string]string
		if err := json.Unmarshal(out, &m); err != nil {
			return "", "", "", "", "", fmt.Errorf("parse inline: %w", err)
		}
		return m["title"], m["author"], m["subject"], m["creator"], m["creation"], nil
	}

	out, err := exec.Command(pyExe, scriptPath, pdfPath).Output()
	if err != nil {
		return "", "", "", "", "", fmt.Errorf("script: %w", err)
	}
	var m map[string]string
	if err := json.Unmarshal(out, &m); err != nil {
		return "", "", "", "", "", fmt.Errorf("parse script: %w", err)
	}
	return m["title"], m["author"], m["subject"], m["creator"], m["creation"], nil
}

// extractPDFMetadataSimple 简化版 metadata 抽取 (用于 classify 子命令)
//
// 返回: producer, creator, first_page_text, error
func extractPDFMetadataSimple(pdfPath string) (producer, creator, firstText string, err error) {
	pyExe := resolvePython()
	// 用 here-string (避免 Go % 字符与 Python 代码冲突)
	pythonCode := `import sys, json
import fitz
doc = fitz.open(sys.argv[1])
m = doc.metadata
first_text = doc[0].get_text()[:200] if doc.page_count > 0 else ""
print(json.dumps({
    "producer": m.get("producer", "") or "",
    "creator": m.get("creator", "") or "",
    "first_text": first_text,
}))
`
	out, err := exec.Command(pyExe, "-c", pythonCode, pdfPath).Output()
	if err != nil {
		return "", "", "", fmt.Errorf("inline fitz: %w", err)
	}
	var m map[string]string
	if err := json.Unmarshal(out, &m); err != nil {
		return "", "", "", fmt.Errorf("parse inline: %w", err)
	}
	return m["producer"], m["creator"], m["first_text"], nil
}

// anno2pptClassifyCmd L0 PDF 类型分类 (用户 2026-08-01 实战 Pn-x 修复)
//
// 用法: medit anno2ppt classify <pdf_path>
//
// 算法:
//  1. producer 关键词匹配 (blacklist / whitelist)
//  2. creator 关键词匹配 (Mozilla + Skia = Chrome 截图)
//  3. 文字层内容判断 ("Image: fig2.png" = ReportLab, "An official website" = Chrome)
//
// 输出: PDFType (real_pdf / reportlab_screenshot / chrome_screenshot / meeting_abstract / unknown)
//   - 修复策略 (replace_with_real_pdf / find_oa_am / abstract_as_main / keep_as_is / inspect_manually)
var anno2pptClassifyCmd = &cobra.Command{
	Use:   "classify <pdf_path>",
	Short: "Classify PDF type by producer+creator+text (ReportLab/Chrome/Real PDF)",
	Long: `Classify PDF and recommend repair strategy.

Producer Blacklist: ReportLab PDF Library, WeasyPrint, Skia/PDF + Mozilla
Producer Whitelist: Veeva Vault, Adobe InDesign, Arbortext, pdfmake, XPP

Output JSON:
  {
    "pdf_type": "reportlab_screenshot",
    "strategy": "replace_with_real_pdf",
    "reason": "producer_blacklist: ReportLab PDF Library"
  }`,
	Args: cobra.MinimumNArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		pdfPath := args[0]
		producer, creator, firstText, err := extractPDFMetadataSimple(pdfPath)
		if err != nil {
			return fmt.Errorf("extract PDF metadata: %w", err)
		}
		pdfType := anno2ppt.ClassifyPDF(producer, creator, firstText)
		strategy := anno2ppt.RecommendStrategy(pdfType, "") // DOI 可选
		ok, reason := anno2ppt.L0ProducerCheck(producer, creator)
		return json.NewEncoder(os.Stdout).Encode(map[string]interface{}{
			"pdf_path":           pdfPath,
			"producer":           producer,
			"creator":            creator,
			"pdf_type":           pdfType,
			"strategy":           strategy,
			"blacklist_check_ok": ok,
			"reason":             reason,
		})
	},
}

// anno2pptDualSourceCmd 双源架构 manifest (用户 2026-08-01 P30-1 实战)
//
// 用法: medit anno2ppt dual-source <pnx_id> <main_pdf> [--fallback <fallback_pdf>]
//
// 输出: JSON manifest schema, 含 evidence_sources, highlight_summary 等
var anno2pptDualSourceCmd = &cobra.Command{
	Use:   "dual-source <pnx_id> <main_pdf>",
	Short: "Generate dual-source manifest (main + fallback architecture)",
	Long: `Build a dual-source manifest for paywall-blocked Pn-x.

Example:
  medit anno2ppt dual-source P30-1 P30-1_main.pdf --fallback P30-1_fallback_NCT.pdf

Output: JSON with main_pdf, fallback_pdfs, evidence_sources, highlight_summary.`,
	Args: cobra.MinimumNArgs(2),
	RunE: func(cmd *cobra.Command, args []string) error {
		pnx := args[0]
		mainPDF := args[1]
		fallbackPDF, _ := cmd.Flags().GetString("fallback")
		doi, _ := cmd.Flags().GetString("doi")

		manifest := anno2ppt.NewDualSourceManifest(pnx, mainPDF)

		if fallbackPDF != "" {
			nctID := anno2ppt.FindNCTRegistry(doi)
			manifest.AddFallback(fallbackPDF, anno2ppt.EvidenceSource{
				Type:         anno2ppt.SourceTypeNCTRegistry,
				DOI:          doi,
				Layout:       "fallback",
				Citation:     nctID,
				Available:    nctID != "",
				Limit:        "ClinicalTrials.gov aggregation",
				DataProvided: []string{"any-grade AE table"},
			})
			if nctID != "" {
				manifest.FallbackTriggerReason = fmt.Sprintf("双源互补: NCT=%s 提供 any-grade AE 表", nctID)
			} else {
				manifest.FallbackTriggerReason = "双源互补: fallback 补充 any-grade AE 表"
			}
		}

		return json.NewEncoder(os.Stdout).Encode(manifest)
	},
}

func init() {
	anno2pptDualSourceCmd.Flags().String("fallback", "", "Fallback PDF path (e.g. NCT02329860 AE table)")
	anno2pptDualSourceCmd.Flags().String("doi", "", "DOI for NCT registry lookup")

	anno2pptCmd.AddCommand(anno2pptParseCmd)
	anno2pptCmd.AddCommand(anno2pptConfirmCmd)
	anno2pptCmd.AddCommand(anno2pptOcrCmd)
	anno2pptCmd.AddCommand(anno2pptL0VerifyCmd)
	anno2pptCmd.AddCommand(anno2pptClassifyCmd)
	anno2pptCmd.AddCommand(anno2pptDualSourceCmd)
	rootCmd.AddCommand(anno2pptCmd)
}
