// Outline generation: audience-specific strategy outlines seeded by
// the deterministic skeleton, enriched by research evidence and
// insights, and written by the LLM when available.
//
// With LLM: the skeleton structure is part of the prompt so the output
// stays inside the five-module spine (市场/竞品/品牌本体/竞争优势/
// 传播) plus audience modules. Parse failures degrade to the skeleton.
package medplan

import (
	"context"
	"encoding/json"
	"fmt"
	"sort"
	"strings"

	"github.com/veawho/via54Medit/internal/foundation"
)

// Generator produces audience-specific strategy outlines.
type Generator struct {
	// LLM is optional; nil produces the deterministic skeleton.
	LLM foundation.LLMProvider
	// ProviderLabel is recorded in GeneratedBy (e.g. "llm:glm").
	ProviderLabel string
}

// Generate builds the outline for one audience.
func (g *Generator) Generate(ctx context.Context, brief *Brief, d *ResearchDossier, ins *Insights, a Audience) (*StrategyOutline, error) {
	if brief == nil {
		return nil, fmt.Errorf("medplan: outline: nil brief")
	}
	base := Skeleton(brief.Project, a)
	if d != nil {
		base.AttachEvidence(d.Items)
	}
	if ins != nil {
		for _, x := range ins.Insights {
			if x.Advantage {
				base.InsightIDs = append(base.InsightIDs, x.ID)
			}
		}
	}
	if g.LLM == nil {
		return base, nil
	}
	o, err := g.generateWithLLM(ctx, brief, d, ins, a, base)
	if err != nil {
		// Degrade to skeleton; callers surface the error text.
		return base, fmt.Errorf("outline llm (fallback to template): %w", err)
	}
	return o, nil
}

// llmSection is the wire format the model is asked to emit.
type llmSection struct {
	Title    string       `json:"title"`
	Points   []string     `json:"points"`
	Evidence []string     `json:"evidence"`
	Children []llmSection `json:"children"`
}

func (g *Generator) generateWithLLM(ctx context.Context, brief *Brief, d *ResearchDossier, ins *Insights, a Audience, base *StrategyOutline) (*StrategyOutline, error) {
	p := ProfileFor(a)
	sys := "你是资深医学策略总监, 为医药品牌撰写策略方案大纲。输出必须是纯 JSON, 不要 markdown 代码块。" +
		"遵守中国大陆合规边界: 不使用绝对化用语, 不作疗效保证, 处方药不面向公众促销。"
	user := fmt.Sprintf(`# 任务
%s

# 产品
%s (企业: %s, 机制: %s, 适应症: %s, 阶段: %s, 分类: %s)
已知差异点: %s
已知竞品: %s

# 目标受众
%s — 基调: %s; 内容侧重: %s; 证据偏好: %s

# 大纲骨架 (必须保留五大核心模块与受众模块的顺序, 可增加子节点与要点)
%s

# 调研材料摘要
%s

# 已提炼观点
%s

# 输出要求
1. sections: 沿用骨架顺序并深化, 每节 3-5 个要点, 需要处增加 children 子节
2. evidence: 引用材料 ID (如 ["L001","P002"]), 只允许引用上面出现过的 ID
3. positioning: 一句话品牌定位陈述 (合规: 事实+差异, 无极限词)
4. key_message: 一条面向该受众的核心信息钥匙
5. 所有观点必须有材料支撑或明确标注为策略假设

输出 JSON: {"positioning":"...","key_message":"...","sections":[{"title":"...","points":["..."],"evidence":["L001"],"children":[...]}]}`,
		brief.Instruction,
		brief.Product.Name, brief.Product.Company, brief.Product.MOA,
		strings.Join(brief.Product.Indications, "、"),
		brief.Product.Stage, brief.Product.RxStatus,
		strings.Join(brief.Product.Differentiators, "、"),
		strings.Join(brief.Product.Competitors, "、"),
		a.StringCN(), p.Tone, p.Focus, p.Evidence,
		skeletonDigest(base),
		dossierDigest(d, 8),
		insightsDigest(ins, 8),
	)
	raw, err := g.LLM.Complete(ctx, sys, user)
	if err != nil {
		return nil, fmt.Errorf("complete: %w", err)
	}
	var got struct {
		Positioning string       `json:"positioning"`
		KeyMessage  string       `json:"key_message"`
		Sections    []llmSection `json:"sections"`
	}
	if err := json.Unmarshal([]byte(extractJSON(raw)), &got); err != nil {
		return nil, fmt.Errorf("parse: %w", err)
	}
	if len(got.Sections) == 0 {
		return nil, fmt.Errorf("model returned 0 sections")
	}

	label := g.ProviderLabel
	if label == "" {
		label = "llm"
	}
	o := &StrategyOutline{
		Project:     brief.Project,
		Audience:    a,
		Version:     1,
		Positioning: strings.TrimSpace(got.Positioning),
		KeyMessage:  strings.TrimSpace(got.KeyMessage),
		GeneratedBy: label,
		CreatedAt:   nowUTC(),
		UpdatedAt:   nowUTC(),
	}
	validIDs := map[string]bool{}
	if d != nil {
		for _, it := range d.Items {
			validIDs[it.ID] = true
		}
	}
	o.Sections = convertSections(got.Sections, validIDs)
	if ins != nil {
		for _, x := range ins.Insights {
			if x.Advantage {
				o.InsightIDs = append(o.InsightIDs, x.ID)
			}
		}
		sort.Strings(o.InsightIDs)
	}
	return o, nil
}

// convertSections maps the wire format to OutlineSection, assigning
// deterministic IDs ("1", "1.1", ...) and filtering evidence IDs.
func convertSections(ss []llmSection, validIDs map[string]bool) []OutlineSection {
	out := make([]OutlineSection, 0, len(ss))
	for i, s := range ss {
		if strings.TrimSpace(s.Title) == "" {
			continue
		}
		sec := OutlineSection{
			ID:     fmt.Sprintf("%d", i+1),
			Title:  strings.TrimSpace(s.Title),
			Points: nonEmpty(s.Points),
		}
		for _, id := range s.Evidence {
			if validIDs[id] {
				sec.Evidence = append(sec.Evidence, id)
			}
		}
		sec.Children = convertChildren(s.Children, sec.ID, validIDs)
		out = append(out, sec)
	}
	return out
}

func convertChildren(ss []llmSection, parent string, validIDs map[string]bool) []OutlineSection {
	out := make([]OutlineSection, 0, len(ss))
	for i, s := range ss {
		if strings.TrimSpace(s.Title) == "" {
			continue
		}
		sec := OutlineSection{
			ID:     fmt.Sprintf("%s.%d", parent, i+1),
			Title:  strings.TrimSpace(s.Title),
			Points: nonEmpty(s.Points),
		}
		for _, id := range s.Evidence {
			if validIDs[id] {
				sec.Evidence = append(sec.Evidence, id)
			}
		}
		sec.Children = convertChildren(s.Children, sec.ID, validIDs)
		out = append(out, sec)
	}
	return out
}

// skeletonDigest renders the skeleton as a compact prompt fragment.
func skeletonDigest(o *StrategyOutline) string {
	var b strings.Builder
	o.WalkAll(func(sec *OutlineSection) bool {
		depth := strings.Count(sec.ID, ".")
		b.WriteString(strings.Repeat("  ", depth))
		fmt.Fprintf(&b, "- %s\n", sec.Title)
		return true
	})
	return b.String()
}

// insightsDigest renders insights as a compact prompt fragment.
func insightsDigest(ins *Insights, n int) string {
	if ins == nil {
		return "(无)"
	}
	var b strings.Builder
	for i, x := range ins.Insights {
		if i >= n {
			break
		}
		fmt.Fprintf(&b, "- [%s|%s] %s\n", x.ID, x.Strength, x.Claim)
	}
	return b.String()
}
