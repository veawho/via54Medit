// Research orchestration: builds a deterministic query matrix from the
// Brief, runs the literature dimension through the router (reusing
// via54Medit's multi-source fan-out), and synthesizes the news /
// report / policy / competitor dimensions via LLM when available.
//
// Every synthesized item is flagged NeedsVerification so downstream
// humans know which evidence is retrievable and which is model output.
package medplan

import (
	"context"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/veawho/via54Medit/internal/foundation"
	"github.com/veawho/via54Medit/pkg/types"
)

// LiteratureSearcher abstracts the multi-source literature fan-out so
// tests can run without network access.
type LiteratureSearcher interface {
	// SearchLiterature runs one query and returns up to max citations.
	SearchLiterature(ctx context.Context, query string, max int) ([]types.Citation, error)
}

// Researcher coordinates the five research dimensions.
type Researcher struct {
	// Searcher powers the literature dimension; nil skips it.
	Searcher LiteratureSearcher
	// LLM powers the synthesized dimensions and the cross-dimension
	// notes; nil leaves those dimensions empty (queries still logged).
	LLM foundation.LLMProvider
	// MaxPerQuery caps citations kept per literature query (default 8).
	MaxPerQuery int
}

// itemPrefix maps a dimension to its deterministic ID prefix.
var itemPrefix = map[ResearchDimension]string{
	DimLiterature: "L",
	DimNews:       "N",
	DimReport:     "R",
	DimPolicy:     "P",
	DimCompetitor: "C",
}

// Research executes the query matrix for a brief. It never fails
// wholesale: per-query errors are recorded on the dossier.
func (r *Researcher) Research(ctx context.Context, brief *Brief) (*ResearchDossier, error) {
	if brief == nil {
		return nil, fmt.Errorf("medplan: research: nil brief")
	}
	start := nowUTC()
	d := &ResearchDossier{
		Project:  brief.Project,
		Queries:  nil,
		Items:    nil,
		Duration: 0,
	}
	maxPerQuery := r.MaxPerQuery
	if maxPerQuery <= 0 {
		maxPerQuery = 8
	}
	seen := map[string]bool{} // cross-query dedupe (pmid > doi > title)

	queries := buildQueryMatrix(brief)
	counters := map[ResearchDimension]int{}

	for dim, qs := range queries {
		for _, q := range qs {
			rq := ResearchQuery{Dimension: dim, Query: q.Query}
			switch {
			case dim == DimLiterature:
				if r.Searcher == nil {
					rq.Error = "no literature searcher configured"
					break
				}
				cites, err := r.Searcher.SearchLiterature(ctx, q.Query, maxPerQuery)
				if err != nil {
					rq.Error = err.Error()
					break
				}
				kept := 0
				for i := range cites {
					c := cites[i]
					key := citationKey(&c)
					if seen[key] {
						continue
					}
					seen[key] = true
					kept++
					counters[dim]++
					d.Items = append(d.Items, citationItem(dim, counters[dim], &c))
				}
				rq.Results = kept
			default:
				if r.LLM == nil {
					rq.Error = "no LLM configured — dimension skipped (use ingest for manual items)"
					break
				}
				items, err := r.synthesize(ctx, brief, dim, q)
				if err != nil {
					rq.Error = err.Error()
					break
				}
				rq.Results = len(items)
				for _, it := range items {
					counters[dim]++
					it.ID = fmt.Sprintf("%s%03d", itemPrefix[dim], counters[dim])
					it.Dimension = dim
					it.Source = "llm"
					it.NeedsVerification = true
					d.Items = append(d.Items, it)
				}
			}
			d.Queries = append(d.Queries, rq)
		}
	}

	if r.LLM != nil && len(d.Items) > 0 {
		if notes, err := r.synthesizeNotes(ctx, brief, d); err == nil {
			d.Notes = notes
		}
	}
	sortDossier(d)
	d.Duration = time.Since(start)
	d.CreatedAt = nowUTC()
	return d, nil
}

// dimensionQuery is one entry of the query matrix.
type dimensionQuery struct {
	Query    string
	Audience string // "" = audience-agnostic
}

// buildQueryMatrix derives research queries from the brief. Deterministic:
// same brief in, same matrix out. Order: AllDimensions order, then query order.
func buildQueryMatrix(brief *Brief) map[ResearchDimension][]dimensionQuery {
	m := map[ResearchDimension][]dimensionQuery{}
	name := strings.TrimSpace(brief.Product.Name)
	inds := nonEmpty(brief.Product.Indications)
	topInd := firstOr(inds, "")
	ind := strings.TrimSpace(topInd)

	// Literature: product-centric + disease-centric queries.
	lit := []dimensionQuery{}
	if name != "" {
		lit = append(lit,
			dimensionQuery{Query: joinNonEmpty(" ", name, ind, "clinical trial")},
			dimensionQuery{Query: joinNonEmpty(" ", name, "safety efficacy")},
		)
		if brief.Product.MOA != "" {
			lit = append(lit, dimensionQuery{Query: joinNonEmpty(" ", name, brief.Product.MOA)})
		}
	}
	if ind != "" {
		lit = append(lit, dimensionQuery{Query: ind + " treatment guideline"})
	}
	for _, a := range brief.Audiences {
		p := ProfileFor(a)
		for _, term := range p.ResearchTerms {
			if ind != "" {
				lit = append(lit, dimensionQuery{
					Query:    joinNonEmpty(" ", ind, term),
					Audience: string(a),
				})
			}
		}
	}
	m[DimLiterature] = lit

	// News: product + company momentum.
	news := []dimensionQuery{}
	if name != "" {
		news = append(news, dimensionQuery{Query: name + " 获批 上市 进展"})
	}
	if brief.Product.Company != "" {
		news = append(news, dimensionQuery{Query: brief.Product.Company + " " + firstOr(nonEmpty([]string{name, ind}), "") + " 动态"})
	}
	m[DimNews] = news

	// Reports: indication market landscape.
	if ind != "" {
		m[DimReport] = []dimensionQuery{{Query: ind + " 市场规模 流行病学 研报"}}
	} else if name != "" {
		m[DimReport] = []dimensionQuery{{Query: name + " 市场 竞争格局"}}
	}

	// Policy: access & regulation.
	pol := []dimensionQuery{}
	if ind != "" {
		pol = append(pol, dimensionQuery{Query: ind + " 医保 支付 政策"})
	}
	pol = append(pol, dimensionQuery{Query: "药品审评审批 医保谈判 最新政策"})
	m[DimPolicy] = pol

	// Competitors: one query per known competitor.
	comps := nonEmpty(brief.Product.Competitors)
	var compQs []dimensionQuery
	for _, c := range comps {
		compQs = append(compQs, dimensionQuery{Query: strings.TrimSpace(c) + " " + ind + " 临床 进展"})
	}
	if len(compQs) == 0 && name != "" {
		compQs = append(compQs, dimensionQuery{Query: name + " 同类 竞品 对比"})
	}
	m[DimCompetitor] = compQs

	// Drop empty dimensions so the executor loop stays clean.
	for k, v := range m {
		if len(v) == 0 {
			delete(m, k)
		}
	}
	return m
}

// citationKey builds the cross-query dedupe key for a citation
// (pmid > doi > normalized title).
func citationKey(c *types.Citation) string {
	if c.PMID != "" {
		return "pmid:" + c.PMID
	}
	if c.DOI != "" {
		return "doi:" + c.DOI
	}
	return "title:" + strings.ToLower(strings.Join(strings.Fields(c.Title), " "))
}

// citationItem converts a router citation into a research item.
func citationItem(dim ResearchDimension, n int, c *types.Citation) ResearchItem {
	id := fmt.Sprintf("%s%03d", itemPrefix[dim], n)
	sum := c.TLDR
	if sum == "" && c.Abstract != "" {
		sum = truncateRunes(c.Abstract, 240)
	}
	url := c.DOI
	if url != "" {
		url = "https://doi.org/" + url
	}
	return ResearchItem{
		ID:        id,
		Dimension: dim,
		Title:     c.Title,
		Summary:   sum,
		URL:       url,
		Source:    strings.Join(c.SourceOrigin, ","),
		Published: fmt.Sprintf("%d", c.Year),
		Citation:  c,
	}
}

// synthesize asks the LLM for research items of one non-literature
// dimension. Output is JSON; ids/dimension are overwritten by caller.
func (r *Researcher) synthesize(ctx context.Context, brief *Brief, dim ResearchDimension, q dimensionQuery) ([]ResearchItem, error) {
	sys := "你是医药行业研究分析师。基于你的知识给出与查询相关的信息点, 只输出 JSON。" +
		"每条信息必须注明信息可能过时的风险。不得编造具体数字精确的来源链接。"
	user := fmt.Sprintf(
		"产品: %s\n适应症: %s\n调研维度: %s\n查询: %s\n\n"+
			"输出 JSON: {\"items\":[{\"title\":\"...\",\"summary\":\"与该产品策划的关联价值\",\"published\":\"大致时间, 如 2025\"}]} (最多 4 条, 按 relevance 排序)",
		brief.Product.Name,
		strings.Join(brief.Product.Indications, "、"),
		dim.StringCN(),
		q.Query,
	)
	raw, err := r.LLM.Complete(ctx, sys, user)
	if err != nil {
		return nil, fmt.Errorf("synthesize %s: %w", dim, err)
	}
	var got struct {
		Items []struct {
			Title     string `json:"title"`
			Summary   string `json:"summary"`
			Published string `json:"published"`
		} `json:"items"`
	}
	if err := json.Unmarshal([]byte(extractJSON(raw)), &got); err != nil {
		return nil, fmt.Errorf("synthesize %s: parse: %w", dim, err)
	}
	out := make([]ResearchItem, 0, len(got.Items))
	for _, it := range got.Items {
		if strings.TrimSpace(it.Title) == "" {
			continue
		}
		out = append(out, ResearchItem{
			Title:     strings.TrimSpace(it.Title),
			Summary:   strings.TrimSpace(it.Summary),
			Published: strings.TrimSpace(it.Published),
		})
	}
	return out, nil
}

// synthesizeNotes produces the cross-dimension synthesis paragraph.
func (r *Researcher) synthesizeNotes(ctx context.Context, brief *Brief, d *ResearchDossier) (string, error) {
	sys := "你是医学策略顾问。基于给定调研材料写一段 300 字以内的综合分析, 指出对本次策划最关键的 3 个发现。只输出正文。"
	user := fmt.Sprintf("任务: %s\n产品: %s\n\n调研材料:\n%s",
		brief.Instruction, brief.Product.Name, dossierDigest(d, 12))
	raw, err := r.LLM.Complete(ctx, sys, user)
	if err != nil {
		return "", fmt.Errorf("notes: %w", err)
	}
	return strings.TrimSpace(raw), nil
}

// dossierDigest renders a compact per-dimension digest of the dossier.
func dossierDigest(d *ResearchDossier, perDim int) string {
	if d == nil || len(d.Items) == 0 {
		return "(无调研材料)"
	}
	var b strings.Builder
	for _, dim := range d.Dimensions() {
		fmt.Fprintf(&b, "## %s\n", dim.StringCN())
		for i, it := range d.ItemsByDimension(dim) {
			if i >= perDim {
				break
			}
			fmt.Fprintf(&b, "- [%s] %s", it.ID, it.Title)
			if it.Summary != "" {
				fmt.Fprintf(&b, " — %s", truncateRunes(it.Summary, 120))
			}
			fmt.Fprintln(&b)
		}
	}
	return b.String()
}

// IngestItems appends manually supplied items (news/report/policy
// clippings the operator collected), re-numbering by dimension.
func IngestItems(d *ResearchDossier, items []ResearchItem) {
	counters := map[ResearchDimension]int{}
	for _, it := range d.Items {
		counters[it.Dimension]++
	}
	for _, it := range items {
		if it.Dimension == "" {
			it.Dimension = DimNews
		}
		counters[it.Dimension]++
		it.ID = fmt.Sprintf("%s%03d", itemPrefix[it.Dimension], counters[it.Dimension])
		d.Items = append(d.Items, it)
	}
	sortDossier(d)
}

// sortDossier orders items deterministically: dimension order, then ID.
func sortDossier(d *ResearchDossier) {
	rank := map[ResearchDimension]int{}
	for i, dim := range AllDimensions() {
		rank[dim] = i
	}
	sort.SliceStable(d.Items, func(i, j int) bool {
		if d.Items[i].Dimension != d.Items[j].Dimension {
			return rank[d.Items[i].Dimension] < rank[d.Items[j].Dimension]
		}
		return d.Items[i].ID < d.Items[j].ID
	})
}

// --- small slice helpers (kept local to avoid a util package) ---

func nonEmpty(ss []string) []string {
	out := make([]string, 0, len(ss))
	for _, s := range ss {
		if strings.TrimSpace(s) != "" {
			out = append(out, strings.TrimSpace(s))
		}
	}
	return out
}

func firstOr(ss []string, def string) string {
	if len(ss) == 0 {
		return def
	}
	return ss[0]
}

func joinNonEmpty(sep string, ss ...string) string {
	parts := make([]string, 0, len(ss))
	for _, s := range ss {
		if strings.TrimSpace(s) != "" {
			parts = append(parts, strings.TrimSpace(s))
		}
	}
	return strings.Join(parts, sep)
}
