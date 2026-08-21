// Semantic optimization: rewrite / deepen an existing outline from a
// natural-language instruction ("把传播策略扩充到县域市场", "为患者版
// 增加用药注意事项教育"), with version + changelog tracking and a
// deterministic before/after diff summary.
package medplan

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/veawho/via54Medit/internal/foundation"
)

// Optimizer applies semantic optimization passes to an outline.
// It requires an LLM — there is no meaningful deterministic rewrite.
type Optimizer struct {
	LLM foundation.LLMProvider
}

// Optimize returns a new version of the outline (the input is not
// mutated). instruction is the free-form optimization directive.
func (opt *Optimizer) Optimize(ctx context.Context, o *StrategyOutline, brief *Brief, d *ResearchDossier, instruction string) (*StrategyOutline, error) {
	if opt == nil || opt.LLM == nil {
		return nil, fmt.Errorf("medplan: optimize requires an LLM provider")
	}
	if o == nil {
		return nil, fmt.Errorf("medplan: optimize: nil outline")
	}
	if strings.TrimSpace(instruction) == "" {
		return nil, fmt.Errorf("medplan: optimize: empty instruction")
	}
	p := ProfileFor(o.Audience)
	sys := "你是资深医学策略总监。对给定策略大纲执行深度优化与扩充。输出必须是纯 JSON。" +
		"遵守中国大陆医学合规边界: 无绝对化用语、无疗效保证、处方药不面向公众促销。"
	user := fmt.Sprintf(`# 优化指令
%s

# 受众
%s — 基调: %s; 侧重: %s

# 产品背景
%s (适应症: %s, 分类: %s)
%s

# 调研材料摘要
%s

# 当前大纲 (v%d)
%s

# 输出要求
1. 完整输出优化后的整份大纲 (不是增量补丁), 满足优化指令
2. 保留未被指令影响的章节, 深化/扩充/重组指令涉及的章节
3. evidence 只允许引用材料中出现过的 ID
4. change_summary: 用 2-3 句话说明本次优化做了什么

输出 JSON: {"positioning":"...","key_message":"...","change_summary":"...","sections":[{"title":"...","points":["..."],"evidence":["L001"],"children":[...]}]}`,
		instruction,
		o.Audience.StringCN(), p.Tone, p.Focus,
		brief.Product.Name, strings.Join(brief.Product.Indications, "、"), brief.Product.RxStatus,
		brief.ExtraConstraints,
		dossierDigest(d, 8),
		o.Version,
		outlineDigest(o),
	)
	raw, err := opt.LLM.Complete(ctx, sys, user)
	if err != nil {
		return nil, fmt.Errorf("optimize: %w", err)
	}
	var got struct {
		Positioning   string       `json:"positioning"`
		KeyMessage    string       `json:"key_message"`
		ChangeSummary string       `json:"change_summary"`
		Sections      []llmSection `json:"sections"`
	}
	if err := json.Unmarshal([]byte(extractJSON(raw)), &got); err != nil {
		return nil, fmt.Errorf("optimize: parse: %w", err)
	}
	if len(got.Sections) == 0 {
		return nil, fmt.Errorf("optimize: model returned 0 sections")
	}

	next := *o // copy metadata (project/audience/changelog)
	next.Version = o.Version + 1
	next.Positioning = strings.TrimSpace(got.Positioning)
	if next.Positioning == "" {
		next.Positioning = o.Positioning
	}
	next.KeyMessage = strings.TrimSpace(got.KeyMessage)
	if next.KeyMessage == "" {
		next.KeyMessage = o.KeyMessage
	}
	validIDs := map[string]bool{}
	if d != nil {
		for _, it := range d.Items {
			validIDs[it.ID] = true
		}
	}
	next.Sections = convertSections(got.Sections, validIDs)
	next.UpdatedAt = nowUTC()
	summary := strings.TrimSpace(got.ChangeSummary)
	if summary == "" {
		summary = diffSummary(o, &next)
	} else {
		summary = summary + " | " + diffSummary(o, &next)
	}
	next.ChangeLog = append(append([]OutlineChange{}, o.ChangeLog...), OutlineChange{
		Version:     next.Version,
		Instruction: instruction,
		Summary:     summary,
		At:          nowUTC(),
	})
	return &next, nil
}

// ExpandSection is Optimize scoped to one section: the instruction is
// derived from the section and the caller's focus note.
func (opt *Optimizer) ExpandSection(ctx context.Context, o *StrategyOutline, brief *Brief, d *ResearchDossier, sectionID, focus string) (*StrategyOutline, error) {
	sec := o.FindSection(sectionID)
	if sec == nil {
		return nil, fmt.Errorf("medplan: expand: section %q not found", sectionID)
	}
	instruction := fmt.Sprintf("深度扩充「%s」章节: 增加子节结构与论据要点。%s", sec.Title, focus)
	return opt.Optimize(ctx, o, brief, d, instruction)
}

// outlineDigest renders an outline for the optimize prompt.
func outlineDigest(o *StrategyOutline) string {
	var b strings.Builder
	if o.Positioning != "" {
		fmt.Fprintf(&b, "定位: %s\n", o.Positioning)
	}
	if o.KeyMessage != "" {
		fmt.Fprintf(&b, "核心信息: %s\n", o.KeyMessage)
	}
	o.WalkAll(func(sec *OutlineSection) bool {
		depth := strings.Count(sec.ID, ".")
		b.WriteString(strings.Repeat("  ", depth))
		fmt.Fprintf(&b, "- %s", sec.Title)
		if len(sec.Points) > 0 {
			fmt.Fprintf(&b, " (%d 要点)", len(sec.Points))
		}
		fmt.Fprintln(&b)
		return true
	})
	return b.String()
}

// diffSummary computes a deterministic structural diff description.
func diffSummary(before, after *StrategyOutline) string {
	bm := sectionMap(before)
	am := sectionMap(after)
	added, removed, expanded := 0, 0, 0
	for title := range am {
		if _, ok := bm[title]; !ok {
			added++
		} else if len(am[title]) > len(bm[title]) {
			expanded++
		}
	}
	for title := range bm {
		if _, ok := am[title]; !ok {
			removed++
		}
	}
	return fmt.Sprintf("结构变化: 章节 %d→%d (+%d/-%d), 扩充 %d 节",
		len(bm), len(am), added, removed, expanded)
}

// sectionMap maps lowercased title → point count.
func sectionMap(o *StrategyOutline) map[string][]string {
	m := map[string][]string{}
	o.WalkAll(func(sec *OutlineSection) bool {
		key := strings.ToLower(strings.TrimSpace(sec.Title))
		if pts, ok := m[key]; !ok || len(sec.Points) > len(pts) {
			m[key] = sec.Points
		}
		return true
	})
	return m
}
