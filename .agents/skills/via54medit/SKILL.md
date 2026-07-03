---
name: via54medit
description: 运用 via54Medit CLI 并发检索 PubMed, OpenAlex 和 蚂蚁阿福 等医疗文献数据源，进行联合证据检索、去重、智能归纳与 PICO/GRADE 评估。
---

# via54medit 医疗文献循证技能 (Medical Evidence Retrieval Skill)

当用户提出任何医学临床问题、药物对比、心衰/疾病指南、系统综述或学术文献提取等任务时，你可以调用此技能来获取权威的循证医学（EBM）证据。

## 主要功能
1. **联合检索与归纳 (medit ask)**：并发查询多个数据库（含 PubMed、OpenAlex、蚂蚁阿福爬虫等），自动对文献进行去重融合，并生成智能总结。
2. **PICO要素抽取 (medit pico)**：从临床疑问中自动提取研究人群 (P)、干预措施 (I)、对照组 (C) 和结局指标 (O)。
3. **系统综述流水线 (medit systematic)**：一键全自动执行 PICO 提取 -> 检索 -> 去重 -> 智能归纳 -> GRADE 评分与存档。
4. **GRADE证据质量评级 (medit grade)**：对获取的证据包执行 GRADE 分级与原因推导。

## 使用指南

### 1. 联合证据问答 (EBM Question Answering)
在本地终端中运行以下命令。建议使用 `--json` 来获取完美的结构化 JSON 输出以便于解析：
```bash
./bin/medit ask "你的临床问题" --json
```

### 2. 多源去重联合文献搜索 (Evidence Search)
如果你只想获取去重后的文献列表而不进行 LLM 归纳总结，可以运行：
```bash
./bin/medit search "检索关键词" --json
```

### 3. 一键系统综述流水线 (Systematic Review Pipeline)
自动生成一个完整的系统综述会话包（自动存储在 `~/.medit/qa` 下），包含 PICO、检索文献、综述和 GRADE 等：
```bash
./bin/medit systematic "你的临床问题/干预对比"
```

### 4. 获取与评估已保存的综述包 (GRADE & List)
* 列出本地已归档的会话 ID 列表：
  ```bash
  ./bin/medit list
  ```
* 对特定的综述会话包（基于会话 ID，如 `conv-1783071596265309000`）执行 GRADE 评估：
  ```bash
  ./bin/medit grade <会话ID>
  ```
