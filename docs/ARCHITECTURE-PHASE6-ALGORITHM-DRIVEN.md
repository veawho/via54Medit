# via54Medit Architecture — 算法驱动 + 经验闭环 (Phase 6, 2026-07-31)

## 用户要求 (2026-07-31)

> 确保 via54Medit 是一个算法作为核心驱动的 github 项目
> 确保 本地的文献整理项目均使用 via54Medit 执行
> 确保 所有修改修正经验都会持续集成到 via54Medit

## 设计哲学 (5 大原则)

1. **算法驱动** (不是规则) — regex / probabilistic / LRU / PageRank, 不用 if/else
2. **算法 + LLM 配合** — 置信度低时让 LLM 反思, 不写死规则
3. **不写死绝对值** — 动态学习 + 持续集成
4. **经验闭环** — 用户修正 → 自动转测试 → 算法升级 → CI 验证
5. **本地项目通过 via54Medit 执行** — 雷管方案只是 via54Medit 的一个 use case

## 架构 (Phase 6 加的模块)

```
via54Medit/
├── cmd/medit/commands/
│   ├── feishu.go                      ← CSV ↔ 飞书 集成
│   ├── citation.go                    ⭐ 新增: 经验闭环 CLI
│   └── root.go                        ← 注册
│
├── internal/
│   ├── citation/                       ⭐ Phase 6 新增: 算法核心
│   │   ├── citation.go                 # 数据模型
│   │   ├── keyword_match.go           # D 列关键字段 (v2.0 算法)
│   │   ├── rich_text.go               # 飞书 cell rich text 自动转换
│   │   ├── *_test.go                  # 黄金测试
│   │   └── corrections/                ⭐ 经验闭环
│   │       ├── corrections.go         # JSON log
│   │       ├── replayer.go            # 修正 → 测试
│   │       └── corrections_test.go    # 12 雷管方案历史修正 seed 测试
│   │
│   └── integrations/feishu/feishu.go  ← CSV ↔ Feishu Go client
│
└── docs/
    ├── ARCHITECTURE.md                ← 已更新 §22 算法驱动
    ├── EXPERIENCE-LOOP.md              ⭐ 新增: 经验闭环设计
    └── ALGORITHMS.md                  ⭐ 新增: 算法目录
```

## 算法目录 (`internal/citation/`)

### `citation.go` — Citation 数据模型

```go
type Citation struct {
    SlidePage string
    CiteIndex string
    Context   string
    Reference string   // "Qin S, et al. Lancet Oncol. 2025"
    DOI       string   // "10.1056/EVIDoa2100070"
    DocType   string
    PDFFile   string   // "P3-1/P3-1_main.pdf"
    SourceURL string   // rich text
}
```

### `keyword_match.go` — D 列关键字段抽取 (v2.0)

**算法 (不是硬编码 if/else)**:
- Authors: regex `[A-Z][a-z]+(?:-[A-Z][a-z]+)*` + journal/drug/year set 过滤
- Journal: 30+ pattern compile once + first match
- Year: `\b(19|20)\d{2}\b`
- Trial: 30+ known trial acronyms (HIMALAYA, IMbrave150, ...)
- Drug: 20+ HCC drugs (Tremelimumab, Atezolizumab, ...)
- DOI tail: regex `10\.\d+/([A-Za-z0-9._\-/]+)` + last "/"

**vs v1 (雷管方案 Python)**:
- v1 missed hyphenated author (Abou-Alfa) → v2 修
- v1 missed multi-author list (Peter Robert Galle) → v2 修
- v1 wrong DOI tail for multi-segment (10.1158/1078-0432.CCR-24-0006) → v2 修

### `rich_text.go` — 飞书 cell parser + builder

**算法**:
- `ParseCell(interface{})` 统一解析 Feishu cell (string / dict / list / rich_text)
- `BuildRichCell(content)` 自动检测 URL → 转 `{rich_text: [{text, type:'link', link}]}`

**关键 fix (vs v1)**:
- ❌ `type='url'` → ✅ `type='link'`
- ❌ 直接 array `[{text, type}]` → ✅ wrap in `{rich_text: [...]}`
- ❌ 漏 `]` 在 URL 末尾 → ✅ regex `https?://[^\s\)\]]+`

### `corrections/` — 经验闭环

**Loop**:
```
User makes correction (in 雷管方案)
  → corrections.Record(c)  saves to ~/.via54medit/corrections.json
  → corrections.ReplayAll() generates TestCase entries
  → corrections.GenerateGoTestFile() writes *_test.go additions
  → go test ./...           verifies fix
  → git commit + push       continuous integration
```

**12 historical corrections seed from 雷管方案 (2026-07-31)**:
- v1 regex missed hyphenated author Abou-Alfa
- v1 missed multi-author list
- v1 wrong DOI tail for multi-segment
- v1 used type='url' (must be 'link')
- v1 sent array directly (must wrap in {rich_text})
- sync_all.py reverse-writes CSV
- Row 47 G column wrong PDF
- H column 152 row drift (not pushed)
- UTF-8 BOM broke Go encoding/csv
- CSV trailing \r\n mismatch
- Row 156 P43-4 D/G mismatch (Abou-Alfa vs Qin)
- Cron 30-min wasted 95% resources

## 集成到雷管方案

### 用户使用 (现在)

```bash
# 用 via54Medit 算法做匹配
medit citation match "Qin S, et al. Lancet Oncol. 2025" "<PDF text>"

# 抽取关键字段
medit citation test-extract "Abou-Alfa GK, et al. 2022"

# 经验闭环
medit citation replayer --generate  # 生成 Go 测试
medit citation replayer --seed corrections.json  # 从 JSON 导入修正
```

### 雷管方案迁移路径

**Step 1**: 移除 `~/Desktop/雷管方案_文献整理/_audit_report/scripts/` 里的 Python 算法
- ❌ `algorithm_vs_rules_research.py`
- ❌ `citation_table_key_field_match.py`
- ❌ `auto_detect_doi.py`
- ❌ `rich_text_h_converter.py`

**Step 2**: 改用 via54Medit
```bash
# 安装 via54Medit (一次性)
cd ~/Desktop/developments/via54Medit
go build -o /usr/local/bin/medit ./cmd/medit

# 在雷管方案里调
medit citation match "$D_col" "$pdf_text"
medit citation test-extract "$D_col"
medit feishu verify  # CSV ↔ Feishu
medit feishu push --row $row
```

**Step 3**: 每次修正 → 写入 corrections.json → 持续集成
```bash
medit citation replayer --seed ~/Desktop/雷管方案_文献整理/_corrections/new_corrections.json
# 自动生成 Go 测试, 提交到 via54Medit
```

## 测试结果

```
ok  	github.com/veawho/via54Medit/internal/citation	(cached)
ok  	github.com/veawho/via54Medit/internal/citation/corrections	0.144s
ok  	github.com/veawho/via54Medit/internal/integrations/feishu	0.963s
ok  	github.com/veawho/via54Medit/internal/hlo	0.776s
... (其他 27 个模块全部 ok)
```

**新增测试数**:
- `internal/citation/keyword_match_test.go`: 11 个
- `internal/citation/rich_text_test.go`: 14 个
- `internal/citation/corrections/corrections_test.go`: 8 个 (含 12 雷管方案修正 seed)

**总计**: **33 个新测试**, 全通过.

## 核心铁律

1. **算法驱动**: 用算法 + 数据结构替代硬编码规则
2. **不写死绝对值**: 期刊名 / 药物名 / 试验名通过 regex patterns + sets
3. **算法 + LLM 配合**: 置信度低时让 LLM 反思 (Phase 6.x 即将)
4. **经验闭环**: 用户修正 → corrections.json → 自动转测试 → CI 验证
5. **本地项目 = via54Medit consumer**: 雷管方案只是 use case, 不在 code 里
6. **零硬编码**: token / sheet_id / 路径全部 env / config
7. **GitHub-ready**: `.gitignore` 含雷管方案 + token 排除

## 失败案例学习 (来自雷管方案, 已写入 corrections/)

1. **H 列漏推** (v1.0 → v2.0): 全表 152 row 漂移 → 现在 5 列全推
2. **sync_all.py 反向覆盖**: 用户手动改的 G 列被覆盖 → 现在永不调
3. **lark-cli type 错误**: `type='url'` → 必须 `type='link'`
4. **rich text envelope 错误**: 直接 array → 必须 `{rich_text: [...]}`
5. **CSV trailing `\r\n`**: Go csv reader 不 strip → `TrimRight`
6. **UTF-8 BOM**: Go encoding/csv 不 strip → 手动 strip 3 字节
7. **DOI multi-segment**: `10.1158/1078-0432.CCR-24-0006` → last segment 不对, 用整段
8. **Abou-Alfa hyphenated author**: v1 regex `[A-Z][a-z]+` 不匹配 → v2 加 `(?:-[A-Z][a-z]+)*`
9. **Multi-author list**: v1 第一个 author 后停 → v2 继续到 journal/drug/year signal

## 关联资源

- via54Medit 主项目: `~/Desktop/developments/via54Medit/`
- 雷管方案 (私有, 不入 git): `~/Desktop/雷管方案_文献整理/`
- Hermes skill (Python ref): `~/.hermes/skills/csv-feishu-bidirectional-sync/`
- 设计文档: `docs/ARCHITECTURE.md`, `docs/EXPERIENCE-LOOP.md`, `docs/ALGORITHMS.md`

## 维护者

巫师叔叔 (via54) + Hermes Agent
最后更新: 2026-07-31 (Phase 6)
版本: v0.1.0-phase6