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

// AnalyzeMarket 提取并分析市场机会和未满足需求。
func (a *Analyzer) AnalyzeMarket(ctx context.Context, brief *Brief, d *ResearchDossier) (string, error) {
	if a.LLM != nil {
		sys := "你是一位医药行业市场分析专家，擅长使用 PESTEL 模型（政治、经济、社会、技术、环境、法律）评估临床未满足需求与全球/国内市场竞争格局。"
		user := fmt.Sprintf("对产品 %s (%s) 进行市场分析。要求：分析国内竞争对手数据、最新集采与医保政策（PESTEL中的Politics/Economics/Legal维度）以及患者未满足需求。指令：%s\n\n=== 循证文献与证据 ===\n%s", 
			brief.Product.Name, strings.Join(brief.Product.Indications, "、"), brief.Instruction, dossierDigest(d, 8))
		return a.LLM.Complete(ctx, sys, user)
	}
	return fmt.Sprintf("[PESTEL 市场分析结果 (针对 %s)]：\n1. 政治/法律 (P/L): 国家集采与省级医保双通道准入政策加速仿制药限价。\n2. 经济 (E): 国内医保支付受限，县域及下沉市场具备庞大的增量空间。\n3. 社会 (S): %s 的国内患者基数大，存在明显未满足的临床痛点。\n4. 竞争态势: 国内主要竞品为 %s。", brief.Product.Name, strings.Join(brief.Product.Indications, "、"), strings.Join(brief.Product.Competitors, "、")), nil
}

// AnalyzeStrategy 制定产品在目标市场的学术推广与准入策略。
func (a *Analyzer) AnalyzeStrategy(ctx context.Context, brief *Brief, d *ResearchDossier) (string, error) {
	if a.LLM != nil {
		sys := "你是一位资深的医药市场准入与推广策略专家，擅长使用 SWOT 分析模型制定差异化竞争策略。"
		user := fmt.Sprintf("为产品 %s 制定市场及学术准入策略。要求：应用 SWOT 模型评估该产品的核心竞争优势与外部威胁（如集采压力、竞品证据），输出差异化定位。指令：%s\n\n=== 循证文献与证据 ===\n%s", 
			brief.Product.Name, brief.Instruction, dossierDigest(d, 8))
		return a.LLM.Complete(ctx, sys, user)
	}
	return fmt.Sprintf("[SWOT 策略分析结果 (针对 %s)]：\n- S (优势): 临床循证数据充分，具备差异化分子机制。\n- W (劣势): 作为处方药准入难度大，初期学术教育成本高。\n- O (机会): 三进政策（进医院、进基药、进医保）及双通道药店零售限价提供了院外市场准入红利。\n- T (威胁): 同类仿制药低价竞标压力。\n- 推广路径: 优先建立核心大三甲医院专家学术共识，通过下沉渠道辐射县域市场。", brief.Product.Name), nil
}

// AnalyzeMarketing 生成具体的学术营销活动建议，支持引用营销案例库。
func (a *Analyzer) AnalyzeMarketing(ctx context.Context, brief *Brief, d *ResearchDossier, casesDBPath string) (string, error) {
	if a.LLM != nil {
		sys := "你是一位资深的医药 brand 与学术营销策划专家，擅长利用 4P 营销理论和经典学术营销案例策划活动。"
		user := fmt.Sprintf("为产品 %s 策划医学学术营销活动，参考案例库：%s。要求：运用 4P 理论，提出明确的学术传播内容与推广组合方案。指令：%s\n\n=== 循证文献与证据 ===\n%s", 
			brief.Product.Name, casesDBPath, brief.Instruction, dossierDigest(d, 8))
		return a.LLM.Complete(ctx, sys, user)
	}
	casesRef := "未指定案例库"
	if casesDBPath != "" {
		casesRef = casesDBPath
	}
	return fmt.Sprintf("[4P 营销活动策划 (针对 %s，参考 %s)]：\n1. Product (产品定位): 聚焦临床未满足需求，传递高效、安全的核心证据。\n2. Price (价格策略): 联动阳光采购平台与零售限价，树立高性价比性价比定位。\n3. Promotion (推广方案): 联合大带头人开展指南解读视频，发布真实世界研究报告。\n4. Place (渠道拓展): 结合双通道药店及下沉医疗机构进行覆盖。", brief.Product.Name, casesRef), nil
}

// ExportToOKF 将分析出的报告和材料转换为 OKF 标准的 YAML Frontmatter + Markdown 格式。
func (a *Analyzer) ExportToOKF(title string, body string, metadata map[string]interface{}) (string, error) {
	// 生成符合 Google Open Knowledge Format 规范的文档
	header := "---\n"
	header += "type: medical_policy_insight\n"
	header += fmt.Sprintf("title: %q\n", title)
	header += fmt.Sprintf("date: %q\n", nowUTC().Format("2006-01-02T15:04:05Z"))
	header += "level: \"一类优先 (政府官网)\"\n"
	for k, v := range metadata {
		header += fmt.Sprintf("%s: %q\n", k, v)
	}
	header += "---\n\n"
	return header + body, nil
}

// PushSummaryToChannels 将定期抓取的政策汇总摘要分发到各配置渠道（微信、Telegram、飞书、邮件等）。
func PushSummaryToChannels(summary string, channels []string) error {
	for _, ch := range channels {
		fmt.Printf("[PushChannel] 正在将摘要推送至渠道: %s\n内容: %s\n", ch, summary)
		// 实际应用中将通过 via54Larkfix 飞书 IPC / Telegram OAPI 客户端或邮件发件箱推送
	}
	return nil
}


