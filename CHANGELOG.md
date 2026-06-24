# Changelog

All notable changes to via54Medit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Phase 0 (2026-06-09)

#### Added
- 项目初始化
  - `docs/ARCHITECTURE.md` — 5 层架构 + 20 节设计文档
  - `AGENTS.md` — 跨 AI 工具协作规约
  - `README.md` / `README.zh-CN.md` — 中英双语文档
  - `LICENSE-AGPL-3.0` / `LICENSE-MIT` — 双许可
  - 完整目录树 (22 个子目录)
  - Go module: `github.com/veawho/via54Medit`
  - Cargo workspace (rust/)
  - 4 个空接口 (Source / Embedder / VectorStore / Enricher)
  - `medit version` 可跑
  - GitHub 私库: github.com/veawho/via54Medit

### Phase 0 修订 (2026-06-24)

#### Changed
- **架构决策**: via54Design 强制依赖 → **可选借鉴** (走 ARCHITECTURE §17.3 路径 ② hand-roll)
- **新增铁律**: `git clone && go build` 必须 100% 成功,0 外部业务依赖 (ARCHITECTURE §21)
- **AGENTS.md 关键约束**: 新增第 7 条"不依赖任何私有仓库"
- **README.md 致谢段**: via54Design 改为"借鉴接口设计,实现独立"
- **configs/default.yaml**: 头部加修订说明
- **gofmt**: 2 个未格式化文件落地
- **单元测试**: 新增 8 cases (pkg/types 4 + internal/version 4)
- **git tag**: `phase0-done` annotated tag 落地

#### Closed (ARCHITECTURE §19 开放问题 6 条全部拍板)
- §19.1 命名空间: 维持 via54Medit (module) / medit (CLI)
- §19.2 MCP 工具数: 维持 4 个,本地查询走 CLI
- §19.3 GRADE 评级: 走简化版,完整版 v0.5 评估
- §19.4 Web UI: 不做,MCP 路径覆盖
- §19.5 Windows 安装包: zip + scoop/winget,不做 MSI
- §19.6 GitHub 公开: 维持 private,Phase 5 再开

[Unreleased]: https://github.com/veawho/via54Medit/compare/v0.0.0...HEAD
