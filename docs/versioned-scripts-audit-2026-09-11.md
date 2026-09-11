# 版本后缀脚本清查（2026-09-11）

`scripts/` 下累积了 19 个带 `_vN` 后缀的文件。这份清单记录对它们逐个的判定依据与结论，
供后续处置参考 —— **不要只看文件名推断版本关系**，理由见下。

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
| `scripts/redownload_36_v2.py` | 无引用、无接线、无 CLI 参数；族内与 v3 重合 38.2% | **一次性任务形态，待人工确认是否已收尾** |
| `scripts/redownload_36_v3.py` | 同上 | 待人工确认 |
| `scripts/redownload_27_v4.py` | 无引用、无接线、无 CLI 参数 | 待人工确认 |
| `scripts/batch_download_v2.py` | 同上 | 待人工确认 |
| `scripts/find_replacements_v2.py` | 同上 | 待人工确认 |
| `scripts/run_missing_v2.py` | 无接线、无 CLI 参数；一份历史文档提及 | 待人工确认 |
| `scripts/literature_v8_process_pn_x_v313.py` | 有 `argparse`（3 处）；与无后缀"兄弟"重合仅 1.6% | **非迭代关系，保留** |

「待人工确认」的 6 个性质是**「一次性任务已完成」而非「被取代」** —— 这两者处置不同：
前者删掉就是删掉历史记录，后者才有明确替代品。判定它们需要知道哪些数据问题已经关闭，
这不在仓库里。

## 同法验证发现、但未纳入本次判定范围

- `scripts/tma_batch_redownload.py`（无后缀）—— 硬编码的 `_3_highlight_v10_glm` 与 `_2_pdfs`
  **均不存在**，按同一判据**同样已死**；但它不在本次 19 个的判定范围内，故未动。
- `scripts/redownload_36.py`（无后缀）—— 未单独验证目标目录。

## 顺带发现：文档引用了不存在的工作流

清理过程中核对引用链，发现两处文档都指向一个**已被删除的 CI 工作流**：

| 位置 | 原文声明 | 事实 |
| --- | --- | --- |
| `AGENTS.md` | `CI: .github/workflows/rules_check.yml 自动跑 via54.py rules <project>` | 该文件不存在。`.github/workflows/` 下**只有 `ci.yml`**，其步骤为 `go build ./...`、`go vet ./...`、`go test -race`、`python -m unittest test_tma_pipeline`、`python test_hl_lib.py` + 工具链 import 探针 —— **没有** rules 步骤 |
| `docs/6_step_sop.md` | `\| CI gate \| .github/workflows/rules_check.yml \| ✓ PR 自动跑 \|` | 同上 |

`rules_check.yml` 在 `bc96e45`（提交信息 `tmp: remove workflow for push test`）中被删除，此后从未恢复。
本轮已把两处改为指向真实存在的 `ci.yml`，并注明 `via54.py rules` 需本地手动跑。

同时实测发现，两处文档的「通过率」都是**项目数据齐全时的历史快照**，现在无法复现：

```
$ python3 scripts/via54_rules.py check "/Users/david/Desktop/TMA_文献整理"
❌ 总体: 2/7 步通过, 6 个 issue
```
原因是 Step 1/3/4/5/6 的输入目录（`_2_pdfs/`、`_3_highlight_v10_glm/`）已随项目归档移出工作目录，
**不是规则回归**。雷管方案目录同样已不在本机。两处文档已加日期标注说明这一点。

可复现的只剩单测：
```
$ python3 scripts/test_via54_rules.py            → Ran 28 tests, OK
$ python3 scripts/test_via54_highlight_fix_v10.py → Ran 41 tests, OK (skipped=4)
```

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
