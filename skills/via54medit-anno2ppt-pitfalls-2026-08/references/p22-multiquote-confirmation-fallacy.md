# P22-1 + P22-2 多引用应证推理 — 错例 + 修正 transcript

> 配套: `via54medit-anno2ppt-pitfalls-2026-08` §12 (应证的根本性铁律) + §13 (多引用结构算法)

## 0. 背景

用户在测试 P22-1 + P22-2 时，先纠正了 **目录污染**（`_audit_report` / `*_highlighted.pdf` / 图叠加文字），然后测试 **应证逻辑**。

## 1. 用户的核心纠正（2026-08-01 严厉批评）

```
用户原话:
"1. P22-1 与 P22-2 需要同时处理 highlight，因为 ppt 中的标注是 1,2
2. 正确理解 P22-1 与 P22-2 对应 PPT 中要表达的内容：
   关键信息<HIMALAYA III期>喜马拉雅III期临床试验；
   关键信息2<全球人群、中国人群>；
   关键信息3<雷管方案一线获益>；
   补充信息（不是必须highlight的）<在uHCC中6年OS率>
3. 解读下来，应该是，P22-1 与 P22-2，应当是证明同一结论/观点，
   一个文献聚焦全球人群，一个文献聚焦中国人群
请检查、验证"
```

## 2. 我犯的根本性错误

我先用 mmx vision 列出 P22-1 + P22-2 PDF 图里所有数字（HR 0.76, HR 0.68, 17.1%, 8.9%, 16.43, 13.77, N=156, N=479, TRAE 等），然后挑了几个说"这些都应该标"。

**这是错的**。

PPT 位置 1 文字只提了：
- "HIMALAYA III 期"（试验名）
- "全球人群、中国人群"（人群）
- "雷管方案一线获益"（结论）
- (补充) "在 uHCC 中 6 年 OS 率"（不是必须）

**PPT 没提**：HR 0.76 / HR 0.68 / 17.1% / 8.9% / 中位 OS 16.43/13.77 / TRAE / N=156 / N=479

## 3. 用户第二次严厉纠正（核心错误）

```
用户原话:
"为什么会判断 HR0.76 OS率 是需要P22-1 和 P22-2应证的内容，
 我给你的信息已经是全部了，OS率有关联，但不是必须。
 HR0.76 这个数据完全没有在PPT中体现。你到底怎么了？"
```

## 4. 修正算法（应证铁律）

```
Step 1: 读 CSV C 列 "位置 1 文字"
Step 2: 抽出 PPT 真正提到的应证要素
Step 3: 在 PDF 里 search_for 同样要素文字
Step 4: 标注 (P3-2 同款黄色下划线 / 荧光黄色块)
Step 5: mmx vision 复核 1 次 (不再扩展)
```

## 5. 真实跑通的修正流程

### P22-1（不动，v3.9 已正确）
- 标的内容: "HIMALAYA 6-y OS KM curve" 标题 + ESMO 来源 + 6 年 OS banner
- 应证: "HIMALAYA III 期 + 全球人群 + 6 年 OS" 全部覆盖

### P22-2 page1（v3.9 错 → v4.0 修正）

**v3.9 现状**: 标了 "HR 0.68 (95% CI 0.52-0.89)"（PPT 没要求）

**v4.0 修正**:
```python
import fitz

doc = fitz.open('/Users/david/Desktop/雷管方案_文献整理/P22-2/P22-2_main_Chan_JHepatol_2025_HIMALAYA_AsianSubgroup.pdf')
page = doc[0]

# PPT 真正要求的应证: HIMALAYA + III期 + 中国人群
targets = [
    'HIMALAYA',              # 主标题里的 HIMALAYA
    'phase III',             # 主标题里的 phase III
    'Asian subgroup',        # 主标题里的 Asian subgroup
    'Asia-Pacific',          # 摘要里的 Asia-Pacific
]

for kw in targets:
    for rect in page.search_for(kw):
        page.add_highlight_annot(rect)  # 荧光黄, P3-2 同款
```

**mmx vision 复核（1 次调用）**:
- ✓ HIMALAYA 标注: 多处 (标题 + Highlights 第 1, 2 条)
- ✓ phase III 标注: 2 处
- ✓ Asian subgroup 标注: 多处 (标题 + Highlights + 底部深蓝条)
- ✓ Asia-Pacific 标注: 2+ 处
- ✗ HR 0.68: 已正确删除 (没标)

## 6. 多引用结构算法 (从这次 session 提炼)

**触发条件**: CSV C 列出现 "多引用 1,2 中 X 部分" 或 "1,2 两个独立标号共享同一段标签文字"

**P22 实战**:
```
PPT 标号 1 (P22-1): Bruno Sangro ESMO 2025 (HIMALAYA 全球人群 6年 OS 数据)
PPT 标号 2 (P22-2): Lau G 2025 J Hepatol (中国人群亚组)
共同应证: "HIMALAYA III 期一线获益 (STRIDE > Sorafenib)"
```

**算法步骤**:
1. 找所有 ref 共享同一段 PPT 文字 → {ref_1, ref_2}
2. 每条 ref 聚焦不同维度
3. **同时处理** (互为补充, 不能只标一个)
4. 对每条 ref:
   - 在 PDF 文字层 search_for 关键要素
   - add_highlight_annot 画黄色色块
   - mmx vision 复核 1 次

## 7. 绝对禁止的诱惑

- ❌ 在 P22-2 里标 HR 0.68 (PDF 有, PPT 没提) → 用户抓到重罚
- ❌ 在 P22-2 里补 N=479 / TRAE / Durva HR 0.83 (PDF 有, PPT 没提) → 同上
- ❌ 反复调 mmx vision 验同一张图 → 用户原话"不要反复确认琐碎选择"
- ❌ 自作主张建 `_audit_report/` 备份 → 用户当场抓到
- ❌ 在高亮图叠加蓝色文字 "应证说明" → 用户原话"不符合一直以来的要求"

## 8. 沉淀进 skill 的内容

- **§12 应证的根本性铁律** (本章精华)
- **§13 多引用结构算法** (P22-1+P22-2 实战)
- **§14 应证推理的 3 类 PPT 引文类型完整版** (A 政策文字 / B 集合结论 / C 临床图表)

## 9. 文件位置

- 高亮图: `_literature_citation_index/P5-18_P12-3_P13-3_P22-2_P24-2_P26-5_P27-5_P33-3_P33-7_P43-3_P43-6/P22-2_page1_highlight.jpg`
- 主文件: `P22-2/P22-2_main_Chan_JHepatol_2025_HIMALAYA_AsianSubgroup.pdf`

## 10. 教训（写给未来的自己）

> 应证的第一驱动源 = CSV C 列 "位置 1 文字"
> mmx vision 是辅助定位工具，不是决定标什么的源头
> 不要的诱惑: "PDF 里有 → 都标" 错. "PDF 有 + PPT 提 → 才标" 对
> 多引用必须同时处理，互为补充维度