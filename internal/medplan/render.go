// Markdown rendering of strategy deliverables: the outline tree with
// evidence footnotes, the insight/SWOT block, and the compliance
// verdict — one .md per audience, ready for human editing.
package medplan

import (
	"fmt"
	"strings"
)

// RenderOptions carries the optional companions of an outline.
type RenderOptions struct {
	Dossier    *ResearchDossier
	Insights   *Insights
	Compliance *ComplianceReport
	Brief      *Brief
}

// RenderMarkdown renders one outline to a Markdown document.
func RenderMarkdown(o *StrategyOutline, opt RenderOptions) string {
	var b strings.Builder
	title := "医学策划方案大纲"
	if o.Audience != "" {
		title += " — " + o.Audience.StringCN()
	}
	fmt.Fprintf(&b, "# %s\n\n", title)
	fmt.Fprintf(&b, "- 项目: `%s`\n", o.Project)
	fmt.Fprintf(&b, "- 版本: v%d (%s)\n", o.Version, o.GeneratedBy)
	if o.CreatedAt.Year() > 1 {
		fmt.Fprintf(&b, "- 生成时间: %s\n", o.CreatedAt.Format("2006-01-02 15:04"))
	}
	if opt.Brief != nil && opt.Brief.Product.Name != "" {
		fmt.Fprintf(&b, "- 产品: %s\n", opt.Brief.Product.Name)
	}
	fmt.Fprintln(&b)

	if o.Positioning != "" {
		fmt.Fprintf(&b, "> **品牌定位**: %s\n\n", o.Positioning)
	}
	if o.KeyMessage != "" {
		fmt.Fprintf(&b, "> **核心信息钥匙**: %s\n\n", o.KeyMessage)
	}

	// Compliance banner first — reviewers must see the verdict up front.
	if opt.Compliance != nil {
		writeComplianceBanner(&b, opt.Compliance)
	}

	// Outline sections.
	for i := range o.Sections {
		writeSection(&b, &o.Sections[i], opt)
	}

	// Insights (advantage first).
	if opt.Insights != nil && len(opt.Insights.Insights) > 0 {
		fmt.Fprintf(&b, "\n## 核心观点与竞争优势\n\n")
		for _, x := range opt.Insights.Insights {
			tag := ""
			if x.Advantage {
				tag = " ⭐竞争优势"
			}
			fmt.Fprintf(&b, "- **[%s|%s]%s** %s\n", x.ID, x.Strength, tag, x.Claim)
			if len(x.ItemIDs) > 0 {
				fmt.Fprintf(&b, "  - 证据: %s\n", strings.Join(x.ItemIDs, ", "))
			}
		}
		writeSWOT(&b, &opt.Insights.SWOT)
	}

	// Evidence appendix.
	if opt.Dossier != nil && len(opt.Dossier.Items) > 0 {
		fmt.Fprintf(&b, "\n## 附录: 调研证据索引\n\n")
		for _, dim := range opt.Dossier.Dimensions() {
			fmt.Fprintf(&b, "### %s\n\n", dim.StringCN())
			for _, it := range opt.Dossier.ItemsByDimension(dim) {
				flag := ""
				if it.NeedsVerification {
					flag = " ⚠️待人工核验"
				}
				fmt.Fprintf(&b, "- **[%s]**%s %s\n", it.ID, flag, it.Title)
				if it.Summary != "" {
					fmt.Fprintf(&b, "  - %s\n", it.Summary)
				}
				if it.URL != "" {
					fmt.Fprintf(&b, "  - 来源: %s\n", it.URL)
				}
			}
			fmt.Fprintln(&b)
		}
		if opt.Dossier.Notes != "" {
			fmt.Fprintf(&b, "### 综合分析\n\n%s\n", opt.Dossier.Notes)
		}
	}
	return b.String()
}

func writeSection(b *strings.Builder, sec *OutlineSection, opt RenderOptions) {
	depth := strings.Count(sec.ID, ".")
	switch depth {
	case 0:
		fmt.Fprintf(b, "\n## %s %s\n\n", sec.ID, sec.Title)
	case 1:
		fmt.Fprintf(b, "\n### %s %s\n\n", sec.ID, sec.Title)
	default:
		fmt.Fprintf(b, "\n**%s %s**\n\n", sec.ID, sec.Title)
	}
	for _, p := range sec.Points {
		fmt.Fprintf(b, "- %s\n", p)
	}
	if len(sec.Evidence) > 0 {
		fmt.Fprintf(b, "\n  证据: %s\n", strings.Join(sec.Evidence, ", "))
	}
	if sec.ComplianceNote != "" {
		fmt.Fprintf(b, "\n  > ⚠️ 合规: %s\n", sec.ComplianceNote)
	}
	for i := range sec.Children {
		writeSection(b, &sec.Children[i], opt)
	}
}

func writeSWOT(b *strings.Builder, s *SWOT) {
	quadrants := []struct {
		name  string
		items []string
	}{
		{"优势 S", s.Strengths},
		{"劣势 W", s.Weaknesses},
		{"机会 O", s.Opportunities},
		{"威胁 T", s.Threats},
	}
	any := false
	for _, q := range quadrants {
		if len(q.items) > 0 {
			any = true
		}
	}
	if !any {
		return
	}
	fmt.Fprintf(b, "\n### SWOT\n\n")
	for _, q := range quadrants {
		if len(q.items) == 0 {
			continue
		}
		fmt.Fprintf(b, "**%s**\n", q.name)
		for _, it := range q.items {
			fmt.Fprintf(b, "- %s\n", it)
		}
	}
}

func writeComplianceBanner(b *strings.Builder, r *ComplianceReport) {
	verdictLabel := map[string]string{
		"pass": "✅ 通过",
		"warn": "⚠️ 需复核",
		"fail": "❌ 不合规",
	}[r.Verdict]
	if verdictLabel == "" {
		verdictLabel = r.Verdict
	}
	counts := r.CountsBySeverity()
	fmt.Fprintf(b, "## 合规验证 (中国大陆) — %s\n\n", verdictLabel)
	fmt.Fprintf(b, "引擎: `%s` | fatal: %d | warn: %d | info: %d\n\n",
		r.Engine, counts[SevFatal], counts[SevWarn], counts[SevInfo])
	if len(r.Findings) == 0 {
		fmt.Fprintln(b, "未发现规则命中。语义风险仍需人工法务复核。")
		return
	}
	fmt.Fprintln(b, "| 级别 | 规则 | 位置 | 命中内容 | 建议 |")
	fmt.Fprintln(b, "|---|---|---|---|---|")
	for _, f := range r.Findings {
		loc := f.SectionID
		if loc == "" {
			loc = "—"
		}
		matched := f.Matched
		if matched == "" {
			matched = "—"
		}
		fmt.Fprintf(b, "| %s | `%s` | %s | %s | %s |\n",
			f.Severity, f.RuleID, loc, escapeCell(truncateRunes(matched, 40)), escapeCell(truncateRunes(f.Suggestion, 60)))
	}
	fmt.Fprintln(b)
}

// escapeCell keeps a Markdown table cell on one line.
func escapeCell(s string) string {
	s = strings.ReplaceAll(s, "|", "\\|")
	s = strings.ReplaceAll(s, "\n", " ")
	return s
}
