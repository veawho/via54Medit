# DECISIONS-PENDING (用户待补决策)

> **生成日期**: 2026-06-30
> **背景**: via54Medit v5.0 升级. 5 决策点中 2 已锁 (1=架构, 2=P0源, 4=付费=0, 5=5 等于 4 已锁).
> 待补: 决策 3 (layer 5B) + 决策 6 (biomcp 集成)
>
> **格式**: 每个问题列 A/B/C 选项 + 推荐 + 默认值 (不答时用什么)

---

## 决策 3: 商业 CLI 形态 — 隔离 vs 子命令?

**agent 问**: "是否需要新增 layer 5B (商业 CLI), 还是作为现有 CLI 子命令 (我倾向前者, 隔离干净)"

**agent 推荐**: 前者 (layer 5B 隔离), 理由:
- EBM 学术 vs 商业情报 业务流程差异大
- 商业需要 7 页 PDF + 图表渲染, 不应污染 EBM 路径
- 用户体验: `medit-ask` vs `medit-intel` 比 `medit ask --mode=business` 清晰

**待你定**: 隔离 (新 binary `medit-intel`) 还是合并 (新子命令 `medit intel`)?

### 5 明确问题

| # | 问题 | 选项 A | 选项 B | 选项 C | 默认 (不答) |
|---|------|-------|-------|-------|------------|
| 3.1 | **新 binary 还是子命令?** | A1: `medit-intel` 新 binary (layer 5B) | A2: `medit intel` 子命令 | A3: `medit ask --intel` flag | A1 (新 binary, agent 推荐) |
| 3.2 | **共享还是独立代码?** | B1: 完全独立 (2 仓) | B2: 共享 core (1 仓 2 binary) | B3: 插件动态加载 | B2 (共享 core, 2 binary 复用 Layer 1-3) |
| 3.3 | **MCP server 1 还是 2?** | C1: 1 个 medit-mcp 含双模式 | C2: medit-mcp + medit-intel-mcp | C3: 1 server + mode flag | C1 (1 server 双模式, 简化部署) |
| 3.4 | **配置/凭据?** | D1: 单一 config.yaml 含双 mode | D2: 分离 config + 分 env | D3: 单一 config + 模式切换 | D1 (单一 config, 简单) |
| 3.5 | **上线方式?** | E1: v5.0 一起上 (双模式) | E2: v5.0 学术 + v5.5 商业 | E3: v5.0 商业 + v5.5 学术 | E2 (稳, v5.0 先稳学术 + 商业代码, v5.5 商业完整) |

**待回答**: 回复 3.1-3.5 任一题, 或用默认.

---

## 决策 6: biomcp 集成方式 — Fork vs MCP 协议?

**agent 问**: "是否真要 fork genomoncology/biomcp (MIT) 进 via54Medit, 还是 MCP 协议调用?"

**待你定**: fork 集成 (代码进入 via54Medit) 还是 MCP 协议调用 (via54Medit 作 MCP client)?

### 5 明确问题

| # | 问题 | 选项 A | 选项 B | 选项 C | 默认 (不答) |
|---|------|-------|-------|-------|------------|
| 6.1 | **集成方式?** | A1: Fork biomcp 进 via54Medit (本地代码) | A2: MCP 协议调用 (via54Medit 作 client) | A3: HTTP/REST 桥接 (经 biomcp server) | A2 (MCP 协议, 解耦, 跟着行业走) |
| 6.2 | **biomcp 版本同步?** | B1: 固定 fork, 手动 sync | B2: 自动 git sync (monthly) | B3: 只用 API 不直接依赖 | B2 (monthly 自动 sync) |
| 6.3 | **覆盖 12+ 实体类别?** | C1: 100% 用 biomcp | C2: 60% biomcp + 40% 自写 | C3: 100% 自写 (re-impl) | C2 (60/40 混合, 关键源自写保证控制) |
| 6.4 | **license 兼容性?** | D1: biomcp MIT → via54Medit AGPL ✅ 兼容 | D2: 需要加 attribution 段 | D3: 不 fork 避免 license 问题 | D1 (MIT + AGPL 兼容, 注意 attribution) |
| 6.5 | **MCP server 部署?** | E1: biomcp 独立 server + via54Medit client | E2: 把 biomcp 包进 via54Medit | E3: 第三方 hosted (genomoncology.io) | E1 (独立 server, 解耦) |

**待回答**: 回复 6.1-6.5 任一题, 或用默认.

---

## 总结

- **决策 1+2+4+5 已锁** (5 个中 4 个 = 1 重复)
- **决策 3+6 待补** = 10 个明确问题等你答
- 任何决策你可以:
  - 答单个题 (e.g. "3.1=A1, 3.2=B2, 3.3=C1")
  - 答整组 (e.g. "3 全默认, 6 全默认")
  - 全部不答 = 全用默认

## 默认值汇总 (不答时)

| 决策 | 默认 | 说明 |
|------|------|------|
| 3.1 | A1 | 新 binary `medit-intel` (隔离干净) |
| 3.2 | B2 | 共享 core (1 仓 2 binary 复用 Layer 1-3) |
| 3.3 | C1 | 1 个 medit-mcp 双模式 (简化部署) |
| 3.4 | D1 | 单一 config.yaml (简单) |
| 3.5 | E2 | v5.0 学术 + v5.5 商业完整 (稳) |
| 6.1 | A2 | MCP 协议调用 (解耦) |
| 6.2 | B2 | monthly 自动 git sync |
| 6.3 | C2 | 60% biomcp + 40% 自写 |
| 6.4 | D1 | MIT + AGPL 兼容 (注意 attribution) |
| 6.5 | E1 | biomcp 独立 server |

**整体默认配置**:
- 商业 CLI: 新 binary medit-intel, 共享 via54Medit core, 1 个 medit-mcp, 单一 config, v5.0 学术+商业代码+v5.5 商业完整
- biomcp 集成: MCP 协议调用 (via54Medit 作 client), monthly 自动 sync, 60/40 混合, MIT+AGPL 兼容, biomcp 独立 server
