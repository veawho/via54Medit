# 豆包工作伙伴：循证医学助手 Medit

> 按豆包工作「伙伴」官方文档标准构建。一个安装包仅包含一个工作伙伴；从豆包客户端「插件·技能·伙伴 → 工作伙伴 → 创建新伙伴 → 从本地导入」拖入本安装包即可使用。

## 伙伴元信息

| 项目 | 内容 |
|---|---|
| 伙伴名称 | 循证医学助手 Medit |
| 形象 | `medit伙伴头像.png`（DNA 双螺旋 + 放大镜研究图标） |
| 人设 | 资深循证医学（EBM）研究助理：以可溯源证据作答，分级输出，绝不裸给结论 |
| 擅长领域 | 医学文献多源检索与融合、PICO/GRADE 评估、系统综述、证据包→PPT 引用应证、文献 highlight 与 OCR 复核、医学策略策划（medplan）、证据同步飞书 |
| 可调用技能 | `via54medit`（医学循证多源检索引擎 + 全工具链编排） |

## 运行架构（默认）

```
豆包工作（伙伴主脑：意图理解、任务编排、成果交付）
   │ 调用技能 via54medit
   ▼
via54Medit（Go CLI 引擎：4 源检索融合 / PICO / GRADE / PPT 应证 / highlight 流水线）
   │ LLM 一律走 DeepSeek（--llm deepseek，默认模型 deepseek-flash）
   ▼
DeepSeek-cli（bin/deepseek.ps1：chat / vision 图像理解 / models / balance，自动埋点 token+耗时）
   │ 实时用量 → lark-cli → 飞书多维表格（每 5 分钟 + 周一 10:30 校验标记）
   ▼
飞书多维表格（Hack Health：实时使用明细 / 监控数据周报）
```

- 主脑：豆包工作（伙伴本体，负责角色化任务执行与交付）。
- 引擎：via54Medit（仓库全部能力，Go CLI + MCP + Python 流水线）。
- LLM 通道：DeepSeek（**已剥离 hermes**：`--llm hermes` 不再可用；config 无 hermes 段；MiniMax 仅保留为手动备用）。
- 落地：lark-cli（用户身份）绑定飞书账号与多维表格；DeepSeek-cli / mmx-cli 调用自动实时采集。

## 依赖与强制条件（部署即校验）

运行 `deploy_medit.ps1` 自动补全全部依赖，**缺失即 FAIL**：

- Go 工具链与 medit 二进制（自动编译部署，含 DeepSeek 通道补丁）
- Python 依赖（pymupdf / python-pptx / Pillow / pywin32）
- FFmpeg、PaddleOCR、poppler、Office COM
- **DeepSeek-cli（强制）**：`bin/deepseek.ps1` 自动部署
- **DeepSeek API Key（强制）**：`$env:DEEPSEEK_API_KEY` 或 `~/.deepseek.key`，缺失体检 FAIL 并提示提供
- lark-cli 自动部署 + 自动绑定本地飞书登录账号（用户身份，无企业自建应用凭据）
- 多维表格自动绑定：`Al8xbS4u9av85esUgjvcWYDankb`（Hack Health）
- 定时任务：`medit-usage-collector`（每 5 分钟实时采集）、`medit-monday-finalize`（周一 10:30 校验标记）

## 安装包内容

```
循证医学助手-Medit-伙伴安装包.zip
├── PARTNER.md            ← 本文件（伙伴元信息）
├── medit伙伴头像.png      ← 伙伴形象
├── deploy_medit.ps1       ← 一键部署：全量依赖 + DeepSeek-cli 强制 + 飞书绑定
├── README.md              ← 使用说明
├── skills/via54medit/     ← 技能（SKILL.md 大写 + YAML name/description，符合上传标准）
│   ├── SKILL.md
│   ├── references/commands.md
│   └── scripts/medit.sh
└── bin/                   ← deepseek.ps1 / usage_collector.py / monday_finalize.ps1 / medit.exe 等
```
