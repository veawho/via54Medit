# GLM 学术数据处理集成参考 v2.0 (2026-08-07)

> 基于智谱官方文档: https://docs.bigmodel.cn/cn/best-practice/case/academic-data
>
> **v2.0 升级 (2026-08-07)**: 从自写 prompt 改成 **官方 4 大 Prompt 库 1:1 复刻**, 强制 `json.loads(content)["content"]` 官方响应解析, 强制 ThreadPoolExecutor 主入口结构。

## 官方权威入口 (v2.0)

**主文件**: `~/.hermes/skills/via54/glm_academic_official.py` (官方文档 1:1 复刻版)

**集成副本**: `~/.hermes/skills/devops/via54-highlight-strict/scripts/glm_literature_processor.py` (via54Medit 体系扩展, 包含医学专用 prompt)

## 强制使用的官方能力清单 (9 项)

| # | 官方能力 | 用途 | 调用点 |
|---|---|---|---|
| 1 | **file-extract API** | PDF/DOCX/PPT/XLSX/PNG/CSV/PY/TXT/MD (≤50MB) → 全文 | `extract_pdf_text(client, pdf_path)` |
| 2 | **官方 Prompt 1: extract_refs** | 论文关键信息抽取 | `extract_references(client, model, pdf_path)` |
| 3 | **官方 Prompt 2: summarize** | 论文内容总结 | `summarize_paper(client, model, pdf_path)` |
| 4 | **官方 Prompt 3: translate** | 论文内容翻译 | `translate_paper(client, model, pdf_path)` |
| 5 | **官方 Prompt 4: xiaohongshu** | 论文扩写润色 (小红书风格) | `rewrite_xiaohongshu(client, model, pdf_path)` |
| 6 | **ThreadPoolExecutor 主入口** | 批量并发处理 (官方推荐结构) | `batch_process_official(pdf_dir, model)` |
| 7 | **client.files.delete()** | 清理临时文件 (官方规范) | `extract_pdf_text` 自动调 |
| 8 | **`json.loads(content)["content"]`** | 官方响应解析 (不是 try/except) | `extract_pdf_text` 内置 |
| 9 | **glm-4-flash-250414** | 免费, 128K 上下文, 文献批处理首选 | 所有调用默认 model |

## 核心代码 (官方原版)

### 1. file-extract API (官方代码)

```python
from zhipuai import ZhipuAI
from pathlib import Path
import json

client = ZhipuAI(
    api_key="YOUR_API_KEY",
    base_url="https://open.bigmodel.cn/api/paas/v4"
)

# 上传文件 (官方代码原版)
file_object = client.files.create(file=Path("paper.pdf"), purpose="file-extract")
# 文件内容抽取 (官方代码原版 - 直接 json.loads)
file_content = json.loads(client.files.content(file_id=file_object.id).content)["content"]
# 清理临时文件 (官方代码原版)
client.files.delete(file_id=file_object.id)
```

### 2. 官方 4 大 Prompt 库 (来自官方文档原文)

**Prompt 1 - 论文关键信息抽取** (提取 authorName/title/journalName/publicationYear/publisherName/volumeName/issueNumber/pageNumbers):

```python
PROMPT_EXTRACT_REFS = """# Goals
你是一位精通总结领域趋势的专家...

# Constrains
- 必须遵循指定的格式进行信息提取。
- ...

# outformat
if (如果文本中没有文献引用) {
    return "{无}";
} else {
    return {
        {
            "authorName": "",
            "title": "",
            "journalName": "",
            "publicationYear": "",
            "publisherName": "",
            "volumeName": "",
            "issueNumber": "",
            "pageNumbers": ""
        }
    };
}
"""
```

**Prompt 2 - 论文内容总结**:

```python
PROMPT_SUMMARIZE = """# Goals
你是一位资深的教授, 擅长从学术论文中提炼出关键内容...

# outformat
{
    "文档标题": "",
    "主要内容": ""
}
"""
```

**Prompt 3 - 论文内容翻译**:

```python
PROMPT_TRANSLATE = """# Goal
你是一位精通翻译的专业人士...

# outformat
{
    "文档原文": "",
    "翻译结果": ""
}
"""
```

**Prompt 4 - 论文扩写润色 (小红书风格)**:

```python
PROMPT_REWRITE_XIAOHONGSHU = """# Goal
作为一位小红书科普账号的编辑...

# outformat
{
    "summary": ""
}
"""
```

**完整 4 prompt 见**: `glm_academic_official.py` 的 `PROMPT_*` 常量

### 3. 批量并发 (官方 ThreadPoolExecutor 主入口)

```python
# 官方代码原版
def get_all_files(folder_path):
    all_files = []
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            all_files.append(os.path.join(root, file))
    return all_files

if __name__ == '__main__':
    all_files = get_all_files("本地存储论文的文件夹路径")
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(process_file, file_path) for file_path in all_files]
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"Future 执行出错: {e}")
```

### 4. via54Medit 医学扩展 Prompt

**Prompt 5 - 医学文献关键信息** (在官方 Prompt 1 基础上扩展 medical_subject/clinical_relevance):

```python
PROMPT_EXTRACT_INFO_MEDICAL = """# Goals
你是一位精通医学文献整理的专家...

# Output Format (JSON)
{
  "title": "", "authors": "", "journal": "", "year": "",
  "volume": "", "issue": "", "pages": "", "doi": "", "pmid": "",
  "abstract": "", "key_findings": "", "study_type": "",
  "medical_subject": "",      // 医学主题 (TMA/aHUS/HSCT-TMA 等)
  "clinical_relevance": ""    // 临床意义
}
"""
```

**Prompt 6 - 应证段提取** (via54-highlight-strict 集成点):

```python
PROMPT_EXTRACT_EVIDENCE = """# Goals
你是一位医学文献应证段提取专家...

# Output Format
{
  "evidence_paragraphs": ["段落1", "段落2"],
  "evidence_location": "Methods/Results/Discussion",
  "relevance": "high/medium/low",
  "page_hint": "约第 X 页"
}

PPT 引用上下文: {citation_context}
"""
```

## 模型选择 (实测 2026-08-07)

| 模型 | 价格 | 上下文 | 实测 | 推荐用途 |
|------|------|--------|------|---------|
| **glm-4-flash-250414** | **免费** | 128K | ✅ 稳定 | **文献批处理首选** (官方默认) |
| glm-z1-flash | 免费 | 128K | ✅ 可用 | 推理任务备选 |
| glm-4.7-flash | 免费 | 200K | ❌ 429 限流严重 | 不推荐 |
| glm-4.5-air | ¥0.8/¥2-6 | 128K | ❌ 余额不足 | 需充值 |
| glm-5 (zai) | ¥4/¥18 | - | ✅ 主 Agent | 对话/工具/视觉 |

## 集成位置 (5 个 skill)

1. **`via54-highlight-strict`** (主算法 SOP) - Step 0 GLM 应证段文本预提取 + Step 3b 批量应证段
2. **`via54-citation-resolver-v3`** (下载链) - 下载后立即 GLM 内容提取
3. **`via54-medit`** (vision-understanding) - GLM 文本层在 vision 之前的预检
4. **`evidence-driven-bulk-pdf-highlight`** (43 Pn-x 批量) - GLM 文本层在关键词匹配前的预检
5. **`via54medit-literature-dir-init`** (本 reference) - 总体集成入口

## Python 环境注意

- `zhipuai` SDK 装在系统 Python (pip3 install zhipuai), **不在 execute_code sandbox**
- sandbox 内用 `requests` 直接调 API (绕过 SDK 限制)
- `GLM_API_KEY` 在 `~/.hermes/.env` 中, Hermes 运行时加载, sandbox 不继承
- 解决方案: `set -a && source ~/.hermes/.env && set +a` 让子进程继承

## 端到端验证 (2026-08-07)

- file-extract: 18490 字符 PDF 提取成功
- glm-4-flash-250414: 14.3s, 5496+600 tokens, ¥0
- 结果: title/authors/journal/year/doi/abstract 全部正确提取
- v2.0 升级: 集成 9 项官方能力, 5 个 skill 全部接入

## 脚本

- `scripts/glm_literature_processor.py` (via54-highlight-strict 副本, via54Medit 医学扩展)
  - `extract_refs` / `summarize` / `translate` / `xiaohongshu` (官方 4 prompt)
  - `extract_info` / `evidence` (via54Medit 医学扩展)
  - `batch_info` / `batch_evidence` (官方 ThreadPoolExecutor 主入口批量)

- `glm_academic_official.py` (via54 主目录, 官方文档 1:1 复刻 + via54Medit 扩展)
  - 完整官方代码, 5 个集成点统一调用