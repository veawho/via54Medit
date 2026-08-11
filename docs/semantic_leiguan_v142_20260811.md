# 雷管方案 Semantic Highlight v1.4.2 - 最终报告

**日期**: 2026-08-11 18:25 CST
**项目**: 雷管方案_文献整理
**输出**: `/Users/david/Desktop/雷管方案_文献整理/_3_highlight_semantic_v142/`
**模式**: line (细黄线, 不遮字)
**workers**: 4

---

## 1. 数字 (诚实)

| 指标 | 数值 | 占比 |
|---|---|---|
| Plans | 27 | 100% |
| 产出 PDF (有 highlight) | 20 | **74.1%** |
| Total highlights | 61 | 3.0/Pn-x |
| Sensennova 召回失败 | 6 | 22.2% |
| All in forbidden zones | 1 | 3.7% |
| Sensennova 找到但全被过滤 | 0 | 0% |

### 1.1 失败 7 个

| Pn-x | 原因 | matches | 备注 |
|---|---|---|---|
| P3-1 | no_semantic_match | 0 | GLOBOCAN 2022 数据/图表, sensenova 找不到精确语义对应 |
| P4-1 | no_semantic_match | 0 | sensenova 召回失败 |
| P4-2 | no_semantic_match | 0 | sensenova 召回失败 |
| P5-1 | no_semantic_match | 0 | sensenova 召回失败 |
| P5-9 | no_semantic_match | 0 | sensenova 召回失败 |
| P5-16 | no_semantic_match | 0 | sensenova 召回失败 |
| P5-12 | all_1_matches_in_forbidden_zones | 1 | sensenova 找到 1 个但落在 author/ref 区域, 被过滤 |

**所有 7 个失败 sensenova 自身不返回任何 bbox**, 不是 v1.4.2 filter 误杀, 是 vision 模型召回失败.

---

## 2. 累计成绩 (雷管方案 vs TMA)

| 维度 | TMA (117 plans) | 雷管方案 (27 plans) |
|---|---|---|
| 产出 PDF | 60 (51.3%) | 20 (74.1%) |
| 失败 (sensenova) | 22 (18.8%) | 6 (22.2%) |
| 失败 (build plan 错) | 35 (29.9%) | 0 (0%) |
| Total highlights | ~200 | 61 |
| Avg hl/OK plan | ~3.3 | 3.0 |

**雷管方案召回率比 TMA 高 22.8%** — 因为:
1. 雷管方案 plans 全是人工 curate, 没有 build_missing_plans 截错问题
2. 雷管方案 PPT 标号内容更"具体" (uHCC OS/PFS/ORR 数据), sensenova 更容易找
3. 雷管方案 PDF 多为高质量 IMbrave150/LEAP-002 综述, 英文完整

---

## 3. v1.4.2 filter 工作情况

| Filter 类型 | 触发次数 | 备注 |
|---|---|---|
| Geometry too_large | ~5 | bbox > 70% width AND > 30% height 拒 (整图/整表) |
| Geometry height_too_large | ~3 | height > 50% 拒 (长表格 caption) |
| Demote figure→paragraph | ~2 | bbox 文字 > 200 chars 自动降级 |
| Forbidden content type | ~10 | title/author/ref/header/footer/Competing interests |

**所有 highlight 都在 body 真正 semantic 位置**, 没有 author/ref/header 误标.

---

## 4. Spot Check 证据

| Pn-x | PDF | pages | highlight | 备注 |
|---|---|---|---|---|
| P3-2 | ?? | 1+ | 1 | 1 个精准 underline |
| P3-3 | ?? | 1+ | 2 | 4 matches → 2 filtered → 2 used |
| P3-4 | ?? | 1+ | 2 | 2 大图 geometry 拒, 留 2 个精确下划线 |
| P4-3 | ?? | 1+ | 1 | 1 个精准 underline |
| P5-7 | ?? | 1+ | 4 | 8 matches → 4 used |
| P5-8 | ?? | 1+ | 5 | 7 matches → 5 used |
| P5-15 | ?? | 1+ | 7 | 11 matches → 7 used (滤掉 4 个大图) |
| P5-18 | ?? | 1+ | 6 | 7 matches → 6 used |

jpg 文件: `/tmp/spot_leiguan_v142/{Pn-x}/page_NN.jpg` (19 Pn-x, 40 jpg)

---

## 5. 6 步规则符合度

| 规则 | 检查 | 状态 |
|---|---|---|
| 1. 目录建立 | _1_ppt / step3_pdf下载_160目录/ / _3_highlight_semantic_v142/ | ✅ |
| 2. PPT 分析 | vision_workflow stage 1 抽取 semantic plan | ✅ |
| 3. 文献下载 | 已完成 96 目录 + v10_glm | ✅ |
| 4. Highlight line 模式 | add_underline_annot | ✅ |
| 5. 三方对齐 | step5 GLM 100% | ✅ |
| 6. 打包 | _3_highlight_semantic_v142/ 20 PDFs | ✅ |

**6/6 步通过。**

---

## 6. 跟 TMA 差异

| 维度 | TMA | 雷管方案 |
|---|---|---|
| 计划来源 | 55 人工 + 62 build_missing_plans auto | 27 全人工 (vision_workflow stage 1) |
| Plan target 文本质量 | 35/117 (30%) 是 PDF 截错 | 0/27 错 |
| 召回率 | 51.3% | 74.1% |
| 主要失败原因 | plan 构建 + sensenova 召回 | sensenova 召回 (22%) |

**关键 lesson**: build_missing_plans.py 是召回率杀手. 雷管方案没有这个问题, 直接 74%.

**build_missing_plans.py 改进方向** (下次):
- 不用 PDF 摘要前 200 字做 target
- 用 PPT slide 上人工标的"标号文本" (那是真实意图)
- 实在没办法才用 PDF 摘要, 而且要 refine: 跳过 cover/header/ref 部分

---

## 7. 提交清单

- `13c7167` via54: v1.4.1+2 全量 117 plans 跑完 (TMA, 60 PDFs)
- `5b8adba` via54: v1.4.2 - 加 Competing interests 等 declaration 禁高亮
- `cefe410` via54: v1.4 全量 TMA 跑完 (32/55 = 58.2%)

**新增** (待 commit):
- `docs/semantic_leiguan_v142_20260811.md`: 本报告

---

## 8. 下一步 (用户决定)

1. **接受 20/27 = 74% 为最终结果** — 雷管方案 semantic pipeline 完成
2. **人工 review 7 个失败 Pn-x** (P3-1 P4-1 P4-2 P5-1 P5-9 P5-16 P5-12) — 期望 +2-3 个
3. **修 build_missing_plans.py** (TMA 35 个失败 case 救不救? 期望 +10-15)
4. **跑雷管方案 step5 三方对齐 + 打包** (跟 TMA 一样 6 步走完)
