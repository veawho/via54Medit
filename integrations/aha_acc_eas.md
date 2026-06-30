# AHA / ACC / EAS 会议摘要集成计划

> **优先级**: P1 (TalkMED §4 临床数据核心, **本次 PDF 直接相关**)  
> **来源**: 各会议官方 abstract 服务器 + 第三方摘要站

## 1. 数据能力

| 会议 | 学科 | 官网 |
|---|---|---|
| **AHA Scientific Sessions** | 心血管 | https://professional.heart.org |
| **ACC Annual Scientific Session** | 心血管 | https://www.acc.org |
| **EAS Congress** | 血脂/动脉粥样 | https://eas-society.org |
| ASCO Annual Meeting | 肿瘤 | https://meetings.asco.org |
| ESMO Congress | 肿瘤 | https://www.esmo.org |
| ESC Congress | 心血管 | https://www.escardio.org |

## 2. TalkMED §4 关键引用

> "AHA 2025/ACC 2026 会议数据"

- AHA 2025 Sessions: 2025年11月, 含 Lp(a) 类 (Olpasiran / Lepodisiran) 最新数据
- ACC 2026: 2026年3月
- EAS 2026: 5月, **血脂领域最核心**, **必定有 Lp(a) / PCSK9 进展**

## 3. 集成步骤

### Phase 5.5
- [ ] `internal/source/conference.go`
  - `SearchAHA(query, year)` → `[]Abstract`
  - `SearchEAS(query, year)` → `[]Abstract`
  - `SearchACC(query, year)` → `[]Abstract`
- [ ] 抓取 + LLM 抽取 (关键结果数字, e.g. LDL-C 降幅)

### 摘要源选择
- 官方 abstract 服务器 (HTML 抓取)
- 第三方: TCTMD (https://www.tctmd.com) / Medscape / Healio 报道
- 优先抓 abstract 编号 (如 AHA 2025-Lp(a-Olpasiran)

## 4. 测试

- [ ] 黄金 9: 已知 Lp(a) 关键 trial 的会议摘要
  - Olpasiran OCEAN(a) — AHA 2024 末公布
  - Lepodisiran — AHA 2025
  - Pelacarsen Lp(a)HORIZON — 预计 ACC 2026

## 5. 风险

- ⚠️ 会议网站经常改版, HTML 抓取 fragile
- ⚠️ 部分会议摘要收费, 需机构订阅
- ⚠️ 中文报道未必精确, 推荐中英双语抓 + LLM 整合

## 6. 工作量

约 4-5 天 (6 个会议网站, 反爬各异)