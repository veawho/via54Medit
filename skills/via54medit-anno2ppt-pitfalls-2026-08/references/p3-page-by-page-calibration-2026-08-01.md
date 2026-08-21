# P3 4 标号逐标号校准 — 2026-08-01 完结

> 配套 skill: `via54medit-anno2ppt-pitfalls-2026-08` (Pitfalls 27-33)
> 关联 skills: `slide-by-slide-ppt-citation-audit` v2.0, `via54medit-anno2ppt-phase7`, `citation-table-cell-truthflow` v1.7

## 背景

**用户原话** (2026-08-01 session):

1. "文字说明和图片对应不上" + "PPT 图表中举例的几个癌肿只是因为图表容量有限, 所以给出了几个常见癌肿, 并不是要求只标注这几个, 只有标注了所有比肝癌的 14.4 高的癌肿"
2. "页面中有 4 个标号才对啊" — P3 实际有 4 个标号 (1, 2, 3, 4), 不是 3 个
3. "为什么又出现了本地文件与飞书文档（逐页引用表）不一致的情况" — P3-1 完全没在 CSV
4. "为什么本地不能和飞书一样有表头呢" + "确保以后做其他文献整理时也能有表头"
5. "回到刚才的工作，一页一页处理PPT" — 触发本次逐标号校准

## 4 标号实况 (P3)

| # | Pn-x | PPT 位置 | PPT 语义 | 高亮图 | 状态 |
|:-:|:----:|:--------:|---------|:------:|:----:|
| 1 | P3-1 | 左半区主标题 | GLOBOCAN 2020 China 36.8万/42.5% | 2 张 (Kudo HBSN OS/ORR) | ⚠️ **错位** |
| 2 | P3-2 | 右半区主标题 | 健康中国2030 → 46.6% | 1 张 (page3) | ✅ |
| 3 | P3-3 | 右半区中部小标题 | 肝癌 14.4%, 远低于其他癌种 | **3 张** (page1+4+5) | ✅ v4.1 修复后 |
| 4 | P3-4 | 右半区右下小标题 | 中晚期肝癌拉低生存率 | 3 张 (page1+2+4) | ✅ |

## Step 0: 标号总数核对 (Pitfall 22)

**用户纠正** "页面中有 4 个标号才对啊" — 我之前以为 P3 只有 3 个标号, 漏了 P3-1 标号 1.

**强制 SOP**:
```python
import subprocess, json

def feishu_get_page_rows(page):
    r = subprocess.run([
        '/Users/david/.hermes/node/bin/lark-cli', 'sheets', '+cells-get',
        '--spreadsheet-token', '<FEISHU_SHEET_TOKEN>',
        '--sheet-id', 'b03e59',
        '--range', f'A{page}:H161',
        '--include', 'value',
    ], capture_output=True, text=True, timeout=60)
    data = json.loads(r.stdout)
    rows = data['data']['ranges'][0]['cells']
    return [r for r in rows if r and r[0].get('value', '').strip() == str(page)]

fs_rows = feishu_get_page_rows(3)
mark_set = set(int(r[1].get('value', '0').strip()) for r in fs_rows
               if r[1].get('value', '').strip().isdigit())
print(f"P3 标号: {sorted(mark_set)}")
# 期望: {1, 2, 3, 4} (4 个标号)
```

## P3-1 详细诊断 (Pitfall 27 + 31)

### 飞书表 D 列原文 (Row 2)

```
PPT标号1: 出现在 1 个位置 (左半区域主标题)
位置1: 「中国肝癌新发和死亡病例占全球近半数1」(P3 左半区主标题文字框)
关联图表与数据 (视觉得到):
- 图表 1: 新发病例占比 饼图 — 中国 42.5% / 其他国家 57.5%, 引线指向 "中国 42.5%" 标签
- 图表 2: 死亡病例占比 饼图 — 中国 41.7% / 其他国家 58.3%, 引线指向 "中国 41.7%" 标签
- 右侧数据 (3 个圆环图标): 36.8万 (中国肝癌发病人数), 42.5% (发病人数在全球占比), 31.7万 (中国肝癌死亡人数), 41.7% (死亡人数在全球占比)
- 引线标签: "全球86.6万" (新发总数), "全球75.8万" (死亡总数)
引文: The Global Cancer Observatory 2022 (GLOBOCAN) — IARC
```

### Crossref DOI 验证

```python
import urllib.request, json
data = json.loads(urllib.request.urlopen(
    'https://api.crossref.org/works/10.3322/caac.21834'
).read())
# 标题: "Global cancer statistics 2022: GLOBOCAN estimates..."
# 期刊: CA: A Cancer Journal for Clinicians
# 出版年: 2024 (Bray F, Laversanne M, Sung H)
# Volume: 74
# → 论文是 2024 出版, 但 GLOBOCAN 数据是 2022 年
```

### 本地 P3-1 目录内容

```
P3-1_fallback_The_Journal_2022.pdf (714 KB) → GLOBOCAN 2024 China, 5,150,572 总数
P3-1_fallback_The_Journal_2022_GLOBOCAN_2022_BrayF.pdf (4816 KB) → GLOBOCAN 2022 全文
P3-1_main_Kudo_HBSN_2022.pdf (157 KB) → Kudo HBSN 2022 Editorial, HIMALAYA OS/ORR
```

### 3 个数据版本冲突

| 数据源 | 实际数据 | 时序 |
|------|---------|------|
| 飞书 D 列 | 36.8万/42.5%/31.7万/41.7% | GLOBOCAN **2020** China |
| 飞书 DOI | 10.3322/caac.21834 | GLOBOCAN **2022** (Bray 2024 出版) |
| 本地 main | Kudo HBSN 2022 Editorial | 完全无关 (HIMALAYA OS/ORR) |
| 本地 fallback | GLOBOCAN 2024 China 速览 | GLOBOCAN **2024** (2 页摘要) |
| 本地 fallback | GLOBOCAN 2022 全文 | GLOBOCAN **2022** (Bray 2024, 35 页) |

**结论**: 飞书 D 列数据时序 (2020) + 飞书 DOI 时序 (2022) + 本地 PDF 时序 (2022+2024) — **三方错位**

### 算法 l4_allegation 错误 (v3.x)

```json
"l4_allegation": [
    "P3左半区标号1: ORR数据 (30% vs 20%)",
    "ORR was better in the Atezo/Bev group (30% vs. 20%)",
    "the duration of the response was longer in the STRIDE regimen group (22.34 months)"
],
"l4_key_terms": ["30%", "20%", "22.34", "18.1", "ORR", "Atezo/Bev", "STRIDE", "duration of response"]
```

**问题**: 我凭印象 (本地有 Kudo_HBSN_2022.pdf) 编造 ORR 数据, 实际飞书 D 列是 GLOBOCAN 36.8万/42.5%.

### 修复决策树 (3 选 1, 待用户决策)

- **A. 修飞书 D 列** → 改成 Kudo HBSN 2022 (HIMALAYA OS/ORR) — 改最少, 但丢 GLOBOCAN 数据
- **B. 修本地 PDF** → 删 Kudo HBSN, 补 GLOBOCAN 2020 China PDF (DOI 10.3322/caac.21654) — 找 2020 论文
- **C. 都修** → 飞书改成 GLOBOCAN 2022 (Bray 2024 caac.21834), 本地保留 GLOBOCAN 2024 China fallback

## P3-3 集合结论推理修复 (Pitfall 28)

### 用户原话

> "PPT 图表中举例的几个癌肿只是因为图表容量有限, 所以给出了几个常见癌肿, 并不是要求只标注这几个, 只有标注了所有比肝癌的 14.4 高的癌肿"

### v4.0 vs v4.1 对比

| 版本 | 高亮 | 覆盖 |
|------|------|------|
| **v4.0 (修前)** | page1 (Abstract 数字) + page4 (Fig.2 27 标签) | 5 种 PPT 列举的癌肿 |
| **v4.1 (修后)** | + page5 (Table 2 整表) | **26 种**癌肿 (24 高 + 1 等 + 1 低) |

### 26 种癌肿分析 (全部 > 14.4% 黄色高亮, 基准 + 低于 = 橙色)

| 癌肿 | 5年生存率% | vs 14.4% | 高亮 |
|------|:----------:|:--------:|:----:|
| Liver (肝癌) | 14.4 | = | 🟠 |
| Pancreas (胰腺癌) | 8.5 | < | 🟠 |
| Gallbladder | 17.8 | > | 🟡 |
| Esophagus | 27.9 | > | 🟡 |
| Lung | 28.7 | > | 🟡 |
| Leukemia | 30.6 | > | 🟡 |
| Stomach | 35.2 | > | 🟡 |
| Brain | 37.7 | > | 🟡 |
| Bone | 39.5 | > | 🟡 |
| Ovary | 39.6 | > | 🟡 |
| Other thoracic | 40.1 | > | 🟡 |
| Lymphoma | 40.8 | > | 🟡 |
| Oral/Pharynx | 47.0 | > | 🟡 |
| Melanoma of skin | 50.3 | > | 🟡 |
| All others | 52.2 | > | 🟡 |
| Larynx | 52.9 | > | 🟡 |
| Colon-rectum | 55.7 | > | 🟡 |
| Nasopharynx | 56.2 | > | 🟡 |
| Kidney | 65.2 | > | 🟡 |
| Cervix | 66.9 | > | 🟡 |
| Uterus | 68.1 | > | 🟡 |
| Prostate | 71.1 | > | 🟡 |
| Bladder | 71.5 | > | 🟡 |
| Testis | 80.7 | > | 🟡 |
| Breast | 80.9 | > | 🟡 |
| Thyroid | 92.9 | > | 🟡 |

**统计**: 24 种 > 14.4% (🟡) + 1 种 = 14.4% (Liver, 🟠) + 1 种 < 14.4% (Pancreas 8.5%, 🟠)

**L4 集合结论推理得分**: 0.95

### 修复代码 (P3-3 page5 Table 2 整表高亮)

```python
import fitz
from PIL import Image, ImageDraw

doc = fitz.open(PDF_PATH)
page = doc[4]  # page5 (0-indexed)
mat = fitz.Matrix(1.5, 1.5)
pix = page.get_pixmap(matrix=mat)
img = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
draw = ImageDraw.Draw(img)

def hl(y0, x0, y1, x1, color):
    s = 1.5
    draw.rectangle([int(x0*s), int(y0*s), int(x1*s), int(y1*s)], fill=color)

yellow = (255, 255, 0)
orange = (255, 165, 0)

# 26 行癌肿 y 坐标 (来自 PyMuPDF get_text("dict"))
rows = [
    (423, "Oral/Pharynx", True),     # 47.0%
    (431, "Nasopharynx", True),      # 56.2%
    (440, "Esophagus", True),        # 27.9%
    (448, "Stomach", True),          # 35.2%
    (457, "Colon-rectum", True),     # 55.7%
    (465, "Liver", False),           # 14.4% = 基准
    (474, "Gallbladder", True),      # 17.8%
    (483, "Pancreas", False),        # 8.5% < 14.4%
    (491, "Larynx", True),           # 52.9%
    (500, "Lung", True),             # 28.7%
    (508, "Other thoracic organs", True),
    (517, "Bone", True),             # 39.5%
    (525, "Melanoma of skin", True), # 50.3%
    (534, "Breast", True),           # 80.9%
    (543, "Cervix", True),           # 66.9%
    (551, "Uterus", True),           # 68.1%
    (560, "Ovary", True),            # 39.6%
    (568, "Prostate", True),         # 71.1%
    (577, "Testis", True),           # 80.7%
    (585, "Kidney", True),           # 65.2%
    (594, "Bladder", True),          # 71.5%
    (602, "Brain", True),            # 37.7%
    (611, "Thyroid", True),          # 92.9%
    (620, "Lymphoma", True),         # 40.8%
    (628, "Leukemia", True),         # 30.6%
    (637, "All others", True),       # 52.2%
]

for y, name, above in rows:
    color = yellow if above else orange
    hl(y-6, 110, y+9, 480, color)
```

### manifest v4.1

```json
"highlight_summary": [
    {"page": 1, "terms": 8, "hits": 11, "path": "P3-3_page1_highlight.jpg",
     "content": "Abstract: 43.3%/43.7%/8.5%/92.9%/60%/20%/46.6%"},
    {"page": 4, "terms": 27, "hits": 27, "path": "P3-3_page4_highlight.jpg",
     "content": "Fig.2(A): 27 cancer sites bar chart"},
    {"page": 5, "terms": 27, "hits": 52, "path": "P3-3_page5_highlight.jpg",
     "content": "Table 2: all 27 cancer sites (24 above-14.4 yellow, Liver=14.4 orange, Pancreas=8.5 orange)"}
],
"l4_key_terms": [8 关键词 + 26 百分比],  // 8 → 34
"l4_collection_conclusion": {
    "claim": "中国肝癌5年生存率仅14.4%, 远低于其他癌种",
    "total_cancers": 26,
    "above_14_4": 24,
    "equal_or_below": 2,
    "verdict": "应证成功 (0.95): 24种远高于, 1种(Liver)等于, 1种(Pancreas 8.5%)低于"
}
```

## L3 sensenova vision cascade (Pitfall 29)

### 3 级 cascade (scripts/vision_verify.py)

1. **sensenova-6.7-flash-lite** (主) — 免费 + 262K context + 无敏感词
2. **MiniMax-M3** (备) — 速度最快, 但经常 429 限流/2056 配额用尽
3. **PyMuPDF local** (兜底) — 只读 metadata, 无视觉理解

**注意**: sensenova API 名是 `sensenova-6.7-flash-lite` (小写), 不是 `sense` / `MiniMax-VL-01`

### P3 4 标号 cascade 验证结果

| 标号 | highlight 图 | 结果 | 验证内容 |
|:----:|-------------|:----:|----------|
| 2 | P3-2_page3 | ✅ | sensenova 正确识别 46.6% + 80% |
| 3 | P3-3_page1 | ✅ | sensenova 正确识别 8 个 Abstract 数字 |
| 3 | P3-3_page4 | ✅ | sensenova 正确识别 27 个癌肿名 + 数值 |
| 3 | P3-3_page5 | ✅ | sensenova 确认黄色 + 橙色高亮分布 |
| 4 | P3-4_page1 | ✅ | sensenova 正确识别分期生存率 (49.3/35.3/26.6/19.5) |
| 1 | P3-1_page1 | ❌ | sensenova 描述 HIMALAYA OS/ORR — **与飞书 D 列 GLOBOCAN 不一致** |

**关键发现**: sensenova cascade 暴露了 P3-1 错位 — 高亮是 HIMALAYA 数据, 飞书 D 列是 GLOBOCAN 数据

## CSV 8 列表头铁律 (Pitfall 30)

### 触发场景

用户原话: "为什么本地不能和飞书一样有表头呢" + "确保以后做其他文献整理时也能有表头"

### 8 列固定表头 (frozen 2026-08-01)

```
PPT页,第几条,引用语义（上下文）,PPT中的文献引用 完整字段,DOI,类型,对应PDF文件,来源链接 → 阅读全文
```

### 双端守门员

**Go**: `via54Medit/internal/citation/sync/csv_sync.go` (14 单测 100% PASS)
**Python**: `via54Medit/scripts/csv_feishu_sync.py` (validate + sync 子命令)

### 修复后状态

| 指标 | 数值 |
|------|------|
| CSV 总行数 | 161 (1 表头 + 160 数据) |
| 飞书数据行 | 161 |
| 7 列校核一致 | 152/160 (95%) |
| 剩余差异 | 8 个本地 PDF 命名 (`_main_` 前缀) |

## lark-cli 关键参数 (Pitfall 32)

```bash
# ✅ 正确
lark-cli sheets +cells-get \
  --spreadsheet-token <FEISHU_SHEET_TOKEN> \
  --sheet-id b03e59 \
  --range A2:F2

# ❌ 错误 (1310251 invalid request)
lark-cli sheets +cells-get \
  --spreadsheet-token b03e59 \
  --sheet-name "逐页引用表"
```

| 参数 | 含义 | 雷管方案 |
|------|------|----------|
| `--spreadsheet-token` | 整表 ID | `<FEISHU_SHEET_TOKEN>` |
| `--sheet-id` | 子表 ID | `b03e59` |

## 7 步逐标号校准 SOP (v4.1)

1. **Step 0 标号总数核对** — 拉飞书 → 数 mark → 确认 N 个
2. **Step 1 拉 CSV + manifest + highlight** — 3 个本地源
3. **Step 2 拉飞书 D/E/F/G/H 列** — 5 个飞书字段
4. **Step 3 GLOBOCAN/IARC 3 步版本诊断** — DOI 出版年 + D 列数据年 + 本地 PDF 年
5. **Step 4 sensenova vision cascade 复核 highlight** — 5-11s/次
6. **Step 5 集合结论推理展开** — N_high + N_low 全部高亮
7. **Step 6 报告 + 修复** — 标 ✅/⚠️/❌, 用户决策

## 算法升级方向 (via54medit-anno2ppt-phase7)

### L4 应证推理机加新维度

```go
type InformationElement struct {
    Geography, Disease, Indicator, Value, Conclusion, Unit string
    ValueNum float64
    DataYear      int  // 新增: D 列数据采集年份
    DOIYear       int  // 新增: DOI 出版年份
    LocalFileYear int  // 新增: 本地 PDF 内容年份
}

func TemporalConsistencyScore(e InformationElement) float64 {
    score := 1.0
    score -= float64(abs(e.DataYear - e.DOIYear)) / 10
    score -= float64(abs(e.DataYear - e.LocalFileYear)) / 10
    return max(0, score)
}
```

### 6 条未来 SOP 铁律

1. **新 PPT audit 必先 Step 0 标号总数核对** (防漏标号)
2. **补录 row 前必先 lark-cli +cells-get 拉飞书真值** (防凭印象)
3. **highlight 必过 sensenova vision cascade 复核** (防标错)
4. **"远低于 X" 集合结论词必读 PDF Table 全量展开** (防标少)
5. **GLOBOCAN/IARC 类数据源必 3 步版本诊断** (防引用错位)
6. **新项目 citation_table.csv 必从模板复制, 含 8 列表头** (防错位 1 行)
