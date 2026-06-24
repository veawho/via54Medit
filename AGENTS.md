# AGENTS.md — via54Medit 跨工具协作规约

> 适用于 **Claude Code / Cursor / GitHub Copilot / Hermes Agent / OpenCode / Codex** 等所有 AI 工具。
> 本文件等价于 `CLAUDE.md` / `.cursorrules` / `.github/copilot-instructions.md`，各工具自动识别同名约定。

---

## 项目身份

- **名称**: via54Medit
- **副标题**: Multi-Source Medical Literature Router for Evidence-Based Medicine
- **作者**: 巫师叔叔 (via54) + Hermes Agent
- **GitHub**: github.com/veawho/via54Medit (private)
- **本地路径**: `G:\agent\developments\via54Medit\`
- **许可**: MIT (templates/configs/docs) + AGPL-3.0 (source code)
- **依赖**: github.com/veawho/via54Design（**可选借鉴**,非强制 — 2026-06-24 修订,见 ARCHITECTURE §21）

## 技术栈

| 层 | 技术 |
|---|---|
| 主语言 | Go 1.22+ (CLI + MCP Server) |
| 热路径 | Rust 1.75+ (PDF 解析 / 分块) |
| 胶水 | Bash (scripts/) |
| 数据库 | SQLite (FTS5) + Qdrant (vector) + bge-m3 (embedder) |
| 协议 | MCP (Model Context Protocol) |
| 测试 | go test + VHS (e2e) + cargo test |
| 文档 | Markdown + Go doc + cargo doc |

## 用户偏好 (巫师叔叔 4A 风格)

1. **第一性铁律验证**: 不接受"理论可行"，必须有可运行示例
2. **批量全修**: 一次给完整修复方案，不分步询问
3. **AGPL-3.0 + MIT 双许可**: 源码 AGPL, 模板/配置 MIT
4. **全平台思维**: 主动考虑 macOS / Linux / Windows
5. **结构化输出**: 表格、清单、决策树；少用 bullet soup
6. **拒绝试错式**: 先穷尽诊断再行动
7. **黄金比例 + 黄金测试**: 关键功能必有 9 案例 / 31 单元测试
8. **确定性优于随机**: map 遍历必排序，CSS 变量生成必 deterministic
9. **质量门禁 8 项**: 编译通过 / 单元测试 / 集成测试 / lint / format / vet / race / coverage≥80%
10. **文档先行**: ARCHITECTURE.md 在 Phase 0 完成，ROADMAP.md 跟 Phase 同步

## 目录结构 (黄金布局)

```
via54Medit/
├── cmd/                 # 入口 (medit CLI + medit-mcp Server)
├── internal/            # 私有 (router / source / enrich / dedupe / extract / anno2ppt / persist / version)
├── pkg/                 # 公开 API
├── rust/                # Rust 库 (cgo 桥)
├── scripts/             # Shell 胶水
├── templates/           # PPT / LaTeX / YAML 模板
├── tests/               # e2e / stress / unit
├── docs/                # 全部文档
├── configs/             # 默认配置
└── .github/workflows/   # CI/CD
```

## 命令速查

```bash
# 构建
go build -o bin/medit.exe ./cmd/medit
go build -o bin/medit-mcp.exe ./cmd/medit-mcp
cd rust && cargo build --release

# 测试
go test ./...                # 单元
go test -tags=integration    # 集成
cd rust && cargo test

# 代码质量
go vet ./...
gofmt -l .
cd rust && cargo clippy
cd rust && cargo fmt --check

# 运行
./bin/medit version
./bin/medit ask "SGLT2 抑制剂对心衰预后"
./bin/medit-mcp  # 启动 MCP Server
```

## 编码规约

- **Go**: gofmt + goimports + golangci-lint (via54Design 配置)
- **Rust**: rustfmt + clippy 严格模式
- **命名**: 公开 API 必有 doc comment, 内部 `_` 前缀
- **错误**: wrapped error (`fmt.Errorf("...: %w", err)`), 不丢 context
- **日志**: 结构化 (`log/slog`), 不打敏感信息
- **并发**: worker pool + semaphore, 不裸 goroutine 撒
- **依赖**: 显式 go.mod / Cargo.toml, 不用 replace 除非必要

## 关键约束 (从 via54Design 借鉴,**2026-06-24 降级为可选**)

1. **不跑本地 LLM** (7B 质量低 + 4-10GB RAM)，bge-m3 (1GB) 是唯一例外
2. **map 遍历前必排序** (Go spec 规定随机)
3. **Plugin 模式**: --embedder / --vectorstore / --provider 三个 flag 必支持
4. **跨平台首发**: Win + Mac + Linux 三平台 binary
5. **CI 必过**: push 前跑 `go test -race -coverprofile=coverage.out`
6. **不依赖 Hermes 内部 API**: via54Medit 是 standalone Go 项目,Hermes 只是开发助手
7. **不依赖任何私有仓库**（**2026-06-24 新增铁律**）: `git clone && go build` 必须 100% 成功。via54Design 借鉴接口设计即可,实现走 `internal/foundation/` hand-roll。**ARCHITECTURE §21** 是最高优先级。

## 任务流转

| 任务类型 | 派给 |
|---|---|
| 写新 source 适配器 | techlab agent |
| 写 enricher | prdlab agent |
| 写 PDF/Rust 工具 | prdlab agent |
| 战略/医学方法学 | strategiclab agent |
| 代码质量审计 | auditlab agent (派单时加 --audit) |
| 调研 / 综述 | research template agent |

派单命令: `python ~/.hermes/bin/lab_dispatch.py <agent> "<req>"`

## 反馈循环

每次任务完成后:
1. 跑 `go test ./...` + `cargo test`
2. 更新 `CHANGELOG.md` 一行
3. Commit message 格式: `<scope>: <verb> <noun> (Phase X)`
4. Push 到 GitHub 私库
5. 重大决策 → 更新 `docs/ARCHITECTURE.md`

---

**最后更新**: 2026-06-09 (Phase 0 init)
**维护者**: 巫师叔叔 via Hermes Agent
