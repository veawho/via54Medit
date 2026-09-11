# 版本后缀脚本清查（2026-09-11）

`scripts/` 下曾累积 19 个带 `_vN` 后缀的文件。这份清单记录对它们逐个的判定依据与结论，
供后续处置参考 —— **不要只看文件名推断版本关系**，理由见下。

**处置结果**：v5.4.16 下线 4 个（能凭硬证据直接判定死亡）；v5.4.17 再下线 6 个
（原标「待人工确认」，本轮从项目侧终态记录补齐了"任务是否已收尾"这一缺失信息）。
**19 → 9**，剩余 9 个 = 4 个仍接线/仍活 + 4 个 v13 审计族（待定）+ 1 个固有命名（非迭代）。

## 判据（按证据强度排序）

1. **后继者是否指名取代** —— 最强。例：`rerun_tma_highlight_v3_final.py` 的 docstring 明写
   「完全替代 `rerun_tma_highlight_v104.py`」。
2. **是否有接线** —— 是 `via54.py` 的分发目标？被其它脚本 `import`？
3. **硬编码的目标目录是否还存在** —— 这批脚本多为一次性、参数写死在代码里（11 个里 9 个连
   `argparse`/`sys.argv` 都没有）。输入输出目录一旦消失，脚本即无法运行。
4. **文档怎么定性** —— 是否被指为「唯一标准」或「仅历史参考」。

## 两个必须先破除的直觉

**① 后缀不代表版本链。** 族内代码重合度普遍只有 17%–38%（`redownload_36` v2↔v3 为 38.2%、
`tma_batch_redownload` v2↔v3 为 30.3%），说明这些是**同一问题的重写式反复尝试**，不是层层
叠加的版本。提交信息也印证这一点（`0/16 success`、`51/117 = 43.6%`、`1/11 成功`）。

**② 后缀有时根本不是"迭代"。** `literature_v8_process_pn_x_v313.py` 与它的无后缀"兄弟"
重合度仅 **1.6%**（1504 行 vs 200 行），是两个完全不同的程序 —— `_v313` 指代外部工具版本。
`integrations/clinicaltrials_v2.md` 同理，`_v2` 是它的固有名字（仓库内不存在 v1）。

## 逐个结论

| 文件 | 关键证据 | 结论 |
| --- | --- | --- |
| `scripts/rerun_tma_highlight_v104.py` | v3_final 的 docstring 指名取代；硬编码 `_2_pdfs` 与其输出目录**均已不存在**；无任何接线 | **已取代，本轮下线** |
| `scripts/fix_zero_yellow_pnx.py` | v10 时代伴生脚本；读 `_2_pdfs/`、写 `_3_highlight_v10_4/`，**两者均已不存在**；唯一用途是调 v104 的 helper；仅一份历史文档提及 | **已失效，随 v104 成对下线** |
| `scripts/tma_batch_redownload_v2.py` | 硬编码输入 `_3_highlight_v10_glm/_redownload_suggestions.json`，**该目录已不存在**；无引用 | **已失效，本轮下线** |
| `scripts/tma_batch_redownload_v3.py` | 同上 | **已失效，本轮下线** |
| `scripts/via54_highlight_fix_v10.py` | 被 **2026-09-05** 的 `process_all_pn_x.py`（当兼容层）与 `vision_highlight_workflow.py`（用 `process_pn_x`）import；后者被 skill 与 `docs/6_step_sop.md` 引用 | **仍活，不可删** |
| `scripts/rerun_tma_highlight_v10.py` | `via54.py highlight --mode legacy-v10` 的分发目标（默认 `visual-v3`） | **仍接线，不可删** |
| `scripts/rerun_leidafang_highlight_v10.py` | 同上 | **仍接线，不可删** |
| `scripts/test_via54_highlight_fix_v10.py` | `AGENTS.md` 引用其测试数作为项目证据；实测 **41 项全过**，但其中 4 个真实 TMA 用例因硬编码的 `_2_pdfs` 已归档而**自动 skip** —— 即覆盖已缩水，而非失败 | **仍活，不可删**；`AGENTS.md` 的表述本轮已修正 |
| `integrations/clinicaltrials_v2.md` | `_v2` 是固有名字，仓库内无 v1 | **非迭代残留，保留** |
| `scripts/audit_all_highlights_v13.py` | 输出目录 `_audit_v13/`（8 项）存在，但停在 2026-08-12 | v13 审计族：跑完未再动，**保留待定** |
| `scripts/audit_semantic_v13.py` | 同上 | 保留待定 |
| `scripts/find_anchors_v13.py` | 输出目录 `_audit_v13_visual/`（108 项）存在，停在 2026-08-12 | 保留待定 |
| `scripts/render_audit_visual_v13.py` | 同上 | 保留待定 |
| `scripts/redownload_36_v2.py` | 无引用、无接线、无 CLI 参数；族内与 v3 重合 38.2%；输入 `/tmp/to_fix_36.json` 与写入的 `_2_pdfs/` 均已不在（后者已更名为 `step3_pdf下载_106目录/`） | **已下线**（v5.4.17） |
| `scripts/redownload_36_v3.py` | 同上；其 `.bak_v3_` 回滚备份也已不存在 | **已下线**（v5.4.17） |
| `scripts/redownload_27_v4.py` | 无引用、无接线、无 CLI 参数；输入 `/tmp/pdf_feishu_alignment_final.json` 已不在 | **已下线**（v5.4.17） |
| `scripts/batch_download_v2.py` | 目标目录 `_2_pdfs_replaced_v2` 已不在 | **已下线**（v5.4.17） |
| `scripts/find_replacements_v2.py` | 其**产出物已入库**：`docs/wrong_pdf_replacement_v2_20260811.json`（8 条替代候选，提交 `99631b9`） | **已下线**（v5.4.17，产出物留存） |
| `scripts/run_missing_v2.py` | 无接线、无 CLI 参数；输入 `_3_highlight_vision/_highlight_plans.json` 与输出 `_3_highlight_semantic_v141/142` 全部不在 | **已下线**（v5.4.17） |
| `scripts/literature_v8_process_pn_x_v313.py` | 有 `argparse`（3 处）；与无后缀"兄弟"重合仅 1.6% | **非迭代关系，保留** |

### 上述 6 个为什么从「待人工确认」改判为「已下线」

上一轮判定它们时缺的正是**「任务是否已收尾」这一信息**。本轮从项目侧的终态记录拿到了，
依据是三条互相独立的证据：

1. **下载已是齐的**。`via54_rules.py check` 的探针实测：`step3_pdf下载_106目录/`
   有 **106 个 Pn-x、106 个都有 PDF**（共 111 个 PDF 文件）。这正是 `redownload_36_*` 与
   `redownload_27_v4` 想达成的终态。
2. **错配已归零**。项目内 `PDF_FEISHU_REDOWNLOAD_v2_REPORT.md` 记录 `MISMATCH 6 → 0`、
   `MATCH 79 → 85`，对应 `redownload_27_v4` 的目标（24 MISMATCH + 3 FS_NO_MD5）。
3. **后继流程已知**。`飞书总结文档_工具开发_2026-08-14.md` 记录 Step 3 下载
   成功率 90–95%、Step 4 highlight **106 个 Pn-x 全部完成**、Step 5 **106/106 对齐**；
   `run_missing_v2` 那一轮的 v1.4.2 只到 **51/117 = 43.6%**（提交信息自述"诚实"），
   已被 v3 FINAL 取代。

同时这些脚本操作的**中间目录已被 6 步结构取代**：`_2_pdfs/` → `step3_pdf下载_106目录/`，
`_3_highlight_semantic_v14x/`、`_3_highlight_v10_glm/` → `step4_highlight_106目录_合并DOI/`。

唯一未闭环的 3 篇（P12-3 UpToDate 占位 / P13-1 焦扬 / P31-6 AANEM 摘要）**需要用户提供原文**，
不是这几个脚本能解决的 —— 故不构成保留理由。

删除前确认：6 个脚本**零代码级引用**（`run_missing_v2` 唯一那处是历史文档
`docs/tma_v142_fix_attempt_20260811.md` 的记录性提及）；其唯一的跨脚本依赖
`semantic_highlight_workflow` 模块仍在，故不留坏 import。

## 同法验证发现、但未纳入判定范围（无后缀的同类，同样已死）

这两个是刚下线的那几族的**无后缀前身**（v1），按同一判据已可直接判定为死，但不在 19 个的范围内，故**未删**：

- `scripts/tma_batch_redownload.py` —— 三个硬编码路径**全部不存在**：
  `_2_pdfs/`、`_3_highlight_v10_glm/_redownload_suggestions.json`、
  `_3_highlight_v10_glm/_tma_redownload_log.json`。零引用。
- `scripts/redownload_36.py` —— `SRC = f'{TMA}/_2_pdfs'`、`LOG = f'{TMA}/_3_highlight_v10_glm/_redownload_36_log.json'`，
  两个目录均已不存在；输入 `/tmp/to_fix_36.json` 也已不在（临时文件）。零代码级引用。

> 处置建议：与已下线的 6 个同批清掉即可；本轮未动是因为不在本次授权范围内。
> 两者与 `redownload_36_v2/v3.py`、`tma_batch_redownload_v2/v3.py` 是同一族的 v1，
> 而那几个已经删除 —— 留着 v1 反而使版本族更不完整。

## 顺带发现：文档引用了不存在的工作流

清理过程中核对引用链，发现两处文档都指向一个**已被删除的 CI 工作流**：

| 位置 | 原文声明 | 事实 |
| --- | --- | --- |
| `AGENTS.md` | `CI: .github/workflows/rules_check.yml 自动跑 via54.py rules <project>` | 该文件不存在。`.github/workflows/` 下**只有 `ci.yml`**，其步骤为 `go build ./...`、`go vet ./...`、`go test -race`、`python -m unittest test_tma_pipeline`、`python test_hl_lib.py` + 工具链 import 探针 —— **没有** rules 步骤 |
| `docs/6_step_sop.md` | `\| CI gate \| .github/workflows/rules_check.yml \| ✓ PR 自动跑 \|` | 同上 |

`rules_check.yml` 在 `bc96e45`（提交信息 `tmp: remove workflow for push test`）中被删除，此后从未恢复。
本轮已把两处改为指向真实存在的 `ci.yml`，并注明 `via54.py rules` 需本地手动跑。

同时发现两处文档的「通过率」对不上现状 —— 但**这里我自己先判断错了，后来被实测推翻**，
过程值得留档：

第一轮我跑规则校验，得到 2/7，于是写下「原因是 Step 1/3/4/5/6 的输入目录已随项目归档移出，
**不是规则回归**」。**这个归因是错的。**

第二轮为了核实，我用软链接做了个非侵入探针：把 TMA 现用的目录名 `step3_pdf下载_106目录`、
`step4_highlight_106目录_合并DOI` 额外映射成校验脚本候选清单里的名字，只改这一处：

```
原始 TMA 目录            →  ❌ 2/7
探针目录(仅补两个别名)   →  ❌ 5/7   ← 差别全部来自命名
```

数据根本没缺：Step 3 在探针下报 `pn_x_dirs: 106, with_pdf: 106`（106 篇全有 PDF）。
真正的根因是 **`via54_rules.py` 的候选目录名过期** —— 清单里写死的是
`step3_pdf下载_160目录`（那是**雷管方案**的 160）与 `step4_highlight_96目录_合并DOI`（TMA 的**旧** 96），
而 TMA 随文献数增长已改名为 `…_106目录`。

剩下 Step 4/5 的失败是另一处缺陷：`_count_pn_x` 与 Step 5 的集合比较都按**目录**计数，
而 Step 6 的合并把 28 个 Pn-x 收进了 12 个目录（`90 = 106 - 28 + 12`），于是被误报成
「highlight 缺 28 个 / 多 12 个」。

已在 **v5.4.17** 一并修掉（显式清单 + 命名族正则兜底；Step 4/5 改按**文献**比较），
修复后实测：

```
$ python3 scripts/via54_rules.py check "/Users/david/Desktop/TMA_文献整理"
✅ 总体: 7/7 步通过, 0 个 issue
```

即 TMA 本来就是 7/7 —— 与文档原先的声明一致，是校验脚本看不见它。
因此这两处文档不再需要「历史快照」标注，已改回可复现的声明（雷管方案的目录确实不在本机，
其数值仍标注为历史记录）。

可复现的测试：
```
$ python3 scripts/test_via54_rules.py            → Ran 41 tests, OK   (28 → 41, 新增 13)
$ python3 scripts/test_via54_highlight_fix_v10.py → Ran 41 tests, OK (skipped=4)
```

> **教训**：把「校验脚本报错」直接读成「数据缺失」是一次没有交叉验证的归因。
> 校验发现异常时，应当先分辨「被校验对象的问题」还是「校验器自身的问题」——
> 这次只要多问一句"候选名里有没有当前这个名字"就能避免。

## 顺带发现（未处理）：`hl_v3_final` 仍用弃用式 `import fitz`

v5.4.11 把弃用警告限定在 `telemetry/` 内修掉了（`watcher.py`、`pdf_utils.py`），但
`scripts/hl_v3_final/` 下仍有约 20 处裸写 `import fitz`（`hl_lib.py`、`render_fitz.py`、
`hl_ocr_band.py`、`step1_export_slides.py`、`examples/hl_p*.py` 等）。这不是当初漏改，
而是**范围之外**：v5.4.11 的表述本就只承诺 `telemetry` 两个模块。

性质：这些是手动运行的 CLI 脚本，警告只污染各自 stderr，不影响退出码，CI 里
`python test_hl_lib.py` 也照过。**本轮未改** —— 这是「唯一标准」的高亮工具链，
批量改导入名需要配套回归（`pymupdf` 正式导入名要求 PyMuPDF 1.24+，旧版需回退），
应由后续单独的改动承担。

## 复现方式

```bash
# 1. 带版本后缀的文件清单
git ls-files | grep -E "_v[0-9]+\.(py|md)$"

# 2. 谁 import 了某个模块
grep -rn "import <module>" --include="*.py" .

# 3. via54.py 的分发目标（当前入口）
grep -oE '[a-z_0-9]+\.py' scripts/via54.py | sort -u

# 4. 硬编码绝对路径是否存在（本判据的核心）
python3 - <<'PY'
import os, re
src = open("scripts/<file>.py", encoding="utf-8").read()
for p in sorted({os.path.dirname(x) for x in re.findall(r'"(/Users/[^"]+)"', src)}):
    print(("✓" if os.path.exists(p) else "✗"), p)
PY

# 5. 族内代码重合度（判断"迭代"还是"不同任务"）
python3 -c "
import difflib
a=open('scripts/<A>').read().splitlines(); b=open('scripts/<B>').read().splitlines()
print(round(difflib.SequenceMatcher(None,a,b).ratio()*100,1), '%')"
```
