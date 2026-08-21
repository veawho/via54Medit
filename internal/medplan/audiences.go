// Audience profiles and deterministic outline skeletons.
//
// The skeleton is the no-LLM floor: every audience gets the five core
// strategy modules (市场 / 竞品 / 品牌本体 / 竞争优势包装 / 传播策略)
// plus audience-specific modules. With an LLM the same skeleton seeds
// the generation prompt so output structure stays stable across runs.
package medplan

// AudienceProfile describes how to research and write for one audience.
type AudienceProfile struct {
	Audience Audience
	Tone     string // 写作基调
	Focus    string // 内容侧重
	Evidence string // 证据偏好
	// StrictCompliance: patient-facing material triggers the strictest
	// rule set (处方药大众传播、疗效断言、患者证言).
	StrictCompliance bool
	// ResearchTerms are appended to literature queries for this audience.
	ResearchTerms []string
}

// ProfileFor returns the profile for an audience.
func ProfileFor(a Audience) AudienceProfile {
	switch a {
	case AudienceHCP:
		return AudienceProfile{
			Audience:      AudienceHCP,
			Tone:          "严谨学术, 循证导向, 数据驱动",
			Focus:         "临床价值、循证证据链、指南与临床路径地位、未满足需求",
			Evidence:      "RCT/Meta 分析/真实世界研究, 指南推荐等级",
			ResearchTerms: []string{"randomized", "meta-analysis", "guideline"},
		}
	case AudiencePatient:
		return AudienceProfile{
			Audience: AudiencePatient,
			Tone:     "通俗共情, 易读易懂, 避免专业术语堆砌",
			Focus:    "疾病认知、诊疗旅程、治疗可及性、患者支持",
			Evidence: "患者结局研究、生活质量数据、可及性政策",
			// 患者材料触发最严合规档: 广告法 16 条 + 处方药 DTC 禁令.
			StrictCompliance: true,
			ResearchTerms:    []string{"patient outcomes", "quality of life"},
		}
	case AudienceIndustry:
		return AudienceProfile{
			Audience:      AudienceIndustry,
			Tone:          "商业洞察, 结构化, 市场与支付视角",
			Focus:         "市场规模与增长、支付与准入 (NMPA/NRDL/VBP)、商业模式、行业趋势",
			Evidence:      "流行病学数据、市场研报、政策文件",
			ResearchTerms: []string{"epidemiology", "market access"},
		}
	}
	// unreachable for validated audiences; keep a sane default.
	return AudienceProfile{Audience: a}
}

// coreModules is the shared five-module strategy spine (稳定骨架,
// 与受众无关): 市场环境 / 竞品分析 / 品牌本体 / 竞争优势包装 / 传播策略.
func coreModules(a Audience) []OutlineSection {
	p := ProfileFor(a)
	return []OutlineSection{
		{
			ID:    "1",
			Title: "市场环境分析",
			Points: []string{
				"疾病负担与流行病学: 患者池规模、诊疗路径现状",
				"治疗格局: 现有治疗方案与未满足的临床需求",
				"市场动态: 增长驱动因素与准入窗口期",
			},
		},
		{
			ID:    "2",
			Title: "竞品分析",
			Points: []string{
				"竞品图谱: 同靶点/同品类竞品定位梳理",
				"头对头证据对比: 疗效、安全性、给药便利性、经济学",
				"竞品传播策略拆解与我方差异化机会点",
			},
		},
		{
			ID:    "3",
			Title: "品牌本体",
			Points: []string{
				"品牌定位陈述 (Positioning Statement)",
				"品牌核心价值主张与个性",
				"循证支撑的品牌故事弧线",
			},
		},
		{
			ID:    "4",
			Title: "核心竞争优势包装",
			Points: []string{
				"优势证据矩阵: 每个竞争优势 ↔ 支撑数据/文献",
				"信息层级: 核心信息钥匙 → 支撑信息 → 佐证数据",
				"针对受众 (" + p.Audience.StringCN() + ") 的优势语言转译",
			},
		},
		{
			ID:    "5",
			Title: "传播策略",
			Points: []string{
				"传播目标与关键信息 (Key Message) 体系",
				"渠道与触点规划: 分阶段投放节奏",
				"效果衡量: 传播 KPI 与监测机制",
			},
		},
	}
}

// audienceModules returns the audience-specific sections appended after
// the five core modules.
func audienceModules(a Audience) []OutlineSection {
	switch a {
	case AudienceHCP:
		return []OutlineSection{
			{
				ID:    "6",
				Title: "循证证据链构建",
				Points: []string{
					"关键临床研究解读: 主要终点、次要终点、亚组发现",
					"证据等级金字塔: RCT → Meta → RWE 的叙事顺序",
					"指南与专家共识中的地位及引用策略",
				},
			},
			{
				ID:    "7",
				Title: "学术传播与医学教育",
				Points: []string{
					"学术会议与卫星会规划 (贡献声明与利益冲突合规)",
					"KOL/学科建设合作框架 (RDPAC 行为准则边界)",
					"医学教育内容矩阵: 从认知到处方行为转化的路径",
				},
			},
		}
	case AudiencePatient:
		return []OutlineSection{
			{
				ID:    "6",
				Title: "疾病认知与患者旅程",
				Points: []string{
					"患者就诊路径中的认知断点与信息需求",
					"从症状识别到规范诊疗的旅程地图",
					"照护者与家庭支持视角",
				},
			},
			{
				ID:    "7",
				Title: "治疗可及与患者支持",
				Points: []string{
					"治疗可及性: 医保/援助项目信息 (仅事实陈述, 不含疗效宣传)",
					"患者支持项目 (PSP) 设计: 用药依从性、随访教育",
					"合规边界: 处方药不得面向公众发布广告, 患者材料限于疾病教育",
				},
			},
		}
	case AudienceIndustry:
		return []OutlineSection{
			{
				ID:    "6",
				Title: "支付与准入策略",
				Points: []string{
					"NMPA 注册审批路径与时间线",
					"国家医保谈判 (NRDL) 与集采 (VBP) 影响推演",
					"药物经济学价值档案 (Value Dossier) 要点",
				},
			},
			{
				ID:    "7",
				Title: "商业模式与合作生态",
				Points: []string{
					"商业模式画布: 客户、渠道、收入结构",
					"行业趋势: 政策与技术变革下的机会窗口",
					"合作伙伴生态与投资亮点",
				},
			},
		}
	}
	return nil
}

// Skeleton returns the deterministic outline template for an audience:
// 5 core modules + audience-specific modules, with evidence slots left
// empty for the research stage to fill.
func Skeleton(project string, a Audience) *StrategyOutline {
	now := nowUTC()
	o := &StrategyOutline{
		Project:     project,
		Audience:    a,
		Version:     1,
		Sections:    append(coreModules(a), audienceModules(a)...),
		GeneratedBy: "template",
		CreatedAt:   now,
		UpdatedAt:   now,
	}
	return o
}

// AttachEvidence links research items to the sections that cite them.
// v1 heuristic mapping by dimension: literature → 循证/优势 sections,
// policy → 准入/传播, competitor → 竞品, news/report → 市场.
// At most maxEvidencePerSection IDs per section keeps renders readable.
const maxEvidencePerSection = 6

// AttachEvidence is deterministic: dimension order → section order.
func (o *StrategyOutline) AttachEvidence(items []ResearchItem) {
	byDim := map[ResearchDimension][]string{}
	for _, it := range items {
		byDim[it.Dimension] = append(byDim[it.Dimension], it.ID)
	}
	for _, dim := range AllDimensions() {
		ids := byDim[dim]
		if len(ids) == 0 {
			continue
		}
		var targets []string
		switch dim {
		case DimLiterature:
			targets = []string{"4", "6"}
		case DimCompetitor:
			targets = []string{"2"}
		case DimPolicy:
			targets = []string{"1", "5"}
		case DimReport, DimNews:
			targets = []string{"1"}
		}
		for _, tid := range targets {
			if sec := o.FindSection(tid); sec != nil {
				rest := maxEvidencePerSection - len(sec.Evidence)
				if rest <= 0 {
					continue
				}
				if len(ids) > rest {
					ids = ids[:rest]
				}
				sec.Evidence = append(sec.Evidence, ids...)
			}
		}
	}
}
