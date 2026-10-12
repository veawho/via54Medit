# 飞书工作伙伴：循证医学助手 Medit（workmate 目录）

本目录是 via54Medit 仓库中**飞书（豆包）工作伙伴**的独立发布目录。伙伴安装包与技能上传包以 **GitHub Release 附件**形式发布（本目录只维护源码级配置），见仓库 Releases 页面 `v5.4.50+`。

## 目录内容

| 文件 | 用途 |
|---|---|
| `PARTNER.md` | 伙伴元信息：形象 / 人设 / 擅长领域 / 可调用技能 / 运行架构 |
| `medit伙伴头像.png` | 伙伴形象（导入安装包时展示） |
| `deploy_medit.py` | 一键部署引擎（**跨平台 Windows/macOS/Linux**）：自动补全全部依赖 + DeepSeek CLI 强制 + API Key 对话内收集 + lark-cli 绑定 + 定时任务注册 |

## 如何部署为飞书工作伙伴（1 步）

1. **导入伙伴安装包**：豆包/飞书客户端 →「插件·技能·伙伴 → 工作伙伴 → 创建新伙伴 → 从本地导入」，选择 Release 附件中的 `via54medit-workmate-installer-v5.4.51.zip`。

部署即完成：召唤伙伴后，伙伴自动检查并执行跨平台部署引擎 `deploy_medit.py`，补全全部依赖；若缺 **DeepSeek API Key**，伙伴直接在对话中向你索取，你回复 key 即完成全部部署。**全程无需打开终端，Windows / macOS 均可**。

完成后自动具备全部能力：3 源循证检索融合（PubMed/OpenAlex/S2）、PICO/GRADE、系统综述、PPT 引用应证、文献 highlight、DeepSeek 视觉、medplan、飞书同步、telemetry 遥测、实时多源用量采集（每 5 分钟）与周一校验标记。

## 架构（默认）

```
豆包工作（伙伴主脑）→ via54Medit（引擎，LLM 一律 --llm deepseek）
→ DeepSeek-cli（chat/vision，自动埋点）→ lark-cli → 飞书多维表格
```

- hermes、antfu（蚂蚁阿福）已剥离：`--llm hermes`、`medit antfu` 均不可用；无需 Chrome CDP。
- 强制条件：DeepSeek CLI 与 API Key（缺失部署体检 FAIL 并提示输入）。

## 版本对应

| Release | 内容 |
|---|---|
| v5.4.51 | **一步部署 + 跨平台（macOS/Windows/Linux）**：deploy_medit.py / deepseek.py 跨平台引擎、darwin 双架构二进制、伙伴对话内收集 API Key |
| v5.4.50 | DeepSeek 默认通道 + 剥离 hermes/antfu + 推理块剥离 + 伙伴包标准化 |
