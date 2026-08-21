// Analysis stage: distills the research dossier into defensible
// insights and a SWOT — the raw material of competitive-advantage
// packaging. LLM-driven when available; deterministic heuristics
// otherwise (evidence anchors from the literature dimension).
package medplan

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/veawho/via54Medit/internal/foundation"
)

// Analyzer extracts insights from a dossier.
type Analyzer struct {
	// LLM is optional; nil falls back to deterministic heuristics.
	LLM foundation.LLMProvider
}

// Analyze runs the insight extraction for a brief.
func (a *Analyzer) Analyze(ctx context.Context, brief *Brief, d *ResearchDossier) (*Insights, error) {
	if brief == nil || d == nil {
		return nil, fmt.Errorf("medplan: analyze: nil brief or dossier")
	}
	if a.LLM != nil {
		if ins, err := a.analyzeWithLLM(ctx, brief, d); err == nil {
			return ins, nil
		}
		// LLM failure degrades to heuristics below.
	}
	return heuristicInsights(brief, d), nil
}

// heuristicInsights builds insights deterministically: literature
// anchors become evidence insights; brief differentiators become
// advantage insights; competitors become threats.
func heuristicInsights(brief *Brief, d *ResearchDossier) *Insights {
	ins := &Insights{Project: brief.Project, CreatedAt: nowUTC()}
	n := 0
	// Literature anchors (max 4, strongest first = most cited).
	lits := d.ItemsByDimension(DimLiterature)
	ranked := make([]ResearchItem, len(lits))
	copy(ranked, lits)
	for i := 1; i < len(ranked); i++ { // stable insert sort by Citation.CitedBy desc
		for j := i; j > 0 && citeBy(ranked[j]) > citeBy(ranked[j-1]); j-- {
			ranked[j], ranked[j-1] = ranked[j-1], ranked[j]
		}
	}
	for i, it := range ranked {
		if i >= 4 {
			break
		}
		n++
		ins.Insights = append(ins.Insights, Insight{
			ID:        fmt.Sprintf("I%d", n),
			Claim:     fmt.Sprintf("关键证据: %s", truncateRunes(it.Title, 80)),
			Dimension: DimLiterature,
			ItemIDs:   []string{it.ID},
			Strength:  "moderate",
		})
	}
	// Differentiators from the brief → advantage insights.
	for _, diff := range nonEmpty(brief.Product.Differentiators) {
		n++
		ins.Insights = append(ins.Insights, Insight{
			ID:        fmt.Sprintf("I%d", n),
			Claim:     fmt.Sprintf("差异化优势: %s", diff),
			Dimension: DimCompetitor,
			Strength:  "moderate",
			Advantage: true,
		})
	}
	// SWOT from brief + dossier.
	for _, diff := range nonEmpty(brief.Product.Differentiators) {
		ins.SWOT.Strengths = append(ins.SWOT.Strengths, diff)
	}
	if len(lits) == 0 {
		ins.SWOT.Weaknesses = append(ins.SWOT.Weaknesses, "可检索的循证文献不足, 证据链薄弱")
	}
	for _, c := range nonEmpty(brief.Product.Competitors) {
		ins.SWOT.Threats = append(ins.SWOT.Threats, fmt.Sprintf("竞品 %s 的市场与证据压力", c))
	}
	ins.SWOT.Opportunities = append(ins.SWOT.Opportunities,
		"结合最新政策与临床未满足需求进行差异化定位 (见调研材料)")
	return ins
}

func citeBy(it ResearchItem) int {
	if it.Citation != nil {
		return it.Citation.CitedBy
	}
	return 0
}

// analyzeWithLLM asks the model for structured insights + SWOT.
func (a *Analyzer) analyzeWithLLM(ctx context.Context, brief *Brief, d *ResearchDossier) (*Insights, error) {
	sys := "你是医学策略专家, 擅长从调研材料中提炼可辩护的品牌观点。只输出 JSON。"
	user := fmt.Sprintf(`任务: %s
产品: %s (机制: %s, 适应症: %s, 已知差异点: %s, 竞品: %s)

=== 调研材料 ===
%s

=== 要求 ===
1. insights: 3-8 条核心观点, 优先挖掘可支撑竞争优势的差异化点
2. 每条 claim 必须能落到 item_ids 中的材料, 不得凭空发挥
3. strength: strong=多项一致证据 / moderate=单一或间接证据 / weak=推测
4. advantage=true 表示该观点可直接包装为竞争优势
5. swot: 四象限各 2-4 条

输出 JSON: {"insights":[{"claim":"...","dimension":"literature|news|report|policy|competitor","item_ids":["L001"],"strength":"strong|moderate|weak","advantage":true}],"swot":{"strengths":[],"weaknesses":[],"opportunities":[],"threats":[]}}`,
		brief.Instruction,
		brief.Product.Name, brief.Product.MOA,
		strings.Join(brief.Product.Indications, "、"),
		strings.Join(brief.Product.Differentiators, "、"),
		strings.Join(brief.Product.Competitors, "、"),
		dossierDigest(d, 8),
	)
	raw, err := a.LLM.Complete(ctx, sys, user)
	if err != nil {
		return nil, fmt.Errorf("analyze: %w", err)
	}
	var got struct {
		Insights []struct {
			Claim     string   `json:"claim"`
			Dimension string   `json:"dimension"`
			ItemIDs   []string `json:"item_ids"`
			Strength  string   `json:"strength"`
			Advantage bool     `json:"advantage"`
		} `json:"insights"`
		SWOT struct {
			Strengths     []string `json:"strengths"`
			Weaknesses    []string `json:"weaknesses"`
			Opportunities []string `json:"opportunities"`
			Threats       []string `json:"threats"`
		} `json:"swot"`
	}
	if err := json.Unmarshal([]byte(extractJSON(raw)), &got); err != nil {
		return nil, fmt.Errorf("analyze: parse: %w", err)
	}
	if len(got.Insights) == 0 {
		return nil, fmt.Errorf("analyze: model returned 0 insights")
	}
	validIDs := map[string]bool{}
	for _, it := range d.Items {
		validIDs[it.ID] = true
	}
	out := &Insights{Project: brief.Project, CreatedAt: nowUTC()}
	for i, x := range got.Insights {
		if strings.TrimSpace(x.Claim) == "" {
			continue
		}
		var ids []string
		for _, id := range x.ItemIDs {
			if validIDs[id] {
				ids = append(ids, id)
			}
		}
		dim := ResearchDimension(x.Dimension)
		switch dim {
		case DimLiterature, DimNews, DimReport, DimPolicy, DimCompetitor:
		default:
			dim = DimLiterature
		}
		strength := x.Strength
		switch strength {
		case "strong", "moderate", "weak":
		default:
			strength = "moderate"
		}
		out.Insights = append(out.Insights, Insight{
			ID:        fmt.Sprintf("I%d", i+1),
			Claim:     strings.TrimSpace(x.Claim),
			Dimension: dim,
			ItemIDs:   ids,
			Strength:  strength,
			Advantage: x.Advantage,
		})
	}
	out.SWOT = SWOT{
		Strengths:     nonEmpty(got.SWOT.Strengths),
		Weaknesses:    nonEmpty(got.SWOT.Weaknesses),
		Opportunities: nonEmpty(got.SWOT.Opportunities),
		Threats:       nonEmpty(got.SWOT.Threats),
	}
	if len(out.Insights) == 0 {
		return nil, fmt.Errorf("analyze: no valid insights after validation")
	}
	return out, nil
}
