# MEDPLAN — 医学策划方案生成 + 中国大陆合规验证 (v1, 2026-08-21)

> `internal/medplan` + `medit medplan` — 基于文献调研能力的医学策划方案撰写系统:
> 指令 + 产品信息 → 五维调研 → 观点提炼 → 分受众策略大纲 (HCP/患者/行业)
> → 语义优化 → 中国大陆医学合规验证。

## 1. 动机与定位

via54Medit 已具备多源医学文献检索/应证能力 (`ask`/`router`/`anno2ppt`)。
medplan 把这条证据链向**策划端**延伸: 医药产品的上市/学术/品牌传播策略
大纲撰写, 并内置中国大陆医学合规验证 (广告法/药品管理法/医疗广告管理
办法/RDPAC)。

GitHub 调研结论 (2026-08, 详见 §7): 该定位在开源界**没有直接竞品** —
策划侧仅有 0-star 的 prompt/skill packs, 合规侧只有通用敏感词过滤。
medplan 的架构借鉴 STORM (outline-first + 受众视角驱动调研) 与
gpt-researcher (带引用的并行检索) 的成熟模式。

## 2. Pipeline (六阶段)

```
[1] Brief      指令 + 产品信息 (Product: 名称/适应症/MOA/竞品/Rx分类/差异点)
[2] Research   五维调研: 文献(router 真实检索) + 新闻/研报/政策/竞品(LLM 综合)
[3] Analyze    观点提炼: insights (强/中/弱证据强度 + advantage 标记) + SWOT
[4] Outline    分受众生成: 5 核心模块骨架 + 受众专属模块 (HCP/患者/行业)
[5] Optimize   语义优化: 自由指令驱动深度优化/扩充, 版本化 + changelog
[6] Compliance 合规验证: 确定性规则引擎 (常开) + LLM 语义审查 (可选)
```

每一阶段**确定性降级**: 无 LLM → 文献=router 引用列表, 大纲=骨架模板,
新闻/研报维度跳过 (可用 `--ingest` 人工补料); LLM 解析失败 → 模板回退。
调研永不因单源失败而中断 (per-query 错误记录在 dossier.queries)。

## 3. CLI

```bash
# 端到端 (推荐): 调研 → 提炼 → 三档大纲 → 合规
medit medplan run --instruction "为 DrugX 上市撰写三档医学传播策略" \
  --name "DrugX" --indication "2型糖尿病" --moa "GLP-1受体激动剂" \
  --rx-status rx --competitor "DrugY" --differentiator "每周一次给药" \
  --llm glm                     # 或 --no-llm 走模板模式

# 分阶段
medit medplan new ...           # 创建项目 (brief.json)
medit medplan research <项目>    # 五维调研 (可 --ingest news.json 补人工材料)
medit medplan outline <项目> --audience hcp|patient|industry|all
medit medplan optimize <项目> --audience hcp --instruction "把传播策略扩充到县域市场"
medit medplan optimize <项目> --audience patient --expand 5   # 仅扩充第 5 节
medit medplan compliance <项目> --audience all
medit medplan show <项目> / list

# LLM 路由
--llm glm      智谱 BigModel (GLM_API_KEY, 默认 glm-4-flash 免费层)
--llm hermes   本地 MiniMax-M3 网关 (localhost:8765)
--llm openai   OpenAI 兼容
```

产物 (每项目一个目录, 原子写入):

```
~/.medit/medplan/<project>/
├── brief.json               # 任务输入
├── research.json            # 五维调研 (item ID: L001/N001/R001/P001/C001)
├── insights.json            # 观点 + SWOT
├── outline_hcp.json         # 大纲 (版本化, changelog)
├── outline_hcp.md           # 渲染稿 (含证据脚注 + 合规横幅)
├── compliance_hcp.json      # 合规报告
└── ... (patient / industry 同构)
```

## 4. 受众画像与大纲骨架

| 受众 | 专属模块 | 基调 | 合规档位 |
|---|---|---|---|
| HCP | 循证证据链构建 / 学术传播与医学教育 | 严谨学术, 循证导向 | 标准 |
| 患者 | 疾病认知与患者旅程 / 治疗可及与患者支持 | 通俗共情 | **最严** (Rx-DTC 禁令 + disclaimer 检查) |
| 行业 | 支付与准入策略 / 商业模式与合作生态 | 商业洞察 | 标准 |

五核心模块 (所有受众共享, 稳定骨架): **市场环境 → 竞品分析 → 品牌本体 →
核心竞争优势包装 → 传播策略**。LLM 生成时骨架嵌入 prompt, 保证结构稳定。

## 5. 合规引擎 (compliance.go + compliance_rules.go)

### 5.1 规则表 (数据驱动, ID 稳定供 CI diff)

| 规则 ID | 依据 | 级别 |
|---|---|---|
| ADV-16-CURE | 广告法§16(1)(一)(二): 疗效断言/治愈率/有效率 | fatal |
| ADV-16-SAFE | 广告法§16(1)(一): 安全性保证 ("安全无副作用") | fatal |
| ADV-16-COMPARE | 广告法§16(1)(三): 与其他药品功效安全性比较 | warn |
| ADV-16-ENDORSE | 广告法§16(1)(四)§16(2): 代言/患者证言 | fatal |
| ADV-09-ABSOLUTE | 广告法§9(三): 绝对化用语 (国家级/最佳/全球首创...) | warn |
| DRG-RX-PUBLIC | 药品管理法§89: 处方药大众媒介广告 (仅 rx 产品) | fatal |
| DRG-INDUCE | 广告审查办法§11: 热销/抢购/无效退款 | warn |
| MED-TECH-CLAIM | 医疗广告管理办法§7: 医疗技术断言 | warn |
| MED-ENDORSE-ORG | 机构名义背书 (卫建委推荐/权威认证) | warn |
| PAT-PRODUCT-PROMO | 处方药 DTC: 患者材料产品宣传 (仅 patient) | fatal |
| PAT-DISCLAIMER | 患者提示语缺失检查 (presence 型, 仅 patient) | info |
| HCP-RDPAC-GIFT | RDPAC 准则: HCP 利益输送表述 | warn |

### 5.2 引擎行为

- **否定语境豁免**: 命中片段或其前 16 字符含否定词 (不得/禁止/避免...)
  时豁免 — 陈述禁令 ≠ 违反禁令 ("处方药**不得**面向公众发布广告" 不报)。
- **presence 型规则**: PAT-DISCLAIMER 在患者大纲**缺**提示语时提示。
- **受众/产品门控**: PatientOnly 规则仅患者版触发; RxOnly 仅处方药触发。
- **LLM 语义层** (可选): 捕捉正则无法覆盖的风险 — off-label、无证据优势
  断言、变相比较、隐性 Rx-DTC、指南引用失真 (LLM-* 规则 ID, 需人工复核)。
- **verdict**: fatal>0 → FAIL; warn>0 → WARN; 否则 PASS。
  section 级标注回写 outline (渲染时显示 ⚠️)。

### 5.3 已知边界

- 规则表是 v1 起点, 不是法律意见; 正式投放物料仍需法务/注册审批
  (广告审查批准文号) 流程。
- 增量路径 (v2 候选): 接入 ToolGood.Words (Apache-2.0, Go DFA 引擎,
  5.2k★) 的广告法词库提升扫描性能; CCCpan/chinese-sensitive-words-mcp
  (MIT) 的医疗宣称词表作为规则补充。

## 6. 模块地图

```
internal/medplan/
├── models.go           数据模型: Brief/Product/Dossier/Insight/Outline/Report
├── audiences.go        受众画像 + 五模块骨架 + 受众模块 + 证据挂接
├── research.go         调研编排: query matrix (确定性) + 文献去重 + LLM 综合
├── analyze.go          观点提炼: LLM 结构化 (item_id 校验) + 启发式回退
├── outline.go          大纲生成: LLM JSON (骨架约束) + 模板回退
├── optimize.go         语义优化: 版本化 + changelog + 结构 diff
├── compliance.go       合规引擎: 规则扫描 + 否定豁免 + LLM 语义层
├── compliance_rules.go 规则表 (数据驱动)
├── project.go          持久化 (~/.medit/medplan/<项目>/, 原子写)
├── render.go           Markdown 渲染 (证据脚注 + 合规横幅 + SWOT)
└── pipeline.go         六阶段编排 (逐阶段降级, slog 审计)
internal/foundation/llm_glm.go    GLM provider (RegisterLLM("glm"))
cmd/medit/commands/medplan.go     8 个子命令
```

测试: `go test ./internal/medplan/ ./internal/foundation/ -v`
(合规规则、否定豁免、query matrix 确定性、LLM 解析校验、降级链、
持久化 round-trip、pipeline 端到端、GLM HTTP 协议)

## 7. GitHub 同类项目调研 (2026-08, 铁律: 动手前先调研高星项目)

**结论: "医学策划生成 + 中国合规验证" 无成熟开源竞品。**

### 策划/研究管线 (借鉴对象)

| 项目 | Stars | 借鉴点 |
|---|---|---|
| [stanford-oval/storm](https://github.com/stanford-oval/storm) | 31.1k | outline-first 两阶段 (调研/大纲与写作分离); Perspective-Guided 受众视角提问 → medplan 的受众驱动 query matrix |
| [assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher) | 29.1k | planner/executor/publisher + 来源追踪 → medplan 的 evidence ID 溯源 (每观点→材料 ID) |
| [bytedance/deer-flow](https://github.com/bytedance/deer-flow) | 80.4k | planner→researcher→ reporter 状态机; 阶段化 pipeline 参考 |
| [binary-husky/gpt_academic](https://github.com/binary-husky/gpt_academic) | 71.2k | 插件式文档工作流 (GPL-3.0, 只借鉴模式不引代码) |
| [andreiiordache/llm_skills_pharma_strategy](https://github.com/andreiiordache/llm_skills_pharma_strategy) | 0 | 唯一 pharm-strategy 开源实现 (prompt pack) — 证明该领域是空白 |

### 敏感词/合规引擎 (词库与算法参考)

| 项目 | Stars | License | 用途 |
|---|---|---|---|
| [toolgood/ToolGood.Words](https://github.com/toolgood/ToolGood.Words) | 5.2k | Apache-2.0 | Go DFA 敏感词引擎 (仓库内置 Go 移植), v2 性能升级候选 |
| [houbb/sensitive-word](https://github.com/houbb/sensitive-word) | 6k | Apache-2.0 | 词分类标签设计 (规则类别↔词表映射) |
| [CCCpan/chinese-sensitive-words-mcp](https://github.com/CCCpan/chinese-sensitive-words-mcp) | 112 | MIT | 含医疗宣称词 + 风险分级, 词表补充候选 |
| [zmexing/go-sensitive-word](https://github.com/zmexing/go-sensitive-word) | 24 | — | Go DFA 最小实现先例 |

### 结论性设计决策

1. **正则规则表而非 DFA**: v1 规则量 (~20 pattern) 下 regexp 足够且可读;
   规则量上百后迁移 ToolGood.Words Go 引擎。
2. **规则常开 + LLM 语义收尾**: 呼应仓库"算法驱动"铁律 — 确定性结果
   可 CI diff, LLM 仅补充语义风险并标注"需人工复核"。
3. **大纲为一等公民** (JSON 持久化 + 版本化): 合规检查/语义优化都作用于
   大纲结构而非生成文本, 对齐 STORM 的 pre-writing 分离。

## 8. Roadmap (v2 候选)

- [ ] 调研维度接入真实新闻/研报源 (integrations/CATALOG.md 中 60+ 商业情报源)
- [ ] 合规词库扩充 (ToolGood.Words 词表 + 医疗宣称词表, 含变体/拼音绕过)
- [ ] 大纲→正文扩写 (per-section 深度写作, goldmark 渲染 DOCX)
- [ ] MCP 工具暴露 (medit-mcp: medplan_run / medplan_compliance)
- [ ] 合规修正建议的 diff 视图 (sergi/go-diff)
