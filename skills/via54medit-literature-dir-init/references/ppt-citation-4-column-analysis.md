# PPT 引用 4 列分析 — Step 2 (2026-08-05 v1.0.0)

## 6 条规则 (用户原话 2026-08-05)

1. **文献标注 = 2 部分**: 引用序号 + slide 底部对应引用文献
2. **视觉分析所有元素可见性**, 底部引用文献超出页面 → 扩大 PPT, 文字颜色保持可见
3. **引用序号 → 相关 PPT 内容视觉+文字分析** → D 列
4. **A=slide 序号, B=slide 中的引用序号, C=对应引用序号的引用文献** (对齐后固定不变)
5. **D 列 = 暂定内容** (缺 PDF 校准, 后续可调)
6. **必走视觉**, 需导出图片 → 建 PPT 导出图片目录

## 实际触发场景

```bash
# Step 1: init_literature_dir.py (Step 1 skill)
# Step 2: 4 个脚本链式调用
python ~/.medit/scripts/expand_slide_for_visibility.py <pptx>        # 规则 #2
python ~/.medit/scripts/export_ppt_to_images.py <pptx> <img_dir>     # 规则 #6
python ~/.medit/scripts/analyze_ppt_citations.py \
    --pptx <pptx> --images <img_dir> --out <csv>                    # 规则 #3-5
```

## 4 步 pipeline

### 1. expand_slide_for_visibility.py (规则 #2)

**职责**: 检测底部超出, 扩大 PPT, 修正文字颜色

**检测算法**:
- 遍历所有 slide
- 找 `bottom > slide_height` 的 shape
- 新高度 = max(原底, 超出 shape 的 bottom) + 0.3" padding

**实测 (2026-08-05 雷管方案 PPT)**:
- 6 个 slide 有底部超出: P5 / P7 / P24 / P30 / P40 / P42
- P5 底部 8.02" (超 7.5" 0.52")
- 修复后: P5 新高度 8.32"

**文字颜色修正**:
- 检测 slide 背景色 (rgb)
- 计算对比度 (WCAG 公式)
- 低于 4.5: 反向建议 (黑底→白字 / 白底→黑字)
- 缺省: 000000 (黑), 不修改原文字

**硬规则**:
- **默认 dry-run** (不写文件, 只报告 plan)
- `--apply` 才写

**Bug 教训**: 之前我写过没测就真跑 → 制造问题. 现在 default dry-run 强制保护.

### 2. export_ppt_to_images.py (规则 #6)

**职责**: PPT → slide_001.jpg ... slide_043.jpg (视觉分析输入)

**算法**:
- 优先: LibreOffice headless → PDF → pdftoppm → jpg
- 备: qlmanage (macOS 原生, 但只首张)
- DPI 默认 150 (1920x1080 16:9)

**输出目录**:
- 默认 `<project>_images/` (按用户约定建)
- 必须建 (即使 soffice 没装, 目录也建, 留空给后续)

**依赖**:
- `soffice` (LibreOffice) — 可选
- `pdftoppm` (poppler) — 可选
- `qlmanage` (macOS) — 系统自带

### 3. analyze_ppt_citations.py (规则 #3-5)

**职责**: 4 列 CSV 输出 (A/B/C/D 固定)

**核心技术**:
- 复用 `via54Medit/scripts/ppt_understand.py` 的 `find_citation_marks_v2()`:
  - 规则 1a: 中文词 + 数字序列 (含逗号): `索拉非尼3,4` → 3, 4
  - 规则 1b: 中文词 + 数字 (兜底): `仑伐替尼5` → 5
  - 规则 2: "方案" + 数字: `T+A方案8,9` → 8, 9
  - 规则 3: "O+Y" + 数字: `O+Y15,16` → 15, 16
- 文本框末尾连续数字 (text_v3 算法, line 285-309)
- 底部引用文献 = y > 5" 的 text frame (按 y 排序)

**输出 CSV 4 列 (严格顺序)**:
```csv
slide_num,mark_num,citation_text,d_content_provisional
1,1,GLOBOCAN 2022,"PPT 标号 1 出现在: 「中国肝癌新发和死亡病例占全球近半数1」 | ..."
```

**D 列暂定规范**:
- 包含: "PPT 标号 N 出现在: 「...」" + 对应引用文献摘要 + 视觉依据 (image path)
- 标记: **provisional** (缺 PDF 校准, 后续可调)

### 4. test_ppt_citation_rules.py (回归保护)

**职责**: 锁住 6 条规则不被未来错误修改

6 个测试:
1. `test_extract_bottom_citation_y5` (规则 #1 底部 y>5)
2. `test_extract_citation_marks_ends_with_digit` (规则 #3 text_v3)
3. `test_output_csv_4_columns` (规则 #4 4 列)
4. `test_d_column_provisional` (规则 #5 D 列含 PPT 标号)
5. `test_expand_dry_run_no_file` (规则 #2 dry-run)
6. `test_export_images_creates_dir` (规则 #6 目录)

## ⚠️ 已知问题 (待用户给规则修复)

1. **标号 N → 引用文献 1:1 对应** 逻辑错误 (当前是循环取, 错位)
   - P3 标号 1 实际只对应 1 条 (GLOBOCAN), 但当前把 4 条都拿了
   - 需要规则: 视觉最近? 出现顺序? 还是按位置左/右?

2. **多引用共享** (e.g. `HIMALAYA中国#人群OS3,4`) 当前当 2 个独立标号
   - 共享 1 条文献, 但标 2 个 PPT 位置
   - 需要规则: 1 行 CSV 还是 2 行?

3. **跨 slide 共享** (P5 标 17 在 P24 也出现) 当前只标 P5
   - 需要规则: 1 行聚合还是每 slide 1 行?

4. **底部占位符** (e.g. `* 唯一: 截止至2026年4月1日...`) 当前当引用文献
   - 这是 PPT 脚注, 不是文献
   - 需要规则: 怎么过滤?

5. **D 列视觉分析** 当前仅文字
   - 应该用 vision_analyze 读 slide_NNN.jpg
   - 留待 v1.2.0

6. **`map_marks_to_citations` 排序逻辑** 当前 next-citation 循环
   - 改为按 y 坐标最近? 视觉对齐? 固定位置?

## 4 步 pipeline 实测 (2026-08-05)

```
[1/4] expand_slide_for_visibility.py  → 6 slide 需扩大, 全部 dry-run 通过
[2/4] export_ppt_to_images.py         → 目录建好 (soffice 未装, 留底)
[3/4] analyze_ppt_citations.py        → 154 行, 43 slide, 102 个有底部引用
[4/4] test_ppt_citation_rules.py      → 6/6 锁住规则
```

**总产出**: `<ppt>_citations.csv` (4 列, 154 行), 但已知 6 个映射 bug 待用户给规则.

## 关键路径

- 主脚本: `~/.medit/scripts/{expand_slide_for_visibility,export_ppt_to_images,analyze_ppt_citations}.py`
- 测试: `~/.medit/tests/test_ppt_citation_rules.py`
- 复用核心: `/Users/david/Desktop/developments/via54Medit/scripts/ppt_understand.py` (find_citation_marks_v2)
- 算法沉淀: `~/.hermes/skills/via54medit-literature-dir-init/SKILL.md` v1.1.0
