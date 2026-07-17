# PPTX 引用提取与验证集成文档

> **模块**: `internal/pptx` (Phase 3)
> **CLI**: `medit pptx verify` / `medit pptx extract`
> **依赖**: 标准库 `archive/zip` + `encoding/xml` — **零第三方依赖**

---

## 1. 概述

PPTX 模块实现了从 PowerPoint 幻灯片 XML 中提取学术引用，验证来源 (PubMed/Crossref/Semantic Scholar)，并分类下载途径 (Sci-Hub / OA / Nexus) 的完整流水线。

## 2. 流水线

```
1. zip.OpenReader → 读 ppt/slides/*.xml + ppt/notesSlides/*.xml
2. xml.Unmarshal <a:t> 标签 → 逐 slide 拼接文本
3. splitIntoLines → 候选行分割
4. isCitationLine → 评分 ≥2 的行判定为引用
5. ParseCitationLine → 提取 PMID / DOI / Year / Volume / Issue / Pages / Journal / Authors
6. Verifier.Verify → 并行：PubMed(PMID) + Crossref(DOI) + S2(title/author)
7. DownloadChecker.Check → 分类下载途径
```

## 3. CLI 使用

```bash
# 提取 + 验证（默认，需要网络）
medit pptx verify deck.pptx

# 纯提取（离线，不调用任何 API）
medit pptx extract deck.pptx
```

输出：控制台表格 + JSON 块

### 示例输出

```
Slide Authors                          Journal      Year         Status       DownloadTier
---- ------------------------------- -------------- ------------ ---------- --------------
1    Finn RS, IMbrave150             NEJM           2020         exact        sci-hub
2    Ren Z, ORIENT-32                Lancet Oncol   2021         exact        sci-hub
3    Yau T, CheckMate 459            Lancet Oncol   2022         exact        sci-hub
4    Song YG, Bleeding Meta          Liver Cancer   2024         exact        oa
```

## 4. 下载分类规则

| 条件 | Tier | 成功概率 | 说明 |
|------|------|---------|------|
| Year ≤ 2022 且非 OA 期刊 | `sci-hub` | >90% | 传统期刊在 Sci-Hub 收录 |
| 已知 OA 期刊 (Front Oncol, Sci Rep, BMC...) | `oa` | ~100% | Unpaywall / S2 / OpenAlex |
| Year ≥ 2023 且非 OA 期刊 | `nexus` | 50-70% | stc(Nexus) Telegram Bot |
| 数据不完整 / 无法验证 | `unavailable` | — | 作者缩写不完整或会议摘要无 DOI |

## 5. 已知限制

1. **作者缩写不完整**: PPTX 引用常仅写 "YX, et al." — 需人工核查
2. **会议摘要**: 44 条会议摘要无 DOI/PMID，无法自动化验证
3. **期刊词库有限**: `journalPat` 当前覆盖约 30 个常用缩写，可根据需要扩充
4. **RE2 限制**: Go 的 RE2 引擎不支持零宽断言 (lookahead/lookbehind)，sentenceSplitter 使用简化模式 `[.!?;]\s+`

## 6. 扩展

- 扩充 `journalPat` 正则词库 → 覆盖更多期刊缩写
- 扩充 `DownloadChecker.oaJournals` → 更多 OA 期刊名称
- `Verifier` 支持额外来源 (Unpaywall API, Google Scholar)
