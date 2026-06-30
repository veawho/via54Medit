# FDA Orange Book 集成计划

> **优先级**: P0 (商业核心, TalkMED §6 引用)  
> **API**: https://api.fda.gov/ + Orange Book 数据下载  
> **鉴权**: API key (免费, 推荐)  
> **GitHub**: m-nolan/fda_orange / jamc88/patents-exclusivities-generic-entry

## 1. 数据能力

| 数据 | 用途 |
|---|---|
| 活性成分 (Active Ingredient) | 通用名匹配 |
| 商品名 (Proprietary Name) | 品牌识别 |
| 申请号 (Application Number) | NDA / BLA / ANDA |
| **专利信息** | **关键**: 哪个药受什么专利保护 |
| **独占期 (Exclusivity)** | **关键**: 数据独占/孤儿药独占 |
| **TE 码 (Therapeutic Equivalence)** | 仿制药替代评级 |

## 2. TalkMED 关系

PCSK9 类药都是新分子, 暂未触发专利悬崖。但 Lp(a) 类 (Pelacarsen / Olpasiran / Lepodisiran) 一旦上市, 立刻面临仿制竞争 — Orange Book 是必查源。

## 3. 集成步骤

### Phase 5.0.2
- [ ] `internal/source/fda_orange.go`
  - `SearchByDrug(name)` → `[]OrangeEntry`
  - `PatentsFor(app_no)` → `[]Patent` (专利号 + 过期日)
  - `ExclusivityFor(app_no)` → `[]Exclusivity`
- [ ] 数据源: openFDA API + 季度 Orange Book PDF 备份

### 数据模型
```go
type OrangeEntry struct {
    AppNo        string  // NDA021366
    Proprietary  string  // Repatha
    Ingredient   string  // evolocumab
    Strength     string
    Form         string
    Applicant    string
    Patents      []Patent
    Exclusivity  []Exclusivity
}

type Patent struct {
    PatentNo    string
    UseCode     string
    SubmitDate  time.Time
    ExpiryDate  time.Time  // 关键 — 何时可仿制
}

type Exclusivity struct {
    Code        string  // NCE / ODE / NDF / etc.
    ExpiryDate  time.Time
}
```

## 4. 测试

- [ ] Repatha (evolocumab) — NDA 125522
- [ ] Praluent (alirocumab) — NDA 142603
- [ ] Leqvio (inclisiran) — NDA 215537

## 5. 风险

- ⚠️ Orange Book 数据每月更新, 缓存策略要做好
- ⚠️ 美国专属 — 全球仿制竞争要结合 EMA / 中国 NMPA

## 6. 工作量

约 2 天