# 飞书工作伙伴：循证医学助手 Medit（workmate 目录 / Workmate Directory）

> **双语 / Bilingual** · 本目录是 via54Medit 仓库中 **飞书（豆包）工作伙伴** 的独立发布目录。
> This directory is the standalone release directory of the **Doubao/Feishu Work workmate** inside the via54Medit repo.

伙伴安装包与技能上传包以 **GitHub Release 附件**形式发布（本目录维护源码级配置），见 Releases 页面 `v5.4.51+`。
Installer & skill packages ship as **GitHub Release assets**; this directory keeps the source-level config. See Releases `v5.4.51+`.

## 目录内容 / Contents

| 文件 / File | 用途 / Purpose |
|---|---|
| `PARTNER.md` | 伙伴元信息：形象 / 人设 / 擅长领域 / 运行架构 — Workmate metadata: persona / expertise / architecture |
| `medit伙伴头像.png` | 伙伴形象（导入安装包时展示）— Avatar shown on import |
| `deploy_medit.py` | 一键部署引擎（**跨平台 Windows/macOS/Linux**）— One-step deploy engine (cross-platform): auto-fills all dependencies + DeepSeek CLI (mandatory) + API Key collected in chat + lark-cli binding + scheduler registration |

## 如何部署为飞书工作伙伴（1 步）/ Deploy as a Workmate (1 step)

1. **导入伙伴安装包 / Import the installer**: 豆包/飞书工作 →「插件·技能·伙伴 → 工作伙伴 → 创建新伙伴 → 从本地导入」，选择 Release 附件 `via54medit-workmate-installer-v5.4.51.zip`。
   Doubao/Feishu Work →「Plugins·Skills·Workmates → Workmates → Create → Import from local」→ pick the Release asset.

部署即完成：召唤伙伴后，伙伴自动执行跨平台部署引擎 `deploy_medit.py` 补全全部依赖；若缺 **DeepSeek API Key**，伙伴直接在对话中索取，回复 key 即完成部署。**全程无需打开终端，Windows / macOS / Linux 均可**。
That's it: when summoned, the workmate auto-runs `deploy_medit.py`; if the **DeepSeek API Key** is missing it asks you right in the chat — reply with the key and deployment is done. **No terminal required; works on Windows / macOS / Linux.**

完成后自动具备全部能力 / After deployment you get the full stack: 3-source EBM retrieval & fusion (PubMed/OpenAlex/S2)、PICO/GRADE、系统综述 systematic review、PPT 引用应证 citation verification、文献 highlight、DeepSeek 视觉 vision、medplan、飞书同步 Feishu sync、telemetry 遥测、实时多源用量采集（每 5 分钟）与周一校验标记（每 5-min usage collection & Monday finalization）。

## 架构（默认）/ Architecture (default)

```
豆包工作（伙伴主脑 / workmate brain）→ via54Medit（引擎，LLM 一律 --llm deepseek / engine, LLM always --llm deepseek）
→ DeepSeek-cli（chat/vision，自动埋点 / auto-instrumented）→ lark-cli → 飞书多维表格 Feishu Bitable
```

- **hermes / antfu（蚂蚁阿福）已剥离 / removed**: `--llm hermes`、`medit antfu` 均不可用；无需 Chrome CDP（no Chrome CDP needed）。
- **强制条件 / Mandatory**: DeepSeek CLI + API Key（缺失部署体检 FAIL 并提示输入 / deployment check FAILs and prompts for the key）。

## 版本对应 / Releases

| Release | 内容 / Content |
|---|---|
| v5.4.51 | **一步部署 + 跨平台（macOS/Windows/Linux）**：deploy_medit.py / deepseek.py 跨平台引擎、darwin 双架构二进制、伙伴对话内收集 API Key — One-step deploy + cross-platform engines, darwin dual-arch binaries, API Key collected in chat |
| v5.4.50 | DeepSeek 默认通道 + 剥离 hermes/antfu + 推理块剥离 + 伙伴包标准化 — DeepSeek default + hermes/antfu removed + reasoning-block stripping + standardized workmate package |
