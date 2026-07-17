# docproc — 临床文档处理流水线

> **via54Medit v9.7 新增** | 2026-06-30 升级

## 定位

文档下载（`full_text_finder` / `download` 包）→ **文档处理** → 实体抽取 → SOAP 摘要 → FHIR 兼容输出

**参考项目：**
- `medical-document-processor` (Mistral AI Solutions) — workflow ingest→extract→summarize→structure
- `OpenClaw-Medical-Skills` (FreedomIntelligence) — clinical-nlp-extractor + clinical-note-summarization

## Pipeline 三阶段

```
[TextExtractor] ─→ [EntityExtractor] ─→ [SoapSummarizer]
  (pdftotext)        (LLM NER)            (LLM SOAP)
     │                   │                    │
     ▼                   ▼                    ▼
  .pdf / .html      symptoms, meds,     Subjective/Objective
  .txt / .md         labs, vitals,       Assessment/Plan
                     diagnoses,          alerts, confidence
```

## CLI

```bash
# 全量：文本提取 + 实体 + SOAP
medit docproc clinical_note.txt

# 仅实体（跳过 SOAP）
medit docproc clinical_note.txt --no-soap

# 自定义 LLM
medit docproc note.pdf --llm hermes --llm-endpoint http://localhost:8765
```

输出格式：

```
--- RAW TEXT ---
(提取的纯文本)

--- ENTITIES ---
{"symptoms": [...], "medications": [...], "lab_values": [...], ...}

--- SOAP ---
{"subjective": "...", "objective": "...", "assessment": "...", "plan": "...", "confidence": 0.9}
```

## Go API

```go
import "github.com/veawho/via54Medit/internal/docproc"

// 全量流水线
pipeline := docproc.NewPipeline(llmProvider)
result, _ := pipeline.Process(ctx, "note.txt")

// 仅实体
pipeline := docproc.NewPipelineWithEntityOnly(llmProvider)
result, _ := pipeline.Process(ctx, "note.pdf")
```

## 输出类型

| 类型 | 结构 | 说明 |
|---|---|---|
| `ExtractedEntities` | `Symptoms[]`, `Medications[]`, `LabValues[]`, `Diagnoses[]`, `VitalSigns[]`, `Procedures[]`, `ActionItems[]`, `Contradictions[]`, `MissingInfo[]`, `PHIFlags[]` | LLM 实体抽取，JSON 输出 |
| `SoapSummary` | `Subjective`, `Objective`, `Assessment`, `Plan`, `Alerts[]`, `MissingInfo[]`, `Confidence` | LLM SOAP 摘要 |
| `Result` | `RawText`, `Entities`, `Soap`, `Errors`, `Duration` | 全量 pipeline 输出 |

## FHIR 兼容性

`ExtractedEntities` 字段命名与 FHIR Resource 兼容：
- `symptoms` → FHIR `Condition`
- `medications` → FHIR `MedicationRequest`
- `lab_values` → FHIR `Observation`
- `diagnoses` → FHIR `Condition`
- `vital_signs` → FHIR `Observation`

## PHI 安全规则

1. **不捏造** — 只提取文本中明确存在的内容
2. **否定排除** — "no fever" 不列为症状
3. **PHI 标记** — 提取患者名、ID、出生日期等并放入 `phi_flags`
4. **矛盾检测** — 文本内不同部分矛盾时标记到 `contradictions`
5. **缺失提示** — 临床相关信息缺失时标记到 `missing_info`

## 依赖

- `pdftotext` (poppler-utils) — PDF 文本提取（非必需，缺失时报错）
- `github.com/PuerkitoBio/goquery` — HTML 解析
- `foundation.LLMProvider` — LLM 调用（hermes / openai）

## 测试

```bash
go test ./internal/docproc -count=1 -v
# 17 项测试全部通过
```

## 集成点

| via54Medit 环节 | docproc 作用 |
|---|---|
| `download` 包下载 PDF | `TextExtractor` 提取文本 |
| `source` 包拉文献 | `EntityExtractor` 从文献摘要抽实体 |
| `enrich` 包 enrich | `SoapSummarizer` 生成摘要 |
| `query` / `ask` | `Result.Entities` 作为结构化上下文 |
