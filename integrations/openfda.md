# OpenFDA 集成计划

> **优先级**: P0 (EBM + 商业双用, **最重要**)  
> **API**: https://api.fda.gov/  
> **鉴权**: API key 选填 (有 120K/天, 无 1K/天)  
> **GitHub MCP**: cyanheads/openfda-mcp-server (**14 tools**, Apache-2.0, 公开 hosted)

## 1. 数据能力 (14 tools)

| Endpoint | 数据 |
|---|---|
| `/drug/label` | FDA 批准药物的官方标签 (SPL) — 15万+ |
| `/drug/ndc` | 国家药品代码 (NDC) 目录 |
| `/drug/event` | 不良事件报告 (FAERS) |
| `/drug/enforcement` | 召回/执法 |
| `/drug/shortage` | 药物短缺 |
| `/drug/drugsfda` | 药品申请 (NDA/BLA/ANDA) |
| `/drug/approval` | 批准历史 |
| `/device/...` | 医疗器械 |
| `/food/...` | 食品召回 |
| `/cosmetic/...` | 化妆品事件 |
| `/other/...` | 兽药/烟草 |

## 2. 跟 TalkMED PDF 关系

TalkMED §2 "PCSK9 注射剂市场" 大量引用 FDA 数据:
- 上市 7 款 PCSK9 注射剂 → openfda `/drug/label`
- 销售轨迹 → 需结合第三方 (药智/Citeline), openfda 不直接给销售
- 不良事件 → `/drug/event` (TalkMED 没展开但应加)

## 3. 集成步骤

### Phase 5.0.2
- [ ] `internal/source/openfda.go` — Go client
  - `DrugSearch(query)` → `[]Drug`
  - `DrugLabel(set_id)` → `*DrugLabel`
  - `AdverseEvents(drug)` → `[]Event`
  - `Shortages()` → `[]Shortage`
- [ ] 跟 cyanheads/openfda-mcp-server 协议兼容 (可作 MCP server 子进程)

### 数据模型
```go
type Drug struct {
    SetId       string
    Name        string
    GenericName string
    Manufacturer string
    NDA         string  // 新药申请号
    ApprovalDate time.Time
    Routes      []string
    PharmClass  []string
}

type DrugLabel struct {
    Indications []string
    Dosage      string
    Warnings    []string
    AdverseReactions []string
    // ...
}
```

## 4. 测试

- [ ] 黄金 9 案例: evolocumab / alirocumab / inclisiran / Rosuvastatin / Atorvastatin 等
- [ ] 验证 `/drug/label` 拉取 PCSK9 7 款产品的标签

## 5. 风险

- ⚠️ API 限速严 (1K/天无 key), 加 API key 后 120K/天, 用户需注册
- ⚠️ 中文标签字段是英文 (FDA 主英), 翻译要在 LLM 层做

## 6. 工作量

约 2 天 (API 简单, 主要是 schema 映射)