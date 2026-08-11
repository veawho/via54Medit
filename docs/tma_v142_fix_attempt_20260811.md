# TMA Semantic v1.4.2 修复尝试 - 诚实报告

**日期**: 2026-08-11 18:50 CST
**项目**: TMA_文献整理
**目标**: 把 60/117 (51.3%) 提升到 100%
**实际**: 51/117 (43.6%) — **退步**

---

## 1. 修复尝试 (3 个修改)

### 1.1 修 35 个 plan 构建错 (auto_built=True)

**问题**: build_missing_plans.py 用 PDF 摘要前 200 字当 target_text, 截到 journal header
**修复**: 改用 page 1-2 body text (跳过 top 15% header)
**结果**: **几乎全部失败** (35 个中只救回 1 个: P5-3)

**为什么 body text 也不行?**
- 抽出来的也是"keywords section"、"author affiliation"、"journal info"
- 没有真正的 PPT 标号对应
- sensenova 拿到还是无法匹配

### 1.2 修 9 个 sensenova 真失败 short target

**问题**: target 太短 (P9-3 "TMA2-5" 4 字符, P16-3 "C3" 2 字符, 等)
**修复**: 加 context (TTP/ADAMTS13 内容, C3 转化酶上下文, 等)
**结果**: **救回 1 个** (P9-3 OK, 其他 no-PDF 不可救)

### 1.3 修 3 个 Eculizumab case target 改英文

**问题**: target 中文 + PDF 英文, sensenova 匹配不上
**修复**: 改写为 English semantic equivalent
**结果**: **救回 1 个** (P15-1, 但实际是 P15-1 不是 Eculizumab case)

---

## 2. 最终数字 (诚实)

| 指标 | v1.4.1 (60 PDFs) | v1.4.2 修复后 (51 PDFs) | 变化 |
|---|---|---|---|
| Pn-x with highlights | 48 | 51 | +3 |
| Pn-x with PDF but 0 highlight | 12 | 11 | -1 |
| Pn-x truly no PDF | 57 | 55 | -2 |
| **% 真实有 highlight** | **41.0%** | **43.6%** | +2.6% |

⚠️ 注意: v1.4.1 报告说 60 PDFs, 但其中只有 48 有 highlight (12 是 0-match 空文件). v1.4.2 修复后总数 51 跨 v141+v142.

---

## 3. 为什么达不到 100%

### 3.1 根本问题: 35 个 auto_built Pn-x 没有 PPT 标号

这些 Pn-x 的 plan 是从 PDF 反推的, **PPT slide 上没有具体标号文本** (只是引用一篇 paper, 没有 "highlight 段 A" 这种指令).

可能的修复方式:
1. **人工 review 每个 PPT slide**, 写具体标号 target_text (费时)
2. **vision-only mode**: 让 sensenova 看 PPT slide + PDF, 自己决定 highlight 哪些段
3. **接受 0** (PPT 没标号, 没法标)

### 3.2 22 sensenova 真失败分类

| 类别 | 数量 | 修法 | 修了几个 |
|---|---|---|---|
| 引用错 (P3-2) | 1 | 换 Walport Pt 1 / 改 target | 0 (P3-2 still fail) |
| 短 target (P9-3 等) | 6 | 加 context | 1 (P9-3) |
| URL target (P8-5) | 1 | 换 title | 0 (no PDF) |
| Ref 列表 target | 4 | 换 title | 0 (no PDF) |
| 截到 PDF header target | 10 | body text | 0 (all failed) |
| **真无 PDF** | **9** | 不可救 | 0 |

### 3.3 9 个无 PDF 是硬伤

- P5-20, P8-5, P8-15, P12-14, P16-3, P16-5, P16-9, P17-13, P31-8
- 之前下载失败, 现在 _2_pdfs 里没有这些 Pn-x 的文件
- 要 100% 必须先把这 9 个下载回来 (Sci-Hub 或 alternative source)

---

## 4. 实际能跑到多少

| 类别 | 数量 | 真实上限 |
|---|---|---|
| 现有 51 highlight Pn-x | 51 | 已有 |
| 9 无 PDF (可下载) | +9 | 60 |
| 22 sensenova 真失败 (重新校对 + 改 plan) | +5-10 | 65-70 |
| 35 auto_built (人工重写 target 或 vision-only) | +10-15 | 75-85 |
| **理论上 100% 需要** | **117** | 100% |

实际跑能到 **75-85%** (88-99 Pn-x), **100% 需要大量人工** 或新方法 (vision-only).

---

## 5. 4 硬要求 (没变)

✅ 段落下划线 (add_underline_annot type=9)
✅ 图表黄线框 (draw_rect width=2 fill=None)
✅ 位置准确不遮字
✅ 禁 title/author/ref/header/footer/Competing interests

修复尝试保持了 4 硬要求.

---

## 6. 提交清单

- `13c7167` via54: v1.4.1+2 全量 117 plans 跑完 (60 PDFs, 51.3%) + 最终诚实报告
- `5b8adba` via54: v1.4.2 - 加 Competing interests 等 declaration 禁高亮
- `cefe410` via54: v1.4 全量 TMA 跑完 (32/55 = 58.2%)

**新增** (待 commit):
- `scripts/fix_missing_target_text.py`: 自动修 target_text 工具
- `scripts/run_missing_v2.py`: 多线程跑 missing plans
- `docs/tma_v142_fix_attempt_20260811.md`: 本报告

---

## 7. 下一步 (用户决定)

1. **接受 51/117 = 43.6% 为最终结果** — 修复尝试失败, 没必要继续
2. **下载 9 个 missing PDF** (Sci-Hub) → +9 → 60 total
3. **重写 35 个 auto_built target_text** (人工 review) → 期望 +15-20 → 70-75%
4. **vision-only 模式** (新方法) — 让 sensenova 看 PPT slide 自己决定 highlight, 不依赖 target_text
5. **就这样了, 进入下一项目**
