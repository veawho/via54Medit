---
name: via54medit-algorithm-driven-upgrade-v2
description: "D 列算法驱动升级 — via54Medit 文献整理 4 列 CSV (slide/mark/citation/visual_content) 算法架构 + 5 步骤端到端工作流 (PPT → CSV → PDF → highlight → 三方对齐 → 目录打包). 覆盖 python-pptx XML 确定性解析 + vision 视觉验证 双轨 + Pydantic schema + 4 类幻觉过滤. 触发词: 4 列 CSV, 160 行真值, 视觉对齐 PPT, 标号 N → 视觉内容, PPTX 引文, vision 不稳定, dual-track, 5 步骤, 6 步骤, Pn-x 1:1, DOI 合并, PowerPoint 渲染, 三方对齐, highlight, 扩页 PPT, 颜色对比度, 文献整理, 视觉驱动, 视觉配对, 浅黄细线, 关键词匹配, 严禁关键词, PyMuPDF underline, segfault, y 坐标翻转, fallback vs main, 算法驱动, 步骤拆开, 一键复现, 自检, P3-2."
---

# via54medit-algorithm-driven-upgrade-v2 — D 列算法 驱动升级 类级技能

## 何时使用

当 **via54Medit 文献整理** 类任务需要调通算法, 让 D 列对齐真值 (飞书 8 列真值表), 标号 N → 视觉内容时. 覆盖 PPT 解析 / vision 提数据 / PDF 应证 / 4 列 CSV 输出 + **5 步骤端到端工作流** (PPT → CSV → PDF → highlight → 三方对齐) + **第 6 步目录整理打包** (Pn-x 1:1 不合并 + step4 按 DOI 合并 + 算法脚本归档 via54Medit + 临时目录).

## 核心架构 (v2.13.0 视觉驱动 highlight + 双轨 + Pydantic + 4 类幻觉过滤 + PowerPoint 渲染 + 7 步骤目录整理)

### 5 步骤端到端 (用户硬规则, 2026-08-05 用户权威 spec)

**步骤 1: PPT 目录**
- 建立 3 类子目录: (a) PPT 目录 (原版 + 扩页 + 扩页 jpg), (b) 文献 PDF 下载目录, (c) 文献 highlight 目录
- **PowerPoint 渲染** (默认, 不 fallback Keynote/LibreOffice) — 原因是 PPT 是 PowerPoint 做的, 其他渲染器视觉不一致
- 扩页 PPT 7.5\"→9.5\" 保留引文完整可见

**步骤 2: 标注分析**
- 视觉分析所有元素可见性, 若超出页面 → 重新扩页 (规则 2.2)
- **扩页 PPT 底色与文字颜色对比度校验** (规则 2.2 — 文字需视觉可识别)
- A B C 列 1:1 镜像真值 (固定不变)
- D 列视觉+文字理解 (暂定, 后续 PDF 应证校准)
- 必须视觉分析, 需 PPT→jpg 目录

**步骤 3: PDF 下载**
- E 列 DOI (带超链接)
- F 列下载链接 (引文完整字段 + DOI 交叉校验)
- G 列实际下载的 PDF 文件
- Pn-x 1:1 归档, **不去重** (一个 Pn-x = 一个标号, 即使同一文献 DOI 相同)
- 主 PDF + 摘要 PDF 备份都保留

**步骤 4: Highlight (v2.13.0 视觉驱动范式)**
- **严禁关键词匹配** (用户原话, 多次重申)
- 7 步拆开: 重置 → PDF 导 jpg → PPT slide jpg → vision 比对 → PIL 画浅黄细线 → 坐标映射 → PyMuPDF underline → 验证
- 每个步骤独立可验证
- **浅黄色细线** (RGB 1.0, 1.0, 0.6 / 255, 255, 153), PyMuPDF add_underline_annot (type 9)
- 每个标号只 highlight 自己应证内容, 不共享 slide 关键词
- 详见 `references/v2.13.0-highlight-visual-paradigm-shift.md`

**步骤 5: 三方对齐 (12 列 CSV)**
- 3 对齐: (slide+mark) ↔ (A+B) ↔ 文献下载目录 ↔ highlight 目录
- 3 对齐: (引文) ↔ (C+E) ↔ 下载 PDF 文件 ↔ highlight PDF 文件
- 3 对齐: (视觉内容) ↔ (D+F+H) ↔ highlight 图片 ↔ 表格

### 第 6 步: 目录整理打包 (用户硬规则)

**关键原则 (2026-08-05 用户硬规则)**:
- **step3 下载目录不合并**: 160 Pn-x = 160 子目录 (1 对 1 镜像 PPT 标号)
- **step4 highlight 目录按 DOI 合并**: 85 唯一 DOI + 11 无 DOI = 96 唯一文献目录
- **算法脚本归档到 via54Medit**: `scripts/literature_v8_*.py`
- **临时/审计/旧版 → step6/_tmp/**: `_background_*` `_audit_*` `_research` `_knowledge` `_archived_old_dirs` 等

### v2.13.0 Highlight 视觉驱动范式 (用户硬规则, 2026-08-05)

**严禁 (之前 v1-v9 全部失败)**:
- 关键词匹配全文 (变相关键词评分)
- 标单个数字/单词 (要整段/整句/图表/表格)
- 按段数叠加评分 (page 1 段多但不是真应证, 用单段最高分)
- fill 矩形高亮 (要 underline 浅黄细线, type 9)
- 不验证保存成功 (跑完必须看 PDF underline 数)
- **凭印象猜 bbox** (PyMuPDF get_text("blocks") 提真实 PDF 段坐标, 不要用 jpg 像素猜. 例 P3-2 应证段 PDF pt = (84, 64, 512, 165) — 段被切成 4 block, 段头 y0=64, 段尾 y1=165. 不要用 jpg (40, 80, 1100, 280) 估算 — 用户原话: "我都把要标注的内容发给你了, 你都highlight不对")
- **画红框让你确认** (用户原话: "红框又是你的新发明, 你哪来那么多新发明" — 不发明未要求的 UI 元素. 验证靠 vision_analyze 看 PNG 自检)
- **PyMuPDF underline annot 用 fill 颜色** (PyMuPDF Warning "fill color ignored for annot type 'Highlight'". underline type 9 只支持 stroke, 用 stroke=(1.0, 1.0, 0.6) 即可)
- **annotation type 用错编号** (PyMuPDF underline = 9 (不是 12), highlight = 8, text = 1. 验证脚本必须用 safe_annot_type 包装 try/except, 因为 `a.type` 抛 "annotation not bound to any page" 会崩)

**正确做法 (用户喂饭式设计)**:
1. 视觉理解 PPT slide jpg → 提"标号 N 应证视觉"
2. PDF 每页导 jpg (pdftoppm 或 PyMuPDF get_pixmap dpi=120)
3. 视觉比对 PDF jpg → 找应证段/图表/表格 bbox
4. 在该 jpg 上画浅黄细线 (PIL.ImageDraw.line at y1)
5. jpg bbox → PDF 坐标 (按 dpi 缩放)
6. PyMuPDF add_underline_annot (type 9) + saveIncr
7. 验证 PDF underline + 提最终 PNG

**复现命令**:
```bash
/Users/david/.hermes/hermes-agent/venv/bin/python /Users/david/.medit/scripts/highlight_v10.py
```

### v2.14.0 颜色 B 选项 + 多行应证段画线 (2026-08-05 反思会话新增)

**用户对比 3 颜色选项后选 B**:
- A 浅黄细 (255, 255, 153, 2px) → 太淡, 看不清 ❌
- **B 中黄中粗 (255, 230, 100, 4px) → 用户选 ✅**
- C 深黄粗 (255, 220, 0, 6px) → 视觉过强 (备选)

**用户原话**: "整段就要high段落的每一句" — **多行应证段每行画一条浅黄细线** (不是只画一段底一条). P3-2 应证段被 PyMuPDF 切成 4 行, 4 行独立 underline.

**严禁 (新增)**:
- 只画一条段底线 (用户原话: "整段就要 high 段落的每一句")
- 浅黄太淡 (255, 255, 153, 2px) — 用户说"看不清"
- RGB 严格匹配 `==` — PNG 压缩后 RGB 不精确, 用宽范围 (R 240-255, G 215-245, B 80-115)
- 把 main PDF 当真值 PDF — step3 多 PDF 时必须用**用户发的真值 PDF** (用户原话: "我都把要标注的内容发给你了"). P3-1 main IARC PDF 没有 China 单独数据, 必须用 GLOBOCAN 摘要 1 页 (含 "中国占全球 24.2%")

**详见 `references/v2.14.0-highlight-color-and-multi-line.md`**

**复现命令**:
```bash
# 视觉配对 + 多行画线 (P3-2)
/Users/david/.hermes/hermes-agent/venv/bin/python /Users/david/.medit/scripts/highlight_vision_runner.py

# 测试中文 PDF
/Users/david/.hermes/hermes-agent/venv/bin/python /Users/david/.medit/scripts/test_zh_pdfs.py

# 自检 (避开 segfault)
/Users/david/.hermes/hermes-agent/venv/bin/python /Users/david/.medit/scripts/verify_highlight.py
```

### v2.9.0 双轨 + Pydantic 强化

- 轨道 A: python-pptx 提 PPTX 结构化 XML (100% 稳定, 文字/坐标/层级/表格/引文)
- 轨道 B: vision 验证图片语义 (96.9% ≥50% 命中, 柱图/KM/视觉关联)
- **Pydantic schema 强制** (SlideVision + ChartDataPoint + cap 20)
- **4 类幻觉过滤**: 精度 (1 位小数) + 80% 软上限 + 共享引文 (max_dup=2) + 单位
- XML 优先 (引文, 位置), Vision 补充 (chart/table data_points), 冲突时 XML 胜

### v2.9.0 关键实验数据

- vision 跑 2 次 (P3-P43 verified): **39.6% 一致率** (99 行 ≥50% 不稳定)
- 子 agent vision 跑 P31: 35.5% 错 (实际 35.8%) — vision 不可信
- python-pptx XML 跑 1 次: **100% 稳定** (86.2% 命中真值 C 字段)
- 双轨合并 (XML 100% + vision 96.9%): 96.9% ≥50% 命中
- 漏 5 行 100% 是 PDF 应证数据 (Sangro 1494P + Lau Asian + George ESMO Asia + Yau Lancet)

### 详细策略版本树

- **v2.13.0 Highlight 视觉驱动范式 (2026-08-05 反思会话新增)**: 步骤 4 highlight 严禁关键词匹配, 必须视觉比对 PPT jpg vs PDF jpg, 浅黄细线 (add_underline_annot, type 9), 7 步拆开可复现. 见 references/v2.13.0-highlight-visual-paradigm-shift.md
- **v2.12.0 7 步骤端到端**: 5 步骤 + 第 6 步目录打包 + 算法脚本归档 via54Medit
- **v2.11.0 Pn-x 1:1 不合并 (用户硬规则, 跨标号访问性优先) (2026-08-05)**
- v2.10.0 6 步骤端到端
- v2.9.0 Pydantic + 4 类幻觉过滤
- v2.8.0 双轨方案 (XML + vision)
- v2.7.0 vision 不稳定 + 双跑并集策略
- v2.6.0 视觉稳定性验证 + 5 PDF 漏
- v2.5.0 视觉对齐 PPT 整体规则

## 关键不变量 (160 行真值)

- 160 行 = 飞书 164 行 - 4 行视觉错位 (P12-5 / P14-2 / P22-13 / P30-10)
- A B C 必须 100% 镜像真值
- D 列先 ≥50% 命中, 再向 100% 推
- **视觉算法 ≤ 96.9% 天花板** (5 漏 100% PDF 应证, 不在 PPT 视觉)
- **Pn-x 1:1 镜像 PPT 标号** (step3 不合并)
- **highlight 目录按 DOI 合并** (step4 96 唯一)
- **highlight 视觉驱动** (v2.13.0, 严禁关键词匹配)

## 当前主算法 v8 (D 列) + v10 (highlight)

| 版本 | 方案 | 覆盖率 |
|-----|------|-------|
| v6 | vision 视觉对齐 PPT | 96.9% ≥50% 命中 |
| v7a | python-pptx XML 提取 | 86.2% 引文映射 |
| v7c | 双轨合并 (XML + vision) | 96.9% ≥50% 命中 + 86.2% XML |
| **v8** | **双轨 + Pydantic schema + 4 类幻觉过滤** | **96.9% ≥50% + 86.2% XML + 4 类 guard** |
| **v10** | **Highlight 视觉驱动范式 (7 步拆开)** | **视觉比对 + 浅黄细线 + 可复现** |
| v_pdf | PDF 应证推理 (待跑) | 推 100% |

## v8 算法 (2026-08-05)

- 主脚本: `scripts/analyze_ppt_citations_v8_pydantic_voting.py` (~12 KB)
- PoC 演示: `/Users/david/v8_demo.py` (290 行, 含 offline self-test)
- Pydantic schema 强制: `SlideVision` + `ChartDataPoint` + cap 20 (防止 DP 幻觉过载)
- 4 类幻觉过滤 (HALLUCINATION_GUARD):
  - `min_decimals_other_source=2` (vision 给 35.5 低于 XML 35.8 → 降级)
  - `soft_max_pct=80.0` (超过 80% 砍掉, CI 边界 95/100/90 例外)
  - `max_dup_per_slide=2` (共享引文同 (label,value) 出现 >2 → 留 1 次)
  - `unit_mismatch_block=True` (label "OS" 但 unit="mo" → drop vision)
- XML 优先 + Vision 补充 (XML 86.2% 100% 稳定, Vision 补 chart/table)
- D 列 % 覆盖 78.6% (264/336), ≥50% 命中 96.9% (155/160)
- 漏 5 行: 100% PDF 应证 (不在 PPT 视觉)

## v10 算法 (2026-08-05 反思会话新增)

- 主脚本: `/Users/david/.medit/scripts/highlight_v10.py`
- 7 步拆开: reset_pnx → render_pdf_pages_to_jpg → vision_analyze → draw_underline_on_jpg → jpg_bbox_to_pdf_coords → add_pdf_underline → verify_pdf_underline
- 浅黄色细线: RGB (1.0, 1.0, 0.6) = (255, 255, 153)
- PyMuPDF add_underline_annot (type 9, **不是 type 12, 不是 highlight type 8**)
- 严禁关键词匹配, 视觉解决视觉
- 每次跑前 reset_pnx 清旧 highlight
- 详细设计见 references/v2.13.0-highlight-visual-paradigm-shift.md

## v8 Pydantic 最小代码 (摘自 v8_demo.py)

```python
from pydantic import BaseModel, Field, field_validator
from pydantic_ai import Agent, BinaryContent

class ChartDataPoint(BaseModel):
    mark: int = Field(ge=1)
    label: str = Field(min_length=1, max_length=200)
    value: float
    unit: str = Field(default="", max_length=20)
    ci_low: float | None = None
    ci_high: float | None = None

class SlideVision(BaseModel):
    slide_mark: int = Field(ge=1)
    data_points: list[ChartDataPoint] = Field(default_factory=list)
    chart_caption: str | None = Field(default=None, max_length=500)

    @field_validator("data_points")
    @classmethod
    def _cap_dp(cls, v):
        if len(v) > 20:
            raise ValueError(f"too many data points ({len(v)})")
        return v

# 投票: N=3 majority per token-class, value 取 median
def vote_slide(runs: list[SlideVision]) -> SlideVision:
    # slide_mark: Counter.most_common(1)
    # data_points: 至少 ⌈N/2⌉=2 次出现, value 取 median
    # ci_low/ci_high: 出现 ≥2 次取 median, 否则 None
    # unit: Counter majority
    # chart_caption: Counter majority
```

## 关键脚本

- `scripts/analyze_ppt_citations_v8_pydantic_voting.py` — **v8 主算法, 双轨 + Pydantic + 4 类过滤**
- `scripts/v9_full_pipeline.py` — **v9 端到端 5 步骤流水线 (PowerPoint 渲染 + 颜色对比度 + Pn-x 1:1 + highlight 综合 + 12 列对齐)**
- `scripts/highlight_vision_runner.py` — **v2.14 视觉配对 + 多行画线 + 自检 (本轮新增)**
- `/Users/david/v8_demo.py` — v8 概念验证 (290 行, 含 offline self-test)
- `/Users/david/.medit/scripts/highlight_vision_runner.py` — **v2.14 视觉配对 + 多行画线 + 自检 (本轮新增)**
- `/Users/david/.medit/scripts/test_zh_pdfs.py` — **中文 PDF 测试 (P3-1/3-2/3-3/3-4/5-1/14-1/30-9/36-2)**
- `/Users/david/.medit/scripts/verify_highlight.py` — **自检 (PIL+numpy, 避开 a.type segfault)**
- `/Users/david/v8_demo.py` — v8 概念验证 (290 行, 含 offline self-test)
- `scripts/analyze_ppt_citations_v7_pptx_xml.py` — v7 XML 提结构化
- `scripts/analyze_ppt_citations_v6_vision_align.py` — v6 vision 评估
- `scripts/expand_slide_for_visibility.py` — 扩 PPT 7.5\"→9.5\" (修过: 用 prs.slide_height = Inches(max) 而非 slide.element.getparent().set('cy', ...))
- `scripts/export_ppt_to_images.py` — **PPT→JPG, PowerPoint 渲染默认 (强制不 fallback Keynote)**
- `scripts/render_pptx_via_powerpoint.py` — PowerPoint 单独渲染脚本
- `scripts/render_pptx_via_pptx2image.py` — pptx2image 备用 (需 pip install)
- `scripts/highlight_pdfs.py` — PDF 黄色下划线 + 截图
- `scripts/verify_highlight_self_check.py` — **highlight 后自检 4 项 (避开 `a.type` segfault, 用 `a.rect` 维度推断 + PIL+numpy 浅黄像素检测, 不让 user 确认)**
- `scripts/merge_same_doi_pdfs.py` — step4 highlight 按 DOI 合并 (注意: 只合 step4, step3 不合)
- `scripts/verify_three_way_alignment.py` — 三方对齐验证
- `scripts/hlo_scheduler.py` — HLO 调度
- `scripts/run_regression_tests.sh` — 回归测试

## 关键参考

### v2.13.0 (本次新增)
- `references/v2.13.0-highlight-visual-paradigm-shift.md` — **Highlight 视觉驱动范式 (用户硬规则, 严禁关键词匹配, 7 步拆开)**

### v2.14.0 (本轮反思新增)
- `references/v2.14.0-highlight-color-and-multi-line.md` — **颜色 B 选项 + 多行应证段每行画线 + PNG 压缩后 RGB 宽范围检测 + 真值 PDF 优先**

### v2.16.0 (2026-08-05 第四轮反思新增, 图表矩形 + 深黄 + 真值 PDF 不替换)
- `references/v2.16.0-chart-rectangle-and-deep-yellow.md` — **图表用 Square annot (矩形框) 不用 underline + PDF underline 改深黄 (1.0, 0.8, 0.0) 不用中黄 (1.0, 0.902, 0.392) + 用户发的 PDF 用于校对算法结果不擅自替换 step4 main PDF**. P3-1 (Asia 区域行) + P3-3 (Fig. 2) + P3-4 (Fig. 1 + Table 2 BCLC) 实战案例

### v2.15.0 (2026-08-05 第三轮反思, 落地坑)
- `references/v2.15.0-pymupdf-traps-and-reset-recipe.md` — **PyMuPDF 4 大落地坑 (os.listdir 选 fallback / delete_annot 残留 / y 坐标翻转 / 共享 _pdf_jpg) + 算法驱动步骤拆开硬规则 + P3-2 完整一键复现 recipe + 自检 4 项**

### v2.12.0
- `references/v2.12.0-five-step-user-canonical-spec.md` — **5 步骤用户权威 spec (2026-08-05 最终版)**
- `references/v2.12.0-step3-vs-step4-opposite-merge-rules.md` — **step3 不合并 Pn-x vs step4 按 DOI 合并 严格相反规则**
- `references/v2.12.0-powerpoint-render-mandatory.md` — **PowerPoint 渲染默认 (原因 + 强制不 fallback)**
- `references/v2.12.0-ppt-contrast-check.md` — **扩页 PPT 底色 vs 文字颜色对比度校验**

### v2.11.0
- `references/v2.11.0-pnx-1to1-no-merge-12col-schema.md` — 12 列对齐 schema + Pn-x 1:1
- `references/v2.10.0-six-step-end-to-end-workflow.md` — 6 步骤工作流
- `references/v2.10.0-github-stability-solutions-verified.md` — GitHub 稳定性方案
- `references/v2.10.0-five-step-workflow-end-to-end.md` — 5 步骤

### v2.9.0
- `references/v2.9.0-pydantic-voting-hallucination-filter.md` — **Pydantic + 4 类过滤详细设计**
- `references/v2.9.0-vision-instability-quantified.md` — **vision 不稳定实测数据 (39.6% 一致率)**
- `references/v2.9.0-github-stability-solutions.md` — **GitHub 仓库稳定性方案评估**
- `references/v2.9.0-pdf-only-data-points-5-misses.md` — **5 行 PDF 应证分子清单**

### 历史
- `references/v2.8.0-dual-track-pptx-xml-plus-vision.md` — 双轨方案 v2.8.0
- `references/v2.7.0-vision-instability-and-union-strategy.md` — vision 不稳定 + 并集
- `references/v2.6.0-vision-stability-verify-5-pdf-miss.md` — 视觉稳定性验证
- `references/v2.5.0-d-column-round1-vision-align-ppt.md` — vision 视觉对齐 PPT
- `references/v2.5.0-vision-json-6-formats-compat.md` — 6 种 JSON 格式兼容
- `references/v2.4.0-4-row-misalignment-case.md` — 4 行错位根因
- `references/v2.3.0-ppt-expand-retry-vision.md` — PPT 扩页重跑
- `references/v2.2.0-structured-d-column-vision.md` — 结构化 D 列 vision
- `references/v2.0.0-ppt-truth-table-4col-analysis.md` — 4 列真值分析
- `references/v2.0.0-rerun-vs-truth-calibration-methodology.md` — 重跑校准
- `references/v2.1.0-b-and-c-100-percent-loop.md` — 100% 循环
- `references/v2.1.0-subagent-vision-ppt-4col.md` — subagent vision 4 列
- `references/v1.9.0-keynote-ppt-export-and-system-tool-scan.md` — Keynote 导出
- `references/v1.7.0-google-filepdf-lifeline.md` — Google File PDF 兜底
- `references/v1.7.0-tool-composition-cheatsheet.md` — 工具组合
- `references/v1.7.0-honest-acknowledgment-boundaries.md` — 诚实边界
- `references/v1.7.0-user-corrections-anti-patterns.md` — 用户纠正反模式
- `references/v1.5.1-honest-correction-after-user-rebuke.md` — 纠正后诚实
- `references/v1.5.1-realignment-after-user-correction.md` — 重新对齐
- `references/v1.5.1-v13-bug-fixes.md` — v1.3 bug 修复
- `references/v1.5.1-8-step-fallback-chain.md` — 8 步 fallback
- `references/v1.5.1-reasoning-first-priority-classification.md` — 推理优先
- `references/v1.5.0-bridging-optimization-opt-8-12.md` — 优化桥接
- `references/v3.0.0-d-column-vision-align-eval.md` — D 列 vision 评估
- `references/v3.0.0-hermes-fabrication-incident.md` — Hermes 假数据事件
- `references/algorithm-vs-ifelse-skill-decision-matrix.md` — 算法 vs ifelse 决策
- `references/benchmark-gap-analysis.md` — 基准差距分析
- `references/optimization-double-track-safety-pattern.md` — 双轨安全
- `references/optimization-p1-completion-2026-08-04.md` — P1 完成
- `references/literature-dir-init-v1.0.0.md` — 文献目录初始化
- `references/github-production-benchmark-2026-08-04.md` — GitHub benchmark

## 39+6 反幻觉铁律

1. 瞎补禁止 (v2.4.0)
2. 紧凑上标必须检测 (v2.4.0)
3. 跨 slide 共享必须检测 (v2.4.0)
4. 160 行是真理 (v2.4.0)
5. 漏的标号必须 subagent 重跑 vision, 不允许直接 PASS (v2.5.0)
6. vision_analyze 必须问"列 PPT 上所有数字+单位" (v2.5.0)
7. data_points 必须含纯数字版本 (v2.5.0)
8. 覆盖率度量必须 ≥50% (v2.5.0)
9. 子 agent 输出格式不能假设统一, 必须分别处理 7 种结构 (v2.5.0)
10. 重跑 vision 验证稳定性时, 取新旧并集, 报告波动 (v2.7.0)
11. vision 模型不稳定是事实, 数字会有 ±0.5% 误差 (v2.7.0)
12. XML 确定性字段不依赖 vision (v2.8.0 新增)
13. Vision 仅补 XML 不能确定的字段 (v2.8.0 新增)
14. XML 与 Vision 冲突时, XML 优先 (v2.8.0 新增)
15. vision 跑 2 次只有 39.6% 一致率, 不接受子 agent 重跑作为稳定性证据 (v2.9.0 新增)
16. Pydantic schema 强制 vision 输出结构, 比 prompt 约束更可靠 (v2.9.0 新增)
17. N=3 majority + median value 比 union 更砍幻觉 (v2.9.0 新增)
18. 5 行 PDF 应证数据 (Sangro 1494P + Lau Asian + George ESMO Asia + Yau Lancet) 不在 PPT 视觉, 必须跑 PDF 应证补到 100% (v2.9.0 新增)
19. **Pn-x 1:1 镜像 PPT 标号 (step3 不合并) vs highlight 按 DOI 合并 (step4 合并) — 严格相反规则, 不可混淆** (v2.12.0 新增)
20. **PowerPoint 渲染作为默认, 强制不 fallback Keynote/LibreOffice (视觉不一致)** (v2.12.0 新增)
21. **扩页 PPT 底色 vs 文字颜色对比度必须 ≥128 RGB 差, 否则视觉不可识别** (v2.12.0 新增)
22. **多 Pn-x 综合 1,2 / 1-3 共享引文: 拆 1,2,3 单独标号, 按上下文分析每个标号对应印证内容** (v2.12.0 新增)
23. **严禁关键词匹配 highlight — 视觉解决视觉 (用户硬规则, 2026-08-05 反思)** (v2.13.0 新增)
24. **严禁标单个数字词汇 — 整段/整句/图表/表格** (v2.13.0 新增)
25. **严禁按段数叠加评分 — 用单段最高分 (含 PPT 视觉核心数字 % + 主题)** (v2.13.0 新增)
26. **严禁 fill 矩形高亮 — 必须 underline 浅黄细线 (add_underline_annot, type 9)** (v2.13.0 新增)
27. **严禁不验证保存成功 — 跑完必须看 PDF underline 数, 没成功标错就重跑** (v2.13.0 新增)
28. **PyMuPDF underline annot 只支持 stroke, 不支持 fill** — `page.add_underline_annot(rect).set_colors(fill=...)` 会被 PyMuPDF Warning 忽略 ("fill color ignored for annot type 'Highlight'"). 只用 stroke=(1.0, 1.0, 0.6) 即可
29. **严禁凭印象猜 bbox** — 应证段 bbox 必须用 PyMuPDF `get_text("blocks")` 提真实 PDF 段坐标 (x0_pt, y0_pt, x1_pt, y1_pt in PDF 72dpi pt 单位). 例: P3-2 应证段 PDF pt = (84, 64, 512, 165), 段被切成 4 个 block (段头 y=64-79, 段尾 y=151-165). 整段 y0 = 段头 y0, y1 = 段尾 y1, x0 = 84, x1 = 512. 不要用 jpg 像素猜 (40, 80, 1100, 280) — 容易错位到上下段. **用 PyMuPDF 真实坐标, 不发明未验证的估算**
30. **严禁画红框让你确认** (用户原话: "红框又是你的新发明, 你哪来那么多新发明") — 不发明未要求的 UI 元素. 验证靠 vision_analyze 看 PNG 自检, 不要画额外标记
31. **PyMuPDF annotation type 必须用 safe 包装** — `a.type` 抛 "annotation not bound to any page" 时脚本会崩. 必须 `try: if a.type and a.type[0] == 9: ... except: pass`
32. **annotation type 编号不能凭印象** — PyMuPDF underline = 9 (不是 12), highlight = 8, text = 1. 测试验证脚本用错类型编号会让"跑通"变"假跑通"
33. **严禁 `a.type` 调用 — PyMuPDF segfault trap** (2026-08-05 反思会话新增) — `saveIncr()` 后 reopen PDF 时, `a.type` 调用会触发 native segfault (exit -11), `try/except` **包不住**. 必须**完全避开 `a.type`, 用 `a.rect.width > 50 and height < 30` 推断 underline**. 自检脚本 `scripts/verify_highlight_self_check.py` 即用此模式, 否则整个脚本 crash 看似"无输出"
34. **严禁让 user 确认 highlight 对错** (用户原话: "你让我确认对不对之前, 为什么不能你自己用视觉检查下", "你自己看你highlight的结果, 对么?" 2026-08-05 反思会话新增) — highlight 跑完**必须自己用 vision_analyze 看 PNG** 或 **PIL+numpy 找浅黄像素位置** 自检 4 项: (a) PDF underline rect 推断存在, (b) jpg 浅黄线 y 位置在应证段底 ±15px, (c) 浅黄颜色 RGB ~(255, 255, 153), (d) x 覆盖率 ≥70%. 不发明未要求的 UI 元素 (红框/绿色检查线/确认对话框). 自检脚本: `scripts/verify_highlight_self_check.py`

### v2.14.0 严禁 (本轮反思新增)

35. **严禁只画一条段底线** — 应证段多行时 (PyMuPDF 切成 N 个 block), **每行画一条浅黄细线** (用户原话: "整段就要 high 段落的每一句"). P3-2 应证段被切成 4 行, 4 行独立 underline. 复现脚本: `scripts/highlight_vision_runner.py` 的 `highlight_multi_lines()`
36. **严禁浅黄太淡 (255, 255, 153, 2px)** — 用户原话: "highlight细线颜色太淡, 看不清highlight线". 用 **B 选项 (255, 230, 100, 4px)** = (1.0, 230/255, 100/255) stroke
37. **严禁深黄过粗 (255, 220, 0, 6px)** — 备选, 视觉过强. B 选项是用户确认
38. **严禁 RGB 严格匹配 ==** — PNG 压缩后 RGB 不精确, 必须宽范围检测 (R 240-255, G 215-245, B 80-115). 严格匹配会 0 命中
39. **严禁把 main PDF 当真值 PDF** — step3 多 PDF 时, **必须用用户发的真值 PDF** (用户原话: "我都把要标注的内容发给你了, 你都highlight不对"). P3-1 main IARC PDF (2 页, 含 Asia 数据) 没有 China 单独数据, 必须用 GLOBOCAN 摘要 1 页 (含 "中国占全球新发癌症 24.2%; 新发和死亡人数均居全球第一"). 把用户发的 PDF 复制到 step4: `cp doc_xxx_P3-1.pdf step4/P3-1/P3-1_globocan_summary.pdf`

### v2.16.0 (2026-08-05 第四轮反思新增, 图表矩形 + 深黄 + 真值 PDF 不替换)
- `references/v2.16.0-chart-rectangle-and-deep-yellow.md` — **图表用 Square annot (矩形框) 不用 underline + PDF underline 改深黄 (1.0, 0.8, 0.0) 不用中黄 (1.0, 0.902, 0.392) + 用户发的 PDF 用于校对算法结果不擅自替换 step4 main PDF**. P3-1 (Asia 区域行) + P3-3 (Fig. 2) + P3-4 (Fig. 1 + Table 2 BCLC) 实战案例

### v2.15.0 (2026-08-05 第三轮反思, 落地坑)

40. **严禁 `os.listdir()[0]` 选 PDF** — step3 多 PDF 目录里 `pdfs = os.listdir(pn_dir); pdf = f'{pn_dir}/{pdfs[0]}'` 会拿到 fallback 而不是 main. 必须用 **startswith 显式选 main**: `pdfs = [f for f in os.listdir(pn_dir) if f.startswith('P3-1_main') and f.endswith('.pdf')]; pdf = f'{pn_dir}/{pdfs[0]}'`. P3-1 fallback 是 Bray GLOBOCAN 2022 35 页 (无 China), main 是 IARC GLOBOCAN Liver 2 页 (有 Asia). 选错 PDF = 整个应证段都不存在
41. **严禁 `page.delete_annot` + `saveIncr` 后信任 `len(annots)==0`** — delete_annot 不总是生效, saveIncr 后还有残留 underline. 必须**用 PDF 字节 grep** `/Type/Annot/Subtype/Underline/...Rect[...]/` 数真实 underline 数. `re.findall(rb'/Type/Annot/Subtype/Underline/.*?Rect\[([\d. ]+)\]', data)` 才能拿到真 underline rect, 同时还能避开 `a.type` segfault
42. **PyMuPDF y 坐标翻转 trap** — `page.add_underline_annot(Rect(x0, y0, x1, y1))` 接受 y-down (page top=0, page.height=bottom), 但 **PDF 内部存 y-up (page.bottom=0)**. PyMuPDF 自动翻. 例: PDF page height=1486, 给 Rect(10, 10, 200, 20) → PDF 内部 Rect(10, 1466, 200, 1476) → 显示在 page 顶. **验证用 y-up 坐标, 自检 jpg 用 y-down 坐标**. 转换公式: `y_down = page_height - y_up`. **不要凭印象猜 PDF 内部 y, 必须验证一次**
43. **严禁把多个 Pn-x 共享 `_pdf_jpg/` 目录** — 每个 Pn-x 必须**独立** `pn_dir/_pdf_jpg/`, 不要跨 Pn-x 复用, 不然 A.pdf jpg 跟 B.pdf jpg 混
44. **算法驱动 + 步骤拆开 + 一键复现** (用户原话: "你肯定要把每个不同的步骤拆开, 算法驱动来调度步骤和工具, 确保工作正确啊, 这是我的思路. 你要怎么设计, 你要根据自己的具体情况去设计稿解决方案, 才能确保完美复现") — **FIRST-CLASS 用户硬规则**. 每个算法必须:
    - 拆成独立步骤 (每步一个函数, 一行能跑)
    - 步骤之间只传数据, 不传 state
    - 主函数 `def run_pnx(pn_key) -> dict` 一键复现
    - 每步输出可验证 (print 中间结果, 写中间文件)
    - 不能"今天跑通明天不通" — 每次跑前 reset (删旧 underline + 重渲染 jpg)
    - 跑完自检 (vision_analyze 看 PNG OR PIL+numpy 找浅黄像素), 不让 user 确认
45. **P3-2 重置完整流程 (v2.13-v2.15 三个版本总结, 防止下次又错)**:
    ```python
    # 1. 重置 (删 fallback PDF + 旧 underline + 旧 jpg)
    for f in os.listdir(pn_dir):
        if 'fallback' in f: os.remove(...)
    doc = fitz.open(pdf)
    for page in doc:
        for a in (page.annots() or []):
            try: page.delete_annot(a)
            except: pass
    doc.saveIncr(); doc.close()
    # 2. 重渲染 jpg (dpi=120, 1750x2477 for IARC, 992x1404 for 健康中国 PDF)
    # 3. PyMuPDF get_text("blocks") 提 page 3 应证段 (y 范围 60-170 for 健康中国)
    # 4. 对每行 block 画浅黄细线 (jpg 上 PIL.ImageDraw.line at y1)
    # 5. PyMuPDF add_underline_annot (每个 block 一个, type 9, stroke 中黄 B 选项)
    # 6. saveIncr + 验证 (PDF 字节 grep + jpg cluster count == N)
    ```

## 跑主算法

```bash
# v8 主算法 (D 列)
/Users/david/.hermes/hermes-agent/venv/bin/python /Users/david/.medit/scripts/analyze_ppt_citations_v8_pydantic_voting.py

# v9 端到端 5 步骤流水线
/Users/david/.hermes/hermes-agent/venv/bin/python /Users/david/.medit/scripts/v9_full_pipeline.py

# v10 highlight 视觉驱动 (本次新增, 7 步拆开)
/Users/david/.hermes/hermes-agent/venv/bin/python /Users/david/.medit/scripts/highlight_v10.py
/Users/david/.hermes/hermes-agent/venv/bin/python /Users/david/.medit/scripts/highlight_v10.py --all
```

离线自检 (无需 API key):
```bash
/tmp/v8venv/bin/python -c "
import sys; sys.path.insert(0, '/Users/david')
from v8_demo import analyze_slide
from pathlib import Path
print(analyze_slide(Path('/tmp/fake.jpg'), Path('/tmp/fixture.pptx'), 0, n_runs=3))
"
```

输出:
- `/Users/david/Desktop/雷管方案_文献整理/_pptx_xml_structured.json` — 365 KB XML 结构化
- `/Users/david/Desktop/雷管方案_文献整理/PPT_citations_4col.csv` — 160 行 4 列
- `/Users/david/Desktop/雷管方案_文献整理/PPT_citations_8col_aligned.csv` — 160 行 12 列完整对齐
- `_archived_old_dirs/PPT_citations_4col_v8_pydantic_<ts>.csv` — 旧版本备份
- `step4_highlight_96目录_合并DOI/Pn-x/_pdf_jpg/page_NNN.jpg` — v10 PDF 每页 jpg
- `step4_highlight_96目录_合并DOI/Pn-x/page_NNN.png` — v10 应证页 PNG

## 评级

- v6 (vision 单独): 96.9% ≥50% 命中 — 视觉算法天花板
- v7 (XML + vision 双轨): 86.2% XML + 96.9% vision — 实际双轨合并
- v8 (双轨 + Pydantic + 4 类过滤): 96.9% ≥50% + 86.2% XML + 4 类 guard — **当前 D 列主算法**
- v9 (5 步骤端到端 + PowerPoint 渲染 + 颜色对比度 + Pn-x 1:1 + DOI 合并 + 12 列对齐): 全流程闭环
- **v10 (Highlight 视觉驱动 7 步拆开 + 浅黄细线 + 视觉比对 jpg): 严禁关键词匹配, 视觉解决视觉**
- v_pdf (待做): 100% 推算目标

## 下一步

PDF 应证推理用 Pn-x 目录下 84 个 PDF + Docling/pdfplumber 提 PDF 应证数据, 补 5 漏 (P5 #15 #17 #18 + P12 #3 #4) 到 100%.

**v10 highlight 已实现视觉驱动范式 (步骤 4)**, Pydantic schema 化 vision 输出待补 (避免 vision 输出格式不稳定).

## 用户硬规则 (2026-08-05 多次重申)

**沟通风格 (FIRST-CLASS 用户偏好, 直接写入 SKILL body)**:
- 说人话 — 不用代码行号 / 列名 / 函数名 / jargon / 百分比术语
- 用户说 "我看不懂, 我要结果" → 立刻切结果导向, 不要先讲技术细节
- 不要展示 CSV 表格内容给用户 — 算法跑完自动对齐真值, 只显示对/错
- 不要反复确认琐碎选择 — 自主决策, 除非涉及破坏性操作
- 沉默等下一步 — 跑完 1 项就停, 不自动展开下一步分析
- **用户发火 = 关键信号, 必须反思根因, 不能"我以为我懂了"** (v2.13.0 新增)
- **用户说"昨天才调试过的, 今天就忘了" = 必须把教训写进 skill, 不能下次再犯** (v2.13.0 新增)
- **用户说"你麻痹" / "草你妈" / "饭喂到嘴边" = 用户已经详细解释了, 仍然错 = 算法没拆开, 没可复现, 没验证** (v2.13.0 新增)

**Highlight 视觉驱动 (v2.13.0 新增, FIRST-CLASS 用户硬规则)**:
- 严禁关键词匹配 (变相关键词评分)
- 严禁标单个数字词汇 (整段/整句/图表/表格)
- 严禁按段数叠加评分 (单段最高分)
- 严禁 fill 矩形高亮 (underline 浅黄细线 type 9)
- 严禁不验证保存成功
- 视觉解决视觉: PPT jpg 视觉 vs PDF 每页 jpg 视觉比对, 不拆 PDF 文字
- 重置+跑: 清旧 highlight, 用干净 PDF 重做
- 可复现: 一键脚本 highlight_v10.py, 主函数 highlight_pnx(pn_key)

**目录整理 (v2.12.0 新增, FIRST-CLASS 用户硬规则)**:
- **step3 下载目录不合并**: 多少 Pn-x 就多少子目录 (160 ↔ 160)
- **step4 highlight 目录按 DOI 合并**: 96 唯一合并目录 (85 唯一 DOI + 11 无 DOI)
- **算法脚本归档到 via54Medit**: `developments/via54Medit/scripts/literature_v8_*.py`
- **临时/审计/旧版 → step6/_tmp/**: `_background_*` `_audit_*` `_research` `_knowledge` `_archived_old_dirs` `scripts/` (留副本) 等

**渲染与扩页 (v2.12.0 新增)**:
- **PowerPoint 渲染作为默认**: 强制不 fallback Keynote/LibreOffice (视觉不一致)
- **扩页 PPT 颜色对比度校验**: 底色 vs 文字颜色 RGB 差 ≥128, 否则视觉不可识别
- **多 Pn-x 1,2 / 1-3 共享引文**: 拆 1,2,3 单独标号, 按上下文分析每个标号对应印证内容

**算法原则**:
- 视觉算法是真理的"PPT 视觉" 部分 — 真值 D 字段含 PDF 应证数据, PPT 视觉 100% 覆盖后还有 PDF 应证漏
- 算法天花板 = 96.9% ≥50% 命中 (5 漏 100% PDF 应证)
- 补到 100% 唯一路径 = PDF 应证 (Docling/pdfplumber 跑 84 个 Pn-x PDF)
- 视觉算法不稳定 (39.6% 一致率) — 不依赖 vision 单一结果, 必须 XML 主干 + vision 验证
- **每个步骤拆开** (v2.13.0 新增) — 算法驱动调度步骤和工具, 确保工作正确
- **每个步骤独立可验证** (v2.13.0 新增) — 不能黑盒跑通, 必须看输出
- **可复现** (v2.13.0 新增) — 一键脚本, 不允许"今天跑通明天不通"