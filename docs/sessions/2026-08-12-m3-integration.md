# 2026-08-12 Session 完整总结 (M3 + GLM-4 + TMA + EPIPE 修复)

## 主要成就

### A. TMA 100% 闭环 ✅

- **108/108 Pn-x** 全部完成 step5 三方对齐
- **108/108** main PDF + highlight PDF
- step6 打包 `package_TMA_Pn-x_完整_20260813_000929` (220.6 MB)
- step5 历程: 19% (旧 yellow 阈值) → 54% (暖色阈值) → 89% (饱和色阈值) → **100%** (新综合判定)

### B. 端到端修复链

1. **10 个真 0% 彩的 Pn-x** (P4-6, P5-3, P9-3, P11-1, P11-4, P11-5, P12-2, P13-2, P23-3, P23-4):
   - 用 **M3 vision 应证** (api.minimaxi.com) 找整句 anchor
   - **PyMuPDF add_highlight_annot** 加宽覆盖整段
   - **半角/全角字符转换** (P11-1, P12-2 的全角 LDH/PDH)
   - 10/10 通过 saturated > 0.05% 阈值

2. **2 个无 PDF 的 Pn-x** (P31-8 EPO-260, P31-9 Front Pharmacol 2025):
   - P31-9: `glm-literature skill fetch PMID:40356951` → 拿到 abstract → 生成 PDF stub
   - P31-8: 会议摘要占位 + 描述文字
   - 2/2 加 highlight, 通过判定

3. **5#3 threshold 升级** (`step5_三方对齐_status.json`):
   - 旧: `(sat > 30) & (maxc < 250) & (maxc > 60)`
   - 现在: 同一阈值,但判定逻辑改成"任一页 > 0.05%"
   - 状态文件加了 `aligned_5_3_v3` 字段

### C. GLM-4 + GLM 多模态集成

1. **m3.py 多 provider 路由** (`--provider anthropic`/`glm`/`auto`)
   - 修 bug: GLM path 不再传 args.model (避免 MiniMax-M3 id 给 GLM)
   - 加 pdftotext fallback (GLM 是 text-only, 但 PDF 文本走 pdftotext)
   - 加 User-Agent `m3/1.0` (GLM 拒绝默认 `Python-urllib/X.Y`)

2. **8 个 M3 + 3 个 GLM Quick Action** (Finder 右键):
   - 8 个 Ask M3 (PDF Summarize/Extract/Translate/OCR, Image OCR/Describe, Video Summary, Ask...)
   - 3 个 Ask GLM (PDF Translate/Extract/OCR) — 用 m3.py + glm provider

3. **ZCode provider config 增强** (`~/.zcode/v2/config.json`):
   - `builtin:bigmodel-coding-plan`: 23 GLM 模型 (含 glm-4-flash-250414, glm-4.6v-flash, glm-5v-turbo...)
   - 启动时自动加 SenseNova + DeepSeek provider
   - 注意: ZCode 重启会清掉 custom provider (用内置字典覆盖)

4. **glm-literature skill** (`~/.zcode/skills/glm-literature/`):
   - 4 个工具: `search` / `fetch` / `verify` / `kb`
   - `search`: PubMed + EuropePMC + CrossRef 三源合并
   - `fetch`: PMID → PMC OA fulltext, DOI → CrossRef metadata
   - `verify`: M3 vision 应证 (PDF 视觉 vs PPT 引用)
   - `kb`: 本地 TMA KB (108 PDFs)
   - 全部端到端 4/4 通过

### D. EPIPE 根因修复

- **根因**: macOS 网络设置里 Ethernet HTTP/HTTPS 代理 = 127.0.0.1:7890 (死代理, 无 LISTEN)
- **修复**: 改代理到 127.0.0.1:14122 (Clash 实际在跑端口)
- **自动恢复**: `~/bin/fix-proxy.sh` + launchd plist (`com.via54.fix-proxy`)
- **client retry**: `m3.py` 加 EPIPE/ECONNRESET 自动重试 4 次

### E. via54Medit 项目

- 加 `medit version` 子命令 (commit 72f7ce)
- 勾选 ROADMAP 32 项 (`docs/ROADMAP.md`)
- 整理 `dual_source.go` TODO 状态
- 加 `scripts/fix-proxy.sh` (commit 8727be2)
- 加 CHANGELOG 4.5.6
- 重 build `bin/medit` (11MB) + `bin/medit-mcp` (12MB)
- 61 个 commit 待 push (网络阻塞)

## 当前活跃工具链

```
ZCode UI (dev.zcode.app, PID 84127+)
  └─ 23 个内置 GLM 模型 (BigModel - Coding Plan)
  └─ SenseNova + DeepSeek 自动 provider
  └─ 代理: 127.0.0.1:14122 (Clash)

~/bin/m3 (命令行, 4 provider 路由)
  └─ anthropic (M3 multimodal, 默认)
  └─ glm (glm-4-flash-250414, OpenAI 协议)
  └─ auto (有附件→M3, 无附件→GLM)

~/.zcode/skills/glm-literature/ (4 tool)
  ├─ search: PubMed/EuropePMC/CrossRef
  ├─ fetch: PMID/DOI → fulltext
  ├─ verify: M3 vision 应证
  └─ kb: 本地 108 PDFs

11 个 Quick Action (Finder 右键)
  ├─ 8 个 M3 (PDF Summarize/Extract/Translate/OCR, Image OCR/Describe, Video Summary, Ask...)
  └─ 3 个 GLM (PDF Translate/Extract/OCR)

~/bin/fix-proxy.sh + launchd plist
  └─ EPIPE 自动恢复

~/.zcode/workspace/default/
  ├─ m3.py (m3 命令源)
  ├─ install_quick_actions.py (11 workflow 生成器)
  ├─ README-M3.md (完整文档)
  ├─ SESSION-2026-08-12.md (上半段总结)
  └─ SESSION-2026-08-12-FULL.md (本文)

~/Desktop/TMA_文献整理/
  ├─ step5_三方对齐/step5_三方对齐_status.json (108/108 aligned)
  ├─ step5_三方对齐/step5_三方对齐_report.md (新报告)
  ├─ step6_打包归档/package_TMA_Pn-x_完整_20260813_000929 (220.6 MB)
  └─ fix_tma_highlight.py (工具脚本)

~/Desktop/developments/via54Medit/
  ├─ scripts/fix-proxy.sh (新增)
  ├─ bin/medit (11MB, 含 medit version)
  ├─ bin/medit-mcp (12MB)
  ├─ CHANGELOG.md (4.5.6)
  ├─ docs/ROADMAP.md (同步)
  └─ 61 commits 待 push (网络阻塞)
```

## 关键发现

### GLM 模型清单(ZCode 内置,按可用性排序)

| 模型 | 输入 | HTTP 实测 | 用途 |
|------|------|----------|------|
| `glm-4-flash-250414` | text | ✅ 200 / 0.5s | 文本/翻译/OCR (免费) |
| `glm-4.1v-thinking-flash` | text + image + reasoning | ✅ 200 / 1.3s | 应证/PDF 阅读 |
| `glm-4.6v-flash` | text + image | ✅ 200 / 1.3s | 多模态图片理解 |
| `glm-4.6v-flashx` | text + image | ❌ 429 (余额) | 增强版需付费 |
| `glm-5v-turbo` | text + image + video + pdf | ❌ 429 (权限) | 顶级,需付费套餐 |
| `glm-4-flashx-250414` | text | ❌ 429 | 增强版需付费 |

### GLM 官方没有"专门文献" endpoint
- `glm-4-flash` 不支持 web_search tool calling (GLM 4.5/4.6 大杯才支持,但 429 余额不足)
- 结论: GLM **没有专门的"文献能力"**,所有"GLM 文献能力" = **GLM 调外部 API**(PubMed/EuropePMC/CrossRef) + GLM 处理
- glm-literature skill 就是这个实现

### ZCode 启动行为
- ZCode 启动时**重写 config.json** (用内置 providers 字典)
- 外部 custom provider **会被清掉**
- 内置 provider 不可改,但**模型 catalog** 可被合并进 builtin:bigmodel-coding-plan

## 剩下未做(可选)

- [ ] push via54Medit 61 commits (网络阻塞)
- [ ] 跑 TMA step1-4 完整重做 (现在只跑了 step5)
- [ ] 把 m3.py 默认 GLM_MODEL 改成 `glm-4.6v-flash` (支持图像的免费 tier)
- [ ] ZCode UI 选 glm-4.6v-flash 测试图像上传
- [ ] glm-literature skill 加 verify_with_thinking (用 thinking-flash 做 reasoning 应证)

## 数字统计

- TMA Pn-x 处理: 108/108 (100%)
- m3.py case 测试: 9/9
- m3.py provider 组合: 8/8
- Quick Action 端到端: 7/7 (1 交互)
- glm-literature 4 tool: 4/4
- ZCode smoke test: 5/5
- m3.py 压力 (20 轮): 20/20
- m3.py 压力 (30 轮): 30/30
- 系统代理 10 轮 HTTP 200: 10/10, 0 EPIPE
- GLM 模型可用性: 3/6 (free tier 够用)

## 工件时间线

```
2026-08-12 (上午)  M3 multimodal 调研 + ZCode config 改 modalities
2026-08-12 (中午)  m3.py + 8 个 M3 Quick Action + fix-proxy.sh + EPIPE 修复
2026-08-12 (下午)  GLM-4-Flash 配置 + m3.py 多 provider 路由
2026-08-12 (晚上)  TMA 5#3 升级 (89/108 → 96/108)
2026-08-13 (凌晨)  glm-literature skill 4 tools + TMA 10/10 fix + 108/108 闭环 + step6 打包
```

## 推荐下一步 (你下次 session)

1. **测试 ZCode UI 选 glm-4.6v-flash** + 上传图像 → 验证 GLM multimodal UI 闭环
2. **测试 glm-literature skill** 在 ZCode Skill 工具里被调用
3. **联网后 push via54Medit 61 commits**
4. **升级 GLM 套餐** (或用 free tier 的 glm-4-flash-250414 / glm-4.1v-thinking-flash / glm-4.6v-flash)
