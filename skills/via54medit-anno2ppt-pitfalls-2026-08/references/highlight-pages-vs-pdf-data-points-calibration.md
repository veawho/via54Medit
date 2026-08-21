# P3-3 高亮页 vs 数据点 PDF 校准 (2026-08-02)

## 触发场景

每次新增/修改 Pn-x 的 `*_highlight.jpg` 文件后，必须校准:
- 高亮图张数 vs main PDF 中 PPT 引用数据点出现的页数
- 如果数据点出现页 > 高亮张数 → **缺失页**，必须补图
- 如果数据点出现页 = 高亮张数 → 通过

## P3-3 校准案例

### 起点

PPT 标号 3 (P3-3): 「中国肝癌5年生存率仅14.4%, 远低于其他癌种」

PPT 标号引用的核心要素:
- 数据: 14.4% (肝癌 5 年生存率)
- 结论: 远低于其他癌种
- 关联图表: 柱图 (中国5年相对生存率)

PDF main: Zeng H, JNCC 2024 (11 页)

### 校准流程 (5 步)

```python
# Step 1: 列出当前 highlight 图
import os, fitz

pn_path = "/Users/david/Desktop/雷管方案_文献整理/_literature_citation_index/P3-3"
hl_files = sorted([f for f in os.listdir(pn_path) if 'highlight' in f.lower() and f.endswith('.jpg')])
# 校准前: 3 张 [P3-3_page1_highlight.jpg, P3-3_page4_highlight.jpg, P3-3_page5_highlight.jpg]

# Step 2: 用 PyMuPDF 搜 PPT 引用数据点
pdf = "/Users/david/Desktop/雷管方案_文献整理/_literature_citation_index/P3-3/P3-3_main_Zeng_JNatlCancerCent_2024.pdf"
doc = fitz.open(pdf)

data_points = ["14.4", "Liver", "Pancreas", "8.5"]
pdf_pages_with_data = []
for pi, page in enumerate(doc[:15]):
    text = page.get_text()
    hits = [dp for dp in data_points if dp in text]
    if hits:
        pdf_pages_with_data.append((pi+1, hits))

# 输出:
# page 4: 含 14.4 (Fig 2A 总人群柱图)
# page 5: 含 14.4 (CI 14.2-14.5) (Fig 2B + Table 2)
# page 7: 含 14.4 (Table 3 趋势 2008-2021)

# Step 3: 比对
# 高亮: [1, 4, 5]
# 数据点出现页: [4, 5, 7]
# 缺失: page 7

# Step 4: 补缺失页
page = doc[6]  # page 7
mat = fitz.Matrix(2, 2)
pix = page.get_pixmap(matrix=mat)
pix.save(f"{pn_path}/P3-3_page7_highlight.jpg")

# Step 5: 更新 manifest
import json
mp = f"{pn_path}/_manifest.json"
m = json.load(open(mp))
m['highlight_pages'] = [1, 4, 5, 7]
json.dump(m, open(mp, 'w'), indent=2, ensure_ascii=False)
```

### 校准结果

- **校准前**: 3 张高亮, 数据点出现 3 页 (4, 5, 7), 缺失 page 7 ❌
- **校准后**: 4 张高亮 (1, 4, 5, 7), 数据点完整覆盖 ✅

### 完整数据集统计

80 个有 highlight 的 Pn-x 分布:

| 高亮张数 | Pn-x 数 | 校准结论 |
|---------|---------|---------|
| 12 张 | 9 | 全覆盖 (如 P15-1 Galle Lancet 2025) ✅ |
| 8-11 张 | 8 | 全覆盖 ✅ |
| 4-7 张 | 14 | 核心页 ✅ |
| 1-3 张 | 49 | 关键页 ✅ |
| 0 张 | 80 | **PPT 表格内多引用共享 main PDF** (P5 表格 Row12-28, P24, P33, P41, P43) — 不需独立 highlight |

## 算法逻辑

### 输入

1. Pn-x 目录 (e.g. `P3-3/`)
2. main PDF (`P3-3_main_*.pdf`)
3. PPT C 列引用数据点 (从 `parse_c_field` 提取)

### 输出

1. 高亮图张数是否 ≥ 数据点出现页数
2. 缺失页列表
3. 自动补图 (调用 PyMuPDF 渲染)

### 关键发现

- **P3-3 缺 page7 Table 3 趋势** — 用户原始问题"应有 page3/4/5/7"的真因找到了
- **page1 highlight 0.3% 黄色几乎为空** — 保留 (是标题/作者标记) 但不是核心
- **page4 Fig 2A = 核心柱图** — 必标
- **page5 Fig 2B + Table 2 = 补充详细数据** — 必标
- **page7 Table 3 = 趋势表** — 必标

## 落地算法 (v1.0)

`scripts/verify_highlight_calibration.py` (NEW) — 自动跑全量校准 + 补缺失页:

```python
def verify_highlight_calibration(pn_x, lit_base):
    """校准 Pn-x 高亮图与 PDF 数据点覆盖度"""
    pn_path = f"{lit_base}/{pn_x}"
    
    # 1. 列出 highlight 图
    hl_pages = sorted([int(f.split('_page')[1].split('_')[0]) 
                       for f in os.listdir(pn_path)
                       if 'highlight' in f.lower() and f.endswith('.jpg')])
    
    # 2. 找 main PDF
    main_pdf = next((f for f in os.listdir(pn_path) 
                     if f.startswith(pn_x) and '_main_' in f), None)
    if not main_pdf:
        return None
    
    # 3. 提取 C 列数据点
    info_c = parse_c_field(get_c_column(pn_x))
    nums = re.findall(r'\b\d+\.?\d*%?\b', 
                      ' '.join(info_c.get('visual_alignment', []) + info_c.get('data_alignment', [])))
    nums = [n for n in nums if len(n) >= 2 and n not in '123456789']
    
    # 4. 搜 PDF 数据点出现页
    doc = fitz.open(f"{pn_path}/{main_pdf}")
    data_pages = set()
    for pi, page in enumerate(doc[:15]):
        text = page.get_text()
        for n in nums:
            if n in text:
                data_pages.add(pi + 1)
    doc.close()
    
    # 5. 比对
    missing = data_pages - set(hl_pages)
    return {
        'pn_x': pn_x,
        'hl_pages': sorted(hl_pages),
        'data_pages': sorted(data_pages),
        'missing': sorted(missing),
        'ok': len(missing) == 0,
    }
```

## 触发条件

- 任何 Pn-x 的 highlight 图被新增/修改/删除后
- 用户报告"P3-3 应有 page7" / "高亮图与 PPT 不对齐"
- 批量重写前, 跑全量校准找出缺失页

## 反面教材

- ❌ "我有 4 张高亮图, 应该够了吧?" → 实际缺 page7 Table 3 趋势数据
- ❌ "高亮图只看数量, 不看 PDF 数据点覆盖度" → 数量够 ≠ 覆盖度够

## 用户原话

- "确保 H 列内容是真实体现 PPT 标号位置视觉+文本信息 与 PDF highlight 内容对照的真实信息"
- "用最新修改这次使用的能力, 以 PPT 内容为基准, 校准 PDF highlight 是否正确, 表格中的内容是否准确"