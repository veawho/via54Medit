// Package commands — medplan subcommand (医学策划方案).
//
// medit medplan new|run|research|outline|optimize|compliance|show|list
//
// Workflow: new (brief) → run (research + analyze + outline×N +
// compliance, end-to-end) — or stage-by-stage via research / outline /
// optimize / compliance. Projects persist under ~/.medit/medplan/<name>/.
package commands

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/veawho/via54Medit/internal/foundation"
	"github.com/veawho/via54Medit/internal/medplan"
	"github.com/veawho/via54Medit/internal/router"
	"github.com/veawho/via54Medit/internal/source"
	"github.com/veawho/via54Medit/pkg/types"
)

// --- parent ---

var medplanCmd = &cobra.Command{
	Use:   "medplan",
	Short: "医学策划方案: 调研 → 观点提炼 → 分受众大纲 → 语义优化 → 合规验证",
	Long: `medplan turns an instruction + product facts into audience-specific
medical strategy proposal outlines (HCP / patient / industry), backed
by via54Medit's literature research and verified against mainland-China
medical compliance rules (广告法/药品管理法/医疗广告管理办法/RDPAC).

Pipeline: new → run (research → analyze → outline×N → compliance)
Stages can also run individually: research / outline / optimize /
compliance. Storage: ~/.medit/medplan/<project>/`,
}

// --- shared flags ---

var (
	mpStore           *medplan.ProjectStore
	mpProject         string
	mpInstruction     string
	mpProductName     string
	mpCompany         string
	mpModality        string
	mpMOA             string
	mpIndications     string
	mpStage           string
	mpRxStatus        string
	mpDifferentiators string
	mpCompetitors     string
	mpConstraint      string
	mpAudiences       string
	mpJSON            bool
	mpMaxResults      int
	mpSources         string
	mpSkipResearch    bool
	mpSkipCompliance  bool
	mpOptimizeInstr   string
	mpExpandSection   string
	mpIngestFile      string
	mpBriefFile       string
)

func init() {
	medplanCmd.PersistentFlags().StringVar(&mpProject, "project", "", "Project name (default: derived from product name)")
	medplanCmd.PersistentFlags().StringVar(&mpProductName, "name", "", "Product name (产品通用名/商品名)")
	medplanCmd.PersistentFlags().StringVar(&mpCompany, "company", "", "产品持有企业")
	medplanCmd.PersistentFlags().StringVar(&mpModality, "modality", "", "产品形态: 药品/器械/疫苗/数字医疗")
	medplanCmd.PersistentFlags().StringVar(&mpMOA, "moa", "", "作用机制 (MOA)")
	medplanCmd.PersistentFlags().StringVar(&mpIndications, "indication", "", "适应症 (逗号分隔)")
	medplanCmd.PersistentFlags().StringVar(&mpStage, "stage", "", "研发/上市阶段: phase-iii/上市/医保谈判...")
	medplanCmd.PersistentFlags().StringVar(&mpRxStatus, "rx-status", "", "rx|otc|device (处方药触发最严合规)")
	medplanCmd.PersistentFlags().StringVar(&mpDifferentiators, "differentiator", "", "已知差异点 (逗号分隔)")
	medplanCmd.PersistentFlags().StringVar(&mpCompetitors, "competitor", "", "竞品 (逗号分隔)")

	medplanCmd.AddCommand(medplanNewCmd)
	medplanCmd.AddCommand(medplanRunCmd)
	medplanCmd.AddCommand(medplanResearchCmd)
	medplanCmd.AddCommand(medplanOutlineCmd)
	medplanCmd.AddCommand(medplanOptimizeCmd)
	medplanCmd.AddCommand(medplanComplianceCmd)
	medplanCmd.AddCommand(medplanShowCmd)
	medplanCmd.AddCommand(medplanListCmd)
}

// --- helpers ---

func mpStoreOrDie() (*medplan.ProjectStore, error) {
	if mpStore != nil {
		return mpStore, nil
	}
	s, err := medplan.NewProjectStore()
	if err != nil {
		return nil, err
	}
	mpStore = s
	return s, nil
}

// buildBriefFromFlags assembles a Brief from CLI flags (or a JSON file).
func buildBriefFromFlags() (*medplan.Brief, error) {
	if mpBriefFile != "" {
		data, err := os.ReadFile(mpBriefFile)
		if err != nil {
			return nil, fmt.Errorf("read brief file: %w", err)
		}
		var b medplan.Brief
		if err := json.Unmarshal(data, &b); err != nil {
			return nil, fmt.Errorf("parse brief file: %w", err)
		}
		return &b, nil
	}
	if mpInstruction == "" || mpProductName == "" {
		return nil, fmt.Errorf("--instruction and --name are required (or pass --brief-file <brief.json>)")
	}
	b := &medplan.Brief{
		Instruction:      mpInstruction,
		Product:          productFromFlags(),
		Audiences:        parseAudienceFlag(mpAudiences),
		ExtraConstraints: mpConstraint,
		CreatedAt:        time.Now().UTC(),
	}
	if len(b.Audiences) == 0 {
		b.Audiences = medplan.AllAudiences()
	}
	if mpProject != "" {
		b.Project = mpProject
	} else {
		b.Project = medplan.Slugify(mpProductName)
	}
	return b, nil
}

func productFromFlags() medplan.Product {
	return medplan.Product{
		Name:            mpProductName,
		Company:         mpCompany,
		Modality:        mpModality,
		MOA:             mpMOA,
		Indications:     splitComma(mpIndications),
		Stage:           mpStage,
		RxStatus:        mpRxStatus,
		Differentiators: splitComma(mpDifferentiators),
		Competitors:     splitComma(mpCompetitors),
	}
}

func splitComma(s string) []string {
	if strings.TrimSpace(s) == "" {
		return nil
	}
	parts := strings.Split(s, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		if p = strings.TrimSpace(p); p != "" {
			out = append(out, p)
		}
	}
	return out
}

func parseAudienceFlag(s string) []medplan.Audience {
	var out []medplan.Audience
	for _, tok := range splitComma(s) {
		switch strings.ToLower(tok) {
		case "all":
			return medplan.AllAudiences()
		default:
			a, err := medplan.ParseAudience(tok)
			if err != nil {
				fmt.Fprintf(os.Stderr, "warning: %v\n", err)
				continue
			}
			out = append(out, a)
		}
	}
	return out
}

// resolveProject picks the project: flag > positional arg > single
// stored project > brief flags.
func resolveProject(args []string, store *medplan.ProjectStore) string {
	if mpProject != "" {
		return mpProject
	}
	if len(args) > 0 {
		return args[0]
	}
	projects, err := store.List()
	if err == nil && len(projects) == 1 {
		return projects[0]
	}
	return ""
}

// loadBrief loads the brief for a resolved project name.
func loadBrief(args []string, store *medplan.ProjectStore) (*medplan.Brief, error) {
	name := resolveProject(args, store)
	if name == "" {
		return nil, fmt.Errorf("project not found: pass a project name or --project")
	}
	b, err := store.LoadBrief(name)
	if err != nil {
		return nil, fmt.Errorf("load brief for %q (run `medit medplan new` first): %w", name, err)
	}
	return b, nil
}

// buildMedplanLLM returns (provider, label, err) from the shared flags.
// Degrades to nil provider with a warning on failure.
func buildMedplanLLM(out io.Writer) foundation.LLMProvider {
	if askNoLLM {
		return nil
	}
	llm, err := buildLLM()
	if err != nil {
		fmt.Fprintf(out, "warning: LLM unavailable (%v) — template/启发式 mode\n", err)
		return nil
	}
	return llm
}

// routerSearcher adapts the multi-source router to the medplan
// LiteratureSearcher interface (browser-free source set by default).
type routerSearcher struct{ r *router.Router }

func (s routerSearcher) SearchLiterature(ctx context.Context, query string, max int) ([]types.Citation, error) {
	ep, err := s.r.Ask(ctx, types.EBMQuestion{
		Query:      query,
		Intent:     types.IntentSearch,
		MaxResults: max,
	})
	if err != nil {
		return nil, err
	}
	return ep.Citations, nil
}

// buildMedplanResearcher assembles the researcher with the router.
func buildMedplanResearcher(llm foundation.LLMProvider) (*medplan.Researcher, error) {
	r := router.NewRouter()
	r.Concurrency = 3
	r.TimeoutPerSource = 30 * time.Second
	r.MaxRetries = 1
	for _, name := range parseSourceList(mpSources) {
		switch name {
		case "pubmed":
			s, err := source.NewPubMedSource(nil)
			if err != nil {
				return nil, err
			}
			r.AddSource(s)
		case "openalex":
			s, err := source.NewOpenAlexSource(nil)
			if err != nil {
				return nil, err
			}
			r.AddSource(s)
		case "s2":
			s, err := source.NewS2Source(nil)
			if err != nil {
				return nil, err
			}
			r.AddSource(s)
		}
	}
	res := &medplan.Researcher{
		Searcher:    routerSearcher{r: r},
		LLM:         llm,
		MaxPerQuery: mpMaxResults,
	}
	return res, nil
}

func labelFor(llm foundation.LLMProvider) string {
	if llm == nil {
		return "template"
	}
	return "llm:" + llm.Name()
}

// --- new ---

var medplanNewCmd = &cobra.Command{
	Use:   "new",
	Short: "创建策划项目 (brief: 指令 + 产品信息)",
	Args:  cobra.NoArgs,
	RunE: func(cmd *cobra.Command, _ []string) error {
		store, err := mpStoreOrDie()
		if err != nil {
			return err
		}
		brief, err := buildBriefFromFlags()
		if err != nil {
			return err
		}
		if err := store.SaveBrief(brief); err != nil {
			return err
		}
		out := cmd.OutOrStdout()
		fmt.Fprintf(out, "项目已创建: %s\n", store.Dir(brief.Project))
		fmt.Fprintf(out, "下一步: medit medplan run %s\n", brief.Project)
		return nil
	},
}

// --- run ---

var medplanRunCmd = &cobra.Command{
	Use:   "run [project]",
	Short: "端到端: 调研 → 提炼 → 分受众大纲 → 合规验证",
	Args:  cobra.MaximumNArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		store, err := mpStoreOrDie()
		if err != nil {
			return err
		}
		ctx := cmd.Context()
		var brief *medplan.Brief
		if len(args) == 0 && mpBriefFile == "" && mpInstruction != "" {
			// Inline brief flags: create on the fly.
			if brief, err = buildBriefFromFlags(); err != nil {
				return err
			}
		} else if brief, err = loadBrief(args, store); err != nil {
			return err
		}
		llm := buildMedplanLLM(cmd.ErrOrStderr())
		researcher, err := buildMedplanResearcher(llm)
		if err != nil {
			return err
		}
		pipe := &medplan.Pipeline{
			Researcher: researcher,
			Analyzer:   &medplan.Analyzer{LLM: llm},
			Generator:  &medplan.Generator{LLM: llm, ProviderLabel: labelFor(llm)},
			Checker:    medplan.NewComplianceChecker(llm),
			Store:      store,
		}
		opts := medplan.RunOptions{
			Brief:          brief,
			SkipResearch:   mpSkipResearch,
			SkipCompliance: mpSkipCompliance,
		}
		if mpAudiences != "" {
			opts.Audiences = parseAudienceFlag(mpAudiences)
		}
		res, err := pipe.Run(ctx, opts)
		if err != nil {
			return err
		}
		out := cmd.OutOrStdout()
		fmt.Fprintf(out, "\n完成 (%.1fs) — %s\n", res.Duration.Seconds(), store.Dir(brief.Project))
		fmt.Fprintf(out, "调研条目: %d | 观点: %d\n", len(res.Dossier.Items), len(res.Insights.Insights))
		for _, a := range brief.Audiences {
			o := res.Outlines[a]
			if o == nil {
				continue
			}
			line := fmt.Sprintf("  [%s] v%d (%s) 章节 %d", a, o.Version, o.GeneratedBy, o.SectionCount())
			if rep := res.Compliance[a]; rep != nil {
				c := rep.CountsBySeverity()
				line += fmt.Sprintf(" | 合规: %s (fatal %d / warn %d / info %d)",
					strings.ToUpper(rep.Verdict), c[medplan.SevFatal], c[medplan.SevWarn], c[medplan.SevInfo])
			}
			fmt.Fprintln(out, line)
			fmt.Fprintf(out, "    → %s\n", store.OutlinePath(brief.Project, a))
		}
		if mpJSON {
			return json.NewEncoder(cmd.OutOrStdout()).Encode(res)
		}
		return nil
	},
}

// --- research ---

var medplanResearchCmd = &cobra.Command{
	Use:   "research [project]",
	Short: "执行五维调研 (文献/新闻/研报/政策/竞品) 并保存",
	Args:  cobra.MaximumNArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		store, err := mpStoreOrDie()
		if err != nil {
			return err
		}
		brief, err := loadBrief(args, store)
		if err != nil {
			return err
		}
		llm := buildMedplanLLM(cmd.ErrOrStderr())
		researcher, err := buildMedplanResearcher(llm)
		if err != nil {
			return err
		}
		d, err := researcher.Research(cmd.Context(), brief)
		if err != nil {
			return err
		}
		if mpIngestFile != "" {
			var items []medplan.ResearchItem
			data, err := os.ReadFile(mpIngestFile)
			if err != nil {
				return fmt.Errorf("read ingest file: %w", err)
			}
			if err := json.Unmarshal(data, &items); err != nil {
				return fmt.Errorf("parse ingest file (want JSON array of {dimension,title,summary,url}): %w", err)
			}
			medplan.IngestItems(d, items)
		}
		if err := store.SaveResearch(d); err != nil {
			return err
		}
		out := cmd.OutOrStdout()
		for _, dim := range d.Dimensions() {
			fmt.Fprintf(out, "%s: %d 条\n", dim.StringCN(), len(d.ItemsByDimension(dim)))
		}
		for _, q := range d.Queries {
			if q.Error != "" {
				fmt.Fprintf(out, "  ! [%s] %s → %s\n", q.Dimension, q.Query, q.Error)
			}
		}
		fmt.Fprintf(out, "已保存: %s\n", store.Dir(brief.Project)+string(os.PathSeparator)+"research.json")
		return nil
	},
}

// --- outline ---

var medplanOutlineCmd = &cobra.Command{
	Use:   "outline [project]",
	Short: "生成指定受众的策略大纲 (--audience hcp|patient|industry|all)",
	Args:  cobra.MaximumNArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		store, err := mpStoreOrDie()
		if err != nil {
			return err
		}
		brief, err := loadBrief(args, store)
		if err != nil {
			return err
		}
		d, err := store.LoadResearch(brief.Project)
		if err != nil {
			return fmt.Errorf("no research.json — run `medit medplan research %s` first: %w", brief.Project, err)
		}
		ins, err := store.LoadInsights(brief.Project)
		if err != nil {
			analyzer := &medplan.Analyzer{LLM: buildMedplanLLM(cmd.ErrOrStderr())}
			if ins, err = analyzer.Analyze(cmd.Context(), brief, d); err != nil {
				return err
			}
			_ = store.SaveInsights(ins)
		}
		audiences := parseAudienceFlag(mpAudiences)
		if len(audiences) == 0 {
			audiences = brief.Audiences
		}
		llm := buildMedplanLLM(cmd.ErrOrStderr())
		gen := &medplan.Generator{LLM: llm, ProviderLabel: labelFor(llm)}
		out := cmd.OutOrStdout()
		for _, a := range audiences {
			o, err := gen.Generate(cmd.Context(), brief, d, ins, a)
			if err != nil {
				fmt.Fprintf(cmd.ErrOrStderr(), "warning: %v\n", err)
			}
			if o == nil {
				return fmt.Errorf("outline(%s): no output", a)
			}
			if err := store.SaveOutline(o); err != nil {
				return err
			}
			md := medplan.RenderMarkdown(o, medplan.RenderOptions{Dossier: d, Insights: ins, Brief: brief})
			if err := store.WriteMarkdown(brief.Project, a, md); err != nil {
				return err
			}
			fmt.Fprintf(out, "[%s] v%d (%s) 章节 %d → %s\n",
				a, o.Version, o.GeneratedBy, o.SectionCount(), store.OutlinePath(brief.Project, a))
		}
		return nil
	},
}

// --- optimize ---

var medplanOptimizeCmd = &cobra.Command{
	Use:   "optimize [project]",
	Short: "语义优化/扩充大纲 (--audience + --instruction 或 --expand <节ID>)",
	Args:  cobra.MaximumNArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		store, err := mpStoreOrDie()
		if err != nil {
			return err
		}
		brief, err := loadBrief(args, store)
		if err != nil {
			return err
		}
		audiences := parseAudienceFlag(mpAudiences)
		if len(audiences) == 0 {
			return fmt.Errorf("--audience required (hcp|patient|industry)")
		}
		d, err := store.LoadResearch(brief.Project)
		if err != nil {
			d = &medplan.ResearchDossier{Project: brief.Project} // optimize without dossier
		}
		llm := buildMedplanLLM(cmd.ErrOrStderr())
		if llm == nil {
			return fmt.Errorf("optimize requires an LLM (--llm glm|hermes|openai)")
		}
		opt := &medplan.Optimizer{LLM: llm}
		out := cmd.OutOrStdout()
		for _, a := range audiences {
			o, err := store.LoadOutline(brief.Project, a)
			if err != nil {
				return fmt.Errorf("no outline for %s — run outline first: %w", a, err)
			}
			var next *medplan.StrategyOutline
			if mpExpandSection != "" {
				next, err = opt.ExpandSection(cmd.Context(), o, brief, d, mpExpandSection, mpOptimizeInstr)
			} else {
				if mpOptimizeInstr == "" {
					return fmt.Errorf("--instruction required (or --expand <sectionID>)")
				}
				next, err = opt.Optimize(cmd.Context(), o, brief, d, mpOptimizeInstr)
			}
			if err != nil {
				return fmt.Errorf("optimize(%s): %w", a, err)
			}
			if err := store.SaveOutline(next); err != nil {
				return err
			}
			md := medplan.RenderMarkdown(next, medplan.RenderOptions{Dossier: d, Brief: brief})
			if err := store.WriteMarkdown(brief.Project, a, md); err != nil {
				return err
			}
			last := next.ChangeLog[len(next.ChangeLog)-1]
			fmt.Fprintf(out, "[%s] v%d ← %s\n  %s\n  → %s\n", a, next.Version, last.Instruction, last.Summary, store.OutlinePath(brief.Project, a))
		}
		return nil
	},
}

// --- compliance ---

var medplanComplianceCmd = &cobra.Command{
	Use:   "compliance [project]",
	Short: "中国大陆医学合规验证 (规则引擎 + 可选 LLM 语义审查)",
	Args:  cobra.MaximumNArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		store, err := mpStoreOrDie()
		if err != nil {
			return err
		}
		brief, err := loadBrief(args, store)
		if err != nil {
			return err
		}
		audiences := parseAudienceFlag(mpAudiences)
		if len(audiences) == 0 {
			audiences = brief.Audiences
		}
		llm := buildMedplanLLM(cmd.ErrOrStderr())
		checker := medplan.NewComplianceChecker(llm)
		out := cmd.OutOrStdout()
		overall := "pass"
		for _, a := range audiences {
			o, err := store.LoadOutline(brief.Project, a)
			if err != nil {
				return fmt.Errorf("no outline for %s: %w", a, err)
			}
			rep, err := checker.Check(cmd.Context(), o, brief.Product)
			if err != nil {
				return err
			}
			if err := store.SaveCompliance(rep); err != nil {
				return err
			}
			c := rep.CountsBySeverity()
			fmt.Fprintf(out, "[%s] v%d 引擎=%s → %s (fatal %d / warn %d / info %d)\n",
				a, o.Version, rep.Engine, strings.ToUpper(rep.Verdict), c[medplan.SevFatal], c[medplan.SevWarn], c[medplan.SevInfo])
			for _, f := range rep.Findings {
				fmt.Fprintf(out, "  %s [%s] %s — %s\n", f.RuleID, f.Severity, f.Matched, f.Suggestion)
			}
			if rep.Verdict == "fail" {
				overall = "fail"
			} else if rep.Verdict == "warn" && overall != "fail" {
				overall = "warn"
			}
		}
		fmt.Fprintf(out, "总体: %s (详细 JSON 见 compliance_<audience>.json)\n", strings.ToUpper(overall))
		return nil
	},
}

// --- show / list ---

var medplanShowCmd = &cobra.Command{
	Use:   "show [project]",
	Short: "查看项目状态与产物路径",
	Args:  cobra.MaximumNArgs(1),
	RunE: func(cmd *cobra.Command, args []string) error {
		store, err := mpStoreOrDie()
		if err != nil {
			return err
		}
		brief, err := loadBrief(args, store)
		if err != nil {
			return err
		}
		out := cmd.OutOrStdout()
		fmt.Fprintf(out, "项目: %s (%s)\n", brief.Project, store.Dir(brief.Project))
		fmt.Fprintf(out, "指令: %s\n", brief.Instruction)
		fmt.Fprintf(out, "产品: %s | 适应症: %s | 分类: %s\n",
			brief.Product.Name, strings.Join(brief.Product.Indications, "、"), brief.Product.RxStatus)
		if d, err := store.LoadResearch(brief.Project); err == nil {
			fmt.Fprintf(out, "调研: %d 条\n", len(d.Items))
		} else {
			fmt.Fprintln(out, "调研: 未执行")
		}
		for _, a := range brief.Audiences {
			if o, err := store.LoadOutline(brief.Project, a); err == nil {
				fmt.Fprintf(out, "大纲[%s]: v%d 章节 %d", a, o.Version, o.SectionCount())
				if rep, err := store.LoadCompliance(brief.Project, a); err == nil {
					fmt.Fprintf(out, " | 合规: %s", strings.ToUpper(rep.Verdict))
				}
				fmt.Fprintln(out)
			}
		}
		return nil
	},
}

var medplanListCmd = &cobra.Command{
	Use:   "list",
	Short: "列出全部策划项目",
	Args:  cobra.NoArgs,
	RunE: func(cmd *cobra.Command, _ []string) error {
		store, err := mpStoreOrDie()
		if err != nil {
			return err
		}
		projects, err := store.List()
		if err != nil {
			return err
		}
		out := cmd.OutOrStdout()
		if len(projects) == 0 {
			fmt.Fprintln(out, "(无项目 — medit medplan new 创建)")
			return nil
		}
		for _, p := range projects {
			fmt.Fprintln(out, p)
		}
		return nil
	},
}

func init() {
	medplanRunCmd.Flags().StringVar(&mpAudiences, "audiences", "", "逗号分隔: hcp,patient,industry|all")
	medplanRunCmd.Flags().IntVar(&mpMaxResults, "max-results", 8, "每条文献查询保留的最大引用数")
	medplanRunCmd.Flags().StringVar(&mpSources, "sources", "pubmed,openalex,s2", "文献源 (逗号分隔)")
	medplanRunCmd.Flags().BoolVar(&mpSkipResearch, "skip-research", false, "复用已保存的 research.json")
	medplanRunCmd.Flags().BoolVar(&mpSkipCompliance, "skip-compliance", false, "跳过合规验证")
	medplanRunCmd.Flags().StringVar(&mpBriefFile, "brief-file", "", "Brief JSON 文件 (代替 flags)")
	medplanRunCmd.Flags().StringVar(&mpInstruction, "instruction", "", "策划指令 (与 flags 组合内联创建项目时必填)")
	medplanRunCmd.Flags().StringVar(&mpConstraint, "constraint", "", "额外约束 (预算/时间线/区域/渠道)")
	medplanRunCmd.Flags().BoolVar(&mpJSON, "json", false, "输出 JSON 结果")

	medplanNewCmd.Flags().StringVar(&mpInstruction, "instruction", "", "策划指令 (必填)")
	medplanNewCmd.Flags().StringVar(&mpConstraint, "constraint", "", "额外约束 (预算/时间线/区域/渠道)")
	medplanNewCmd.Flags().StringVar(&mpAudiences, "audiences", "", "逗号分隔: hcp,patient,industry|all")

	medplanResearchCmd.Flags().IntVar(&mpMaxResults, "max-results", 8, "每条文献查询保留的最大引用数")
	medplanResearchCmd.Flags().StringVar(&mpSources, "sources", "pubmed,openalex,s2", "文献源 (逗号分隔)")
	medplanResearchCmd.Flags().StringVar(&mpIngestFile, "ingest", "", "补充人工调研材料 JSON 数组文件 ({dimension,title,summary,url})")

	medplanOutlineCmd.Flags().StringVar(&mpAudiences, "audience", "", "hcp|patient|industry|all (默认 brief 全部受众)")

	medplanOptimizeCmd.Flags().StringVar(&mpAudiences, "audience", "", "hcp|patient|industry (必填)")
	medplanOptimizeCmd.Flags().StringVar(&mpOptimizeInstr, "instruction", "", "优化指令 (自由语义)")
	medplanOptimizeCmd.Flags().StringVar(&mpExpandSection, "expand", "", "仅深度扩充指定章节 (节 ID, 如 5 或 5.2)")

	medplanComplianceCmd.Flags().StringVar(&mpAudiences, "audience", "", "hcp|patient|industry|all (默认 brief 全部受众)")
}
