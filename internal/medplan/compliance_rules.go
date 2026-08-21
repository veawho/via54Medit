// China-mainland medical compliance rules (中国大陆医学合规规则表).
//
// Scope: content destined for promotional / communication materials in
// mainland China is checked against:
//
//   - 《中华人民共和国广告法》第九条   绝对化用语 (极限词)
//   - 《中华人民共和国广告法》第十六条 医疗/药品/医疗器械广告禁止内容
//   - 《药品管理法》及《药品、医疗器械、保健食品、特殊医学用途配方食品
//     广告审查管理暂行办法》 处方药大众媒介禁令、诱导性内容
//   - 《医疗广告管理办法》 医疗技术断言
//   - RDPAC《行业行为准则》 HCP 互动材料边界
//
// Rules are data, not code: each entry declares pattern(s), severity,
// legal basis, a rewrite suggestion, and optional audience/Rx gating.
// The engine (compliance.go) applies them deterministically; the LLM
// layer only adds semantic findings regex cannot catch.
package medplan

import "regexp"

// checkKind distinguishes how a rule evaluates.
type checkKind string

const (
	// checkViolation: any pattern match is a finding (default).
	checkViolation checkKind = "violation"
	// checkPresence: a finding is raised when NO pattern matches the
	// whole outline (used for "disclaimer missing" advisory rules).
	checkPresence checkKind = "presence"
)

// ComplianceRule declares one deterministic check.
type ComplianceRule struct {
	ID         string
	Category   string
	Severity   ComplianceSeverity
	Patterns   []*regexp.Regexp
	LegalBasis string
	Suggestion string
	// Kind selects violation vs presence semantics.
	Kind checkKind
	// Audiences: empty = applies to every audience; otherwise only the
	// listed audiences trigger it.
	Audiences []Audience
	// PatientOnly: rule fires only for the patient audience
	// (patient-facing material is held to the strictest standard).
	PatientOnly bool
	// RxOnly: only fires when the product is a prescription drug.
	RxOnly bool
}

// complianceRules is the v1 rule table. Order = report order within
// equal severity; IDs are stable for CI diffing.
var complianceRules = []ComplianceRule{
	// --- 广告法第十六条: 疗效/安全性断言与保证 (fatal) ---
	{
		ID:       "ADV-16-CURE",
		Category: "疗效断言/保证",
		Severity: SevFatal,
		Patterns: []*regexp.Regexp{
			regexp.MustCompile(`根治|治愈率|有效率\s*(?:高达|达到)?\s*\d|保证治愈|彻底治愈|包治|药到病除|攻克癌症|治愈一切`),
			regexp.MustCompile(`100%\s*(?:有效|安全|治愈)`),
		},
		LegalBasis: "《广告法》第十六条第一款第(一)项: 医疗、药品、医疗器械广告不得含有表示功效、安全性的断言或者保证; 第(二)项: 不得说明治愈率或者有效率",
		Suggestion: "删除断言性疗效承诺, 改为引用具体临床研究数据并标注来源与研究局限",
	},
	{
		ID:       "ADV-16-SAFE",
		Category: "安全性断言",
		Severity: SevFatal,
		Patterns: []*regexp.Regexp{
			regexp.MustCompile(`安全无(?:毒)?副作用|绝对安全|无毒副作用|零风险|无任何副作用`),
		},
		LegalBasis: "《广告法》第十六条第一款第(一)项: 不得含有表示安全性的断言或者保证",
		Suggestion: "安全性表述必须基于说明书与临床试验不良事件数据, 不得作绝对化保证",
	},
	{
		ID:       "ADV-16-COMPARE",
		Category: "与其他药品比较",
		Severity: SevWarn,
		Patterns: []*regexp.Regexp{
			regexp.MustCompile(`优于\s*(?:所有|其他)\s*(?:药品|药物|竞品|治疗方案)|疗效(?:远)?优于|全面超越竞品`),
			regexp.MustCompile(`最好的\s*(?:药|治疗|方案)`),
		},
		LegalBasis: "《广告法》第十六条第一款第(三)项: 不得与其他药品、医疗器械的功效和安全性比较",
		Suggestion: "比较性表述仅限专业学术场景下头对头数据的客观陈述; 对外传播改为差异事实描述 (机制/给药频次/可及性)",
	},
	{
		ID:       "ADV-16-ENDORSE",
		Category: "代言/患者证言",
		Severity: SevFatal,
		Patterns: []*regexp.Regexp{
			regexp.MustCompile(`(?:明星|代言人).{0,8}(?:推荐|代言)|患者现身说法|患者证言|用户反馈证实`),
		},
		LegalBasis: "《广告法》第十六条第一款第(四)项: 不得利用广告代言人作推荐、证明; 第十六条第二款: 不得利用患者名义或形象作证明",
		Suggestion: "删除代言与患者证言类内容; 患者故事仅可用于非促销性质的疾病教育活动, 且需授权与场景合规审核",
	},

	// --- 广告法第九条: 绝对化用语 (warn) ---
	{
		ID:       "ADV-09-ABSOLUTE",
		Category: "绝对化用语",
		Severity: SevWarn,
		Patterns: []*regexp.Regexp{
			regexp.MustCompile(`国家级|世界级|最高级|最佳|最好|最强|最有效|最安全|最先进|最新技术|第一品牌|顶级|极品|全网第一|销量第一|史上最|独一无二|全球首创|全球第一|国内首创`),
			regexp.MustCompile(`(?i)NO\.?\s*1`),
		},
		LegalBasis: "《广告法》第九条第(三)项: 不得使用国家级、最高级、最佳等绝对化用语",
		Suggestion: "极限词一律删除; 事实性的首创/首个表述须有可查证批件或文献佐证, 并改为客观陈述",
	},

	// --- 药品广告审查: 处方药大众媒介 + 诱导性内容 ---
	{
		ID:       "DRG-RX-PUBLIC",
		Category: "处方药大众传播",
		Severity: SevFatal,
		Patterns: []*regexp.Regexp{
			regexp.MustCompile(`大众(?:媒介|媒体)|电视广告|短视频(?:平台)?投放|社交平台种草|朋友圈广告|电梯广告`),
		},
		LegalBasis: "《药品管理法》第八十九条: 处方药不得在大众媒体发布广告; 《广告审查管理暂行办法》第五条",
		Suggestion: "处方药推广仅限医学药学专业刊物与学术渠道; 面向公众的内容必须转为纯疾病教育 (不含产品名与疗效信息)",
		RxOnly:     true,
	},
	{
		ID:       "DRG-INDUCE",
		Category: "诱导性内容",
		Severity: SevWarn,
		Patterns: []*regexp.Regexp{
			regexp.MustCompile(`热销|抢购|限时优惠|买一送一|家庭必备|送礼佳品|无效退款|保险公司承保`),
		},
		LegalBasis: "《广告审查管理暂行办法》第十一条: 药品广告不得含有热销、抢购、家庭必备等诱导性内容, 不得含有无效退款等承诺",
		Suggestion: "删除促销诱导语; 药品传播不得附购物式激励",
	},

	// --- 医疗广告管理办法: 技术断言 ---
	{
		ID:       "MED-TECH-CLAIM",
		Category: "医疗技术断言",
		Severity: SevWarn,
		Patterns: []*regexp.Regexp{
			regexp.MustCompile(`最(?:新|先进)诊疗技术|尖端技术|国际领先技术|革命性突破|里程碑式治愈`),
		},
		LegalBasis: "《医疗广告管理办法》第七条: 医疗广告不得含有涉及医疗技术、诊疗方法等内容",
		Suggestion: "技术领先类表述改为具体技术特征与已发表证据的客观描述",
	},

	// --- 机构名义背书 ---
	{
		ID:       "MED-ENDORSE-ORG",
		Category: "机构名义背书",
		Severity: SevWarn,
		Patterns: []*regexp.Regexp{
			regexp.MustCompile(`国家(?:机关|推荐)|卫建委推荐|药监局推荐|三甲医院(?:指定|联名)|中华医学会推荐|权威机构认证`),
		},
		LegalBasis: "《广告法》及《医疗广告管理办法》: 不得利用国家机关、医疗单位、学术机构、行业组织的名义或形象作推荐证明",
		Suggestion: "删除机构背书表述; 指南引用须准确注明来源、版本与推荐级别, 不得暗示官方推荐",
	},

	// --- 患者材料专项 (patient-only, 最严档) ---
	{
		ID:       "PAT-PRODUCT-PROMO",
		Category: "患者材料产品宣传",
		Severity: SevFatal,
		Patterns: []*regexp.Regexp{
			regexp.MustCompile(`处方药.{0,12}(?:广告|推广|宣传)|产品疗效宣传`),
		},
		LegalBasis:  "《药品管理法》第八十九条处方药 DTC 禁令: 患者端材料应为疾病教育, 不含产品促销信息",
		Suggestion:  "患者端内容仅保留疾病认知、就诊指引与合规疾病教育; 产品信息限说明书公开范围并提示遵医嘱",
		PatientOnly: true,
	},
	{
		ID:       "PAT-DISCLAIMER",
		Category: "患者提示缺失",
		Severity: SevInfo,
		Kind:     checkPresence,
		Patterns: []*regexp.Regexp{
			regexp.MustCompile(`遵医嘱|在医生指导下|请咨询医生|专业诊疗建议|不能替代专业诊疗`),
		},
		LegalBasis:  "患者教育材料合规惯例 + 《广告法》第十六条精神",
		Suggestion:  "患者端材料应在显著位置包含: 本内容仅供疾病教育, 不能替代专业诊疗建议, 请遵医嘱",
		PatientOnly: true,
	},

	// --- HCP 材料 RDPAC 边界 ---
	{
		ID:       "HCP-RDPAC-GIFT",
		Category: "HCP 互动合规",
		Severity: SevWarn,
		Patterns: []*regexp.Regexp{
			regexp.MustCompile(`(?:向|为)(?:医生|HCP).{0,10}(?:赠送|礼品|提成|返点|旅游)|回扣|处方费`),
		},
		LegalBasis: "RDPAC《行业行为准则》: 禁止以利益诱导处方; 《反不正当竞争法》第七条商业贿赂条款",
		Suggestion: "删除利益输送表述; HCP 合作限定于学术交流, 咨询费公允且透明申报",
	},
}

// rxStatus values recognized by the compliance engine.
const (
	rxStatusRx     = "rx"     // 处方药
	rxStatusOTC    = "otc"    // 非处方药
	rxStatusDevice = "device" // 医疗器械
)

// rulesFor returns the rules that apply to an audience + product,
// preserving table order (deterministic).
func rulesFor(a Audience, product Product) []ComplianceRule {
	out := make([]ComplianceRule, 0, len(complianceRules))
	for _, r := range complianceRules {
		if r.RxOnly && product.RxStatus != rxStatusRx {
			continue
		}
		if r.PatientOnly && a != AudiencePatient {
			continue
		}
		if len(r.Audiences) > 0 {
			match := false
			for _, x := range r.Audiences {
				if x == a {
					match = true
					break
				}
			}
			if !match {
				continue
			}
		}
		out = append(out, r)
	}
	return out
}
